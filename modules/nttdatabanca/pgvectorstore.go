package main

import (
	"context"
	"fmt"
	"log"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// VectorStore reemplaza a Qdrant: el resto del código (ingest, rag) depende
// solo de esta interfaz, no de Postgres concretamente -- mismo patrón de
// "seam" que modules/ingesta's StorageInterface (memoria vs. Postgres real).
// FakeVectorStore (en rag_test.go) la implementa para los tests, sin
// necesitar una base real.
type VectorStore interface {
	// Info devuelve la dimensión de los vectores ya indexados, o existe=false
	// si todavía no hay ninguno.
	Info(ctx context.Context) (dim int, existe bool, err error)
	// Asegurar dejá el store listo para vectores de dimensión dim: si reset,
	// borra lo que había; si no, falla con errDim ante una dimensión distinta.
	Asegurar(ctx context.Context, dim int, reset bool) error
	Upsert(ctx context.Context, items []VectorItem) error
	// Hibrida combina búsqueda densa (coseno) y léxica (texto completo),
	// fusionadas por reciprocal rank fusion -- ver fusionarRRF.
	Hibrida(ctx context.Context, dense []float32, queryText string, boost []string, limit int) ([]Hit, error)
	DenseEnDocs(ctx context.Context, dense []float32, ids []string, limit int) ([]Hit, error)
}

type VectorItem struct {
	Chunk  Chunk
	Vector []float32
	Model  string
}

type Hit struct {
	Score   float64 `json:"score"`
	Payload Chunk   `json:"payload"`
}

func errDim(nombre string, actual, nueva int) error {
	return fmt.Errorf("%q ya tiene vectores de dimensión %d, pero el embedder devuelve dimensión %d "+
		"(usá `ingest -reset` o cambiá EMB_PROVIDER/EMBED_DIM)", nombre, actual, nueva)
}

// PgVectorStore guarda los embeddings en la tabla chunk_vectors (migración
// 0009_nttdatabanca_rag_support.sql) y usa chunks.tsv (generado por Postgres)
// para la parte léxica -- ver esa migración para el porqué de cada columna.
type PgVectorStore struct {
	pool *pgxpool.Pool
}

func nuevoPgVectorStore(pool *pgxpool.Pool) *PgVectorStore {
	return &PgVectorStore{pool: pool}
}

func (s *PgVectorStore) Info(ctx context.Context) (int, bool, error) {
	var dim int
	err := s.pool.QueryRow(ctx, "SELECT dim FROM chunk_vectors LIMIT 1").Scan(&dim)
	if err == pgx.ErrNoRows {
		return 0, false, nil
	}
	if err != nil {
		return 0, false, fmt.Errorf("chunk_vectors info: %w", err)
	}
	return dim, true, nil
}

func (s *PgVectorStore) Asegurar(ctx context.Context, dim int, reset bool) error {
	actual, existe, err := s.Info(ctx)
	if err != nil {
		return err
	}
	if !existe {
		return nil
	}
	if !reset {
		if actual != dim {
			return errDim("chunk_vectors", actual, dim)
		}
		return nil
	}
	log.Printf("reset: borro chunk_vectors (dimensión vieja=%d, nueva=%d)", actual, dim)
	if _, err := s.pool.Exec(ctx, "TRUNCATE chunk_vectors"); err != nil {
		return fmt.Errorf("truncar chunk_vectors: %w", err)
	}
	return nil
}

func vectorLiteral(v []float32) string {
	var b strings.Builder
	b.WriteByte('[')
	for i, f := range v {
		if i > 0 {
			b.WriteByte(',')
		}
		b.WriteString(strconv.FormatFloat(float64(f), 'f', -1, 32))
	}
	b.WriteByte(']')
	return b.String()
}

// Upsert inserta/actualiza de a lotes, igual que Qdrant.Upsert (idempotente:
// chunk_id es la clave primaria de chunk_vectors).
func (s *PgVectorStore) Upsert(ctx context.Context, items []VectorItem) error {
	const lote = 200
	for i := 0; i < len(items); i += lote {
		fin := min(i+lote, len(items))
		batch := &pgx.Batch{}
		for _, it := range items[i:fin] {
			batch.Queue(
				`INSERT INTO chunk_vectors (chunk_id, doc_id, embedding, dim, model)
				 VALUES ($1, $2, $3::vector, $4, $5)
				 ON CONFLICT (chunk_id) DO UPDATE
				 SET embedding = EXCLUDED.embedding, dim = EXCLUDED.dim, model = EXCLUDED.model`,
				it.Chunk.ChunkID, it.Chunk.DocID, vectorLiteral(it.Vector), len(it.Vector), it.Model,
			)
		}
		br := s.pool.SendBatch(ctx, batch)
		for range items[i:fin] {
			if _, err := br.Exec(); err != nil {
				br.Close()
				return fmt.Errorf("chunk_vectors upsert: %w", err)
			}
		}
		if err := br.Close(); err != nil {
			return fmt.Errorf("chunk_vectors upsert: %w", err)
		}
	}
	return nil
}

func scanHits(rows pgx.Rows) ([]Hit, error) {
	defer rows.Close()
	var out []Hit
	for rows.Next() {
		var h Hit
		var ruta *string
		var pagina *int
		if err := rows.Scan(&h.Payload.ChunkID, &h.Payload.DocID, &ruta, &pagina, &h.Payload.Texto, &h.Score); err != nil {
			return nil, err
		}
		if ruta != nil {
			h.Payload.Ruta = *ruta
		}
		if pagina != nil {
			h.Payload.Pagina = *pagina
		}
		out = append(out, h)
	}
	return out, rows.Err()
}

const denseSQL = `
	SELECT c.chunk_id, c.doc_id, c.section_label, c.page_number, c.text,
	       1 - (cv.embedding <=> $1::vector) AS score
	FROM chunk_vectors cv JOIN chunks c USING (chunk_id)
	ORDER BY cv.embedding <=> $1::vector
	LIMIT $2`

const denseEnDocsSQL = `
	SELECT c.chunk_id, c.doc_id, c.section_label, c.page_number, c.text,
	       1 - (cv.embedding <=> $1::vector) AS score
	FROM chunk_vectors cv JOIN chunks c USING (chunk_id)
	WHERE cv.doc_id = ANY($2)
	ORDER BY cv.embedding <=> $1::vector
	LIMIT $3`

const lexicalSQL = `
	SELECT chunk_id, doc_id, section_label, page_number, text,
	       ts_rank_cd(tsv, websearch_to_tsquery('spanish', $1)) AS score
	FROM chunks
	WHERE tsv @@ websearch_to_tsquery('spanish', $1)
	ORDER BY score DESC
	LIMIT $2`

const boostSQL = `
	SELECT c.chunk_id, c.doc_id, c.section_label, c.page_number, c.text,
	       1 - (cv.embedding <=> $1::vector) AS score
	FROM chunk_vectors cv JOIN chunks c USING (chunk_id)
	WHERE cv.doc_id = ANY($2)
	ORDER BY cv.embedding <=> $1::vector
	LIMIT 10`

// rrfK es la constante estándar de reciprocal rank fusion (1/(k+rank)); 60 es
// el valor usado por la mayoría de las implementaciones de referencia.
const rrfK = 60.0

// fusionarRRF combina varias listas ya ordenadas por relevancia en un único
// ranking, igual que el fusion:"rrf" nativo de Qdrant sobre sus prefetch.
func fusionarRRF(listas ...[]Hit) []Hit {
	puntaje := map[string]float64{}
	porID := map[string]Hit{}
	for _, lista := range listas {
		for rank, h := range lista {
			puntaje[h.Payload.ChunkID] += 1 / (rrfK + float64(rank+1))
			if _, ok := porID[h.Payload.ChunkID]; !ok {
				porID[h.Payload.ChunkID] = h
			}
		}
	}
	out := make([]Hit, 0, len(porID))
	for id, h := range porID {
		h.Score = puntaje[id]
		out = append(out, h)
	}
	sortHitsByScoreDesc(out)
	return out
}

func sortHitsByScoreDesc(hits []Hit) {
	for i := 1; i < len(hits); i++ {
		for j := i; j > 0 && hits[j].Score > hits[j-1].Score; j-- {
			hits[j], hits[j-1] = hits[j-1], hits[j]
		}
	}
}

// Hibrida: dense (pgvector, distancia coseno) + léxico (tsvector/GIN de
// Postgres) + un boost opcional filtrado por doc_id, fusionados con RRF.
// Reemplaza el fusion:"rrf" server-side de Qdrant sobre dense+bm25.
func (s *PgVectorStore) Hibrida(ctx context.Context, dense []float32, queryText string, boost []string, limit int) ([]Hit, error) {
	vec := vectorLiteral(dense)

	rows, err := s.pool.Query(ctx, denseSQL, vec, limit)
	if err != nil {
		return nil, fmt.Errorf("pgvector dense: %w", err)
	}
	denseHits, err := scanHits(rows)
	if err != nil {
		return nil, fmt.Errorf("pgvector dense: %w", err)
	}

	listas := [][]Hit{denseHits}
	if strings.TrimSpace(queryText) != "" {
		rows, err := s.pool.Query(ctx, lexicalSQL, queryText, limit)
		if err != nil {
			return nil, fmt.Errorf("postgres fts: %w", err)
		}
		lexHits, err := scanHits(rows)
		if err != nil {
			return nil, fmt.Errorf("postgres fts: %w", err)
		}
		listas = append(listas, lexHits)
	}
	if len(boost) > 0 {
		rows, err := s.pool.Query(ctx, boostSQL, vec, boost)
		if err != nil {
			return nil, fmt.Errorf("pgvector boost: %w", err)
		}
		boostHits, err := scanHits(rows)
		if err != nil {
			return nil, fmt.Errorf("pgvector boost: %w", err)
		}
		listas = append(listas, boostHits)
	}

	fused := fusionarRRF(listas...)
	if len(fused) > limit {
		fused = fused[:limit]
	}
	return fused, nil
}

func (s *PgVectorStore) DenseEnDocs(ctx context.Context, dense []float32, ids []string, limit int) ([]Hit, error) {
	rows, err := s.pool.Query(ctx, denseEnDocsSQL, vectorLiteral(dense), ids, limit)
	if err != nil {
		return nil, fmt.Errorf("pgvector dense-en-docs: %w", err)
	}
	return scanHits(rows)
}
