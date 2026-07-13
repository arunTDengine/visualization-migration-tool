#!/usr/bin/env bash
# Agent harness — end-to-end workflow wrapper for AI agents or CI
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${IDMP_URL:=http://localhost:6042}"

usage() {
  cat <<EOF
Agentic PI Migration Upgrade — agent harness

Usage:
  $0 validate [keyword]
  $0 ingest <customer-folder> [output.json]
  $0 migrate <scenario.json>
  $0 full <customer-folder>          # ingest + migrate

Environment:
  IDMP_URL and either IDMP_USER + IDMP_PASSWORD or IDMP_API_KEY

EOF
}

cmd="${1:-}"
shift || true

case "$cmd" in
  validate)
    ./run.sh validate --keyword "${1:-SCE}"
    ;;
  ingest)
    folder="${1:?customer folder required}"
    out="${2:-scenarios/generated.json}"
    ./run.sh ingest-folder "$folder" -o "$out"
    echo "Review screenshots referenced in $out before migrate"
    ;;
  migrate)
    scenario="${1:?scenario json required}"
    mkdir -p reports
    ./run.sh migrate "$scenario" --report "reports/$(basename "$scenario" .json)-report.json"
    ;;
  full)
    folder="${1:?customer folder required}"
    out="scenarios/generated-$(date +%Y%m%d-%H%M%S).json"
    ./run.sh ingest-folder "$folder" -o "$out"
    mkdir -p reports
    ./run.sh migrate "$out" --report "reports/latest.json"
    ;;
  *)
    usage
    exit 1
    ;;
esac
