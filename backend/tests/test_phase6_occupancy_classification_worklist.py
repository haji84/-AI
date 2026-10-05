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


def test_phase6_occupancy_catalog_flattens_classification_entries():
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
    worklist["source_path"] = "test.xml"
    catalog = mod.build_catalog(worklist)

    assert catalog["classification_entry_count"] == 2
    assert catalog["entries"][0]["classification_code"] == "（三）イ"
    assert catalog["entries"][1]["classification_code"] == "（三）ロ"
    assert catalog["entries"][1]["classification_label"] == "飲食店"
    assert catalog["entries"][1]["row_provision_key"] == worklist["rows"][0]["row_provision_key"]
    assert catalog["entries"][1]["proposed_conditions"] == {}
    assert catalog["entries"][1]["proposed_outcome"]["classification_code"] == "（三）ロ"
    assert catalog["policy"]["human_review_required"] is True


def test_phase6_occupancy_worklist_shape_guard_detects_unreviewed_legal_change():
    mod = _mod()
    bad = {
        "row_count": 21,
        "classification_entry_count": 35,
        "rows": [],
    }
    try:
        mod.validate_expected_shape(bad)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "row count changed" in str(exc)



def test_phase6_occupancy_worklist_reads_egov_bulk_zip(tmp_path):
    import csv
    import io
    import zipfile

    mod = _mod()
    law_id = "336CO0000000037"
    folder = f"{law_id}_20251001_507CO0000000085"
    xml_name = f"{folder}/{folder}.xml"
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

    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow([
        "法令種別","法令番号","法令名","法令名読み","旧法令名","公布日",
        "改正法令名","改正法令番号","改正法令公布日","施行日","施行日備考",
        "法令ID","本文URL","未施行"
    ])
    writer.writerow([
        "政令","昭和三十六年政令第三十七号","消防法施行令","しょうぼうほうしこうれい",
        "","","","","","2025-10-01","",law_id,"https://example.invalid",""
    ])

    archive = tmp_path / "egov-all.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("all_law_list.csv", csv_buf.getvalue().encode("utf-8-sig"))
        z.writestr(xml_name, xml)

    source, data = mod.find_target_xml(tmp_path)

    assert str(source).startswith(str(archive))
    assert "!/" in str(source)
    assert xml_name in str(source)
    result = mod.extract_schedule_one(data)
    assert result["law_title"] == "消防法施行令"
    assert result["classification_entry_count"] == 2
    assert result["rows"][0]["classification_entries"][1]["classification_code"] == "（三）ロ"
