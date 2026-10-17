/**
 * TypeScript mirrors of modules/ingesta/schema.py's HTTP-facing shapes
 * (CatalogEntry, DocumentMetadata and friends). Field names match the JSON
 * ingesta's FastAPI app returns verbatim (snake_case, no aliasing on the
 * pydantic side). Keep in sync with schema.py if that contract changes.
 */

export type IngestaDocStatus =
  "ACTIVE" | "SUPERSEDED" | "PARTIALLY_SUPERSEDED" | "REVOKED" | "EXPIRED";

export interface IngestaCatalogEntryDTO {
  doc_id: string;
  title: string;
  doc_type: string;
  status: IngestaDocStatus;
  valid_from: string | null;
  valid_until: string | null;
  defined_terms: string[];
  topic_tags: string[];
}

export interface IngestaIdentityMetadataDTO {
  doc_id: string;
  chunk_index: number;
  doc_type: string;
  title: string;
  issuer: string;
  topic_tags: string[];
  defined_terms: string[];
  referenced_terms: string[];
  source_uri: string | null;
}

export interface IngestaPatchRecordDTO {
  clause: string;
  old_text: string;
  new_text: string;
  patched_by: string | null;
  effective_date: string | null;
}

export interface IngestaLifecycleMetadataDTO {
  status: IngestaDocStatus;
  valid_from: string | null;
  valid_until: string | null;
  version: string | null;
  review_flags: string[];
  missing_dependencies: string[];
  patch_log: IngestaPatchRecordDTO[];
  notes: string[];
}

export interface IngestaLineageMetadataDTO {
  supersedes: string[];
  superseded_by: string[];
  amends: string[];
  patched_by: string[];
  consolidates: string[];
  split_from: string[];
  split_into: string[];
  contradicts: string[];
  revokes: string[];
  revoked_by: string[];
  overrides: string[];
  overridden_by: string[];
  impacts: string[];
  definition_sources: Record<string, string>;
}

export interface IngestaDocumentMetadataDTO {
  identity_metadata: IngestaIdentityMetadataDTO;
  lifecycle_metadata: IngestaLifecycleMetadataDTO;
  lineage_metadata: IngestaLineageMetadataDTO;
}
