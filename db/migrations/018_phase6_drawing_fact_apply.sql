-- Phase 6.1: track Human-approved application of drawing fact candidates.

ALTER TABLE drawing_fact_candidates
  ADD COLUMN IF NOT EXISTS applied_by uuid REFERENCES app_users(user_id),
  ADD COLUMN IF NOT EXISTS applied_at timestamptz,
  ADD COLUMN IF NOT EXISTS applied_facility_version bigint;
