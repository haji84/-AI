-- Phase 5.3 hardening: idempotent generated Rule draft candidates.

ALTER TABLE legal_rule_draft_candidates
  ADD COLUMN IF NOT EXISTS candidate_fingerprint varchar(64),
  ADD COLUMN IF NOT EXISTS generation_context jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_rule_draft_candidate_fingerprint
  ON legal_rule_draft_candidates(candidate_fingerprint)
  WHERE candidate_fingerprint IS NOT NULL;
