import type { NttdatabancaRespuestaDTO } from "@/lib/domain/nttdatabanca-types";

/**
 * Server-only. Import from server-function handlers (src/server/functions/*)
 * only, never from client components -- mirrors src/server/ingesta-client.ts's
 * convention: the base URL is read via process.env, never import.meta.env, so
 * it is never bundled for the browser. Matches the port modules/nttdatabanca's
 * docker-compose service publishes.
 */
const BASE_URL = process.env["NTTDATABANCA_API_URL"] ?? "http://localhost:8002";

export async function askQuestion(pregunta: string): Promise<NttdatabancaRespuestaDTO> {
  const res = await fetch(`${BASE_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta }),
  });
  if (!res.ok) {
    throw new Error(`nttdatabanca POST /ask failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as NttdatabancaRespuestaDTO;
}
