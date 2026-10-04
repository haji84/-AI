from __future__ import annotations

import hashlib
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_RE = re.compile(r"([A-Z]+)(\d+)$")


@dataclass(frozen=True)
class SheetRow:
    row_no: int
    by_column: dict[str, str]
    by_header: dict[str, str]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for si in root.findall(f"{{{NS}}}si"):
        values.append("".join((t.text or "") for t in si.iter(f"{{{NS}}}t")))
    return values


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{NS}}}is")
        if inline is None:
            return ""
        return "".join((t.text or "") for t in inline.iter(f"{{{NS}}}t"))
    value = cell.find(f"{{{NS}}}v")
    if value is None:
        return ""
    raw = value.text or ""
    if cell_type == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return raw
    if cell_type == "b":
        return "1" if raw == "1" else "0"
    return raw


def _sheet_path(z: zipfile.ZipFile, sheet_name: str) -> str:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {r.attrib["Id"]: r.attrib["Target"] for r in rels.findall(f"{{{PKG}}}Relationship")}
    sheets = wb.find(f"{{{NS}}}sheets")
    if sheets is None:
        raise ValueError("workbook has no sheets")
    for sheet in sheets:
        if sheet.attrib.get("name") != sheet_name:
            continue
        rel_id = sheet.attrib[f"{{{RNS}}}id"]
        target = relmap[rel_id].lstrip("/")
        if target.startswith("xl/"):
            return target
        return f"xl/{target}"
    raise ValueError(f"sheet not found: {sheet_name}")


def read_sheet(path: Path, sheet_name: str, header_row: int = 1) -> tuple[dict[str, str], list[SheetRow]]:
    """Read cached OOXML values without Excel/VBA.

    Returns a column->header map plus rows. Duplicate/blank headers are preserved in
    by_column; by_header uses the first non-blank occurrence only. Importers that need
    lossless source preservation must persist by_column.
    """
    with zipfile.ZipFile(path) as z:
        shared = _shared_strings(z)
        root = ET.fromstring(z.read(_sheet_path(z, sheet_name)))
        cells_by_row: dict[int, dict[str, str]] = {}
        for cell in root.iter(f"{{{NS}}}c"):
            ref = cell.attrib.get("r", "")
            m = _CELL_RE.match(ref)
            if not m:
                continue
            col, row_text = m.groups()
            row_no = int(row_text)
            value = _cell_value(cell, shared)
            if value != "":
                cells_by_row.setdefault(row_no, {})[col] = value

    headers = {col: value.strip() for col, value in cells_by_row.get(header_row, {}).items()}
    rows: list[SheetRow] = []
    for row_no in sorted(k for k in cells_by_row if k > header_row):
        by_col = cells_by_row[row_no]
        if not by_col:
            continue
        by_header: dict[str, str] = {}
        for col, value in by_col.items():
            header = headers.get(col, "").strip()
            if header and header not in by_header:
                by_header[header] = value
        rows.append(SheetRow(row_no=row_no, by_column=dict(by_col), by_header=by_header))
    return headers, rows
