"""Deterministic per-PR changed-line IDs for constrained local AI reviews.

Model sees numbered, bounded diff hunks. It selects IDs; only trusted code
reconstructs exact source lines. An ID is location evidence, NOT risk proof.
"""
from __future__ import annotations


class AnchorStop(ValueError):
    pass


def build_line_catalog(files):
    if not isinstance(files, list) or not 1 <= len(files) <= 40:
        raise AnchorStop("unbounded changed-file inventory")
    mapping, annotated = {}, []
    for file_index, item in enumerate(files, 1):
        if not isinstance(item, dict):
            raise AnchorStop("invalid changed-file entry")
        path, patch = item.get("path"), item.get("patch")
        if (not isinstance(path, str) or not path
                or not isinstance(patch, str) or len(patch) > 100_000
                or path in mapping):
            raise AnchorStop("duplicate or missing source patch")
        paths = {}
        lines = []
        in_hunk = False
        for raw in patch.splitlines():
            if raw.startswith("@@ "):
                in_hunk = True
                lines.append(raw)
                continue
            if (in_hunk and 2 <= len(raw) <= 1000
                    and ((raw.startswith("+") and not raw.startswith("+++"))
                         or (raw.startswith("-") and not raw.startswith("---")))):
                anchor = f"F{file_index:02d}L{len(paths) + 1:04d}"
                paths[anchor] = raw
                lines.append(f"[{anchor}] {raw}")
            else:
                lines.append(raw)
        mapping[path] = paths
        annotated.append({"path": path, "annotated_patch": "\n".join(lines)})
    return mapping, annotated


def model_view(snapshot):
    if not isinstance(snapshot, dict):
        raise AnchorStop("invalid snapshot")
    mapping, annotated = build_line_catalog(snapshot.get("files"))
    if not any(mapping.values()):
        raise AnchorStop("no changed lines to inspect")
    return {
        "repo": snapshot["repo"], "pr": snapshot["pr"],
        "head": snapshot["head"], "base": snapshot["base"],
        "ci": snapshot["ci"], "rules": snapshot["rules"],
        "specification_excerpt": snapshot["specification_excerpt"],
        "files": annotated,
    }


def resolve_anchor(mapping, path, anchor_id):
    if (not isinstance(path, str) or not isinstance(anchor_id, str)
            or anchor_id not in mapping.get(path, {})):
        raise AnchorStop("finding has no valid changed-line anchor ID")
    return mapping[path][anchor_id]
