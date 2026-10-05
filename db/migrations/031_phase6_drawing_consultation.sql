-- Migration 031: Phase 6 drawing consultation / occupancy classification gate.
-- Expands managed legal Rule domains for occupancy classification and future placement rules.

ALTER TABLE legal_rules
  DROP CONSTRAINT IF EXISTS legal_rules_domain_check;
ALTER TABLE legal_rules
  ADD CONSTRAINT ck_legal_rules_domain_v2
  CHECK (domain IN (
    'submission_requirement',
    'equipment_requirement',
    'occupancy_classification',
    'equipment_placement'
  ));

ALTER TABLE legal_rule_draft_candidates
  DROP CONSTRAINT IF EXISTS legal_rule_draft_candidates_domain_check;
ALTER TABLE legal_rule_draft_candidates
  ADD CONSTRAINT ck_legal_rule_draft_candidates_domain_v2
  CHECK (domain IN (
    'submission_requirement',
    'equipment_requirement',
    'occupancy_classification',
    'equipment_placement'
  ));

CREATE TABLE IF NOT EXISTS drawing_consultations (
  drawing_consultation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  drawing_analysis_id uuid NOT NULL
    REFERENCES drawing_analyses(drawing_analysis_id) ON DELETE CASCADE,
  drawing_annotation_set_id uuid NOT NULL
    REFERENCES drawing_annotation_sets(drawing_annotation_set_id) ON DELETE RESTRICT,
  status varchar(40) NOT NULL DEFAULT 'draft'
    CHECK (status IN (
      'draft',
      'classification_pending',
      'classification_candidate',
      'classified',
      'equipment_evaluated',
      'reviewed'
    )),
  input_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  classification_results jsonb NOT NULL DEFAULT '[]'::jsonb,
  missing_information jsonb NOT NULL DEFAULT '[]'::jsonb,
  confirmed_classification_code varchar(100),
  confirmed_classification_label text,
  confirmed_classification_rule_version_id uuid
    REFERENCES legal_rule_versions(legal_rule_version_id),
  classification_confirmed_by uuid REFERENCES app_users(user_id),
  classification_confirmed_at timestamptz,
  equipment_results jsonb NOT NULL DEFAULT '[]'::jsonb,
  placement_results jsonb NOT NULL DEFAULT '[]'::jsonb,
  consultation_notes text,
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drawing_consultation_analysis
  ON drawing_consultations(drawing_analysis_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_drawing_consultation_status
  ON drawing_consultations(status, created_at DESC);
