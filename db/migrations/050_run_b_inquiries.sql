-- Evidence-required council inquiries; exact values remain Decimal strings inside immutable JSON snapshots.


CREATE TABLE inquiries (
	inquiry_id UUID NOT NULL,
	year BIGINT NOT NULL,
	question TEXT NOT NULL,
	draft TEXT NOT NULL,
	claims JSON NOT NULL,
	status VARCHAR(20) NOT NULL,
	revision_of UUID,
	provenance JSON NOT NULL,
	review_snapshot JSON NOT NULL,
	reviewed_by UUID,
	reviewed_at TIMESTAMP WITH TIME ZONE,
	approved_by UUID,
	approved_at TIMESTAMP WITH TIME ZONE,
	created_by UUID NOT NULL,
	deleted BOOLEAN NOT NULL,
	version BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (inquiry_id),
	CONSTRAINT ck_inquiry_year CHECK (year BETWEEN 1900 AND 2200),
	CONSTRAINT ck_inquiry_status CHECK (status IN ('draft','reviewed','approved')),
	CONSTRAINT ck_inquiry_human CHECK (status <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND approved_by IS NOT NULL AND approved_at IS NOT NULL)),
	FOREIGN KEY(revision_of) REFERENCES inquiries (inquiry_id),
	FOREIGN KEY(reviewed_by) REFERENCES app_users (user_id),
	FOREIGN KEY(approved_by) REFERENCES app_users (user_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
)

;

CREATE INDEX ix_inquiries_year ON inquiries (year);


CREATE TABLE inquiry_evidence (
	evidence_id UUID NOT NULL,
	inquiry_id UUID NOT NULL,
	source_type VARCHAR(50) NOT NULL,
	source_id UUID NOT NULL,
	document_id UUID,
	excerpt TEXT NOT NULL,
	snapshot JSON NOT NULL,
	query_parameters JSON NOT NULL,
	created_by UUID NOT NULL,
	retrieved_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (evidence_id),
	FOREIGN KEY(inquiry_id) REFERENCES inquiries (inquiry_id),
	FOREIGN KEY(document_id) REFERENCES documents (document_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
)

;

CREATE INDEX ix_inquiry_evidence_inquiry_id ON inquiry_evidence (inquiry_id);


CREATE TABLE inquiry_candidates (
	candidate_id UUID NOT NULL,
	inquiry_id UUID NOT NULL,
	draft TEXT NOT NULL,
	claims JSON NOT NULL,
	model VARCHAR(200) NOT NULL,
	model_version VARCHAR(200) NOT NULL,
	input_provenance JSON NOT NULL,
	confidence VARCHAR(50),
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_by UUID NOT NULL,
	PRIMARY KEY (candidate_id),
	FOREIGN KEY(inquiry_id) REFERENCES inquiries (inquiry_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
)

;

CREATE INDEX ix_inquiry_candidates_inquiry_id ON inquiry_candidates (inquiry_id);


CREATE TABLE inquiry_rendered_forms (
	rendered_id UUID NOT NULL,
	inquiry_id UUID NOT NULL,
	form_template_id UUID NOT NULL,
	document_id UUID NOT NULL,
	manifest JSON NOT NULL,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (rendered_id),
	FOREIGN KEY(inquiry_id) REFERENCES inquiries (inquiry_id),
	FOREIGN KEY(form_template_id) REFERENCES form_templates (form_template_id),
	FOREIGN KEY(document_id) REFERENCES documents (document_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
)

;

CREATE FUNCTION inquiry_immutable_guard() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
 IF OLD.status = 'approved' THEN
  RAISE EXCEPTION 'approved inquiry is immutable; create revision' USING ERRCODE='23514';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END;
$guard$;
CREATE TRIGGER inquiry_immutable BEFORE UPDATE OR DELETE ON inquiries FOR EACH ROW EXECUTE FUNCTION inquiry_immutable_guard();
CREATE FUNCTION inquiry_snapshot_guard() RETURNS trigger LANGUAGE plpgsql AS $guard$
DECLARE parent_status text;
BEGIN
 EXECUTE 'SELECT status FROM ' || pg_catalog.quote_ident(TG_TABLE_SCHEMA) || '.inquiries WHERE inquiry_id=$1 FOR UPDATE' INTO parent_status USING OLD.inquiry_id;
 IF TG_OP='UPDATE' OR parent_status='approved' THEN
  RAISE EXCEPTION 'inquiry evidence/candidate snapshot immutable' USING ERRCODE='23514';
 END IF;
 RETURN OLD;
END;
$guard$;
CREATE TRIGGER inquiry_evidence_immutable BEFORE UPDATE OR DELETE ON inquiry_evidence FOR EACH ROW EXECUTE FUNCTION inquiry_snapshot_guard();
CREATE TRIGGER inquiry_candidate_immutable BEFORE UPDATE OR DELETE ON inquiry_candidates FOR EACH ROW EXECUTE FUNCTION inquiry_snapshot_guard();
