-- Phase 8: deterministic fire-photo metadata, quality and duplicate-analysis foundation.
-- Original photo Documents remain immutable. This table stores derived metadata only.

CREATE TABLE IF NOT EXISTS fire_photo_profiles (
  fire_photo_profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_investigation_media_id uuid NOT NULL UNIQUE
    REFERENCES fire_investigation_media(fire_investigation_media_id) ON DELETE CASCADE,
  photo_number integer,
  image_width integer,
  image_height integer,
  orientation integer,
  exif_captured_at timestamptz,
  camera_make text,
  camera_model text,
  exif_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  exact_sha256 varchar(64) NOT NULL,
  perceptual_hash varchar(64),
  duplicate_of_media_id uuid
    REFERENCES fire_investigation_media(fire_investigation_media_id) ON DELETE SET NULL,
  duplicate_distance integer,
  brightness_score double precision,
  contrast_score double precision,
  sharpness_score double precision,
  quality_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
  search_text text NOT NULL DEFAULT '',
  analysis_version varchar(80) NOT NULL DEFAULT 'photo-metadata-v1',
  analyzed_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fire_photo_profiles_sha
  ON fire_photo_profiles(exact_sha256);
CREATE INDEX IF NOT EXISTS idx_fire_photo_profiles_phash
  ON fire_photo_profiles(perceptual_hash);
CREATE INDEX IF NOT EXISTS idx_fire_photo_profiles_number
  ON fire_photo_profiles(photo_number);
CREATE INDEX IF NOT EXISTS idx_fire_photo_profiles_duplicate
  ON fire_photo_profiles(duplicate_of_media_id);
