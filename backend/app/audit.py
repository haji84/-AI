from sqlalchemy.orm import Session
from .models import AuditLog


def write_audit(
    db: Session,
    *,
    user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    before=None,
    after=None,
    success: bool = True,
    request_id: str | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before,
            after_data=after,
            success=success,
            request_id=request_id,
        )
    )