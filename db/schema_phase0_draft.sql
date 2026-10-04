-- 消防業務ローカルAI Phase 0 Target Schema Draft
-- PostgreSQL draft. 実装前に命名・権限・保持期間を再確認する。
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE facilities (
  building_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legacy_internal_key text UNIQUE,
  legacy_category_key text,
  legacy_serial_no text,
  legacy_global_serial text,
  name text NOT NULL,
  phone text,
  address text,
  zoning text,
  article8_partition text,
  structure text,
  above_ground_floors integer,
  basement_floors integer,
  building_area numeric,
  total_floor_area numeric,
  status text NOT NULL DEFAULT 'active',
  version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE facility_classifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  classification_code text NOT NULL,
  detail_1 text,
  detail_2 text,
  valid_from date,
  valid_to date
);

CREATE TABLE facility_contacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  contact_type text NOT NULL DEFAULT 'representative',
  name text,
  title text,
  address text,
  phone text,
  valid_from date,
  valid_to date
);

CREATE TABLE facility_floors (
  floor_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  floor_no integer NOT NULL,
  floor_label text,
  floor_area numeric,
  use_name text,
  occupancy_count integer,
  employee_count integer,
  windowless_status text,
  UNIQUE(building_id, floor_no)
);

CREATE TABLE facility_floor_materials (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  floor_id uuid NOT NULL REFERENCES facility_floors(floor_id),
  curtain_status text,
  carpet_status text,
  plywood_status text
);

CREATE TABLE equipment_types (
  equipment_type_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE
);

CREATE TABLE facility_equipment (
  equipment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  equipment_type_id uuid REFERENCES equipment_types(equipment_type_id),
  legacy_slot integer,
  installed_or_checked_at date,
  status text,
  notes text
);

CREATE TABLE facility_equipment_floors (
  equipment_id uuid NOT NULL REFERENCES facility_equipment(equipment_id),
  floor_id uuid NOT NULL REFERENCES facility_floors(floor_id),
  status text,
  PRIMARY KEY(equipment_id, floor_id)
);

CREATE TABLE equipment_inspection_reports (
  report_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  equipment_id uuid REFERENCES facility_equipment(equipment_id),
  report_type text,
  inspection_result text,
  inspected_at date,
  submitted_at date,
  next_due_at date,
  document_id uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE fire_management_assignments (
  assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  manager_name text,
  manager_title text,
  appointment_submitted_at date,
  fire_plan_submitted_at date,
  valid_from date,
  valid_to date
);

CREATE TABLE submission_types (
  submission_type_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text UNIQUE,
  name text NOT NULL,
  active boolean NOT NULL DEFAULT true
);

CREATE TABLE submissions (
  submission_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid REFERENCES facilities(building_id),
  submission_type_id uuid REFERENCES submission_types(submission_type_id),
  received_at timestamptz,
  submitted_at date,
  status text NOT NULL DEFAULT 'received',
  submitted_by text,
  reviewer_user_id uuid,
  version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE facility_regulated_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  item_name text,
  submitted_at date,
  inspected_at date,
  legacy_slot integer,
  notes text
);

CREATE TABLE inspections (
  inspection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  inspected_at timestamptz,
  inspection_type text,
  status text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE inspection_findings (
  finding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  inspection_id uuid NOT NULL REFERENCES inspections(inspection_id),
  category text,
  finding_text text NOT NULL,
  corrective_status text,
  completed_at date
);

CREATE TABLE guidance_records (
  guidance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  inspection_id uuid REFERENCES inspections(inspection_id),
  subject text,
  issued_at date,
  content text,
  legacy_slot integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE facility_notes (
  note_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  note_text text NOT NULL,
  legacy_line integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE documents (
  document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid REFERENCES facilities(building_id),
  storage_path text NOT NULL,
  original_filename text NOT NULL,
  sha256 text NOT NULL,
  mime_type text,
  document_type text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE document_versions (
  version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(document_id),
  version_no integer NOT NULL,
  derived_from uuid REFERENCES document_versions(version_id),
  storage_path text NOT NULL,
  sha256 text NOT NULL,
  version_type text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(document_id, version_no)
);

CREATE TABLE fire_cases (
  fire_case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid REFERENCES facilities(building_id),
  occurred_at timestamptz,
  discovered_at timestamptz,
  reported_at timestamptz,
  extinguished_at timestamptz,
  status text NOT NULL DEFAULT 'open',
  summary text,
  version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE fire_case_legacy_notes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id),
  legacy_line integer,
  note_text text NOT NULL
);

CREATE TABLE fire_case_timeline (
  timeline_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_case_id uuid NOT NULL REFERENCES fire_cases(fire_case_id),
  event_at timestamptz,
  event_text text NOT NULL,
  source_type text,
  source_id uuid,
  confidence numeric
);

CREATE TABLE photos (
  photo_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_case_id uuid REFERENCES fire_cases(fire_case_id),
  building_id uuid REFERENCES facilities(building_id),
  storage_path text NOT NULL,
  sha256 text NOT NULL,
  captured_at timestamptz,
  original_filename text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audio_files (
  audio_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_case_id uuid REFERENCES fire_cases(fire_case_id),
  storage_path text NOT NULL,
  sha256 text NOT NULL,
  original_filename text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transcripts (
  transcript_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  audio_id uuid NOT NULL REFERENCES audio_files(audio_id),
  start_ms bigint,
  end_ms bigint,
  speaker_label text,
  transcript_text text NOT NULL,
  confidence numeric,
  model_version text
);

CREATE TABLE statements (
  statement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_case_id uuid NOT NULL REFERENCES fire_cases(fire_case_id),
  transcript_id uuid REFERENCES transcripts(transcript_id),
  person_label text,
  statement_text text NOT NULL,
  uncertainty_text text,
  status text NOT NULL DEFAULT 'draft',
  confirmed_by uuid,
  confirmed_at timestamptz
);

CREATE TABLE legal_rules (
  rule_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_code text NOT NULL,
  rule_name text NOT NULL
);

CREATE TABLE legal_rule_versions (
  rule_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_id uuid NOT NULL REFERENCES legal_rules(rule_id),
  version_no integer NOT NULL,
  effective_from date NOT NULL,
  effective_to date,
  rule_payload jsonb NOT NULL,
  source_reference text,
  approved_at timestamptz,
  UNIQUE(rule_id, version_no)
);

CREATE TABLE ai_models (
  ai_model_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  capability text NOT NULL,
  version text NOT NULL,
  role text NOT NULL CHECK (role IN ('champion','candidate','retired')),
  metrics jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_results (
  ai_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  capability text NOT NULL,
  model_version text NOT NULL,
  source_type text NOT NULL,
  source_id uuid,
  result_payload jsonb NOT NULL,
  confidence numeric,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_feedback (
  feedback_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ai_result_id uuid NOT NULL REFERENCES ai_results(ai_result_id),
  feedback_type text NOT NULL,
  corrected_payload jsonb,
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_learning_data (
  learning_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  capability text NOT NULL,
  source_feedback_id uuid REFERENCES ai_feedback(feedback_id),
  training_payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_tasks (
  task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid REFERENCES facilities(building_id),
  fire_case_id uuid REFERENCES fire_cases(fire_case_id),
  task_type text NOT NULL,
  severity text,
  reason text,
  evidence jsonb,
  status text NOT NULL DEFAULT 'open',
  assigned_to uuid,
  due_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_logs (
  audit_id bigserial PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  user_id uuid,
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id uuid,
  before_data jsonb,
  after_data jsonb,
  ai_used boolean NOT NULL DEFAULT false,
  ai_model_version text,
  client_info jsonb
);