-- Phase 3: inspection history/findings and submission receipt/status foundation.

CREATE TABLE IF NOT EXISTS inspections (
  inspection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id) ON DELETE CASCADE,
  inspected_at date NOT NULL,
  inspection_type varchar(120) NOT NULL DEFAULT 'general',
  status varchar(30) NOT NULL DEFAULT 'open',
  notes text,
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inspections_building ON inspections(building_id);
CREATE INDEX IF NOT EXISTS idx_inspections_date ON inspections(inspected_at);
CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspections(status);

CREATE TABLE IF NOT EXISTS inspection_findings (
  finding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  inspection_id uuid NOT NULL REFERENCES inspections(inspection_id) ON DELETE CASCADE,
  category varchar(200),
  finding_text text NOT NULL,
  severity varchar(30),
  corrective_status varchar(30) NOT NULL DEFAULT 'open',
  due_date date,
  completed_at date,
  notes text,
  version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inspection_findings_inspection ON inspection_findings(inspection_id);
CREATE INDEX IF NOT EXISTS idx_inspection_findings_status ON inspection_findings(corrective_status);

CREATE TABLE IF NOT EXISTS submission_types (
  submission_type_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(120) UNIQUE NOT NULL,
  name varchar(300) NOT NULL,
  category varchar(120),
  active boolean NOT NULL DEFAULT true,
  requires_document boolean NOT NULL DEFAULT true,
  rules jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS submissions (
  submission_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id) ON DELETE CASCADE,
  submission_type_id uuid NOT NULL REFERENCES submission_types(submission_type_id),
  official_number varchar(30) CHECK (official_number IS NULL OR official_number ~ '^[0-9]+$'),
  received_at timestamptz NOT NULL DEFAULT now(),
  submitted_at date,
  status varchar(30) NOT NULL DEFAULT 'received',
  submitted_by text,
  notes text,
  payload_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_submissions_building ON submissions(building_id);
CREATE INDEX IF NOT EXISTS idx_submissions_type ON submissions(submission_type_id);
CREATE INDEX IF NOT EXISTS idx_submissions_official_number ON submissions(official_number);
CREATE INDEX IF NOT EXISTS idx_submissions_received_at ON submissions(received_at);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);

CREATE TABLE IF NOT EXISTS submission_files (
  submission_id uuid NOT NULL REFERENCES submissions(submission_id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(document_id) ON DELETE RESTRICT,
  file_role varchar(80) NOT NULL DEFAULT 'original',
  page_order integer,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (submission_id, document_id)
);

CREATE TABLE IF NOT EXISTS equipment_inspection_reports (
  report_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id) ON DELETE CASCADE,
  submission_id uuid UNIQUE REFERENCES submissions(submission_id) ON DELETE CASCADE,
  equipment_label text,
  submitted_at date,
  inspection_date date,
  result_summary text,
  next_due_at date,
  source_kind varchar(30) NOT NULL DEFAULT 'submission',
  raw_result_text text,
  raw_report_text text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_equipment_reports_building ON equipment_inspection_reports(building_id);

CREATE TABLE IF NOT EXISTS fire_management_assignments (
  assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id) ON DELETE CASCADE,
  submission_id uuid UNIQUE REFERENCES submissions(submission_id) ON DELETE CASCADE,
  manager_name text,
  manager_title text,
  appointed_at date,
  appointment_submitted_at date,
  status varchar(30) NOT NULL DEFAULT 'active',
  source_kind varchar(30) NOT NULL DEFAULT 'submission',
  legacy_slot integer,
  raw_submission_text text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fire_management_building ON fire_management_assignments(building_id);

CREATE TABLE IF NOT EXISTS fire_plans (
  fire_plan_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id) ON DELETE CASCADE,
  submission_id uuid UNIQUE REFERENCES submissions(submission_id) ON DELETE CASCADE,
  submitted_at date,
  plan_version_label varchar(120),
  status varchar(30) NOT NULL DEFAULT 'submitted',
  source_kind varchar(30) NOT NULL DEFAULT 'submission',
  legacy_slot integer,
  raw_submission_text text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fire_plans_building ON fire_plans(building_id);

CREATE TABLE IF NOT EXISTS inspection_reporting_profiles (
  building_id uuid PRIMARY KEY REFERENCES facilities(building_id) ON DELETE CASCADE,
  report_cycle_years numeric(5,2),
  next_due_date date,
  raw_cycle_text text,
  raw_next_due_text text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS guidance_records (
  guidance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id) ON DELETE CASCADE,
  subject text,
  issued_at date,
  content text,
  legacy_slot integer,
  source_kind varchar(30) NOT NULL DEFAULT 'legacy',
  raw_issued_text text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(building_id, source_kind, legacy_slot)
);
CREATE INDEX IF NOT EXISTS idx_guidance_records_building ON guidance_records(building_id);