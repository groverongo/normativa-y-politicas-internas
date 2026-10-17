# Design To Dev Dart

Implement exactly the screenshot and nothing else

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/e12c3a7a-1d3d-46a7-9b0e-daaf052dd9f0).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```

## Connecting the Biblioteca view to modules/ingesta

By default `/biblioteca` reads the demo fixtures in `src/lib/demo/fixtures.ts`
(`src/services/index.ts`'s `demoProvider`). To read real documents from
`modules/ingesta`'s API instead:

1. Start ingesta's API: `make -C ../ingesta api` (or `docker compose up ingesta`
   from the repo root), reachable at `http://localhost:8000` by default.
2. Copy `.env.example` to `.env.local` and set `VITE_SERVICES_MODE=backend`.
   Adjust `INGESTA_API_URL` if ingesta isn't on the default port.
3. Run `npm run dev` as usual.

`src/services/index.ts`'s `backendProvider` calls ingesta through TanStack
Start server functions (`src/server/functions/documents.ts`), so
`INGESTA_API_URL` is read server-side only and never reaches the browser.
`src/server/ingesta-adapter.ts` maps ingesta's document-graph model onto this
app's `NormativeDocument` shape — see that file's header comment for the
simplifications involved (one ingesta `doc_id` becomes one document with a
single synthetic version, not a full version history).

## Connecting the Consultor view to modules/nttdatabanca

The same `VITE_SERVICES_MODE=backend` switch also routes `/` (the "Consultor
normativo" page) to `modules/nttdatabanca`'s RAG API instead of the demo
answer fixtures:

1. Start nttdatabanca's API: `docker compose up nttdatabanca` from the repo
   root (it needs Voyage/Gemini API keys configured in its own `.env` to
   actually answer), reachable at `http://localhost:8002` by default.
2. Set `NTTDATABANCA_API_URL` in `.env.local` if it isn't on the default port.
3. Run `npm run dev` as usual.

`src/server/functions/consultas.ts` calls nttdatabanca's `POST /ask` and
`src/server/nttdatabanca-adapter.ts` maps its response onto this app's
`ConsultAnswer` shape — see that file's header comment for what's
synthesized (there's no backend equivalent of `title`/`interpretation`,
so those are derived from the response's shape rather than invented).
