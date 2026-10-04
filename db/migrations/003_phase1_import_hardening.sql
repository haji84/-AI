-- Phase 1 import hardening and separated emergency permissions.

CREATE TABLE IF NOT EXISTS legacy_facility_source_rows (
  source_row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_file_id uuid NOT NULL REFERENCES source_files(source_file_id),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  legacy_internal_key text NOT NULL,
  source_sheet text NOT NULL DEFAULT 'DB保存',
  source_row_no integer NOT NULL,
  raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(source_file_id, source_sheet, source_row_no)
);
CREATE INDEX IF NOT EXISTS idx_legacy_facility_source_building ON legacy_facility_source_rows(building_id);
CREATE INDEX IF NOT EXISTS idx_legacy_facility_source_key ON legacy_facility_source_rows(legacy_internal_key);

INSERT INTO permissions(code, description) VALUES
 ('facility.import','旧査察台帳データ取込'),
 ('emergency.case.read','救急事案個票参照'),
 ('emergency.patient.read','救急傷病者個票参照'),
 ('emergency.crew.read','救急出動隊員個票参照'),
 ('system.backup','バックアップ・復元管理')
ON CONFLICT (code) DO NOTHING;