-- Phase 1 core foundation (PostgreSQL)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS employees (
  employee_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_code text UNIQUE,
  display_name text NOT NULL,
  organization_unit text,
  title text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_users (
  user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid UNIQUE REFERENCES employees(employee_id),
  username text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  version bigint NOT NULL DEFAULT 1,
  last_login_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS roles (
  role_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  description text,
  system_role boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS permissions (
  permission_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  description text
);

CREATE TABLE IF NOT EXISTS user_roles (
  user_id uuid NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
  role_id uuid NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
  PRIMARY KEY(user_id, role_id)
);

CREATE TABLE IF NOT EXISTS role_permissions (
  role_id uuid NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
  permission_id uuid NOT NULL REFERENCES permissions(permission_id) ON DELETE CASCADE,
  PRIMARY KEY(role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_sessions (
  session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  client_info jsonb
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(token_hash);

CREATE TABLE IF NOT EXISTS facilities (
  building_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legacy_internal_key text UNIQUE,
  legacy_category_key text,
  legacy_serial_no text,
  legacy_global_serial text,
  name text NOT NULL,
  phone text,
  address text,
  status text NOT NULL DEFAULT 'active',
  version bigint NOT NULL DEFAULT 1,
  deleted_at timestamptz,
  deleted_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_facilities_name ON facilities(name);
CREATE INDEX IF NOT EXISTS idx_facilities_status ON facilities(status);

CREATE TABLE IF NOT EXISTS documents (
  document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id uuid REFERENCES facilities(building_id),
  storage_path text NOT NULL,
  original_filename text NOT NULL,
  sha256 text NOT NULL,
  size_bytes bigint,
  mime_type text,
  document_type text,
  created_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(storage_path),
  UNIQUE(sha256, storage_path)
);
CREATE INDEX IF NOT EXISTS idx_documents_building ON documents(building_id);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);

CREATE TABLE IF NOT EXISTS source_files (
  source_file_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_kind text NOT NULL,
  original_filename text NOT NULL,
  storage_path text,
  sha256 text NOT NULL,
  size_bytes bigint,
  imported_by uuid REFERENCES app_users(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(source_kind, sha256)
);

CREATE TABLE IF NOT EXISTS import_runs (
  import_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_file_id uuid REFERENCES source_files(source_file_id),
  import_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  started_by uuid REFERENCES app_users(user_id),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  inserted_count integer NOT NULL DEFAULT 0,
  updated_count integer NOT NULL DEFAULT 0,
  skipped_count integer NOT NULL DEFAULT 0,
  error_count integer NOT NULL DEFAULT 0,
  details jsonb
);

-- Keep audit append-only at the application permission layer.
CREATE TABLE IF NOT EXISTS audit_logs (
  audit_id bigserial PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  request_id uuid,
  user_id uuid REFERENCES app_users(user_id),
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id text,
  before_data jsonb,
  after_data jsonb,
  success boolean NOT NULL DEFAULT true,
  ai_used boolean NOT NULL DEFAULT false,
  ai_model_version text,
  client_info jsonb
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_occurred ON audit_logs(occurred_at DESC);

-- Phase 1 seed permissions. More permissions are added by module migrations.
INSERT INTO permissions(code, description) VALUES
 ('system.health.read','ヘルスチェック参照'),
 ('facility.read','対象物参照'),
 ('facility.create','対象物新規登録'),
 ('facility.update','対象物更新'),
 ('facility.restore','対象物復元'),
 ('document.create','原本メタデータ登録'),
 ('document.read','原本メタデータ参照'),
 ('audit.read','監査ログ参照'),
 ('emergency.import','救急データ取込'),
 ('emergency.report.read','救急集計参照')
ON CONFLICT (code) DO NOTHING;