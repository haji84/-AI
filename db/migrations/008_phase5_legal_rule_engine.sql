-- Phase 5: managed legal/requirement rule engine.
-- No legal content is seeded here. Official rules must be registered from verified source material
-- and explicitly approved before they can participate in evaluations.

CREATE TABLE IF NOT EXISTS legal_rules (
  rule_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_code varchar(150) NOT NULL UNIQUE,
  name varchar(300) NOT NULL,
  domain varchar(60) NOT NULL CHECK (domain IN ('submission_requirement','equipment_requirement')),
  description text,
  active boolean NOT NULL DEFAULT true,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_legal_rules_domain ON legal_rules(domain);

CREATE TABLE IF NOT EXISTS legal_rule_versions (
  legal_rule_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_id uuid NOT NULL REFERENCES legal_rules(rule_id) ON DELETE CASCADE,
  version_no integer NOT NULL,
  effective_from date NOT NULL,
  effective_to date,
  conditions jsonb NOT NULL,
  outcome jsonb NOT NULL,
  source_document_id uuid REFERENCES documents(document_id),
  source_reference text,
  status varchar(30) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','retired')),
  approved_by uuid REFERENCES app_users(user_id),
  approved_at timestamptz,
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_legal_rule_version_dates CHECK (effective_to IS NULL OR effective_to >= effective_from),
  CONSTRAINT uq_legal_rule_version UNIQUE(rule_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_legal_rule_versions_rule ON legal_rule_versions(rule_id);
CREATE INDEX IF NOT EXISTS idx_legal_rule_versions_status_dates ON legal_rule_versions(status, effective_from, effective_to);

CREATE TABLE IF NOT EXISTS requirement_evaluations (
  evaluation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id) ON DELETE CASCADE,
  domain varchar(60) NOT NULL CHECK (domain IN ('submission_requirement','equipment_requirement')),
  evaluation_date date NOT NULL,
  facility_version bigint NOT NULL,
  engine_version varchar(50) NOT NULL DEFAULT 'phase5-v1',
  input_snapshot jsonb NOT NULL,
  results jsonb NOT NULL DEFAULT '[]'::jsonb,
  status varchar(30) NOT NULL DEFAULT 'candidate',
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_requirement_evaluations_building ON requirement_evaluations(building_id, created_at);
CREATE INDEX IF NOT EXISTS idx_requirement_evaluations_domain ON requirement_evaluations(domain);
