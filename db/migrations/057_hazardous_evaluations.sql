-- Dedicated candidates; no permit/violation/compliance formalization.
CREATE TABLE hazardous_evaluations (
    evaluation_id uuid PRIMARY KEY,
    installation_id uuid NOT NULL REFERENCES hazardous_installations(installation_id),
    legal_profile_id uuid NOT NULL REFERENCES legal_profiles(legal_profile_id),
    evaluation_date date NOT NULL,
    input_snapshot jsonb NOT NULL,
    rules_snapshot jsonb NOT NULL,
    results jsonb NOT NULL,
    coverage_status varchar(20) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'candidate',
    version bigint NOT NULL DEFAULT 1,
    reason text,
    created_by uuid NOT NULL REFERENCES app_users(user_id),
    reviewed_by uuid REFERENCES app_users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz,
    CONSTRAINT hazardous_evaluation_status CHECK (status IN ('candidate','reviewed')),
    CONSTRAINT hazardous_evaluation_coverage CHECK (coverage_status IN ('evaluated','unavailable')),
    CONSTRAINT hazardous_evaluation_version CHECK (version >= 1),
    CONSTRAINT hazardous_evaluation_review CHECK (status <> 'reviewed' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE INDEX ix_hazardous_evaluations_installation_id ON hazardous_evaluations(installation_id);
CREATE FUNCTION hazardous_evaluation_immutable() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'hazardous evaluation evidence cannot be deleted' USING ERRCODE='23514';
    END IF;
    IF ROW(NEW.evaluation_id, NEW.installation_id, NEW.legal_profile_id, NEW.evaluation_date,
        NEW.input_snapshot, NEW.rules_snapshot, NEW.results, NEW.coverage_status, NEW.created_by, NEW.created_at)
        IS DISTINCT FROM ROW(OLD.evaluation_id, OLD.installation_id, OLD.legal_profile_id, OLD.evaluation_date,
        OLD.input_snapshot, OLD.rules_snapshot, OLD.results, OLD.coverage_status, OLD.created_by, OLD.created_at)
        OR OLD.status <> 'candidate' OR NEW.status <> 'reviewed' OR NEW.version <> OLD.version + 1
        OR NEW.reviewed_by IS NULL OR NEW.reviewed_at IS NULL OR length(btrim(COALESCE(NEW.reason, ''))) = 0 THEN
        RAISE EXCEPTION 'hazardous evaluation evidence is immutable; independent Human review required' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$guard$;
CREATE TRIGGER hazardous_evaluation_immutable BEFORE UPDATE OR DELETE ON hazardous_evaluations
    FOR EACH ROW EXECUTE FUNCTION hazardous_evaluation_immutable();
