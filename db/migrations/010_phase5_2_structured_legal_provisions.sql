-- Phase 5.2: structured legal provisions and exact Rule citations.

CREATE TABLE IF NOT EXISTS legal_provisions (
  legal_provision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_source_document_version_id uuid NOT NULL
    REFERENCES legal_source_document_versions(legal_source_document_version_id) ON DELETE CASCADE,
  parent_provision_id uuid REFERENCES legal_provisions(legal_provision_id) ON DELETE CASCADE,
  provision_type varchar(50) NOT NULL,
  provision_key text NOT NULL,
  sequence_no integer NOT NULL,
  display_label text,
  heading_text text,
  body_text text NOT NULL DEFAULT '',
  source_anchor text,
  source_path text,
  source_meta jsonb NOT NULL DEFAULT '{}'::jsonb,
  content_sha256 varchar(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_legal_provision_key UNIQUE(legal_source_document_version_id, provision_key)
);
CREATE INDEX IF NOT EXISTS idx_legal_provisions_version
  ON legal_provisions(legal_source_document_version_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_legal_provisions_parent
  ON legal_provisions(parent_provision_id);
CREATE INDEX IF NOT EXISTS idx_legal_provisions_type
  ON legal_provisions(provision_type);

CREATE TABLE IF NOT EXISTS legal_rule_citations (
  legal_rule_version_id uuid NOT NULL
    REFERENCES legal_rule_versions(legal_rule_version_id) ON DELETE CASCADE,
  legal_provision_id uuid NOT NULL
    REFERENCES legal_provisions(legal_provision_id) ON DELETE RESTRICT,
  citation_role varchar(40) NOT NULL DEFAULT 'primary'
    CHECK (citation_role IN ('primary','definition','exception','reference','supplementary')),
  cited_text_snapshot text NOT NULL DEFAULT '',
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (legal_rule_version_id, legal_provision_id, citation_role)
);
CREATE INDEX IF NOT EXISTS idx_legal_rule_citations_provision
  ON legal_rule_citations(legal_provision_id);

ALTER TABLE legal_source_document_versions
  ADD COLUMN IF NOT EXISTS structure_status varchar(30) NOT NULL DEFAULT 'unparsed',
  ADD COLUMN IF NOT EXISTS structure_parser_version varchar(80),
  ADD COLUMN IF NOT EXISTS provision_count integer,
  ADD COLUMN IF NOT EXISTS structured_at timestamptz;
