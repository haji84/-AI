-- Phase 7.4: render approved fire report drafts into registered official form templates.

CREATE TABLE IF NOT EXISTS fire_report_exports (
  fire_report_export_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fire_report_draft_id uuid NOT NULL
    REFERENCES fire_report_drafts(fire_report_draft_id) ON DELETE CASCADE,
  form_template_id uuid NOT NULL REFERENCES form_templates(form_template_id),
  template_document_id uuid NOT NULL REFERENCES documents(document_id),
  template_sha256 varchar(64) NOT NULL,
  report_draft_version bigint NOT NULL,
  request_sha256 varchar(64) NOT NULL UNIQUE,
  output_format varchar(30) NOT NULL,
  field_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  render_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  output_document_id uuid REFERENCES documents(document_id),
  status varchar(30) NOT NULL DEFAULT 'rendered'
    CHECK (status IN ('rendered','verified','failed')),
  error_detail text,
  created_by uuid REFERENCES app_users(user_id),
  verified_by uuid REFERENCES app_users(user_id),
  verified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fire_report_exports_draft
  ON fire_report_exports(fire_report_draft_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fire_report_exports_output
  ON fire_report_exports(output_document_id);
