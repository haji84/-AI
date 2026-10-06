from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import text
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy.orm import Session

from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool
from .db import get_db, engine
from .tenant import TenantBoundaryMiddleware, validate_runtime_binding
from .settings import settings
from .routers import emergency_reports, emergency, operations, assets, administration
from .routers import auth, facilities, documents, extensions, templates, contracts, inspections, submissions, intake, legal_rules, legal_sources, legal_rule_drafts, legal_review_queue, equipment, equipment_regression, equipment_placement_regression, drawings, drawing_annotations, drawing_consultations, drawing_benchmarks, fire_investigations, occupancy_regression, fire_report_exports, fire_photos, audio_benchmarks, evidence_benchmarks, search as unified_search

@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(validate_runtime_binding, engine, settings)
    yield


app = FastAPI(title=settings.app_name, version="0.12.0", lifespan=lifespan)
app.add_middleware(TenantBoundaryMiddleware, engine=engine, config=settings)


@app.get("/health")
def health(response: Response, db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        db.rollback()
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        database = "unavailable"
    return {"status": "ok" if database == "ok" else "degraded", "phase": 10, "database": database, "ai_required": False}


app.include_router(auth.router)
app.include_router(administration.router)
app.include_router(emergency_reports.router)
app.include_router(emergency.router)
app.include_router(operations.router)
app.include_router(assets.router)
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
app.include_router(equipment_regression.router)
app.include_router(equipment_placement_regression.router)
app.include_router(drawings.router)
app.include_router(drawing_annotations.router)
app.include_router(drawing_consultations.router)
app.include_router(occupancy_regression.router)
app.include_router(drawing_benchmarks.router)
# Register static audio-benchmark paths before /fire-investigations/{case_id}.
app.include_router(audio_benchmarks.router)
app.include_router(evidence_benchmarks.router)
app.include_router(fire_investigations.router)
app.include_router(fire_report_exports.router)
app.include_router(fire_photos.router)
app.include_router(unified_search.router)

_ui = Path(__file__).resolve().parents[2] / "frontend"
if _ui.exists():
    app.mount("/ui", StaticFiles(directory=str(_ui), html=True), name="ui")
