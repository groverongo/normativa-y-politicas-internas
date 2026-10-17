import type { DocumentRelation, DocumentVersion, NormativeDocument } from "@/lib/domain/types";
import type {
  IngestaCatalogEntryDTO,
  IngestaDocStatus,
  IngestaDocumentMetadataDTO,
  IngestaLineageMetadataDTO,
} from "@/lib/domain/ingesta-types";

/**
 * ingesta models one lifecycle state per doc_id -- a new version is a
 * *different* doc_id linked via lineage edges (supersedes/superseded_by),
 * while NormativeDocument expects one document with a versions[] history.
 * This adapter does the simplest honest mapping -- one ingesta doc becomes
 * one NormativeDocument with a single synthetic version -- rather than
 * walking the supersedes chain to rebuild a version history. Revisit if the
 * UI needs true multi-version grouping.
 */

const UNASSIGNED_OWNER = "Por asignar";

function toVersionStatus(status: IngestaDocStatus): DocumentVersion["status"] {
  return status === "ACTIVE" ? "approved" : "replaced";
}

function buildVersion(
  status: IngestaDocStatus,
  validFrom: string | null,
  validUntil: string | null,
  version: string | null,
  owner: string | null,
): DocumentVersion {
  return {
    v: version ?? "1",
    status: toVersionStatus(status),
    from: validFrom,
    until: validUntil,
    approved: validFrom,
    by: owner,
    note: "",
  };
}

/** Only the lineage edges with an unambiguous frontend equivalent are mapped; the
 * rest (amends, consolidates, split_from/into, revokes, overrides, impacts, ...)
 * have no counterpart in DocumentRelation and are intentionally dropped. */
function buildRelations(lineage: IngestaLineageMetadataDTO): DocumentRelation[] {
  const relations: DocumentRelation[] = [];
  for (const target of lineage.supersedes) {
    relations.push({
      kind: "replaces",
      target,
      status: "confirmada",
      note: `Reemplaza a ${target}`,
    });
  }
  for (const target of lineage.superseded_by) {
    relations.push({
      kind: "replaces",
      target,
      status: "confirmada",
      note: `Reemplazado por ${target}`,
    });
  }
  for (const target of lineage.contradicts) {
    relations.push({
      kind: "potential_conflict",
      target,
      status: "no resuelta",
      note: "Conflicto detectado por ingesta",
    });
  }
  return relations;
}

/** Maps a /documents list entry. No issuer or lineage is available at this
 * granularity, so owner/relations fall back to their "unknown" defaults. */
export function catalogEntryToNormativeDocument(entry: IngestaCatalogEntryDTO): NormativeDocument {
  return {
    id: entry.doc_id,
    code: entry.doc_id,
    title: entry.title,
    type: entry.doc_type,
    area: entry.topic_tags[0] ?? "",
    owner: UNASSIGNED_OWNER,
    description: "",
    versions: [buildVersion(entry.status, entry.valid_from, entry.valid_until, null, null)],
    relations: [],
    classification: entry.doc_type,
    uploaded: null,
    review: "",
    pendingValidation: false,
    isDemo: false,
  };
}

/** Maps a /documents/{doc_id} detail response, which carries issuer and
 * lineage that the catalog list entry doesn't. */
export function documentMetadataToNormativeDocument(
  meta: IngestaDocumentMetadataDTO,
): NormativeDocument {
  const {
    identity_metadata: identity,
    lifecycle_metadata: lifecycle,
    lineage_metadata: lineage,
  } = meta;
  return {
    id: identity.doc_id,
    code: identity.doc_id,
    title: identity.title,
    type: identity.doc_type,
    area: identity.topic_tags[0] ?? "",
    owner: identity.issuer || UNASSIGNED_OWNER,
    description: "",
    versions: [
      buildVersion(
        lifecycle.status,
        lifecycle.valid_from,
        lifecycle.valid_until,
        lifecycle.version,
        identity.issuer || null,
      ),
    ],
    relations: buildRelations(lineage),
    classification: identity.doc_type,
    uploaded: null,
    review: "",
    pendingValidation:
      lifecycle.missing_dependencies.length > 0 || lifecycle.review_flags.length > 0,
    isDemo: false,
  };
}
