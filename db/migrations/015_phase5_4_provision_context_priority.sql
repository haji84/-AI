-- Phase 5.4: provision-context priority for current-rule authoring.

ALTER TABLE legal_provision_review_candidates
  ADD COLUMN IF NOT EXISTS provision_context varchar(40) NOT NULL DEFAULT 'main',
  ADD COLUMN IF NOT EXISTS context_priority_score double precision NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_legal_provision_review_total_priority
  ON legal_provision_review_candidates(
    status,
    source_priority_score DESC,
    context_priority_score DESC,
    relevance_score DESC
  );
