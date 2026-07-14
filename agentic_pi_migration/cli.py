#!/usr/bin/env python3
"""Agentic PI Migration Upgrade — CLI entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agentic_pi_migration.client import IdmpClient
from agentic_pi_migration.folder_intake import ingest_folder, write_scenario
from agentic_pi_migration.idmp_compat import discover_local_idmp
from agentic_pi_migration.loader import load_dashboards
from agentic_pi_migration.migrator import AgenticPiMigrator, PI_TO_IDMP_PANEL
from agentic_pi_migration.qa import run_quality_check


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def cmd_validate(args: argparse.Namespace) -> int:
    client = IdmpClient(
        args.idmp_url,
        args.user,
        args.password,
        api_key=args.api_key or None,
    )
    rows = client.search_elements(args.keyword or "", limit=10)
    print(f"Connected to {args.idmp_url}")
    print(f"Sample elements ({len(rows)}):")
    for row in rows[:10]:
        print(f"  {row['id']:>18}  {row.get('name')}")
    print("\nCompatibility profile:")
    print(json.dumps(client.profile.to_dict(), indent=2))
    return 0


def cmd_map_types(_: argparse.Namespace) -> int:
    print("PI Vision → IDMP panel type map (Agentic PI Migration Upgrade):\n")
    for pi, idmp in sorted(PI_TO_IDMP_PANEL.items()):
        print(f"  {pi:12} → {idmp}")
    print("\nP&ID / process displays automatically publish as editable IDMP Canvas dashboards.")
    return 0


def cmd_discover(_: argparse.Namespace) -> int:
    rows = discover_local_idmp()
    if not rows:
        print("No local IDMP web/API ports found.")
        print("If IDMP runs in Docker, expose its xx42 port or use the Compose service name.")
        return 1
    print("Local IDMP candidates:")
    for row in rows:
        print(f"  {row['url']:<36} {row['detail']}")
    return 0


def cmd_ingest_folder(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    output = Path(args.output)
    scenario = write_scenario(folder, output)
    print(f"Ingested folder: {folder}")
    print(f"Displays found: {len(scenario.get('displays', []))}")
    for d in scenario.get("displays", []):
        shot = d.get("reference_screenshot", "no screenshot")
        print(f"  • {d['name']} — {len(d.get('panels', []))} panels — {shot}")
    print(f"\nScenario written: {output}")
    print(f"Next: ./run.sh migrate {output}")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    scenario = Path(args.scenario)
    if not scenario.exists():
        print(f"Scenario not found: {scenario}", file=sys.stderr)
        return 1

    client = IdmpClient(
        args.idmp_url,
        args.user,
        args.password,
        api_key=args.api_key or None,
    )
    migrator = AgenticPiMigrator(
        client,
        workers=args.workers,
        external_assist=(
            False if args.no_external_assist else (True if args.external_assist else None)
        ),
    )
    dashboards = load_dashboards(scenario)

    results = []
    for spec in dashboards:
        print(f"\n▶ Agentic migration: {spec.name}")
        result = migrator.migrate_dashboard(
            spec,
            update_existing=bool(args.update_existing),
        )
        results.append(result)
        print(f"  {result['action']} dashboard id={result['dashboard_id']} ({result['panel_count']} panels)")
        print(f"  {result['url']}")
        if result.get("edit_url"):
            print(f"  Canvas editor: {result['edit_url']}")

    if args.report:
        report_path = Path(args.report)
        report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nReport written: {report_path}")

    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    """External-LLM (or structural-only) quality check on a migration report."""
    report = Path(args.report)
    if not report.exists():
        print(f"Report not found: {report}", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else report.with_name(report.stem + "-qa.json")
    result = run_quality_check(
        report,
        folder=args.folder,
        display_path=args.display,
        out_path=out,
        use_llm=not args.structural_only,
        include_screenshot=not args.no_screenshot,
    )
    print(f"QA verdict: {result['verdict']}  score={result['overall_score']}/{result['pass_score']}")
    if result.get("primary", {}).get("url"):
        print(f"Dashboard: {result['primary']['url']}")
    structural = result.get("structural") or {}
    if structural.get("critical_failures"):
        print(f"Critical structural: {', '.join(structural['critical_failures'])}")
    for issue in (result.get("issues") or [])[:8]:
        print(f"  • {issue}")
    print(f"Wrote {out}")
    if result["verdict"] == "fail":
        return 2
    if result["verdict"] == "needs_review":
        return 0 if args.allow_review else 3
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentic-pi-migration",
        description=(
            "Agentic PI Migration Upgrade — recreate PI Vision displays on TDengine IDMP "
            "when tags and data already match."
        ),
    )
    parser.add_argument(
        "--idmp-url",
        default=_env("IDMP_URL", "http://localhost:6042"),
        help="IDMP base URL (auto-discovers common local xx42 ports)",
    )
    parser.add_argument(
        "--user",
        default=_env("IDMP_USER", _env("IDMP_USERNAME", "")),
        help="IDMP login email ($IDMP_USER)",
    )
    parser.add_argument(
        "--password",
        default=_env("IDMP_PASSWORD", ""),
        help="IDMP password ($IDMP_PASSWORD)",
    )
    parser.add_argument(
        "--api-key",
        default=_env("IDMP_API_KEY", ""),
        help="IDMP API key ($IDMP_API_KEY); takes precedence over password login",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Test IDMP connection and list elements")
    p_validate.add_argument("--keyword", default="", help="Element search keyword (optional)")
    p_validate.set_defaults(func=cmd_validate)

    p_map = sub.add_parser("map-types", help="Show PI Vision → IDMP panel type mapping")
    p_map.set_defaults(func=cmd_map_types)

    p_discover = sub.add_parser("discover", help="Find locally running IDMP web/API ports")
    p_discover.set_defaults(func=cmd_discover)

    p_ingest = sub.add_parser(
        "ingest-folder",
        help="Build scenario JSON from a folder of screenshots + tags.csv files",
    )
    p_ingest.add_argument("folder", help="Customer submission folder (one subfolder per display)")
    p_ingest.add_argument(
        "-o", "--output",
        default="scenarios/generated.json",
        help="Output scenario JSON path",
    )
    p_ingest.set_defaults(func=cmd_ingest_folder)

    p_migrate = sub.add_parser("migrate", help="Run agentic migration from scenario JSON")
    p_migrate.add_argument(
        "scenario",
        help="Path to scenario JSON (e.g. scenarios/generated.json)",
    )
    p_migrate.add_argument("--workers", type=int, default=3, help="Parallel AI panel workers")
    p_migrate.add_argument(
        "--update-existing",
        action="store_true",
        help="Update dashboard_id from the scenario instead of creating a new dashboard",
    )
    p_migrate.add_argument(
        "--create-new",
        action="store_true",
        help="(default) Always create a new dashboard; kept for compatibility",
    )
    p_migrate.add_argument("--report", help="Write migration report JSON to this path")
    assist = p_migrate.add_mutually_exclusive_group()
    assist.add_argument(
        "--external-assist",
        action="store_true",
        help="Force external LLM co-pilot for IDMP panel AI",
    )
    assist.add_argument(
        "--no-external-assist",
        action="store_true",
        help="Disable external LLM panel co-pilot",
    )
    p_migrate.set_defaults(func=cmd_migrate)

    p_qa = sub.add_parser(
        "qa",
        help="Quality-check a migrated IDMP panel/Canvas with structural + optional external LLM agent",
    )
    p_qa.add_argument("report", help="Migration report JSON (from ./run.sh migrate --report …)")
    p_qa.add_argument(
        "--folder",
        help="Customer folder with screenshot + tags.csv + display.json (vision ground truth)",
    )
    p_qa.add_argument("--display", help="Path to display.json if not inside --folder")
    p_qa.add_argument(
        "-o",
        "--out",
        help="Write QA report JSON (default: <report>-qa.json)",
    )
    p_qa.add_argument(
        "--structural-only",
        action="store_true",
        help="Skip external LLM; run deterministic checks only",
    )
    p_qa.add_argument(
        "--no-screenshot",
        action="store_true",
        help="Do not attach reference screenshot to the LLM (text-only judge)",
    )
    p_qa.add_argument(
        "--allow-review",
        action="store_true",
        help="Exit 0 on needs_review (default exit 3)",
    )
    p_qa.set_defaults(func=cmd_qa)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command not in ("map-types", "ingest-folder", "discover", "qa") and (
        not args.api_key and (not args.user or not args.password)
    ):
        print(
            "Set IDMP_API_KEY or provide IDMP_USER and IDMP_PASSWORD.",
            file=sys.stderr,
        )
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
