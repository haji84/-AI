-- Human-managed organization/personnel history; immutable employee IDs retained.
ALTER TABLE employees ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1;
CREATE TABLE IF NOT EXISTS organization_units (
    organization_id UUID PRIMARY KEY,
    code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    parent_id UUID REFERENCES organization_units(organization_id),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    version BIGINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS employee_assignments (
    assignment_id UUID PRIMARY KEY,
    employee_id UUID NOT NULL REFERENCES employees(employee_id),
    organization_id UUID NOT NULL REFERENCES organization_units(organization_id),
    title VARCHAR(200) NOT NULL,
    kind VARCHAR(20) NOT NULL DEFAULT 'primary' CHECK (kind IN ('primary','secondary')),
    valid_from DATE NOT NULL,
    valid_to DATE,
    version BIGINT NOT NULL DEFAULT 1,
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE INDEX IF NOT EXISTS employee_assignment_employee ON employee_assignments(employee_id);
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE employee_assignments ADD CONSTRAINT employee_primary_period_exclusion
    EXCLUDE USING gist (employee_id WITH =, daterange(valid_from, valid_to, '[]') WITH &&)
    WHERE (kind = 'primary');
CREATE TABLE IF NOT EXISTS employee_assignment_roles (
    assignment_id UUID NOT NULL REFERENCES employee_assignments(assignment_id),
    role_id UUID NOT NULL REFERENCES roles(role_id),
    PRIMARY KEY (assignment_id,role_id)
);
CREATE TABLE IF NOT EXISTS account_password_history (
    history_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(user_id),
    password_hash VARCHAR(500) NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS account_password_history_user ON account_password_history(user_id);
INSERT INTO permissions(code,description) VALUES
    ('personnel.read','職員・組織・人事履歴参照'),
    ('personnel.manage','職員・組織・人事辞令Human管理'),
    ('account.manage','アカウント・永続ロールHuman管理')
ON CONFLICT (code) DO NOTHING;
-- Existing system_admin is the explicit Human administrative authority.
INSERT INTO role_permissions(role_id,permission_id)
SELECT r.role_id,p.permission_id FROM roles r CROSS JOIN permissions p
WHERE r.code = 'system_admin' AND p.code IN ('personnel.read','personnel.manage','account.manage')
ON CONFLICT DO NOTHING;
