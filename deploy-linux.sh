#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${1:-.env.docker}"

if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.docker.example "$ENV_FILE"
  echo "Created $ENV_FILE from .env.docker.example"
fi

if command -v openssl >/dev/null 2>&1; then
  if grep -q '^AUTH_SECRET_KEY=replace-with-a-long-random-string$' "$ENV_FILE"; then
    secret="$(openssl rand -hex 32)"
    sed -i "s|^AUTH_SECRET_KEY=.*$|AUTH_SECRET_KEY=${secret}|" "$ENV_FILE"
    echo "Generated AUTH_SECRET_KEY in $ENV_FILE"
  fi
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -z "${SHERPA_MODEL_DIR:-}" ]]; then
  echo "SHERPA_MODEL_DIR is missing in $ENV_FILE"
  exit 1
fi

mkdir -p "$SHERPA_MODEL_DIR"

echo "Step 1/3: Pull images"
docker compose --env-file "$ENV_FILE" pull || true

echo "Step 2/3: Download Sherpa model from Hugging Face"
docker compose --env-file "$ENV_FILE" run --rm model-downloader

echo "Step 3/3: Build and start services"
docker compose --env-file "$ENV_FILE" up -d --build backend frontend

docker compose --env-file "$ENV_FILE" ps

echo "Deployment finished. Frontend is expected at http://<server-ip>:8080"
