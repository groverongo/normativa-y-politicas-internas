PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
PORT ?= 8000

.PHONY: help venv install env test smoke-test ingest trace run api docker-build docker-run clean

help:
	@echo "Targets:"
	@echo "  make install       Create .venv and install requirements.txt"
	@echo "  make env           Copy .env.example to .env (no-op if .env exists)"
	@echo "  make test          Run the smoke test suite (LLM_PROVIDER=mock)"
	@echo "  make ingest        Ingest sample_docs/examples with the seed corpus"
	@echo "  make trace FILE=<path>  Pretty-print an interaction_log.jsonl"
	@echo "  make api           Run the FastAPI app locally with uvicorn --reload"
	@echo "  make docker-build  Build the ingesta Docker image"
	@echo "  make docker-run    Run the Docker image via run.sh"
	@echo "  make clean         Remove .venv, __pycache__, and runs/"

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)

venv: $(BIN)/python

install: venv
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

env:
	[ -f .env ] || cp .env.example .env

test: install env
	$(BIN)/python smoke_test.py

smoke-test: test

ingest: install env
	$(BIN)/python main.py ingest sample_docs/examples --seed sample_docs/seed_corpus.json

trace: install
	$(BIN)/python main.py trace $(FILE)

api: install env
	$(BIN)/uvicorn api:app --reload --port $(PORT)

docker-build:
	docker build -t ingesta .

docker-run:
	./run.sh

clean:
	rm -rf $(VENV) __pycache__ runs
