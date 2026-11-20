-- Private evaluation metadata only. Human review never grants production release.
CREATE TABLE emergency_acceptance_evaluations (
    evaluation_id uuid PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE,
    request_sha256 varchar(64) NOT NULL,
    supersedes_id uuid UNIQUE REFERENCES emergency_acceptance_evaluations(evaluation_id),
    dataset_kind varchar(20) NOT NULL,
    measurement jsonb NOT NULL,
    summary jsonb NOT NULL,
    evidence jsonb NOT NULL DEFAULT '[]',
    status varchar(20) NOT NULL DEFAULT 'recorded',
    version bigint NOT NULL DEFAULT 1,
    review_decision varchar(20),
    created_by uuid NOT NULL REFERENCES app_users(user_id),
    created_employee_id uuid REFERENCES employees(employee_id),
    reviewed_by uuid REFERENCES app_users(user_id),
    reviewed_employee_id uuid REFERENCES employees(employee_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz,
    CONSTRAINT em_acceptance_kind CHECK (dataset_kind IN ('synthetic','internal_trial')),
    CONSTRAINT em_acceptance_status CHECK (status IN ('recorded','reviewed')),
    CONSTRAINT em_acceptance_version CHECK (version >= 1),
    CONSTRAINT em_acceptance_decision CHECK (review_decision IS NULL OR review_decision IN ('confirmed','rejected')),
    CONSTRAINT em_acceptance_independent_review CHECK (status <> 'reviewed' OR (
        reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND reviewed_by <> created_by
        AND reviewed_employee_id IS NOT NULL AND created_employee_id IS NOT NULL
        AND reviewed_employee_id <> created_employee_id AND review_decision IS NOT NULL))
);

CREATE FUNCTION emergency_acceptance_immutable() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'evaluation history cannot be deleted through ordinary writes' USING ERRCODE='23514';
    END IF;
    IF ROW(NEW.evaluation_id, NEW.request_id, NEW.request_sha256, NEW.supersedes_id,
        NEW.dataset_kind, NEW.measurement, NEW.summary, NEW.created_by, NEW.created_employee_id, NEW.created_at)
        IS DISTINCT FROM ROW(OLD.evaluation_id, OLD.request_id, OLD.request_sha256, OLD.supersedes_id,
        OLD.dataset_kind, OLD.measurement, OLD.summary, OLD.created_by, OLD.created_employee_id, OLD.created_at)
        OR OLD.status <> 'recorded' OR NEW.status <> 'reviewed' OR NEW.version <> OLD.version + 1
        OR NEW.reviewed_by IS NULL OR NEW.reviewed_at IS NULL OR NEW.review_decision IS NULL
        OR NEW.reviewed_by = OLD.created_by OR NEW.reviewed_employee_id IS NULL
        OR OLD.created_employee_id IS NULL OR NEW.reviewed_employee_id = OLD.created_employee_id THEN
        RAISE EXCEPTION 'evaluation snapshot is immutable; independent review required' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$guard$;
CREATE TRIGGER emergency_acceptance_immutable BEFORE UPDATE OR DELETE ON emergency_acceptance_evaluations
    FOR EACH ROW EXECUTE FUNCTION emergency_acceptance_immutable();
