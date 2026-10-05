from __future__ import annotations

import importlib.util
from pathlib import Path


def _mod():
    script = Path(__file__).resolve().parents[2] / "scripts" / "build_occupancy_classification_worklist.py"
    spec = importlib.util.spec_from_file_location("build_occupancy_classification_worklist", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_phase6_occupancy_worklist_extracts_schedule_one_table_rows():
    mod = _mod()
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Law>
  <LawBody>
    <LawTitle>消防法施行令</LawTitle>
    <LawNum>昭和三十六年政令第三十七号</LawNum>
    <AppdxTable Num="1">
      <AppdxTableTitle>別表第一</AppdxTableTitle>
      <TableStruct>
        <Table>
          <TableRow>
            <TableColumn><Sentence>（一）</Sentence></TableColumn>
            <TableColumn>
              <Sentence Num="1">イ　テスト用途A</Sentence>
              <Sentence Num="2">ロ　テスト用途B</Sentence>
            </TableColumn>
          </TableRow>
          <TableRow>
            <TableColumn><Sentence>（二）</Sentence></TableColumn>
            <TableColumn><Sentence Num="1">テスト用途C</Sentence></TableColumn>
          </TableRow>
        </Table>
      </TableStruct>
    </AppdxTable>
  </LawBody>
</Law>
""".encode("utf-8")

    result = mod.extract_schedule_one(xml)

    assert result["law_title"] == "消防法施行令"
    assert result["law_number"] == "昭和三十六年政令第三十七号"
    assert result["target_appendix"] == "別表第一"
    assert result["row_count"] == 2
    assert result["classification_entry_count"] == 3
    assert result["rows"][0]["item_label"] == "（一）"
    assert len(result["rows"][0]["classification_entries"]) == 2
    assert result["rows"][0]["classification_entries"][0]["classification_code"] == "（一）イ"
    assert result["rows"][0]["classification_entries"][0]["classification_label"] == "テスト用途A"
    assert result["rows"][0]["classification_entries"][1]["classification_code"] == "（一）ロ"
    assert result["rows"][1]["classification_entries"][0]["classification_code"] == "（二）"
    assert result["rows"][0]["classification_entries"][0]["proposed_outcome"]["decision"] == "classification_candidate"
    assert result["rows"][0]["classification_entries"][0]["proposed_conditions"] == {}
    assert result["rows"][0]["classification_entries"][0]["conditions_authoring_status"] == "required"
    assert len(result["rows"][0]["classification_entries"][0]["entry_sha256"]) == 64
    assert len(result["rows"][0]["row_sha256"]) == 64
    assert result["policy"]["auto_approve"] is False
    assert result["policy"]["auto_conditions"] is False
    assert result["policy"]["classification_identity_from_official_table"] is True

from __future__ import annotations

import importlib.util
from pathlib import Path


def _mod():
    script = Path(__file__).resolve().parents[2] / "scripts" / "build_occupancy_classification_worklist.py"
    spec = importlib.util.spec_from_file_location("build_occupancy_classification_worklist", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_phase6_occupancy_worklist_extracts_schedule_one_table_rows():
    mod = _mod()
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Law>
  <LawBody>
    <LawTitle>消防法施行令</LawTitle>
    <AppdxTable Num="1">
      <AppdxTableTitle>別表第一（第一条の二関係）</AppdxTableTitle>
      <TableStruct>
        <Table>
          <TableRow>
            <TableColumn><Sentence>項</Sentence></TableColumn>
            <TableColumn><Sentence>防火対象物</Sentence></TableColumn>
          </TableRow>
          <TableRow>
            <TableColumn><Sentence>（一）</Sentence></TableColumn>
            <TableColumn><Sentence>テスト用途A</Sentence></TableColumn>
          </TableRow>
          <TableRow>
            <TableColumn><Sentence>（二）</Sentence></TableColumn>
            <TableColumn><Sentence>テスト用途B</Sentence></TableColumn>
          </TableRow>
        </Table>
      </TableStruct>
    </AppdxTable>
  </LawBody>
</Law>
""".encode("utf-8")

    result = mod.extract_schedule_one(xml)

    assert result["law_title"] == "消防法施行令"
    assert result["target_appendix"].startswith("別表第一")
    assert result["row_count"] == 3
    assert result["classification_entry_count"] == 7
    assert result["rows"][0]["cells"] == ["項", "防火対象物"]
    assert result["rows"][1]["cells"] == ["（一）", "テスト用途A"]
    assert result["rows"][1]["domain"] == "occupancy_classification"
    assert len(result["rows"][1]["classification_entries"]) == 4
    assert result["rows"][1]["classification_entries"][0]["classification_code"] == "（一）イ"
    assert result["rows"][1]["classification_entries"][0]["proposed_outcome"]["decision"] == "classification_candidate"
    assert result["rows"][1]["classification_entries"][0]["proposed_conditions"] == {}
    assert result["rows"][2]["classification_entries"][1]["classification_code"] == "（二）ロ"
    assert result["rows"][1]["human_review_status"] == "pending"
    assert result["rows"][1]["classification_entries"][0]["conditions_authoring_status"] == "required"
    assert len(result["rows"][1]["row_sha256"]) == 64
    assert result["policy"]["auto_approve"] is False
    assert result["policy"]["auto_conditions"] is False
    assert result["policy"]["classification_identity_from_official_table"] is True


def test_phase6_occupancy_worklist_rejects_wrong_law_and_missing_schedule():
    mod = _mod()
    wrong = """<Law><LawBody><LawTitle>別の政令</LawTitle></LawBody></Law>""".encode("utf-8")
    try:
        mod.extract_schedule_one(wrong)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unexpected law title" in str(exc)

    missing = """<Law><LawBody><LawTitle>消防法施行令</LawTitle></LawBody></Law>""".encode("utf-8")
    try:
        mod.extract_schedule_one(missing)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "AppdxTable" in str(exc)



def test_phase6_schedule_one_worklist_key_matches_citable_table_row_provision():
    from app.legal_structure import PARSER_VERSION, parse_egov_xml

    mod = _mod()
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Law>
  <LawBody>
    <LawTitle>消防法施行令</LawTitle>
    <LawNum>昭和三十六年政令第三十七号</LawNum>
    <AppdxTable Num="1">
      <AppdxTableTitle>別表第一</AppdxTableTitle>
      <TableStruct>
        <Table>
          <TableRow>
            <TableColumn><Sentence>（三）</Sentence></TableColumn>
            <TableColumn>
              <Sentence Num="1">イ　待合、料理店その他これらに類するもの</Sentence>
              <Sentence Num="2">ロ　飲食店</Sentence>
            </TableColumn>
          </TableRow>
        </Table>
      </TableStruct>
    </AppdxTable>
  </LawBody>
</Law>
""".encode("utf-8")

    worklist = mod.extract_schedule_one(xml)
    provisions = parse_egov_xml(xml)
    table_rows = [x for x in provisions if x.provision_type == "table_row"]

    assert PARSER_VERSION == "legal-structure-v2"
    assert len(table_rows) == 1
    assert worklist["rows"][0]["row_provision_key"] == table_rows[0].provision_key
    assert table_rows[0].display_label is None
    assert "（三）" in table_rows[0].body_text
    assert "飲食店" in table_rows[0].body_text
