-- Run B finance. Common contract/vendor/document tables remain authoritative.
-- Follows refreshed canonical main maximum043; production amounts remain NUMERIC(18,2).

CREATE TABLE finance_years (
	year_id UUID NOT NULL, 
	fiscal_year BIGINT NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	decimal_places BIGINT NOT NULL, 
	require_invoice_on_payment BOOLEAN NOT NULL, 
	account_levels JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	reason TEXT NOT NULL, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (year_id), 
	CONSTRAINT ck_finance_year_policy CHECK (currency IN ('JPY','USD','EUR') AND decimal_places BETWEEN 0 AND 2), 
	UNIQUE (fiscal_year), 
	FOREIGN KEY(approved_by) REFERENCES app_users (user_id)
);

CREATE TABLE finance_accounts (
	account_id UUID NOT NULL, 
	year_id UUID NOT NULL, 
	parent_id UUID, 
	level BIGINT NOT NULL, 
	code VARCHAR(100) NOT NULL, 
	name VARCHAR(300) NOT NULL, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (account_id), 
	CONSTRAINT uq_finance_account_code UNIQUE (year_id, code), 
	CONSTRAINT ck_finance_account_level CHECK (level BETWEEN 1 AND 32), 
	FOREIGN KEY(year_id) REFERENCES finance_years (year_id), 
	FOREIGN KEY(parent_id) REFERENCES finance_accounts (account_id)
);

CREATE INDEX ix_finance_accounts_year_id ON finance_accounts (year_id);

CREATE TABLE finance_contract_profiles (
	profile_id UUID NOT NULL, 
	contract_case_id UUID NOT NULL, 
	year_id UUID NOT NULL, 
	renewal_on DATE, 
	approved_evidence JSON, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (profile_id), 
	UNIQUE (contract_case_id), 
	FOREIGN KEY(contract_case_id) REFERENCES contract_cases (contract_case_id), 
	FOREIGN KEY(year_id) REFERENCES finance_years (year_id)
);

CREATE TABLE finance_candidates (
	candidate_id UUID NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	year_id UUID NOT NULL, 
	account_id UUID NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	amount NUMERIC(18, 2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	document_id UUID NOT NULL, 
	contract_case_id UUID, 
	counterparty_id UUID, 
	status VARCHAR(20) NOT NULL, 
	review_snapshot JSON NOT NULL, 
	reviewed_by UUID, 
	reason TEXT, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (candidate_id), 
	CONSTRAINT ck_finance_candidate CHECK (kind IN ('quote','request','estimate') AND amount >= 0), 
	FOREIGN KEY(year_id) REFERENCES finance_years (year_id), 
	FOREIGN KEY(account_id) REFERENCES finance_accounts (account_id), 
	FOREIGN KEY(document_id) REFERENCES documents (document_id), 
	FOREIGN KEY(contract_case_id) REFERENCES contract_cases (contract_case_id), 
	FOREIGN KEY(counterparty_id) REFERENCES contract_counterparties (counterparty_id), 
	FOREIGN KEY(reviewed_by) REFERENCES app_users (user_id)
);

CREATE TABLE finance_contract_amendments (
	amendment_id UUID NOT NULL, 
	contract_case_id UUID NOT NULL, 
	expected_contract_version BIGINT NOT NULL, 
	amount NUMERIC(18, 2) NOT NULL, 
	end_date DATE, 
	document_id UUID NOT NULL, 
	reason TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	review_snapshot JSON NOT NULL, 
	reviewed_by UUID, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (amendment_id), 
	CONSTRAINT ck_finance_contract_amendment_amount CHECK (amount >= 0), 
	FOREIGN KEY(contract_case_id) REFERENCES contract_cases (contract_case_id), 
	FOREIGN KEY(document_id) REFERENCES documents (document_id), 
	FOREIGN KEY(reviewed_by) REFERENCES app_users (user_id), 
	FOREIGN KEY(approved_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_finance_contract_amendments_contract_case_id ON finance_contract_amendments (contract_case_id);

CREATE TABLE finance_import_previews (
	preview_id UUID NOT NULL, 
	dataset VARCHAR(30) NOT NULL, 
	file_sha256 VARCHAR(64) NOT NULL, 
	source_document_id UUID NOT NULL, 
	row_data JSON NOT NULL, 
	created_by UUID NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	applied_ids JSON NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (preview_id), 
	CONSTRAINT uq_finance_import_hash UNIQUE (dataset, file_sha256), 
	FOREIGN KEY(source_document_id) REFERENCES documents (document_id), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE TABLE finance_procurement_events (
	event_id UUID NOT NULL, 
	contract_case_id UUID NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	occurred_on DATE NOT NULL, 
	description TEXT NOT NULL, 
	amount NUMERIC(18, 2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	document_id UUID NOT NULL, 
	related_event_id UUID, 
	status VARCHAR(20) NOT NULL, 
	review_snapshot JSON NOT NULL, 
	reviewed_by UUID, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	reason TEXT, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (event_id), 
	CONSTRAINT ck_finance_procurement_event CHECK (kind IN ('delivery','inspection','invoice') AND amount >= 0), 
	CONSTRAINT ck_finance_event_status CHECK (status IN ('draft','reviewed','approved','cancelled')), 
	CONSTRAINT ck_finance_event_human CHECK (status <> 'approved' OR (reviewed_by IS NOT NULL AND approved_by IS NOT NULL AND approved_at IS NOT NULL)), 
	FOREIGN KEY(contract_case_id) REFERENCES contract_cases (contract_case_id), 
	FOREIGN KEY(document_id) REFERENCES documents (document_id), 
	FOREIGN KEY(related_event_id) REFERENCES finance_procurement_events (event_id), 
	FOREIGN KEY(reviewed_by) REFERENCES app_users (user_id), 
	FOREIGN KEY(approved_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_finance_procurement_events_contract_case_id ON finance_procurement_events (contract_case_id);

CREATE TABLE finance_proposals (
	proposal_id UUID NOT NULL, 
	kind VARCHAR(30) NOT NULL, 
	account_id UUID NOT NULL, 
	to_account_id UUID, 
	amount NUMERIC(18, 2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	document_id UUID NOT NULL, 
	contract_case_id UUID, 
	commitment_id UUID, 
	invoice_id UUID, 
	reverses_id UUID, 
	idempotency_key VARCHAR(200) NOT NULL, 
	reason TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	review_snapshot JSON NOT NULL, 
	reviewed_by UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	created_by UUID NOT NULL, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (proposal_id), 
	CONSTRAINT ck_finance_proposal_kind CHECK (kind IN ('initial','amendment','transfer','commitment','payment','reversal')), 
	CONSTRAINT ck_finance_proposal_status CHECK (status IN ('draft','reviewed','approved','cancelled')), 
	CONSTRAINT ck_finance_proposal_amount CHECK (amount >= 0 OR kind='amendment'), 
	CONSTRAINT ck_finance_proposal_human CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND reviewed_by IS NOT NULL AND approved_at IS NOT NULL)), 
	FOREIGN KEY(account_id) REFERENCES finance_accounts (account_id), 
	FOREIGN KEY(to_account_id) REFERENCES finance_accounts (account_id), 
	FOREIGN KEY(document_id) REFERENCES documents (document_id), 
	FOREIGN KEY(contract_case_id) REFERENCES contract_cases (contract_case_id), 
	FOREIGN KEY(commitment_id) REFERENCES finance_proposals (proposal_id), 
	FOREIGN KEY(invoice_id) REFERENCES finance_procurement_events (event_id), 
	FOREIGN KEY(reverses_id) REFERENCES finance_proposals (proposal_id), 
	UNIQUE (idempotency_key), 
	FOREIGN KEY(reviewed_by) REFERENCES app_users (user_id), 
	FOREIGN KEY(approved_by) REFERENCES app_users (user_id), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_finance_proposals_account_id ON finance_proposals (account_id);

CREATE TABLE finance_journal (
	journal_id UUID NOT NULL, 
	version BIGINT NOT NULL, 
	proposal_id UUID NOT NULL, 
	account_id UUID NOT NULL, 
	allocated NUMERIC(18, 2) NOT NULL, 
	reserved NUMERIC(18, 2) NOT NULL, 
	spent NUMERIC(18, 2) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (journal_id), 
	CONSTRAINT uq_finance_posting_account UNIQUE (proposal_id, account_id), 
	FOREIGN KEY(proposal_id) REFERENCES finance_proposals (proposal_id), 
	FOREIGN KEY(account_id) REFERENCES finance_accounts (account_id)
);

CREATE INDEX ix_finance_journal_account_id ON finance_journal (account_id);

CREATE INDEX ix_finance_journal_proposal_id ON finance_journal (proposal_id);

CREATE TABLE finance_rendered_forms (
	rendered_id UUID NOT NULL, 
	proposal_id UUID NOT NULL, 
	form_template_id UUID NOT NULL, 
	document_id UUID NOT NULL, 
	manifest JSON NOT NULL, 
	created_by UUID NOT NULL, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (rendered_id), 
	FOREIGN KEY(proposal_id) REFERENCES finance_proposals (proposal_id), 
	FOREIGN KEY(form_template_id) REFERENCES form_templates (form_template_id), 
	FOREIGN KEY(document_id) REFERENCES documents (document_id), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

-- Approved source snapshots and postings are append-only, even for direct SQL.
CREATE FUNCTION finance_immutable_guard() RETURNS trigger LANGUAGE plpgsql AS '
BEGIN
    IF TG_TABLE_NAME = ''finance_journal'' THEN
        RAISE EXCEPTION ''financial journal is append-only'' USING ERRCODE = ''23514'';
    END IF;
    IF OLD.status = ''approved'' THEN
        RAISE EXCEPTION ''approved financial authority is immutable; append compensation'' USING ERRCODE = ''23514'';
    END IF;
    IF TG_OP = ''DELETE'' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
';
CREATE TRIGGER finance_journal_immutable BEFORE UPDATE OR DELETE ON finance_journal FOR EACH ROW EXECUTE FUNCTION finance_immutable_guard();
CREATE TRIGGER finance_proposal_immutable BEFORE UPDATE OR DELETE ON finance_proposals FOR EACH ROW EXECUTE FUNCTION finance_immutable_guard();
CREATE TRIGGER finance_policy_immutable BEFORE UPDATE OR DELETE ON finance_years FOR EACH ROW EXECUTE FUNCTION finance_immutable_guard();
CREATE TRIGGER finance_amendment_immutable BEFORE UPDATE OR DELETE ON finance_contract_amendments FOR EACH ROW EXECUTE FUNCTION finance_immutable_guard();
CREATE UNIQUE INDEX uq_finance_approved_reversal ON finance_proposals(reverses_id) WHERE status = 'approved' AND reverses_id IS NOT NULL;

CREATE FUNCTION finance_account_identity_guard() RETURNS trigger LANGUAGE plpgsql AS '
DECLARE p RECORD; y RECORD;
BEGIN
    IF TG_OP = ''UPDATE'' AND (NEW.year_id,NEW.parent_id,NEW.level,NEW.code) IS DISTINCT FROM (OLD.year_id,OLD.parent_id,OLD.level,OLD.code) THEN
        RAISE EXCEPTION ''account year, code and hierarchy are immutable'' USING ERRCODE = ''23514'';
    END IF;
    -- Resolve authority beside the triggered table, never through caller search_path.
    -- EXECUTE does not set FOUND; an absent row has a null nonnullable primary key.
    EXECUTE ''SELECT * FROM '' || pg_catalog.quote_ident(TG_TABLE_SCHEMA) || ''.finance_years WHERE year_id = $1'' INTO y USING NEW.year_id;
    IF y.year_id IS NULL OR y.status <> ''approved'' OR NEW.level > json_array_length(y.account_levels) THEN
        RAISE EXCEPTION ''account depth follows approved configured policy'' USING ERRCODE = ''23514'';
    END IF;
    IF NEW.level = 1 AND NEW.parent_id IS NOT NULL THEN
        RAISE EXCEPTION ''root account has no parent'' USING ERRCODE = ''23514'';
    ELSIF NEW.level > 1 THEN
        EXECUTE ''SELECT * FROM '' || pg_catalog.quote_ident(TG_TABLE_SCHEMA) || ''.finance_accounts WHERE account_id = $1'' INTO p USING NEW.parent_id;
        IF p.account_id IS NULL OR p.year_id <> NEW.year_id OR p.level <> NEW.level - 1 THEN
            RAISE EXCEPTION ''parent must be preceding level in same year'' USING ERRCODE = ''23514'';
        END IF;
    END IF;
    RETURN NEW;
END;
';
CREATE TRIGGER finance_account_identity BEFORE INSERT OR UPDATE ON finance_accounts FOR EACH ROW EXECUTE FUNCTION finance_account_identity_guard();

ALTER TABLE finance_proposals ADD CONSTRAINT ck_finance_proposal_finite CHECK (amount <> 'NaN'::numeric);
ALTER TABLE finance_candidates ADD CONSTRAINT ck_finance_candidate_finite CHECK (amount <> 'NaN'::numeric);
ALTER TABLE finance_contract_amendments ADD CONSTRAINT ck_finance_amendment_finite CHECK (amount <> 'NaN'::numeric);
ALTER TABLE finance_journal ADD CONSTRAINT ck_finance_journal_finite CHECK (allocated <> 'NaN'::numeric AND reserved <> 'NaN'::numeric AND spent <> 'NaN'::numeric);

CREATE TRIGGER finance_event_immutable BEFORE UPDATE OR DELETE ON finance_procurement_events FOR EACH ROW EXECUTE FUNCTION finance_immutable_guard();
ALTER TABLE finance_procurement_events ADD CONSTRAINT ck_finance_event_finite CHECK (amount <> 'NaN'::numeric);
ALTER TABLE finance_years ADD CONSTRAINT ck_finance_hierarchy_depth CHECK (json_array_length(account_levels) BETWEEN 1 AND 32);
