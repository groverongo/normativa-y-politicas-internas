// normativa-rag: RAG sobre normativa SBS + políticas internas.
// Dependencias externas: Postgres (pgvector, vía github.com/jackc/pgx/v5 --
// mismo rol que modules/ingesta's S3DbStorage) + S3 (vía aws-sdk-go-v2 --
// mismo rol que modules/ingesta/modules/nttbanca-n), Voyage AI (o Jina) para
// embeddings/rerank, un LLM con API compatible con OpenAI (Gemini por
// defecto), y `pdftotext` (poppler-utils) para la ingesta.
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

type Config struct {
	EmbProvider, RerankProvider                    string // jina | voyage
	VoyageKey, VoyageEmbedModel, VoyageRerankModel string
	JinaKey, EmbedModel, RerankModel               string
	Dim                                            int // solo Jina (parámetro "dimensions")
	LLMBase, LLMKey, LLMModel, LLMEffort           string
	PriceIn, PriceOut                              float64 // USD por millón de tokens
	RegistryPath, Addr, CORSOrigin                 string
	RegistryBackend                                string // file (registry.json) | postgres (documents/document_lineage)

	// Postgres: mismas variables de entorno que modules/ingesta/config.py's
	// Settings (DB_PASSWORD se lee aparte, directo del entorno, en db.go).
	DBHost, DBPort, DBName, DBUser, DBSSLMode string
	DBConnectTimeout                          int

	// S3: mismas variables que modules/ingesta (raw text) y
	// modules/nttbanca-n/app/services/s3.py (S3Service).
	AWSRegion, S3BucketName, S3EndpointURL, S3KeyPrefix string
	S3PresignedURLExpiration                            int
}

func env(k, def string) string {
	if v := strings.TrimSpace(os.Getenv(k)); v != "" {
		return v
	}
	return def
}

func envFloat(k string, def float64) (float64, error) {
	s := env(k, "")
	if s == "" {
		return def, nil
	}
	f, err := strconv.ParseFloat(s, 64)
	if err != nil || f < 0 {
		return 0, fmt.Errorf("%s=%q no es un número válido", k, s)
	}
	return f, nil
}

func envInt(k string, def int) (int, error) {
	s := env(k, "")
	if s == "" {
		return def, nil
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0, fmt.Errorf("%s=%q no es un entero válido", k, s)
	}
	return n, nil
}

func cargarConfig() (Config, error) {
	dim, _ := strconv.Atoi(env("EMBED_DIM", "1024"))
	emb := strings.ToLower(env("EMB_PROVIDER", "voyage"))
	cfg := Config{
		EmbProvider:       emb,
		RerankProvider:    strings.ToLower(env("RERANK_PROVIDER", "voyage")),
		VoyageKey:         env("VOYAGE_API_KEY", ""),
		VoyageEmbedModel:  env("VOYAGE_EMBED_MODEL", "voyage-4"),
		VoyageRerankModel: env("VOYAGE_RERANK_MODEL", "rerank-2.5"),
		JinaKey:           env("JINA_API_KEY", ""),
		EmbedModel:        env("JINA_EMBED_MODEL", "jina-embeddings-v5-text-small"),
		RerankModel:       env("JINA_RERANK_MODEL", "jina-reranker-v3.5"),
		Dim:               dim,
		LLMBase:           env("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
		LLMKey:            env("LLM_API_KEY", ""),
		LLMModel:          env("LLM_MODEL", "gemini-3.8-flash"),
		LLMEffort:         strings.ToLower(env("LLM_REASONING_EFFORT", "low")),
		RegistryPath:      env("REGISTRY_PATH", "registry.json"),
		Addr:              env("ADDR", ":8080"),
		CORSOrigin:        env("CORS_ORIGIN", "*"),
		RegistryBackend:   strings.ToLower(env("REGISTRY_BACKEND", "file")),

		DBHost:    env("DB_HOST", ""),
		DBPort:    env("DB_PORT", "5432"),
		DBName:    env("DB_NAME", ""),
		DBUser:    env("DB_USER", ""),
		DBSSLMode: env("DB_SSLMODE", ""),

		AWSRegion:     env("AWS_REGION", ""),
		S3BucketName:  env("S3_BUCKET_NAME", ""),
		S3EndpointURL: env("S3_ENDPOINT_URL", ""),
		S3KeyPrefix:   env("S3_KEY_PREFIX", ""),
	}
	var err error
	if cfg.PriceIn, err = envFloat("LLM_PRICE_IN", 0.75); err != nil {
		return cfg, err
	}
	if cfg.PriceOut, err = envFloat("LLM_PRICE_OUT", 3.75); err != nil {
		return cfg, err
	}
	if cfg.DBConnectTimeout, err = envInt("DB_CONNECT_TIMEOUT", 10); err != nil {
		return cfg, err
	}
	if cfg.S3PresignedURLExpiration, err = envInt("S3_PRESIGNED_URL_EXPIRATION", 3600); err != nil {
		return cfg, err
	}
	return cfg, nil
}

var reGeminiVersion = regexp.MustCompile(`^gemini-(\d+)`)

// validarEffort: los modelos Gemini 3.x en adelante no permiten apagar el thinking.
func validarEffort(model, effort string) error {
	if effort != "none" {
		return nil
	}
	if m := reGeminiVersion.FindStringSubmatch(strings.ToLower(model)); m != nil {
		if v, _ := strconv.Atoi(m[1]); v >= 3 {
			return fmt.Errorf("LLM_REASONING_EFFORT=none no está soportado por %s (usá low, medium o high)", model)
		}
	}
	return nil
}

func faltantes(pares ...string) error {
	var f []string
	for i := 0; i+1 < len(pares); i += 2 {
		if pares[i+1] == "" {
			f = append(f, pares[i])
		}
	}
	if len(f) > 0 {
		return fmt.Errorf("faltan variables de entorno: %s", strings.Join(f, ", "))
	}
	return nil
}

func nuevoLLM(cfg Config) (*LLM, error) {
	if err := faltantes("LLM_API_KEY", cfg.LLMKey, "LLM_MODEL", cfg.LLMModel); err != nil {
		return nil, err
	}
	if err := validarEffort(cfg.LLMModel, cfg.LLMEffort); err != nil {
		return nil, err
	}
	return &LLM{base: cfg.LLMBase, key: cfg.LLMKey, model: cfg.LLMModel, effort: cfg.LLMEffort,
		priceIn: cfg.PriceIn, priceOut: cfg.PriceOut}, nil
}

// cargarRegistro elige la fuente del registro de vigencia según
// REGISTRY_BACKEND: "file" (default) sigue leyendo registry.json como
// siempre, sin requerir ningún servicio externo (lo que mantiene `ingest
// -dry` utilizable sin credenciales); "postgres" lo reconstruye desde la
// tabla compartida `documents` -- ver LoadRegistryFromDB.
func cargarRegistro(ctx context.Context, cfg Config, pool *pgxpool.Pool) (*Registry, error) {
	if cfg.RegistryBackend == "postgres" {
		return LoadRegistryFromDB(ctx, pool)
	}
	return LoadRegistry(cfg.RegistryPath)
}

// nuevoRAG valida solo lo que se va a usar: eval -norerank no pide el reranker
// y eval no pide el LLM. El vector store ya no es opcional/Qdrant: siempre es
// Postgres (pgvector), de ahí que reciba el pool ya abierto en vez de
// construir su propio cliente.
func nuevoRAG(cfg Config, reg *Registry, pool *pgxpool.Pool, conLLM, conRerank bool) (*RAG, error) {
	emb, err := nuevoEmbedder(cfg)
	if err != nil {
		return nil, err
	}
	r := &RAG{reg: reg, emb: emb, vs: nuevoPgVectorStore(pool)}
	if conRerank {
		if r.rr, err = nuevoReranker(cfg); err != nil {
			return nil, err
		}
	}
	if conLLM {
		if r.llm, err = nuevoLLM(cfg); err != nil {
			return nil, err
		}
	}
	return r, nil
}

func uso() {
	fmt.Fprint(os.Stderr, `uso:
  normativa-rag ingest [-dry] [-reset=true]   parsea, chunkea, embebe e indexa el corpus
  normativa-rag eval   [-f evals.json] [-k 5] [-norerank]   mide el retrieval (sin LLM)
  normativa-rag serve                          levanta la API HTTP
  normativa-rag healthcheck                    consulta /healthz local (para Docker)
`)
	os.Exit(2)
}

// healthcheck: la imagen distroless no trae curl ni shell, así que el propio
// binario consulta /healthz. No carga config ni registro: solo necesita ADDR.
func healthcheck() int {
	addr := env("ADDR", ":8080")
	if strings.HasPrefix(addr, ":") {
		addr = "127.0.0.1" + addr
	}
	c := http.Client{Timeout: 3 * time.Second}
	resp, err := c.Get("http://" + addr + "/healthz")
	if err != nil {
		log.Print(err)
		return 1
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		log.Printf("healthz: %s", resp.Status)
		return 1
	}
	return 0
}

func main() {
	log.SetFlags(0)
	if len(os.Args) < 2 {
		uso()
	}
	cmd, args := os.Args[1], os.Args[2:]
	if cmd == "healthcheck" {
		os.Exit(healthcheck())
	}
	cfg, err := cargarConfig()
	if err != nil {
		log.Fatal(err)
	}
	ctx := context.Background()

	switch cmd {
	case "ingest":
		fs := flag.NewFlagSet("ingest", flag.ExitOnError)
		dry := fs.Bool("dry", false, "solo parsea y escribe chunks.jsonl (no gasta créditos)")
		reset := fs.Bool("reset", true, "borra y recrea los embeddings antes de indexar")
		fs.Parse(args)

		if *dry {
			// -dry nunca toca servicios externos: ni Postgres ni S3, solo
			// corpus/ + registry.json local, igual que antes.
			reg, errReg := LoadRegistry(cfg.RegistryPath)
			if errReg != nil {
				log.Fatalf("registro de vigencia: %v", errReg)
			}
			err = runIngest(ctx, cfg, reg, nil, nil, *reset, true)
			break
		}
		pool, errDB := nuevoDB(ctx, cfg)
		if errDB != nil {
			log.Fatal(errDB)
		}
		defer pool.Close()
		s3, errS3 := nuevoS3(ctx, cfg)
		if errS3 != nil {
			log.Fatal(errS3)
		}
		reg, errReg := cargarRegistro(ctx, cfg, pool)
		if errReg != nil {
			log.Fatalf("registro de vigencia: %v", errReg)
		}
		err = runIngest(ctx, cfg, reg, pool, s3, *reset, false)
	case "eval":
		fs := flag.NewFlagSet("eval", flag.ExitOnError)
		file := fs.String("f", "evals.json", "archivo de preguntas golden")
		k := fs.Int("k", 5, "top-k a evaluar")
		norerank := fs.Bool("norerank", false, "evaluar sin reranker (para comparar)")
		fs.Parse(args)
		pool, errDB := nuevoDB(ctx, cfg)
		if errDB != nil {
			log.Fatal(errDB)
		}
		defer pool.Close()
		reg, errReg := cargarRegistro(ctx, cfg, pool)
		if errReg != nil {
			log.Fatalf("registro de vigencia: %v", errReg)
		}
		var rag *RAG
		if rag, err = nuevoRAG(cfg, reg, pool, false, !*norerank); err == nil {
			err = runEval(ctx, rag, *file, *k, !*norerank)
		}
	case "serve":
		pool, errDB := nuevoDB(ctx, cfg)
		if errDB != nil {
			log.Fatal(errDB)
		}
		defer pool.Close()
		reg, errReg := cargarRegistro(ctx, cfg, pool)
		if errReg != nil {
			log.Fatalf("registro de vigencia: %v", errReg)
		}
		var rag *RAG
		if rag, err = nuevoRAG(cfg, reg, pool, true, true); err == nil {
			err = runServe(cfg, rag)
		}
	default:
		uso()
	}
	if err != nil {
		log.Fatal(err)
	}
}
