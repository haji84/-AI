-- Phase 5.3: legal Rule draft candidates generated from structured provisions.

CREATE TABLE IF NOT EXISTS legal_rule_draft_candidates (
  legal_rule_draft_candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_legal_document_version_id uuid
    REFERENCES legal_source_document_versions(legal_source_document_version_id) ON DELETE CASCADE,
  domain varchar(60) NOT NULL CHECK (domain IN ('submission_requirement','equipment_requirement')),
  proposed_rule_code varchar(150),
  proposed_name varchar(300) NOT NULL,
  proposed_conditions jsonb NOT NULL DEFAULT '{}'::jsonb,
  proposed_outcome jsonb NOT NULL DEFAULT '{}'::jsonb,
  extraction_method varchar(30) NOT NULL
    CHECK (extraction_method IN ('manual','deterministic','ai')),
  model_version varchar(200),
  confidence double precision,
  rationale text,
  status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','reviewed','rejected','promoted')),
  version bigint NOT NULL DEFAULT 1,
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  promoted_rule_id uuid REFERENCES legal_rules(rule_id),
  promoted_rule_version_id uuid REFERENCES legal_rule_versions(legal_rule_version_id),
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_legal_rule_draft_candidates_status
  ON legal_rule_draft_candidates(status, domain);
CREATE INDEX IF NOT EXISTS idx_legal_rule_draft_candidates_source
  ON legal_rule_draft_candidates(source_legal_document_version_id);

CREATE TABLE IF NOT EXISTS legal_rule_draft_citations (
  legal_rule_draft_candidate_id uuid NOT NULL
    REFERENCES legal_rule_draft_candidates(legal_rule_draft_candidate_id) ON DELETE CASCADE,
  legal_provision_id uuid NOT NULL
    REFERENCES legal_provisions(legal_provision_id) ON DELETE RESTRICT,
  citation_role varchar(40) NOT NULL DEFAULT 'primary'
    CHECK (citation_role IN ('primary','definition','exception','reference','supplementary')),
  PRIMARY KEY (legal_rule_draft_candidate_id, legal_provision_id, citation_role)
);
CREATE INDEX IF NOT EXISTS idx_legal_rule_draft_citations_provision
  ON legal_rule_draft_citations(legal_provision_id);
