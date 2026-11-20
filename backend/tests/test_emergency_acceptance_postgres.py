"""Disposable PostgreSQL upgrade, competing review, and immutable snapshots.

Uses synthetic records only. Without the explicitly configured test database,
this is skipped; SQLite results do not stand in for these PostgreSQL checks.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


PREFIX = "/emergency/acceptance"
MIGRATION = "059_emergency_acceptance.sql"
PASSWORD = "synthetic-native-acceptance-password"


def _measurement():
    """Known synthetic miss ensures a nonempty measurement/summary is retained."""
    return {
        "dataset_kind": "synthetic",
        "reports": [
            {
                "report_id": str(uuid4()), "report_version": 1, "cohort": "baseline",
                "followup_complete": True, "corrected_after_submission": True,
                "work_complete": True,
                "work": [{"worker_id": str(uuid4()), "stage": "check",
                          "start_seconds": 0, "end_seconds": 120}],
            },
            {
                "report_id": str(uuid4()), "report_version": 1, "cohort": "assisted",
                "followup_complete": True, "corrected_after_submission": False,
                "independent_review_complete": True, "work_complete": True,
                "work": [{"worker_id": str(uuid4()), "stage": "check",
                          "start_seconds": 0, "end_seconds": 60}],
                "opportunities": [{
                    "opportunity_id": str(uuid4()), "error_id": str(uuid4()),
                    "truth": "error", "decision": "unchecked",
                    "read_state": "unreadable", "verified_read_state": "unreadable",
                }],
            },
        ],
    }


def test_acceptance_upgrade_competing_independent_review_and_immutable_snapshots(tmp_path, monkeypatch):
    url = os.environ.get("FIRE_AI_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("actual PostgreSQL 058-to-059 upgrade/concurrent review requires FIRE_AI_TEST_POSTGRES_URL")
    assert make_url(url).get_backend_name() == "postgresql", "PostgreSQL test URL is required"

    from app.db import get_db
    from app.emergency_acceptance_models import EmergencyAcceptanceEvaluation
    from app.main import app
    from app.migrations import apply_migrations
    from app.models import AuditLog, Employee, Facility, User, UserRole
    from app.personnel import OrganizationUnit
    from app.rbac_seed import seed_rbac
    from app.security import hash_password
    from app.settings import settings
    from app.workforce_models import WorkforceTeam

    root = Path(__file__).resolve().parents[2]
    baseline = tmp_path / "through_058"
    upgraded = tmp_path / "through_059"
    baseline.mkdir()
    upgraded.mkdir()
    for path in (root / "db/migrations").glob("*.sql"):
        if path.name < MIGRATION:
            shutil.copy2(path, baseline / path.name)
        if path.name <= MIGRATION:
            shutil.copy2(path, upgraded / path.name)
    assert (baseline / "058_workforce_teams.sql").exists()
    assert (upgraded / MIGRATION).exists()

    name = "fi_em_accept_" + uuid4().hex[:16]
    admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    target = None
    created_database = False
    previous = dict(app.dependency_overrides)
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    monkeypatch.setattr(settings, "emergency_acceptance_internal_enabled", False)
    try:
        with admin.connect() as connection:
            # Name is generated above from a fixed prefix and hexadecimal UUID.
            connection.exec_driver_sql("CREATE DATABASE " + name)
        created_database = True
        target_url = make_url(url).set(database=name).render_as_string(hide_password=False)
        initial = apply_migrations(target_url, baseline)
        assert initial[-1] == "058_workforce_teams.sql"
        target = create_engine(target_url)

        with Session(target) as db:
            roles = seed_rbac(db)
            author_employee = Employee(display_name="Synthetic acceptance author")
            reviewer_employee = Employee(display_name="Synthetic acceptance reviewer")
            facility = Facility(name="Synthetic preserved acceptance facility", status="active")
            unit = OrganizationUnit(code="SYN-ACCEPT-PG", name="Synthetic preserved unit")
            db.add_all([author_employee, reviewer_employee, facility, unit])
            db.flush()
            author = User(username="native-acceptance-author", employee_id=author_employee.employee_id,
                          password_hash=hash_password(PASSWORD))
            reviewer = User(username="native-acceptance-reviewer", employee_id=reviewer_employee.employee_id,
                            password_hash=hash_password(PASSWORD))
            db.add_all([author, reviewer])
            db.flush()
            db.add_all([
                UserRole(user_id=author.user_id, role_id=roles["emergency_editor"].role_id),
                UserRole(user_id=author.user_id, role_id=roles["emergency_reviewer"].role_id),
                UserRole(user_id=reviewer.user_id, role_id=roles["emergency_reviewer"].role_id),
            ])
            team = WorkforceTeam(
                organization_id=unit.organization_id, code="SYN-PRESERVED", name="Synthetic preserved team",
                reason="Synthetic migration preservation evidence", created_by=author.user_id,
            )
            db.add(team)
            db.commit()
            building_id, team_id = facility.building_id, team.team_id
            author_id, author_employee_id = author.user_id, author_employee.employee_id
            reviewer_id, reviewer_employee_id = reviewer.user_id, reviewer_employee.employee_id

        assert apply_migrations(target_url, upgraded) == [MIGRATION]
        assert apply_migrations(target_url, upgraded) == []
        with Session(target) as db:
            assert db.get(Facility, building_id).name == "Synthetic preserved acceptance facility"
            assert db.get(WorkforceTeam, team_id).name == "Synthetic preserved team"
            assert db.get(User, author_id).employee_id == author_employee_id
            assert db.get(User, reviewer_id).employee_id == reviewer_employee_id
            assert db.scalar(select(func.count()).select_from(EmergencyAcceptanceEvaluation)) == 0
            assert db.execute(text("SELECT count(*) FROM schema_migrations WHERE version=:version"),
                              {"version": MIGRATION}).scalar_one() == 1

        def sessions():
            with Session(target, expire_on_commit=False) as db:
                yield db

        app.dependency_overrides[get_db] = sessions
        with TestClient(app) as client:
            login = client.post("/auth/login", json={"username": "native-acceptance-author", "password": PASSWORD})
            assert login.status_code == 200, login.text
            payload = {"request_id": str(uuid4()), "measurement": _measurement()}
            created = client.post(PREFIX + "/evaluations", json=payload)
            assert created.status_code == 201, created.text
            saved = created.json()
            evaluation_id = saved["evaluation_id"]
            expected_measurement, expected_summary = saved["measurement"], saved["summary"]
            assert expected_summary["metrics"]["recall"]["actual_errors"] == 1
            assert expected_summary["metrics"]["recall"]["detected_errors"] == 0
            assert saved["production_complete"] is False
            assert saved["summary"]["status"] == "DEVELOPMENT_ONLY"
            retry = client.post(PREFIX + "/evaluations", json=payload)
            assert retry.status_code == 200, retry.text
            assert retry.json()["evaluation_id"] == evaluation_id

            review_url = PREFIX + "/evaluations/" + evaluation_id + "/review"
            review_payload = {"expected_version": 1, "decision": "confirmed", "evidence": []}
            # The author has review permission, so this specifically exercises independence.
            assert client.post(review_url, json=review_payload).status_code == 403

            # Even an otherwise valid independent-review transition cannot alter
            # either immutable JSON snapshot. Each attempt rolls back separately.
            transition = (
                ", status='reviewed', version=version+1, review_decision='confirmed',"
                " reviewed_by=:reviewer, reviewed_employee_id=:employee, reviewed_at=now()"
                " WHERE evaluation_id=:identity"
            )
            params = {"identity": evaluation_id, "reviewer": reviewer_id, "employee": reviewer_employee_id}
            for mutation in (
                "measurement=jsonb_set(measurement, '{comparison_confirmed}', 'true'::jsonb)",
                "summary=jsonb_set(summary, '{production_complete}', 'true'::jsonb)",
            ):
                with pytest.raises(IntegrityError) as error:
                    with target.begin() as connection:
                        connection.execute(text("UPDATE emergency_acceptance_evaluations SET " + mutation + transition), params)
                assert error.value.orig.sqlstate == "23514"
            with Session(target) as db:
                row = db.get(EmergencyAcceptanceEvaluation, evaluation_id)
                assert row.status == "recorded" and row.version == 1
                assert row.measurement == expected_measurement and row.summary == expected_summary

            login = client.post("/auth/login", json={"username": "native-acceptance-reviewer", "password": PASSWORD})
            assert login.status_code == 200, login.text
            cookies = dict(client.cookies)
            barrier = Barrier(2)

            def review():
                with TestClient(app) as contender:
                    contender.cookies.update(cookies)
                    barrier.wait(timeout=10)
                    response = contender.post(review_url, json=review_payload)
                    return response.status_code, response.json()

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(review) for _ in range(2)]
                results = [future.result(timeout=30) for future in futures]
            assert sorted(status for status, _ in results) == [200, 409], results
            winner = next(body for status, body in results if status == 200)
            assert winner["version"] == 2 and winner["review_decision"] == "confirmed"
            assert winner["production_complete"] is False
            assert winner["measurement"] == expected_measurement and winner["summary"] == expected_summary

            with Session(target) as db:
                row = db.get(EmergencyAcceptanceEvaluation, evaluation_id)
                assert row.status == "reviewed" and row.version == 2
                assert row.created_by == author_id and row.created_employee_id == author_employee_id
                assert row.reviewed_by == reviewer_id and row.reviewed_employee_id == reviewer_employee_id
                assert row.created_employee_id != row.reviewed_employee_id
                assert row.measurement == expected_measurement and row.summary == expected_summary
                for action in ("create", "review"):
                    assert db.scalar(select(func.count()).select_from(AuditLog).where(
                        AuditLog.action == "emergency.acceptance." + action,
                        AuditLog.entity_id == evaluation_id,
                    )) == 1

            for statement in (
                "UPDATE emergency_acceptance_evaluations SET measurement='{}'::jsonb WHERE evaluation_id=:identity",
                "UPDATE emergency_acceptance_evaluations SET summary='{}'::jsonb WHERE evaluation_id=:identity",
                "UPDATE emergency_acceptance_evaluations SET review_decision='rejected' WHERE evaluation_id=:identity",
                "DELETE FROM emergency_acceptance_evaluations WHERE evaluation_id=:identity",
            ):
                with pytest.raises(IntegrityError) as error:
                    with target.begin() as connection:
                        connection.execute(text(statement), {"identity": evaluation_id})
                assert error.value.orig.sqlstate == "23514"

            reloaded = client.get(PREFIX + "/evaluations/" + evaluation_id)
            assert reloaded.status_code == 200, reloaded.text
            assert reloaded.json()["measurement"] == expected_measurement
            assert reloaded.json()["summary"] == expected_summary
            assert reloaded.json()["review_decision"] == "confirmed"
            assert reloaded.json()["version"] == 2
            assert client.post(review_url, json=review_payload).status_code == 409
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        if target is not None:
            target.dispose()
        if created_database:
            with admin.connect() as connection:
                connection.exec_driver_sql("DROP DATABASE IF EXISTS " + name + " WITH (FORCE)")
        admin.dispose()
