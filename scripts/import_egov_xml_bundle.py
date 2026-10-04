from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def first_text(root: ET.Element, wanted: str) -> str | None:
    for elem in root.iter():
        if local_name(elem.tag) == wanted:
            text = "".join(elem.itertext()).strip()
            if text:
                return text
    return None


def normalized_text(root: ET.Element) -> str:
    parts: list[str] = []
    for elem in root.iter():
        if local_name(elem.tag) in {"Sentence", "LawTitle", "ArticleTitle", "ParagraphNum", "ItemTitle", "LawNum"}:
            text = "".join(elem.itertext()).strip()
            if text:
                parts.append(text)
    if not parts:
        parts = [x.strip() for x in root.itertext() if x and x.strip()]
    return "\n".join(parts)


def stable_external_id(member_name: str) -> str:
    stem = Path(member_name).stem
    return stem.split("_", 1)[0]


def main() -> None:
    p = argparse.ArgumentParser(description="Import an official e-Gov XML bulk/delta archive into versioned legal storage.")
    p.add_argument("--source-id", required=True)
    p.add_argument("--archive", required=True)
    p.add_argument("--manifest", required=True)
    args = p.parse_args()

    archive_path = Path(args.archive).resolve()
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    archive_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    expected_hash = manifest.get("archive_sha256")
    if expected_hash and expected_hash != archive_hash:
        raise SystemExit("archive SHA-256 does not match manifest")

    storage_root = Path(settings.storage_root).resolve()
    target_root = storage_root / "legal_sources" / args.source_id
    target_root.mkdir(parents=True, exist_ok=True)

    inserted = 0
    unchanged = 0
    failures: list[dict] = []

    with SessionLocal() as db:
        source = db.get(LegalSource, args.source_id)
        if not source:
            raise SystemExit("legal source not found")

        with zipfile.ZipFile(archive_path) as zf:
            members = [name for name in zf.namelist() if name.lower().endswith(".xml") and not name.endswith("/")]
            for member in members:
                try:
                    body = zf.read(member)
                    digest = sha256_bytes(body)
                    root = ET.fromstring(body)
                    ext_id = stable_external_id(member)
                    title = first_text(root, "LawTitle") or ext_id
                    law_num = first_text(root, "LawNum")
                    law_type = root.attrib.get("LawType") or "law"

                    doc = db.scalar(
                        select(LegalSourceDocument).where(
                            LegalSourceDocument.legal_source_id == source.legal_source_id,
                            LegalSourceDocument.external_id == ext_id,
                        )
                    )
                    if doc is None:
                        doc = LegalSourceDocument(
                            legal_source_id=source.legal_source_id,
                            external_id=ext_id,
                            document_type=str(law_type)[:80],
                            title=title,
                            document_number=law_num,
                            source_url=f"https://laws.e-gov.go.jp/law/{ext_id}",
                        )
                        db.add(doc)
                        db.flush()
                    else:
                        doc.title = title
                        if law_num:
                            doc.document_number = law_num
                        doc.updated_at = datetime.now(timezone.utc)

                    exists = db.scalar(
                        select(LegalSourceDocumentVersion).where(
                            LegalSourceDocumentVersion.legal_source_document_id == doc.legal_source_document_id,
                            LegalSourceDocumentVersion.sha256 == digest,
                        )
                    )
                    if exists:
                        unchanged += 1
                        continue

                    previous = db.scalar(
                        select(LegalSourceDocumentVersion)
                        .where(LegalSourceDocumentVersion.legal_source_document_id == doc.legal_source_document_id)
                        .order_by(LegalSourceDocumentVersion.retrieved_at.desc())
                    )

                    stored = target_root / f"{digest}.xml"
                    if not stored.exists():
                        stored.write_bytes(body)
                    rel = str(stored.relative_to(storage_root))
                    raw = Document(
                        storage_path=rel,
                        original_filename=Path(member).name,
                        sha256=digest,
                        size_bytes=len(body),
                        mime_type="application/xml",
                        document_type="legal_source_original",
                    )
                    db.add(raw)
                    db.flush()

                    version = LegalSourceDocumentVersion(
                        legal_source_document_id=doc.legal_source_document_id,
                        version_label=Path(member).stem,
                        revision_external_id=Path(member).stem,
                        retrieved_at=datetime.now(timezone.utc),
                        raw_document_id=raw.document_id,
                        normalized_text=normalized_text(root),
                        structured_content={
                            "root_attributes": dict(root.attrib),
                            "archive_member": member,
                            "provider": "e-Gov",
                            "collector_mode": manifest.get("mode"),
                            "collector_update_date": manifest.get("update_date"),
                        },
                        source_url=f"https://laws.e-gov.go.jp/law/{ext_id}",
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
                    failures.append({"member": member, "error": type(exc).__name__})

        source.last_checked_at = datetime.now(timezone.utc)
        if not failures:
            source.last_success_at = datetime.now(timezone.utc)
        source.captured_document_count = inserted + unchanged
        if manifest.get("mode") == "all":
            source.coverage_status = "complete" if not failures else "partial"
            source.last_full_sync_at = datetime.now(timezone.utc)
        elif failures and source.coverage_status == "complete":
            source.coverage_status = "stale"
        db.commit()

    print(json.dumps({
        "inserted_versions": inserted,
        "unchanged_documents": unchanged,
        "failure_count": len(failures),
        "collector_mode": manifest.get("mode"),
        "failures": failures,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
