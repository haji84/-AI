-- Additive operational extension; source records and reviewed candidates stay separate.
ALTER TABLE emergency_clinical_flags ADD COLUMN version bigint NOT NULL DEFAULT 1;
ALTER TABLE emergency_clinical_flags ADD COLUMN candidate_fingerprint varchar(64) UNIQUE;
CREATE TABLE emergency_treatments (
 treatment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 emergency_patient_id uuid NOT NULL REFERENCES emergency_patients(emergency_patient_id),
 code varchar(50) NOT NULL,
 performed_at timestamptz,
 notes text,
 source_document_id uuid REFERENCES documents(document_id),
 created_by uuid NOT NULL REFERENCES app_users(user_id),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_emergency_treatments_patient ON emergency_treatments(emergency_patient_id);
CREATE TABLE emergency_report_drafts (
 report_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 emergency_case_id uuid NOT NULL REFERENCES emergency_cases(emergency_case_id),
 kind varchar(50) NOT NULL,
 content jsonb NOT NULL DEFAULT '{}',
 source_snapshot jsonb NOT NULL DEFAULT '{}',
 status varchar(30) NOT NULL DEFAULT 'draft',
 version bigint NOT NULL DEFAULT 1,
 created_by uuid NOT NULL REFERENCES app_users(user_id),
 reviewed_by uuid REFERENCES app_users(user_id),
 reviewed_at timestamptz,
 review_note text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_emergency_report_drafts_case ON emergency_report_drafts(emergency_case_id);
