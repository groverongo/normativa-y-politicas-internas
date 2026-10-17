# normativa-y-politicas-internas (monorepo)

This repository is a monorepo with two modules:

- [`modules/ingesta/`](modules/ingesta/README.md) -- the "B2 Normativa" regulatory-document ingestion pipeline. See its own README for architecture and usage, and its `Makefile` for commands (`make -C modules/ingesta help`).
- [`modules/nttbanca-n/`](modules/nttbanca-n/README.md) -- imported from [AaronAP1/NttBanca_N](https://github.com/AaronAP1/NttBanca_N) via `git subtree`, full history preserved. See its own README for what it is and how to run it.

## Quick start

```bash
make help            # root-level targets
make install          # install deps for every module
make test              # run tests for every module
```

See `CLAUDE.md` for more detail on how the modules relate and how to pull/push `modules/nttbanca-n` upstream.
