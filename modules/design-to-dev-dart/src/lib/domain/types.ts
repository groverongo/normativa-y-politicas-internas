export type Tone = "green" | "amber" | "red" | "gray" | "blue";

export type VersionStatus = "approved" | "replaced" | "pending";

export interface DocumentVersion {
  v: string;
  status: VersionStatus;
  from: string | null;
  until: string | null;
  approved: string | null;
  by: string | null;
  note: string;
}

export interface DocumentRelation {
  kind: "replaces" | "potential_conflict" | "related";
  target: string;
  status: "confirmada" | "no resuelta" | "por verificar" | "programada";
  note: string;
}

export interface NormativeDocument {
  id: string;
  code: string;
  title: string;
  type: string;
  area: string;
  owner: string;
  description: string;
  versions: DocumentVersion[];
  relations: DocumentRelation[];
  classification: string;
  uploaded: string | null;
  review: string;
  /** Explicit flag set by a responsible reviewer (demo: CIR-RC-028). */
  pendingValidation?: boolean;
  /** True when the document is demo/test data, never real institutional data. */
  isDemo: boolean;
}

export type ValidityState = "Vigente" | "Pendiente" | "Revisión" | "Sin versión";

export interface ValidityAssessment {
  state: ValidityState;
  label: string;
  tone: Tone;
  version: DocumentVersion | null;
  futureVersion: DocumentVersion | null;
  reason: string;
  uncertain: boolean;
}

export type EvidenceLevel = "suficiente" | "parcial" | "insuficiente" | "revision";

export interface EvidenceFragment {
  code: string;
  title: string;
  version: string;
  section: string | null;
  page: string | null;
  /** HTML-free text; segments wrapped in [[ ]] are highlighted. */
  quote: string;
  why: string;
}

export interface ConsultAnswer {
  id: string;
  question: string;
  title: string;
  level: EvidenceLevel;
  facts: string[];
  interpretation: string | null;
  evidence: EvidenceFragment[];
  warnings: string[];
  answeredAt: string;
  /** "demo" answers come from predefined fixtures and are NOT verified. */
  source: "demo" | "backend";
}

export type FindingKind =
  | "vencido"
  | "contradiccion"
  | "version"
  | "revision"
  | "metadatos";

export interface ValidationFinding {
  id: string;
  kind: FindingKind;
  title: string;
  description: string;
  reason: string;
  documents: string[];
  severity: "alta" | "media" | "baja";
  reviewStatus: "pendiente" | "en revisión" | "resuelto";
  origin: "regla local" | "demo";
}
