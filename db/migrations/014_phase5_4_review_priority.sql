-- Phase 5.4 priority lanes for Human legal review.

ALTER TABLE legal_provision_review_candidates
  ADD COLUMN IF NOT EXISTS priority_lane varchar(30) NOT NULL DEFAULT 'normal',
  ADD COLUMN IF NOT EXISTS source_priority_score double precision NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_legal_provision_review_priority
  ON legal_provision_review_candidates(
    status,
    priority_lane,
    source_priority_score DESC,
    relevance_score DESC
  );
