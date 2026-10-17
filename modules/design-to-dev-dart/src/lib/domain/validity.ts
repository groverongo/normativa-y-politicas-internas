import type { NormativeDocument, ValidityAssessment, ValidationFinding } from "./types";

export const fmtDate = (d: string | null | undefined) =>
  d
    ? new Date(d + "T12:00:00")
        .toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" })
        .replace(".", "")
    : "No registrada";

/**
 * Determines the applicable version of a document at a reference date.
 * Rule: approved + validity window includes the date. Missing dates or pending
 * validation never yield a conclusive "Vigente".
 */
export function assessValidity(doc: NormativeDocument, date: string): ValidityAssessment {
  const futureVersion =
    doc.versions
      .filter((v) => v.status === "approved" && v.from && v.from > date)
      .sort((a, b) => a.from!.localeCompare(b.from!))[0] ?? null;

  if (doc.pendingValidation || doc.versions.some((v) => v.status === "pending")) {
    return {
      state: "Pendiente",
      label: "Pendiente de validación",
      tone: "amber",
      version: null,
      futureVersion,
      reason:
        "Existe una revisión pendiente; no se puede determinar una versión aplicable hasta completar la validación.",
      uncertain: true,
    };
  }

  const applicable = doc.versions
    .filter(
      (v) => v.status === "approved" && v.from && v.from <= date && (!v.until || date <= v.until),
    )
    .sort((a, b) => b.from!.localeCompare(a.from!))[0];

  if (applicable) {
    return {
      state: "Vigente",
      label: futureVersion ? "Vigente · nueva versión futura" : "Vigente",
      tone: "green",
      version: applicable,
      futureVersion,
      reason: futureVersion
        ? `La versión ${applicable.v} es aplicable a la fecha de referencia. La versión ${futureVersion.v} está aprobada, pero entra en vigor el ${fmtDate(futureVersion.from)}.`
        : "Existe una versión aprobada cuya vigencia incluye la fecha de referencia.",
      uncertain: false,
    };
  }

  const approvedNoDates = doc.versions.find((v) => v.status === "approved" && !v.from);
  if (approvedNoDates) {
    return {
      state: "Revisión",
      label: "Vigencia por confirmar",
      tone: "amber",
      version: approvedNoDates,
      futureVersion,
      reason:
        "La aprobación está registrada, pero faltan fechas de vigencia verificables. No debe tratarse como fuente normativa concluyente.",
      uncertain: true,
    };
  }

  const expired = doc.versions.some((v) => v.status === "approved" && v.until && v.until < date);
  return {
    state: "Sin versión",
    label: expired ? "Vencido" : "Sin versión aplicable",
    tone: expired ? "red" : "amber",
    version: null,
    futureVersion,
    reason: "No se encontró una versión aprobada con fechas de vigencia que incluyan esta fecha.",
    uncertain: true,
  };
}

/** Local rule-based checks over registered metadata. Not an institutional verification. */
export function runLocalChecks(docs: NormativeDocument[], date: string): ValidationFinding[] {
  const out: ValidationFinding[] = [];
  for (const d of docs) {
    const a = assessValidity(d, date);
    if (a.label === "Vencido") {
      out.push({
        id: `exp-${d.code}`,
        kind: "vencido",
        title: "Documento sin versión vigente",
        description: `${d.code} no tiene una versión aprobada vigente a la fecha de referencia.`,
        reason: "Todas las versiones aprobadas tienen fecha de término anterior a la fecha evaluada.",
        documents: [d.code],
        severity: "alta",
        reviewStatus: "pendiente",
        origin: "regla local",
      });
    }
    if (d.versions.some((v) => v.status === "approved" && !v.from)) {
      out.push({
        id: `meta-${d.code}`,
        kind: "metadatos",
        title: "Fecha de vigencia no registrada",
        description: `${d.code} tiene una versión aprobada sin fecha de inicio de vigencia.`,
        reason: "Sin fecha de vigencia no se puede confirmar la aplicabilidad del documento.",
        documents: [d.code],
        severity: "media",
        reviewStatus: "pendiente",
        origin: "regla local",
      });
    }
    if (!d.owner || d.owner === "Por asignar") {
      out.push({
        id: `owner-${d.code}`,
        kind: "metadatos",
        title: "Responsable documental sin asignar",
        description: `${d.code} no tiene un responsable documental asignado.`,
        reason: "Metadato obligatorio incompleto.",
        documents: [d.code],
        severity: "baja",
        reviewStatus: "pendiente",
        origin: "regla local",
      });
    }
    const seen = new Set<string>();
    for (const v of d.versions) {
      if (seen.has(v.v)) {
        out.push({
          id: `dup-${d.code}-${v.v}`,
          kind: "version",
          title: "Versión duplicada",
          description: `${d.code} registra más de una vez la versión ${v.v}.`,
          reason: "Los números de versión deben ser únicos por documento.",
          documents: [d.code],
          severity: "media",
          reviewStatus: "pendiente",
          origin: "regla local",
        });
      }
      seen.add(v.v);
    }
    for (const r of d.relations) {
      if (r.kind === "potential_conflict" && r.status === "no resuelta") {
        out.push({
          id: `conf-${d.code}`,
          kind: "contradiccion",
          title: "Posible contradicción normativa",
          description: `${d.code} y ${r.target}: ${r.note}`,
          reason: "Relación de conflicto registrada sin resolución de precedencia.",
          documents: [d.code, r.target.split(" ")[0] ?? r.target],
          severity: "alta",
          reviewStatus: "pendiente",
          origin: "regla local",
        });
      }
    }
    if (d.review && /^\d{4}-\d{2}-\d{2}$/.test(d.review) && d.review <= date) {
      out.push({
        id: `rev-${d.code}`,
        kind: "revision",
        title: "Revisión periódica vencida",
        description: `${d.code} tenía revisión programada para el ${fmtDate(d.review)}.`,
        reason: "La fecha de revisión programada ya pasó.",
        documents: [d.code],
        severity: "media",
        reviewStatus: "pendiente",
        origin: "regla local",
      });
    }
  }
  return out;
}
