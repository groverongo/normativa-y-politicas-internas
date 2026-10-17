#!/usr/bin/env bash
# Bring up both modules via the root docker-compose.yml, making sure each
# module has its own .env (copied from .env.example if missing) before the
# build starts -- compose's env_file: directive fails hard if the file is
# absent.
#
# Usage:
#   ./docker-up.sh                 # equivalent to: docker compose up --build
#   ./docker-up.sh up --build api  # any args are passed through to `docker compose`
#   ./docker-up.sh down            # tear down both modules
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

MODULES=(ingesta nttbanca-n)

for m in "${MODULES[@]}"; do
  env_file="modules/$m/.env"
  example_file="modules/$m/.env.example"
  if [[ ! -f "$env_file" ]]; then
    if [[ -f "$example_file" ]]; then
      echo "modules/$m: no .env found, copying from .env.example" >&2
      cp "$example_file" "$env_file"
    else
      echo "modules/$m: missing both .env and .env.example -- aborting" >&2
      exit 1
    fi
  fi
done

if [[ $# -eq 0 ]]; then
  set -- up --build
fi

exec docker compose -f docker-compose.yml "$@"
