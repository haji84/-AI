from pathlib import Path


def _html() -> str:
    return (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "index.html"
    ).read_text(encoding="utf-8")


def test_phase6_annotation_undo_redo_tracks_all_persistent_edit_types():
    html = _html()

    required = [
        "drawingUndoStack:[]",
        "drawingRedoStack:[]",
        "drawingSavedSnapshotKey:null",
        "drawingHistoryLimit:50",
        "function drawingPushHistory(label)",
        "function drawingUndo()",
        "function drawingRedo()",
        "function drawingRefreshDirty()",
        "function drawingResetHistory()",
        "drawingPushHistory('区画情報変更')",
        "drawingPushHistory('頂点移動')",
        "drawingPushHistory('頂点追加')",
        "drawingPushHistory('頂点削除')",
        "drawingPushHistory('縮尺校正')",
        "drawingPushHistory('縮尺解除')",
        "drawingPushHistory('既知階面積登録')",
        "drawingPushHistory('既知階面積解除')",
        "drawingPushHistory('区画追加')",
        "drawingPushHistory('区画削除')",
    ]
    missing = [x for x in required if x not in html]
    assert not missing, f"Annotation Undo/Redo mutation wiring missing: {missing}"


def test_phase6_annotation_undo_redo_has_dirty_guard_and_save_checkpoint():
    html = _html()

    required = [
        "drawingDirty:false",
        "drawingConfirmDiscardChanges(",
        "未保存のHuman Annotation変更があります。閉じると破棄されます。",
        "Reference Draftを読み込むと現在の未保存変更は破棄されます。",
        "別の図面を開くと破棄されます。",
        "drawingResetHistory();",
        "window.addEventListener('beforeunload'",
        "state.drawingDirty",
    ]
    missing = [x for x in required if x not in html]
    assert not missing, f"Annotation dirty-state guard missing: {missing}"

    save_start = html.index("async function saveDrawingAnnotation")
    save_end = html.index("async function reviewDrawingAnnotation", save_start)
    save_block = html[save_start:save_end]
    assert "state.drawingAnnotation=row;" in save_block
    assert "drawingResetHistory();" in save_block


def test_phase6_annotation_undo_redo_keyboard_and_visible_controls_are_wired():
    html = _html()

    required = [
        "onclick=\"drawingUndo()\"",
        "onclick=\"drawingRedo()\"",
        ">元に戻す<",
        ">やり直す<",
        "未保存",
        "保存済み",
        "Ctrl/⌘+Z",
        "if(ev.shiftKey)drawingRedo();else drawingUndo();",
        "ev.key.toLowerCase()==='y'",
    ]
    missing = [x for x in required if x not in html]
    assert not missing, f"Annotation Undo/Redo UI wiring missing: {missing}"


def test_phase6_annotation_vertex_drag_creates_one_history_checkpoint_per_gesture():
    html = _html()

    assert "drawingDragHistoryPushed:false" in html
    assert "state.drawingDragHistoryPushed=false;" in html
    assert (
        "if(!state.drawingDragHistoryPushed){drawingPushHistory('頂点移動');"
        "state.drawingDragHistoryPushed=true}"
    ) in html
    assert "state.drawingDragVertexIndex=null;state.drawingDragPointerId=null;state.drawingSnapTarget=null" in html
    assert "state.drawingDragHistoryPushed=false;" in html


def test_phase6_annotation_switch_checks_unsaved_state_before_replacing_selection():
    html = _html()
    start = html.index("function selectDrawingAnnotation")
    end = html.index("function selectDrawingConsultation", start)
    block = html[start:end]

    guard_pos = block.index("drawingConfirmDiscardChanges()")
    assignment_pos = block.index("state.drawingAnnotation=(state.drawingAnnotations")
    assert guard_pos < assignment_pos
