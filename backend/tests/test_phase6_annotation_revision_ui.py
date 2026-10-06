from pathlib import Path


def _html() -> str:
    return (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "index.html"
    ).read_text(encoding="utf-8")


def test_phase6_reviewed_annotation_revision_action_is_wired():
    html = _html()

    required = [
        "async function reviseDrawingAnnotation()",
        "/revise",
        "expected_version:ann.version",
        "修正版Draftを作る",
        "現在のHuman確認済みAnnotationを残したまま",
        "drawingResetHistory();",
    ]
    missing = [x for x in required if x not in html]
    assert not missing, f"Annotation revision UI wiring missing: {missing}"


def test_phase6_annotation_revision_provenance_is_visible_in_workspace():
    html = _html()

    required = [
        "revision_history",
        "Revision '+esc(revisionHistory.length)",
        "source_annotation_id",
    ]
    missing = [x for x in required if x not in html]
    assert not missing, f"Annotation revision provenance UI missing: {missing}"
