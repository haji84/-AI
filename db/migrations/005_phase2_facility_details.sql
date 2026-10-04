-- Phase 2: normalized prevention facility detail, contact, and floor data.

CREATE TABLE IF NOT EXISTS facility_details (
  building_id uuid PRIMARY KEY REFERENCES facilities(building_id) ON DELETE CASCADE,
  legacy_book_type text,
  content_as_of text,
  classification_code text,
  classification_detail_1 text,
  classification_detail_2 text,
  zoning text,
  article8_partition text,
  structure text,
  above_ground_floors integer,
  basement_floors integer,
  building_area numeric(14,2),
  total_floor_area numeric(14,2),
  occupancy_total integer,
  employee_total integer,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_facility_details_classification ON facility_details(classification_code);

CREATE TABLE IF NOT EXISTS facility_contacts (
  building_id uuid PRIMARY KEY REFERENCES facilities(building_id) ON DELETE CASCADE,
  representative_name text,
  representative_title text,
  representative_address text,
  representative_phone text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS facility_floors (
  facility_floor_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid NOT NULL REFERENCES facilities(building_id) ON DELETE CASCADE,
  floor_number integer NOT NULL,
  floor_label text,
  floor_area numeric(14,2),
  use_name text,
  occupancy_count integer,
  employee_count integer,
  windowless_status text,
  curtain_status text,
  carpet_status text,
  plywood_status text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(building_id, floor_number)
);
CREATE INDEX IF NOT EXISTS idx_facility_floors_building ON facility_floors(building_id);