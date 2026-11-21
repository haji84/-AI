-- Dedicated private audit originals, immutable snapshots, durable jobs.


CREATE TABLE emergency_audit_sources (
	source_id UUID NOT NULL,
	request_id UUID NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	media_type VARCHAR(30) NOT NULL,
	size_bytes BIGINT NOT NULL,
	page_count BIGINT NOT NULL,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (source_id),
	UNIQUE (request_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE TABLE emergency_audit_configurations (
	config_id UUID NOT NULL,
	request_id UUID NOT NULL,
	request_sha256 VARCHAR(64) NOT NULL,
	supersedes_id UUID,
	kind VARCHAR(10) NOT NULL,
	label VARCHAR(100) NOT NULL,
	form_key VARCHAR(64) NOT NULL,
	definition_cipher BYTEA NOT NULL,
	source_id UUID,
	status VARCHAR(12) NOT NULL,
	version BIGINT NOT NULL,
	impact JSON,
	created_by UUID NOT NULL,
	created_employee_id UUID,
	approved_by UUID,
	approved_employee_id UUID,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	approved_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (config_id),
	CONSTRAINT em_audit_config_kind CHECK (kind IN ('profile','rules')),
	CONSTRAINT em_audit_config_status CHECK (status IN ('draft','approved','retired')),
	CONSTRAINT em_audit_config_version CHECK (version >= 1),
	UNIQUE (request_id),
	UNIQUE (supersedes_id),
	FOREIGN KEY(supersedes_id) REFERENCES emergency_audit_configurations (config_id),
	FOREIGN KEY(source_id) REFERENCES emergency_audit_sources (source_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id),
	FOREIGN KEY(created_employee_id) REFERENCES employees (employee_id),
	FOREIGN KEY(approved_by) REFERENCES app_users (user_id),
	FOREIGN KEY(approved_employee_id) REFERENCES employees (employee_id)
);

CREATE INDEX ix_emergency_audit_configurations_form_key ON emergency_audit_configurations (form_key);

CREATE TABLE emergency_audit_reports (
	report_id UUID NOT NULL,
	request_id UUID NOT NULL,
	request_sha256 VARCHAR(64) NOT NULL,
	owner_id UUID NOT NULL,
	owner_employee_id UUID,
	reviewer_id UUID,
	reviewer_employee_id UUID,
	dataset_kind VARCHAR(20) NOT NULL,
	current_revision_id UUID,
	version BIGINT NOT NULL,
	revision_number BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (report_id),
	CONSTRAINT em_audit_dataset CHECK (dataset_kind IN ('synthetic','internal_trial')),
	CONSTRAINT em_audit_report_version CHECK (version >= 1),
	UNIQUE (request_id),
	FOREIGN KEY(owner_id) REFERENCES app_users (user_id),
	FOREIGN KEY(owner_employee_id) REFERENCES employees (employee_id),
	FOREIGN KEY(reviewer_id) REFERENCES app_users (user_id),
	FOREIGN KEY(reviewer_employee_id) REFERENCES employees (employee_id)
);

CREATE INDEX ix_emergency_audit_reports_owner_id ON emergency_audit_reports (owner_id);

CREATE TABLE emergency_audit_revisions (
	revision_id UUID NOT NULL,
	report_id UUID NOT NULL,
	number BIGINT NOT NULL,
	request_id UUID NOT NULL,
	request_sha256 VARCHAR(64) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	media_type VARCHAR(30) NOT NULL,
	size_bytes BIGINT NOT NULL,
	page_count BIGINT NOT NULL,
	profile_id UUID,
	version BIGINT NOT NULL,
	processing_status VARCHAR(20) NOT NULL,
	error_code VARCHAR(60),
	reading_cipher BYTEA,
	fields_cipher BYTEA,
	ai_cipher BYTEA,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (revision_id),
	CONSTRAINT em_audit_revision_number UNIQUE (report_id, number),
	FOREIGN KEY(report_id) REFERENCES emergency_audit_reports (report_id),
	UNIQUE (request_id),
	FOREIGN KEY(profile_id) REFERENCES emergency_audit_configurations (config_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_emergency_audit_revisions_report_id ON emergency_audit_revisions (report_id);

CREATE TABLE emergency_audit_jobs (
	job_id UUID NOT NULL,
	revision_id UUID NOT NULL,
	kind VARCHAR(8) NOT NULL,
	page_number BIGINT,
	status VARCHAR(12) NOT NULL,
	attempts BIGINT NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	revision_version BIGINT NOT NULL,
	requested_by UUID NOT NULL,
	requested_employee_id UUID,
	lease_token UUID,
	lease_until TIMESTAMP WITH TIME ZONE,
	error_code VARCHAR(60),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE,
	finished_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (job_id),
	CONSTRAINT em_audit_job_kind CHECK (kind IN ('read','ai','vision')),
	CONSTRAINT em_audit_job_status CHECK (status IN ('queued','processing','done','failed','cancelled')),
	FOREIGN KEY(revision_id) REFERENCES emergency_audit_revisions (revision_id),
	FOREIGN KEY(requested_by) REFERENCES app_users (user_id),
	FOREIGN KEY(requested_employee_id) REFERENCES employees (employee_id)
);

CREATE INDEX ix_emergency_audit_jobs_revision_id ON emergency_audit_jobs (revision_id);

CREATE INDEX ix_emergency_audit_jobs_status ON emergency_audit_jobs (status);

CREATE TABLE emergency_audit_runs (
	run_id UUID NOT NULL,
	report_id UUID NOT NULL,
	revision_id UUID NOT NULL,
	revision_version BIGINT NOT NULL,
	report_version BIGINT NOT NULL,
	rule_set_id UUID,
	mode VARCHAR(12) NOT NULL,
	payload_cipher BYTEA NOT NULL,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (run_id),
	FOREIGN KEY(report_id) REFERENCES emergency_audit_reports (report_id),
	FOREIGN KEY(revision_id) REFERENCES emergency_audit_revisions (revision_id),
	FOREIGN KEY(rule_set_id) REFERENCES emergency_audit_configurations (config_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_emergency_audit_runs_report_id ON emergency_audit_runs (report_id);

CREATE TABLE emergency_audit_events (
	event_id UUID NOT NULL,
	supersedes_id UUID UNIQUE REFERENCES emergency_audit_events(event_id),
	report_id UUID NOT NULL,
	kind VARCHAR(30) NOT NULL,
	request_sha256 VARCHAR(64) NOT NULL,
	payload JSON NOT NULL,
	actor_id UUID NOT NULL,
	actor_employee_id UUID,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (event_id),
	FOREIGN KEY(report_id) REFERENCES emergency_audit_reports (report_id),
	FOREIGN KEY(actor_id) REFERENCES app_users (user_id),
	FOREIGN KEY(actor_employee_id) REFERENCES employees (employee_id)
);

CREATE INDEX ix_emergency_audit_events_report_id ON emergency_audit_events (report_id);

CREATE TABLE emergency_audit_worker_heartbeats (
	worker_id UUID NOT NULL,
	seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (worker_id)
);

-- At most one active processor for an original/kind. Expired leases are
-- reclaimed on that same row, rather than spawning an unfenced duplicate.
CREATE UNIQUE INDEX em_audit_active_job ON emergency_audit_jobs(revision_id,kind)
    WHERE status IN ('queued','processing');

CREATE FUNCTION emergency_audit_immutable_record() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
    RAISE EXCEPTION 'private source or audit history is immutable' USING ERRCODE='23514';
END;
$guard$;
CREATE TRIGGER emergency_audit_source_immutable BEFORE UPDATE OR DELETE ON emergency_audit_sources
    FOR EACH ROW EXECUTE FUNCTION emergency_audit_immutable_record();
CREATE TRIGGER emergency_audit_run_immutable BEFORE UPDATE OR DELETE ON emergency_audit_runs
    FOR EACH ROW EXECUTE FUNCTION emergency_audit_immutable_record();
CREATE TRIGGER emergency_audit_event_immutable BEFORE UPDATE OR DELETE ON emergency_audit_events
    FOR EACH ROW EXECUTE FUNCTION emergency_audit_immutable_record();

CREATE FUNCTION emergency_audit_revision_guard() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'private original revisions cannot be deleted by ordinary writes' USING ERRCODE='23514';
    END IF;
    IF ROW(NEW.revision_id,NEW.report_id,NEW.number,NEW.request_id,NEW.request_sha256,
           NEW.source_sha256,NEW.media_type,NEW.size_bytes,NEW.page_count,NEW.created_by,NEW.created_at)
        IS DISTINCT FROM
       ROW(OLD.revision_id,OLD.report_id,OLD.number,OLD.request_id,OLD.request_sha256,
           OLD.source_sha256,OLD.media_type,OLD.size_bytes,OLD.page_count,OLD.created_by,OLD.created_at) THEN
        RAISE EXCEPTION 'original identity and content are immutable' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$guard$;
CREATE TRIGGER emergency_audit_revision_guard BEFORE UPDATE OR DELETE ON emergency_audit_revisions
    FOR EACH ROW EXECUTE FUNCTION emergency_audit_revision_guard();

CREATE FUNCTION emergency_audit_config_guard() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'configuration history cannot be deleted by ordinary writes' USING ERRCODE='23514';
    END IF;
    IF ROW(NEW.config_id,NEW.request_id,NEW.request_sha256,NEW.supersedes_id,NEW.kind,
           NEW.label,NEW.form_key,NEW.definition_cipher,NEW.source_id,NEW.created_by,NEW.created_employee_id,NEW.created_at)
        IS DISTINCT FROM
       ROW(OLD.config_id,OLD.request_id,OLD.request_sha256,OLD.supersedes_id,OLD.kind,
           OLD.label,OLD.form_key,OLD.definition_cipher,OLD.source_id,OLD.created_by,OLD.created_employee_id,OLD.created_at)
       OR NEW.version <> OLD.version + 1 THEN
        RAISE EXCEPTION 'configuration definition is immutable; create a new version' USING ERRCODE='23514';
    END IF;
    IF NEW.status='approved' AND (NEW.approved_by IS NULL OR NEW.approved_employee_id IS NULL
        OR OLD.created_employee_id IS NULL OR NEW.approved_by=OLD.created_by
        OR NEW.approved_employee_id=OLD.created_employee_id OR NEW.approved_at IS NULL) THEN
        RAISE EXCEPTION 'independent configuration approval required' USING ERRCODE='23514';
    END IF;
    IF OLD.status='retired' OR (OLD.status='approved' AND NEW.status <> 'retired') THEN
        RAISE EXCEPTION 'approved configuration must be superseded or retired' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$guard$;
CREATE TRIGGER emergency_audit_config_guard BEFORE UPDATE OR DELETE ON emergency_audit_configurations
    FOR EACH ROW EXECUTE FUNCTION emergency_audit_config_guard();

CREATE FUNCTION emergency_audit_report_guard() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
    IF TG_OP='DELETE' THEN
        RAISE EXCEPTION 'report history cannot be deleted by ordinary writes' USING ERRCODE='23514';
    END IF;
    IF ROW(NEW.report_id,NEW.request_id,NEW.request_sha256,NEW.owner_id,NEW.owner_employee_id,NEW.dataset_kind,NEW.created_at)
       IS DISTINCT FROM
       ROW(OLD.report_id,OLD.request_id,OLD.request_sha256,OLD.owner_id,OLD.owner_employee_id,OLD.dataset_kind,OLD.created_at)
       OR NEW.version < OLD.version THEN
        RAISE EXCEPTION 'report identity and dataset binding are immutable' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$guard$;
CREATE TRIGGER emergency_audit_report_guard BEFORE UPDATE OR DELETE ON emergency_audit_reports
    FOR EACH ROW EXECUTE FUNCTION emergency_audit_report_guard();
