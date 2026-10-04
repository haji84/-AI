-- Phase 1 extensibility, Human Change Request, official forms, and contract foundation.

CREATE TABLE IF NOT EXISTS module_definitions (
  module_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1.0.0',
  status text NOT NULL DEFAULT 'active',
  manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feature_flags (
  feature_flag_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text NOT NULL UNIQUE,
  module_code text,
  enabled boolean NOT NULL DEFAULT false,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  version bigint NOT NULL DEFAULT 1,
  updated_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feature_flags_module ON feature_flags(module_code);

CREATE TABLE IF NOT EXISTS form_templates (
  form_template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  template_code text NOT NULL,
  name text NOT NULL,
  module_code text NOT NULL,
  document_id uuid NOT NULL REFERENCES documents(document_id),
  version_label text NOT NULL,
  issuer text,
  effective_from date,
  effective_to date,
  field_mapping jsonb NOT NULL DEFAULT '{}'::jsonb,
  print_settings jsonb NOT NULL DEFAULT '{}'::jsonb,
  modification_policy text NOT NULL DEFAULT 'fill_only',
  status text NOT NULL DEFAULT 'active',
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(template_code, version_label)
);
CREATE INDEX IF NOT EXISTS idx_form_templates_code ON form_templates(template_code);
CREATE INDEX IF NOT EXISTS idx_form_templates_module ON form_templates(module_code);

CREATE TABLE IF NOT EXISTS change_requests (
  change_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  request_text text NOT NULL,
  target_module text,
  target_surface text,
  status text NOT NULL DEFAULT 'draft',
  risk_level text NOT NULL DEFAULT 'unassessed',
  analysis jsonb NOT NULL DEFAULT '{}'::jsonb,
  proposed_changes jsonb NOT NULL DEFAULT '{}'::jsonb,
  acceptance_criteria jsonb NOT NULL DEFAULT '[]'::jsonb,
  sandbox_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  requester_id uuid REFERENCES app_users(user_id),
  approved_by uuid REFERENCES app_users(user_id),
  approved_at timestamptz,
  version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_change_requests_status ON change_requests(status);
CREATE INDEX IF NOT EXISTS idx_change_requests_module ON change_requests(target_module);

CREATE TABLE IF NOT EXISTS extension_intakes (
  extension_intake_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_id uuid NOT NULL REFERENCES documents(document_id),
  requested_goal text,
  target_module text,
  detected_kind text,
  status text NOT NULL DEFAULT 'pending_analysis',
  analysis jsonb NOT NULL DEFAULT '{}'::jsonb,
  diff jsonb NOT NULL DEFAULT '{}'::jsonb,
  proposed_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  sandbox_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  submitted_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_extension_intakes_status ON extension_intakes(status);

CREATE TABLE IF NOT EXISTS contract_counterparties (
  counterparty_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  registration_no text,
  address text,
  contact text,
  active boolean NOT NULL DEFAULT true,
  version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_contract_counterparties_name ON contract_counterparties(name);

CREATE TABLE IF NOT EXISTS contract_cases (
  contract_case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_no text UNIQUE,
  title text NOT NULL,
  counterparty_id uuid REFERENCES contract_counterparties(counterparty_id),
  contract_method text,
  amount numeric(18,2),
  currency text NOT NULL DEFAULT 'JPY',
  start_date date,
  end_date date,
  status text NOT NULL DEFAULT 'draft',
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  approved_by uuid REFERENCES app_users(user_id),
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_contract_cases_title ON contract_cases(title);
CREATE INDEX IF NOT EXISTS idx_contract_cases_status ON contract_cases(status);

CREATE TABLE IF NOT EXISTS contract_documents (
  contract_document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_case_id uuid NOT NULL REFERENCES contract_cases(contract_case_id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(document_id),
  document_role text NOT NULL,
  form_template_id uuid REFERENCES form_templates(form_template_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(contract_case_id, document_id)
);

CREATE TABLE IF NOT EXISTS contract_changes (
  contract_change_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_case_id uuid NOT NULL REFERENCES contract_cases(contract_case_id) ON DELETE CASCADE,
  sequence_no integer NOT NULL,
  reason text,
  before_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(contract_case_id, sequence_no)
);

INSERT INTO permissions(code, description) VALUES
 ('extension.read','拡張・取込参照'),
 ('extension.create','拡張取込・Change Request作成'),
 ('extension.review','拡張案レビュー'),
 ('extension.apply','拡張案本番反映'),
 ('template.read','正式様式参照'),
 ('template.manage','正式様式登録・Version管理'),
 ('contract.read','契約案件参照'),
 ('contract.create','契約案件作成'),
 ('contract.update','契約案件更新'),
 ('contract.approve','契約案件正式承認')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS import_adapter_definitions (
  import_adapter_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  module_code text NOT NULL,
  source_kind text NOT NULL,
  version text NOT NULL,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_import_adapters_module ON import_adapter_definitions(module_code);
CREATE INDEX IF NOT EXISTS idx_import_adapters_source_kind ON import_adapter_definitions(source_kind);

CREATE TABLE IF NOT EXISTS extension_deployments (
  extension_deployment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  change_request_id uuid NOT NULL REFERENCES change_requests(change_request_id),
  module_code text NOT NULL,
  release_version text NOT NULL,
  previous_version text,
  migration_version text,
  feature_flag_key text,
  status text NOT NULL DEFAULT 'applied',
  rollback_of uuid REFERENCES extension_deployments(extension_deployment_id),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  applied_by uuid REFERENCES app_users(user_id),
  applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_extension_deployments_cr ON extension_deployments(change_request_id);
CREATE INDEX IF NOT EXISTS idx_extension_deployments_module ON extension_deployments(module_code);