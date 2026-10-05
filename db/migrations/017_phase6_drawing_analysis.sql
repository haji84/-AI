-- Phase 6: drawing analysis foundation.
-- AI/manual/import observations remain candidates until Human Review.

CREATE TABLE IF NOT EXISTS drawing_analyses (
  drawing_analysis_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(document_id) ON DELETE RESTRICT,
  status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','analyzed','reviewed','failed')),
  analysis_method varchar(30) NOT NULL DEFAULT 'ai'
    CHECK (analysis_method IN ('ai','manual','import')),
  model_version varchar(200),
  page_count integer,
  confidence double precision,
  summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drawing_analyses_building
  ON drawing_analyses(building_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_drawing_analyses_document
  ON drawing_analyses(document_id);

CREATE TABLE IF NOT EXISTS drawing_elements (
  drawing_element_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  drawing_analysis_id uuid NOT NULL
    REFERENCES drawing_analyses(drawing_analysis_id) ON DELETE CASCADE,
  page_no integer NOT NULL DEFAULT 1,
  element_type varchar(80) NOT NULL,
  label text,
  floor_number integer,
  geometry jsonb NOT NULL DEFAULT '{}'::jsonb,
  extracted_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence double precision,
  source_kind varchar(30) NOT NULL DEFAULT 'ai'
    CHECK (source_kind IN ('ai','manual','import')),
  review_status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (review_status IN ('pending','accepted','rejected')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drawing_elements_analysis
  ON drawing_elements(drawing_analysis_id, page_no, element_type);
CREATE INDEX IF NOT EXISTS idx_drawing_elements_review
  ON drawing_elements(review_status);

CREATE TABLE IF NOT EXISTS drawing_equipment_candidates (
  drawing_equipment_candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  drawing_analysis_id uuid NOT NULL
    REFERENCES drawing_analyses(drawing_analysis_id) ON DELETE CASCADE,
  drawing_element_id uuid REFERENCES drawing_elements(drawing_element_id) ON DELETE SET NULL,
  equipment_type_id uuid REFERENCES equipment_types(equipment_type_id),
  suggested_equipment_type_code varchar(150),
  suggested_label text,
  floor_number integer,
  location_text text,
  quantity integer,
  confidence double precision,
  status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','accepted','rejected','promoted')),
  facility_equipment_id uuid REFERENCES facility_equipment(facility_equipment_id),
  version bigint NOT NULL DEFAULT 1,
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drawing_equipment_candidates_analysis
  ON drawing_equipment_candidates(drawing_analysis_id, status);
CREATE INDEX IF NOT EXISTS idx_drawing_equipment_candidates_type
  ON drawing_equipment_candidates(equipment_type_id);

CREATE TABLE IF NOT EXISTS drawing_fact_candidates (
  drawing_fact_candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  drawing_analysis_id uuid NOT NULL
    REFERENCES drawing_analyses(drawing_analysis_id) ON DELETE CASCADE,
  drawing_element_id uuid REFERENCES drawing_elements(drawing_element_id) ON DELETE SET NULL,
  target_path varchar(200) NOT NULL,
  proposed_value jsonb NOT NULL,
  confidence double precision,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','accepted','rejected')),
  version bigint NOT NULL DEFAULT 1,
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drawing_fact_candidates_analysis
  ON drawing_fact_candidates(drawing_analysis_id, status);
