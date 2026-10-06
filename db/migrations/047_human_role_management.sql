-- Human permission policy; existing roles remain active/version1.
ALTER TABLE roles ADD COLUMN active boolean NOT NULL DEFAULT true;
ALTER TABLE roles ADD COLUMN version bigint NOT NULL DEFAULT 1;
CREATE TABLE human_role_rules (
	rule_id UUID NOT NULL,
	name VARCHAR(200) NOT NULL,
	role_id UUID NOT NULL,
	organization_id UUID,
	title VARCHAR(200),
	kind VARCHAR(20),
	valid_from DATE NOT NULL,
	valid_to DATE,
	active BOOLEAN NOT NULL,
	source_document_id UUID,
	source_sha256 VARCHAR(64),
	reason TEXT NOT NULL,
	created_by UUID NOT NULL,
	version BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (rule_id),
	CONSTRAINT role_rule_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
	CONSTRAINT role_rule_kind CHECK (kind IS NULL OR kind IN ('primary','secondary')),
	CONSTRAINT role_rule_exact_selector CHECK (organization_id IS NOT NULL OR title IS NOT NULL),
	CONSTRAINT role_rule_source CHECK ((source_document_id IS NULL AND source_sha256 IS NULL) OR (source_document_id IS NOT NULL AND source_sha256 IS NOT NULL)),
	FOREIGN KEY(role_id) REFERENCES roles (role_id),
	FOREIGN KEY(organization_id) REFERENCES organization_units (organization_id),
	FOREIGN KEY(source_document_id) REFERENCES documents (document_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);
CREATE INDEX ix_human_role_rules_role_id ON human_role_rules (role_id);
CREATE TABLE temporary_role_grants (
	grant_id UUID NOT NULL,
	user_id UUID NOT NULL,
	role_id UUID NOT NULL,
	acting_for_employee_id UUID,
	valid_from DATE NOT NULL,
	valid_to DATE NOT NULL,
	source_document_id UUID,
	source_sha256 VARCHAR(64),
	reason TEXT NOT NULL,
	created_by UUID NOT NULL,
	version BIGINT NOT NULL,
	revoked_at TIMESTAMP WITH TIME ZONE,
	revoked_by UUID,
	revocation_reason TEXT,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (grant_id),
	CONSTRAINT temporary_role_dates CHECK (valid_to >= valid_from),
	CONSTRAINT temporary_role_source CHECK ((source_document_id IS NULL AND source_sha256 IS NULL) OR (source_document_id IS NOT NULL AND source_sha256 IS NOT NULL)),
	FOREIGN KEY(user_id) REFERENCES app_users (user_id),
	FOREIGN KEY(role_id) REFERENCES roles (role_id),
	FOREIGN KEY(acting_for_employee_id) REFERENCES employees (employee_id),
	FOREIGN KEY(source_document_id) REFERENCES documents (document_id),
	FOREIGN KEY(created_by) REFERENCES app_users (user_id),
	FOREIGN KEY(revoked_by) REFERENCES app_users (user_id)
);
CREATE INDEX ix_temporary_role_grants_role_id ON temporary_role_grants (role_id);
CREATE INDEX ix_temporary_role_grants_user_id ON temporary_role_grants (user_id);
