-- Migration 033: Phase 6 equipment-requirement authoring batch tracking.

CREATE TABLE IF NOT EXISTS equipment_requirement_authoring_batches (
  equipment_requirement_authoring_batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  worklist_sha256 varchar(64) NOT NULL UNIQUE,
  worklist_item_count integer NOT NULL DEFAULT 0,
  expected_candidate_count integer NOT NULL DEFAULT 0,
  import_version varchar(120) NOT NULL,
  source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS equipment_requirement_batch_candidates (
  equipment_requirement_authoring_batch_id uuid NOT NULL
    REFERENCES equipment_requirement_authoring_batches(equipment_requirement_authoring_batch_id)
    ON DELETE CASCADE,
  legal_provision_review_candidate_id uuid NOT NULL
    REFERENCES legal_provision_review_candidates(legal_provision_review_candidate_id)
    ON DELETE CASCADE,
  provision_content_sha256 varchar(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (
    equipment_requirement_authoring_batch_id,
    legal_provision_review_candidate_id
  )
);

CREATE INDEX IF NOT EXISTS idx_equipment_requirement_batch_candidates_candidate
  ON equipment_requirement_batch_candidates(legal_provision_review_candidate_id);
