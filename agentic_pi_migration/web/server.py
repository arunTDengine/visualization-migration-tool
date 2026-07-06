"""FastAPI server for the Agentic PI Migration Upgrade web UI."""

from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agentic_pi_migration.client import IdmpClient
from agentic_pi_migration.folder_intake import ingest_folder
from agentic_pi_migration.loader import load_dashboards
from agentic_pi_migration.migrator import AgenticPiMigrator, PI_TO_IDMP_PANEL

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"
UPLOADS_DIR = ROOT / "uploads"
SCENARIOS_DIR = ROOT / "scenarios"

BUILTIN_EXAMPLES: dict[str, str] = {
    "summit-creek-oil": "Summit Creek oil — 3 dashboards (ops, P-101, SEP-101)",
    "examples/ops-overview": "Single display folder intake example",
}


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    import os

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


_load_dotenv()

app = FastAPI(
    title="Agentic PI Migration Upgrade",
    description="Web UI for PI Vision to TDengine IDMP dashboard migration",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs: dict[str, dict[str, Any]] = {}


class ValidateRequest(BaseModel):
    idmp_url: str = "http://localhost:7142"
    user: str
    password: str
    keyword: str = "SCE"


class ExampleIngestRequest(BaseModel):
    example_id: str


class MigrateRequest(BaseModel):
    job_id: str
    idmp_url: str = "http://localhost:7142"
    user: str
    password: str
    create_new: bool = False
    workers: int = Field(default=3, ge=1, le=8)


def _default_config() -> dict[str, str]:
    import os

    return {
        "idmp_url": os.environ.get("IDMP_URL", "http://localhost:7142"),
        "user": os.environ.get("IDMP_USER", os.environ.get("IDMP_USERNAME", "")),
        "has_password": bool(os.environ.get("IDMP_PASSWORD")),
    }


def _safe_extract_zip(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise HTTPException(status_code=400, detail="Invalid zip entry path")
        zf.extractall(dest)


def _normalize_upload_root(folder: Path) -> Path:
    """If zip contained a single top-level folder, use it as the migration root."""
    entries = [p for p in folder.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return folder


def _scenario_summary(scenario: dict[str, Any]) -> dict[str, Any]:
    displays = scenario.get("displays", [scenario])
    return {
        "name": scenario.get("name", "Migration"),
        "description": scenario.get("description", ""),
        "source_folder": scenario.get("source_folder"),
        "display_count": len(displays),
        "displays": [
            {
                "name": d.get("name"),
                "element_id": d.get("element_id"),
                "dashboard_id": d.get("dashboard_id"),
                "theme": d.get("theme"),
                "panel_count": len(d.get("panels", [])),
                "has_screenshot": bool(d.get("reference_screenshot")),
                "panels": [
                    {
                        "key": p.get("key"),
                        "title": p.get("title"),
                        "type": p.get("type"),
                        "element_id": p.get("element_id"),
                        "pi_tags": p.get("pi_tags", []),
                    }
                    for p in d.get("panels", [])
                ],
            }
            for d in displays
        ],
    }


def _create_job(scenario: dict[str, Any], *, source: str, scenario_path: Path) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scenario_path": str(scenario_path),
        "summary": _scenario_summary(scenario),
    }
    jobs[job_id] = job
    return job


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agentic-pi-migration-ui"}


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return _default_config()


@app.get("/api/map-types")
def map_types() -> list[dict[str, str]]:
    return [{"pi_vision": pi, "idmp": idmp} for pi, idmp in sorted(PI_TO_IDMP_PANEL.items())]


@app.get("/api/examples")
def list_examples() -> list[dict[str, Any]]:
    items = []
    for example_id, label in BUILTIN_EXAMPLES.items():
        path = SCENARIOS_DIR / f"{example_id}.json" if "/" not in example_id else None
        if example_id.startswith("examples/"):
            folder = SCENARIOS_DIR / example_id
            available = folder.is_dir()
        else:
            available = path is not None and path.exists()
        items.append({"id": example_id, "label": label, "available": available})
    return items


@app.post("/api/validate")
def validate_connection(body: ValidateRequest) -> dict[str, Any]:
    try:
        client = IdmpClient(body.idmp_url, body.user, body.password)
        rows = client.search_elements(body.keyword, limit=20)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "ok": True,
        "idmp_url": body.idmp_url,
        "keyword": body.keyword,
        "element_count": len(rows),
        "elements": [
            {"id": row["id"], "name": row.get("name"), "type": row.get("type")}
            for row in rows[:20]
        ],
    }


@app.post("/api/ingest/upload")
async def ingest_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip file containing your migration folder")

    job_dir = UPLOADS_DIR / uuid.uuid4().hex[:12]
    job_dir.mkdir(parents=True, exist_ok=True)
    zip_path = job_dir / "upload.zip"

    try:
        content = await file.read()
        zip_path.write_bytes(content)
        extract_dir = job_dir / "folder"
        _safe_extract_zip(zip_path, extract_dir)
        root = _normalize_upload_root(extract_dir)
        scenario = ingest_folder(root)
        scenario_path = job_dir / "scenario.json"
        scenario_path.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = _create_job(scenario, source=f"upload:{file.filename}", scenario_path=scenario_path)
    return {"job_id": job["id"], "summary": job["summary"]}


@app.post("/api/ingest/example")
def ingest_example(body: ExampleIngestRequest) -> dict[str, Any]:
    example_id = body.example_id
    if example_id not in BUILTIN_EXAMPLES:
        raise HTTPException(status_code=404, detail=f"Unknown example: {example_id}")

    job_dir = UPLOADS_DIR / uuid.uuid4().hex[:12]
    job_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = job_dir / "scenario.json"

    try:
        if example_id.startswith("examples/"):
            folder = SCENARIOS_DIR / example_id
            if not folder.is_dir():
                raise HTTPException(status_code=404, detail=f"Example folder not found: {example_id}")
            scenario = ingest_folder(folder)
        else:
            src = SCENARIOS_DIR / f"{example_id}.json"
            if not src.exists():
                raise HTTPException(status_code=404, detail=f"Example scenario not found: {example_id}")
            scenario = json.loads(src.read_text(encoding="utf-8"))
        scenario_path.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = _create_job(scenario, source=f"example:{example_id}", scenario_path=scenario_path)
    return {"job_id": job["id"], "summary": job["summary"]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/migrate")
def migrate(body: MigrateRequest) -> dict[str, Any]:
    job = jobs.get(body.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found. Re-upload or re-select your scenario.")

    scenario_path = Path(job["scenario_path"])
    if not scenario_path.exists():
        raise HTTPException(status_code=404, detail="Scenario file missing on server")

    try:
        client = IdmpClient(body.idmp_url, body.user, body.password)
        migrator = AgenticPiMigrator(client, workers=body.workers)
        dashboards = load_dashboards(scenario_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for spec in dashboards:
        try:
            result = migrator.migrate_dashboard(spec, update_existing=not body.create_new)
            results.append(result)
        except Exception as exc:
            errors.append(f"{spec.name}: {exc}")

    job["migration"] = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "errors": errors,
    }

    return {
        "ok": len(errors) == 0,
        "migrated": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }


@app.get("/")
def index() -> FileResponse:
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Web UI not found")
    return FileResponse(index_path)


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def main() -> None:
    import os

    import uvicorn

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    host = os.environ.get("UI_HOST", "127.0.0.1")
    port = int(os.environ.get("UI_PORT", "8765"))
    uvicorn.run(
        "agentic_pi_migration.web.server:app",
        host=host,
        port=port,
        reload=os.environ.get("UI_RELOAD", "").lower() in ("1", "true", "yes"),
    )


if __name__ == "__main__":
    main()
