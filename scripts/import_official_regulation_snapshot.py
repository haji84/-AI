from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import shutil
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    Document,
    LegalSource,
    LegalSourceDocument,
    LegalSourceDocumentVersion,
    LegalUpdateCandidate,
)
from app.settings import settings
from app.legal_update_bundle import verified_import_inputs, lock_and_validate_freshness, validate_source_snapshot
from app.audit import write_audit
from uuid import UUID


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name_from_url(url: str, fallback: str) -> str:
    name = Path(urllib.parse.urlsplit(url).path).name
    if not name or len(name) > 180:
        return fallback
    return name


def text_from_original(body: bytes, content_type: str | None) -> str:
    ctype = (content_type or "").lower()
    if "html" in ctype:
        parser = TextExtractor()
        parser.feed(body.decode("utf-8", errors="replace"))
        return "\n".join(parser.parts)
    if ctype.startswith("text/") or "xml" in ctype or "json" in ctype:
        return body.decode("utf-8", errors="replace")
    return ""


def main() -> None:
    p = argparse.ArgumentParser(description="Import a collected official regulation snapshot into the legal source/version DB.")
    p.add_argument("--source-id", required=True)
    p.add_argument("--manifest", required=True)
    args = p.parse_args()

    args.source_id=str(UUID(args.source_id))
    with verified_import_inputs(SessionLocal,args.source_id,args.manifest,settings) as verified:
        manifest_path = verified.manifest_path
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        docs = manifest.get("documents") or []
        storage_root = Path(settings.storage_root).resolve()
        target_root = storage_root / "legal_sources" / args.source_id

        inserted = 0
        unchanged = 0
        failures: list[dict] = []

        with SessionLocal() as db:
            lock_and_validate_freshness(db,args.source_id,verified.provenance)
            source = db.get(LegalSource, args.source_id)
            if not source:
                raise SystemExit("legal source not found")
            validate_source_snapshot(source,verified.provenance)
            target_root.mkdir(parents=True, exist_ok=True)

            for item in docs:
                try:
                    source_file = (manifest_path.parent / item["file"]).resolve()
                    body = source_file.read_bytes()
                    digest = sha256_bytes(body)
                    if digest != item["sha256"]:
                        raise ValueError("manifest SHA-256 mismatch")

                    external_id = item["url"]
                    content_type = item.get("content_type")
                    existing_doc = db.scalar(
                        select(LegalSourceDocument).where(
                            LegalSourceDocument.legal_source_id == source.legal_source_id,
                            LegalSourceDocument.external_id == external_id,
                        )
                    )
                    if existing_doc is None:
                        existing_doc = LegalSourceDocument(
                            legal_source_id=source.legal_source_id,
                            external_id=external_id,
                            document_type=(content_type or "unknown").split(";")[0][:80],
                            title=item.get("title") or external_id,
                            source_url=external_id,
                        )
                        db.add(existing_doc)
                        db.flush()

                    already = db.scalar(
                        select(LegalSourceDocumentVersion).where(
                            LegalSourceDocumentVersion.legal_source_document_id == existing_doc.legal_source_document_id,
                            LegalSourceDocumentVersion.sha256 == digest,
                        )
                    )
                    if already:
                        unchanged += 1
                        continue

                    previous = db.scalar(
                        select(LegalSourceDocumentVersion)
                        .where(LegalSourceDocumentVersion.legal_source_document_id == existing_doc.legal_source_document_id)
                        .order_by(LegalSourceDocumentVersion.retrieved_at.desc())
                    )

                    suffix = source_file.suffix or mimetypes.guess_extension((content_type or "").split(";")[0]) or ".bin"
                    stored = target_root / f"{digest}{suffix}"
                    if not stored.exists():
                        shutil.copy2(source_file, stored)
                    rel = str(stored.relative_to(storage_root))
                    doc_row = Document(
                        storage_path=rel,
                        original_filename=safe_name_from_url(external_id, stored.name),
                        sha256=digest,
                        size_bytes=len(body),
                        mime_type=content_type,
                        document_type="legal_source_original",
                    )
                    db.add(doc_row)
                    db.flush()

                    version = LegalSourceDocumentVersion(
                        legal_source_document_id=existing_doc.legal_source_document_id,
                        version_label=manifest.get("retrieved_at"),
                        source_current_date=None,
                        retrieved_at=datetime.now(timezone.utc),
                        raw_document_id=doc_row.document_id,
                        normalized_text=text_from_original(body, content_type),
                        structured_content={
                            "bundle_verification": verified.provenance,
                            "collector_manifest": {
                                "retrieved_at": manifest.get("retrieved_at"),
                                "allowed_host": manifest.get("allowed_host"),
                                "index_url": manifest.get("index_url"),
                            }
                        },
                        source_url=external_id,
                        sha256=digest,
                        previous_version_id=previous.legal_source_document_version_id if previous else None,
                        change_summary={
                            "previous_sha256": previous.sha256 if previous else None,
                            "current_sha256": digest,
                        },
                    )
                    db.add(version)
                    db.flush()
                    db.add(
                        LegalUpdateCandidate(
                            legal_source_document_version_id=version.legal_source_document_version_id,
                            previous_version_id=version.previous_version_id,
                            change_type="amended" if previous else "new",
                            diff_payload=version.change_summary,
                            impacted_rule_ids=[],
                            impacted_modules=[],
                            status="review_required",
                        )
                    )
                    inserted += 1
                except Exception as exc:
                    failures.append({"url": item.get("url"), "error": type(exc).__name__})

            source.captured_document_count = manifest.get("captured_count")
            source.coverage_status = (
                "complete" if manifest.get("complete_candidate") and not failures
                else "partial" if inserted or unchanged
                else "error"
            )
            source.last_full_sync_at = datetime.now(timezone.utc)
            source.last_checked_at = datetime.now(timezone.utc)
            if not failures:
                source.last_success_at = datetime.now(timezone.utc)
            write_audit(db,user_id=None,action='legal.bundle.import',entity_type='legal_source',entity_id=args.source_id,
                        after={**verified.provenance,'inserted_versions':inserted,'unchanged_documents':unchanged,'failure_count':len(failures),'human_review_required':True})
            db.commit()

        print(json.dumps({
            "inserted_versions": inserted,
            "unchanged_documents": unchanged,
            "failure_count": len(failures),
            "coverage_status": source.coverage_status,
            "failures": failures,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
