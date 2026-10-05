from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import text
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy.orm import Session

from .db import get_db
from .settings import settings
from .routers import auth, facilities, documents, extensions, templates, contracts, inspections, submissions, intake, legal_rules, legal_sources, legal_rule_drafts, legal_review_queue, equipment, drawings

app = FastAPI(title=settings.app_name, version="0.7.0")


@app.get("/health")
def health(response: Response, db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        db.rollback()
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        database = "unavailable"
    return {"status": "ok" if database == "ok" else "degraded", "phase": 6, "database": database, "ai_required": False}


app.include_router(auth.router)
app.include_router(facilities.router)
app.include_router(documents.router)

app.include_router(extensions.router)
app.include_router(templates.router)
app.include_router(contracts.router)
app.include_router(inspections.router)
app.include_router(submissions.router)
app.include_router(intake.router)
app.include_router(legal_rules.router)
app.include_router(legal_sources.router)
app.include_router(legal_rule_drafts.router)
app.include_router(legal_review_queue.router)
app.include_router(equipment.router)
app.include_router(drawings.router)

_ui = Path(__file__).resolve().parents[2] / "frontend"
if _ui.exists():
    app.mount("/ui", StaticFiles(directory=str(_ui), html=True), name="ui")