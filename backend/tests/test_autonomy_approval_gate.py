"""Synthetic tests for exact-PR chat authorization evidence, not independent review."""
from datetime import datetime, timezone, timedelta
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "scripts/autonomy/approval_gate.py"
spec = importlib.util.spec_from_file_location("aios_approval_gate", PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

HEAD = "a" * 40
NOW = datetime(2026, 10, 13, 1, 0, 0, tzinfo=timezone.utc)
CREATED = "2026-10-13T00:00:00Z"
EXPIRES = "2026-10-13T02:00:00Z"
COMMAND = (f"AIOS_APPROVE\nPR=135\nHEAD={HEAD}\n"
           f"EXPIRES={EXPIRES}\nNONCE=distinct-token-123456")


def fixture():
    event = {
        "action": "created",
        "repository": {"full_name": "haji84/-AI"},
        "sender": {"login": "haji84"},
        "issue": {"number": 135, "pull_request": {"url": "https://example.invalid/pr"}},
        "comment": {"id": 123456, "body": COMMAND, "created_at": CREATED,
                    "user": {"login": "haji84", "type": "User"},
                    "author_association": "OWNER"},
    }
    pr = {"number": 135, "state": "open", "merged_at": None,
          "head": {"sha": HEAD}, "base": {"ref": "main"}}
    return event, pr


def test_exact_owner_comment_produces_no_merge_authority():
    event, pr = fixture()
    receipt = gate.inspect_event(event, pr, now=NOW)
    assert receipt["decision"] == "chat_authorized_for_bounded_next_step"
    assert receipt["head"] == HEAD
    assert receipt["comment_id"] == 123456
    assert receipt["independent_review_satisfied"] is False
    assert receipt["auto_merge_permitted"] is False
    assert receipt["production_change_permitted"] is False
    assert "distinct-token" not in str(receipt)


@pytest.mark.parametrize("change", [
    lambda e, p: e["comment"]["user"].update(login="attacker"),
    lambda e, p: e["sender"].update(login="attacker"),
    lambda e, p: e["comment"].update(author_association="CONTRIBUTOR"),
    lambda e, p: e["repository"].update(full_name="attacker/clone"),
    lambda e, p: e["issue"].pop("pull_request"),
    lambda e, p: e.update(action="edited"),
    lambda e, p: p["head"].update(sha="b" * 40),
    lambda e, p: p["base"].update(ref="develop"),
    lambda e, p: p.update(state="closed"),
    lambda e, p: e["comment"].update(id=0),
    lambda e, p: e["comment"].update(body="承認"),
    lambda e, p: e["comment"].update(body=COMMAND + "\ncommand=MERGE"),
])
def test_bad_approval_never_matches(change):
    event, pr = fixture()
    change(event, pr)
    with pytest.raises(gate.ApprovalError):
        gate.inspect_event(event, pr, now=NOW)


def test_expired_or_future_comment_refused():
    event, pr = fixture()
    with pytest.raises(gate.ApprovalError):
        gate.inspect_event(event, pr, now=NOW + timedelta(hours=3))
    with pytest.raises(gate.ApprovalError):
        gate.inspect_event(event, pr, now=NOW - timedelta(hours=2))


def test_overlong_approval_expiry_refused():
    event, pr = fixture()
    event["comment"]["body"] = COMMAND.replace(EXPIRES, "2026-10-15T02:00:00Z")
    with pytest.raises(gate.ApprovalError):
        gate.inspect_event(event, pr, now=NOW)


def test_invalid_clock_refused():
    event, pr = fixture()
    event["comment"]["body"] = COMMAND.replace(EXPIRES, "2026-10-13T99:00:00Z")
    with pytest.raises(gate.ApprovalError):
        gate.inspect_event(event, pr, now=NOW)
