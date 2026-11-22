-- Private independent teacher records and immutable family/dataset registries.
-- No original/label text, model weights, or credentials are stored as JSON here.

CREATE TABLE emergency_training_family_members (
    report_id UUID PRIMARY KEY REFERENCES emergency_audit_reports(report_id),
    family_id UUID NOT NULL,
    created_by UUID NOT NULL REFERENCES app_users(user_id),
    created_employee_id UUID NOT NULL REFERENCES employees(employee_id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX ix_emergency_training_family_members_family_id
    ON emergency_training_family_members(family_id);

CREATE TABLE emergency_training_family_partitions (
    family_id UUID PRIMARY KEY,
    split VARCHAR(12) NOT NULL,
    created_by UUID NOT NULL REFERENCES app_users(user_id),
    created_employee_id UUID NOT NULL REFERENCES employees(employee_id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT em_training_partition CHECK (split IN ('train','validation','holdout'))
);

CREATE TABLE emergency_training_truths (
    truth_id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    request_sha256 VARCHAR(64) NOT NULL,
    supersedes_id UUID UNIQUE REFERENCES emergency_training_truths(truth_id),
    revision_id UUID NOT NULL REFERENCES emergency_audit_revisions(revision_id),
    task VARCHAR(20) NOT NULL,
    payload_cipher BYTEA NOT NULL,
    created_by UUID NOT NULL REFERENCES app_users(user_id),
    created_employee_id UUID NOT NULL REFERENCES employees(employee_id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT em_training_truth_task CHECK (task IN ('transcription','content_review'))
);
CREATE INDEX ix_emergency_training_truths_revision_id ON emergency_training_truths(revision_id);
CREATE UNIQUE INDEX em_training_truth_root ON emergency_training_truths(revision_id,task)
    WHERE supersedes_id IS NULL;

CREATE TABLE emergency_training_datasets (
    dataset_id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    request_sha256 VARCHAR(64) NOT NULL,
    supersedes_id UUID UNIQUE REFERENCES emergency_training_datasets(dataset_id),
    task VARCHAR(20) NOT NULL,
    manifest_sha256 VARCHAR(64) NOT NULL,
    manifest_cipher BYTEA NOT NULL,
    created_by UUID NOT NULL REFERENCES app_users(user_id),
    created_employee_id UUID NOT NULL REFERENCES employees(employee_id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT em_training_dataset_task CHECK (task IN ('transcription','content_review'))
);

CREATE TRIGGER emergency_training_family_immutable
    BEFORE UPDATE OR DELETE ON emergency_training_family_members
    FOR EACH ROW EXECUTE FUNCTION emergency_audit_immutable_record();
CREATE TRIGGER emergency_training_partition_immutable
    BEFORE UPDATE OR DELETE ON emergency_training_family_partitions
    FOR EACH ROW EXECUTE FUNCTION emergency_audit_immutable_record();
CREATE TRIGGER emergency_training_truth_immutable
    BEFORE UPDATE OR DELETE ON emergency_training_truths
    FOR EACH ROW EXECUTE FUNCTION emergency_audit_immutable_record();
CREATE TRIGGER emergency_training_dataset_immutable
    BEFORE UPDATE OR DELETE ON emergency_training_datasets
    FOR EACH ROW EXECUTE FUNCTION emergency_audit_immutable_record();
