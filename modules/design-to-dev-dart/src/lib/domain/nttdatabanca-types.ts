/**
 * TypeScript mirrors of modules/nttdatabanca's POST /ask response shape
 * (rag.go's Respuesta/Cita/Contradiccion/Resultado/Alerta structs). Field
 * names match the JSON the Go API returns verbatim (snake_case json tags).
 * Keep in sync with rag.go if that contract changes.
 */

export interface NttdatabancaCitaDTO {
  chunk_id: string;
  cita_textual: string;
  documento: string;
  ruta: string;
  pagina: number;
  estado: string;
  url?: string;
}

export interface NttdatabancaContradiccionDTO {
  chunk_a: string;
  chunk_b: string;
  explicacion: string;
  prevalece?: string;
  criterio: string;
}

export interface NttdatabancaAlertaDTO {
  tipo: string;
  doc_id: string;
  detalle: string;
}

export interface NttdatabancaResultadoDTO {
  chunk_id: string;
  doc_id: string;
  documento: string;
  tipo: string;
  estado: string;
  ruta: string;
  pagina: number;
  url?: string;
  texto: string;
  score: number;
  reemplazo?: boolean;
}

export interface NttdatabancaRespuestaDTO {
  respuesta: string;
  sin_respuesta: boolean;
  citas: NttdatabancaCitaDTO[];
  citas_descartadas: number;
  contradicciones: NttdatabancaContradiccionDTO[];
  alertas: NttdatabancaAlertaDTO[];
  fuentes: NttdatabancaResultadoDTO[];
}
