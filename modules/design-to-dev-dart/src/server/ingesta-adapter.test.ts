import { describe, expect, it } from "vitest";
import {
  catalogEntryToNormativeDocument,
  documentMetadataToNormativeDocument,
} from "./ingesta-adapter";
import type {
  IngestaCatalogEntryDTO,
  IngestaDocStatus,
  IngestaDocumentMetadataDTO,
} from "@/lib/domain/ingesta-types";

const catalogEntry = (overrides: Partial<IngestaCatalogEntryDTO> = {}): IngestaCatalogEntryDTO => ({
  doc_id: "BCP-001-2026",
  title: "Circular de riesgo crediticio",
  doc_type: "circular",
  status: "ACTIVE",
  valid_from: "2026-01-01",
  valid_until: null,
  defined_terms: [],
  topic_tags: ["riesgo-crediticio"],
  ...overrides,
});

const documentMetadata = (
  overrides: Partial<IngestaDocumentMetadataDTO["lifecycle_metadata"]> = {},
  lineageOverrides: Partial<IngestaDocumentMetadataDTO["lineage_metadata"]> = {},
): IngestaDocumentMetadataDTO => ({
  identity_metadata: {
    doc_id: "BCP-001-2026",
    chunk_index: 0,
    doc_type: "circular",
    title: "Circular de riesgo crediticio",
    issuer: "SBS",
    topic_tags: ["riesgo-crediticio"],
    defined_terms: [],
    referenced_terms: [],
    source_uri: "docs/BCP-001-2026.txt",
  },
  lifecycle_metadata: {
    status: "ACTIVE",
    valid_from: "2026-01-01",
    valid_until: null,
    version: "2",
    review_flags: [],
    missing_dependencies: [],
    patch_log: [],
    notes: [],
    ...overrides,
  },
  lineage_metadata: {
    supersedes: [],
    superseded_by: [],
    amends: [],
    patched_by: [],
    consolidates: [],
    split_from: [],
    split_into: [],
    contradicts: [],
    revokes: [],
    revoked_by: [],
    overrides: [],
    overridden_by: [],
    impacts: [],
    definition_sources: {},
    ...lineageOverrides,
  },
});

describe("catalogEntryToNormativeDocument", () => {
  it("maps identity fields and marks the result as non-demo", () => {
    const doc = catalogEntryToNormativeDocument(catalogEntry());
    expect(doc.code).toBe("BCP-001-2026");
    expect(doc.area).toBe("riesgo-crediticio");
    expect(doc.isDemo).toBe(false);
    expect(doc.owner).toBe("Por asignar");
    expect(doc.relations).toEqual([]);
  });

  it.each<[IngestaDocStatus, "approved" | "replaced"]>([
    ["ACTIVE", "approved"],
    ["SUPERSEDED", "replaced"],
    ["PARTIALLY_SUPERSEDED", "replaced"],
    ["REVOKED", "replaced"],
    ["EXPIRED", "replaced"],
  ])("maps DocStatus %s to version status %s", (status, expected) => {
    const doc = catalogEntryToNormativeDocument(catalogEntry({ status }));
    expect(doc.versions[0]?.status).toBe(expected);
  });
});

describe("documentMetadataToNormativeDocument", () => {
  it("uses the issuer as owner and the lifecycle version number", () => {
    const doc = documentMetadataToNormativeDocument(documentMetadata());
    expect(doc.owner).toBe("SBS");
    expect(doc.versions[0]?.v).toBe("2");
  });

  it("falls back to the unassigned-owner sentinel when issuer is blank", () => {
    const meta = documentMetadata();
    meta.identity_metadata.issuer = "";
    const doc = documentMetadataToNormativeDocument(meta);
    expect(doc.owner).toBe("Por asignar");
  });

  it("maps supersedes/superseded_by to replaces relations", () => {
    const doc = documentMetadataToNormativeDocument(
      documentMetadata({}, { supersedes: ["OLD-1"], superseded_by: ["NEW-1"] }),
    );
    expect(doc.relations).toEqual([
      { kind: "replaces", target: "OLD-1", status: "confirmada", note: "Reemplaza a OLD-1" },
      { kind: "replaces", target: "NEW-1", status: "confirmada", note: "Reemplazado por NEW-1" },
    ]);
  });

  it("maps contradicts to a potential_conflict relation", () => {
    const doc = documentMetadataToNormativeDocument(
      documentMetadata({}, { contradicts: ["RIVAL-1"] }),
    );
    expect(doc.relations).toEqual([
      {
        kind: "potential_conflict",
        target: "RIVAL-1",
        status: "no resuelta",
        note: "Conflicto detectado por ingesta",
      },
    ]);
  });

  it("flags pendingValidation when missing_dependencies is non-empty", () => {
    const doc = documentMetadataToNormativeDocument(
      documentMetadata({ missing_dependencies: ["TERM-X"] }),
    );
    expect(doc.pendingValidation).toBe(true);
  });

  it("flags pendingValidation when review_flags is non-empty", () => {
    const doc = documentMetadataToNormativeDocument(
      documentMetadata({ review_flags: ["needs_review"] }),
    );
    expect(doc.pendingValidation).toBe(true);
  });

  it("leaves pendingValidation false when there is nothing flagged", () => {
    const doc = documentMetadataToNormativeDocument(documentMetadata());
    expect(doc.pendingValidation).toBe(false);
  });
});
