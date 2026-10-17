PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: help venv install env test migrate migrate-status migrate-dry-run

help:
	@echo "Targets:"
	@echo "  make install           Create .venv and install requirements.txt + requirements-dev.txt"
	@echo "  make env               Copy .env.example to .env (no-op if .env exists)"
	@echo "  make test              Run pytest (SQLite in-memory + moto-mocked S3, no AWS/DB needed)"
	@echo "  make migrate           Apply pending migrations (see migrations/README.md)"
	@echo "  make migrate-status    Show applied vs. pending migrations"
	@echo "  make migrate-dry-run   Apply + roll back all migrations, to validate a new one"

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)

venv: $(BIN)/python

install: venv
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt -r requirements-dev.txt

env:
	[ -f .env ] || cp .env.example .env

test: install env
	$(BIN)/pytest

migrate: install
	$(BIN)/python -m app.db.migrate

migrate-status: install
	$(BIN)/python -m app.db.migrate --status

migrate-dry-run: install
	$(BIN)/python -m app.db.migrate --dry-run
