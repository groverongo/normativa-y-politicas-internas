#!/usr/bin/env bash
# Build (if needed) and run the ingesta Docker image with env vars from .env.
#
# Usage:
#   ./run.sh                         # start the API on http://localhost:8000
#   ./run.sh python smoke_test.py    # run the smoke test suite inside the container
#   ./run.sh python main.py ingest sample_docs/examples --seed sample_docs/seed_corpus.json
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

IMAGE_NAME="ingesta"
ENV_FILE=".env"
PORT="${PORT:-8000}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE -- copy .env.example to .env and fill in what you need." >&2
  exit 1
fi

docker build -t "$IMAGE_NAME" .

docker run --rm -it \
  --env-file "$ENV_FILE" \
  -p "${PORT}:8000" \
  -v "$(pwd)/runs:/app/runs" \
  "$IMAGE_NAME" "$@"
