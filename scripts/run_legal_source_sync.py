from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select

from app.db import SessionLocal
from app.models import LegalSource, LegalSyncRun


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def is_due(source: LegalSource, now: datetime) -> bool:
    if not source.enabled:
        return False
    if source.update_mode != "online":
        return False
    if source.last_checked_at is None:
        return True
    last = source.last_checked_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    freq = (source.sync_frequency or "daily").lower()
    if freq == "hourly":
        return now - last >= timedelta(hours=1)
    if freq == "weekly":
        return now - last >= timedelta(days=7)
    return now - last >= timedelta(days=1)


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"command failed: {cmd}")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        return {}
    return json.loads(lines[-1])


def sync_egov(source: LegalSource, work: Path, *, allow_bootstrap: bool) -> dict:
    if source.last_full_sync_at is None:
        if not allow_bootstrap:
            raise RuntimeError("initial e-Gov full bootstrap required; rerun with --allow-bootstrap")
        mode = "all"
        update_date = None
    else:
        mode = "delta"
        last = source.last_success_at or source.last_checked_at or datetime.now(timezone.utc) - timedelta(days=1)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        update_date = last.astimezone(timezone.utc).strftime("%Y%m%d")

    collect_cmd = [
        sys.executable,
        str(SCRIPTS / "collect_egov_update_bundle.py"),
        "--mode", mode,
        "--output-dir", str(work),
    ]
    if update_date:
        collect_cmd += ["--date", update_date]
    manifest = run_json(collect_cmd)

    manifest_files = sorted(work.glob("*.manifest.json"))
    if not manifest_files:
        raise RuntimeError("e-Gov collector did not produce a manifest")
    manifest_path = manifest_files[-1]
    archive_path = work / manifest["archive_file"]
    imported = run_json([
        sys.executable,
        str(SCRIPTS / "import_egov_xml_bundle.py"),
        "--source-id", source.legal_source_id,
        "--archive", str(archive_path),
        "--manifest", str(manifest_path),
    ])
    return {"collector": manifest, "importer": imported}


def sync_official_html(source: LegalSource, work: Path) -> dict:
    config = source.parser_config or {}
    index_url = source.index_url or source.base_url
    allowed_host = config.get("allowed_host") or urlsplit(index_url).hostname
    include_regex = config.get("include_regex")
    crawl_regex = config.get("crawl_regex")
    if not allowed_host or not include_regex or not crawl_regex:
        raise RuntimeError("official_html_crawl requires allowed_host/include_regex/crawl_regex")

    collected = run_json([
        sys.executable,
        str(SCRIPTS / "collect_official_regulation_snapshot.py"),
        "--index-url", index_url,
        "--allowed-host", allowed_host,
        "--include-regex", include_regex,
        "--crawl-regex", crawl_regex,
        "--output-dir", str(work),
        "--max-pages", str(int(config.get("max_pages", 3000))),
        "--max-depth", str(int(config.get("max_depth", 4))),
    ])
    imported = run_json([
        sys.executable,
        str(SCRIPTS / "import_official_regulation_snapshot.py"),
        "--source-id", source.legal_source_id,
        "--manifest", str(work / "manifest.json"),
    ])
    return {"collector": collected, "importer": imported}


def sync_source(source_id: str, *, allow_bootstrap: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        source = db.get(LegalSource, source_id)
        if not source:
            raise RuntimeError("legal source not found")
        if not source.enabled or source.update_mode != "online":
            raise RuntimeError("enabled online legal source required")
        run = LegalSyncRun(legal_source_id=source.legal_source_id, status="running")
        db.add(run)
        source.last_checked_at = now
        db.commit()
        run_id = run.legal_sync_run_id
        adapter = source.adapter_type

    result: dict = {}
    try:
        with tempfile.TemporaryDirectory(prefix="fire-ai-legal-sync-") as tmp:
            work = Path(tmp)
            if adapter == "egov_v2":
                result = sync_egov(source, work, allow_bootstrap=allow_bootstrap)
            elif adapter == "official_html_crawl":
                result = sync_official_html(source, work)
            else:
                raise RuntimeError(f"unsupported online adapter: {adapter}")

        importer = result.get("importer") or {}
        inserted = int(importer.get("inserted_versions", 0) or 0)
        unchanged = int(importer.get("unchanged_documents", 0) or 0)
        errors = int(importer.get("failure_count", 0) or 0)
        with SessionLocal() as db:
            run = db.get(LegalSyncRun, run_id)
            source = db.get(LegalSource, source_id)
            run.status = "completed" if errors == 0 else "completed_with_errors"
            run.completed_at = datetime.now(timezone.utc)
            run.checked_count = inserted + unchanged
            run.new_count = inserted
            run.unchanged_count = unchanged
            run.error_count = errors
            run.details = result
            if errors == 0:
                source.last_success_at = datetime.now(timezone.utc)
            db.commit()
        return {"source_id": source_id, "status": "completed", **result}
    except Exception as exc:
        with SessionLocal() as db:
            run = db.get(LegalSyncRun, run_id)
            source = db.get(LegalSource, source_id)
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.error_count = 1
            run.details = {"error": type(exc).__name__, "message": str(exc)}
            if source.coverage_status == "complete":
                source.coverage_status = "stale"
            db.commit()
        raise


def main() -> None:
    p = argparse.ArgumentParser(description="Run due online legal-source synchronizations.")
    p.add_argument("--source-id")
    p.add_argument("--allow-bootstrap", action="store_true")
    args = p.parse_args()
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        if args.source_id:
            ids = [args.source_id]
        else:
            ids = [
                x.legal_source_id
                for x in db.scalars(select(LegalSource).where(LegalSource.enabled.is_(True))).all()
                if is_due(x, now)
            ]

    results = []
    for source_id in ids:
        try:
            results.append(sync_source(source_id, allow_bootstrap=args.allow_bootstrap))
        except Exception as exc:
            results.append({"source_id": source_id, "status": "failed", "error": type(exc).__name__, "message": str(exc)})

    print(json.dumps({"checked_sources": len(ids), "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
