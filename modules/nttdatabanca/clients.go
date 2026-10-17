package main

import (
	"context"
	"fmt"
	"log"
	"sort"
)

// ---------- Jina (embeddings + rerank) ----------

var jinaBase = "https://api.jina.ai/v1" // var (no const) para poder apuntarlo a un fake en tests

type Jina struct {
	key, embedModel, rerankModel string
	dim                          int
}

func (j *Jina) headers() map[string]string {
	return map[string]string{"Authorization": "Bearer " + j.key}
}

// EmbedDocs / EmbedQuery usan task "retrieval.passage" para indexar y
// "retrieval.query" para preguntas (embeddings asimétricos: la pregunta y el
// artículo se embeben distinto).
func (j *Jina) EmbedDocs(ctx context.Context, texts []string) ([][]float32, error) {
	return j.embed(ctx, texts, "retrieval.passage")
}

func (j *Jina) EmbedQuery(ctx context.Context, text string) ([]float32, error) {
	vecs, err := j.embed(ctx, []string{text}, "retrieval.query")
	if err != nil {
		return nil, err
	}
	return vecs[0], nil
}

func (j *Jina) embed(ctx context.Context, textos []string, task string) ([][]float32, error) {
	const lote = 32
	out := make([][]float32, 0, len(textos))
	for i := 0; i < len(textos); i += lote {
		fin := min(i+lote, len(textos))
		req := map[string]any{"model": j.embedModel, "task": task, "input": textos[i:fin]}
		if j.dim > 0 {
			req["dimensions"] = j.dim
		}
		var resp struct {
			Data []struct {
				Index     int       `json:"index"`
				Embedding []float32 `json:"embedding"`
			} `json:"data"`
		}
		if err := doJSON(ctx, politicaProveedor, "POST", jinaBase+"/embeddings", j.headers(), req, &resp); err != nil {
			return nil, fmt.Errorf("jina embeddings: %w", err)
		}
		if len(resp.Data) != fin-i {
			return nil, fmt.Errorf("jina embeddings: pedí %d, volvieron %d", fin-i, len(resp.Data))
		}
		sort.Slice(resp.Data, func(a, b int) bool { return resp.Data[a].Index < resp.Data[b].Index })
		for _, d := range resp.Data {
			out = append(out, d.Embedding)
		}
		if len(textos) > lote {
			log.Printf("  embeddings %d/%d", fin, len(textos))
		}
	}
	return out, nil
}

func (j *Jina) Rerank(ctx context.Context, query string, docs []string, topK int) ([]RerankResult, error) {
	req := map[string]any{"model": j.rerankModel, "query": query, "documents": docs, "top_n": topK, "return_documents": false}
	var resp struct {
		Results []struct {
			Index int     `json:"index"`
			Score float64 `json:"relevance_score"`
		} `json:"results"`
	}
	if err := doJSON(ctx, politicaProveedor, "POST", jinaBase+"/rerank", j.headers(), req, &resp); err != nil {
		return nil, fmt.Errorf("jina rerank: %w", err)
	}
	out := make([]RerankResult, 0, len(resp.Results))
	for _, r := range resp.Results {
		if r.Index >= 0 && r.Index < len(docs) {
			out = append(out, RerankResult{Index: r.Index, Score: r.Score})
		}
	}
	return out, nil
}

// Qdrant fue reemplazado por PgVectorStore (pgvectorstore.go): los embeddings
// y la búsqueda híbrida ahora viven en Postgres (pgvector + tsvector/GIN),
// ver la migración 0009_nttdatabanca_rag_support.sql.
