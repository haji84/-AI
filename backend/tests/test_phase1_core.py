import os, tempfile
import pytest
os.environ["FIRE_AI_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

from fastapi.testclient import TestClient
from sqlalchemy import select
from app.db import Base, engine, SessionLocal
from app.models import User, Employee, Role, Permission, UserRole, RolePermission, Facility
from app.security import hash_password
from app.main import app

Base.metadata.create_all(engine)

def seed():
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username=="tester")): return
        emp=Employee(display_name="テスト利用者"); db.add(emp); db.flush()
        u=User(employee_id=emp.employee_id,username="tester",password_hash=hash_password("long-test-password")); db.add(u)
        r=Role(code="tester",name="Tester"); db.add(r); db.flush()
        db.add(UserRole(user_id=u.user_id,role_id=r.role_id))
        for code in ["facility.read","facility.create","facility.update","facility.restore","document.create","document.read", "inspection.read","inspection.create","inspection.update", "submission.read","submission.create","submission.update","submission.manage", "intake.read","intake.analyze","intake.review","intake.apply", "extension.read","extension.create","extension.review","extension.apply","template.read","template.manage","contract.read","contract.create","contract.update","contract.approve","legal_rule.read","legal_rule.manage","legal_rule.approve","legal_rule.evaluate","legal_source.read","legal_source.manage","legal_source.sync"]:
            p=Permission(code=code,description=code); db.add(p); db.flush(); db.add(RolePermission(role_id=r.role_id,permission_id=p.permission_id))
        db.commit()

seed()
from app.module_seed import seed_modules
from app.submission_seed import seed_submission_types
with SessionLocal() as db:
    seed_modules(db); seed_submission_types(db); db.commit()
client=TestClient(app)

@pytest.fixture(autouse=True)
def reset_database_between_tests():
    # Tests share a StaticPool in-memory SQLite engine. Reset all persistent state
    # so feature flags, roles, submissions, and optimistic-lock versions from one
    # test cannot contaminate the next test.
    client.cookies.clear()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed()
    with SessionLocal() as db:
        seed_modules(db)
        seed_submission_types(db)
        db.commit()
    yield
    client.cookies.clear()

def login():
    r=client.post("/auth/login",json={"username":"tester","password":"long-test-password"})
    assert r.status_code==200

def test_health_without_ai():
    r=client.get("/health"); assert r.status_code==200; assert r.json()["ai_required"] is False

def test_login_create_and_optimistic_lock():
    login()
    r=client.post("/facilities",json={"name":"テスト対象物","address":"テスト住所"})
    assert r.status_code==201
    item=r.json(); bid=item["building_id"]
    r1=client.patch(f"/facilities/{bid}",json={"expected_version":1,"name":"更新後"})
    assert r1.status_code==200 and r1.json()["version"]==2
    stale=client.patch(f"/facilities/{bid}",json={"expected_version":1,"address":"古い画面から更新"})
    assert stale.status_code==409


def test_document_upload_and_hash():
    login()
    r=client.post("/documents/upload", files={"file":("sample.pdf", b"not-a-real-pdf-but-test-bytes", "application/pdf")}, data={"document_type":"test"})
    assert r.status_code==201
    body=r.json()
    assert body["original_filename"]=="sample.pdf"
    assert len(body["sha256"])==64
    r2=client.get(f"/documents/{body['document_id']}")
    assert r2.status_code==200 and r2.json()["sha256"]==body["sha256"]


def test_rbac_policy_separates_emergency_summary_from_patient_detail():
    from app.rbac_seed import seed_rbac
    from app.models import Role, Permission, RolePermission
    with SessionLocal() as db:
        roles = seed_rbac(db)
        db.commit()
        reporter = roles["emergency_reporter"]
        codes = set(db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
            .where(RolePermission.role_id == reporter.role_id)
        ).all())
        assert "emergency.report.read" in codes
        assert "emergency.patient.read" not in codes
        assert "emergency.case.read" not in codes


def test_abolish_and_restore_with_version_lock():
    login()
    r=client.post("/facilities",json={"name":"廃止復元テスト"})
    assert r.status_code==201
    item=r.json(); bid=item["building_id"]
    a=client.post(f"/facilities/{bid}/abolish",json={"expected_version":1})
    assert a.status_code==200 and a.json()["status"]=="abolished" and a.json()["version"]==2
    stale=client.post(f"/facilities/{bid}/restore",json={"expected_version":1})
    assert stale.status_code==409
    restored=client.post(f"/facilities/{bid}/restore",json={"expected_version":2})
    assert restored.status_code==200 and restored.json()["status"]=="active" and restored.json()["version"]==3


def test_migration_splitter_handles_comments_and_quoted_semicolons():
    from app.migrations import split_sql
    sql="""-- first; comment\nCREATE TABLE a(x text);\nINSERT INTO a(x) VALUES ('a;b'); /* c; */\nCREATE TABLE \"semi;name\"(x integer);"""
    parts=split_sql(sql)
    assert len(parts)==3
    assert "'a;b'" in parts[1]


def test_phase2_facility_list_search():
    login()
    client.post("/facilities", json={"name":"検索対象ABC","address":"特別住所XYZ","legacy_internal_key":"LEGACY-SEARCH"})
    r=client.get("/facilities", params={"q":"特別住所XYZ"})
    assert r.status_code==200
    body=r.json(); assert body["total"] >= 1
    assert any(x["name"]=="検索対象ABC" for x in body["items"])


def test_extension_change_request_requires_review_before_human_approval():
    login()
    r=client.post("/extensions/change-requests",json={"title":"対象物画面改善","request_text":"右上に未提出件数を表示して","target_module":"prevention","target_surface":"facility_detail"})
    assert r.status_code==201
    cr=r.json(); cid=cr["change_request_id"]
    blocked=client.post(f"/extensions/change-requests/{cid}/approve",json={"expected_version":1})
    assert blocked.status_code==409
    reviewed=client.post(f"/extensions/change-requests/{cid}/review",json={"expected_version":1,"risk_level":"low","analysis":{"db_change":False},"proposed_changes":{"ui":"badge"},"acceptance_criteria":["未提出件数を表示"],"sandbox_result":{"tests":"pass"}})
    assert reviewed.status_code==200 and reviewed.json()["status"]=="reviewed" and reviewed.json()["version"]==2
    approved=client.post(f"/extensions/change-requests/{cid}/approve",json={"expected_version":2})
    assert approved.status_code==200 and approved.json()["status"]=="approved" and approved.json()["version"]==3


def test_official_form_template_registers_original_document():
    login()
    upload=client.post("/documents/upload",files={"file":("official.xlsx",b"official-template-bytes","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},data={"document_type":"official_form"})
    assert upload.status_code==201
    doc=upload.json()
    r=client.post("/templates",json={"template_code":"CONTRACT-001","name":"契約書正式様式","module_code":"contracts","document_id":doc["document_id"],"version_label":"2026-01","issuer":"test issuer","effective_from":"2026-04-01","field_mapping":{"A1":"contract_no"},"print_settings":{"paper":"A4"},"modification_policy":"fill_only"})
    assert r.status_code==201
    body=r.json(); assert body["document_id"]==doc["document_id"] and body["modification_policy"]=="fill_only"
    latest=client.get("/templates/CONTRACT-001/latest",params={"on_date":"2026-10-04"})
    assert latest.status_code==200 and latest.json()["version_label"]=="2026-01"


def test_contract_optimistic_lock_and_explicit_approval():
    login()
    cp=client.post("/contracts/counterparties",json={"name":"テスト契約先"})
    assert cp.status_code==201
    r=client.post("/contracts",json={"contract_no":"TEST-2026-001","title":"テスト修繕","counterparty_id":cp.json()["counterparty_id"],"amount":1250000,"start_date":"2026-10-10","end_date":"2027-01-31"})
    assert r.status_code==201
    c=r.json(); cid=c["contract_case_id"]
    p=client.patch(f"/contracts/{cid}",json={"expected_version":1,"amount":1430000,"end_date":"2027-02-28"})
    assert p.status_code==200 and p.json()["version"]==2
    stale=client.patch(f"/contracts/{cid}",json={"expected_version":1,"title":"古い更新"})
    assert stale.status_code==409
    approved=client.post(f"/contracts/{cid}/approve",json={"expected_version":2})
    assert approved.status_code==200 and approved.json()["status"]=="approved" and approved.json()["version"]==3


def test_module_registry_is_seeded():
    login()
    r=client.get("/extensions/modules")
    assert r.status_code==200
    codes={x["code"] for x in r.json()}
    assert {"prevention","emergency_reporting","fire_investigation","contracts","extensions"}.issubset(codes)


def test_feature_flag_and_deployment_rollback_are_auditable():
    login()
    cr=client.post("/extensions/change-requests",json={"title":"テスト拡張","request_text":"テスト機能追加","target_module":"prevention"}).json()
    reviewed=client.post(f"/extensions/change-requests/{cr['change_request_id']}/review",json={"expected_version":1,"risk_level":"low","analysis":{},"proposed_changes":{},"acceptance_criteria":["test"],"sandbox_result":{"tests":"pass"}}).json()
    approved=client.post(f"/extensions/change-requests/{cr['change_request_id']}/approve",json={"expected_version":reviewed["version"]}).json()
    flags=client.get("/extensions/feature-flags").json()
    target=next(x for x in flags if x["key"]=="module.prevention.enabled")
    dep=client.post(f"/extensions/change-requests/{cr['change_request_id']}/deployments",json={"module_code":"prevention","release_version":"1.1.0","previous_version":"1.0.0","migration_version":"004-test","feature_flag_key":target["key"],"evidence":{"tests":"pass"}})
    assert dep.status_code==201 and dep.json()["status"]=="applied"
    rollback=client.post(f"/extensions/deployments/{dep.json()['extension_deployment_id']}/rollback")
    assert rollback.status_code==200 and rollback.json()["status"]=="rollback_applied"
    flags2=client.get("/extensions/feature-flags").json()
    target2=next(x for x in flags2 if x["key"]=="module.prevention.enabled")
    assert target2["enabled"] is False


def test_phase2_browser_preview_is_served():
    r=client.get("/ui/")
    assert r.status_code==200
    assert "消防業務 Local AI" in r.text
    assert "防火対象物" in r.text


def test_phase2_facility_detail_nested_crud_history_and_conflict_payload():
    login()
    created = client.post(
        "/facilities",
        json={
            "name": "Phase2詳細テスト",
            "phone": "0997-test",
            "address": "詳細住所",
            "legacy_serial_no": "S-200",
            "detail": {
                "classification_code": "テスト区分",
                "structure": "RC",
                "above_ground_floors": 2,
                "building_area": 120.5,
                "total_floor_area": 220.5,
            },
            "contact": {"representative_name": "代表者テスト"},
            "floors": [
                {"floor_number": 1, "floor_label": "1階", "floor_area": 120.5, "use_name": "店舗", "occupancy_count": 20},
                {"floor_number": 2, "floor_label": "2階", "floor_area": 100.0, "use_name": "事務所", "occupancy_count": 10},
            ],
        },
    )
    assert created.status_code == 201
    bid = created.json()["building_id"]
    detail = client.get(f"/facilities/{bid}/detail")
    assert detail.status_code == 200
    body = detail.json()
    assert body["facility"]["phone"] == "0997-test"
    assert body["detail"]["classification_code"] == "テスト区分"
    assert body["contact"]["representative_name"] == "代表者テスト"
    assert len(body["floors"]) == 2

    updated = client.patch(
        f"/facilities/{bid}",
        json={
            "expected_version": 1,
            "name": "Phase2詳細更新",
            "detail": {"classification_code": "更新区分", "structure": "S", "above_ground_floors": 1},
            "contact": {"representative_name": "更新代表者"},
            "floors": [{"floor_number": 1, "floor_label": "1階", "use_name": "飲食店", "occupancy_count": 35}],
        },
    )
    assert updated.status_code == 200 and updated.json()["version"] == 2
    stale = client.patch(f"/facilities/{bid}", json={"expected_version": 1, "address": "古い編集"})
    assert stale.status_code == 409
    conflict = stale.json()["detail"]
    assert conflict["message"] == "record was updated by another user"
    assert conflict["current"]["facility"]["version"] == 2

    history = client.get(f"/facilities/{bid}/history")
    assert history.status_code == 200
    actions = [x["action"] for x in history.json()]
    assert "facility.create" in actions and "facility.update" in actions


def test_phase2_pagination_sort_and_serial_search():
    login()
    for name, serial in [("ZZZ並びテスト", "SER-Z"), ("AAA並びテスト", "SER-A")]:
        r = client.post("/facilities", json={"name": name, "legacy_serial_no": serial})
        assert r.status_code == 201
    by_serial = client.get("/facilities", params={"q": "SER-A", "limit": 10})
    assert by_serial.status_code == 200
    assert any(x["legacy_serial_no"] == "SER-A" for x in by_serial.json()["items"])
    sorted_r = client.get("/facilities", params={"q": "並びテスト", "sort_by": "name", "sort_dir": "asc", "limit": 1, "offset": 0})
    assert sorted_r.status_code == 200 and sorted_r.json()["total"] >= 2
    assert sorted_r.json()["items"][0]["name"].startswith("AAA")


def test_phase2_duplicate_floor_rejected():
    login()
    r = client.post(
        "/facilities",
        json={"name": "重複階テスト", "floors": [{"floor_number": 1}, {"floor_number": 1}]},
    )
    assert r.status_code == 422


def test_phase2_browser_has_crud_and_conflict_ui():
    r = client.get("/ui/")
    assert r.status_code == 200
    assert "新規対象物" in r.text
    assert "他の職員が先に更新しています" in r.text
    assert "旧台帳の意味未確定項目" in r.text


def test_phase2_partial_nested_patch_preserves_unspecified_detail_fields():
    login()
    created = client.post(
        "/facilities",
        json={"name": "部分更新テスト", "detail": {"classification_code": "元区分", "structure": "RC", "zoning": "元用途地域"}},
    )
    bid = created.json()["building_id"]
    patched = client.patch(f"/facilities/{bid}", json={"expected_version": 1, "detail": {"structure": "S"}})
    assert patched.status_code == 200
    detail = client.get(f"/facilities/{bid}/detail").json()["detail"]
    assert detail["structure"] == "S"
    assert detail["classification_code"] == "元区分"
    assert detail["zoning"] == "元用途地域"



def test_phase3_inspection_findings_workflow():
    login()
    facility = client.post("/facilities", json={"name": "Phase3査察対象"}).json()
    bid = facility["building_id"]
    created = client.post("/inspections", json={
        "building_id": bid,
        "inspected_at": "2026-10-05",
        "inspection_type": "定期査察",
        "findings": [{"category": "防火管理", "finding_text": "消防計画を確認", "severity": "medium"}],
    })
    assert created.status_code == 201
    inspection = created.json()
    assert len(inspection["findings"]) == 1
    finding = inspection["findings"][0]
    updated = client.patch(f"/inspections/findings/{finding['finding_id']}", json={
        "expected_version": 1,
        "corrective_status": "completed",
        "completed_at": "2026-10-06",
    })
    assert updated.status_code == 200
    assert updated.json()["corrective_status"] == "completed"
    stale = client.patch(f"/inspections/findings/{finding['finding_id']}", json={"expected_version": 1, "notes": "stale"})
    assert stale.status_code == 409
    listing = client.get("/inspections", params={"building_id": bid})
    assert listing.status_code == 200 and listing.json()[0]["inspection_type"] == "定期査察"


def test_phase3_submission_receipt_updates_facility_status_and_links_original():
    login()
    facility = client.post("/facilities", json={"name": "Phase3届出対象"}).json()
    bid = facility["building_id"]
    upload = client.post(
        "/documents/upload",
        files={"file": ("scan0001.pdf", b"phase3-source", "application/pdf")},
        data={"document_type": "submission_source"},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["document_id"]
    receipt = client.post("/submissions", json={
        "building_id": bid,
        "submission_type_code": "fire_manager_appointment",
        "official_number": "1234",
        "submitted_at": "2026-10-05",
        "submitted_by": "届出者",
        "document_ids": [doc_id],
        "payload_data": {"manager_name": "管理者テスト", "manager_title": "店長", "appointed_at": "2026-10-01"},
    })
    assert receipt.status_code == 201
    body = receipt.json()
    assert body["official_number"] == "1234" and body["document_ids"] == [doc_id]
    bad = client.post("/submissions", json={
        "building_id": bid,
        "submission_type_code": "fire_plan",
        "official_number": "予防1234号",
        "document_ids": [doc_id],
    })
    assert bad.status_code == 422
    dashboard = client.get(f"/facilities/{bid}/dashboard")
    assert dashboard.status_code == 200
    statuses = {x["code"]: x for x in dashboard.json()["submission_statuses"]}
    assert statuses["fire_manager_appointment"]["state"] == "received"
    assert statuses["fire_plan"]["state"] == "not_submitted"


def test_phase3_required_document_and_submission_optimistic_lock():
    login()
    facility = client.post("/facilities", json={"name": "Phase3提出対象"}).json()
    bid = facility["building_id"]
    missing = client.post("/submissions", json={
        "building_id": bid,
        "submission_type_code": "equipment_inspection_report",
        "official_number": "99",
    })
    assert missing.status_code == 422
    upload = client.post("/documents/upload", files={"file": ("IMG_0001.jpg", b"imagebytes", "image/jpeg")}, data={"document_type": "submission_source"}).json()
    created = client.post("/submissions", json={
        "building_id": bid,
        "submission_type_code": "equipment_inspection_report",
        "official_number": "99",
        "submitted_at": "2026-10-05",
        "document_ids": [upload["document_id"]],
        "payload_data": {"inspection_date": "2026-09-30", "result_summary": "不良2件"},
    })
    assert created.status_code == 201
    sid = created.json()["submission_id"]
    updated = client.patch(f"/submissions/{sid}", json={"expected_version": 1, "status": "reviewed"})
    assert updated.status_code == 200 and updated.json()["version"] == 2
    stale = client.patch(f"/submissions/{sid}", json={"expected_version": 1, "notes": "old"})
    assert stale.status_code == 409



def test_phase3_inspection_findings_dashboard_and_conflict():
    login()
    f=client.post("/facilities",json={"name":"Phase3査察テスト"}).json()
    bid=f["building_id"]
    r=client.post("/inspections",json={
        "building_id":bid,"inspected_at":"2026-10-05","inspection_type":"general","notes":"初回査察",
        "findings":[{"category":"設備","finding_text":"誘導灯を確認","severity":"medium","due_date":"2026-11-01"}]
    })
    assert r.status_code==201
    ins=r.json(); assert len(ins["findings"])==1
    iid=ins["inspection_id"]; fid=ins["findings"][0]["finding_id"]
    patched=client.patch(f"/inspection-findings/{fid}",json={"expected_version":1,"corrective_status":"completed","completed_at":"2026-10-10"})
    assert patched.status_code==200 and patched.json()["version"]==2
    stale=client.patch(f"/inspection-findings/{fid}",json={"expected_version":1,"notes":"古い画面"})
    assert stale.status_code==409
    dash=client.get(f"/facilities/{bid}/dashboard")
    assert dash.status_code==200
    assert dash.json()["inspections_total"]==1
    assert dash.json()["open_findings"]==0
    assert dash.json()["latest_inspection_at"]=="2026-10-05"
    listed=client.get(f"/facilities/{bid}/inspections")
    assert listed.status_code==200 and listed.json()[0]["inspection_id"]==iid


def test_phase3_submission_original_document_status_and_specialized_data():
    from app.models import EquipmentInspectionReport
    login()
    f=client.post("/facilities",json={"name":"Phase3届出テスト"}).json(); bid=f["building_id"]
    up=client.post("/documents/upload",files={"file":("scan0001.pdf",b"phase3-original","application/pdf")},data={"building_id":bid,"document_type":"submission_original"})
    assert up.status_code==201
    doc=up.json()
    r=client.post("/submissions",json={
        "building_id":bid,"submission_type_code":"equipment_inspection_report","official_number":"00123",
        "submitted_at":"2026-10-05","submitted_by":"届出者","document_ids":[doc["document_id"]],
        "payload_data":{"inspection_date":"2026-09-20","result_summary":"不良2件","next_due_at":"2027-03-31"}
    })
    assert r.status_code==201
    sub=r.json(); assert sub["official_number"]=="00123" and doc["document_id"] in sub["document_ids"]
    with SessionLocal() as db:
        spec=db.scalar(select(EquipmentInspectionReport).where(EquipmentInspectionReport.submission_id==sub["submission_id"]))
        assert spec is not None and spec.result_summary=="不良2件"
    dash=client.get(f"/facilities/{bid}/dashboard").json()
    status_by={x["code"]:x for x in dash["submission_statuses"]}
    assert status_by["equipment_inspection_report"]["state"]=="received"
    assert status_by["equipment_inspection_report"]["detail"]["requirement_status"]=="not_evaluated"
    assert status_by["fire_manager_appointment"]["state"]=="not_submitted"
    assert status_by["fire_plan"]["state"]=="not_submitted"


def test_phase3_submission_official_number_digits_only_and_document_scope():
    login()
    f1=client.post("/facilities",json={"name":"届出対象A"}).json()
    f2=client.post("/facilities",json={"name":"届出対象B"}).json()
    up=client.post("/documents/upload",files={"file":("arbitrary-name.pdf",b"other-facility","application/pdf")},data={"building_id":f1["building_id"],"document_type":"submission_original"}).json()
    bad_no=client.post("/submissions",json={"building_id":f1["building_id"],"submission_type_code":"fire_plan","official_number":"予防123号","document_ids":[up["document_id"]]})
    assert bad_no.status_code==422
    wrong=client.post("/submissions",json={"building_id":f2["building_id"],"submission_type_code":"fire_plan","official_number":"123","document_ids":[up["document_id"]]})
    assert wrong.status_code==409


def test_phase3_submission_patch_optimistic_lock_and_fire_manager_plan():
    login()
    f=client.post("/facilities",json={"name":"Phase3管理計画テスト"}).json(); bid=f["building_id"]
    docs=[]
    for name in ("manager.pdf","plan.pdf"):
        docs.append(client.post("/documents/upload",files={"file":(name,b"doc-"+name.encode(),"application/pdf")},data={"building_id":bid,"document_type":"submission_original"}).json()["document_id"])
    manager=client.post("/submissions",json={"building_id":bid,"submission_type_code":"fire_manager_appointment","official_number":"200","submitted_at":"2026-10-01","document_ids":[docs[0]],"payload_data":{"manager_name":"山田太郎","manager_title":"店長","appointed_at":"2026-09-01"}})
    assert manager.status_code==201
    plan=client.post("/submissions",json={"building_id":bid,"submission_type_code":"fire_plan","official_number":"201","submitted_at":"2026-10-02","document_ids":[docs[1]],"payload_data":{"plan_version_label":"2026改訂"}})
    assert plan.status_code==201
    sid=plan.json()["submission_id"]
    p=client.patch(f"/submissions/{sid}",json={"expected_version":1,"status":"reviewed","notes":"確認済"})
    assert p.status_code==200 and p.json()["version"]==2
    stale=client.patch(f"/submissions/{sid}",json={"expected_version":1,"notes":"古い更新"})
    assert stale.status_code==409
    dash=client.get(f"/facilities/{bid}/dashboard").json()
    states={x["code"]:x["state"] for x in dash["submission_statuses"]}
    assert states["fire_manager_appointment"]=="received" and states["fire_plan"]=="reviewed"


def test_phase3_submission_type_alias_used_by_browser():
    login()
    r=client.get("/submissions/types")
    assert r.status_code==200
    codes={x["code"] for x in r.json()}
    assert {"equipment_inspection_report","fire_manager_appointment","fire_plan"}.issubset(codes)


def test_phase3_migration_enforces_digits_only_official_number():
    from pathlib import Path
    sql=(Path(__file__).resolve().parents[2]/"db"/"migrations"/"006_phase3_inspections_submissions.sql").read_text(encoding="utf-8")
    assert "official_number ~ '^[0-9]+$'" in sql


def test_phase3_prevention_role_has_inspection_submission_permissions_but_not_type_management():
    from app.rbac_seed import seed_rbac
    with SessionLocal() as db:
        roles=seed_rbac(db); db.commit()
        role=roles["prevention_editor"]
        codes=set(db.scalars(select(Permission.code).join(RolePermission,RolePermission.permission_id==Permission.permission_id).where(RolePermission.role_id==role.role_id)).all())
        assert {"inspection.read","inspection.create","inspection.update","submission.read","submission.create","submission.update"}.issubset(codes)
        assert "submission.manage" not in codes


def test_phase3_legacy_prevention_values_preserve_raw_and_dashboard_marks_legacy_recorded():
    from app.importers.facility_normalization import normalize_facility_from_raw
    from app.models import FireManagementAssignment, FirePlan, EquipmentInspectionReport, GuidanceRecord
    login()
    created=client.post('/facilities',json={'name':'旧台帳Phase3移行テスト'}).json(); bid=created['building_id']
    raw={
        'HC':'管理者名','HD':'店長','HE':'R4.1.19\n届出済','HF':'提出済',
        'CN':'消火器','IU':'44580','IV':'44581',
        'JO':'立入検査','JP':'H29.11.7 担当者','JQ':'指摘事項なし',
    }
    with SessionLocal() as db:
        facility=db.get(Facility,bid)
        normalize_facility_from_raw(db,facility,raw)
        db.commit()
        manager=db.scalar(select(FireManagementAssignment).where(FireManagementAssignment.building_id==bid))
        plan=db.scalar(select(FirePlan).where(FirePlan.building_id==bid))
        equip=db.scalar(select(EquipmentInspectionReport).where(EquipmentInspectionReport.building_id==bid))
        guidance=db.scalar(select(GuidanceRecord).where(GuidanceRecord.building_id==bid))
        assert manager.appointment_submitted_at.isoformat()=='2022-01-19'
        assert manager.raw_submission_text.startswith('R4.1.19')
        assert plan.submitted_at is None and plan.raw_submission_text=='提出済'
        assert equip.inspection_date.isoformat()=='2022-01-19'
        assert equip.submitted_at.isoformat()=='2022-01-20'
        assert guidance.issued_at.isoformat()=='2017-11-07'
        assert guidance.raw_issued_text.startswith('H29.11.7')
    dashboard=client.get(f'/facilities/{bid}/dashboard')
    assert dashboard.status_code==200
    states={x['code']:x for x in dashboard.json()['submission_statuses']}
    assert states['equipment_inspection_report']['state']=='legacy_recorded'
    assert states['fire_manager_appointment']['state']=='legacy_recorded'
    assert states['fire_plan']['state']=='legacy_recorded'
    assert states['fire_plan']['detail']['raw_submission_text']=='提出済'


def test_phase3_legacy_manager_name_does_not_claim_submission_evidence():
    from app.importers.facility_normalization import normalize_facility_from_raw
    login()
    bid=client.post('/facilities',json={'name':'管理者のみ旧記録'}).json()['building_id']
    with SessionLocal() as db:
        facility=db.get(Facility,bid)
        normalize_facility_from_raw(db,facility,{'HC':'氏名のみ'})
        db.commit()
    states={x['code']:x for x in client.get(f'/facilities/{bid}/dashboard').json()['submission_statuses']}
    assert states['fire_manager_appointment']['state']=='legacy_manager_only'
    assert states['fire_manager_appointment']['detail']['submission_evidence_recorded'] is False



def test_phase4_text_document_analysis_review_and_receipt_human_gate():
    login()
    facility = client.post("/facilities", json={
        "name": "Phase4ホテル",
        "address": "鹿児島県テスト町旧住所1番地",
        "phone": "0997-11-1111",
    }).json()
    bid = facility["building_id"]
    text = """消防用設備等点検結果報告書
防火対象物名称: Phase4ホテル
所在地: 鹿児島県テスト町新住所2番地
電話番号: 0997-22-2222
令和8年10月5日
""".encode("utf-8")
    uploaded = client.post(
        "/documents/upload",
        files={"file": ("scan0001.txt", text, "text/plain")},
        data={"document_type": "submission_source"},
    )
    assert uploaded.status_code == 201
    doc_id = uploaded.json()["document_id"]
    analyzed = client.post("/document-analyses", json={"document_id": doc_id})
    assert analyzed.status_code == 201
    body = analyzed.json()
    assert body["detected_submission_type_code"] == "equipment_inspection_report"
    assert body["facility_candidates"][0]["building_id"] == bid
    assert body["detected_fields"]["address"] == "鹿児島県テスト町新住所2番地"
    assert "facility.address" in body["difference_candidates"]

    blocked = client.post(
        f"/document-analyses/{body['document_analysis_id']}/confirm-receipt",
        json={"expected_version": body["version"], "official_number": "1001"},
    )
    assert blocked.status_code == 409

    reviewed = client.post(
        f"/document-analyses/{body['document_analysis_id']}/review",
        json={"expected_version": body["version"], "building_id": bid},
    )
    assert reviewed.status_code == 200
    reviewed_body = reviewed.json()
    assert reviewed_body["status"] == "reviewed"
    proposals = client.get(f"/document-analyses/{body['document_analysis_id']}/change-proposals")
    assert proposals.status_code == 200 and len(proposals.json()) == 1

    invalid_number = client.post(
        f"/document-analyses/{body['document_analysis_id']}/confirm-receipt",
        json={"expected_version": reviewed_body["version"], "official_number": "予防1001号"},
    )
    assert invalid_number.status_code == 422
    confirmed = client.post(
        f"/document-analyses/{body['document_analysis_id']}/confirm-receipt",
        json={"expected_version": reviewed_body["version"], "official_number": "1001", "submitted_at": "2026-10-05"},
    )
    assert confirmed.status_code == 201
    assert confirmed.json()["building_id"] == bid
    assert confirmed.json()["document_ids"] == [doc_id]


def test_phase4_change_proposal_requires_explicit_paths_and_facility_version():
    login()
    facility = client.post("/facilities", json={
        "name": "Phase4差分対象",
        "address": "鹿児島県旧住所12345",
        "phone": "0997-00-0000",
    }).json()
    bid = facility["building_id"]
    source = """防火管理者選任届出書
防火対象物名称: Phase4差分対象
所在地: 鹿児島県新住所54321
電話番号: 0997-99-9999
防火管理者氏名: 山田太郎
""".encode("utf-8")
    doc = client.post("/documents/upload", files={"file": ("random.txt", source, "text/plain")}, data={"document_type":"submission_source"}).json()
    analysis = client.post("/document-analyses", json={"document_id": doc["document_id"]}).json()
    reviewed = client.post(
        f"/document-analyses/{analysis['document_analysis_id']}/review",
        json={"expected_version": analysis["version"], "building_id": bid},
    ).json()
    proposal = client.get(f"/document-analyses/{analysis['document_analysis_id']}/change-proposals").json()[0]

    none = client.post(
        f"/facility-change-proposals/{proposal['facility_change_proposal_id']}/apply",
        json={"expected_version": proposal["version"], "expected_facility_version": 1, "accepted_paths": []},
    )
    assert none.status_code == 422

    # Another user-facing edit makes the proposal stale.
    direct = client.patch(f"/facilities/{bid}", json={"expected_version": 1, "name": "Phase4差分対象 更新"})
    assert direct.status_code == 200
    stale = client.post(
        f"/facility-change-proposals/{proposal['facility_change_proposal_id']}/apply",
        json={"expected_version": proposal["version"], "expected_facility_version": 1, "accepted_paths": ["facility.address"]},
    )
    assert stale.status_code == 409

    # Re-review after the facility changed creates/refreshes a proposal with the new version.
    rereview = client.post(
        f"/document-analyses/{analysis['document_analysis_id']}/review",
        json={"expected_version": reviewed["version"], "building_id": bid, "submission_type_code": "fire_manager_appointment"},
    )
    assert rereview.status_code == 200
    proposal2 = client.get(f"/document-analyses/{analysis['document_analysis_id']}/change-proposals").json()[0]
    applied = client.post(
        f"/facility-change-proposals/{proposal2['facility_change_proposal_id']}/apply",
        json={"expected_version": proposal2["version"], "expected_facility_version": 2, "accepted_paths": ["facility.address"]},
    )
    assert applied.status_code == 200 and applied.json()["status"] == "applied"
    detail = client.get(f"/facilities/{bid}/detail").json()
    assert detail["facility"]["address"] == "鹿児島県新住所54321"
    assert detail["facility"]["phone"] == "0997-00-0000"  # not explicitly accepted


def test_phase4_pdf_direct_text_extraction_without_ocr(tmp_path):
    import fitz
    from app.document_intake import extract_document
    from app.models import Document
    from app.settings import settings
    pdf_path = tmp_path / "simple.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Phase4 PDF direct text extraction")
    pdf.save(pdf_path)
    old_root = settings.storage_root
    try:
        settings.storage_root = str(tmp_path)
        doc = Document(storage_path="simple.pdf", original_filename="arbitrary.pdf", sha256="x", mime_type="application/pdf")
        text, method, page_count, evidence = extract_document(doc, False)
    finally:
        settings.storage_root = old_root
    assert method == "pdf_text"
    assert page_count == 1
    assert "Phase4 PDF direct text extraction" in text
    assert evidence["ocr_used"] is False


def test_phase4_docx_and_xlsx_text_extraction(tmp_path):
    from docx import Document as WordDocument
    from openpyxl import Workbook
    from app.document_intake import extract_document
    from app.models import Document
    from app.settings import settings

    docx_path = tmp_path / "sample.docx"
    word = WordDocument(); word.add_paragraph("防火管理者選任届出書"); word.save(docx_path)
    xlsx_path = tmp_path / "sample.xlsx"
    wb = Workbook(); ws = wb.active; ws["A1"] = "消防計画"; ws["B1"] = "Phase4"; wb.save(xlsx_path)
    old_root = settings.storage_root
    try:
        settings.storage_root = str(tmp_path)
        d1 = Document(storage_path="sample.docx", original_filename="x.docx", sha256="x", mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        t1, m1, _, _ = extract_document(d1, False)
        d2 = Document(storage_path="sample.xlsx", original_filename="x.xlsx", sha256="x", mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        t2, m2, _, _ = extract_document(d2, False)
    finally:
        settings.storage_root = old_root
    assert m1 == "docx_text" and "防火管理者選任届出書" in t1
    assert m2 == "excel_cells" and "消防計画" in t2


def test_phase4_prevention_role_has_intake_permissions():
    from app.rbac_seed import seed_rbac
    with SessionLocal() as db:
        roles = seed_rbac(db); db.commit()
        role = roles["prevention_editor"]
        codes = set(db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
            .where(RolePermission.role_id == role.role_id)
        ).all())
        assert {"intake.read","intake.analyze","intake.review","intake.apply"}.issubset(codes)


def test_phase4_migration_and_browser_entrypoint_exist():
    from pathlib import Path
    from app.migrations import split_sql
    root = Path(__file__).resolve().parents[2]
    sql = (root / "db" / "migrations" / "007_phase4_document_intake.sql").read_text(encoding="utf-8")
    parts = split_sql(sql)
    assert len(parts) >= 8
    assert "CREATE TABLE IF NOT EXISTS document_analyses" in sql
    assert "CREATE TABLE IF NOT EXISTS facility_change_proposals" in sql
    ui = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "文書解析して受付" in ui
    assert "smartReceiveSubmission" in ui
    assert ".heic" not in ui


def test_phase4_analysis_rejects_unmanaged_storage_path(tmp_path):
    from app.document_intake import extract_document
    from app.models import Document
    from app.settings import settings
    outside = tmp_path / "outside.txt"
    outside.write_text("消防計画", encoding="utf-8")
    old_root = settings.storage_root
    managed = tmp_path / "managed"
    managed.mkdir()
    try:
        settings.storage_root = str(managed)
        doc = Document(storage_path=str(outside), original_filename="outside.txt", sha256="x", mime_type="text/plain")
        with pytest.raises(ValueError, match="outside managed storage"):
            extract_document(doc, False)
    finally:
        settings.storage_root = old_root

def test_phase5_approved_rules_only_drive_candidate_evaluation():
    login()
    facility=client.post("/facilities",json={
        "name":"Phase5対象",
        "detail":{"classification_code":"X-TEST","total_floor_area":500,"above_ground_floors":2}
    })
    assert facility.status_code==201
    bid=facility.json()["building_id"]

    rule=client.post("/legal-rules",json={
        "rule_code":"TEST-RULE-001",
        "name":"テスト用設備候補ルール",
        "domain":"equipment_requirement",
        "description":"自動テスト専用。実法令ではない。"
    })
    assert rule.status_code==201
    rid=rule.json()["rule_id"]

    draft=client.post(f"/legal-rules/{rid}/versions",json={
        "version_no":1,
        "effective_from":"2026-01-01",
        "conditions":{"all":[{"field":"total_floor_area","op":"gte","value":300}]},
        "outcome":{"requirement_code":"TEST-EQ","requirement_name":"テスト設備","decision":"candidate_required"}
    })
    assert draft.status_code==201
    vid=draft.json()["legal_rule_version_id"]

    # Draft rules never participate in evaluation.
    pre=client.post(f"/legal-rules/evaluate/{bid}",json={"domain":"equipment_requirement","evaluation_date":"2026-10-05"})
    assert pre.status_code==201
    assert pre.json()["results"]==[]

    # A verified source is mandatory before approval.
    blocked=client.post(f"/legal-rules/versions/{vid}/approve",json={"expected_version":1})
    assert blocked.status_code==409

    # Create a new sourced version rather than mutating the draft.
    sourced=client.post(f"/legal-rules/{rid}/versions",json={
        "version_no":2,
        "effective_from":"2026-01-01",
        "conditions":{"all":[{"field":"total_floor_area","op":"gte","value":300}]},
        "outcome":{"requirement_code":"TEST-EQ","requirement_name":"テスト設備","decision":"candidate_required"},
        "source_reference":"TEST SOURCE ONLY - NOT A REAL LEGAL CITATION"
    })
    assert sourced.status_code==201
    approved=client.post(
        f"/legal-rules/versions/{sourced.json()['legal_rule_version_id']}/approve",
        json={"expected_version":1},
    )
    assert approved.status_code==200
    assert approved.json()["status"]=="approved"

    evaluated=client.post(f"/legal-rules/evaluate/{bid}",json={"domain":"equipment_requirement","evaluation_date":"2026-10-05"})
    assert evaluated.status_code==201
    body=evaluated.json()
    assert body["status"]=="candidate"
    assert len(body["results"])==1
    assert body["results"][0]["rule_code"]=="TEST-RULE-001"
    assert body["results"][0]["decision_status"]=="candidate"
    assert body["facility_version"]==1


def test_phase5_rejects_unsupported_rule_field():
    login()
    rule=client.post("/legal-rules",json={
        "rule_code":"TEST-RULE-BAD-FIELD",
        "name":"不正フィールド検証",
        "domain":"submission_requirement"
    })
    rid=rule.json()["rule_id"]
    bad=client.post(f"/legal-rules/{rid}/versions",json={
        "version_no":1,
        "effective_from":"2026-01-01",
        "conditions":{"all":[{"field":"secret_unknown_field","op":"eq","value":"x"}]},
        "outcome":{"requirement_code":"X"}
    })
    assert bad.status_code==422


def test_phase5_1_legal_profile_and_source_registry():
    login()
    national=client.post("/legal-sources/jurisdictions",json={
        "code":"JP",
        "name":"日本国",
        "jurisdiction_type":"national",
        "official_base_url":"https://laws.e-gov.go.jp/"
    })
    assert national.status_code==201
    local=client.post("/legal-sources/jurisdictions",json={
        "code":"TEST-FD",
        "name":"テスト消防本部",
        "jurisdiction_type":"fire_department",
        "official_base_url":"https://example.invalid/"
    })
    assert local.status_code==201

    profile=client.post("/legal-sources/profiles",json={
        "code":"TEST-PROFILE",
        "name":"テスト消防本部法令プロファイル",
        "fire_department_name":"テスト消防本部"
    })
    assert profile.status_code==201
    pid=profile.json()["legal_profile_id"]

    for jid,prio in [(national.json()["jurisdiction_id"],10),(local.json()["jurisdiction_id"],20)]:
        r=client.post(f"/legal-sources/profiles/{pid}/jurisdictions",json={
            "jurisdiction_id":jid,
            "priority":prio
        })
        assert r.status_code==204

    source=client.post("/legal-sources/sources",json={
        "legal_profile_id":pid,
        "jurisdiction_id":national.json()["jurisdiction_id"],
        "source_code":"egov-v2",
        "name":"e-Gov 法令API Version2",
        "source_type":"national_law_api",
        "adapter_type":"egov_v2",
        "base_url":"https://laws.e-gov.go.jp/api/2",
        "update_mode":"online",
        "content_scope":"all",
        "sync_frequency":"daily",
        "trust_level":"official",
        "parser_config":{"mode":"watchlist"}
    })
    assert source.status_code==201
    assert source.json()["adapter_type"]=="egov_v2"
    assert source.json()["content_scope"]=="all"

    listed=client.get("/legal-sources/sources",params={"profile_id":pid})
    assert listed.status_code==200
    assert len(listed.json())==1


def test_phase5_1_rejects_source_for_unknown_jurisdiction():
    login()
    profile=client.post("/legal-sources/profiles",json={
        "code":"TEST-PROFILE-UNKNOWN",
        "name":"テスト"
    }).json()
    r=client.post("/legal-sources/sources",json={
        "legal_profile_id":profile["legal_profile_id"],
        "jurisdiction_id":"00000000-0000-0000-0000-000000000000",
        "source_code":"bad",
        "name":"bad",
        "source_type":"test",
        "adapter_type":"manual",
        "base_url":"https://example.invalid/"
    })
    assert r.status_code==422


def test_phase5_2_egov_structure_parser():
    from app.legal_structure import parse_egov_xml
    xml=b"""<?xml version="1.0" encoding="UTF-8"?>
    <Law>
      <LawBody>
        <MainProvision>
          <Article Num="23">
            <ArticleCaption>（テスト条文）</ArticleCaption>
            <ArticleTitle>第二十三条</ArticleTitle>
            <Paragraph Num="1">
              <ParagraphNum>１</ParagraphNum>
              <ParagraphSentence><Sentence>対象物は必要な措置を講ずる。</Sentence></ParagraphSentence>
              <Item Num="1">
                <ItemTitle>一</ItemTitle>
                <ItemSentence><Sentence>第一の条件</Sentence></ItemSentence>
              </Item>
            </Paragraph>
          </Article>
          <AppdxTable Num="1">
            <AppdxTableTitle>別表第一</AppdxTableTitle>
            <TableStruct><Table><TableRow><TableColumn>表内容</TableColumn></TableRow></Table></TableStruct>
          </AppdxTable>
        </MainProvision>
      </LawBody>
    </Law>"""
    rows=parse_egov_xml(xml)
    assert any(x.provision_type=="article" and x.display_label=="第二十三条" for x in rows)
    article=next(x for x in rows if x.provision_type=="article")
    paragraph=next(x for x in rows if x.provision_type=="paragraph")
    item=next(x for x in rows if x.provision_type=="item")
    appendix=next(x for x in rows if x.provision_type=="appendix_table")
    assert paragraph.parent_key==article.provision_key
    assert item.parent_key==paragraph.provision_key
    assert "対象物は必要な措置を講ずる" in paragraph.body_text
    assert appendix.display_label=="別表第一"


def test_phase5_2_local_regulation_structure_parser():
    from app.legal_structure import parse_regulation_html
    html="""<html><body>
    <div id="a1">第一条　目的を定める。</div>
    <div>２　第二項の本文。</div>
    <div>一　第一号の本文。</div>
    <div id="a2">第二条　別の条文。</div>
    <div>附則</div>
    <div>様式第1号</div>
    </body></html>""".encode("utf-8")
    rows=parse_regulation_html(html,"text/html; charset=utf-8")
    assert any(x.provision_type=="article" and x.display_label.startswith("第一条") for x in rows)
    assert any(x.provision_type=="paragraph" and "第二項" in x.body_text for x in rows)
    assert any(x.provision_type=="item" and "第一号" in x.body_text for x in rows)
    assert any(x.provision_type=="supplementary" for x in rows)
    assert any(x.provision_type=="form" for x in rows)


def test_phase5_2_structured_rule_requires_exact_citation_before_approval():
    from app.models import (
        LegalJurisdiction, LegalSource, LegalSourceDocument,
        LegalSourceDocumentVersion, LegalProvision
    )
    login()
    with SessionLocal() as db:
        j=LegalJurisdiction(code="TEST-JUR-52",name="Test",jurisdiction_type="national")
        db.add(j); db.flush()
        s=LegalSource(
            jurisdiction_id=j.jurisdiction_id,
            source_code="test-source-52",
            name="Test source",
            source_type="test",
            adapter_type="manual",
            base_url="https://example.invalid/",
        )
        db.add(s); db.flush()
        d=LegalSourceDocument(
            legal_source_id=s.legal_source_id,
            external_id="LAW-52",
            document_type="law",
            title="テスト法令",
        )
        db.add(d); db.flush()
        v=LegalSourceDocumentVersion(
            legal_source_document_id=d.legal_source_document_id,
            normalized_text="第二十三条 テスト",
            structured_content={},
            sha256="a"*64,
            structure_status="structured",
            provision_count=1,
        )
        db.add(v); db.flush()
        p=LegalProvision(
            legal_source_document_version_id=v.legal_source_document_version_id,
            provision_type="article",
            provision_key="article:23",
            sequence_no=1,
            display_label="第二十三条",
            body_text="テスト条文",
            content_sha256="b"*64,
        )
        db.add(p); db.commit()
        source_version_id=v.legal_source_document_version_id
        provision_id=p.legal_provision_id

    rule=client.post("/legal-rules",json={
        "rule_code":"TEST-RULE-STRUCTURED-52",
        "name":"構造化根拠テスト",
        "domain":"equipment_requirement"
    })
    assert rule.status_code==201
    rid=rule.json()["rule_id"]
    rv=client.post(f"/legal-rules/{rid}/versions",json={
        "version_no":1,
        "effective_from":"2026-01-01",
        "conditions":{"all":[{"field":"status","op":"eq","value":"active"}]},
        "outcome":{"requirement_code":"TEST"},
        "source_legal_document_version_id":source_version_id
    })
    assert rv.status_code==201
    rvid=rv.json()["legal_rule_version_id"]

    blocked=client.post(f"/legal-rules/versions/{rvid}/approve",json={"expected_version":1})
    assert blocked.status_code==409

    citation=client.post(f"/legal-rules/versions/{rvid}/citations",json={
        "legal_provision_id":provision_id,
        "citation_role":"primary"
    })
    assert citation.status_code==201
    assert citation.json()["provision"]["display_label"]=="第二十三条"

    approved=client.post(f"/legal-rules/versions/{rvid}/approve",json={"expected_version":1})
    assert approved.status_code==200
    assert approved.json()["status"]=="approved"

    citations=client.get(f"/legal-rules/versions/{rvid}/citations")
    assert citations.status_code==200 and len(citations.json())==1
