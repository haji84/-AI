from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from app.db import SessionLocal
from app.legal_rule_candidate_generation import (
    GENERATOR_VERSION,
    candidate_fingerprint,
    detect_candidate_signals,
)
from app.models import (
    LegalProvision,
    LegalRuleDraftCandidate,
    LegalRuleDraftCitation,
    LegalSourceDocument,
    LegalSourceDocumentVersion,
)


def main() -> None:
    p = argparse.ArgumentParser(description="Generate pending legal Rule relevance candidates from structured provisions.")
    p.add_argument("--source-version-id")
    p.add_argument("--document-id")
    p.add_argument("--limit", type=int, default=500)
    args = p.parse_args()

    inserted = 0
    skipped = 0
    scanned = 0

    with SessionLocal() as db:
        stmt = (
            select(LegalProvision, LegalSourceDocumentVersion, LegalSourceDocument)
            .join(
                LegalSourceDocumentVersion,
                LegalSourceDocumentVersion.legal_source_document_version_id
                == LegalProvision.legal_source_document_version_id,
            )
            .join(
                LegalSourceDocument,
                LegalSourceDocument.legal_source_document_id
                == LegalSourceDocumentVersion.legal_source_document_id,
            )
            .where(LegalProvision.present_in_source.is_(True))
            .order_by(LegalProvision.legal_source_document_version_id, LegalProvision.sequence_no)
        )
        if args.source_version_id:
            stmt = stmt.where(
                LegalProvision.legal_source_document_version_id == args.source_version_id
            )
        if args.document_id:
            stmt = stmt.where(
                LegalSourceDocument.legal_source_document_id == args.document_id
            )

        rows = db.execute(stmt).all()
        for provision, source_version, document in rows:
            if scanned >= max(1, args.limit):
                break
            if provision.provision_type not in {
                "article",
                "paragraph",
                "item",
                "subitem1",
                "subitem2",
                "subitem3",
                "document_body",
            }:
                continue

            signals = detect_candidate_signals(
                "\n".join(
                    x for x in [provision.heading_text, provision.body_text] if x
                ),
                document.title,
            )
            if not signals:
                continue
            scanned += 1

            for signal in signals:
                fingerprint = candidate_fingerprint(
                    source_version_id=source_version.legal_source_document_version_id,
                    provision_id=provision.legal_provision_id,
                    domain=signal.domain,
                )
                exists = db.scalar(
                    select(LegalRuleDraftCandidate).where(
                        LegalRuleDraftCandidate.candidate_fingerprint == fingerprint
                    )
                )
                if exists:
                    skipped += 1
                    continue

                label = provision.display_label or provision.provision_key
                draft = LegalRuleDraftCandidate(
                    source_legal_document_version_id=source_version.legal_source_document_version_id,
                    domain=signal.domain,
                    proposed_rule_code=None,
                    proposed_name=f"要レビュー: {document.title} {label}",
                    proposed_conditions={},
                    proposed_outcome={},
                    extraction_method="deterministic",
                    model_version=None,
                    confidence=signal.confidence,
                    rationale=(
                        "Explicit legal-text keyword match only. "
                        "No legal condition or outcome has been interpreted. "
                        f"Matched terms: {', '.join(signal.matched_terms)}"
                    ),
                    candidate_fingerprint=fingerprint,
                    generation_context={
                        "generator_version": GENERATOR_VERSION,
                        "document_title": document.title,
                        "provision_key": provision.provision_key,
                        "matched_terms": list(signal.matched_terms),
                        "interpretation_status": "required",
                    },
                    status="pending",
                )
                db.add(draft)
                db.flush()
                db.add(
                    LegalRuleDraftCitation(
                        legal_rule_draft_candidate_id=draft.legal_rule_draft_candidate_id,
                        legal_provision_id=provision.legal_provision_id,
                        citation_role="primary",
                    )
                )
                inserted += 1

        db.commit()

    print(
        json.dumps(
            {
                "generator_version": GENERATOR_VERSION,
                "relevant_provisions_scanned": scanned,
                "inserted_candidates": inserted,
                "duplicate_candidates_skipped": skipped,
                "interpretation_policy": "no conditions/outcomes generated automatically",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
