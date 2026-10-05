from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..authz import require_permission
from ..audit import write_audit
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
    FirePhotoProfileOut,
    FirePhotoSearchItemOut,
)

router = APIRouter(prefix="/fire-investigations", tags=["fire-photo-intelligence"])


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


def _media_out(media: FireInvestigationMedia):
    from ..schemas import FireInvestigationMediaOut
    return FireInvestigationMediaOut(
        fire_investigation_media_id=media.fire_investigation_media_id,
        fire_investigation_case_id=media.fire_investigation_case_id,
        document_id=media.document_id,
        media_type=media.media_type,
        sequence_no=media.sequence_no,
        captured_at=media.captured_at.isoformat() if media.captured_at else None,
        location_label=media.location_label,
        floor_number=media.floor_number,
        notes=media.notes,
        review_status=media.review_status,
        ai_metadata=media.ai_metadata or {},
    )


def _annotation_out(row: FirePhotoAnnotation):
    from ..schemas import FirePhotoAnnotationOut
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


def _require_photo(db: Session, media_id: str) -> FireInvestigationMedia:
    media=db.get(FireInvestigationMedia,media_id)
    if not media:
        raise HTTPException(status_code=404,detail="fire investigation media not found")
    if media.media_type!="photo":
        raise HTTPException(status_code=422,detail="photo profile requires photo media")
    return media


def _build_search_text(
    media: FireInvestigationMedia,
    profile_data: dict,
    accepted_annotations: list[FirePhotoAnnotation],
) -> str:
    parts=[
        media.location_label or "",
        media.notes or "",
        profile_data.get("camera_make") or "",
        profile_data.get("camera_model") or "",
    ]
    for ann in accepted_annotations:
        parts.append(ann.description or "")
        parts.extend(str(x) for x in (ann.tags or []))
    return "\n".join(x.strip() for x in parts if isinstance(x,str) and x.strip())


def _find_duplicate(
    db: Session,
    *,
    media: FireInvestigationMedia,
    exact_sha256: str,
    perceptual_hash: str | None,
) -> tuple[str | None,int | None]:
    others=db.execute(
        select(FirePhotoProfile,FireInvestigationMedia)
        .join(
            FireInvestigationMedia,
            FireInvestigationMedia.fire_investigation_media_id
            == FirePhotoProfile.fire_investigation_media_id,
        )
        .where(
            FireInvestigationMedia.fire_investigation_case_id==media.fire_investigation_case_id,
            FirePhotoProfile.fire_investigation_media_id!=media.fire_investigation_media_id,
        )
    ).all()

    exact=[(p,m) for p,m in others if p.exact_sha256==exact_sha256]
    if exact:
        exact.sort(key=lambda x:(x[0].photo_number is None,x[0].photo_number or 10**9,x[0].created_at))
        return exact[0][1].fire_investigation_media_id,0

    best_id=None
    best_distance=None
    for profile,other_media in others:
        distance=hamming_distance_hex(perceptual_hash,profile.perceptual_hash)
        if distance is None or distance>NEAR_DUPLICATE_MAX_DISTANCE:
            continue
        if best_distance is None or distance<best_distance:
            best_distance=distance
            best_id=other_media.fire_investigation_media_id
    return best_id,best_distance


@router.post("/media/{media_id}/photo-profile/analyze",response_model=FirePhotoProfileOut)
def analyze_fire_photo(
    media_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    media=_require_photo(db,media_id)
    doc=db.get(Document,media.document_id)
    if not doc:
        raise HTTPException(status_code=409,detail="photo original document not found")
    try:
        path=managed_document_path(doc.storage_path)
        result=analyze_photo_file(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409,detail="photo original file missing") from exc
    except Exception as exc:
        raise HTTPException(status_code=422,detail=f"photo metadata analysis failed: {type(exc).__name__}") from exc

    accepted=list(db.scalars(
        select(FirePhotoAnnotation)
        .where(
            FirePhotoAnnotation.fire_investigation_media_id==media_id,
            FirePhotoAnnotation.status=="accepted",
        )
        .order_by(FirePhotoAnnotation.created_at)
    ).all())
    search_text=_build_search_text(media,result,accepted)
    duplicate_id,distance=_find_duplicate(
        db,
        media=media,
        exact_sha256=doc.sha256,
        perceptual_hash=result.get("perceptual_hash"),
    )

    row=db.scalar(
        select(FirePhotoProfile).where(
            FirePhotoProfile.fire_investigation_media_id==media_id
        )
    )
    if row is None:
        if media.sequence_no is not None:
            photo_number=media.sequence_no
        else:
            max_no=db.scalar(
                select(func.max(FirePhotoProfile.photo_number))
                .join(
                    FireInvestigationMedia,
                    FireInvestigationMedia.fire_investigation_media_id
                    == FirePhotoProfile.fire_investigation_media_id,
                )
                .where(FireInvestigationMedia.fire_investigation_case_id==media.fire_investigation_case_id)
            ) or 0
            photo_number=int(max_no)+1
        row=FirePhotoProfile(
            fire_investigation_media_id=media_id,
            photo_number=photo_number,
            exact_sha256=doc.sha256,
        )
        db.add(row)

    row.image_width=result["image_width"]
    row.image_height=result["image_height"]
    row.orientation=result["orientation"]
    row.exif_captured_at=result["exif_captured_at"]
    row.camera_make=result["camera_make"]
    row.camera_model=result["camera_model"]
    row.exif_metadata=result["exif_metadata"]
    row.exact_sha256=doc.sha256
    row.perceptual_hash=result["perceptual_hash"]
    row.duplicate_of_media_id=duplicate_id
    row.duplicate_distance=distance
    row.brightness_score=result["brightness_score"]
    row.contrast_score=result["contrast_score"]
    row.sharpness_score=result["sharpness_score"]
    row.quality_flags=result["quality_flags"]
    row.search_text=search_text
    row.analysis_version=ANALYSIS_VERSION
    row.analyzed_at=datetime.now(timezone.utc)
    row.updated_at=datetime.now(timezone.utc)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.photo_profile.analyze",
        entity_type="fire_photo_profile",
        entity_id=row.fire_photo_profile_id,
        after={
            "media_id":media_id,
            "analysis_version":ANALYSIS_VERSION,
            "exact_sha256":doc.sha256,
            "perceptual_hash":row.perceptual_hash,
            "duplicate_of_media_id":row.duplicate_of_media_id,
            "duplicate_distance":row.duplicate_distance,
            "quality_flags":row.quality_flags,
        },
    )
    db.commit()
    return _profile_out(row)


@router.get("/media/{media_id}/photo-profile",response_model=FirePhotoProfileOut)
def get_fire_photo_profile(
    media_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    _require_photo(db,media_id)
    row=db.scalar(
        select(FirePhotoProfile).where(
            FirePhotoProfile.fire_investigation_media_id==media_id
        )
    )
    if not row:
        raise HTTPException(status_code=404,detail="photo profile not analyzed")
    return _profile_out(row)


@router.get("/{case_id}/photo-search",response_model=list[FirePhotoSearchItemOut])
def search_fire_photos(
    case_id: str,
    q: str | None = None,
    quality_flag: str | None = None,
    duplicates_only: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    if not db.get(FireInvestigationCase,case_id):
        raise HTTPException(status_code=404,detail="fire investigation case not found")

    medias=list(db.scalars(
        select(FireInvestigationMedia)
        .where(
            FireInvestigationMedia.fire_investigation_case_id==case_id,
            FireInvestigationMedia.media_type=="photo",
        )
        .order_by(FireInvestigationMedia.sequence_no,FireInvestigationMedia.created_at)
    ).all())

    output=[]
    needle=(q or "").strip().lower()
    for media in medias:
        profile=db.scalar(
            select(FirePhotoProfile).where(
                FirePhotoProfile.fire_investigation_media_id==media.fire_investigation_media_id
            )
        )
        annotations=list(db.scalars(
            select(FirePhotoAnnotation)
            .where(
                FirePhotoAnnotation.fire_investigation_media_id==media.fire_investigation_media_id,
                FirePhotoAnnotation.status=="accepted",
            )
            .order_by(FirePhotoAnnotation.created_at)
        ).all())
        if quality_flag and (not profile or quality_flag not in (profile.quality_flags or [])):
            continue
        if duplicates_only and (not profile or not profile.duplicate_of_media_id):
            continue

        blob="\n".join([
            media.location_label or "",
            media.notes or "",
            profile.search_text if profile else "",
            *[(a.description or "") for a in annotations],
            *[str(tag) for a in annotations for tag in (a.tags or [])],
        ]).lower()
        if needle and needle not in blob:
            continue

        score=0
        if needle:
            score+=blob.count(needle)
            score+=sum(2 for a in annotations if needle in (a.description or "").lower())
        output.append(
            FirePhotoSearchItemOut(
                media=_media_out(media),
                profile=_profile_out(profile) if profile else None,
                accepted_annotations=[_annotation_out(x) for x in annotations],
                search_score=score,
            )
        )

    output.sort(
        key=lambda x:(
            -x.search_score,
            x.profile.photo_number if x.profile and x.profile.photo_number is not None else 10**9,
            x.media.sequence_no if x.media.sequence_no is not None else 10**9,
        )
    )
    return output[:max(1,min(limit,500))]
