from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.legal_structure import PARSER_VERSION
from app.legal_structure_service import structure_legal_version
from app.models import LegalSourceDocumentVersion


def _structure_version(db, version: LegalSourceDocumentVersion) -> dict:
    if not version.raw_document_id:
        versicle/paragraph/item provisions.")
    p.add_argument("--version-id")
    p.add_argument("--source-document-id")
    p.add_argument("--only-unparsed", action="store_true")
    p.add_argument("--limit", type=int)
    args = p.parse_args()

    with SessionLocal() as db:
        stmt = select(LegalSourceDocumentVersion).order_by(LegalSourceDocumentVersion.retrieved_at)
        if args.version_id:
            stmt = stmt.where(LegalSourceDocumentVersion.legal_source_document_version_id == args.version_id)
        if args.source_document_id:
            stmt = stmt.where(LegalSourceDocumentVersion.legal_source_document_id == args.source_document_id)
        if args.only_unparsed:
            stmt = stmt.where(LegalSourceDocumentVersion.structure_status == "unparsed")
        if args.limit:
            stmt = stmt.limit(max(1, args.limit))
        versions = db.scalars(stmt).all()

        results = []
        failures = []
        for version in versions:
            try:
                results.append(structure_legal_version(db, version))
                db.commit()
            except Exception as exc:
                db.rollback()
                failures.append({
                    "version_id": version.legal_source_document_version_id,
                    "error": type(exc).__name__,
                    "message": str(exc)[:500],
                })

    print(json.dumps({
        "processed": len(results),
        "failures": len(failures),
        "parser_version": PARSER_VERSION,
        "results": results,
        "failure_details": failures,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
