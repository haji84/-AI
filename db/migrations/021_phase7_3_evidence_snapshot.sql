-- Phase 7.3: immutable evidence snapshots and AI report provenance.
-- A snapshot freezes only Human-accepted/reviewed/confirmed evidence that may be used by report generation.

CREATE TABLE IF NOT EXISTS fire_evidence_snapshots (
  fire_evidence_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_case_id uuid NOT NULL
    REFERENCES fire_investigation_cases(fire_investigation_case_id) ON DELETE CASCADE,
  case_version bigint NOT NULL,
  snapshot_sha256 varchar(64) NOT NULL,
  photo_annotation_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  transcript_segment_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  statement_draft_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  timeline_event_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  official_cause_candidate_id uuid
    REFERENCES fire_cause_candidates(fire_cause_candidate_id) ON DELETE SET NULL,
  media_document_hashes jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fire_evidence_snapshot UNIQUE(fire_investigation_case_id, snapshot_sha256)
);
CREATE INDEX IF NOT EXISTS idx_fire_evidence_snapshots_case
  ON fire_evidence_snapshots(fire_investigation_case_id, created_at DESC);

ALTER TABLE fire_report_drafts
  ADD COLUMN IF NOT EXISTS fire_evidence_snapshot_id uuid
    REFERENCES fire_evidence_snapshots(fire_evidence_snapshot_id),
  ADD COLUMN IF NOT EXISTS source_manifest_id uuid
    REFERENCES fire_investigation_ai_manifests(fire_investigation_ai_manifest_id);

ALTER TABLE fire_investigation_ai_manifests
  DROP CONSTRAINT IF EXISTS fire_investigation_ai_manifests_manifest_type_check;

ALTER TABLE fire_investigation_ai_manifests
  ADD CONSTRAINT fire_investigation_ai_manifests_manifest_type_check
  CHECK (manifest_type IN ('photo_analysis','transcript','statement_draft','report_draft'));

CREATE INDEX IF NOT EXISTS idx_fire_report_drafts_snapshot
  ON fire_report_drafts(fire_evidence_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_fire_report_drafts_manifest
  ON fire_report_drafts(source_manifest_id);
