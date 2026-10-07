-- Additive source-backed hazardous register. No legal classification or Rule execution.
CREATE TABLE hazardous_installations (
	installation_id UUID NOT NULL,
	building_id UUID NOT NULL,
	name VARCHAR(500) NOT NULL,
	category_label VARCHAR(500) NOT NULL,
	location_detail TEXT NOT NULL,
	notes TEXT NOT NULL,
	materials JSON NOT NULL,
	status VARCHAR(20) NOT NULL,
	version BIGINT NOT NULL,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (installation_id),
	CONSTRAINT hazardous_installation_status CHECK (status IN ('active','retired')),
	CONSTRAINT hazardous_installation_version CHECK (version >= 1),
	FOREIGN KEY(building_id) REFERENCES facilities (building_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_hazardous_installations_building_id ON hazardous_installations (building_id);

CREATE TABLE hazardous_records (
	record_id UUID NOT NULL,
	installation_id UUID NOT NULL,
	supersedes_record_id UUID,
	kind VARCHAR(30) NOT NULL,
	title VARCHAR(500) NOT NULL,
	reference_no VARCHAR(400),
	recorded_on DATE NOT NULL,
	due_on DATE,
	notes TEXT NOT NULL,
	document_ids JSON NOT NULL,
	legal_source_version_ids JSON NOT NULL,
	inspection_ids JSON NOT NULL,
	violation_case_ids JSON NOT NULL,
	status VARCHAR(20) NOT NULL,
	version BIGINT NOT NULL,
	source_snapshot JSON NOT NULL,
	confirmed_by UUID,
	confirmed_at TIMESTAMP WITH TIME ZONE,
	last_human_reason TEXT,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (record_id),
	CONSTRAINT hazardous_record_kind CHECK (kind IN ('permit','notification','change')),
	CONSTRAINT hazardous_record_status CHECK (status IN ('draft','confirmed','cancelled','superseded')),
	CONSTRAINT hazardous_record_version CHECK (version >= 1),
	FOREIGN KEY(installation_id) REFERENCES hazardous_installations (installation_id),
	FOREIGN KEY(supersedes_record_id) REFERENCES hazardous_records (record_id),
	FOREIGN KEY(confirmed_by) REFERENCES app_users (user_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_hazardous_records_due_on ON hazardous_records (due_on);
CREATE INDEX ix_hazardous_records_installation_id ON hazardous_records (installation_id);

CREATE TABLE hazardous_history (
	history_id UUID NOT NULL,
	installation_id UUID NOT NULL,
	record_id UUID,
	action VARCHAR(50) NOT NULL,
	reason TEXT NOT NULL,
	before JSON,
	after JSON NOT NULL,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (history_id),
	FOREIGN KEY(installation_id) REFERENCES hazardous_installations (installation_id),
	FOREIGN KEY(record_id) REFERENCES hazardous_records (record_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_hazardous_history_installation_id ON hazardous_history (installation_id);
CREATE INDEX ix_hazardous_history_record_id ON hazardous_history (record_id);

-- The API accepts decimal strings and PostgreSQL independently rejects rounding/coercion.
CREATE FUNCTION hazardous_materials_valid(payload JSONB) RETURNS BOOLEAN
LANGUAGE plpgsql IMMUTABLE AS $guard$
DECLARE material JSONB;
BEGIN
 IF jsonb_typeof(payload) IS DISTINCT FROM 'array' THEN RETURN FALSE; END IF;
 IF jsonb_array_length(payload) > 100 THEN RETURN FALSE; END IF;
 FOR material IN SELECT value FROM jsonb_array_elements(payload) LOOP
  IF jsonb_typeof(material) IS DISTINCT FROM 'object'
   OR jsonb_typeof(material->'quantity') IS DISTINCT FROM 'string'
   OR (material->>'quantity') !~ '^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$'
   OR jsonb_typeof(material->'name') IS DISTINCT FROM 'string'
   OR length(btrim(material->>'name')) = 0
   OR jsonb_typeof(material->'quantity_unit') IS DISTINCT FROM 'string'
   OR length(btrim(material->>'quantity_unit')) = 0
  THEN RETURN FALSE; END IF;
  IF material->'capacity' IS NOT NULL AND material->'capacity' <> 'null'::JSONB THEN
   IF jsonb_typeof(material->'capacity') IS DISTINCT FROM 'string'
    OR (material->>'capacity') !~ '^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$'
    OR jsonb_typeof(material->'capacity_unit') IS DISTINCT FROM 'string'
    OR length(btrim(material->>'capacity_unit')) = 0
   THEN RETURN FALSE; END IF;
  ELSIF material->'capacity_unit' IS NOT NULL AND material->'capacity_unit' <> 'null'::JSONB THEN
   RETURN FALSE;
  END IF;
 END LOOP;
 RETURN TRUE;
END;
$guard$;
ALTER TABLE hazardous_installations ADD CONSTRAINT hazardous_exact_materials CHECK (hazardous_materials_valid(materials::JSONB));

CREATE FUNCTION hazardous_history_immutable() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
 RAISE EXCEPTION 'hazardous history is append-only' USING ERRCODE='23514';
END;
$guard$;
CREATE TRIGGER hazardous_history_immutable BEFORE UPDATE OR DELETE ON hazardous_history
 FOR EACH ROW EXECUTE FUNCTION hazardous_history_immutable();

CREATE FUNCTION hazardous_installation_guard() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
 IF TG_OP = 'DELETE' THEN
  RAISE EXCEPTION 'retire hazardous installations; deletion is forbidden' USING ERRCODE='23514';
 END IF;
 IF OLD.status = 'retired' OR NEW.version <> OLD.version + 1
  OR NEW.installation_id IS DISTINCT FROM OLD.installation_id
  OR NEW.building_id IS DISTINCT FROM OLD.building_id
  OR NEW.created_by IS DISTINCT FROM OLD.created_by
  OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
  RAISE EXCEPTION 'hazardous installation identity/history is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$guard$;
CREATE TRIGGER hazardous_installation_guard BEFORE UPDATE OR DELETE ON hazardous_installations
 FOR EACH ROW EXECUTE FUNCTION hazardous_installation_guard();

CREATE FUNCTION hazardous_record_guard() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
 IF TG_OP = 'DELETE' THEN
  RAISE EXCEPTION 'cancel or supersede hazardous evidence; deletion is forbidden' USING ERRCODE='23514';
 END IF;
 IF NEW.version <> OLD.version + 1
  OR NEW.record_id IS DISTINCT FROM OLD.record_id
  OR NEW.installation_id IS DISTINCT FROM OLD.installation_id
  OR NEW.supersedes_record_id IS DISTINCT FROM OLD.supersedes_record_id
  OR NEW.created_by IS DISTINCT FROM OLD.created_by
  OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
  RAISE EXCEPTION 'hazardous evidence identity/version is immutable' USING ERRCODE='23514';
 END IF;
 IF OLD.status IN ('cancelled','superseded') THEN
  RAISE EXCEPTION 'closed hazardous evidence is immutable' USING ERRCODE='23514';
 END IF;
 IF OLD.status = 'confirmed' THEN
  IF NEW.status NOT IN ('cancelled','superseded')
   OR (to_jsonb(NEW) - ARRAY['status','version','updated_at','last_human_reason'])
    IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','version','updated_at','last_human_reason']) THEN
   RAISE EXCEPTION 'confirmed hazardous evidence requires a new revision' USING ERRCODE='23514';
  END IF;
 ELSIF NEW.status = 'superseded' THEN
  RAISE EXCEPTION 'only confirmed evidence may be superseded' USING ERRCODE='23514';
 ELSIF NEW.status = 'confirmed' THEN
  IF NEW.confirmed_by IS NULL OR NEW.confirmed_at IS NULL
   OR jsonb_array_length(NEW.document_ids::JSONB) < 1
   OR NEW.source_snapshot::JSONB->'record'->>'record_id' IS DISTINCT FROM NEW.record_id::TEXT
   OR NEW.source_snapshot::JSONB->'record'->>'version' IS DISTINCT FROM NEW.version::TEXT THEN
   RAISE EXCEPTION 'Human confirmation must bind originals and record revision' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END;
$guard$;
CREATE TRIGGER hazardous_record_guard BEFORE UPDATE OR DELETE ON hazardous_records
 FOR EACH ROW EXECUTE FUNCTION hazardous_record_guard();
CREATE UNIQUE INDEX hazardous_one_confirmed_revision ON hazardous_records(supersedes_record_id)
 WHERE status='confirmed' AND supersedes_record_id IS NOT NULL;
