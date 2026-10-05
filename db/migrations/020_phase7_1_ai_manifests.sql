-- Phase 7.1: idempotent AI manifests for fire investigation derived evidence.

CREATE TABLE IF NOT EXISTS fire_investigation_ai_manifests (
  fire_investigation_ai_manifest_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_case_id uuid NOT NULL
    REFERENCES fire_investigation_cases(fire_investigation_case_id) ON DELETE CASCADE,
  fire_investigation_media_id uuid
    REFERENCES fire_investigation_media(fire_investigation_media_id) ON DELETE CASCADE,
  scope_key varchar(200) NOT NULL,
  manifest_type varchar(50) NOT NULL
    CHECK (manifest_type IN ('photo_analysis','transcript','statement_draft')),
  manifest_sha256 varchar(64) NOT NULL,
  model_version varchar(200),
  payload_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fire_ai_manifest UNIQUE(scope_key, manifest_type, manifest_sha256)
);
CREATE INDEX IF NOT EXISTS idx_fire_ai_manifests_case
  ON fire_investigation_ai_manifests(fire_investigation_case_id, manifest_type, created_at);
CREATE INDEX IF NOT EXISTS idx_fire_ai_manifests_media
  ON fire_investigation_ai_manifests(fire_investigation_media_id, manifest_type, created_at);

ALTER TABLE fire_photo_annotations
  ADD COLUMN IF NOT EXISTS source_manifest_id uuid
  REFERENCES fire_investigation_ai_manifests(fire_investigation_ai_manifest_id);

ALTER TABLE fire_transcript_segments
  ADD COLUMN IF NOT EXISTS source_manifest_id uuid
  REFERENCES fire_investigation_ai_manifests(fire_investigation_ai_manifest_id);

ALTER TABLE fire_statement_drafts
  ADD COLUMN IF NOT EXISTS source_manifest_id uuid
  REFERENCES fire_investigation_ai_manifests(fire_investigation_ai_manifest_id);

CREATE INDEX IF NOT EXISTS idx_fire_photo_annotations_manifest
  ON fire_photo_annotations(source_manifest_id);
CREATE INDEX IF NOT EXISTS idx_fire_transcript_segments_manifest
  ON fire_transcript_segments(source_manifest_id);
CREATE INDEX IF NOT EXISTS idx_fire_statement_drafts_manifest
  ON fire_statement_drafts(source_manifest_id);
