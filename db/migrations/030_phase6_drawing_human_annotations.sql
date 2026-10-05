-- Migration 030: Phase 6 Human Annotation sets for drawing benchmark references.
-- AI may seed a draft, but only Human-reviewed annotations can be exported as benchmark reference data.

CREATE TABLE IF NOT EXISTS drawing_annotation_sets (
  drawing_annotation_set_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  drawing_analysis_id uuid NOT NULL
    REFERENCES drawing_analyses(drawing_analysis_id) ON DELETE CASCADE,
  annotation_kind varchar(50) NOT NULL DEFAULT 'human_reference'
    CHECK (annotation_kind IN ('human_reference')),
  coordinate_space varchar(30) NOT NULL DEFAULT 'pixel'
    CHECK (coordinate_space IN ('pixel','normalized')),
  page_dimensions jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_method varchar(30) NOT NULL DEFAULT 'manual'
    CHECK (source_method IN ('manual','ai_seed','import')),
  status varchar(30) NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','reviewed','rejected')),
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drawing_annotation_analysis
  ON drawing_annotation_sets(drawing_analysis_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_drawing_annotation_status
  ON drawing_annotation_sets(status, created_at DESC);
