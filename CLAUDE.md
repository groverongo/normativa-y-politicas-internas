# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

This repository is a monorepo with three independent modules:

- `modules/ingesta/` -- the "B2 Normativa" regulatory-document ingestion pipeline. See `modules/ingesta/CLAUDE.md` for its architecture, gotchas, and commands. Has its own `Makefile`.
- `modules/nttbanca-n/` -- imported via `git subtree` from `https://github.com/AaronAP1/NttBanca_N` (full history preserved under `modules/nttbanca-n/`). See `modules/nttbanca-n/CLAUDE.md` for its architecture and commands. Has its own `Makefile`.
- `modules/design-to-dev-dart/` -- imported via `git subtree` from `https://github.com/jchinchayrobles-design/design-to-dev-dart` (full history preserved under `modules/design-to-dev-dart/`). A Vite/React frontend scaffolded with Lovable. Read its own `README.md` for how to run it; it does not yet have a `Makefile` or a `CLAUDE.md`.

Each module is self-contained: its own dependencies, `.venv`, `.env`, Dockerfile, and `.gitignore` live under its own directory. There is no shared build step or shared dependency file at the repo root.

## Commands

```bash
make help                    # list root-level targets
make install                 # install dependencies for every module that has a Makefile
make test                    # run tests for every module that has a Makefile
make migrate                 # apply the one shared DB migration sequence (see modules/nttbanca-n/migrations/README.md)
make -C modules/ingesta help  # see modules/ingesta/Makefile for the full per-module target list
```

`modules/ingesta` and `modules/nttbanca-n` share one Postgres database and one
migration sequence (`modules/nttbanca-n/migrations/`, applied by
`modules/nttbanca-n/app/db/migrate.py`); `modules/ingesta` no longer
auto-creates its own schema, so run `make migrate` once against the target
database before using `STORAGE_BACKEND=postgres` there.

## Working with modules/nttbanca-n

That directory's history was merged in with `git subtree`, not a submodule -- there is no separate `.git` to manage and no `git submodule update` step. To pull upstream changes later:

```bash
git subtree pull --prefix=modules/nttbanca-n https://github.com/AaronAP1/NttBanca_N main
```

To push local changes made under `modules/nttbanca-n/` back upstream (requires push access to that repo):

```bash
git subtree push --prefix=modules/nttbanca-n https://github.com/AaronAP1/NttBanca_N <branch>
```

## Working with modules/design-to-dev-dart

Same situation as `nttbanca-n`: merged in with `git subtree`, no separate `.git` to manage.

```bash
git subtree pull --prefix=modules/design-to-dev-dart https://github.com/jchinchayrobles-design/design-to-dev-dart main
git subtree push --prefix=modules/design-to-dev-dart https://github.com/jchinchayrobles-design/design-to-dev-dart <branch>
```
