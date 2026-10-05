from __future__ import annotations

from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..fire_photo_metadata import (
    ANALYSIS_VERSION,
    NEAR_DUPLICATE_MAX_DISTANCE,
    analyze_photo_file,
    hamming_distance_hex,
    managed_document_path,
)
from ..models import (
    Document,
    FireInvestigationCase,
    FireInvestigationMedia,
    FirePhotoAnnotation,
    FirePhotoProfile,
    User,
)
from ..schemas import (
    FireInvestigationMediaOut,
    FirePhotoAnnotationOut,
    FirePhotoProfileOut,
    FirePhotoSearchItemOut,
)

router = APIRouter(prefix="/fire-photos", tags=["fire-photos"])


def _require_case(db: Session, case_id: str) -> FireInvestigationCase:
    row = db.get(FireInvestigationCase, case_id)
    if not row:
        raise HTTPException(status_code=404, detail="fire investigation case not found")
    return row


def _require_photo_media(db: Session, media_id: str) -> FireInvestigationMedia:
    row = db.get(FireInvestigationMedia, media_id)
    if not row:
        raise HTTPException(status_code=404, detail="fire media not found")
    if row.media_type != "photo":
        raise HTTPException(status_code=409, detail="media is not a photo")
    return row


def _media_out(row: FireInvestigationMedia) -> FireInvestigationMediaOut:
    return FireInvestigationMediaOut(
        fire_investigation_media_id=row.fire_investigation_media_id,
        fire_investigation_case_id=row.fire_investigation_case_id,
        document_id=row.document_id,
        media_type=row.media_type,
        sequence_no=row.sequence_no,
        captured_at=row.captured_at.isoformat() if row.captured_at else None,
        location_label=row.location_label,
        floor_number=row.floor_number,
        notes=row.notes,
        review_status=row.review_status,
        ai_metadata=row.ai_metadata or {},
    )


def _profile_out(row: FirePhotoProfile) -> FirePhotoProfileOut:
    return FirePhotoProfileOut(
        fire_photo_profile_id=row.fire_photo_profile_id,
        fire_investigation_media_id=row.fire_investigation_media_id,
        photo_number=row.photo_number,
        image_width=row.image_width,
        image_height=row.image_height,
        orientation=row.orientation,
        exif_captured_at=row.exif_captured_at.isoformat() if row.exif_captured_at else None,
        camera_make=row.camera_make,
        camera_model=row.camera_model,
        exif_metadata=row.exif_metadata or {},
        exact_sha256=row.exact_sha256,
        perceptual_hash=row.perceptual_hash,
        duplicate_of_media_id=row.duplicate_of_media_id,
        duplicate_distance=row.duplicate_distance,
        brightness_score=row.brightness_score,
        contrast_score=row.contrast_score,
        sharpness_score=row.sharpness_score,
        quality_flags=row.quality_flags or [],
        search_text=row.search_text or "",
        analysis_version=row.analysis_version,
        analyzed_at=row.analyzed_at.isoformat(),
    )


def _annotation_out(row: FirePhotoAnnotation) -> FirePhotoAnnotationOut:
    return FirePhotoAnnotationOut(
        fire_photo_annotation_id=row.fire_photo_annotation_id,
        fire_investigation_media_id=row.fire_investigation_media_id,
        description=row.description,
        tags=row.tags or [],
        map_position=row.map_position or {},
        confidence=row.confidence,
        source_kind=row.source_kind,
        model_version=row.model_version,
        status=row.status,
        version=row.version,
    )


def _stable_photo_number(db: Session, media: FireInvestigationMedia) -> int:
    rows = db.scalars(
        select(FireInvestigationMedia)
        .where(
            FireInvestigationMedia.fire_investigation_case_id
            == media.fire_investigation_case_id,
            FireInvestigationMedia.media_type == "photo",
        )
        .order_by(
            FireInvestigationMedia.sequence_no.asc().nulls_last(),
            FireInvestigationMedia.created_at,
            FireInvestigationMedia.fire_investigation_media_id,
        )
    ).all()
    for idx, row in enumerate(rows, start=1):
        if row.fire_investigation_media_id == media.fire_investigation_media_id:
            return row.sequence_no if row.sequence_no is not None else idx
    return media.sequence_no or 1


def _find_duplicate(
    db: Session,
    *,
    media: FireInvestigationMedia,
    exact_sha256: str,
    perceptual_hash: str | None,
) -> tuple[str | None, int | None]:
    peers = db.execute(
        select(FirePhotoProfile, FireInvestigationMedia)
        .join(
            FireInvestigationMedia,
            FireInvestigationMedia.fire_investigation_media_id
            == FirePhotoProfile.fire_investigation_media_id,
        )
        .where(
            FireInvestigationMedia.fire_investigation_case_id
            == media.fire_investigation_case_id,
            FirePhotoProfile.fire_investigation_media_id
            != media.fire_investigation_media_id,
        )
    ).all()

    for profile, peer_media in peers:
        if profile.exact_sha256 == exact_sha256:
            return peer_media.fire_investigation_media_id, 0

    best_id = None
    best_distance = None
    for profile, peer_media in peers:
        distance = hamming_distance_hex(perceptual_hash, profile.perceptual_hash)
        if distance is None or distance > NEAR_DUPLICATE_MAX_DISTANCE:
            continue
        if best_distance is None or distance < best_distance:
            best_id = peer_media.fire_investigation_media_id
            best_distance = distance
    return best_id, best_distance


def _search_text(
    *,
    doc: Document,
    media: FireInvestigationMedia,
    profile_values: dict,
) -> str:
    parts = [
        doc.original_filename,
        media.location_label or "",
        media.notes or "",
        profile_values.get("camera_make") or "",
        profile_values.get("camera_model") or "",
    ]
    return "\n".join(x.strip() for x in parts if isinstance(x, str) and x.strip())


@router.post("/media/{media_id}/analyze", response_model=FirePhotoProfileOut)
def analyze_fire_photo(
    media_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    media = _require_photo_media(db, media_id)
    doc = db.get(Document, media.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="source photo document not found")
    try:
        values = analyze_photo_file(managed_document_path(doc.storage_path))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="source photo file not found")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"photo metadata analysis failed: {type(exc).__name__}")

    duplicate_id, duplicate_distance = _find_duplicate(
        db,
        media=media,
        exact_sha256=doc.sha256,
        perceptual_hash=values.get("perceptual_hash"),
    )
    profile = db.scalar(
        select(FirePhotoProfile).where(
            FirePhotoProfile.fire_investigation_media_id == media_id
        )
    )
    if profile is None:
        profile = FirePhotoProfile(
            fire_investigation_media_id=media_id,
            exact_sha256=doc.sha256,
        )
        db.add(profile)

    profile.photo_number = _stable_photo_number(db, media)
    profile.image_width = values["image_width"]
    profile.image_height = values["image_height"]
    profile.orientation = values["orientation"]
    profile.exif_captured_at = values["exif_captured_at"]
    profile.camera_make = values["camera_make"]
    profile.camera_model = values["camera_model"]
    profile.exif_metadata = values["exif_metadata"]
    profile.exact_sha256 = doc.sha256
    profile.perceptual_hash = values["perceptual_hash"]
    profile.duplicate_of_media_id = duplicate_id
    profile.duplicate_distance = duplicate_distance
    profile.brightness_score = values["brightness_score"]
    profile.contrast_score = values["contrast_score"]
    profile.sharpness_score = values["sharpness_score"]
    profile.quality_flags = values["quality_flags"]
    profile.search_text = _search_text(doc=doc, media=media, profile_values=values)
    profile.analysis_version = ANALYSIS_VERSION
    profile.analyzed_at = datetime.now(timezone.utc)
    profile.updated_at = datetime.now(timezone.utc)

    # Only fill captured_at when EXIF contains an explicit timezone.
    if media.captured_at is None and values["exif_captured_at"] is not None:
        media.captured_at = values["exif_captured_at"]

    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_photo.metadata.analyze",
        entity_type="fire_photo_profile",
        entity_id=profile.fire_photo_profile_id,
        after={
            "media_id": media_id,
            "photo_number": profile.photo_number,
            "image_width": profile.image_width,
            "image_height": profile.image_height,
            "quality_flags": profile.quality_flags,
            "duplicate_of_media_id": profile.duplicate_of_media_id,
            "duplicate_distance": profile.duplicate_distance,
            "analysis_version": profile.analysis_version,
        },
    )
    db.commit()
    return _profile_out(profile)


@router.get("/media/{media_id}/profile", response_model=FirePhotoProfileOut)
def get_fire_photo_profile(
    media_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    _require_photo_media(db, media_id)
    row = db.scalar(
        select(FirePhotoProfile).where(
            FirePhotoProfile.fire_investigation_media_id == media_id
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="photo profile not analyzed")
    return _profile_out(row)


@router.get("/cases/{case_id}/duplicates", response_model=list[FirePhotoSearchItemOut])
def list_duplicate_photo_candidates(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    _require_case(db, case_id)
    rows = db.execute(
        select(FireInvestigationMedia, FirePhotoProfile)
        .join(
            FirePhotoProfile,
            FirePhotoProfile.fire_investigation_media_id
            == FireInvestigationMedia.fire_investigation_media_id,
        )
        .where(
            FireInvestigationMedia.fire_investigation_case_id == case_id,
            FirePhotoProfile.duplicate_of_media_id.is_not(None),
        )
        .order_by(FirePhotoProfile.duplicate_distance, FirePhotoProfile.photo_number)
    ).all()
    return [
        FirePhotoSearchItemOut(
            media=_media_out(media),
            profile=_profile_out(profile),
            accepted_annotations=[],
            search_score=0,
        )
        for media, profile in rows
    ]


@router.get("/cases/{case_id}/search", response_model=list[FirePhotoSearchItemOut])
def search_fire_photos(
    case_id: str,
    q: str,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    _require_case(db, case_id)
    query = (q or "").strip().lower()
    if not query:
        return []
    terms = [x for x in re.split(r"[\s,、]+", query) if x]

    media_rows = db.scalars(
        select(FireInvestigationMedia)
        .where(
            FireInvestigationMedia.fire_investigation_case_id == case_id,
            FireInvestigationMedia.media_type == "photo",
        )
        .order_by(FireInvestigationMedia.sequence_no, FireInvestigationMedia.created_at)
    ).all()
    out: list[FirePhotoSearchItemOut] = []
    for media in media_rows:
        doc = db.get(Document, media.document_id)
        profile = db.scalar(
            select(FirePhotoProfile).where(
                FirePhotoProfile.fire_investigation_media_id
                == media.fire_investigation_media_id
            )
        )
        annotations = db.scalars(
            select(FirePhotoAnnotation).where(
                FirePhotoAnnotation.fire_investigation_media_id
                == media.fire_investigation_media_id,
                FirePhotoAnnotation.status == "accepted",
            )
        ).all()
        text_parts = [
            doc.original_filename if doc else "",
            media.location_label or "",
            media.notes or "",
            profile.search_text if profile else "",
        ]
        for annotation in annotations:
            text_parts.append(annotation.description or "")
            text_parts.extend(annotation.tags or [])
        haystack = "\n".join(text_parts).lower()
        score = sum(1 for term in terms if term in haystack)
        if score == 0:
            continue
        out.append(
            FirePhotoSearchItemOut(
                media=_media_out(media),
                profile=_profile_out(profile) if profile else None,
                accepted_annotations=[_annotation_out(x) for x in annotations],
                search_score=score,
            )
        )
    out.sort(
        key=lambda x: (
            -x.search_score,
            x.profile.photo_number if x.profile and x.profile.photo_number is not None else 999999,
        )
    )
    return out[: max(1, min(limit, 500))]
