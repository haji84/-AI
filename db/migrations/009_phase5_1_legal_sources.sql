-- Phase 5.1: national-law and fire-department/local-regulation source registry.

CREATE TABLE IF NOT EXISTS legal_jurisdictions (
  jurisdiction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(150) NOT NULL UNIQUE,
  name varchar(300) NOT NULL,
  jurisdiction_type varchar(40) NOT NULL CHECK (jurisdiction_type IN ('national','prefecture','municipality','fire_union','fire_department','other')),
  parent_jurisdiction_id uuid REFERENCES legal_jurisdictions(jurisdiction_id),
  official_base_url text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS legal_profiles (
  legal_profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(150) NOT NULL UNIQUE,
  name varchar(300) NOT NULL,
  fire_department_name varchar(300),
  active boolean NOT NULL DEFAULT true,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS legal_profile_jurisdictions (
  legal_profile_id uuid NOT NULL REFERENCES legal_profiles(legal_profile_id) ON DELETE CASCADE,
  jurisdiction_id uuid NOT NULL REFERENCES legal_jurisdictions(jurisdiction_id) ON DELETE CASCADE,
  applicability varchar(40) NOT NULL DEFAULT 'applicable',
  priority integer NOT NULL DEFAULT 100,
  PRIMARY KEY (legal_profile_id, jurisdiction_id)
);

CREATE TABLE IF NOT EXISTS legal_sources (
  legal_source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_profile_id uuid REFERENCES legal_profiles(legal_profile_id) ON DELETE CASCADE,
  jurisdiction_id uuid NOT NULL REFERENCES legal_jurisdictions(jurisdiction_id) ON DELETE CASCADE,
  source_code varchar(180) NOT NULL,
  name varchar(300) NOT NULL,
  source_type varchar(60) NOT NULL,
  adapter_type varchar(80) NOT NULL,
  base_url text NOT NULL,
  index_url text,
  update_mode varchar(30) NOT NULL DEFAULT 'online' CHECK (update_mode IN ('online','bundle','manual')),
  content_scope varchar(30) NOT NULL DEFAULT 'all',
  sync_frequency varchar(30) NOT NULL DEFAULT 'daily',
  trust_level varchar(30) NOT NULL DEFAULT 'official',
  parser_config jsonb NOT NULL DEFAULT '{}'::jsonb,
  enabled boolean NOT NULL DEFAULT true,
  content_current_date date,
  last_checked_at timestamptz,
  last_success_at timestamptz,
  etag text,
  last_modified text,
  index_hash varchar(64),
  coverage_status varchar(30) NOT NULL DEFAULT 'unverified' CHECK (coverage_status IN ('unverified','complete','partial','stale','error')),
  expected_document_count integer,
  captured_document_count integer,
  last_full_sync_at timestamptz,
  stale_after_hours integer NOT NULL DEFAULT 168,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_legal_source_code UNIQUE(jurisdiction_id, source_code)
);

CREATE TABLE IF NOT EXISTS legal_source_documents (
  legal_source_document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_source_id uuid NOT NULL REFERENCES legal_sources(legal_source_id) ON DELETE CASCADE,
  external_id text NOT NULL,
  document_type varchar(80) NOT NULL,
  title text NOT NULL,
  document_number text,
  promulgation_date date,
  enacted_date date,
  current_status varchar(30) NOT NULL DEFAULT 'current',
  source_url text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_legal_source_document UNIQUE(legal_source_id, external_id)
);

CREATE TABLE IF NOT EXISTS legal_source_document_versions (
  legal_source_document_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_source_document_id uuid NOT NULL REFERENCES legal_source_documents(legal_source_document_id) ON DELETE CASCADE,
  version_label varchar(160),
  revision_external_id text,
  effective_from date,
  effective_to date,
  source_current_date date,
  retrieved_at timestamptz NOT NULL DEFAULT now(),
  raw_document_id uuid REFERENCES documents(document_id),
  normalized_text text NOT NULL DEFAULT '',
  structured_content jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_url text,
  sha256 varchar(64) NOT NULL,
  previous_version_id uuid REFERENCES legal_source_document_versions(legal_source_document_version_id),
  change_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  parse_status varchar(30) NOT NULL DEFAULT 'stored',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_legal_source_document_hash UNIQUE(legal_source_document_id, sha256)
);

CREATE TABLE IF NOT EXISTS legal_sync_runs (
  legal_sync_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_source_id uuid NOT NULL REFERENCES legal_sources(legal_source_id) ON DELETE CASCADE,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  status varchar(30) NOT NULL DEFAULT 'running',
  checked_count integer NOT NULL DEFAULT 0,
  new_count integer NOT NULL DEFAULT 0,
  amended_count integer NOT NULL DEFAULT 0,
  repealed_count integer NOT NULL DEFAULT 0,
  unchanged_count integer NOT NULL DEFAULT 0,
  error_count integer NOT NULL DEFAULT 0,
  details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS legal_update_candidates (
  legal_update_candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_source_document_version_id uuid NOT NULL REFERENCES legal_source_document_versions(legal_source_document_version_id) ON DELETE CASCADE,
  previous_version_id uuid REFERENCES legal_source_document_versions(legal_source_document_version_id),
  change_type varchar(30) NOT NULL,
  diff_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  impacted_rule_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  impacted_modules jsonb NOT NULL DEFAULT '[]'::jsonb,
  status varchar(30) NOT NULL DEFAULT 'review_required',
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE legal_rule_versions
  ADD COLUMN IF NOT EXISTS source_legal_document_version_id uuid
  REFERENCES legal_source_document_versions(legal_source_document_version_id);

CREATE INDEX IF NOT EXISTS idx_legal_sources_profile ON legal_sources(legal_profile_id);
CREATE INDEX IF NOT EXISTS idx_legal_sources_jurisdiction ON legal_sources(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_legal_source_documents_source ON legal_source_documents(legal_source_id);
CREATE INDEX IF NOT EXISTS idx_legal_source_document_versions_doc ON legal_source_document_versions(legal_source_document_id, retrieved_at);
CREATE INDEX IF NOT EXISTS idx_legal_sync_runs_source ON legal_sync_runs(legal_source_id, started_at);
CREATE INDEX IF NOT EXISTS idx_legal_update_candidates_status ON legal_update_candidates(status);
