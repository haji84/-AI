-- Phase 4: document analysis, human review and explicit facility-change proposal.
CREATE TABLE IF NOT EXISTS document_analyses (
  document_analysis_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  status varchar(40) NOT NULL DEFAULT 'analyzed',
  extraction_method varchar(80) NOT NULL,
  extracted_text text NOT NULL DEFAULT '',
  page_count integer,
  detected_submission_type_code varchar(120),
  detected_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
  facility_candidates jsonb NOT NULL DEFAULT '[]'::jsonb,
  difference_candidates jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence double precision,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  selected_building_id uuid REFERENCES facilities(building_id),
  selected_submission_type_code varchar(120),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_document_analyses_document ON document_analyses(document_id);
CREATE INDEX IF NOT EXISTS idx_document_analyses_type ON document_analyses(detected_submission_type_code);
CREATE INDEX IF NOT EXISTS idx_document_analyses_building ON document_analyses(selected_building_id);

CREATE TABLE IF NOT EXISTS facility_change_proposals (
  facility_change_proposal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_analysis_id uuid NOT NULL REFERENCES document_analyses(document_analysis_id) ON DELETE CASCADE,
  building_id uuid NOT NULL REFERENCES facilities(building_id) ON DELETE CASCADE,
  expected_facility_version bigint NOT NULL,
  changes jsonb NOT NULL DEFAULT '{}'::jsonb,
  status varchar(30) NOT NULL DEFAULT 'pending',
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  applied_at timestamptz,
  version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_facility_change_proposals_analysis ON facility_change_proposals(document_analysis_id);
CREATE INDEX IF NOT EXISTS idx_facility_change_proposals_building ON facility_change_proposals(building_id);
CREATE INDEX IF NOT EXISTS idx_facility_change_proposals_status ON facility_change_proposals(status);