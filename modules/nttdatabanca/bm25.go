package main

import (
	"strings"
)

// sinAcentos: usado para normalizar texto en la validación de citas (rag.go)
// y en los slugs de chunk_id (ingest.go). El ranking léxico de la búsqueda
// híbrida (antes BM25 sobre Qdrant) ahora lo hace Postgres directamente sobre
// chunks.tsv -- ver pgvectorstore.go y la migración
// 0009_nttdatabanca_rag_support.sql.
var acentos = strings.NewReplacer("á", "a", "é", "e", "í", "i", "ó", "o", "ú", "u", "ü", "u", "ñ", "n",
	"à", "a", "è", "e", "ì", "i", "ò", "o", "ù", "u")

func sinAcentos(s string) string { return acentos.Replace(strings.ToLower(s)) }
