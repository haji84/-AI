-- Phase 8.1: Human-reviewed photo position links on drawing analyses.

CREATE TABLE IF NOT EXISTS fire_photo_plan_links (
  fire_photo_plan_link_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_media_id uuid NOT NULL
    REFERENCES fire_investigation_media(fire_investigation_media_id) ON DELETE CASCADE,
  drawing_analysis_id uuid NOT NULL
    REFERENCES drawing_analyses(drawing_analysis_id) ON DELETE CASCADE,
  drawing_element_id uuid
    REFERENCES drawing_elements(drawing_element_id) ON DELETE SET NULL,
  page_no integer,
  floor_number integer,
  position jsonb NOT NULL DEFAULT '{}'::jsonb,
  label text,
  source_kind varchar(30) NOT NULL DEFAULT 'manual'
    CHECK (source_kind IN ('manual','ai','import')),
  confidence double precision,
  status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','accepted','rejected')),
  version bigint NOT NULL DEFAULT 1,
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fire_photo_plan_links_media
  ON fire_photo_plan_links(fire_investigation_media_id, status);
CREATE INDEX IF NOT EXISTS idx_fire_photo_plan_links_drawing
  ON fire_photo_plan_links(drawing_analysis_id, page_no);
CREATE INDEX IF NOT EXISTS idx_fire_photo_plan_links_element
  ON fire_photo_plan_links(drawing_element_id);
