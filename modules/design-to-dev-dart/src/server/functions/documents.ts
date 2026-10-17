import { createServerFn } from "@tanstack/react-start";
import type { NormativeDocument } from "@/lib/domain/types";
import { fetchCatalog, fetchDocument } from "@/server/ingesta-client";
import {
  catalogEntryToNormativeDocument,
  documentMetadataToNormativeDocument,
} from "@/server/ingesta-adapter";

export const listDocumentsFn = createServerFn({ method: "GET" }).handler(
  async (): Promise<NormativeDocument[]> => {
    const catalog = await fetchCatalog();
    return catalog.map(catalogEntryToNormativeDocument);
  },
);

export const getDocumentFn = createServerFn({ method: "GET" })
  .validator((code: unknown): string => {
    if (typeof code !== "string" || code.length === 0) {
      throw new Error("getDocumentFn requires a non-empty document code");
    }
    return code;
  })
  .handler(async ({ data: code }): Promise<NormativeDocument | null> => {
    const meta = await fetchDocument(code);
    return meta ? documentMetadataToNormativeDocument(meta) : null;
  });
