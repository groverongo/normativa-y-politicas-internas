import type {
  IngestaCatalogEntryDTO,
  IngestaDocumentMetadataDTO,
} from "@/lib/domain/ingesta-types";

/**
 * Server-only. Import this from server-function handlers (src/server-fns/*)
 * only, never from client components -- the base URL is read via process.env,
 * not import.meta.env, specifically so it is never bundled for the browser.
 * Defaults to the port modules/ingesta's docker-compose service publishes.
 */
const BASE_URL = process.env["INGESTA_API_URL"] ?? "http://localhost:8000";

export async function fetchCatalog(): Promise<IngestaCatalogEntryDTO[]> {
  const res = await fetch(`${BASE_URL}/documents`);
  if (!res.ok) {
    throw new Error(`ingesta GET /documents failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as IngestaCatalogEntryDTO[];
}

export async function fetchDocument(docId: string): Promise<IngestaDocumentMetadataDTO | null> {
  const res = await fetch(`${BASE_URL}/documents/${encodeURIComponent(docId)}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`ingesta GET /documents/${docId} failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as IngestaDocumentMetadataDTO;
}
