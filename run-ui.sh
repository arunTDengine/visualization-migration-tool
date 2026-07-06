#!/usr/bin/env bash
# Start the Agentic PI Migration Upgrade web UI
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

VENV="$ROOT/.venv"
if [[ ! -d "$VENV" ]]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

if ! python -c "import fastapi" 2>/dev/null; then
  echo "Installing UI dependencies..."
  pip install -q -r requirements.txt
fi

: "${UI_HOST:=127.0.0.1}"
: "${UI_PORT:=8765}"

echo ""
echo "  Agentic PI Migration Upgrade — Web UI"
echo "  Open http://${UI_HOST}:${UI_PORT}"
echo ""

PYTHONPATH="$ROOT" python -m agentic_pi_migration.web.server
