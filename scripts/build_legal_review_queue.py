from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.legal_relevance import SCANNER_VERSION, score_fire_service_relevance
from app.legal_priority import classify_provision_context, classify_source_priority
REVIEWABLE_TYPES = {
    "article","paragraph","item","subitem1","subitem2","subitem3",
    "subitem4","subitem5","subitem6","document_body"
}

from app.models import (
    LegalProvision,
    LegalProvisionReviewCandidate,
    LegalSourceDocument,
    LegalSourceDocumentVersion,
)


def main() -> None:
    p = argparse.ArgumentParser(description="Populate non-authoritative fire-service legal provision review candidates.")
    p.add_argument("--source-id")
    p.add_argument("--document-id")
    p.add_argument("--version-id")
    p.add_argument("--min-score", type=float, default=2.0)
    p.add_argument("--limit", type=int)
    args = p.parse_args()

    with SessionLocal() as db:
        stmt = (
            select(LegalProvision, LegalSourceDocument.title)
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
        if args.version_id:
            stmt = stmt.where(
                LegalProvision.legal_source_document_version_id == args.version_id
            )
        if args.document_id:
            stmt = stmt.where(LegalSourceDocument.legal_source_document_id == args.document_id)
        if args.source_id:
            stmt = stmt.where(LegalSourceDocument.legal_source_id == args.source_id)
        if args.limit:
            stmt = stmt.limit(max(1, args.limit))

        scanned = 0
        inserted = 0
        updated = 0
        matched_provisions = 0

        for provision, title in db.execute(stmt.execution_options(yield_per=1000)):
            if provision.provision_type not in REVIEWABLE_TYPES:
                continue
            scanned += 1
            source_priority = classify_source_priority(title)
            context_priority = classify_provision_context(provision.provision_key, provision.provision_type)
            hits = [
                x
                for x in score_fire_service_relevance(
                    title=title,
                    label=provision.display_label,
                    heading=provision.heading_text,
                    body=provision.body_text,
                    provision_type=provision.provision_type,
                )
                if x.score >= args.min_score
            ]
            if not hits:
                continue
            matched_provisions += 1
            for hit in hits:
                existing = db.scalar(
                    select(LegalProvisionReviewCandidate).where(
                        LegalProvisionReviewCandidate.legal_provision_id
                        == provision.legal_provision_id,
                        LegalProvisionReviewCandidate.category == hit.category,
                    )
                )
                reasons = [
                    {
                        "scanner_version": SCANNER_VERSION,
                        "match": reason,
                    }
                    for reason in hit.reasons
                ]
                if existing is None:
                    db.add(
                        LegalProvisionReviewCandidate(
                            legal_provision_id=provision.legal_provision_id,
                            category=hit.category,
                            relevance_score=hit.score,
                            priority_lane=source_priority.lane,
                            source_priority_score=source_priority.score,
                            provision_context=context_priority.context,
                            context_priority_score=context_priority.score,
                            reasons=[
                                *reasons,
                                *[
                                    {"priority_lane": source_priority.lane, "source_priority": reason}
                                    for reason in source_priority.reasons
                                ],
                                *(
                                    [{"provision_context": context_priority.context, "context_priority": context_priority.reason}]
                                    if context_priority.reason else []
                                ),
                            ],
                            extraction_method="deterministic",
                            model_version=SCANNER_VERSION,
                        )
                    )
                    inserted += 1
                elif existing.status == "pending":
                    existing.relevance_score = hit.score
                    existing.priority_lane = source_priority.lane
                    existing.source_priority_score = source_priority.score
                    existing.provision_context = context_priority.context
                    existing.context_priority_score = context_priority.score
                    existing.reasons = [
                        *reasons,
                        *[
                            {"priority_lane": source_priority.lane, "source_priority": reason}
                            for reason in source_priority.reasons
                        ],
                        *(
                            [{"provision_context": context_priority.context, "context_priority": context_priority.reason}]
                            if context_priority.reason else []
                        ),
                    ]
                    existing.model_version = SCANNER_VERSION
                    existing.updated_at = datetime.now(timezone.utc)
                    updated += 1

        db.commit()

    print(
        json.dumps(
            {
                "scanner_version": SCANNER_VERSION,
                "scanned_provisions": scanned,
                "matched_provisions": matched_provisions,
                "inserted_candidates": inserted,
                "updated_pending_candidates": updated,
                "min_score": args.min_score,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
