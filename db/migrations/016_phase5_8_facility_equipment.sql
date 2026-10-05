-- Phase 5.8: installed fire-safety equipment registry.

CREATE TABLE IF NOT EXISTS equipment_types (
  equipment_type_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(150) NOT NULL UNIQUE,
  name varchar(300) NOT NULL,
  category varchar(120),
  active boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS facility_equipment (
  facility_equipment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id) ON DELETE CASCADE,
  equipment_type_id uuid NOT NULL REFERENCES equipment_types(equipment_type_id),
  floor_number integer,
  location_text text,
  quantity integer,
  operational_status varchar(30) NOT NULL DEFAULT 'installed'
    CHECK (operational_status IN ('installed','removed','unknown')),
  verification_status varchar(30) NOT NULL DEFAULT 'verified'
    CHECK (verification_status IN ('verified','unverified','legacy_only','ai_candidate')),
  source_kind varchar(30) NOT NULL DEFAULT 'manual'
    CHECK (source_kind IN ('manual','submission','legacy','drawing_ai','import')),
  source_document_id uuid REFERENCES documents(document_id),
  submission_id uuid REFERENCES submissions(submission_id),
  installed_at date,
  last_verified_at date,
  notes text,
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  updated_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_facility_equipment_building
  ON facility_equipment(building_id, operational_status, verification_status);
CREATE INDEX IF NOT EXISTS idx_facility_equipment_type
  ON facility_equipment(equipment_type_id);
CREATE INDEX IF NOT EXISTS idx_facility_equipment_source
  ON facility_equipment(source_kind);
