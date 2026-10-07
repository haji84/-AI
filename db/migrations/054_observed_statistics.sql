-- Immutable observed statistics. Independent of reserved 051 and vehicle assignment 053.


CREATE TABLE statistics_reports (
	report_id UUID NOT NULL,
	snapshot JSON NOT NULL,
	metric_keys JSON NOT NULL,
	state VARCHAR(20) NOT NULL,
	version BIGINT NOT NULL,
	predecessor_id UUID,
	successor_id UUID,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	confirmed_by UUID,
	confirmed_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (report_id),
	CONSTRAINT ck_statistics_state CHECK (state IN ('saved','confirmed')),
	CONSTRAINT ck_statistics_human CHECK ((state='saved' AND confirmed_by IS NULL AND confirmed_at IS NULL) OR (state='confirmed' AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)),
	CONSTRAINT ck_statistics_version CHECK (version >= 1),
	UNIQUE (predecessor_id),
	FOREIGN KEY(predecessor_id) REFERENCES statistics_reports (report_id),
	UNIQUE (successor_id),
	FOREIGN KEY(successor_id) REFERENCES statistics_reports (report_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id),
	FOREIGN KEY(confirmed_by) REFERENCES app_users (user_id)
)

;


CREATE TABLE statistics_evidence (
	report_id UUID NOT NULL,
	evidence JSON NOT NULL,
	fingerprint VARCHAR(64) NOT NULL,
	PRIMARY KEY (report_id),
	FOREIGN KEY(report_id) REFERENCES statistics_reports (report_id)
)

;


CREATE TABLE statistics_history (
	history_id UUID NOT NULL,
	report_id UUID NOT NULL,
	version BIGINT NOT NULL,
	action VARCHAR(20) NOT NULL,
	note TEXT,
	actor_id UUID NOT NULL,
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (history_id),
	CONSTRAINT uq_statistics_history_version UNIQUE (report_id, version),
	CONSTRAINT ck_statistics_history_action CHECK (action IN ('saved','confirmed','replaced')),
	FOREIGN KEY(report_id) REFERENCES statistics_reports (report_id),
	FOREIGN KEY(actor_id) REFERENCES app_users (user_id)
)

;

CREATE INDEX ix_statistics_history_report_id ON statistics_history (report_id);

CREATE FUNCTION statistics_no_rewrite() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
 RAISE EXCEPTION 'statistics evidence/history is immutable' USING ERRCODE='23514';
END;
$guard$;
CREATE TRIGGER statistics_evidence_immutable BEFORE UPDATE OR DELETE ON statistics_evidence FOR EACH ROW EXECUTE FUNCTION statistics_no_rewrite();
CREATE TRIGGER statistics_history_immutable BEFORE UPDATE OR DELETE ON statistics_history FOR EACH ROW EXECUTE FUNCTION statistics_no_rewrite();

CREATE FUNCTION statistics_report_guard() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'statistics report is immutable' USING ERRCODE='23514';
 END IF;
 IF NEW.report_id IS DISTINCT FROM OLD.report_id OR NEW.snapshot::jsonb IS DISTINCT FROM OLD.snapshot::jsonb
 OR NEW.metric_keys::jsonb IS DISTINCT FROM OLD.metric_keys::jsonb OR NEW.predecessor_id IS DISTINCT FROM OLD.predecessor_id
 OR NEW.created_by IS DISTINCT FROM OLD.created_by OR NEW.created_at IS DISTINCT FROM OLD.created_at
 OR NEW.version <> OLD.version + 1
 OR NOT ((OLD.state='saved' AND NEW.state='confirmed' AND OLD.successor_id IS NULL AND NEW.successor_id IS NULL)
 OR (NEW.state=OLD.state AND NEW.confirmed_by IS NOT DISTINCT FROM OLD.confirmed_by AND NEW.confirmed_at IS NOT DISTINCT FROM OLD.confirmed_at
 AND OLD.successor_id IS NULL AND NEW.successor_id IS NOT NULL)) THEN
  RAISE EXCEPTION 'statistics snapshot and previous Human facts are immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$guard$;
CREATE TRIGGER statistics_report_immutable BEFORE UPDATE OR DELETE ON statistics_reports FOR EACH ROW EXECUTE FUNCTION statistics_report_guard();
