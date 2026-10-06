-- Workforce/duty management. Canonical Employee/Organization/Assignment tables remain authoritative.
CREATE TABLE IF NOT EXISTS workforce_shift_types (
    shift_type_id UUID PRIMARY KEY,
    code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    timezone_name VARCHAR(80) NOT NULL DEFAULT 'Asia/Tokyo',
    cross_midnight BOOLEAN NOT NULL DEFAULT FALSE,
    payable_minutes BIGINT NOT NULL CHECK (payable_minutes > 0 AND payable_minutes <= 2880),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS workforce_employee_qualifications (
    qualification_id UUID PRIMARY KEY,
    employee_id UUID NOT NULL REFERENCES employees(employee_id),
    code VARCHAR(100) NOT NULL,
    label VARCHAR(200) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    document_id UUID REFERENCES documents(document_id),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID NOT NULL REFERENCES app_users(user_id),
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(employee_id,code,valid_from),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE INDEX IF NOT EXISTS workforce_qualification_employee ON workforce_employee_qualifications(employee_id);

CREATE TABLE IF NOT EXISTS workforce_staffing_rules (
    staffing_rule_id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organization_units(organization_id),
    shift_type_id UUID NOT NULL REFERENCES workforce_shift_types(shift_type_id),
    min_staff BIGINT NOT NULL CHECK (min_staff > 0),
    qualification_code VARCHAR(100),
    effective_from DATE NOT NULL,
    effective_to DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','approved','cancelled')),
    rule_note TEXT,
    created_by UUID NOT NULL REFERENCES app_users(user_id),
    reviewed_by UUID REFERENCES app_users(user_id),
    reviewed_at TIMESTAMPTZ,
    approved_by UUID REFERENCES app_users(user_id),
    approved_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
);
CREATE INDEX IF NOT EXISTS workforce_staffing_rule_scope ON workforce_staffing_rules(organization_id,shift_type_id,effective_from);

CREATE TABLE IF NOT EXISTS workforce_roster_entries (
    roster_entry_id UUID PRIMARY KEY,
    employee_id UUID NOT NULL REFERENCES employees(employee_id),
    organization_id UUID NOT NULL REFERENCES organization_units(organization_id),
    assignment_id UUID REFERENCES employee_assignments(assignment_id),
    assignment_version BIGINT,
    shift_type_id UUID NOT NULL REFERENCES workforce_shift_types(shift_type_id),
    work_date DATE NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    payable_minutes BIGINT NOT NULL CHECK (payable_minutes > 0),
    support_placement BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','approved','cancelled')),
    note TEXT,
    document_id UUID REFERENCES documents(document_id),
    created_by UUID NOT NULL REFERENCES app_users(user_id),
    reviewed_by UUID REFERENCES app_users(user_id),
    reviewed_at TIMESTAMPTZ,
    approved_by UUID REFERENCES app_users(user_id),
    approved_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (ends_at > starts_at)
);
CREATE INDEX IF NOT EXISTS workforce_roster_employee_period ON workforce_roster_entries(employee_id,starts_at,ends_at);
CREATE INDEX IF NOT EXISTS workforce_roster_org_date ON workforce_roster_entries(organization_id,work_date);

CREATE TABLE IF NOT EXISTS workforce_leave_entries (
    leave_entry_id UUID PRIMARY KEY,
    employee_id UUID NOT NULL REFERENCES employees(employee_id),
    leave_type VARCHAR(30) NOT NULL CHECK (leave_type IN ('annual','special','compensatory')),
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('grant','use','adjustment_add','adjustment_subtract','expire')),
    quantity_minutes BIGINT NOT NULL CHECK (quantity_minutes > 0),
    effective_on DATE NOT NULL,
    expires_on DATE,
    private_reason TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','approved','cancelled')),
    created_by UUID NOT NULL REFERENCES app_users(user_id),
    reviewed_by UUID REFERENCES app_users(user_id),
    reviewed_at TIMESTAMPTZ,
    approved_by UUID REFERENCES app_users(user_id),
    approved_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expires_on IS NULL OR expires_on >= effective_on)
);
CREATE INDEX IF NOT EXISTS workforce_leave_employee_date ON workforce_leave_entries(employee_id,effective_on);

CREATE TABLE IF NOT EXISTS workforce_attendance (
    attendance_id UUID PRIMARY KEY,
    employee_id UUID NOT NULL REFERENCES employees(employee_id),
    roster_entry_id UUID REFERENCES workforce_roster_entries(roster_entry_id),
    work_date DATE NOT NULL,
    check_in_at TIMESTAMPTZ NOT NULL,
    check_out_at TIMESTAMPTZ,
    worked_minutes BIGINT,
    calculation JSON NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','approved','cancelled')),
    created_by UUID NOT NULL REFERENCES app_users(user_id),
    reviewed_by UUID REFERENCES app_users(user_id),
    reviewed_at TIMESTAMPTZ,
    approved_by UUID REFERENCES app_users(user_id),
    approved_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (check_out_at IS NULL OR check_out_at > check_in_at),
    CHECK (worked_minutes IS NULL OR worked_minutes >= 0)
);
CREATE INDEX IF NOT EXISTS workforce_attendance_employee_date ON workforce_attendance(employee_id,work_date);

CREATE TABLE IF NOT EXISTS workforce_time_entries (
    time_entry_id UUID PRIMARY KEY,
    employee_id UUID NOT NULL REFERENCES employees(employee_id),
    attendance_id UUID REFERENCES workforce_attendance(attendance_id),
    kind VARCHAR(30) NOT NULL CHECK (kind IN ('overtime','comp_grant','comp_use')),
    minutes BIGINT NOT NULL CHECK (minutes > 0),
    occurred_on DATE NOT NULL,
    note TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','approved','cancelled')),
    created_by UUID NOT NULL REFERENCES app_users(user_id),
    reviewed_by UUID REFERENCES app_users(user_id),
    reviewed_at TIMESTAMPTZ,
    approved_by UUID REFERENCES app_users(user_id),
    approved_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS workforce_time_employee_date ON workforce_time_entries(employee_id,occurred_on);

CREATE TABLE IF NOT EXISTS workforce_import_previews (
    preview_id UUID PRIMARY KEY,
    dataset VARCHAR(30) NOT NULL CHECK (dataset IN ('rosters')),
    schema_version VARCHAR(30) NOT NULL,
    filename TEXT NOT NULL,
    file_sha256 VARCHAR(64) NOT NULL,
    document_id UUID REFERENCES documents(document_id),
    row_data JSON NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'preview' CHECK (status IN ('preview','applied')),
    created_by UUID NOT NULL REFERENCES app_users(user_id),
    expires_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO permissions(code,description) VALUES
 ('workforce.read','勤務・配置・休暇・勤怠参照'),
 ('workforce.create','勤務表・休暇・勤怠草案作成'),
 ('workforce.update','勤務表・休暇・勤怠草案更新'),
 ('workforce.review','勤務・休暇・勤怠Human確認'),
 ('workforce.approve','勤務・休暇・勤怠Human承認'),
 ('workforce.admin','勤務区分・最低人員Rule・資格管理'),
 ('workforce.import','勤務表取込'),
 ('workforce.export','勤務データ出力'),
 ('workforce.aggregate','勤務集計参照')
ON CONFLICT (code) DO NOTHING;
INSERT INTO role_permissions(role_id,permission_id)
SELECT r.role_id,p.permission_id FROM roles r CROSS JOIN permissions p
WHERE r.code='system_admin' AND p.code LIKE 'workforce.%'
ON CONFLICT DO NOTHING;
