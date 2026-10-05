-- Phase 7: fire investigation case/evidence foundation.
-- Original files remain in documents; AI-derived content is stored separately and remains reviewable.

CREATE TABLE IF NOT EXISTS fire_investigation_cases (
  fire_investigation_case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_number varchar(120) UNIQUE,
  building_id uuid REFERENCES facilities(building_id) ON DELETE SET NULL,
  title varchar(500) NOT NULL,
  occurred_at timestamptz,
  location_text text,
  status varchar(30) NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','active','review','closed')),
  official_cause_text text,
  official_cause_candidate_id uuid,
  final_report_document_id uuid REFERENCES documents(document_id),
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  updated_by uuid REFERENCES app_users(user_id),
  cause_approved_by uuid REFERENCES app_users(user_id),
  cause_approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fire_investigation_cases_building
  ON fire_investigation_cases(building_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_fire_investigation_cases_status
  ON fire_investigation_cases(status, occurred_at DESC);

CREATE TABLE IF NOT EXISTS fire_investigation_media (
  fire_investigation_media_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_case_id uuid NOT NULL
    REFERENCES fire_investigation_cases(fire_investigation_case_id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(document_id) ON DELETE RESTRICT,
  media_type varchar(30) NOT NULL
    CHECK (media_type IN ('photo','audio','video','drawing','other')),
  sequence_no integer,
  captured_at timestamptz,
  location_label text,
  floor_number integer,
  notes text,
  review_status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (review_status IN ('pending','accepted','rejected')),
  ai_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fire_investigation_media_document UNIQUE(fire_investigation_case_id, document_id)
);
CREATE INDEX IF NOT EXISTS idx_fire_investigation_media_case
  ON fire_investigation_media(fire_investigation_case_id, media_type, sequence_no);

CREATE TABLE IF NOT EXISTS fire_photo_annotations (
  fire_photo_annotation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_media_id uuid NOT NULL
    REFERENCES fire_investigation_media(fire_investigation_media_id) ON DELETE CASCADE,
  description text,
  tags jsonb NOT NULL DEFAULT '[]'::jsonb,
  map_position jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence double precision,
  source_kind varchar(30) NOT NULL DEFAULT 'ai'
    CHECK (source_kind IN ('ai','manual','import')),
  model_version varchar(200),
  status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','accepted','rejected')),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fire_photo_annotations_media
  ON fire_photo_annotations(fire_investigation_media_id, status);

CREATE TABLE IF NOT EXISTS fire_transcript_segments (
  fire_transcript_segment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_media_id uuid NOT NULL
    REFERENCES fire_investigation_media(fire_investigation_media_id) ON DELETE CASCADE,
  start_ms integer,
  end_ms integer,
  speaker_label varchar(200),
  text text NOT NULL,
  confidence double precision,
  source_kind varchar(30) NOT NULL DEFAULT 'ai'
    CHECK (source_kind IN ('ai','manual','import')),
  model_version varchar(200),
  review_status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (review_status IN ('pending','accepted','rejected')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fire_transcript_segments_media
  ON fire_transcript_segments(fire_investigation_media_id, start_ms);

CREATE TABLE IF NOT EXISTS fire_statement_drafts (
  fire_statement_draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_case_id uuid NOT NULL
    REFERENCES fire_investigation_cases(fire_investigation_case_id) ON DELETE CASCADE,
  fire_investigation_media_id uuid
    REFERENCES fire_investigation_media(fire_investigation_media_id) ON DELETE SET NULL,
  person_label varchar(300),
  draft_text text NOT NULL,
  evidence_segment_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  ai_generated boolean NOT NULL DEFAULT false,
  model_version varchar(200),
  status varchar(30) NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','reviewed','rejected')),
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fire_statement_drafts_case
  ON fire_statement_drafts(fire_investigation_case_id, status);

CREATE TABLE IF NOT EXISTS fire_timeline_events (
  fire_timeline_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_case_id uuid NOT NULL
    REFERENCES fire_investigation_cases(fire_investigation_case_id) ON DELETE CASCADE,
  event_time timestamptz,
  event_time_text text,
  event_type varchar(80),
  title varchar(500) NOT NULL,
  description text,
  source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  confidence double precision,
  status varchar(30) NOT NULL DEFAULT 'candidate'
    CHECK (status IN ('candidate','confirmed','rejected')),
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fire_timeline_events_case
  ON fire_timeline_events(fire_investigation_case_id, event_time);

CREATE TABLE IF NOT EXISTS fire_cause_candidates (
  fire_cause_candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_case_id uuid NOT NULL
    REFERENCES fire_investigation_cases(fire_investigation_case_id) ON DELETE CASCADE,
  cause_category varchar(200),
  cause_text text NOT NULL,
  hypothesis jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  confidence double precision,
  extraction_method varchar(30) NOT NULL DEFAULT 'manual'
    CHECK (extraction_method IN ('manual','ai','import')),
  model_version varchar(200),
  status varchar(30) NOT NULL DEFAULT 'candidate'
    CHECK (status IN ('candidate','reviewed','rejected')),
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fire_cause_candidates_case
  ON fire_cause_candidates(fire_investigation_case_id, status);

ALTER TABLE fire_investigation_cases
  ADD CONSTRAINT fk_fire_investigation_official_cause
  FOREIGN KEY (official_cause_candidate_id)
  REFERENCES fire_cause_candidates(fire_cause_candidate_id)
  ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS fire_report_drafts (
  fire_report_draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_case_id uuid NOT NULL
    REFERENCES fire_investigation_cases(fire_investigation_case_id) ON DELETE CASCADE,
  report_type varchar(120) NOT NULL,
  form_template_id uuid REFERENCES form_templates(form_template_id),
  narrative_text text,
  structured_content jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  ai_generated boolean NOT NULL DEFAULT false,
  model_version varchar(200),
  status varchar(30) NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','reviewed','approved')),
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  approved_by uuid REFERENCES app_users(user_id),
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fire_report_drafts_case
  ON fire_report_drafts(fire_investigation_case_id, report_type, status);
