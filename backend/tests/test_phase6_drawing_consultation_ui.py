from pathlib import Path


def test_phase6_drawing_consultation_workspace_is_wired_to_human_gates():
    html = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "index.html"
    ).read_text(encoding="utf-8")

    required_fragments = [
        'id="drawingWorkspaceModal"',
        "Human Annotation・設備相談",
        "openDrawingWorkspace(",
        "drawingOverlayClick(event)",
        "finishDrawingRoom()",
        "/annotations/seed",
        "/drawing-annotations/",
        "/consultations",
        "/classify",
        "/classification/confirm",
        "/equipment/evaluate",
        "/response",
        "/response/review",
        "/benchmark-hypothesis",
        "/benchmark-reference",
        "AI Hypothesis JSON",
        "Human Reference JSON",
        "drawingCoverageHtml(r.coverage||{})",
        "r.equipment_actions||[]",
        "review_stale",
    ]
    missing = [x for x in required_fragments if x not in html]
    assert not missing, f"Phase 6 drawing consultation UI wiring missing: {missing}"


def test_phase6_drawing_consultation_workspace_supports_pdf_page_annotation():
    html = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert "/preview-info" in html
    assert "/pages/" in html
    assert "/preview" in html
    assert "changeDrawingWorkspacePage" in html
    assert "pageCount>1" in html
    assert "page_no:page" in html
    assert "Number(x.page_no||1)!==currentPage" in html
    assert "AI解析結果は正解データではありません" in html
    assert "Human確認済みにする" in html
