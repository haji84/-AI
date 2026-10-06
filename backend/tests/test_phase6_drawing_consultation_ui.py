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



def test_phase6_annotation_editing_area_and_zone_tools_are_wired():
    html = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "index.html"
    ).read_text(encoding="utf-8")

    required_fragments = [
        "beginDrawingVertexDrag(",
        "drawingOverlayPointerMove(",
        "addDrawingVertex()",
        "removeDrawingVertex()",
        "applySelectedDrawingMeta()",
        "2点で縮尺校正",
        "startDrawingCalibration()",
        "reference_length_m",
        "meters_per_pixel",
        "drawingPolygonAreaPx2(",
        "drawingMetricLabel(",
        "区画追加",
        '<option value="zone">任意区画</option>',
        "㎡",
    ]
    missing = [x for x in required_fragments if x not in html]
    assert not missing, f"Annotation edit/area wiring missing: {missing}"


def test_phase6_annotation_overlay_has_pointer_drag_handlers():
    html = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert 'onpointermove="drawingOverlayPointerMove(event)"' in html
    assert 'onpointerup="endDrawingVertexDrag(event)"' in html
    assert 'class="drawingVertexHandle"' in html



def test_phase6_reference_draft_import_ui_is_wired_to_editable_annotation():
    html = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "index.html"
    ).read_text(encoding="utf-8")

    required_fragments = [
        "Reference Draft JSONを読み込む",
        "別Reference Draftを読み込む",
        'id="drawingReferenceImportFile"',
        "importDrawingReferenceDraftFile(event)",
        "chooseDrawingReferenceDraft()",
        "/annotations/import-reference",
        "JSON.parse(text)",
        "state.drawingEditElementIndex=null",
        "state.drawingSelectedVertexIndex=null",
        "原本SHA-256一致が必須",
    ]
    missing = [x for x in required_fragments if x not in html]
    assert not missing, f"Reference Draft import UI wiring missing: {missing}"



def test_phase6_drawing_workspace_shows_baseline_readiness():
    html = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "index.html"
    ).read_text(encoding="utf-8")

    required_fragments = [
        "/baseline-readiness",
        "drawingBaselineReadiness",
        "drawingBaselineReadinessHtml(",
        "初回Baseline Readiness",
        "Geometry ",
        "Human Reference",
        "AI Hypothesis",
        "面積校正",
    ]
    missing = [x for x in required_fragments if x not in html]
    assert not missing, f"Baseline readiness UI wiring missing: {missing}"



def test_phase6_workspace_runs_in_app_baseline():
    html = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "index.html"
    ).read_text(encoding="utf-8")

    required_fragments = [
        "/baseline-run",
        "runDrawingBaselineFromWorkspace(",
        "drawingBaselineRunHtml(",
        "この図面でBaseline実行",
        "Geometry F1",
        "mean IoU",
        "Benchmark採用は別のHuman Review Gate",
    ]
    missing = [x for x in required_fragments if x not in html]
    assert not missing, f"In-app Baseline UI wiring missing: {missing}"
