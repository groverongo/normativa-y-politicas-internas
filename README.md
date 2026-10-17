# normativa-y-politicas-internas (monorepo)

This repository is a monorepo with four independent modules:

- [`modules/ingesta/`](modules/ingesta/README.md) -- the "B2 Normativa" regulatory-document ingestion pipeline. See its own README for architecture and usage, and its `Makefile` for commands (`make -C modules/ingesta help`).
- [`modules/nttbanca-n/`](modules/nttbanca-n/README.md) -- imported from [AaronAP1/NttBanca_N](https://github.com/AaronAP1/NttBanca_N) via `git subtree`, full history preserved. See its own README for what it is and how to run it.
- [`modules/design-to-dev-dart/`](modules/design-to-dev-dart/README.md) -- imported from [jchinchayrobles-design/design-to-dev-dart](https://github.com/jchinchayrobles-design/design-to-dev-dart) via `git subtree`. A Vite/React frontend scaffolded with Lovable; it does not yet have a `Makefile` or `CLAUDE.md`.
- [`modules/nttdatabanca/`](modules/nttdatabanca/README.md) -- imported from [imjowend/nttdatabanca](https://github.com/imjowend/nttdatabanca) via `git subtree` (squashed). A standalone Go RAG service over SBS regulatory docs + internal policies (Qdrant, Voyage/Jina, an OpenAI-compatible LLM); it does not yet have a `Makefile` or `CLAUDE.md`.

Each module is self-contained: its own dependencies, `.venv`, `.env`, Dockerfile, and `.gitignore` live under its own directory. There is no shared build step or shared dependency file at the repo root.

## Quick start

```bash
make help       # root-level targets
make install    # install deps for every module that has a Makefile
make test       # run tests for every module that has a Makefile
make migrate    # apply the one shared DB migration sequence (modules/ingesta + modules/nttbanca-n)
```

See `CLAUDE.md` for more detail on how the modules relate and how to pull/push the subtree modules upstream.
