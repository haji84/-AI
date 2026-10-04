-- Emergency reporting module foundation (PostgreSQL)
-- Stores normalized source rows and leaves report layouts as derived output.

CREATE TABLE IF NOT EXISTS emergency_import_batches (
  batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  import_run_id uuid REFERENCES import_runs(import_run_id),
  target_period text,
  station_scope text,
  source_system text NOT NULL DEFAULT 'legacy_csv',
  status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS emergency_cases (
  emergency_case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_case_key text NOT NULL UNIQUE,
  call_month text,
  station_code text,
  dispatch_number text,
  ambulance_code text,
  call_date date,
  call_time time,
  dispatch_time time,
  scene_arrival_time time,
  leave_scene_time time,
  return_station_time time,
  incident_area_code text,
  incident_address text,
  activity_type text,
  incident_type text,
  incident_place text,
  dispatch_vehicle text,
  command_text text,
  cpr_wishes_none text,
  source_batch_id uuid REFERENCES emergency_import_batches(batch_id),
  raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_emergency_cases_period_station ON emergency_cases(call_month, station_code);
CREATE INDEX IF NOT EXISTS idx_emergency_cases_dispatch ON emergency_cases(station_code, dispatch_number);

CREATE TABLE IF NOT EXISTS emergency_patients (
  emergency_patient_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  emergency_case_id uuid NOT NULL REFERENCES emergency_cases(emergency_case_id) ON DELETE CASCADE,
  patient_number integer NOT NULL,
  sex text,
  age integer,
  age_class text,
  residence_class text,
  hospital_code text,
  hospital_category text,
  department_code text,
  severity_code text,
  injury_class_major text,
  injury_class_middle text,
  injury_class_minor text,
  resuscitation_code text,
  first_aid_flag text,
  condition_text text,
  diagnosis_text text,
  symptoms_text text,
  medical_history_text text,
  other_information_text text,
  team_urgency text,
  source_batch_id uuid REFERENCES emergency_import_batches(batch_id),
  raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(emergency_case_id, patient_number)
);
CREATE INDEX IF NOT EXISTS idx_emergency_patients_hospital ON emergency_patients(hospital_code);
CREATE INDEX IF NOT EXISTS idx_emergency_patients_severity ON emergency_patients(severity_code);

CREATE TABLE IF NOT EXISTS emergency_crew_assignments (
  crew_assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  emergency_case_id uuid NOT NULL REFERENCES emergency_cases(emergency_case_id) ON DELETE CASCADE,
  source_record_key text NOT NULL UNIQUE,
  source_row_no integer,
  source_identity_status text NOT NULL DEFAULT 'complete',
  crew_role text NOT NULL,
  source_crew_code text,
  employee_id uuid REFERENCES employees(employee_id),
  qualification text,
  rank_name text,
  source_batch_id uuid REFERENCES emergency_import_batches(batch_id),
  raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_emergency_crew_employee ON emergency_crew_assignments(employee_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_emergency_crew_complete_identity
  ON emergency_crew_assignments(emergency_case_id, crew_role, source_crew_code)
  WHERE source_crew_code IS NOT NULL AND source_crew_code <> '';

CREATE TABLE IF NOT EXISTS emergency_hospital_master (
  hospital_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_key text UNIQUE,
  display_name text NOT NULL,
  category text,
  aliases text[] NOT NULL DEFAULT ARRAY[]::text[],
  active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS emergency_severity_master (
  severity_code text PRIMARY KEY,
  display_name text NOT NULL,
  output_order integer,
  include_in_reports boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS emergency_clinical_flags (
  flag_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  emergency_patient_id uuid NOT NULL REFERENCES emergency_patients(emergency_patient_id) ON DELETE CASCADE,
  flag_type text NOT NULL,
  flag_value text NOT NULL,
  derivation_method text NOT NULL CHECK (derivation_method IN ('explicit','rule','ai','manual')),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence numeric,
  review_status text NOT NULL DEFAULT 'unreviewed',
  confirmed_by uuid REFERENCES app_users(user_id),
  confirmed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_emergency_flags_type ON emergency_clinical_flags(flag_type, review_status);

CREATE TABLE IF NOT EXISTS emergency_report_runs (
  report_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_type text NOT NULL,
  period_start date,
  period_end date,
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  generated_by uuid REFERENCES app_users(user_id),
  generated_at timestamptz NOT NULL DEFAULT now(),
  source_batch_ids uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
  result_storage_path text,
  result_sha256 text,
  row_count integer,
  status text NOT NULL DEFAULT 'generated'
);

-- Generic views proving the legacy workbook outputs can be derived from normalized data.
CREATE OR REPLACE VIEW v_emergency_hospital_severity_counts AS
SELECT
  c.call_month,
  c.station_code,
  p.hospital_code,
  p.severity_code,
  count(*) AS patient_count
FROM emergency_patients p
JOIN emergency_cases c ON c.emergency_case_id = p.emergency_case_id
GROUP BY c.call_month, c.station_code, p.hospital_code, p.severity_code;

CREATE OR REPLACE VIEW v_emergency_crew_dispatch_counts AS
SELECT
  c.call_month,
  c.station_code,
  ca.employee_id,
  ca.source_crew_code,
  count(DISTINCT c.emergency_case_id) AS dispatch_count
FROM emergency_crew_assignments ca
JOIN emergency_cases c ON c.emergency_case_id = ca.emergency_case_id
GROUP BY c.call_month, c.station_code, ca.employee_id, ca.source_crew_code;