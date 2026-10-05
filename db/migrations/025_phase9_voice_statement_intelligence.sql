-- Phase 9: transcript uncertainty preservation, search metadata and evidence-comparison candidates.

ALTER TABLE fire_transcript_segments
  ADD COLUMN IF NOT EXISTS uncertainty_markers jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS text_sha256 varchar(64),
  ADD COLUMN IF NOT EXISTS search_text text NOT NULL DEFAULT '';

ALTER TABLE fire_statement_drafts
  ADD COLUMN IF NOT EXISTS source_uncertainty_markers jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS uncertainty_reviewed boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS fire_evidence_comparison_candidates (
  fire_evidence_comparison_candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_case_id uuid NOT NULL
    REFERENCES fire_investigation_cases(fire_investigation_case_id) ON DELETE CASCADE,
  source_manifest_id uuid
    REFERENCES fire_investigation_ai_manifests(fire_investigation_ai_manifest_id) ON DELETE SET NULL,
  issue_type varchar(80) NOT NULL,
  summary text NOT NULL,
  left_ref jsonb NOT NULL,
  right_ref jsonb NOT NULL,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  confidence double precision,
  extraction_method varchar(30) NOT NULL DEFAULT 'ai'
    CHECK (extraction_method IN ('ai','manual','deterministic')),
  model_version varchar(200),
  status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','accepted','rejected')),
  version bigint NOT NULL DEFAULT 1,
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fire_evidence_comparison_case
  ON fire_evidence_comparison_candidates(fire_investigation_case_id, status);
CREATE INDEX IF NOT EXISTS idx_fire_evidence_comparison_manifest
  ON fire_evidence_comparison_candidates(source_manifest_id);
