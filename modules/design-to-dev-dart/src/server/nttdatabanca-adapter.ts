import type { ConsultAnswer, EvidenceFragment } from "@/lib/domain/types";
import type {
  NttdatabancaCitaDTO,
  NttdatabancaRespuestaDTO,
} from "@/lib/domain/nttdatabanca-types";

/**
 * nttdatabanca's /ask returns one free-text "respuesta" with inline
 * [chunk_id] citation markers, plus separate validated citas/alertas/
 * contradicciones -- it has no notion of ConsultAnswer's "title" or
 * "interpretation" fields. This adapter synthesizes a title from the
 * response's shape (sin_respuesta / contradicciones present), strips the
 * inline citation markers from the display text (the "evidence" cards
 * already carry that detail), and leaves interpretation null rather than
 * inventing editorializing the backend never produced.
 */

const CITATION_MARKER_RE = /\s*\[[^\]\s][^\]]*\]/g;

function stripCitationMarkers(text: string): string {
  return text.replace(CITATION_MARKER_RE, "").trim();
}

const VERSION_RE = /\bv(\d+(?:\.\d+)?)\b/i;

function extractVersion(documento: string): string {
  const match = VERSION_RE.exec(documento);
  return match ? `v${match[1]}` : "";
}

function docIdFromChunkId(chunkId: string): string {
  return chunkId.split("#")[0] ?? chunkId;
}

function citaToEvidenceFragment(cita: NttdatabancaCitaDTO): EvidenceFragment {
  return {
    code: docIdFromChunkId(cita.chunk_id),
    title: cita.documento,
    version: extractVersion(cita.documento),
    section: cita.ruta || null,
    page: cita.pagina > 0 ? String(cita.pagina) : null,
    quote: cita.cita_textual,
    why:
      cita.estado === "vigente"
        ? "Cita validada contra el fragmento recuperado."
        : `Fuente en estado "${cita.estado}".`,
  };
}

function pickLevel(resp: NttdatabancaRespuestaDTO): ConsultAnswer["level"] {
  if (resp.sin_respuesta || resp.citas.length === 0) return "insuficiente";
  if (resp.contradicciones.length > 0) return "revision";
  if (resp.alertas.length > 0) return "parcial";
  return "suficiente";
}

function pickTitle(resp: NttdatabancaRespuestaDTO): string {
  if (resp.sin_respuesta) return "Sin evidencia suficiente en la biblioteca documental";
  if (resp.contradicciones.length > 0) return "Respuesta con una contradicción normativa detectada";
  return "Respuesta basada en la normativa vigente";
}

function buildWarnings(resp: NttdatabancaRespuestaDTO): string[] {
  const warnings: string[] = [];
  for (const alerta of resp.alertas) {
    warnings.push(alerta.detalle);
  }
  for (const c of resp.contradicciones) {
    const resolucion = c.prevalece ? ` Prevalece ${c.prevalece} (${c.criterio}).` : "";
    warnings.push(`Contradicción entre ${c.chunk_a} y ${c.chunk_b}: ${c.explicacion}${resolucion}`);
  }
  if (resp.citas_descartadas > 0) {
    warnings.push(
      `Se descartaron ${resp.citas_descartadas} cita(s) que no coincidían con el fragmento original.`,
    );
  }
  return warnings;
}

export function respuestaToConsultAnswer(params: {
  id: string;
  question: string;
  respuesta: NttdatabancaRespuestaDTO;
}): ConsultAnswer {
  const { id, question, respuesta } = params;
  const cleanedRespuesta = stripCitationMarkers(respuesta.respuesta);
  return {
    id,
    question,
    title: pickTitle(respuesta),
    level: pickLevel(respuesta),
    facts: cleanedRespuesta ? [cleanedRespuesta] : [],
    interpretation: null,
    evidence: respuesta.citas.map(citaToEvidenceFragment),
    warnings: buildWarnings(respuesta),
    answeredAt: new Date().toISOString(),
    source: "backend",
  };
}
