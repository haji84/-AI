-- Migration 037: Phase 6 persisted consultation response review evidence.

ALTER TABLE drawing_consultations
  ADD COLUMN IF NOT EXISTS response_payload jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE drawing_consultations
  ADD COLUMN IF NOT EXISTS response_sha256 varchar(64);

ALTER TABLE drawing_consultations
  ADD COLUMN IF NOT EXISTS response_review_notes text;
