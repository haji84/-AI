-- Additive Human-gated violation/correction domain; inspection observations remain independent.
CREATE TABLE violation_cases (
	case_id UUID NOT NULL,
	building_id UUID NOT NULL,
	finding_id UUID,
	supersedes_case_id UUID,
	observed_on DATE NOT NULL,
	possible_issue TEXT NOT NULL,
	missing_information JSON NOT NULL,
	confirmation_steps JSON NOT NULL,
	rule_version_ids JSON NOT NULL,
	evidence_document_ids JSON NOT NULL,
	procedure_document_ids JSON NOT NULL,
	origin VARCHAR(20) NOT NULL,
	ai_provenance JSON NOT NULL,
	status VARCHAR(30) NOT NULL,
	review_snapshot JSON NOT NULL,
	reviewed_by UUID,
	reviewed_at TIMESTAMP WITH TIME ZONE,
	confirmed_by UUID,
	confirmed_at TIMESTAMP WITH TIME ZONE,
	last_human_reason TEXT,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	version BIGINT NOT NULL,
	completed_by UUID,
	completed_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (case_id),
	CONSTRAINT violation_case_status CHECK (status IN ('candidate','reviewed','confirmed','completed','resolved_candidate','withdrawn','superseded')),
	CONSTRAINT violation_case_origin CHECK (origin IN ('human','ai')),
	CONSTRAINT violation_case_version CHECK (version >= 1),
	FOREIGN KEY(building_id) REFERENCES facilities (building_id),
	FOREIGN KEY(finding_id) REFERENCES inspection_findings (finding_id),
	FOREIGN KEY(supersedes_case_id) REFERENCES violation_cases (case_id),
	FOREIGN KEY(reviewed_by) REFERENCES app_users (user_id),
	FOREIGN KEY(confirmed_by) REFERENCES app_users (user_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id),
	FOREIGN KEY(completed_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_violation_cases_building_id ON violation_cases (building_id);

CREATE INDEX ix_violation_cases_status ON violation_cases (status);

CREATE TABLE violation_measures (
	measure_id UUID NOT NULL,
	case_id UUID NOT NULL,
	kind VARCHAR(30) NOT NULL,
	instruction TEXT NOT NULL,
	official_reference VARCHAR(400),
	due_on DATE,
	document_ids JSON NOT NULL,
	procedure_document_ids JSON NOT NULL,
	status VARCHAR(30) NOT NULL,
	review_snapshot JSON NOT NULL,
	reviewed_by UUID,
	reviewed_at TIMESTAMP WITH TIME ZONE,
	confirmed_by UUID,
	confirmed_at TIMESTAMP WITH TIME ZONE,
	withdrawal_snapshot JSON NOT NULL,
	last_human_reason TEXT,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	version BIGINT NOT NULL,
	PRIMARY KEY (measure_id),
	CONSTRAINT violation_measure_kind CHECK (kind IN ('guidance','order','disposition')),
	CONSTRAINT violation_measure_status CHECK (status IN ('draft','reviewed','confirmed','cancelled','withdrawn')),
	FOREIGN KEY(case_id) REFERENCES violation_cases (case_id),
	FOREIGN KEY(reviewed_by) REFERENCES app_users (user_id),
	FOREIGN KEY(confirmed_by) REFERENCES app_users (user_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_violation_measures_case_id ON violation_measures (case_id);

CREATE TABLE corrective_actions (
	action_id UUID NOT NULL,
	case_id UUID NOT NULL,
	measure_id UUID,
	description TEXT NOT NULL,
	due_on DATE,
	status VARCHAR(30) NOT NULL,
	verification_passed BOOLEAN,
	verification_snapshot JSON NOT NULL,
	verified_by UUID,
	verified_at TIMESTAMP WITH TIME ZONE,
	completed_by UUID,
	completed_at TIMESTAMP WITH TIME ZONE,
	completion_snapshot JSON NOT NULL,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	version BIGINT NOT NULL,
	PRIMARY KEY (action_id),
	CONSTRAINT corrective_action_status CHECK (status IN ('open','responded','verified','completed','cancelled')),
	FOREIGN KEY(case_id) REFERENCES violation_cases (case_id),
	FOREIGN KEY(measure_id) REFERENCES violation_measures (measure_id),
	FOREIGN KEY(verified_by) REFERENCES app_users (user_id),
	FOREIGN KEY(completed_by) REFERENCES app_users (user_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_corrective_actions_case_id ON corrective_actions (case_id);

CREATE INDEX ix_corrective_actions_due_on ON corrective_actions (due_on);

CREATE TABLE correction_events (
	event_id UUID NOT NULL,
	action_id UUID NOT NULL,
	sequence_no BIGINT NOT NULL,
	kind VARCHAR(30) NOT NULL,
	text TEXT NOT NULL,
	human_reason TEXT NOT NULL,
	verification_passed BOOLEAN,
	source_snapshot JSON NOT NULL,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (event_id),
	CONSTRAINT correction_event_sequence UNIQUE (action_id, sequence_no),
	CONSTRAINT correction_event_kind CHECK (kind IN ('instruction','response','verification','completion','cancel','reopen')),
	FOREIGN KEY(action_id) REFERENCES corrective_actions (action_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_correction_events_action_id ON correction_events (action_id);
