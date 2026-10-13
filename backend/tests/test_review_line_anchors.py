"""Changed-line IDs stay pinned to snapshot path and source text."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/autonomy"))
import review_line_anchors as anchors


def sample():
    return [
        {"path": "a.py",
         "patch": "@@ -1 +1,2 @@\n-old = 1\n+new = 2\n+newer = 3"},
        {"path": ".github/workflows/ci.yml",
         "patch": "@@ -0,0 +1,2 @@\n+name: Test\n+on: push"},
    ]


def test_ids_are_path_bound_exact_and_deterministic():
    catalog, model_diff = anchors.build_line_catalog(sample())
    assert catalog["a.py"] == {
        "F01L0001": "-old = 1",
        "F01L0002": "+new = 2",
        "F01L0003": "+newer = 3",
    }
    assert catalog[".github/workflows/ci.yml"]["F02L0001"] == "+name: Test"
    assert "[F01L0002] +new = 2" in model_diff[0]["annotated_patch"]
    assert anchors.resolve_anchor(catalog, "a.py", "F01L0002") == "+new = 2"
    assert catalog == anchors.build_line_catalog(sample())[0]


def test_unknown_or_cross_file_id_fails_closed():
    catalog, _ = anchors.build_line_catalog(sample())
    for path, anchor_id in [
        ("a.py", "F02L0001"),
        ("a.py", "F01L9999"),
        ("wrong.py", "F01L0002"),
        ("a.py", "+new = 2"),
    ]:
        with pytest.raises(anchors.AnchorStop, match="anchor ID"):
            anchors.resolve_anchor(catalog, path, anchor_id)


def test_annotated_model_view_never_replaces_trusted_snapshot():
    original = {
        "repo": "test/repo", "pr": 133, "head": "a" * 40, "base": "b" * 40,
        "ci": {}, "rules": "rules", "specification_excerpt": "## 4. Synthetic",
        "files": sample(),
    }
    view = anchors.model_view(original)
    assert view["files"][0]["path"] == "a.py"
    assert "[F01L0002] +new = 2" in view["files"][0]["annotated_patch"]
    assert original["files"][0]["patch"].startswith("@@")
    assert "annotated_patch" not in original["files"][0]


def test_duplicate_paths_cannot_alias_anchors():
    same_path_twice = [sample()[0], sample()[0]]
    with pytest.raises(anchors.AnchorStop, match="duplicate"):
        anchors.build_line_catalog(same_path_twice)
