"""Actual Chromium acceptance for SPECIFICATION §54(2); synthetic records only.

The browser drives the shared shell and real HTTP endpoints. Interception is
limited to holding a real response or injecting one failed request, so retries
and originating-session checks can be observed deterministically.
Run only in the dedicated browser job with FIRE_AI_TEST_BROWSER=1.
"""

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest


PASSWORD = "synthetic-intake-password"
SELECTED_NAME = "Synthetic Intake Selected Hotel"
OTHER_NAME = "Synthetic Intake Unselected Hotel"
OLD_ADDRESS = "Synthetic old selected address 101"
NEW_ADDRESS = "Synthetic reviewed address 202"
OLD_PHONE = "0997-11-1111"
NEW_PHONE = "0997-99-9999"
SOURCE_BYTES = (
    "消防用設備等点検結果報告書\n"
    f"防火対象物名称: {SELECTED_NAME}\n"
    f"所在地: {NEW_ADDRESS}\n"
    f"電話番号: {NEW_PHONE}\n"
    "令和8年10月5日\n"
).encode("utf-8")


INTAKE_SEED = """
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import Facility, User, UserRole
from app.rbac_seed import seed_rbac
from app.submission_seed import seed_submission_types
from app.security import hash_password
Base.metadata.create_all(engine)
with SessionLocal() as db:
    roles = seed_rbac(db)
    seed_submission_types(db)
    for username in ['intake-operator', 'intake-other-operator']:
        user = User(username=username, password_hash=hash_password('synthetic-intake-password'))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.user_id, role_id=roles['system_admin'].role_id))
    db.add(Facility(name='Synthetic Intake Selected Hotel', address='Synthetic old selected address 101', phone='0997-11-1111', status='active'))
    db.add(Facility(name='Synthetic Intake Unselected Hotel', address='Synthetic untouched address 303', phone='0997-33-3333', status='active'))
    db.commit()
"""

@pytest.fixture
def intake_browser(tmp_path):
    if os.environ.get("FIRE_AI_TEST_BROWSER") != "1":
        pytest.skip("actual Chromium intake journey executes in dedicated CI job")
    from playwright.sync_api import expect, sync_playwright

    root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "PYTHONPATH": str(root / "backend"),
        "FIRE_AI_DATABASE_URL": "sqlite+pysqlite:///" + str(tmp_path / "synthetic.db"),
        "FIRE_AI_STORAGE_ROOT": str(tmp_path / "storage"),
        "FIRE_AI_PRODUCTION_MODE": "false",
    }
    env.pop("FIRE_AI_TENANT_ID", None)
    subprocess.run(
        [sys.executable, "-c", INTAKE_SEED], cwd=root, env=env, check=True, capture_output=True
    )
    with socket.socket() as allocation:
        allocation.bind(("127.0.0.1", 0))
        port = allocation.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "server.log"
    with log_path.open("w") as logs:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=root, env=env, stdout=logs, stderr=logs,
        )
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + "/health", timeout=0.2).close()
                    break
                except OSError:
                    if server.poll() is not None:
                        raise AssertionError(log_path.read_text())
                    time.sleep(0.1)
            else:
                raise AssertionError("synthetic intake server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context()
                page = context.new_page()
                page.set_default_timeout(15_000)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/ui/")
                page.locator("#loginUser").fill("intake-operator")
                page.locator("#loginPass").fill(PASSWORD)
                page.get_by_role("button", name="ログイン", exact=True).click()
                expect(page.locator("#facilityList")).to_contain_text(SELECTED_NAME)
                facilities = _get(page, base, "/facilities?limit=50")["items"]
                selected = next(row for row in facilities if row["name"] == SELECTED_NAME)
                other = next(row for row in facilities if row["name"] == OTHER_NAME)
                page.locator(".facilityItem").filter(has_text=SELECTED_NAME).click()
                expect(page.locator("#detailView h1")).to_have_text(SELECTED_NAME)
                # Detail rendering precedes its final list refresh. Wait until
                # the row is current so the next guarded click is not discarded.
                expect(page.locator(".facilityItem.selected b")).to_have_text(SELECTED_NAME)
                try:
                    yield page, base, selected, other, tmp_path
                    assert not errors, errors
                finally:
                    context.close()
                    browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            if sys.exc_info()[0]:
                print(log_path.read_text())


def _get(page, base, path):
    response = page.request.get(base + path)
    assert response.status == 200, response.text()
    return response.json()


def _selected_submissions(page, base, selected, other):
    # The list API is facility-scoped. Always inspect both fixture facilities so
    # an unexpected receipt on the unselected target cannot escape a count check.
    rows = _get(page, base, "/submissions?building_id=" + selected["building_id"])
    untouched = _get(page, base, "/submissions?building_id=" + other["building_id"])
    assert untouched == [], "unselected facility has an unexpected receipt: " + repr(untouched)
    assert all(row["building_id"] == selected["building_id"] for row in rows)
    return rows


def _route_once(page, pattern, handler):
    # Keep the handler installed after its first match; later requests fall through.
    # Expiring an interception can strand the next request on older Chromium.
    consumed = False

    def dispatch(route):
        nonlocal consumed
        if consumed:
            return route.fallback()
        consumed = True
        return handler(route)

    page.route(pattern, dispatch)


def _hold_response(page, pattern):
    held = []

    def hold(route):
        held.append((route, route.fetch()))

    _route_once(page, pattern, hold)
    return held


def _await_held(page, held):
    deadline = time.monotonic() + 15
    while not held and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert len(held) == 1, "expected one real HTTP response held by Chromium"
    return held[0]


def _artifact(page, tmp_path, name, evidence=None):
    destination = Path(os.environ.get("FIRE_AI_BROWSER_ARTIFACTS", str(tmp_path / "artifacts")))
    destination.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(destination / f"{name}.png"), full_page=True)
    if evidence is not None:
        (destination / f"{name}.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class _PromptJourney:
    """Answer the existing native dialogs as a Human operator, without replacing them."""

    def __init__(self, page, *, cancel_at=None, before_receipt=None, upload_failure=False):
        self.page = page
        self.cancel_at = cancel_at
        self.before_receipt = before_receipt
        self.upload_failure = upload_failure
        self.finished = False
        self.callback_error = None
        self.messages = []
        self.failures = []
        self.responses = []
        self.requests = []
        page.on("dialog", self.answer)
        page.on("response", self.record_response)
        page.on("request", self.record_request)

    def record_request(self, request):
        if request.method == "POST" and any(
            part in request.url
            for part in ("/documents/upload", "/document-analyses", "/facility-change-proposals")
        ):
            self.requests.append(request)

    def record_response(self, response):
        if response.request.method == "POST" and any(
            part in response.url
            for part in ("/documents/upload", "/document-analyses", "/facility-change-proposals")
        ):
            self.responses.append(response)

    def answer(self, dialog):
        if self.callback_error is not None:
            dialog.dismiss()
            return
        try:
            self._answer(dialog)
        except Exception as exc:
            # Playwright event listeners otherwise log this exception and leave
            # the native dialog open, hiding the assertion behind a timeout.
            self.callback_error = exc
            self.finished = True
            try:
                dialog.dismiss()
            except Exception:
                pass  # Preserve the original assertion if already dismissed.

    def _answer(self, dialog):
        message = dialog.message
        self.messages.append(message)
        if message.startswith("文書解析完了"):
            dialog.accept()
        elif message.startswith("対象物候補を確認してください"):
            # The source names only SELECTED_NAME, even when another facility is open.
            assert f"1: {SELECTED_NAME}" in message, message
            if self.cancel_at == "facility":
                self.finished = True
                dialog.dismiss()
            else:
                dialog.accept("1")
        elif message.startswith("書類種別を確認してください"):
            if self.cancel_at == "classification":
                self.finished = True
                dialog.dismiss()
            else:
                assert "[解析候補]" in message, message
                dialog.accept(dialog.default_value)
        elif message.startswith("台帳との差分候補があります"):
            if self.before_receipt:
                self.before_receipt()
            dialog.accept()
        elif message.startswith("正式届出番号"):
            if self.cancel_at == "official_number":
                self.finished = True
                dialog.dismiss()
            else:
                dialog.accept("5402")
        elif message.startswith("提出日 YYYY-MM-DD"):
            if self.cancel_at == "submitted_at":
                self.finished = True
                dialog.dismiss()
            else:
                dialog.accept("2026-10-05")
        elif message.startswith("受付を確定します"):
            if self.cancel_at == "receipt":
                self.finished = True
                dialog.dismiss()
            else:
                dialog.accept()
        elif message.startswith("台帳変更候補"):
            if "\nfacility.address\n" in message:
                dialog.accept()
            else:
                dialog.dismiss()
        elif message.startswith("台帳差分は反映されませんでした"):
            dialog.accept()
        elif message == "受付を登録しました。":
            self.finished = True
            dialog.accept()
        elif self.upload_failure and message.startswith("文書解析受付を完了できません"):
            assert "Synthetic upload unavailable" in message, message
            self.finished = True
            dialog.accept()
        else:
            self.failures.append(message)
            self.finished = True
            dialog.dismiss()

    def wait(self):
        deadline = time.monotonic() + 20
        while not self.finished and time.monotonic() < deadline:
            self.page.wait_for_timeout(20)
        if self.callback_error is not None:
            raise self.callback_error
        assert self.finished, self.messages
        assert not self.failures, self.failures

    def result(self, suffix, status):
        matches = [response for response in self.responses if response.url.endswith(suffix)]
        assert len(matches) == 1, [(response.url, response.status) for response in matches]
        response = matches[0]
        assert response.status == status, response.text()
        return response.json()

    def close(self):
        self.page.remove_listener("dialog", self.answer)
        self.page.remove_listener("response", self.record_response)
        self.page.remove_listener("request", self.record_request)


def _choose_source(page):
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="文書解析して受付", exact=True).click()
    chooser.value.set_files(
        {"name": "Synthetic intake original.txt", "mimeType": "text/plain", "buffer": SOURCE_BYTES}
    )


def _assert_original(page, base, document_id):
    original = _get(page, base, "/documents/" + document_id)
    assert original["sha256"] == sha256(SOURCE_BYTES).hexdigest()
    assert original["size_bytes"] == len(SOURCE_BYTES)
    response = page.request.get(base + "/documents/" + document_id + "/download")
    assert response.status == 200, response.text()
    assert response.body() == SOURCE_BYTES
    return original


def _facility(page, base, building_id):
    return _get(page, base, "/facilities/" + building_id + "/detail")["facility"]


def test_intake_document_human_receipt_address_only_and_unified_search(intake_browser):
    from playwright.sync_api import expect

    page, base, selected, other, tmp_path = intake_browser
    # The Human selection must win over the facility open when upload starts.
    page.locator(".facilityItem").filter(has_text=OTHER_NAME).click()
    expect(page.locator("#detailView h1")).to_have_text(OTHER_NAME)
    expect(page.locator(".facilityItem.selected b")).to_have_text(OTHER_NAME)
    before = _facility(page, base, selected["building_id"])
    untouched = _facility(page, base, other["building_id"])
    gate_snapshots = []

    def check_human_gate():
        gate_snapshots.append(_selected_submissions(page, base, selected, other))
        assert gate_snapshots[-1] == []
        assert _facility(page, base, selected["building_id"]) == before
        assert _facility(page, base, other["building_id"]) == untouched

    journey = _PromptJourney(page, before_receipt=check_human_gate)
    try:
        _choose_source(page)
        journey.wait()
        doc = journey.result("/documents/upload", 201)
        analysis = journey.result("/document-analyses", 201)
        key = analysis["document_analysis_id"]
        review = journey.result("/review", 200)
        receipt = journey.result("/confirm-receipt", 201)
        proposal = journey.result("/apply", 200)
        assert gate_snapshots == [[]]
        assert analysis["document_id"] == doc["document_id"]
        assert analysis["detected_submission_type_code"] == "equipment_inspection_report"
        assert analysis["facility_candidates"][0]["building_id"] == selected["building_id"]
        assert {"facility.address", "facility.phone"} <= set(analysis["difference_candidates"])
        assert review["status"] == "reviewed"
        assert review["selected_building_id"] == selected["building_id"]
        assert receipt["building_id"] == selected["building_id"]
        assert receipt["document_ids"] == [doc["document_id"]]
        assert receipt["official_number"] == "5402"
        assert receipt["submitted_at"] == "2026-10-05"
        assert proposal["status"] == "applied"
        apply_request = next(request for request in journey.requests if request.url.endswith("/apply"))
        assert apply_request.post_data_json["accepted_paths"] == ["facility.address"]
        assert any("\nfacility.phone\n" in message for message in journey.messages)
        updated = _facility(page, base, selected["building_id"])
        assert updated["address"] == NEW_ADDRESS
        assert updated["phone"] == OLD_PHONE
        assert updated["name"] == SELECTED_NAME
        assert updated["version"] == before["version"] + 1
        assert _facility(page, base, other["building_id"]) == untouched
        assert len(_selected_submissions(page, base, selected, other)) == 1
        original = _assert_original(page, base, doc["document_id"])
        confirmed = _get(page, base, "/document-analyses/" + key)
        assert confirmed["status"] == "receipt_confirmed"

        # A double-submitted/retried same-analysis request cannot create a second
        # receipt, including a retry with the terminal analysis's latest version.
        # The UI still has native prompts, not a separate resumable receipt form.
        for version in (review["version"], confirmed["version"]):
            duplicate = page.request.post(
                base + "/document-analyses/" + key + "/confirm-receipt",
                data={"expected_version": version, "official_number": "5402", "submitted_at": "2026-10-05"},
            )
            assert duplicate.status == 409, duplicate.text()
        assert len(_selected_submissions(page, base, selected, other)) == 1
        expect(page.locator("#detailView h1")).to_have_text(SELECTED_NAME)
        expect(page.locator("#detailView")).to_contain_text(NEW_ADDRESS)
        expect(page.locator("#detailView")).to_contain_text("5402")

        page.locator("#unifiedSearchBtn").click()
        page.locator("#unifiedSearchQ").fill(SELECTED_NAME)
        with page.expect_response(lambda response: "/search?" in response.url) as searched:
            page.locator("#unifiedSearchQ").press("Enter")
        assert searched.value.status == 200, searched.value.text()
        hits = searched.value.json()["hits"]
        assert any(hit["module"] == "facilities" and hit["source_id"] == selected["building_id"] for hit in hits)
        assert any(hit["module"] == "submissions" and hit["source_id"] == receipt["submission_id"] for hit in hits)
        expect(page.locator("#unifiedSearchResults")).to_contain_text(NEW_ADDRESS)
        expect(page.locator("#unifiedSearchResults")).to_contain_text("5402")
        page.locator("#unifiedSearchQ").fill(original["sha256"])
        with page.expect_response(lambda response: "/search?" in response.url) as source_search:
            page.locator("#unifiedSearchQ").press("Enter")
        assert source_search.value.status == 200, source_search.value.text()
        document_hits = source_search.value.json()["hits"]
        assert any(hit["module"] == "documents" and hit["source_id"] == doc["document_id"] for hit in document_hits)
        expect(page.locator("#unifiedSearchResults")).to_contain_text(original["sha256"])
        # Receipt linking gives this document a building_id. The current search
        # UI navigates linked-document hits to the facility; it has no original
        # link for these hits. Exact original bytes were checked via the real
        # authorized download API above, not an invented browser control.

        # Follow the actual unified-search facility navigation back to its receipt.
        page.locator("#unifiedSearchQ").fill(SELECTED_NAME)
        with page.expect_response(lambda response: "/search?" in response.url):
            page.locator("#unifiedSearchQ").press("Enter")
        facility_hit = page.locator("#unifiedSearchResults .card").filter(has_text="出典 facility / " + selected["building_id"])
        with page.expect_response(lambda response: response.url == base + "/facilities/" + selected["building_id"] + "/detail") as reopened:
            facility_hit.get_by_role("button").click()
        assert reopened.value.status == 200, reopened.value.text()
        expect(page.locator("#unifiedSearchModal")).to_be_hidden()
        expect(page.locator("#detailView h1")).to_have_text(SELECTED_NAME)
        expect(page.locator("#detailView")).to_contain_text("5402")
        _artifact(page, tmp_path, "intake-human-receipt-address-search", {
            "analysis_id": key, "submission_id": receipt["submission_id"],
            "selected_building_id": selected["building_id"], "original_sha256": original["sha256"],
            "original_size_bytes": original["size_bytes"], "accepted_paths": ["facility.address"],
            "receipt_count": 1, "search_modules": sorted({hit["module"] for hit in hits}),
        })
    finally:
        journey.close()


@pytest.mark.parametrize("cancel_at", ["facility", "classification", "official_number", "submitted_at", "receipt"])
def test_intake_cancel_leaves_original_without_receipt_or_facility_changes(intake_browser, cancel_at):
    page, base, selected, other, tmp_path = intake_browser
    before = [_facility(page, base, row["building_id"]) for row in (selected, other)]
    journey = _PromptJourney(page, cancel_at=cancel_at)
    try:
        _choose_source(page)
        journey.wait()
        doc = journey.result("/documents/upload", 201)
        analysis = journey.result("/document-analyses", 201)
        current = _get(page, base, "/document-analyses/" + analysis["document_analysis_id"])
        assert current["status"] == ("analyzed" if cancel_at in ("facility", "classification") else "reviewed")
        assert _selected_submissions(page, base, selected, other) == []
        assert not any(request.url.endswith(("/confirm-receipt", "/apply")) for request in journey.requests)
        assert [_facility(page, base, row["building_id"]) for row in (selected, other)] == before
        _assert_original(page, base, doc["document_id"])
        _artifact(page, tmp_path, "intake-cancel-" + cancel_at)
    finally:
        journey.close()


def test_intake_rejected_upload_can_retry_from_same_facility(intake_browser):
    page, base, selected, other, _ = intake_browser
    before = [_facility(page, base, row["building_id"]) for row in (selected, other)]
    _route_once(page, "**/documents/upload", lambda route: route.fulfill(
        status=503, json={"detail": "Synthetic upload unavailable"}
    ))
    failed = _PromptJourney(page, upload_failure=True)
    try:
        _choose_source(page)
        failed.wait()
        assert failed.result("/documents/upload", 503)["detail"] == "Synthetic upload unavailable"
        assert len(failed.requests) == 1
        assert _get(page, base, "/document-analyses") == []
        assert _selected_submissions(page, base, selected, other) == []
        assert [_facility(page, base, row["building_id"]) for row in (selected, other)] == before
    finally:
        failed.close()
    retried = _PromptJourney(page)
    try:
        _choose_source(page)
        retried.wait()
        doc = retried.result("/documents/upload", 201)
        retried.result("/confirm-receipt", 201)
        assert len(_get(page, base, "/document-analyses")) == 1
        assert len(_selected_submissions(page, base, selected, other)) == 1
        _assert_original(page, base, doc["document_id"])
    finally:
        retried.close()


def test_intake_stale_facility_keeps_receipt_and_rejects_address_apply(intake_browser):
    from playwright.sync_api import expect

    page, base, selected, other, tmp_path = intake_browser
    untouched = _facility(page, base, other["building_id"])
    concurrent = page.context.browser.new_context()
    login = concurrent.request.post(base + "/auth/login", data={"username": "intake-other-operator", "password": PASSWORD})
    assert login.status == 200, login.text()
    updates = []

    def other_operator_edit():
        response = concurrent.request.patch(base + "/facilities/" + selected["building_id"], data={
            "expected_version": selected["version"], "phone": "0997-44-4444",
        })
        assert response.status == 200, response.text()
        updates.append(response.json())

    journey = _PromptJourney(page, before_receipt=other_operator_edit)
    try:
        _choose_source(page)
        journey.wait()
        assert len(updates) == 1
        doc = journey.result("/documents/upload", 201)
        analysis = journey.result("/document-analyses", 201)
        journey.result("/confirm-receipt", 201)
        journey.result("/apply", 409)
        assert any(message.startswith("台帳差分は反映されませんでした") for message in journey.messages)
        actual = _facility(page, base, selected["building_id"])
        assert actual["address"] == OLD_ADDRESS
        assert actual["phone"] == "0997-44-4444"
        assert actual["version"] == selected["version"] + 1
        assert _facility(page, base, other["building_id"]) == untouched
        assert len(_selected_submissions(page, base, selected, other)) == 1
        proposals = _get(page, base, "/document-analyses/" + analysis["document_analysis_id"] + "/change-proposals")
        assert len(proposals) == 1 and proposals[0]["status"] == "pending"
        _assert_original(page, base, doc["document_id"])
        expect(page.locator("#detailView")).to_contain_text(OLD_ADDRESS)
        expect(page.locator("#detailView")).to_contain_text("5402")
        _artifact(page, tmp_path, "intake-stale-facility-receipt-preserved")
    finally:
        journey.close()
        concurrent.close()


@pytest.mark.parametrize("next_user", ["intake-operator", "intake-other-operator"])
def test_intake_late_upload_cannot_cross_authenticated_session_change(intake_browser, next_user):
    from playwright.sync_api import expect

    page, base, selected, other, tmp_path = intake_browser
    before_facilities = [_facility(page, base, row["building_id"]) for row in (selected, other)]
    held = _hold_response(page, "**/documents/upload")
    dialogs = []

    def unexpected_dialog(dialog):
        dialogs.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", unexpected_dialog)
    _choose_source(page)
    route, upload = _await_held(page, held)
    assert upload.status == 201, upload.text()
    doc = upload.json()
    before = _get(page, base, "/auth/context")
    assert page.request.post(base + "/auth/logout").status == 200
    switched = page.request.post(base + "/auth/login", data={"username": next_user, "password": PASSWORD})
    assert switched.status == 200, switched.text()
    after = _get(page, base, "/auth/context")
    assert before["session_id"] != after["session_id"]
    assert (before["user_id"] == after["user_id"]) == (next_user == "intake-operator")
    with page.expect_response(lambda response: response.url == base + "/documents/upload"):
        route.fulfill(response=upload)
    expect(page.locator("#loginView")).to_be_visible()
    expect(page.locator("#detailView")).not_to_contain_text(SELECTED_NAME)
    assert page.evaluate("state.detail") is None
    assert dialogs == [], dialogs
    assert _get(page, base, "/document-analyses") == []
    assert _selected_submissions(page, base, selected, other) == []
    assert [_facility(page, base, row["building_id"]) for row in (selected, other)] == before_facilities
    _assert_original(page, base, doc["document_id"])
    _artifact(page, tmp_path, "intake-session-change-" + next_user)


@pytest.mark.parametrize("scenario", ["candidate-cancel", "candidate-negative", "candidate-fraction", "candidate-out-of-range", "candidate-nonnumeric", "official-cancel", "official-empty"])
def test_intake_actual_prompt_function_cancellation_contract(scenario):
    """Small Node regression of the actual prompt function; this is not Chromium evidence."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the prompt cancellation regression")
    root = Path(__file__).resolve().parents[2]
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[1], 'utf8');
const scenario = process.argv[2];
const start = html.indexOf('async function smartReceiveSubmission()');
const end = html.indexOf('\nfunction showLegalQueue()', start);
assert(start >= 0 && end > start, 'shared-shell intake function boundaries missing');
const calls = [], prompts = [], alerts = [];
const analysis = {document_analysis_id:'synthetic-analysis',version:1,extraction_method:'text',confidence:0.9,
  detected_submission_type_code:'equipment_inspection_report',
  facility_candidates:[{building_id:'selected',name:'Synthetic selected',address:'Synthetic old address',score:0.9}]};
let fileInput;
const candidate = {'candidate-cancel':null,'candidate-negative':'-1','candidate-fraction':'0.5',
  'candidate-out-of-range':'2','candidate-nonnumeric':'invalid'};
const context = {console,Number,JSON,Date,
  state:{detail:{facility:{building_id:'selected',name:'Synthetic selected'}},offset:0},
  document:{createElement(){fileInput={files:[{name:'synthetic.txt'}],click(){}};return fileInput;}},
  FormData:class {append(){}},
  alert(message){alerts.push(message);},
  confirm(){return true;},
  prompt(message,defaultValue){
    prompts.push(message);
    if(message.startsWith('対象物候補'))return Object.hasOwn(candidate,scenario)?candidate[scenario]:'1';
    if(message.startsWith('書類種別'))return '1';
    if(message.startsWith('正式届出番号'))return scenario==='official-cancel'?null:'';
    if(message.startsWith('提出日'))return '2026-10-05';
    throw Error('unexpected prompt '+message);
  },
  async api(path,options){
    calls.push({path,options});
    if(path==='/documents/upload')return {document_id:'synthetic-document'};
    if(path==='/document-analyses')return analysis;
    if(path==='/submissions/types')return [{code:'equipment_inspection_report',name:'Synthetic report'}];
    if(path.endsWith('/review'))return {...analysis,version:2,detected_fields:{},difference_candidates:{}};
    if(path.endsWith('/confirm-receipt'))return {submission_id:'synthetic-receipt'};
    if(path.endsWith('/change-proposals'))return [];
    throw Error('unexpected endpoint '+path);
  },
  async loadFacilities(){},async selectFacility(){}
};
vm.createContext(context);
vm.runInContext(html.slice(start,end),context);
(async()=>{
  await vm.runInContext('smartReceiveSubmission()',context);
  assert(fileInput?.onchange,'actual file input callback was not installed');
  await fileInput.onchange();
  const paths=calls.map(call=>call.path);
  if(scenario.startsWith('candidate-')){
    assert.deepEqual(paths,['/documents/upload','/document-analyses'], 'invalid/cancelled facility choice must stop before type lookup or Human review');
    assert.equal(prompts.length,1,'invalid/cancelled facility choice must not advance prompts');
  }else if(scenario==='official-cancel'){
    assert.deepEqual(paths,['/documents/upload','/document-analyses','/submissions/types','/document-analyses/synthetic-analysis/review'], 'cancelled receipt number must stop before receipt mutation');
    assert.equal(prompts.length,3,'cancelled receipt number must not advance to submitted date');
  }else{
    const receipts=calls.filter(call=>call.path.endsWith('/confirm-receipt'));
    assert.equal(receipts.length,1,'an explicitly blank official number remains permitted');
    assert.equal(JSON.parse(receipts[0].options.body).official_number,null);
    assert(alerts.includes('受付を登録しました。'));
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [node, "-e", script, str(root / "frontend" / "index.html"), scenario],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_intake_dialog_callback_failure_is_reported_without_waiting():
    from types import SimpleNamespace

    failure = AssertionError('Synthetic receipt query returned 422')
    actions = []
    def fail_gate():
        raise failure
    def unexpected_wait(_):
        pytest.fail('callback failure must be reported before waiting for another dialog')
    page = SimpleNamespace(on=lambda *_: None, wait_for_timeout=unexpected_wait)
    dialog = SimpleNamespace(message='台帳との差分候補があります', accept=lambda: actions.append('accept'), dismiss=lambda: actions.append('dismiss'))
    journey = _PromptJourney(page, before_receipt=fail_gate)
    journey.answer(dialog)
    with pytest.raises(AssertionError) as captured:
        journey.wait()
    assert captured.value is failure
    assert actions == ['dismiss']


def test_intake_browser_receipt_queries_match_real_api(tmp_path):
    """Run the browser's exact seed and receipt helper against the real API, without Chromium."""
    root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        'PYTHONPATH': os.pathsep.join((str(root / 'backend'), str(root / 'backend' / 'tests'))),
        'FIRE_AI_DATABASE_URL': 'sqlite+pysqlite:///' + str(tmp_path / 'api-contract.db'),
        'FIRE_AI_STORAGE_ROOT': str(tmp_path / 'storage'),
        'FIRE_AI_PRODUCTION_MODE': 'false',
    }
    env.pop('FIRE_AI_TENANT_ID', None)
    contract = r'''
from types import SimpleNamespace
from fastapi.testclient import TestClient
from test_intake_browser import _selected_submissions, SOURCE_BYTES, PASSWORD, SELECTED_NAME, OTHER_NAME
with TestClient(app) as client:
    response = client.post('/auth/login', json={'username': 'intake-operator', 'password': PASSWORD})
    assert response.status_code == 200, response.text
    missing = client.get('/submissions')
    assert missing.status_code == 422, missing.text
    assert missing.json()['detail'][0]['loc'] == ['query', 'building_id']
    facilities = client.get('/facilities').json()['items']
    selected = next(row for row in facilities if row['name'] == SELECTED_NAME)
    other = next(row for row in facilities if row['name'] == OTHER_NAME)
    queries = []
    def get(url):
        queries.append(url)
        response = client.get(url)
        return SimpleNamespace(status=response.status_code, text=lambda: response.text, json=response.json)
    page = SimpleNamespace(request=SimpleNamespace(get=get))
    def receipts():
        queries.clear()
        rows = _selected_submissions(page, '', selected, other)
        assert queries == ['/submissions?building_id=' + selected['building_id'], '/submissions?building_id=' + other['building_id']]
        return rows
    assert receipts() == []
    def create_receipt(facility):
        upload = client.post('/documents/upload', files={'file': ('synthetic-intake.txt', SOURCE_BYTES, 'text/plain')}, data={'document_type': 'submission_source'})
        assert upload.status_code == 201, upload.text
        response = client.post('/submissions', json={'building_id': facility['building_id'], 'submission_type_code': 'equipment_inspection_report', 'document_ids': [upload.json()['document_id']], 'official_number': '5402'})
        assert response.status_code == 201, response.text
        return response.json()
    first = create_receipt(selected)
    assert [row['submission_id'] for row in receipts()] == [first['submission_id']]
    second = create_receipt(selected)
    assert {row['submission_id'] for row in receipts()} == {first['submission_id'], second['submission_id']}, 'duplicate receipts must remain visible to browser count assertions'
    unexpected = create_receipt(other)
    try:
        receipts()
    except AssertionError as exc:
        assert 'unselected facility has an unexpected receipt' in str(exc)
        assert unexpected['submission_id'] in str(exc)
    else:
        raise AssertionError('an orphan receipt on the unselected facility escaped detection')
'''
    result = subprocess.run([sys.executable, '-c', INTAKE_SEED + contract], cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
