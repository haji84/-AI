from pathlib import Path


def _html() -> str:
    return (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "index.html"
    ).read_text(encoding="utf-8")


def test_phase6_annotation_boundary_snapping_is_wired_for_drag_and_new_points():
    html = _html()
    required = [
        "drawingSnapEnabled:true",
        "drawingSnapTarget:null",
        "function drawingSnapThreshold(svg)",
        "function drawingProjectPointToSegment(point,a,b)",
        "function drawingSnapPoint(point,svg,excludeElementIndex=null)",
        "drawingSnapPoint(raw,svg,state.drawingEditElementIndex)",
        "drawingSnapPoint(raw,svg,null)",
        "境界スナップ",
        "表示上10px以内",
        "snap '+esc(s.type)",
    ]
    missing = [x for x in required if x not in html]
    assert not missing, f"Annotation snapping wiring missing: {missing}"


def test_phase6_annotation_snapping_can_be_disabled_and_clears_transient_target():
    html = _html()

    assert "function toggleDrawingSnap()" in html
    assert "state.drawingSnapEnabled=!state.drawingSnapEnabled" in html
    assert "if(!state.drawingSnapEnabled)return {point,target:null}" in html
    assert "state.drawingDragVertexIndex=null;state.drawingDragPointerId=null;state.drawingSnapTarget=null" in html
    assert "state.drawingDrawActive=false;state.drawingDrawPoints=[];state.drawingSnapTarget=null" in html
