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
        for code in ["facility.read","facility.create","facility.update","facility.restore","document.create","document.read", "inspection.read","inspection.create","inspection.update", "submission.read","submission.create","submission.update","submission.manage", "intake.read","intake.analyze","intake.review","intake.apply", "extension.read","extension.create","extension.review","extension.apply","template.read","template.manage","contract.read","contract.create","contract.update","contract.approve","legal_rule.read","legal_rule.manage","legal_rule.approve","legal_rule.evaluate","legal_source.read","legal_source.manage","legal_source.sync","equipment.read","equipment.manage","drawing.read","drawing.analyze","drawing.review","fire_investigation.read","fire_investigation.create","fire_investigation.update","fire_investigation.review","fire_investigation.approve","search.use"]:
            p=Permission(code=code,description=code); db.add(p); db.flush(); db.add(RolePermission(role_id=r.role_id,permission_id=p.permission_id))
        db.commit()

seed()
from app.module_seed import seed_modules
from app.submission_seed import seed_submission_types
from app.equipment_seed import seed_equipment_types
with SessionLocal() as db:
    seed_modules(db); seed_submission_types(db); seed_equipment_types(db); db.commit()
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
        seed_equipment_types(db)
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
    xml="""<?xml version="1.0" encoding="UTF-8"?>
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
    </Law>""".encode("utf-8")
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
        source_document_id=d.legal_source_document_id
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

    docs=client.get("/legal-sources/documents",params={"q":"テスト法令"})
    assert docs.status_code==200
    assert any(x["legal_source_document_id"]==source_document_id for x in docs.json())

    versions=client.get(f"/legal-sources/documents/{source_document_id}/versions")
    assert versions.status_code==200
    assert versions.json()[0]["legal_source_document_version_id"]==source_version_id

    provisions=client.get(
        f"/legal-rules/source-versions/{source_version_id}/provisions",
        params={"q":"第二十三条"},
    )
    assert provisions.status_code==200
    assert len(provisions.json())==1
    assert provisions.json()[0]["legal_provision_id"]==provision_id


def test_phase5_2_articleless_notice_fallback():
    from app.legal_structure import parse_regulation_html
    html="""<html><body>
    <h1>指定金融機関の指定について</h1>
    <div>平成元年4月1日</div>
    <div>地方自治法施行令第168条第2項の規定によって，次の金融機関を指定金融機関に指定する。</div>
    <div>株式会社 鹿児島銀行</div>
    </body></html>""".encode("utf-8")
    rows=parse_regulation_html(html,"text/html; charset=utf-8")
    assert len(rows)==1
    assert rows[0].provision_type=="document_body"
    assert "指定金融機関" in rows[0].body_text


def test_phase5_3_rule_draft_requires_review_and_promotes_only_to_draft_rule():
    from app.models import (
        LegalJurisdiction, LegalSource, LegalSourceDocument,
        LegalSourceDocumentVersion, LegalProvision, LegalRuleVersion
    )
    login()
    with SessionLocal() as db:
        j=LegalJurisdiction(code="TEST-JUR-53",name="Test 5.3",jurisdiction_type="national")
        db.add(j); db.flush()
        s=LegalSource(
            jurisdiction_id=j.jurisdiction_id,
            source_code="test-source-53",
            name="Test source 5.3",
            source_type="test",
            adapter_type="manual",
            base_url="https://example.invalid/",
        )
        db.add(s); db.flush()
        d=LegalSourceDocument(
            legal_source_id=s.legal_source_id,
            external_id="LAW-53",
            document_type="law",
            title="テスト法令5.3",
        )
        db.add(d); db.flush()
        v=LegalSourceDocumentVersion(
            legal_source_document_id=d.legal_source_document_id,
            normalized_text="第十七条 テスト",
            structured_content={},
            sha256="c"*64,
            structure_status="structured",
            provision_count=1,
        )
        db.add(v); db.flush()
        p=LegalProvision(
            legal_source_document_version_id=v.legal_source_document_version_id,
            provision_type="article",
            provision_key="article:17",
            sequence_no=1,
            display_label="第十七条",
            body_text="テスト法令の正式原文",
            content_sha256="d"*64,
        )
        db.add(p); db.commit()
        source_version_id=v.legal_source_document_version_id
        provision_id=p.legal_provision_id

    created=client.post("/legal-rule-drafts",json={
        "source_legal_document_version_id":source_version_id,
        "domain":"equipment_requirement",
        "proposed_rule_code":"TEST-DRAFT-53",
        "proposed_name":"AI抽出候補",
        "proposed_conditions":{"all":[{"field":"status","op":"eq","value":"active"}]},
        "proposed_outcome":{"requirement_code":"TEST-EQ-53","decision":"candidate_required"},
        "extraction_method":"ai",
        "model_version":"test-model",
        "confidence":0.8,
        "rationale":"テスト用候補",
        "citations":[{"legal_provision_id":provision_id,"citation_role":"primary"}]
    })
    assert created.status_code==201
    draft=created.json()
    did=draft["legal_rule_draft_candidate_id"]
    assert draft["status"]=="pending"

    blocked=client.post(f"/legal-rule-drafts/{did}/promote",json={
        "expected_version":1,
        "effective_from":"2026-01-01"
    })
    assert blocked.status_code==409

    reviewed=client.post(f"/legal-rule-drafts/{did}/review",json={
        "expected_version":1,
        "status":"reviewed"
    })
    assert reviewed.status_code==200
    assert reviewed.json()["status"]=="reviewed"
    assert reviewed.json()["version"]==2

    promoted=client.post(f"/legal-rule-drafts/{did}/promote",json={
        "expected_version":2,
        "effective_from":"2026-01-01"
    })
    assert promoted.status_code==200
    body=promoted.json()
    assert body["status"]=="promoted"
    assert body["promoted_rule_version_id"]

    with SessionLocal() as db:
        rv=db.get(LegalRuleVersion,body["promoted_rule_version_id"])
        assert rv is not None
        assert rv.status=="draft"
        assert rv.source_legal_document_version_id==source_version_id


def test_phase5_4_relevance_scanner_is_review_priority_only():
    from app.legal_relevance import score_fire_service_relevance
    hits=score_fire_service_relevance(
        title="テスト規程",
        label="第十条",
        heading="消防用設備等",
        body="消防用設備等点検結果報告を提出する。",
        provision_type="article",
    )
    categories={x.category for x in hits}
    assert "equipment_requirement" in categories
    assert "submission_requirement" in categories
    assert all(x.score >= 2 for x in hits)


def test_phase5_4_review_queue_human_status_transition():
    from app.models import (
        LegalJurisdiction, LegalSource, LegalSourceDocument,
        LegalSourceDocumentVersion, LegalProvision, LegalProvisionReviewCandidate
    )
    login()
    with SessionLocal() as db:
        j=LegalJurisdiction(code="TEST-JUR-54",name="Test 5.4",jurisdiction_type="fire_union")
        db.add(j); db.flush()
        s=LegalSource(
            jurisdiction_id=j.jurisdiction_id,
            source_code="test-source-54",
            name="Test source 5.4",
            source_type="official_regulation",
            adapter_type="manual",
            base_url="https://example.invalid/",
        )
        db.add(s); db.flush()
        d=LegalSourceDocument(
            legal_source_id=s.legal_source_id,
            external_id="REG-54",
            document_type="regulation",
            title="テスト火災予防規程",
        )
        db.add(d); db.flush()
        v=LegalSourceDocumentVersion(
            legal_source_document_id=d.legal_source_document_id,
            normalized_text="消防用設備等",
            structured_content={},
            sha256="e"*64,
            structure_status="structured",
            provision_count=1,
        )
        db.add(v); db.flush()
        p=LegalProvision(
            legal_source_document_version_id=v.legal_source_document_version_id,
            provision_type="article",
            provision_key="article:54",
            sequence_no=1,
            display_label="第五十四条",
            body_text="消防用設備等に関するテスト",
            content_sha256="f"*64,
        )
        db.add(p); db.flush()
        q=LegalProvisionReviewCandidate(
            legal_provision_id=p.legal_provision_id,
            category="equipment_requirement",
            relevance_score=7.25,
            reasons=[{"scanner_version":"test","match":"消防用設備×1"}],
            extraction_method="deterministic",
            model_version="test",
        )
        db.add(q); db.commit()
        qid=q.legal_provision_review_candidate_id

    listed=client.get("/legal-review-queue",params={"category":"equipment_requirement","min_score":7})
    assert listed.status_code==200
    target=next(x for x in listed.json() if x["legal_provision_review_candidate_id"]==qid)
    assert target["status"]=="pending"
    assert target["document_title"]=="テスト火災予防規程"

    reviewed=client.patch(f"/legal-review-queue/{qid}",json={
        "expected_version":1,
        "status":"reviewed"
    })
    assert reviewed.status_code==200
    assert reviewed.json()["status"]=="reviewed"
    assert reviewed.json()["version"]==2

    stale=client.patch(f"/legal-review-queue/{qid}",json={
        "expected_version":1,
        "status":"ignored"
    })
    assert stale.status_code==409


def test_phase5_3_candidate_signal_detection_is_relevance_only():
    from app.legal_rule_candidate_generation import detect_candidate_signals, candidate_fingerprint
    signals=detect_candidate_signals("消防用設備等点検結果報告を提出すること。","テスト法令")
    domains={x.domain for x in signals}
    assert "equipment_requirement" in domains
    assert "submission_requirement" in domains
    assert all(0 < x.confidence <= 0.75 for x in signals)
    assert detect_candidate_signals("一般的な組織規程","テスト")==[]
    a=candidate_fingerprint(source_version_id="v",provision_id="p",domain="equipment_requirement")
    b=candidate_fingerprint(source_version_id="v",provision_id="p",domain="equipment_requirement")
    assert a==b and len(a)==64


def test_phase5_3_generated_candidate_cannot_review_until_human_completes_rule():
    from app.models import (
        LegalJurisdiction, LegalSource, LegalSourceDocument,
        LegalSourceDocumentVersion, LegalProvision,
        LegalRuleDraftCandidate, LegalRuleDraftCitation,
    )
    login()
    with SessionLocal() as db:
        j=LegalJurisdiction(code="TEST-JUR-53-INCOMPLETE",name="Test 5.3 incomplete",jurisdiction_type="national")
        db.add(j); db.flush()
        s=LegalSource(
            jurisdiction_id=j.jurisdiction_id,
            source_code="test-source-53-incomplete",
            name="Test source 5.3 incomplete",
            source_type="test",
            adapter_type="manual",
            base_url="https://example.invalid/",
        )
        db.add(s); db.flush()
        d=LegalSourceDocument(
            legal_source_id=s.legal_source_id,
            external_id="LAW-53-INCOMPLETE",
            document_type="law",
            title="テスト法令5.3未解釈",
        )
        db.add(d); db.flush()
        v=LegalSourceDocumentVersion(
            legal_source_document_id=d.legal_source_document_id,
            normalized_text="消防用設備等",
            structured_content={},
            sha256="e"*64,
            structure_status="structured",
            provision_count=1,
        )
        db.add(v); db.flush()
        p=LegalProvision(
            legal_source_document_version_id=v.legal_source_document_version_id,
            provision_type="article",
            provision_key="article:99",
            sequence_no=1,
            display_label="第九十九条",
            body_text="消防用設備等について定める。",
            content_sha256="f"*64,
        )
        db.add(p); db.flush()
        draft=LegalRuleDraftCandidate(
            source_legal_document_version_id=v.legal_source_document_version_id,
            domain="equipment_requirement",
            proposed_rule_code=None,
            proposed_name="要レビュー候補",
            proposed_conditions={},
            proposed_outcome={},
            extraction_method="deterministic",
            confidence=0.4,
            rationale="keyword only",
            candidate_fingerprint="1"*64,
            generation_context={"interpretation_status":"required"},
        )
        db.add(draft); db.flush()
        db.add(LegalRuleDraftCitation(
            legal_rule_draft_candidate_id=draft.legal_rule_draft_candidate_id,
            legal_provision_id=p.legal_provision_id,
            citation_role="primary",
        ))
        db.commit()
        did=draft.legal_rule_draft_candidate_id

    blocked=client.post(f"/legal-rule-drafts/{did}/review",json={
        "expected_version":1,
        "status":"reviewed"
    })
    assert blocked.status_code==409

    patched=client.patch(f"/legal-rule-drafts/{did}",json={
        "expected_version":1,
        "proposed_rule_code":"TEST-GENERATED-53",
        "proposed_name":"職員確認済みルール案",
        "proposed_conditions":{"all":[{"field":"status","op":"eq","value":"active"}]},
        "proposed_outcome":{"requirement_code":"TEST-53","decision":"candidate_required"},
        "rationale":"職員が条件と結論を確認・補完"
    })
    assert patched.status_code==200
    assert patched.json()["version"]==2

    reviewed=client.post(f"/legal-rule-drafts/{did}/review",json={
        "expected_version":2,
        "status":"reviewed"
    })
    assert reviewed.status_code==200
    assert reviewed.json()["status"]=="reviewed"


def test_phase5_4_reviewed_provision_handoff_creates_incomplete_rule_draft():
    from app.models import (
        LegalJurisdiction, LegalSource, LegalSourceDocument,
        LegalSourceDocumentVersion, LegalProvision,
        LegalProvisionReviewCandidate, LegalRuleDraftCandidate,
    )
    login()
    with SessionLocal() as db:
        j=LegalJurisdiction(code="TEST-JUR-54-HANDOFF",name="Test 5.4 handoff",jurisdiction_type="fire_union")
        db.add(j); db.flush()
        s=LegalSource(
            jurisdiction_id=j.jurisdiction_id,
            source_code="test-source-54-handoff",
            name="Test source 5.4 handoff",
            source_type="official_regulation",
            adapter_type="manual",
            base_url="https://example.invalid/",
        )
        db.add(s); db.flush()
        d=LegalSourceDocument(
            legal_source_id=s.legal_source_id,
            external_id="REG-54-HANDOFF",
            document_type="regulation",
            title="テスト消防用設備規程",
        )
        db.add(d); db.flush()
        v=LegalSourceDocumentVersion(
            legal_source_document_id=d.legal_source_document_id,
            normalized_text="消防用設備等",
            structured_content={},
            sha256="2"*64,
            structure_status="structured",
            provision_count=1,
        )
        db.add(v); db.flush()
        p=LegalProvision(
            legal_source_document_version_id=v.legal_source_document_version_id,
            provision_type="article",
            provision_key="article:54-handoff",
            sequence_no=1,
            display_label="第五十四条",
            body_text="消防用設備等に関する規定",
            content_sha256="3"*64,
        )
        db.add(p); db.flush()
        q=LegalProvisionReviewCandidate(
            legal_provision_id=p.legal_provision_id,
            category="equipment_requirement",
            relevance_score=7.5,
            reasons=[{"scanner_version":"test","match":"消防用設備×1"}],
            extraction_method="deterministic",
            model_version="test",
        )
        db.add(q); db.commit()
        qid=q.legal_provision_review_candidate_id

    reviewed=client.patch(f"/legal-review-queue/{qid}",json={
        "expected_version":1,
        "status":"reviewed"
    })
    assert reviewed.status_code==200
    assert reviewed.json()["version"]==2

    handed=client.post(f"/legal-review-queue/{qid}/draft",json={
        "expected_version":2,
        "proposed_name":"消防用設備候補のRule草案"
    })
    assert handed.status_code==200
    hb=handed.json()
    assert hb["status"]=="drafted"
    did=hb["legal_rule_draft_candidate_id"]
    assert did

    with SessionLocal() as db:
        draft=db.get(LegalRuleDraftCandidate,did)
        assert draft is not None
        assert draft.proposed_conditions=={}
        assert draft.proposed_outcome=={}
        assert draft.status=="pending"

    blocked=client.post(f"/legal-rule-drafts/{did}/review",json={
        "expected_version":1,
        "status":"reviewed"
    })
    assert blocked.status_code==409

    patched=client.patch(f"/legal-rule-drafts/{did}",json={
        "expected_version":1,
        "proposed_rule_code":"TEST-HANDOFF-54",
        "proposed_conditions":{"all":[{"field":"status","op":"eq","value":"active"}]},
        "proposed_outcome":{"requirement_code":"TEST-HANDOFF-EQ","decision":"candidate_required"},
        "rationale":"Human-completed test interpretation"
    })
    assert patched.status_code==200

    draft_reviewed=client.post(f"/legal-rule-drafts/{did}/review",json={
        "expected_version":2,
        "status":"reviewed"
    })
    assert draft_reviewed.status_code==200
    assert draft_reviewed.json()["status"]=="reviewed"


def test_phase5_4_source_priority_lanes():
    from app.legal_priority import classify_source_priority
    national=classify_source_priority("消防法")
    assert national.lane=="national_core"
    assert national.score>=20

    local=classify_source_priority("大島地区消防組合火災予防条例施行規則")
    assert local.lane=="local_core"
    assert local.score>=15

    normal=classify_source_priority("大島地区消防組合職員旅費規則")
    assert normal.lane=="normal"
    assert normal.score==0


def test_phase5_4_browser_legal_review_entrypoint_exists():
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    ui=(root/"frontend"/"index.html").read_text(encoding="utf-8")
    assert "法令レビュー" in ui
    assert "openLegalReview" in ui
    assert "/legal-review-queue" in ui
    assert "national_core" in ui
    assert "local_core" in ui


def test_phase5_4_relevance_scanner_rejects_generic_reporting_noise():
    from app.legal_relevance import score_fire_service_relevance, SCANNER_VERSION
    assert SCANNER_VERSION=="fire-legal-relevance-v2"
    noise=score_fire_service_relevance(
        title="地方税法",
        label="第百条",
        heading="報告",
        body="申告書を提出し、その結果を報告しなければならない。",
        provision_type="article",
    )
    assert noise==[]

    fire=score_fire_service_relevance(
        title="消防法施行規則",
        label="第三条",
        heading="消防計画",
        body="防火管理者は消防計画を作成し、届出書により届け出なければならない。",
        provision_type="article",
    )
    categories={x.category for x in fire}
    assert "submission_requirement" in categories
    assert "fire_management" in categories


def test_phase5_4_supplementary_provisions_are_retained_but_deprioritized():
    from app.legal_priority import classify_provision_context
    main=classify_provision_context("chapter:1/article:17/paragraph:1","paragraph")
    assert main.context=="main"
    assert main.score==0

    supplementary=classify_provision_context(
        "supplementary:true/article:2/paragraph:1","paragraph"
    )
    assert supplementary.context=="supplementary_transition"
    assert supplementary.score < 0

    notice=classify_provision_context("document_body:1","document_body")
    assert notice.context=="document_body"
    assert notice.score < 0


def test_phase5_5_hash_bound_worklist_import_is_idempotent():
    from sqlalchemy import func
    from app.legal_authoring_import import import_worklist
    from app.models import (
        LegalJurisdiction, LegalSource, LegalSourceDocument,
        LegalSourceDocumentVersion, LegalProvision,
        LegalProvisionReviewCandidate,
    )

    with SessionLocal() as db:
        j=LegalJurisdiction(code="TEST-JUR-55-IMPORT",name="Test 5.5 import",jurisdiction_type="national")
        db.add(j); db.flush()
        s=LegalSource(
            jurisdiction_id=j.jurisdiction_id,
            source_code="test-source-55-import",
            name="Test source 5.5 import",
            source_type="test",
            adapter_type="manual",
            base_url="https://example.invalid/",
        )
        db.add(s); db.flush()
        d=LegalSourceDocument(
            legal_source_id=s.legal_source_id,
            external_id="LAW55IMPORT",
            document_type="law",
            title="テスト法令5.5",
        )
        db.add(d); db.flush()
        v=LegalSourceDocumentVersion(
            legal_source_document_id=d.legal_source_document_id,
            normalized_text="消防用設備等",
            structured_content={},
            sha256="4"*64,
            structure_status="structured",
            provision_count=1,
        )
        db.add(v); db.flush()
        p=LegalProvision(
            legal_source_document_version_id=v.legal_source_document_version_id,
            provision_type="article",
            provision_key="article:55",
            sequence_no=1,
            display_label="第五十五条",
            body_text="消防用設備等に関するテスト",
            content_sha256="5"*64,
        )
        db.add(p); db.commit()
        pid=p.legal_provision_id

    item={
        "scope":"national",
        "document_title":"テスト法令5.5",
        "source_ref":"LAW55IMPORT_20261005/LAW55IMPORT_20261005.xml",
        "priority_lane":"national_core",
        "source_priority_score":20.0,
        "provision_context":"main",
        "context_priority_score":0.0,
        "provision_key":"article:55",
        "provision_content_sha256":"5"*64,
        "hits":[{
            "category":"equipment_requirement",
            "score":8.25,
            "reasons":["消防用設備×1"],
        }],
    }

    with SessionLocal() as db:
        dry=import_worklist(db,[item],allowed_categories={"equipment_requirement"},apply=False)
        assert dry.inserted==1
        assert db.scalar(select(func.count()).select_from(LegalProvisionReviewCandidate).where(
            LegalProvisionReviewCandidate.legal_provision_id==pid
        ))==0

    with SessionLocal() as db:
        applied=import_worklist(db,[item],allowed_categories={"equipment_requirement"},apply=True)
        db.commit()
        assert applied.inserted==1
        row=db.scalar(select(LegalProvisionReviewCandidate).where(
            LegalProvisionReviewCandidate.legal_provision_id==pid,
            LegalProvisionReviewCandidate.category=="equipment_requirement",
        ))
        assert row is not None
        assert row.priority_lane=="national_core"
        assert row.relevance_score==8.25

    with SessionLocal() as db:
        again=import_worklist(db,[item],allowed_categories={"equipment_requirement"},apply=True)
        db.commit()
        assert again.unchanged==1
        assert again.inserted==0

    stale=dict(item)
    stale["provision_content_sha256"]="6"*64
    with SessionLocal() as db:
        rejected=import_worklist(db,[stale],allowed_categories={"equipment_requirement"},apply=True)
        db.commit()
        assert rejected.stale_hash==1
        assert rejected.updated_pending==0


def test_phase5_5_review_queue_summary_search_and_priority_filter():
    from app.models import (
        LegalJurisdiction, LegalSource, LegalSourceDocument,
        LegalSourceDocumentVersion, LegalProvision,
        LegalProvisionReviewCandidate,
    )
    login()
    with SessionLocal() as db:
        j=LegalJurisdiction(code="TEST-JUR-55-SUMMARY",name="Test 5.5 summary",jurisdiction_type="national")
        db.add(j); db.flush()
        s=LegalSource(
            jurisdiction_id=j.jurisdiction_id,
            source_code="test-source-55-summary",
            name="Test source 5.5 summary",
            source_type="test",
            adapter_type="manual",
            base_url="https://example.invalid/",
        )
        db.add(s); db.flush()
        d=LegalSourceDocument(
            legal_source_id=s.legal_source_id,
            external_id="LAW55SUMMARY",
            document_type="law",
            title="テスト集計55法令",
        )
        db.add(d); db.flush()
        v=LegalSourceDocumentVersion(
            legal_source_document_id=d.legal_source_document_id,
            normalized_text="テスト",
            structured_content={},
            sha256="7"*64,
            structure_status="structured",
            provision_count=2,
        )
        db.add(v); db.flush()
        p1=LegalProvision(
            legal_source_document_version_id=v.legal_source_document_version_id,
            provision_type="article",
            provision_key="article:55-summary-1",
            sequence_no=1,
            display_label="第五十五条",
            body_text="消防用設備等",
            content_sha256="8"*64,
        )
        p2=LegalProvision(
            legal_source_document_version_id=v.legal_source_document_version_id,
            provision_type="paragraph",
            provision_key="article:55-summary-2/paragraph:1",
            sequence_no=2,
            display_label="1",
            body_text="届出を提出する",
            content_sha256="9"*64,
        )
        db.add_all([p1,p2]); db.flush()
        q1=LegalProvisionReviewCandidate(
            legal_provision_id=p1.legal_provision_id,
            category="equipment_requirement",
            relevance_score=8.0,
            priority_lane="national_core",
            source_priority_score=20.0,
            provision_context="main",
            context_priority_score=0,
            reasons=[],
            extraction_method="deterministic",
            model_version="test",
            status="pending",
        )
        q2=LegalProvisionReviewCandidate(
            legal_provision_id=p2.legal_provision_id,
            category="submission_requirement",
            relevance_score=6.0,
            priority_lane="national_core",
            source_priority_score=20.0,
            provision_context="main",
            context_priority_score=0,
            reasons=[],
            extraction_method="deterministic",
            model_version="test",
            status="reviewed",
        )
        db.add_all([q1,q2]); db.commit()

    summary=client.get("/legal-review-queue/summary",params={"q":"テスト集計55"})
    assert summary.status_code==200
    body=summary.json()
    assert body["total"]==2
    assert body["by_status"]["pending"]==1
    assert body["by_status"]["reviewed"]==1
    assert body["by_category"]["equipment_requirement"]==1
    assert body["by_category"]["submission_requirement"]==1

    pending=client.get("/legal-review-queue",params={
        "q":"テスト集計55",
        "queue_status":"pending",
        "min_review_priority":25,
        "limit":50,
        "offset":0,
    })
    assert pending.status_code==200
    assert len(pending.json())==1
    assert pending.json()[0]["category"]=="equipment_requirement"

    too_high=client.get("/legal-review-queue",params={
        "q":"テスト集計55",
        "queue_status":"",
        "min_review_priority":29,
    })
    assert too_high.status_code==200
    assert too_high.json()==[]


def test_phase5_6_rule_coverage_endpoint_is_counts_not_percentage():
    login()
    r=client.get("/legal-rules/coverage")
    assert r.status_code==200
    body=r.json()
    assert "equipment_requirement" in body["review_queue_by_domain_status"]
    assert "submission_requirement" in body["review_queue_by_domain_status"]
    assert "equipment_requirement" in body["draft_candidates_by_domain_status"]
    assert "submission_requirement" in body["rule_versions_by_domain_status"]
    assert isinstance(body["approved_rule_count_by_domain"]["equipment_requirement"], int)
    assert isinstance(body["exact_citation_count"], int)
    assert "not a percentage" in body["note"]


def test_phase5_7_submission_compliance_uses_only_explicit_approved_presence_rules():
    login()

    type_code="test_presence_submission_57"
    created_type=client.post("/submission-types",json={
        "code":type_code,
        "name":"テストPresence届出57",
        "category":"test",
        "requires_document":False,
        "rules":{"dashboard":False}
    })
    assert created_type.status_code==201

    periodic_code="test_periodic_submission_57"
    created_periodic=client.post("/submission-types",json={
        "code":periodic_code,
        "name":"テスト周期届出57",
        "category":"test",
        "requires_document":False,
        "rules":{"dashboard":False}
    })
    assert created_periodic.status_code==201

    facility=client.post("/facilities",json={
        "name":"Phase5.7対象",
        "detail":{"classification_code":"SUB-57"}
    })
    assert facility.status_code==201
    bid=facility.json()["building_id"]

    rule=client.post("/legal-rules",json={
        "rule_code":"TEST-SUB-PRESENCE-57",
        "name":"Presence届出Rule57",
        "domain":"submission_requirement"
    })
    assert rule.status_code==201
    rid=rule.json()["rule_id"]
    rv=client.post(f"/legal-rules/{rid}/versions",json={
        "version_no":1,
        "effective_from":"2026-01-01",
        "conditions":{"all":[{"field":"classification_code","op":"eq","value":"SUB-57"}]},
        "outcome":{
            "decision":"required",
            "submission_type_code":type_code,
            "comparison_mode":"presence"
        },
        "source_reference":"TEST SOURCE 57"
    })
    assert rv.status_code==201
    approved=client.post(
        f"/legal-rules/versions/{rv.json()['legal_rule_version_id']}/approve",
        json={"expected_version":1}
    )
    assert approved.status_code==200

    periodic_rule=client.post("/legal-rules",json={
        "rule_code":"TEST-SUB-PERIODIC-57",
        "name":"Periodic届出Rule57",
        "domain":"submission_requirement"
    })
    assert periodic_rule.status_code==201
    prv=client.post(f"/legal-rules/{periodic_rule.json()['rule_id']}/versions",json={
        "version_no":1,
        "effective_from":"2026-01-01",
        "conditions":{"all":[{"field":"classification_code","op":"eq","value":"SUB-57"}]},
        "outcome":{
            "decision":"required",
            "submission_type_code":periodic_code,
            "comparison_mode":"periodic"
        },
        "source_reference":"TEST SOURCE 57 PERIODIC"
    })
    assert prv.status_code==201
    assert client.post(
        f"/legal-rules/versions/{prv.json()['legal_rule_version_id']}/approve",
        json={"expected_version":1}
    ).status_code==200

    first=client.post(f"/facilities/{bid}/submission-compliance/evaluate")
    assert first.status_code==200
    body=first.json()
    presence=next(x for x in body["items"] if x["submission_type_code"]==type_code)
    periodic=next(x for x in body["items"] if x["submission_type_code"]==periodic_code)
    assert presence["state"]=="missing_record_candidate"
    assert periodic["state"]=="manual_review_required"
    assert body["gap_candidate_count"]>=1
    assert body["manual_review_count"]>=1
    assert "not a formal violation" in body["note"]

    received=client.post("/submissions",json={
        "building_id":bid,
        "submission_type_code":type_code,
        "official_number":"5701",
        "submitted_at":"2026-10-05",
        "submitted_by":"テスト提出者",
        "payload_data":{},
        "document_ids":[]
    })
    assert received.status_code==201

    second=client.post(f"/facilities/{bid}/submission-compliance/evaluate")
    assert second.status_code==200
    body2=second.json()
    presence2=next(x for x in body2["items"] if x["submission_type_code"]==type_code)
    assert presence2["state"]=="modern_submission_recorded"
    assert presence2["latest_submission_id"]==received.json()["submission_id"]


def test_phase5_8_equipment_registry_and_rule_comparison_states():
    login()

    et=client.post("/equipment-types",json={
        "code":"test_auto_alarm_58",
        "name":"テスト自動火災報知設備58",
        "category":"alarm",
        "metadata":{"test":True}
    })
    assert et.status_code==201

    facility=client.post("/facilities",json={
        "name":"Phase5.8対象",
        "detail":{"classification_code":"EQ-58"}
    })
    assert facility.status_code==201
    bid=facility.json()["building_id"]

    rule=client.post("/legal-rules",json={
        "rule_code":"TEST-EQ-PRESENCE-58",
        "name":"設備Presence Rule58",
        "domain":"equipment_requirement"
    })
    assert rule.status_code==201
    rid=rule.json()["rule_id"]

    rv=client.post(f"/legal-rules/{rid}/versions",json={
        "version_no":1,
        "effective_from":"2026-01-01",
        "conditions":{"all":[{"field":"classification_code","op":"eq","value":"EQ-58"}]},
        "outcome":{
            "decision":"required",
            "equipment_type_code":"test_auto_alarm_58",
            "comparison_mode":"presence"
        },
        "source_reference":"TEST SOURCE EQ58"
    })
    assert rv.status_code==201
    assert client.post(
        f"/legal-rules/versions/{rv.json()['legal_rule_version_id']}/approve",
        json={"expected_version":1}
    ).status_code==200

    first=client.post(f"/facilities/{bid}/equipment-compliance/evaluate")
    assert first.status_code==200
    body=first.json()
    assert body["gap_candidate_count"]==1
    item=next(x for x in body["items"] if x["equipment_type_code"]=="test_auto_alarm_58")
    assert item["state"]=="missing_equipment_candidate"
    assert "not a formal violation" in body["note"]

    ai=client.post(f"/facilities/{bid}/equipment",json={
        "equipment_type_code":"test_auto_alarm_58",
        "floor_number":1,
        "location_text":"1階",
        "quantity":1,
        "verification_status":"ai_candidate",
        "source_kind":"drawing_ai",
        "notes":"図面AI候補"
    })
    assert ai.status_code==201
    eid=ai.json()["facility_equipment_id"]

    second=client.post(f"/facilities/{bid}/equipment-compliance/evaluate")
    assert second.status_code==200
    item2=next(x for x in second.json()["items"] if x["equipment_type_code"]=="test_auto_alarm_58")
    assert item2["state"]=="unverified_evidence_only"
    assert eid in item2["evidence_equipment_ids"]

    verified=client.patch(f"/facility-equipment/{eid}",json={
        "expected_version":1,
        "verification_status":"verified",
        "source_kind":"manual",
        "last_verified_at":"2026-10-05"
    })
    assert verified.status_code==200
    assert verified.json()["version"]==2
    assert verified.json()["verification_status"]=="verified"

    third=client.post(f"/facilities/{bid}/equipment-compliance/evaluate")
    assert third.status_code==200
    item3=next(x for x in third.json()["items"] if x["equipment_type_code"]=="test_auto_alarm_58")
    assert item3["state"]=="verified_installed"
    assert eid in item3["verified_equipment_ids"]


def test_phase5_8_equipment_update_uses_optimistic_lock():
    login()
    assert client.post("/equipment-types",json={
        "code":"test_extinguisher_58",
        "name":"テスト消火器58"
    }).status_code==201
    facility=client.post("/facilities",json={"name":"設備競合58"}).json()
    created=client.post(f"/facilities/{facility['building_id']}/equipment",json={
        "equipment_type_code":"test_extinguisher_58",
        "quantity":2,
        "verification_status":"verified",
        "source_kind":"manual"
    })
    assert created.status_code==201
    eid=created.json()["facility_equipment_id"]

    p1=client.patch(f"/facility-equipment/{eid}",json={
        "expected_version":1,
        "quantity":3
    })
    assert p1.status_code==200 and p1.json()["version"]==2

    stale=client.patch(f"/facility-equipment/{eid}",json={
        "expected_version":1,
        "quantity":4
    })
    assert stale.status_code==409


def test_phase5_8_prevention_role_has_equipment_permissions():
    from app.rbac_seed import seed_rbac
    with SessionLocal() as db:
        roles=seed_rbac(db); db.commit()
        role=roles["prevention_editor"]
        codes=set(db.scalars(
            select(Permission.code)
            .join(RolePermission,RolePermission.permission_id==Permission.permission_id)
            .where(RolePermission.role_id==role.role_id)
        ).all())
        assert {"equipment.read","equipment.manage"}.issubset(codes)


def test_phase5_9_rule_outcome_rejects_unknown_master_codes():
    login()

    eq_rule=client.post("/legal-rules",json={
        "rule_code":"TEST-EQ-BAD-CODE-59",
        "name":"不明設備コード拒否59",
        "domain":"equipment_requirement"
    })
    assert eq_rule.status_code==201
    bad_eq=client.post(f"/legal-rules/{eq_rule.json()['rule_id']}/versions",json={
        "version_no":1,
        "effective_from":"2026-01-01",
        "conditions":{"all":[{"field":"status","op":"eq","value":"active"}]},
        "outcome":{
            "decision":"required",
            "equipment_type_code":"does_not_exist_59",
            "comparison_mode":"presence"
        },
        "source_reference":"TEST SOURCE 59"
    })
    assert bad_eq.status_code==422

    sub_rule=client.post("/legal-rules",json={
        "rule_code":"TEST-SUB-BAD-CODE-59",
        "name":"不明届出コード拒否59",
        "domain":"submission_requirement"
    })
    assert sub_rule.status_code==201
    bad_sub=client.post(f"/legal-rules/{sub_rule.json()['rule_id']}/versions",json={
        "version_no":1,
        "effective_from":"2026-01-01",
        "conditions":{"all":[{"field":"status","op":"eq","value":"active"}]},
        "outcome":{
            "decision":"required",
            "submission_type_code":"does_not_exist_59",
            "comparison_mode":"presence"
        },
        "source_reference":"TEST SOURCE 59"
    })
    assert bad_sub.status_code==422


def test_phase5_9_seeded_equipment_master_is_extensible_not_legal_completeness_claim():
    login()
    r=client.get("/equipment-types")
    assert r.status_code==200
    rows={x["code"]:x for x in r.json()}
    assert "extinguisher" in rows
    assert "automatic_fire_alarm" in rows
    assert rows["automatic_fire_alarm"]["metadata"]["legal_completeness"] is False
    assert rows["automatic_fire_alarm"]["metadata"]["editable_master"] is True


def test_phase6_drawing_candidate_requires_human_review_before_equipment_promotion():
    login()

    facility=client.post("/facilities",json={
        "name":"Phase6図面対象",
        "detail":{"classification_code":"DRAW-6"}
    })
    assert facility.status_code==201
    bid=facility.json()["building_id"]

    upload=client.post(
        "/documents/upload",
        files={"file":("drawing.pdf",b"test-drawing-bytes","application/pdf")},
        data={"document_type":"drawing"}
    )
    assert upload.status_code==201
    document_id=upload.json()["document_id"]

    analysis=client.post(f"/facilities/{bid}/drawing-analyses",json={
        "document_id":document_id,
        "analysis_method":"ai",
        "model_version":"test-drawing-model-v1",
        "page_count":1,
        "confidence":0.88,
        "summary":{"drawing_type":"floor_plan"},
        "evidence":{"test":True}
    })
    assert analysis.status_code==201
    aid=analysis.json()["drawing_analysis_id"]
    assert analysis.json()["status"]=="pending"

    element=client.post(f"/drawing-analyses/{aid}/elements",json={
        "page_no":1,
        "element_type":"equipment_symbol",
        "label":"自火報",
        "floor_number":1,
        "geometry":{"x":10,"y":20},
        "confidence":0.91,
        "source_kind":"ai"
    })
    assert element.status_code==201
    element_id=element.json()["drawing_element_id"]

    candidate=client.post(f"/drawing-analyses/{aid}/equipment-candidates",json={
        "drawing_element_id":element_id,
        "suggested_equipment_type_code":"automatic_fire_alarm",
        "suggested_label":"自動火災報知設備",
        "floor_number":1,
        "location_text":"1階",
        "quantity":1,
        "confidence":0.91
    })
    assert candidate.status_code==201
    cid=candidate.json()["drawing_equipment_candidate_id"]
    assert candidate.json()["status"]=="pending"

    blocked=client.post(f"/drawing-equipment-candidates/{cid}/promote",json={
        "expected_version":1
    })
    assert blocked.status_code==409

    accepted=client.patch(f"/drawing-equipment-candidates/{cid}",json={
        "expected_version":1,
        "status":"accepted"
    })
    assert accepted.status_code==200
    assert accepted.json()["version"]==2

    promoted=client.post(f"/drawing-equipment-candidates/{cid}/promote",json={
        "expected_version":2,
        "notes":"Human accepted drawing evidence; field verification still required"
    })
    assert promoted.status_code==200
    assert promoted.json()["status"]=="promoted"
    eid=promoted.json()["facility_equipment_id"]
    assert eid

    equipment=client.get(f"/facilities/{bid}/equipment")
    assert equipment.status_code==200
    row=next(x for x in equipment.json() if x["facility_equipment_id"]==eid)
    assert row["verification_status"]=="ai_candidate"
    assert row["source_kind"]=="drawing_ai"
    assert row["source_document_id"]==document_id

    rule=client.post("/legal-rules",json={
        "rule_code":"TEST-DRAWING-EQ-6",
        "name":"図面設備照合Rule6",
        "domain":"equipment_requirement"
    })
    assert rule.status_code==201
    rv=client.post(f"/legal-rules/{rule.json()['rule_id']}/versions",json={
        "version_no":1,
        "effective_from":"2026-01-01",
        "conditions":{"all":[{"field":"classification_code","op":"eq","value":"DRAW-6"}]},
        "outcome":{
            "decision":"required",
            "equipment_type_code":"automatic_fire_alarm",
            "comparison_mode":"presence"
        },
        "source_reference":"TEST DRAWING SOURCE 6"
    })
    assert rv.status_code==201
    assert client.post(
        f"/legal-rules/versions/{rv.json()['legal_rule_version_id']}/approve",
        json={"expected_version":1}
    ).status_code==200

    before_verify=client.post(f"/facilities/{bid}/equipment-compliance/evaluate")
    assert before_verify.status_code==200
    item=next(x for x in before_verify.json()["items"] if x["equipment_type_code"]=="automatic_fire_alarm")
    assert item["state"]=="unverified_evidence_only"
    assert eid in item["evidence_equipment_ids"]

    verified=client.patch(f"/facility-equipment/{eid}",json={
        "expected_version":1,
        "verification_status":"verified",
        "last_verified_at":"2026-10-05"
    })
    assert verified.status_code==200
    assert verified.json()["verification_status"]=="verified"
    assert verified.json()["source_kind"]=="drawing_ai"

    after_verify=client.post(f"/facilities/{bid}/equipment-compliance/evaluate")
    assert after_verify.status_code==200
    item2=next(x for x in after_verify.json()["items"] if x["equipment_type_code"]=="automatic_fire_alarm")
    assert item2["state"]=="verified_installed"
    assert eid in item2["verified_equipment_ids"]


def test_phase6_analysis_review_waits_for_all_candidates():
    login()
    facility=client.post("/facilities",json={"name":"Phase6レビュー対象"}).json()
    upload=client.post(
        "/documents/upload",
        files={"file":("plan.pdf",b"plan-bytes","application/pdf")},
        data={"document_type":"drawing"}
    ).json()
    analysis=client.post(f"/facilities/{facility['building_id']}/drawing-analyses",json={
        "document_id":upload["document_id"],
        "analysis_method":"ai",
        "model_version":"test-model"
    }).json()
    aid=analysis["drawing_analysis_id"]

    fact=client.post(f"/drawing-analyses/{aid}/fact-candidates",json={
        "target_path":"detail.total_floor_area",
        "proposed_value":{"value":1234.5},
        "confidence":0.7,
        "evidence":{"page":1}
    })
    assert fact.status_code==201
    fid=fact.json()["drawing_fact_candidate_id"]

    blocked=client.post(f"/drawing-analyses/{aid}/review",json={"expected_version":1})
    assert blocked.status_code==409

    rejected=client.patch(f"/drawing-fact-candidates/{fid}",json={
        "expected_version":1,
        "status":"rejected"
    })
    assert rejected.status_code==200

    reviewed=client.post(f"/drawing-analyses/{aid}/review",json={"expected_version":1})
    assert reviewed.status_code==200
    assert reviewed.json()["status"]=="reviewed"
    assert reviewed.json()["version"]==2

    locked=client.post(f"/drawing-analyses/{aid}/fact-candidates",json={
        "target_path":"detail.building_area",
        "proposed_value":{"value":500}
    })
    assert locked.status_code==409


def test_phase6_prevention_role_has_drawing_permissions():
    from app.rbac_seed import seed_rbac
    with SessionLocal() as db:
        roles=seed_rbac(db); db.commit()
        role=roles["prevention_editor"]
        codes=set(db.scalars(
            select(Permission.code)
            .join(RolePermission,RolePermission.permission_id==Permission.permission_id)
            .where(RolePermission.role_id==role.role_id)
        ).all())
        assert {"drawing.read","drawing.analyze","drawing.review"}.issubset(codes)


def test_phase6_1_accepted_drawing_fact_applies_with_facility_optimistic_lock():
    login()
    facility=client.post("/facilities",json={
        "name":"Phase6.1 Fact対象",
        "detail":{"classification_code":"OLD","total_floor_area":100}
    }).json()
    bid=facility["building_id"]

    upload=client.post(
        "/documents/upload",
        files={"file":("fact-plan.pdf",b"fact-plan","application/pdf")},
        data={"document_type":"drawing"}
    ).json()
    analysis=client.post(f"/facilities/{bid}/drawing-analyses",json={
        "document_id":upload["document_id"],
        "analysis_method":"ai",
        "model_version":"fact-test-v1"
    }).json()
    aid=analysis["drawing_analysis_id"]

    fact=client.post(f"/drawing-analyses/{aid}/fact-candidates",json={
        "target_path":"detail.total_floor_area",
        "proposed_value":{"value":1234.5},
        "confidence":0.82,
        "evidence":{"page":1,"label":"延べ面積"}
    })
    assert fact.status_code==201
    fid=fact.json()["drawing_fact_candidate_id"]

    pending_apply=client.post(f"/drawing-fact-candidates/{fid}/apply",json={
        "expected_version":1,
        "expected_facility_version":1
    })
    assert pending_apply.status_code==409

    accepted=client.patch(f"/drawing-fact-candidates/{fid}",json={
        "expected_version":1,
        "status":"accepted"
    })
    assert accepted.status_code==200
    assert accepted.json()["version"]==2

    applied=client.post(f"/drawing-fact-candidates/{fid}/apply",json={
        "expected_version":2,
        "expected_facility_version":1
    })
    assert applied.status_code==200
    body=applied.json()
    assert body["version"]==3
    assert body["applied_facility_version"]==2
    assert body["applied_at"]

    detail=client.get(f"/facilities/{bid}/detail")
    assert detail.status_code==200
    assert detail.json()["detail"]["total_floor_area"]==1234.5
    assert detail.json()["facility"]["version"]==2

    duplicate=client.post(f"/drawing-fact-candidates/{fid}/apply",json={
        "expected_version":3,
        "expected_facility_version":2
    })
    assert duplicate.status_code==409


def test_phase6_1_drawing_fact_rejects_stale_facility_and_unapproved_target_path():
    login()
    facility=client.post("/facilities",json={"name":"Phase6.1 stale対象"}).json()
    bid=facility["building_id"]
    upload=client.post(
        "/documents/upload",
        files={"file":("stale-plan.pdf",b"stale-plan","application/pdf")},
        data={"document_type":"drawing"}
    ).json()
    aid=client.post(f"/facilities/{bid}/drawing-analyses",json={
        "document_id":upload["document_id"],
        "analysis_method":"ai"
    }).json()["drawing_analysis_id"]

    good=client.post(f"/drawing-analyses/{aid}/fact-candidates",json={
        "target_path":"detail.above_ground_floors",
        "proposed_value":{"value":3}
    }).json()
    gid=good["drawing_fact_candidate_id"]
    assert client.patch(f"/drawing-fact-candidates/{gid}",json={
        "expected_version":1,"status":"accepted"
    }).status_code==200

    updated=client.patch(f"/facilities/{bid}",json={
        "expected_version":1,
        "name":"別職員が更新済み"
    })
    assert updated.status_code==200
    assert updated.json()["version"]==2

    stale=client.post(f"/drawing-fact-candidates/{gid}/apply",json={
        "expected_version":2,
        "expected_facility_version":1
    })
    assert stale.status_code==409

    bad=client.post(f"/drawing-analyses/{aid}/fact-candidates",json={
        "target_path":"facility.secret_admin_flag",
        "proposed_value":{"value":True}
    }).json()
    bad_id=bad["drawing_fact_candidate_id"]
    assert client.patch(f"/drawing-fact-candidates/{bad_id}",json={
        "expected_version":1,"status":"accepted"
    }).status_code==200
    rejected=client.post(f"/drawing-fact-candidates/{bad_id}/apply",json={
        "expected_version":2,
        "expected_facility_version":2
    })
    assert rejected.status_code==422


def test_phase6_3_drawing_manifest_ingest_is_idempotent_and_version_guarded():
    login()
    facility=client.post("/facilities",json={"name":"Phase6.3 Manifest対象"}).json()
    bid=facility["building_id"]
    upload=client.post(
        "/documents/upload",
        files={"file":("manifest-plan.pdf",b"manifest-plan","application/pdf")},
        data={"document_type":"drawing"}
    ).json()
    analysis=client.post(f"/facilities/{bid}/drawing-analyses",json={
        "document_id":upload["document_id"],
        "analysis_method":"ai"
    })
    assert analysis.status_code==201
    aid=analysis.json()["drawing_analysis_id"]
    assert analysis.json()["status"]=="pending"
    assert analysis.json()["version"]==1

    manifest={
        "expected_version":1,
        "model_version":"local-vision-test-v1",
        "page_count":1,
        "confidence":0.93,
        "summary":{"drawing_type":"floor_plan"},
        "evidence":{"source":"unit-test"},
        "elements":[{
            "client_ref":"symbol-1",
            "page_no":1,
            "element_type":"equipment_symbol",
            "label":"自火報",
            "floor_number":1,
            "geometry":{"x":1,"y":2},
            "extracted_data":{"symbol":"FA"},
            "confidence":0.94
        }],
        "equipment_candidates":[{
            "drawing_element_ref":"symbol-1",
            "suggested_equipment_type_code":"automatic_fire_alarm",
            "suggested_label":"自動火災報知設備",
            "floor_number":1,
            "location_text":"1階",
            "quantity":1,
            "confidence":0.94
        }],
        "fact_candidates":[{
            "drawing_element_ref":"symbol-1",
            "target_path":"detail.total_floor_area",
            "proposed_value":{"value":999.5},
            "confidence":0.75,
            "evidence":{"page":1}
        }]
    }

    first=client.post(f"/drawing-analyses/{aid}/manifest",json=manifest)
    assert first.status_code==200
    body=first.json()
    assert body["analysis"]["status"]=="analyzed"
    assert body["analysis"]["version"]==2
    assert body["analysis"]["model_version"]=="local-vision-test-v1"
    assert len(body["elements"])==1
    assert len(body["equipment_candidates"])==1
    assert len(body["fact_candidates"])==1
    assert body["equipment_candidates"][0]["drawing_element_id"]==body["elements"][0]["drawing_element_id"]
    assert body["fact_candidates"][0]["drawing_element_id"]==body["elements"][0]["drawing_element_id"]

    repeated=client.post(f"/drawing-analyses/{aid}/manifest",json=manifest)
    assert repeated.status_code==200
    body2=repeated.json()
    assert body2["analysis"]["version"]==2
    assert len(body2["elements"])==1
    assert len(body2["equipment_candidates"])==1
    assert len(body2["fact_candidates"])==1

    changed=dict(manifest)
    changed["summary"]={"drawing_type":"changed"}
    stale=client.post(f"/drawing-analyses/{aid}/manifest",json=changed)
    assert stale.status_code==409


def test_phase7_fire_investigation_human_gates_for_ai_evidence_cause_and_report():
    login()

    facility=client.post("/facilities",json={"name":"Phase7火災調査対象"}).json()
    bid=facility["building_id"]

    case=client.post("/fire-investigations",json={
        "case_number":"FIRE-TEST-7-001",
        "building_id":bid,
        "title":"Phase7テスト火災",
        "occurred_at":"2026-10-05T01:00:00+09:00",
        "location_text":"テスト現場"
    })
    assert case.status_code==201
    cb=case.json()
    cid=cb["fire_investigation_case_id"]
    assert cb["status"]=="draft"
    assert cb["official_cause_text"] is None
    assert cb["version"]==1

    photo_doc=client.post(
        "/documents/upload",
        files={"file":("scene.jpg",b"photo-bytes","image/jpeg")},
        data={"document_type":"fire_scene_photo"}
    ).json()
    audio_doc=client.post(
        "/documents/upload",
        files={"file":("interview.m4a",b"audio-bytes","audio/mp4")},
        data={"document_type":"fire_interview_audio"}
    ).json()

    photo=client.post(f"/fire-investigations/{cid}/media",json={
        "document_id":photo_doc["document_id"],
        "media_type":"photo",
        "sequence_no":1,
        "location_label":"居室",
        "floor_number":1
    })
    assert photo.status_code==201
    pmid=photo.json()["fire_investigation_media_id"]

    audio=client.post(f"/fire-investigations/{cid}/media",json={
        "document_id":audio_doc["document_id"],
        "media_type":"audio",
        "sequence_no":2,
        "location_label":"聞き取り"
    })
    assert audio.status_code==201
    amid=audio.json()["fire_investigation_media_id"]

    annotation=client.post(f"/fire-investigations/media/{pmid}/photo-annotations",json={
        "description":"焼損範囲候補",
        "tags":["焼損","壁面"],
        "confidence":0.77,
        "source_kind":"ai",
        "model_version":"vision-test-v1"
    })
    assert annotation.status_code==201
    ann=annotation.json()
    assert ann["status"]=="pending"
    assert ann["version"]==1

    ann_reviewed=client.patch(f"/fire-investigations/photo-annotations/{ann['fire_photo_annotation_id']}",json={
        "expected_version":1,
        "status":"accepted"
    })
    assert ann_reviewed.status_code==200
    assert ann_reviewed.json()["status"]=="accepted"
    assert ann_reviewed.json()["version"]==2

    segment=client.post(f"/fire-investigations/media/{amid}/transcript-segments",json={
        "start_ms":0,
        "end_ms":5000,
        "speaker_label":"関係者A",
        "text":"午前1時頃に煙に気付いた。",
        "confidence":0.92,
        "source_kind":"ai",
        "model_version":"stt-test-v1"
    })
    assert segment.status_code==201
    seg=segment.json()
    assert seg["review_status"]=="pending"
    assert seg["version"]==1

    seg_reviewed=client.patch(f"/fire-investigations/transcript-segments/{seg['fire_transcript_segment_id']}",json={
        "expected_version":1,
        "status":"accepted"
    })
    assert seg_reviewed.status_code==200
    assert seg_reviewed.json()["review_status"]=="accepted"
    assert seg_reviewed.json()["version"]==2

    statement=client.post(f"/fire-investigations/{cid}/statements",json={
        "fire_investigation_media_id":amid,
        "person_label":"関係者A",
        "draft_text":"関係者Aは午前1時頃に煙に気付いた旨を述べた。",
        "evidence_segment_ids":[seg["fire_transcript_segment_id"]],
        "ai_generated":True,
        "model_version":"statement-test-v1"
    })
    assert statement.status_code==201
    st=statement.json()
    assert st["status"]=="draft"
    statement_review=client.patch(f"/fire-investigations/statements/{st['fire_statement_draft_id']}",json={
        "expected_version":1,
        "status":"reviewed",
        "uncertainty_reviewed":True
    })
    assert statement_review.status_code==200
    assert statement_review.json()["status"]=="reviewed"

    timeline=client.post(f"/fire-investigations/{cid}/timeline",json={
        "event_time":"2026-10-05T01:00:00+09:00",
        "event_type":"observation",
        "title":"煙を確認",
        "description":"関係者Aの供述候補",
        "source_refs":[{"type":"transcript_segment","id":seg["fire_transcript_segment_id"]}],
        "confidence":0.8
    })
    assert timeline.status_code==201
    tl=timeline.json()
    assert tl["status"]=="candidate"
    tl_review=client.patch(f"/fire-investigations/timeline/{tl['fire_timeline_event_id']}",json={
        "expected_version":1,
        "status":"confirmed"
    })
    assert tl_review.status_code==200
    assert tl_review.json()["status"]=="confirmed"

    cause=client.post(f"/fire-investigations/{cid}/cause-candidates",json={
        "cause_category":"電気関係",
        "cause_text":"電気配線から出火した可能性",
        "hypothesis":{"kind":"test"},
        "evidence_refs":[{"type":"photo_annotation","id":ann["fire_photo_annotation_id"]}],
        "confidence":0.55,
        "extraction_method":"ai",
        "model_version":"cause-test-v1"
    })
    assert cause.status_code==201
    cc=cause.json()
    assert cc["status"]=="candidate"

    blocked_cause=client.post(f"/fire-investigations/{cid}/official-cause",json={
        "expected_case_version":1,
        "cause_candidate_id":cc["fire_cause_candidate_id"]
    })
    assert blocked_cause.status_code==409

    cause_review=client.patch(f"/fire-investigations/cause-candidates/{cc['fire_cause_candidate_id']}",json={
        "expected_version":1,
        "status":"reviewed"
    })
    assert cause_review.status_code==200
    assert cause_review.json()["status"]=="reviewed"

    approved_cause=client.post(f"/fire-investigations/{cid}/official-cause",json={
        "expected_case_version":1,
        "cause_candidate_id":cc["fire_cause_candidate_id"]
    })
    assert approved_cause.status_code==200
    assert approved_cause.json()["official_cause_candidate_id"]==cc["fire_cause_candidate_id"]
    assert approved_cause.json()["official_cause_text"]=="電気配線から出火した可能性"
    assert approved_cause.json()["version"]==2

    direct_ai_report=client.post(f"/fire-investigations/{cid}/report-drafts",json={
        "report_type":"fire_investigation_report",
        "narrative_text":"AI作成の報告書下書き",
        "structured_content":{"summary":"test"},
        "evidence_refs":[],
        "ai_generated":True,
        "model_version":"report-test-v1"
    })
    assert direct_ai_report.status_code==422

    snapshot=client.post(f"/fire-investigations/{cid}/evidence-snapshots",json={
        "metadata":{"purpose":"unit-test-report"}
    })
    assert snapshot.status_code==201
    snap=snapshot.json()
    assert snap["case_version"]==2
    assert ann["fire_photo_annotation_id"] in snap["photo_annotation_ids"]
    assert seg["fire_transcript_segment_id"] in snap["transcript_segment_ids"]
    assert st["fire_statement_draft_id"] in snap["statement_draft_ids"]
    assert tl["fire_timeline_event_id"] in snap["timeline_event_ids"]
    assert snap["official_cause_candidate_id"]==cc["fire_cause_candidate_id"]

    snapshot2=client.post(f"/fire-investigations/{cid}/evidence-snapshots",json={
        "metadata":{"purpose":"same-evidence-second-call"}
    })
    assert snapshot2.status_code==201
    assert snapshot2.json()["fire_evidence_snapshot_id"]==snap["fire_evidence_snapshot_id"]

    report_manifest={
        "evidence_snapshot_id":snap["fire_evidence_snapshot_id"],
        "report_type":"fire_investigation_report",
        "model_version":"report-test-v2",
        "narrative_text":"Evidence Snapshotを根拠にしたAI報告書下書き",
        "structured_content":{"summary":"test"},
        "payload_metadata":{"source":"unit-test"}
    }
    report=client.post(f"/fire-investigations/{cid}/report-ai-manifest",json=report_manifest)
    assert report.status_code==200
    rb=report.json()
    assert rb["created"] is True
    assert len(rb["derived_ids"])==1
    report_id=rb["derived_ids"][0]

    report_repeat=client.post(f"/fire-investigations/{cid}/report-ai-manifest",json=report_manifest)
    assert report_repeat.status_code==200
    assert report_repeat.json()["created"] is False
    assert report_repeat.json()["derived_ids"]==[report_id]

    detail_before_review=client.get(f"/fire-investigations/{cid}").json()
    rp=next(x for x in detail_before_review["report_drafts"] if x["fire_report_draft_id"]==report_id)
    assert rp["status"]=="draft"
    assert rp["ai_generated"] is True
    assert rp["fire_evidence_snapshot_id"]==snap["fire_evidence_snapshot_id"]
    assert rp["source_manifest_id"]==rb["fire_investigation_ai_manifest_id"]

    blocked_report=client.post(f"/fire-investigations/report-drafts/{report_id}/approve",json={
        "expected_version":1
    })
    assert blocked_report.status_code==409

    reviewed_report=client.patch(f"/fire-investigations/report-drafts/{report_id}",json={
        "expected_version":1,
        "status":"reviewed"
    })
    assert reviewed_report.status_code==200
    assert reviewed_report.json()["status"]=="reviewed"
    assert reviewed_report.json()["version"]==2

    approved_report=client.post(f"/fire-investigations/report-drafts/{report_id}/approve",json={
        "expected_version":2
    })
    assert approved_report.status_code==200
    assert approved_report.json()["status"]=="approved"
    assert approved_report.json()["version"]==3

    detail=client.get(f"/fire-investigations/{cid}")
    assert detail.status_code==200
    db=detail.json()
    assert len(db["media"])==2
    assert len(db["statements"])==1
    assert len(db["timeline"])==1
    assert len(db["cause_candidates"])==1
    assert len(db["report_drafts"])==1


def test_phase7_case_optimistic_lock_and_cross_case_evidence_guard():
    login()

    c1=client.post("/fire-investigations",json={
        "case_number":"FIRE-TEST-7-A",
        "title":"Case A"
    })
    c2=client.post("/fire-investigations",json={
        "case_number":"FIRE-TEST-7-B",
        "title":"Case B"
    })
    assert c1.status_code==201 and c2.status_code==201
    a=c1.json()
    b=c2.json()

    updated=client.patch(f"/fire-investigations/{a['fire_investigation_case_id']}",json={
        "expected_version":1,
        "title":"Case A updated",
        "status":"active"
    })
    assert updated.status_code==200
    assert updated.json()["version"]==2

    stale=client.patch(f"/fire-investigations/{a['fire_investigation_case_id']}",json={
        "expected_version":1,
        "location_text":"stale"
    })
    assert stale.status_code==409

    audio_doc=client.post(
        "/documents/upload",
        files={"file":("case-b.m4a",b"audio-b","audio/mp4")},
        data={"document_type":"fire_interview_audio"}
    ).json()
    media=client.post(f"/fire-investigations/{b['fire_investigation_case_id']}/media",json={
        "document_id":audio_doc["document_id"],
        "media_type":"audio"
    }).json()
    seg=client.post(f"/fire-investigations/media/{media['fire_investigation_media_id']}/transcript-segments",json={
        "text":"Case B evidence",
        "source_kind":"manual"
    }).json()

    cross=client.post(f"/fire-investigations/{a['fire_investigation_case_id']}/statements",json={
        "person_label":"A",
        "draft_text":"cross-case invalid",
        "evidence_segment_ids":[seg["fire_transcript_segment_id"]]
    })
    assert cross.status_code==422


def test_phase7_fire_investigation_roles_separate_review_from_approval():
    from app.rbac_seed import seed_rbac

    with SessionLocal() as db:
        roles=seed_rbac(db)
        db.commit()

        investigator=roles["fire_investigator"]
        investigator_codes=set(db.scalars(
            select(Permission.code)
            .join(RolePermission,RolePermission.permission_id==Permission.permission_id)
            .where(RolePermission.role_id==investigator.role_id)
        ).all())
        assert "fire_investigation.review" in investigator_codes
        assert "fire_investigation.update" in investigator_codes
        assert "fire_investigation.approve" not in investigator_codes

        approver=roles["fire_investigation_approver"]
        approver_codes=set(db.scalars(
            select(Permission.code)
            .join(RolePermission,RolePermission.permission_id==Permission.permission_id)
            .where(RolePermission.role_id==approver.role_id)
        ).all())
        assert "fire_investigation.approve" in approver_codes
        assert "fire_investigation.update" not in approver_codes
        assert "fire_investigation.create" not in approver_codes


def test_phase7_1_ai_manifests_are_idempotent_and_statement_uses_only_accepted_transcript():
    login()
    case=client.post("/fire-investigations",json={
        "case_number":"FIRE-TEST-71",
        "title":"Phase7.1 Manifest"
    }).json()
    cid=case["fire_investigation_case_id"]

    photo_doc=client.post(
        "/documents/upload",
        files={"file":("manifest-photo.jpg",b"manifest-photo","image/jpeg")},
        data={"document_type":"fire_scene_photo"}
    ).json()
    audio_doc=client.post(
        "/documents/upload",
        files={"file":("manifest-audio.m4a",b"manifest-audio","audio/mp4")},
        data={"document_type":"fire_interview_audio"}
    ).json()

    photo=client.post(f"/fire-investigations/{cid}/media",json={
        "document_id":photo_doc["document_id"],
        "media_type":"photo"
    }).json()
    audio=client.post(f"/fire-investigations/{cid}/media",json={
        "document_id":audio_doc["document_id"],
        "media_type":"audio"
    }).json()
    pmid=photo["fire_investigation_media_id"]
    amid=audio["fire_investigation_media_id"]

    photo_manifest={
        "model_version":"photo-ai-test-v1",
        "payload_metadata":{"source":"unit-test"},
        "annotations":[{
            "description":"焼損箇所候補",
            "tags":["焼損"],
            "map_position":{"x":0.4,"y":0.6},
            "confidence":0.81
        }]
    }
    p1=client.post(f"/fire-investigations/media/{pmid}/photo-ai-manifest",json=photo_manifest)
    assert p1.status_code==200
    pb=p1.json()
    assert pb["created"] is True
    assert len(pb["derived_ids"])==1
    p2=client.post(f"/fire-investigations/media/{pmid}/photo-ai-manifest",json=photo_manifest)
    assert p2.status_code==200
    assert p2.json()["created"] is False
    assert p2.json()["fire_investigation_ai_manifest_id"]==pb["fire_investigation_ai_manifest_id"]
    assert p2.json()["derived_ids"]==pb["derived_ids"]

    annotations=client.get(f"/fire-investigations/media/{pmid}/photo-annotations")
    assert annotations.status_code==200
    assert len(annotations.json())==1
    assert annotations.json()[0]["status"]=="pending"

    transcript_manifest={
        "model_version":"stt-test-v2",
        "payload_metadata":{"language":"ja"},
        "segments":[{
            "start_ms":0,
            "end_ms":3500,
            "speaker_label":"関係者B",
            "text":"コンセント付近から煙が見えた。",
            "confidence":0.9
        },{
            "start_ms":3500,
            "end_ms":7000,
            "speaker_label":"関係者B",
            "text":"その後すぐに外へ避難した。",
            "confidence":0.88
        }]
    }
    t1=client.post(f"/fire-investigations/media/{amid}/transcript-ai-manifest",json=transcript_manifest)
    assert t1.status_code==200
    tb=t1.json()
    assert tb["created"] is True
    assert len(tb["derived_ids"])==2
    t2=client.post(f"/fire-investigations/media/{amid}/transcript-ai-manifest",json=transcript_manifest)
    assert t2.status_code==200
    assert t2.json()["created"] is False
    assert t2.json()["derived_ids"]==tb["derived_ids"]

    segments=client.get(f"/fire-investigations/media/{amid}/transcript-segments")
    assert segments.status_code==200
    assert len(segments.json())==2
    assert all(x["review_status"]=="pending" for x in segments.json())
    first_segment=segments.json()[0]

    statement_manifest={
        "model_version":"statement-ai-test-v1",
        "payload_metadata":{"source":"accepted-transcript-only"},
        "statements":[{
            "fire_investigation_media_id":amid,
            "person_label":"関係者B",
            "draft_text":"関係者Bはコンセント付近から煙を認め、直後に避難した旨を述べた。",
            "evidence_segment_ids":[first_segment["fire_transcript_segment_id"]]
        }]
    }
    blocked=client.post(f"/fire-investigations/{cid}/statement-ai-manifest",json=statement_manifest)
    assert blocked.status_code==409

    accepted=client.patch(
        f"/fire-investigations/transcript-segments/{first_segment['fire_transcript_segment_id']}",
        json={"expected_version":1,"status":"accepted"}
    )
    assert accepted.status_code==200

    s1=client.post(f"/fire-investigations/{cid}/statement-ai-manifest",json=statement_manifest)
    assert s1.status_code==200
    sb=s1.json()
    assert sb["created"] is True
    assert len(sb["derived_ids"])==1
    s2=client.post(f"/fire-investigations/{cid}/statement-ai-manifest",json=statement_manifest)
    assert s2.status_code==200
    assert s2.json()["created"] is False
    assert s2.json()["derived_ids"]==sb["derived_ids"]

    detail=client.get(f"/fire-investigations/{cid}")
    assert detail.status_code==200
    statements=detail.json()["statements"]
    assert len(statements)==1
    assert statements[0]["ai_generated"] is True
    assert statements[0]["status"]=="draft"
    assert statements[0]["evidence_segment_ids"]==[first_segment["fire_transcript_segment_id"]]


def test_phase7_1_transcript_manifest_rejects_invalid_segment_range():
    login()
    case=client.post("/fire-investigations",json={"title":"Phase7.1 invalid range"}).json()
    doc=client.post(
        "/documents/upload",
        files={"file":("bad-audio.m4a",b"bad-audio","audio/mp4")},
        data={"document_type":"fire_interview_audio"}
    ).json()
    media=client.post(f"/fire-investigations/{case['fire_investigation_case_id']}/media",json={
        "document_id":doc["document_id"],
        "media_type":"audio"
    }).json()
    r=client.post(
        f"/fire-investigations/media/{media['fire_investigation_media_id']}/transcript-ai-manifest",
        json={
            "model_version":"stt-bad",
            "segments":[{
                "start_ms":5000,
                "end_ms":1000,
                "text":"invalid"
            }]
        }
    )
    assert r.status_code==422


def test_phase7_3_stale_snapshot_and_out_of_snapshot_evidence_are_rejected():
    login()
    case=client.post("/fire-investigations",json={
        "case_number":"FIRE-TEST-73-STALE",
        "title":"Phase7.3 stale snapshot"
    }).json()
    cid=case["fire_investigation_case_id"]

    audio_doc=client.post(
        "/documents/upload",
        files={"file":("snapshot-audio.m4a",b"snapshot-audio","audio/mp4")},
        data={"document_type":"fire_interview_audio"}
    ).json()
    media=client.post(f"/fire-investigations/{cid}/media",json={
        "document_id":audio_doc["document_id"],
        "media_type":"audio"
    }).json()
    seg=client.post(f"/fire-investigations/media/{media['fire_investigation_media_id']}/transcript-segments",json={
        "text":"Snapshot evidence",
        "source_kind":"manual"
    }).json()
    accepted=client.patch(
        f"/fire-investigations/transcript-segments/{seg['fire_transcript_segment_id']}",
        json={"expected_version":1,"status":"accepted"}
    )
    assert accepted.status_code==200

    snap=client.post(f"/fire-investigations/{cid}/evidence-snapshots",json={"metadata":{"test":"stale"}})
    assert snap.status_code==201
    sid=snap.json()["fire_evidence_snapshot_id"]

    invalid_ref=client.post(f"/fire-investigations/{cid}/report-ai-manifest",json={
        "evidence_snapshot_id":sid,
        "report_type":"fire_investigation_report",
        "model_version":"report-test-v3",
        "narrative_text":"invalid ref",
        "evidence_refs":[{"type":"transcript_segment","id":"00000000-0000-0000-0000-000000000000"}]
    })
    assert invalid_ref.status_code==422

    changed=client.patch(f"/fire-investigations/{cid}",json={
        "expected_version":1,
        "title":"Phase7.3 stale snapshot changed"
    })
    assert changed.status_code==200
    assert changed.json()["version"]==2

    stale=client.post(f"/fire-investigations/{cid}/report-ai-manifest",json={
        "evidence_snapshot_id":sid,
        "report_type":"fire_investigation_report",
        "model_version":"report-test-v3",
        "narrative_text":"stale snapshot"
    })
    assert stale.status_code==409
    assert "stale" in stale.text


def test_phase7_4_approved_report_renders_registered_excel_template_without_modifying_original():
    from io import BytesIO
    from pathlib import Path
    from openpyxl import Workbook, load_workbook
    from app.models import Document
    from app.official_form_renderer import sha256_file
    from app.settings import settings

    login()

    wb=Workbook()
    ws=wb.active
    ws.title="様式"
    ws["A1"]="正式様式原本"
    ws["B2"]=""
    ws["B3"]=""
    ws["B4"]=""
    buf=BytesIO()
    wb.save(buf)
    buf.seek(0)

    uploaded=client.post(
        "/documents/upload",
        files={"file":("fire-report-template.xlsx",buf.getvalue(),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"document_type":"form_template"}
    )
    assert uploaded.status_code==201
    template_doc=uploaded.json()

    template=client.post("/templates",json={
        "template_code":"FIRE_REPORT_TEST_74",
        "name":"火災調査報告テスト様式",
        "module_code":"fire_investigation",
        "document_id":template_doc["document_id"],
        "version_label":"2026-test",
        "issuer":"test",
        "effective_from":"2026-01-01",
        "effective_to":None,
        "field_mapping":{
            "case_number":{"sheet":"様式","cell":"B2"},
            "title":{"sheet":"様式","cell":"B3"},
            "narrative_text":{"sheet":"様式","cell":"B4"}
        },
        "print_settings":{},
        "modification_policy":"fill_only"
    })
    assert template.status_code==201
    template_id=template.json()["form_template_id"]

    case=client.post("/fire-investigations",json={
        "case_number":"FIRE-TEST-74",
        "title":"正式様式出力テスト",
        "occurred_at":"2026-10-05T09:00:00+09:00",
        "location_text":"テスト地点"
    })
    assert case.status_code==201
    cb=case.json()
    cid=cb["fire_investigation_case_id"]

    report=client.post(f"/fire-investigations/{cid}/report-drafts",json={
        "report_type":"fire_investigation_report",
        "form_template_id":template_id,
        "narrative_text":"Human確認済み報告本文",
        "structured_content":{"summary":"test"},
        "evidence_refs":[],
        "ai_generated":False
    })
    assert report.status_code==201
    rid=report.json()["fire_report_draft_id"]

    reviewed=client.patch(f"/fire-investigations/report-drafts/{rid}",json={
        "expected_version":1,
        "status":"reviewed"
    })
    assert reviewed.status_code==200
    approved=client.post(f"/fire-investigations/report-drafts/{rid}/approve",json={
        "expected_version":2
    })
    assert approved.status_code==200
    assert approved.json()["status"]=="approved"
    assert approved.json()["version"]==3

    with SessionLocal() as db:
        src=db.get(Document,template_doc["document_id"])
        source_path=(Path(settings.storage_root).resolve()/src.storage_path).resolve()
        original_hash=sha256_file(source_path)
        assert original_hash==src.sha256

    rendered=client.post(f"/fire-investigations/report-drafts/{rid}/render-form",json={
        "expected_report_version":3
    })
    assert rendered.status_code==201
    exp=rendered.json()
    assert exp["status"]=="rendered"
    assert exp["output_document_id"]
    assert exp["template_sha256"]==original_hash
    assert exp["output_format"]=="xlsx"

    rendered_again=client.post(f"/fire-investigations/report-drafts/{rid}/render-form",json={
        "expected_report_version":3
    })
    assert rendered_again.status_code==201
    assert rendered_again.json()["fire_report_export_id"]==exp["fire_report_export_id"]
    assert rendered_again.json()["output_document_id"]==exp["output_document_id"]

    with SessionLocal() as db:
        src=db.get(Document,template_doc["document_id"])
        out=db.get(Document,exp["output_document_id"])
        source_path=(Path(settings.storage_root).resolve()/src.storage_path).resolve()
        output_path=(Path(settings.storage_root).resolve()/out.storage_path).resolve()
        assert sha256_file(source_path)==original_hash
        out_wb=load_workbook(output_path,data_only=False)
        out_ws=out_wb["様式"]
        assert out_ws["A1"].value=="正式様式原本"
        assert out_ws["B2"].value=="FIRE-TEST-74"
        assert out_ws["B3"].value=="正式様式出力テスト"
        assert out_ws["B4"].value=="Human確認済み報告本文"

    downloaded=client.get(f"/documents/{exp['output_document_id']}/download")
    assert downloaded.status_code==200
    assert downloaded.content
    assert downloaded.content[:2]==b"PK"

    verified=client.post(f"/fire-investigations/report-exports/{exp['fire_report_export_id']}/verify",json={
        "expected_case_version":1
    })
    assert verified.status_code==200
    assert verified.json()["status"]=="verified"

    case_after=client.get(f"/fire-investigations/{cid}")
    assert case_after.status_code==200
    assert case_after.json()["case"]["final_report_document_id"]==exp["output_document_id"]
    assert case_after.json()["case"]["version"]==2


def test_phase7_4_docx_renderer_preserves_source_and_rejects_split_placeholder(tmp_path):
    from docx import Document as WordDocument
    from app.official_form_renderer import (
        TemplateRenderError,
        render_template,
        sha256_file,
    )

    source=tmp_path/"template.docx"
    output=tmp_path/"output.docx"
    doc=WordDocument()
    doc.add_paragraph("正式様式原本")
    p=doc.add_paragraph()
    p.add_run("番号: {{case_number}}")
    doc.save(source)

    before=sha256_file(source)
    manifest=render_template(
        source,
        output,
        {"case_number":{"placeholder":"{{case_number}}"}},
        {"case_number":"FIRE-DOCX-74"},
    )
    assert manifest["format"]=="docx"
    assert manifest["applied"][0]["occurrences"]==1
    assert sha256_file(source)==before

    rendered=WordDocument(output)
    assert any("番号: FIRE-DOCX-74" in p.text for p in rendered.paragraphs)
    assert any("正式様式原本" in p.text for p in rendered.paragraphs)

    split_source=tmp_path/"split.docx"
    split_output=tmp_path/"split-out.docx"
    split=WordDocument()
    p=split.add_paragraph()
    p.add_run("{{case_")
    p.add_run("number}}")
    split.save(split_source)

    with pytest.raises(TemplateRenderError,match="spans multiple runs"):
        render_template(
            split_source,
            split_output,
            {"case_number":{"placeholder":"{{case_number}}"}},
            {"case_number":"FIRE-DOCX-74"},
        )
    assert not split_output.exists()


def test_phase8_fire_photo_metadata_duplicate_and_search(tmp_path):
    from io import BytesIO
    from PIL import Image as PILImage
    from app.settings import settings

    login()
    old_root=settings.storage_root
    settings.storage_root=str(tmp_path)
    try:
        facility=client.post("/facilities",json={"name":"Phase8写真対象"}).json()
        bid=facility["building_id"]
        case=client.post("/fire-investigations",json={
            "case_number":"FIRE-PHOTO-8-001",
            "building_id":bid,
            "title":"Phase8写真テスト"
        })
        assert case.status_code==201
        cid=case.json()["fire_investigation_case_id"]

        image=PILImage.new("RGB",(1200,900),(95,110,125))
        for x in range(100,1100,100):
            for y in range(100,800):
                image.putpixel((x,y),(210,80,40))
        buf=BytesIO()
        image.save(buf,format="JPEG",quality=92)
        photo_bytes=buf.getvalue()

        def upload_and_link(name,seq):
            doc=client.post(
                "/documents/upload",
                files={"file":(name,photo_bytes,"image/jpeg")},
                data={"document_type":"fire_scene_photo","building_id":bid},
            )
            assert doc.status_code==201
            db=doc.json()
            media=client.post(f"/fire-investigations/{cid}/media",json={
                "document_id":db["document_id"],
                "media_type":"photo",
                "sequence_no":seq,
                "location_label":"出火室",
            })
            assert media.status_code==201
            return db,media.json()

        doc1,media1=upload_and_link("scene-001.jpg",1)
        a1=client.post(f"/fire-photos/media/{media1['fire_investigation_media_id']}/analyze")
        assert a1.status_code==200
        p1=a1.json()
        assert p1["photo_number"]==1
        assert p1["image_width"]==1200 and p1["image_height"]==900
        assert p1["exact_sha256"]==doc1["sha256"]
        assert p1["analysis_version"]=="photo-metadata-v1"
        assert p1["duplicate_of_media_id"] is None

        # Analysis is derived-only: source document hash remains identical.
        doc1_after=client.get(f"/documents/{doc1['document_id']}")
        assert doc1_after.status_code==200
        assert doc1_after.json()["sha256"]==doc1["sha256"]

        # Re-analysis updates the same one-to-one profile rather than duplicating it.
        a1_again=client.post(f"/fire-photos/media/{media1['fire_investigation_media_id']}/analyze")
        assert a1_again.status_code==200
        assert a1_again.json()["fire_photo_profile_id"]==p1["fire_photo_profile_id"]

        doc2,media2=upload_and_link("scene-copy.jpg",2)
        a2=client.post(f"/fire-photos/media/{media2['fire_investigation_media_id']}/analyze")
        assert a2.status_code==200
        p2=a2.json()
        assert p2["exact_sha256"]==doc2["sha256"]==doc1["sha256"]
        assert p2["duplicate_of_media_id"]==media1["fire_investigation_media_id"]
        assert p2["duplicate_distance"]==0

        duplicates=client.get(f"/fire-photos/cases/{cid}/duplicates")
        assert duplicates.status_code==200
        assert any(
            x["media"]["fire_investigation_media_id"]==media2["fire_investigation_media_id"]
            for x in duplicates.json()
        )

        annotation=client.post(
            f"/fire-investigations/media/{media1['fire_investigation_media_id']}/photo-annotations",
            json={
                "description":"壁面の焼損とコンセント周辺を確認",
                "tags":["焼損","コンセント","壁面"],
                "confidence":0.8,
                "source_kind":"ai",
                "model_version":"phase8-test",
            },
        )
        assert annotation.status_code==201
        ann=annotation.json()
        accepted=client.patch(
            f"/fire-investigations/photo-annotations/{ann['fire_photo_annotation_id']}",
            json={"expected_version":1,"status":"accepted"},
        )
        assert accepted.status_code==200

        search=client.get(f"/fire-photos/cases/{cid}/search",params={"q":"コンセント 焼損"})
        assert search.status_code==200
        assert search.json()
        assert search.json()[0]["media"]["fire_investigation_media_id"]==media1["fire_investigation_media_id"]
        assert search.json()[0]["search_score"]==2
        assert len(search.json()[0]["accepted_annotations"])==1
    finally:
        settings.storage_root=old_root


def test_phase8_perceptual_hash_distance_is_deterministic():
    from PIL import Image as PILImage
    from app.fire_photo_metadata import dhash_hex, hamming_distance_hex

    a=PILImage.new("RGB",(100,100),"white")
    b=PILImage.new("RGB",(100,100),"white")
    for y in range(20,80):
        a.putpixel((50,y),(0,0,0))
        b.putpixel((50,y),(0,0,0))
    ha=dhash_hex(a)
    hb=dhash_hex(b)
    assert ha==hb
    assert hamming_distance_hex(ha,hb)==0


def test_phase8_1_photo_plan_link_requires_same_facility_and_human_review():
    login()

    facility=client.post("/facilities",json={"name":"Phase8.1写真リンク対象"}).json()
    bid=facility["building_id"]
    other=client.post("/facilities",json={"name":"Phase8.1別対象"}).json()

    case=client.post("/fire-investigations",json={
        "case_number":"FIRE-PHOTO-LINK-8-001",
        "building_id":bid,
        "title":"Phase8.1写真位置リンク"
    })
    assert case.status_code==201
    cid=case.json()["fire_investigation_case_id"]

    photo_doc=client.post(
        "/documents/upload",
        files={"file":("plan-photo.jpg",b"not-real-image-needed-for-link-test","image/jpeg")},
        data={"document_type":"fire_scene_photo","building_id":bid},
    ).json()
    photo=client.post(f"/fire-investigations/{cid}/media",json={
        "document_id":photo_doc["document_id"],
        "media_type":"photo",
        "sequence_no":1,
    })
    assert photo.status_code==201
    pmid=photo.json()["fire_investigation_media_id"]

    drawing_doc=client.post(
        "/documents/upload",
        files={"file":("drawing.pdf",b"drawing-bytes","application/pdf")},
        data={"document_type":"drawing","building_id":bid},
    ).json()
    drawing=client.post(f"/facilities/{bid}/drawing-analyses",json={
        "document_id":drawing_doc["document_id"],
        "analysis_method":"manual",
        "summary":{"kind":"floor-plan"}
    })
    assert drawing.status_code==201
    aid=drawing.json()["drawing_analysis_id"]

    wrong_doc=client.post(
        "/documents/upload",
        files={"file":("wrong.pdf",b"wrong-drawing","application/pdf")},
        data={"document_type":"drawing","building_id":other["building_id"]},
    ).json()
    wrong=client.post(f"/facilities/{other['building_id']}/drawing-analyses",json={
        "document_id":wrong_doc["document_id"],
        "analysis_method":"manual"
    })
    assert wrong.status_code==201

    wrong_link=client.post(f"/fire-photos/media/{pmid}/plan-links",json={
        "drawing_analysis_id":wrong.json()["drawing_analysis_id"],
        "page_no":1,
        "position":{"x":0.3,"y":0.4},
        "source_kind":"ai",
        "confidence":0.7,
    })
    assert wrong_link.status_code==409

    bad_position=client.post(f"/fire-photos/media/{pmid}/plan-links",json={
        "drawing_analysis_id":aid,
        "page_no":1,
        "position":{"x":1.5,"y":0.4},
        "source_kind":"manual",
    })
    assert bad_position.status_code==422

    created=client.post(f"/fire-photos/media/{pmid}/plan-links",json={
        "drawing_analysis_id":aid,
        "page_no":1,
        "floor_number":1,
        "position":{"x":0.32,"y":0.44},
        "label":"出火室北側から撮影",
        "source_kind":"ai",
        "confidence":0.72,
    })
    assert created.status_code==201
    link=created.json()
    assert link["status"]=="pending"
    assert link["version"]==1

    accepted_before=client.get(f"/fire-photos/media/{pmid}/plan-links",params={"accepted_only":"true"})
    assert accepted_before.status_code==200
    assert accepted_before.json()==[]

    reviewed=client.patch(f"/fire-photos/plan-links/{link['fire_photo_plan_link_id']}",json={
        "expected_version":1,
        "status":"accepted"
    })
    assert reviewed.status_code==200
    assert reviewed.json()["status"]=="accepted"
    assert reviewed.json()["version"]==2

    accepted_after=client.get(f"/fire-photos/media/{pmid}/plan-links",params={"accepted_only":"true"})
    assert accepted_after.status_code==200
    assert len(accepted_after.json())==1

    stale=client.patch(f"/fire-photos/plan-links/{link['fire_photo_plan_link_id']}",json={
        "expected_version":1,
        "status":"rejected"
    })
    assert stale.status_code==409


def test_phase9_uncertainty_marker_positions_are_deterministic():
    from app.fire_transcript_semantics import extract_uncertainty_markers, transcript_text_sha256
    text="たぶん10時頃だったと思う。"
    markers=extract_uncertainty_markers(text)
    assert [x["text"] for x in markers]==["たぶん","10時頃","と思う"]
    for marker in markers:
        assert text[marker["start"]:marker["end"]]==marker["text"]
    assert transcript_text_sha256(text)==transcript_text_sha256(text)


def test_phase9_1_transcript_uncertainty_search_statement_gate_and_evidence_comparison():
    login()
    case=client.post("/fire-investigations",json={
        "case_number":"FIRE-TEST-9-001",
        "title":"Phase9音声供述テスト"
    })
    assert case.status_code==201
    cid=case.json()["fire_investigation_case_id"]

    audio=client.post(
        "/documents/upload",
        files={"file":("phase9.m4a",b"phase9-audio","audio/mp4")},
        data={"document_type":"fire_interview_audio"}
    )
    assert audio.status_code==201
    media=client.post(f"/fire-investigations/{cid}/media",json={
        "document_id":audio.json()["document_id"],
        "media_type":"audio",
        "sequence_no":1
    })
    assert media.status_code==201
    mid=media.json()["fire_investigation_media_id"]

    manifest=client.post(f"/fire-investigations/media/{mid}/transcript-ai-manifest",json={
        "model_version":"stt-test-v9",
        "payload_metadata":{"source":"unit-test"},
        "segments":[
            {
                "start_ms":0,
                "end_ms":5000,
                "speaker_label":"関係者A",
                "text":"たぶん10時頃に煙を見たと思います。",
                "confidence":0.82
            },
            {
                "start_ms":6000,
                "end_ms":9000,
                "speaker_label":"関係者A",
                "text":"玄関から外へ出ました。",
                "confidence":0.95
            }
        ]
    })
    assert manifest.status_code==200
    ids=manifest.json()["derived_ids"]
    assert len(ids)==2

    segments=client.get(f"/fire-investigations/media/{mid}/transcript-segments")
    assert segments.status_code==200
    rows=segments.json()
    uncertain=next(x for x in rows if x["fire_transcript_segment_id"]==ids[0])
    certain=next(x for x in rows if x["fire_transcript_segment_id"]==ids[1])
    assert uncertain["uncertainty_markers"]
    types={x["type"] for x in uncertain["uncertainty_markers"]}
    assert {"probability","approximation","belief"}.issubset(types)
    assert uncertain["text_sha256"]

    for row in (uncertain,certain):
        accepted=client.patch(
            f"/fire-investigations/transcript-segments/{row['fire_transcript_segment_id']}",
            json={"expected_version":1,"status":"accepted"}
        )
        assert accepted.status_code==200

    search=client.get(f"/fire-investigations/{cid}/transcript-search",params={
        "q":"煙",
        "uncertain_only":"true"
    })
    assert search.status_code==200
    assert len(search.json())==1
    assert search.json()[0]["segment"]["fire_transcript_segment_id"]==uncertain["fire_transcript_segment_id"]

    statement_manifest=client.post(f"/fire-investigations/{cid}/statement-ai-manifest",json={
        "model_version":"statement-test-v9",
        "payload_metadata":{"source":"unit-test"},
        "statements":[{
            "fire_investigation_media_id":mid,
            "person_label":"関係者A",
            "draft_text":"関係者Aは、10時頃に煙を見た可能性がある旨を述べた。",
            "evidence_segment_ids":[uncertain["fire_transcript_segment_id"]]
        }]
    })
    assert statement_manifest.status_code==200
    statement_id=statement_manifest.json()["derived_ids"][0]

    detail=client.get(f"/fire-investigations/{cid}")
    assert detail.status_code==200
    statement=next(x for x in detail.json()["statements"] if x["fire_statement_draft_id"]==statement_id)
    assert statement["source_uncertainty_markers"]
    assert "たぶん" in statement["source_uncertainty_markers"]
    assert statement["uncertainty_reviewed"] is False

    blocked=client.patch(f"/fire-investigations/statements/{statement_id}",json={
        "expected_version":1,
        "status":"reviewed",
        "uncertainty_reviewed":False
    })
    assert blocked.status_code==409

    reviewed=client.patch(f"/fire-investigations/statements/{statement_id}",json={
        "expected_version":1,
        "status":"reviewed",
        "uncertainty_reviewed":True
    })
    assert reviewed.status_code==200
    assert reviewed.json()["uncertainty_reviewed"] is True

    timeline=client.post(f"/fire-investigations/{cid}/timeline",json={
        "event_time_text":"10時頃",
        "event_type":"observation",
        "title":"煙を確認",
        "description":"供述に基づく候補",
        "source_refs":[{"type":"transcript_segment","id":uncertain["fire_transcript_segment_id"]}],
        "confidence":0.8
    })
    assert timeline.status_code==201
    tl=timeline.json()
    confirmed=client.patch(f"/fire-investigations/timeline/{tl['fire_timeline_event_id']}",json={
        "expected_version":1,
        "status":"confirmed"
    })
    assert confirmed.status_code==200

    comparison_payload={
        "model_version":"compare-test-v9",
        "payload_metadata":{"source":"unit-test"},
        "comparisons":[{
            "issue_type":"time_difference",
            "summary":"供述時刻とタイムライン記録を照合する必要がある。",
            "left_ref":{"type":"transcript_segment","id":uncertain["fire_transcript_segment_id"]},
            "right_ref":{"type":"timeline_event","id":tl["fire_timeline_event_id"]},
            "evidence_refs":[{"type":"statement","id":statement_id}],
            "confidence":0.7
        }]
    }
    comp=client.post(f"/fire-investigations/{cid}/evidence-comparison-ai-manifest",json=comparison_payload)
    assert comp.status_code==200
    cb=comp.json()
    assert cb["created"] is True
    assert len(cb["derived_ids"])==1
    comp_id=cb["derived_ids"][0]

    comp_repeat=client.post(f"/fire-investigations/{cid}/evidence-comparison-ai-manifest",json=comparison_payload)
    assert comp_repeat.status_code==200
    assert comp_repeat.json()["created"] is False
    assert comp_repeat.json()["derived_ids"]==[comp_id]

    listed=client.get(f"/fire-investigations/{cid}/evidence-comparisons")
    assert listed.status_code==200
    candidate=next(x for x in listed.json() if x["fire_evidence_comparison_candidate_id"]==comp_id)
    assert candidate["status"]=="pending"
    assert candidate["issue_type"]=="time_difference"

    accepted_comp=client.patch(f"/fire-investigations/evidence-comparisons/{comp_id}",json={
        "expected_version":1,
        "status":"accepted"
    })
    assert accepted_comp.status_code==200
    assert accepted_comp.json()["status"]=="accepted"
    assert accepted_comp.json()["version"]==2
    # Phase 9 hard gate: comparison acceptance must not mutate source evidence
    # or promote a formal fire cause.
    detail_after_comparison=client.get(f"/fire-investigations/{cid}")
    assert detail_after_comparison.status_code==200
    after=detail_after_comparison.json()
    statement_after=next(x for x in after["statements"] if x["fire_statement_draft_id"]==statement_id)
    timeline_after=next(x for x in after["timeline"] if x["fire_timeline_event_id"]==tl["fire_timeline_event_id"])
    assert statement_after["draft_text"]=="関係者Aは、10時頃に煙を見た可能性がある旨を述べた。"
    assert statement_after["status"]=="reviewed"
    assert timeline_after["status"]=="confirmed"
    assert after["case"]["official_cause_candidate_id"] is None
    assert after["case"]["official_cause_text"] is None


    stale=client.patch(f"/fire-investigations/evidence-comparisons/{comp_id}",json={
        "expected_version":1,
        "status":"rejected"
    })
    assert stale.status_code==409


def test_phase10_unified_search_is_permission_filtered_and_audited():
    from app.models import AuditLog
    login()

    facility=client.post("/facilities",json={
        "name":"横断検索キーワードOMEGA",
        "address":"検索住所"
    })
    assert facility.status_code==201

    fire_case=client.post("/fire-investigations",json={
        "case_number":"OMEGA-FIRE-001",
        "title":"横断検索キーワードOMEGA 火災調査"
    })
    assert fire_case.status_code==201

    result=client.get("/search",params={"q":"OMEGA","modules":"facilities,fire","limit":20})
    assert result.status_code==200
    body=result.json()
    assert {"facilities","fire"}.issubset(set(body["searched_modules"]))
    assert any(x["module"]=="facilities" for x in body["hits"])
    assert any(x["module"]=="fire" for x in body["hits"])
    assert all(x["required_permission"] for x in body["hits"])

    # Raw search text is not written to the audit log.
    with SessionLocal() as db:
        audit=db.scalar(
            select(AuditLog)
            .where(AuditLog.action=="unified_search.query")
            .order_by(AuditLog.audit_id.desc())
        )
        assert audit is not None
        after=audit.after_data or {}
        assert after.get("query_sha256")
        assert after.get("query_length")==5
        assert "OMEGA" not in str(after)

    # Create a second user with only facility search permission.
    with SessionLocal() as db:
        emp=Employee(display_name="検索限定利用者"); db.add(emp); db.flush()
        limited=User(
            employee_id=emp.employee_id,
            username="search-limited",
            password_hash=hash_password("limited-search-password"),
        )
        db.add(limited)
        role=Role(code="search_limited",name="Search Limited")
        db.add(role); db.flush()
        db.add(UserRole(user_id=limited.user_id,role_id=role.role_id))
        for code in ("search.use","facility.read"):
            perm=db.scalar(select(Permission).where(Permission.code==code))
            if perm is None:
                perm=Permission(code=code,description=code); db.add(perm); db.flush()
            db.add(RolePermission(role_id=role.role_id,permission_id=perm.permission_id))
        db.commit()

    client.cookies.clear()
    limited_login=client.post("/auth/login",json={
        "username":"search-limited",
        "password":"limited-search-password"
    })
    assert limited_login.status_code==200

    limited_result=client.get("/search",params={"q":"OMEGA"})
    assert limited_result.status_code==200
    limited_body=limited_result.json()
    assert limited_body["searched_modules"]==["facilities"]
    assert limited_body["hits"]
    assert all(x["module"]=="facilities" for x in limited_body["hits"])
    assert "fire" in limited_body["skipped_modules"]

    forbidden=client.get("/search",params={"q":"OMEGA","modules":"fire"})
    assert forbidden.status_code==403


def test_phase10_unified_search_returns_reviewed_fire_evidence_only():
    login()
    case=client.post("/fire-investigations",json={
        "case_number":"SEARCH-FIRE-10",
        "title":"Phase10証拠検索"
    }).json()
    cid=case["fire_investigation_case_id"]
    audio=client.post(
        "/documents/upload",
        files={"file":("search10.m4a",b"audio-search10","audio/mp4")},
        data={"document_type":"fire_interview_audio"}
    ).json()
    media=client.post(f"/fire-investigations/{cid}/media",json={
        "document_id":audio["document_id"],
        "media_type":"audio"
    }).json()
    mid=media["fire_investigation_media_id"]

    pending=client.post(f"/fire-investigations/media/{mid}/transcript-segments",json={
        "start_ms":0,
        "end_ms":2000,
        "speaker_label":"関係者",
        "text":"SECRET-PENDING-TRANSCRIPT",
        "source_kind":"ai",
        "model_version":"search-test"
    }).json()

    before=client.get("/search",params={"q":"SECRET-PENDING-TRANSCRIPT","modules":"fire"})
    assert before.status_code==200
    assert not any(x["source_type"]=="accepted_transcript" for x in before.json()["hits"])

    accepted=client.patch(
        f"/fire-investigations/transcript-segments/{pending['fire_transcript_segment_id']}",
        json={"expected_version":1,"status":"accepted"}
    )
    assert accepted.status_code==200

    after=client.get("/search",params={"q":"SECRET-PENDING-TRANSCRIPT","modules":"fire"})
    assert after.status_code==200
    hits=[x for x in after.json()["hits"] if x["source_type"]=="accepted_transcript"]
    assert len(hits)==1
    assert hits[0]["navigation"]["segment_id"]==pending["fire_transcript_segment_id"]


def test_phase9_audio_benchmark_scoring_helpers():
    import importlib.util
    from pathlib import Path

    script=Path(__file__).resolve().parents[2]/"scripts"/"benchmark_fire_audio.py"
    spec=importlib.util.spec_from_file_location("benchmark_fire_audio",script)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    exact=mod.score_text("火災調査","火災調査")
    assert exact["cer"]==0
    changed=mod.score_text("火災調査","火災調書")
    assert changed["errors"]==1
    assert changed["cer"]==1/4

    diar=mod.diarization_score(
        [
            {"start_ms":0,"end_ms":1000,"speaker":"A"},
            {"start_ms":1000,"end_ms":2000,"speaker":"B"},
        ],
        [
            {"start_ms":0,"end_ms":1000,"speaker":"A"},
            {"start_ms":1000,"end_ms":1500,"speaker":"A"},
            {"start_ms":1500,"end_ms":2000,"speaker":"B"},
        ],
    )
    assert diar["reference_ms"]==2000
    assert diar["speaker_confusion_ms"]==500
    assert diar["speaker_error_rate"]==0.25

    markers=mod.marker_metrics(
        [
            {"start_ms":100,"end_ms":200,"type":"low_confidence"},
            {"start_ms":300,"end_ms":400,"type":"inaudible"},
        ],
        [
            {"start_ms":100,"end_ms":200,"type":"low_confidence"},
            {"start_ms":500,"end_ms":600,"type":"inaudible"},
        ],
    )
    assert markers["true_positive"]==1
    assert markers["false_positive"]==1
    assert markers["false_negative"]==1
    assert markers["precision"]==0.5
    assert markers["recall"]==0.5


def test_phase9_audio_benchmark_v2_speaker_mapping_tolerance_and_aggregate(tmp_path):
    import importlib.util
    import json
    from pathlib import Path

    script=Path(__file__).resolve().parents[2]/"scripts"/"benchmark_fire_audio.py"
    spec=importlib.util.spec_from_file_location("benchmark_fire_audio_v2",script)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Hypothesis labels are intentionally swapped. Auto mapping should recover them.
    diar=mod.diarization_score(
        [
            {"start_ms":0,"end_ms":1000,"speaker":"INVESTIGATOR"},
            {"start_ms":1000,"end_ms":2000,"speaker":"WITNESS"},
        ],
        [
            {"start_ms":0,"end_ms":1000,"speaker":"SPEAKER_01"},
            {"start_ms":1000,"end_ms":2000,"speaker":"SPEAKER_00"},
        ],
        auto_map_speakers=True,
    )
    assert diar["speaker_error_rate"]==0
    assert diar["speaker_mapping"]["SPEAKER_01"]=="INVESTIGATOR"
    assert diar["speaker_mapping"]["SPEAKER_00"]=="WITNESS"

    # A small timestamp shift should match under tolerance but not exact mode.
    ref_markers=[{"start_ms":1000,"end_ms":1200,"type":"inaudible"}]
    hyp_markers=[{"start_ms":1030,"end_ms":1235,"type":"inaudible"}]
    exact=mod.marker_metrics(ref_markers,hyp_markers,tolerance_ms=0)
    tolerant=mod.marker_metrics(ref_markers,hyp_markers,tolerance_ms=50)
    assert exact["f1"]==0
    assert tolerant["f1"]==1

    ref1={
        "transcript_text":"火災調査",
        "speaker_segments":[{"start_ms":0,"end_ms":1000,"speaker":"A"}],
        "uncertainty_markers":[],
    }
    hyp1={
        "transcript_text":"火災調査",
        "speaker_segments":[{"start_ms":0,"end_ms":1000,"speaker":"S0"}],
        "uncertainty_markers":[],
    }
    ref2={
        "transcript_text":"出火場所",
        "speaker_segments":[{"start_ms":0,"end_ms":1000,"speaker":"B"}],
        "uncertainty_markers":[{"start_ms":500,"end_ms":700,"type":"low_confidence"}],
    }
    hyp2={
        "transcript_text":"出火場処",
        "speaker_segments":[{"start_ms":0,"end_ms":1000,"speaker":"S1"}],
        "uncertainty_markers":[{"start_ms":520,"end_ms":720,"type":"low_confidence"}],
    }

    (tmp_path/"r1.json").write_text(json.dumps(ref1,ensure_ascii=False),encoding="utf-8")
    (tmp_path/"h1.json").write_text(json.dumps(hyp1,ensure_ascii=False),encoding="utf-8")
    (tmp_path/"r2.json").write_text(json.dumps(ref2,ensure_ascii=False),encoding="utf-8")
    (tmp_path/"h2.json").write_text(json.dumps(hyp2,ensure_ascii=False),encoding="utf-8")
    manifest={
        "marker_tolerance_ms":50,
        "recordings":[
            {"id":"case-1","metadata":{"environment":"quiet_room","speaker_count":1},"reference":"r1.json","hypothesis":"h1.json"},
            {"id":"case-2","metadata":{"environment":"field_like","speaker_count":1},"reference":"r2.json","hypothesis":"h2.json"},
        ],
    }
    manifest_path=tmp_path/"manifest.json"
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False),encoding="utf-8")

    result=mod.score_manifest(manifest_path)
    assert result["benchmark_format"]=="fire-ai-japanese-stt-benchmark-v2"
    assert len(result["manifest_sha256"])==64
    assert all(len(x["reference_sha256"])==64 for x in result["recordings"])
    assert all(len(x["hypothesis_sha256"])==64 for x in result["recordings"])
    assert result["recordings"][0]["metadata"]["environment"]=="quiet_room"
    assert result["recordings"][1]["metadata"]["environment"]=="field_like"
    assert result["aggregate"]["recording_count"]==2
    assert result["aggregate"]["text_micro"]["reference_chars"]==8
    assert result["aggregate"]["text_micro"]["errors"]==1
    assert result["aggregate"]["text_micro"]["cer"]==1/8
    assert result["aggregate"]["diarization_micro"]["speaker_error_rate"]==0
    assert result["aggregate"]["uncertainty_markers_micro"]["f1"]==1


def test_phase9_audio_benchmark_v2_false_alarm_and_overlap_do_not_double_count():
    import importlib.util
    from pathlib import Path

    script=Path(__file__).resolve().parents[2]/"scripts"/"benchmark_fire_audio.py"
    spec=importlib.util.spec_from_file_location("benchmark_fire_audio_v2_false_alarm",script)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result=mod.diarization_score(
        [{"start_ms":0,"end_ms":1000,"speaker":"A"}],
        [
            {"start_ms":0,"end_ms":1000,"speaker":"H1"},
            {"start_ms":250,"end_ms":750,"speaker":"H2"},
            {"start_ms":1000,"end_ms":1200,"speaker":"H3"},
        ],
        auto_map_speakers=True,
    )
    assert result["reference_ms"]==1000
    assert result["correct_speaker_ms"]<=1000
    assert result["speaker_confusion_ms"]+result["missed_ms"]<=1000
    assert result["false_alarm_ms"]==200


def test_phase9_audio_benchmark_run_registry_is_idempotent_and_human_reviewed():
    login()
    result_payload={
        "benchmark_format":"fire-ai-japanese-stt-benchmark-v2",
        "manifest_sha256":"a"*64,
        "marker_tolerance_ms":250,
        "speaker_mapping":"auto_overlap",
        "recordings":[
            {
                "recording_id":"case-001",
                "metadata":{"environment":"quiet_room"},
                "reference":"r.json",
                "reference_sha256":"b"*64,
                "hypothesis":"h.json",
                "hypothesis_sha256":"c"*64,
                "text":{"reference_chars":10,"hypothesis_chars":10,"substitutions":0,"insertions":0,"deletions":0,"errors":0,"cer":0},
                "diarization":{"reference_ms":1000,"correct_speaker_ms":1000,"speaker_confusion_ms":0,"missed_ms":0,"false_alarm_ms":0,"speaker_error_ms":0,"speaker_error_rate":0,"speaker_mapping":{"S0":"A"},"speaker_mapping_mode":"auto_overlap"},
                "uncertainty_markers":{"reference_markers":0,"hypothesis_markers":0,"true_positive":0,"false_positive":0,"false_negative":0,"precision":1,"recall":1,"f1":1,"tolerance_ms":250}
            }
        ],
        "aggregate":{
            "recording_count":1,
            "text_micro":{"reference_chars":10,"substitutions":0,"insertions":0,"deletions":0,"errors":0,"cer":0},
            "diarization_micro":{"reference_ms":1000,"correct_speaker_ms":1000,"speaker_confusion_ms":0,"missed_ms":0,"false_alarm_ms":0,"speaker_error_ms":0,"speaker_error_rate":0},
            "uncertainty_markers_micro":{"true_positive":0,"false_positive":0,"false_negative":0,"precision":1,"recall":1,"f1":1}
        },
        "policy":"evidence only"
    }

    first=client.post("/fire-investigations/audio-benchmarks",json={
        "dataset_label":"Baseline A",
        "result_payload":result_payload
    })
    assert first.status_code==201
    body=first.json()
    bid=body["fire_audio_benchmark_run_id"]
    assert body["review_status"]=="pending"
    assert body["recording_count"]==1
    assert len(body["result_sha256"])==64

    duplicate=client.post("/fire-investigations/audio-benchmarks",json={
        "dataset_label":"Duplicate label should not create another row",
        "result_payload":result_payload
    })
    assert duplicate.status_code==201
    assert duplicate.json()["fire_audio_benchmark_run_id"]==bid

    reviewed=client.post(f"/fire-investigations/audio-benchmarks/{bid}/review",json={
        "expected_version":1,
        "human_decision":"accepted_baseline",
        "review_notes":"Benchmark baseline accepted for comparison only."
    })
    assert reviewed.status_code==200
    assert reviewed.json()["review_status"]=="reviewed"
    assert reviewed.json()["human_decision"]=="accepted_baseline"
    assert reviewed.json()["version"]==2

    stale=client.post(f"/fire-investigations/audio-benchmarks/{bid}/review",json={
        "expected_version":1,
        "human_decision":"rejected_baseline"
    })
    assert stale.status_code==409

    listed=client.get("/fire-investigations/audio-benchmarks")
    assert listed.status_code==200
    assert any(x["fire_audio_benchmark_run_id"]==bid for x in listed.json())


def test_phase9_audio_benchmark_registry_rejects_unknown_format():
    login()
    bad=client.post("/fire-investigations/audio-benchmarks",json={
        "dataset_label":"Bad format",
        "result_payload":{"benchmark_format":"unknown-v99"}
    })
    assert bad.status_code==422


def test_phase9_audio_benchmark_comparison_reports_metric_deltas_only():
    login()

    def payload(cer, der, f1, marker):
        return {
            "benchmark_format":"fire-ai-japanese-stt-benchmark-v2",
            "manifest_sha256":marker*64,
            "recordings":[],
            "aggregate":{
                "recording_count":2,
                "text_micro":{"cer":cer},
                "diarization_micro":{"speaker_error_rate":der},
                "uncertainty_markers_micro":{"f1":f1}
            }
        }

    left=client.post("/fire-investigations/audio-benchmarks",json={
        "dataset_label":"Model A",
        "result_payload":payload(0.20,0.30,0.60,"d")
    })
    right=client.post("/fire-investigations/audio-benchmarks",json={
        "dataset_label":"Model B",
        "result_payload":payload(0.10,0.20,0.80,"e")
    })
    assert left.status_code==201 and right.status_code==201

    compared=client.get("/fire-investigations/audio-benchmarks/compare",params={
        "left_id":left.json()["fire_audio_benchmark_run_id"],
        "right_id":right.json()["fire_audio_benchmark_run_id"],
    })
    assert compared.status_code==200
    body=compared.json()
    assert round(body["metrics"]["cer"]["delta_right_minus_left"],6)==-0.1
    assert round(body["metrics"]["speaker_error_rate"]["delta_right_minus_left"],6)==-0.1
    assert round(body["metrics"]["uncertainty_f1"]["delta_right_minus_left"],6)==0.2
    assert body["metrics"]["cer"]["lower_is_better"] is True
    assert body["metrics"]["uncertainty_f1"]["higher_is_better"] is True
    assert "Dataset composition" in body["note"]


def test_phase9_evidence_comparison_benchmark_registry_human_gate_and_comparison():
    login()

    def payload(precision, recall, f1, fp, marker):
        tp = 8
        fn = 2
        hypothesis_count = tp + fp
        return {
            "benchmark_format": "fire-ai-evidence-comparison-benchmark-v1",
            "manifest_sha256": marker * 64,
            "cases": [],
            "aggregate": {
                "case_count": 5,
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "reference_count": tp + fn,
                "hypothesis_count": hypothesis_count,
            },
            "policy": "benchmark evidence only",
        }

    first_payload = payload(0.8, 0.8, 0.8, 2, "a")
    first = client.post(
        "/fire-investigations/evidence-comparison-benchmarks",
        json={"dataset_label": "Evidence Model A", "result_payload": first_payload},
    )
    assert first.status_code == 201
    body = first.json()
    bid = body["fire_evidence_comparison_benchmark_run_id"]
    assert body["review_status"] == "pending"
    assert body["case_count"] == 5
    assert len(body["result_sha256"]) == 64

    duplicate = client.post(
        "/fire-investigations/evidence-comparison-benchmarks",
        json={
            "dataset_label": "Duplicate label must not create another row",
            "result_payload": first_payload,
        },
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["fire_evidence_comparison_benchmark_run_id"] == bid

    reviewed = client.post(
        f"/fire-investigations/evidence-comparison-benchmarks/{bid}/review",
        json={
            "expected_version": 1,
            "human_decision": "accepted_baseline",
            "review_notes": "Accepted for benchmark comparison only.",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "reviewed"
    assert reviewed.json()["human_decision"] == "accepted_baseline"
    assert reviewed.json()["version"] == 2

    stale = client.post(
        f"/fire-investigations/evidence-comparison-benchmarks/{bid}/review",
        json={"expected_version": 1, "human_decision": "rejected_baseline"},
    )
    assert stale.status_code == 409

    second = client.post(
        "/fire-investigations/evidence-comparison-benchmarks",
        json={
            "dataset_label": "Evidence Model B",
            "result_payload": payload(0.9, 0.8, 0.8470588235294118, 1, "b"),
        },
    )
    assert second.status_code == 201

    compared = client.get(
        "/fire-investigations/evidence-comparison-benchmarks/compare",
        params={
            "left_id": bid,
            "right_id": second.json()["fire_evidence_comparison_benchmark_run_id"],
        },
    )
    assert compared.status_code == 200
    metrics = compared.json()["metrics"]
    assert round(metrics["precision"]["delta_right_minus_left"], 6) == 0.1
    assert round(metrics["recall"]["delta_right_minus_left"], 6) == 0.0
    assert metrics["f1"]["higher_is_better"] is True
    assert round(metrics["false_positives_per_case"]["delta_right_minus_left"], 6) == -0.2
    assert metrics["false_positives_per_case"]["lower_is_better"] is True

    listed = client.get("/fire-investigations/evidence-comparison-benchmarks")
    assert listed.status_code == 200
    assert any(
        x["fire_evidence_comparison_benchmark_run_id"] == bid for x in listed.json()
    )

    bad = client.post(
        "/fire-investigations/evidence-comparison-benchmarks",
        json={
            "dataset_label": "Bad format",
            "result_payload": {"benchmark_format": "unknown-v99"},
        },
    )
    assert bad.status_code == 422
