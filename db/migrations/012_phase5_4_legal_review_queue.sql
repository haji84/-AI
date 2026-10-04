-- Phase 5.4: non-authoritative review queue for fire-service-relevant legal provisions.

CREATE TABLE IF NOT EXISTS legal_provision_review_candidates (
  legal_provision_review_candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_provision_id uuid NOT NULL
    REFERENCES legal_provisions(legal_provision_id) ON DELETE CASCADE,
  category varchar(80) NOT NULL,
  relevance_score double precision NOT NULL,
  reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  extraction_method varchar(30) NOT NULL DEFAULT 'deterministic'
    CHECK (extraction_method IN ('deterministic','ai','manual')),
  model_version varchar(200),
  status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','reviewed','ignored','drafted')),
  version bigint NOT NULL DEFAULT 1,
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  legal_rule_draft_candidate_id uuid
    REFERENCES legal_rule_draft_candidates(legal_rule_draft_candidate_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_legal_provision_review_category UNIQUE(legal_provision_id, category)
);
CREATE INDEX IF NOT EXISTS idx_legal_provision_review_status
  ON legal_provision_review_candidates(status, category, relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_legal_provision_review_provision
  ON legal_provision_review_candidates(legal_provision_id);
