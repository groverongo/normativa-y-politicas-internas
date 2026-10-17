package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode"
	"unicode/utf8"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Chunk struct {
	ChunkID string `json:"chunk_id"`
	DocID   string `json:"doc_id"`
	Ruta    string `json:"ruta"`
	Pagina  int    `json:"pagina"`
	Texto   string `json:"texto"`
}

const maxChunkChars = 3000 // ~750 tokens

var (
	// "Artículo 5.-", "Artículo 5°.-", "Artículo Primero.-", "Artículo Décimo Segundo.-",
	// "ARTÍCULO 4.-", y "## Artículo 3.-" en los .md sintéticos. Exige el guion para
	// no cortar en referencias del tipo "conforme al artículo 5 del Reglamento".
	reArticulo = regexp.MustCompile(`(?im)^[ \t]*(?:#+[ \t]*)?art[íi]culo[ \t]+([0-9]+[°º]?|[a-záéíóúñ]+(?:[ \t]+[a-záéíóúñ]+)?)[ \t]*\.?[ \t]*[-–—]`)
	// "regla-\nmento" → "reglamento"
	reGuion = regexp.MustCompile(`(\p{L})-\n[ \t]*(\p{Ll})`)
)

func leerPaginas(path string) ([]string, error) {
	switch strings.ToLower(filepath.Ext(path)) {
	case ".md", ".txt":
		b, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		return strings.Split(string(b), "\f"), nil
	case ".pdf":
		// Sin -layout: El Peruano publica a varias columnas y el modo por defecto
		// respeta mejor el orden de lectura. pdftotext separa páginas con \f.
		out, err := exec.Command("pdftotext", "-enc", "UTF-8", path, "-").Output()
		if err != nil {
			return nil, fmt.Errorf("pdftotext %s: %w (¿está instalado poppler-utils?)", path, err)
		}
		pages := strings.Split(string(out), "\f")
		if n := len(pages); n > 1 && strings.TrimSpace(pages[n-1]) == "" {
			pages = pages[:n-1]
		}
		return pages, nil
	}
	return nil, fmt.Errorf("formato no soportado: %s", path)
}

func chunkear(docID string, pages []string) []Chunk {
	var sb strings.Builder
	starts := make([]int, len(pages))
	for i, p := range pages {
		starts[i] = sb.Len()
		sb.WriteString(reGuion.ReplaceAllString(p, "$1$2"))
		sb.WriteString("\n")
	}
	text := sb.String()
	pagina := func(off int) int {
		return sort.Search(len(starts), func(i int) bool { return starts[i] > off })
	}

	type tramo struct {
		ruta     string
		ini, fin int
	}
	var tramos []tramo
	locs := reArticulo.FindAllStringSubmatchIndex(text, -1)
	if len(locs) == 0 {
		tramos = append(tramos, tramo{"Documento", 0, len(text)})
	} else {
		if pre := strings.TrimSpace(text[:locs[0][0]]); len(pre) > 200 {
			tramos = append(tramos, tramo{"Preámbulo", 0, locs[0][0]})
		}
		for i, l := range locs {
			fin := len(text)
			if i+1 < len(locs) {
				fin = locs[i+1][0]
			}
			tramos = append(tramos, tramo{"Artículo " + nombreArticulo(text[l[2]:l[3]]), l[0], fin})
		}
	}

	var chunks []Chunk
	usados := map[string]int{}
	for _, t := range tramos {
		partes := partir(text, t.ini, t.fin)
		for j, p := range partes {
			ruta := t.ruta
			if len(partes) > 1 {
				ruta = fmt.Sprintf("%s (parte %d)", t.ruta, j+1)
			}
			texto := strings.Join(strings.Fields(text[p[0]:p[1]]), " ")
			if texto == "" {
				continue
			}
			id := docID + "#" + slug(ruta)
			usados[id]++
			if n := usados[id]; n > 1 { // ej: un reglamento anexo con su propio "Artículo 1"
				id = fmt.Sprintf("%s-%d", id, n)
			}
			chunks = append(chunks, Chunk{ChunkID: id, DocID: docID, Ruta: ruta, Pagina: pagina(p[0]), Texto: texto})
		}
	}
	return chunks
}

// partir corta tramos largos en fin de oración / línea, sin romper runas UTF-8.
func partir(text string, ini, fin int) [][2]int {
	var out [][2]int
	for fin-ini > maxChunkChars {
		desde, limite := ini+maxChunkChars/2, ini+maxChunkChars
		ventana := text[desde:limite]
		corte := limite
		for _, sep := range []string{".\n", ". ", "\n"} {
			if i := strings.LastIndex(ventana, sep); i >= 0 {
				corte = desde + i + len(sep)
				break
			}
		}
		for corte > ini && corte < len(text) && !utf8.RuneStart(text[corte]) {
			corte--
		}
		out = append(out, [2]int{ini, corte})
		ini = corte
	}
	return append(out, [2]int{ini, fin})
}

func nombreArticulo(s string) string {
	s = strings.TrimSpace(strings.Trim(s, "°º"))
	if s != "" && unicode.IsDigit(rune(s[0])) {
		return s
	}
	palabras := strings.Fields(strings.ToLower(s))
	for i, p := range palabras {
		r, n := utf8.DecodeRuneInString(p)
		palabras[i] = string(unicode.ToUpper(r)) + p[n:]
	}
	return strings.Join(palabras, " ")
}

func slug(s string) string {
	var b strings.Builder
	guion := false
	for _, r := range sinAcentos(s) {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
			guion = false
		} else if !guion && b.Len() > 0 {
			b.WriteByte('-')
			guion = true
		}
	}
	return strings.TrimSuffix(b.String(), "-")
}

// conEncabezado es el "contextual chunk header": se embebe y se rerankea con
// el nombre del documento y el artículo adelante, pero se guarda sin él.
func conEncabezado(reg *Registry, c Chunk) string {
	cab := c.DocID
	if d, ok := reg.Get(c.DocID); ok {
		cab = d.Label()
	}
	return cab + " — " + c.Ruta + "\n" + c.Texto
}

type docIngestado struct {
	doc    *Doc
	pages  []string
	chunks []Chunk
}

func runIngest(ctx context.Context, cfg Config, reg *Registry, pool *pgxpool.Pool, s3 *S3Store, reset, dry bool) error {
	base := filepath.Dir(cfg.RegistryPath)
	var chunks []Chunk
	var docs []docIngestado
	for _, d := range reg.Docs() {
		if d.Archivo == "" {
			log.Printf("· %s: sin archivo, se saltea", d.ID)
			continue
		}
		path := d.Archivo
		if !filepath.IsAbs(path) {
			path = filepath.Join(base, path)
		}
		if _, err := os.Stat(path); err != nil {
			log.Printf("! %-28s no encuentro %s, se saltea", d.ID, path)
			continue
		}
		pages, err := leerPaginas(path)
		if err != nil {
			return err
		}
		cs := chunkear(d.ID, pages)
		log.Printf("· %-28s %3d págs → %3d chunks", d.ID, len(pages), len(cs))
		chunks = append(chunks, cs...)
		docs = append(docs, docIngestado{doc: d, pages: pages, chunks: cs})
	}
	if err := escribirJSONL("chunks.jsonl", chunks); err != nil {
		return err
	}
	log.Printf("total: %d chunks (revisalos en chunks.jsonl)", len(chunks))
	if dry || len(chunks) == 0 {
		return nil
	}

	emb, err := nuevoEmbedder(cfg)
	if err != nil {
		return err
	}
	vs := nuevoPgVectorStore(pool)

	for _, di := range docs {
		if err := persistirDocumento(ctx, pool, s3, di); err != nil {
			return fmt.Errorf("persistir %s en Postgres/S3: %w", di.doc.ID, err)
		}
	}
	log.Printf("documentos, chunks y lineage escritos en Postgres; texto crudo subido a S3 ✓")

	textos := make([]string, len(chunks))
	for i, c := range chunks {
		textos[i] = conEncabezado(reg, c)
	}

	vecs, err := emb.EmbedDocs(ctx, textos)
	if err != nil {
		return err
	}
	if len(vecs) != len(chunks) || len(vecs[0]) == 0 {
		return fmt.Errorf("el embedder devolvió %d vectores para %d chunks", len(vecs), len(chunks))
	}
	if err := vs.Asegurar(ctx, len(vecs[0]), reset); err != nil {
		return fmt.Errorf("preparar chunk_vectors: %w", err)
	}
	items := make([]VectorItem, len(chunks))
	for i, c := range chunks {
		items[i] = VectorItem{Chunk: c, Vector: vecs[i], Model: cfg.EmbedModel}
	}
	if err := vs.Upsert(ctx, items); err != nil {
		return err
	}
	log.Printf("indexados %d chunks en chunk_vectors (Postgres/pgvector) ✓", len(items))
	return nil
}

// persistirDocumento sube el texto crudo del documento a S3 (documents.source_uri)
// y escribe sus filas en documents/chunks/document_lineage -- el mismo
// trabajo que modules/ingesta/storage.py's S3DbStorage.put_document hace para
// su propio corpus, aplicado al de nttdatabanca.
func persistirDocumento(ctx context.Context, pool *pgxpool.Pool, s3 *S3Store, di docIngestado) error {
	d := di.doc
	rawText := strings.Join(di.pages, "\n\f\n")
	sourceURI, err := s3.PutRawText(ctx, d.ID, rawText)
	if err != nil {
		return err
	}

	status := "ACTIVE"
	if d.DerogadoPor != "" {
		status = "REVOKED"
	}
	var validFrom *string
	if d.VigenteDesde != "" {
		validFrom = &d.VigenteDesde
	} else if d.Fecha != "" {
		validFrom = &d.Fecha
	}
	var numero, url *string
	if d.Numero != "" {
		numero = &d.Numero
	}
	if d.URL != "" {
		url = &d.URL
	}

	_, err = pool.Exec(ctx, `
		INSERT INTO documents (doc_id, doc_type, title, issuer, source_uri, status, valid_from, external_code, external_url)
		VALUES ($1, $2, $3, '', $4, $5, $6::date, $7, $8)
		ON CONFLICT (doc_id) DO UPDATE SET
			doc_type = EXCLUDED.doc_type, title = EXCLUDED.title, source_uri = EXCLUDED.source_uri,
			status = EXCLUDED.status, valid_from = EXCLUDED.valid_from,
			external_code = EXCLUDED.external_code, external_url = EXCLUDED.external_url`,
		d.ID, d.Tipo, d.Titulo, sourceURI, status, validFrom, numero, url)
	if err != nil {
		return fmt.Errorf("documents: %w", err)
	}

	batch := &pgx.Batch{}
	for idx, c := range di.chunks {
		batch.Queue(`
			INSERT INTO chunks (chunk_id, doc_id, chunk_index, text, section_label, page_number)
			VALUES ($1, $2, $3, $4, $5, $6)
			ON CONFLICT (chunk_id) DO UPDATE SET
				text = EXCLUDED.text, section_label = EXCLUDED.section_label,
				page_number = EXCLUDED.page_number, chunk_index = EXCLUDED.chunk_index`,
			c.ChunkID, c.DocID, idx, c.Texto, c.Ruta, c.Pagina)
	}
	batch.Queue(`DELETE FROM document_lineage WHERE doc_id = $1 AND relation IN ('revoked_by', 'patched_by')`, d.ID)
	if d.DerogadoPor != "" {
		batch.Queue(`INSERT INTO document_lineage (doc_id, relation, target_doc_id) VALUES ($1, 'revoked_by', $2)
			ON CONFLICT (doc_id, relation, target_doc_id) DO NOTHING`, d.ID, d.DerogadoPor)
	}
	for _, m := range d.ModificadoPor {
		batch.Queue(`INSERT INTO document_lineage (doc_id, relation, target_doc_id) VALUES ($1, 'patched_by', $2)
			ON CONFLICT (doc_id, relation, target_doc_id) DO NOTHING`, d.ID, m)
	}
	br := pool.SendBatch(ctx, batch)
	n := len(di.chunks) + 1 + len(d.ModificadoPor)
	if d.DerogadoPor != "" {
		n++
	}
	for i := 0; i < n; i++ {
		if _, err := br.Exec(); err != nil {
			br.Close()
			return fmt.Errorf("chunks/document_lineage: %w", err)
		}
	}
	return br.Close()
}

func escribirJSONL(path string, chunks []Chunk) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	w := bufio.NewWriter(f)
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	for _, c := range chunks {
		if err := enc.Encode(c); err != nil {
			return err
		}
	}
	return w.Flush()
}
