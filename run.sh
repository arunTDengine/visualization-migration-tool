#!/usr/bin/env bash
# Agentic PI Migration Upgrade — quick launcher for Summit Creek oil scenario
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${IDMP_URL:=http://localhost:6042}"

case "${1:-}" in
  map-types|ingest-folder|discover)
    ;;
  *)
    if [[ -z "${IDMP_API_KEY:-}" ]]; then
      : "${IDMP_USER:?Set IDMP_USER or IDMP_API_KEY}"
      : "${IDMP_PASSWORD:?Set IDMP_PASSWORD or IDMP_API_KEY}"
    fi
    ;;
esac

PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
PYTHONPATH="$ROOT" "$PYTHON" -m agentic_pi_migration.cli "$@"
