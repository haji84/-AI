from __future__ import annotations

import argparse
import hashlib
import json
import sys
import os
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from official_download import open_official

EGOV_BULK_URL = "https://laws.e-gov.go.jp/bulkdownload"


def build_url(mode: str, update_date: str | None = None) -> str:
    if mode == "all":
        return f"{EGOV_BULK_URL}?file_section=1&only_xml_flag=true"
    if mode == "delta":
        if not update_date or len(update_date) != 8 or not update_date.isdigit():
            raise ValueError("delta mode requires YYYYMMDD update_date")
        return f"{EGOV_BULK_URL}?file_section=3&update_date={update_date}&only_xml_flag=true"
    raise ValueError("mode must be all or delta")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "fire-ai-local-legal-collector/0.1",
            "Accept": "application/zip,application/octet-stream,*/*",
        },
    )
    with open_official(req, timeout=120) as response, dest.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
        return response.geturl()


def collect(mode: str, output_dir: Path, update_date: str | None = None, *, signing_key_file: Path | None = None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    if signing_key_file and list(output_dir.glob("*.manifest.json")):raise ValueError("signed output directory must be new")
    url = build_url(mode, update_date)
    with tempfile.NamedTemporaryFile(prefix="egov-", suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        effective_url=download(url, tmp_path)
        if not isinstance(effective_url,str):effective_url=url
        digest = sha256_file(tmp_path)
        archive_name = f"egov-{mode}-{update_date or 'all'}-{digest[:12]}.zip"
        archive_path = output_dir / archive_name
        if not archive_path.exists():
            os.replace(tmp_path, archive_path)
        else:
            tmp_path.unlink(missing_ok=True)
        manifest = {
            "bundle_format": "fire-ai-legal-update-v1",
            "provider": "e-Gov Law API / bulk XML",
            "authority": "official",
            "mode": mode,
            "update_date": update_date,
            "source_url": url,
            "effective_source_url": effective_url,
            "retrieval_policy": "https-exact-host-redirect-checked-v1",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "archive_file": archive_name,
            "archive_sha256": digest,
            "signature_status": "unsigned",
            "import_policy": "hash-verify-and-review",
        }
        if signing_key_file:
            manifest['signature_status']='signed'
            manifest['import_policy']='signature-verify-and-review'
        manifest_path = output_dir / f"{archive_name}.manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if signing_key_file:
            from app.legal_update_bundle import sign_manifest
            sign_manifest(manifest_path,signing_key_file)
        return manifest
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect official e-Gov bulk legal XML for Local AI update import.")
    parser.add_argument("--mode", choices=["all", "delta"], required=True)
    parser.add_argument("--date", help="YYYYMMDD; required for delta")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument('--signing-key-file',default=os.environ.get('FIRE_AI_COLLECTOR_SIGNING_KEY_FILE'))
    args = parser.parse_args()
    manifest = collect(args.mode, Path(args.output_dir), args.date,signing_key_file=Path(args.signing_key_file) if args.signing_key_file else None)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
