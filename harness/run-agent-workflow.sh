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
  $0 qa <report.json> [customer-folder]   # structural + optional external LLM judge
  $0 full <customer-folder>               # ingest + migrate (+ qa if QA_LLM_API_KEY set)

Environment:
  IDMP_URL and either IDMP_USER + IDMP_PASSWORD or IDMP_API_KEY
  Optional QA: QA_LLM_API_KEY, QA_LLM_PROVIDER=openai|anthropic, QA_LLM_MODEL, QA_LLM_BASE_URL

EOF
}

cmd="${1:-}"
shift || true

case "$cmd" in
  validate)
    ./run.sh validate --keyword "${1:-}"
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
  qa)
    report="${1:?migration report json required}"
    folder="${2:-}"
    mkdir -p reports
    if [[ -n "$folder" ]]; then
      ./run.sh qa "$report" --folder "$folder" -o "reports/$(basename "$report" .json)-qa.json"
    else
      ./run.sh qa "$report" -o "reports/$(basename "$report" .json)-qa.json"
    fi
    ;;
  full)
    folder="${1:?customer folder required}"
    out="scenarios/generated-$(date +%Y%m%d-%H%M%S).json"
    ./run.sh ingest-folder "$folder" -o "$out"
    mkdir -p reports
    ./run.sh migrate "$out" --report "reports/latest.json"
    if [[ -n "${QA_LLM_API_KEY:-}${OPENAI_API_KEY:-}${ANTHROPIC_API_KEY:-}" ]]; then
      ./run.sh qa reports/latest.json --folder "$folder" -o reports/latest-qa.json --allow-review
    else
      ./run.sh qa reports/latest.json --folder "$folder" -o reports/latest-qa.json --structural-only --allow-review
      echo "Tip: set QA_LLM_API_KEY to enable external LLM panel QA"
    fi
    ;;
  *)
    usage
    exit 1
    ;;
esac
