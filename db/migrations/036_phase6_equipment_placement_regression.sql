-- Migration 036: Phase 6 equipment placement regression cases and runs.

CREATE TABLE IF NOT EXISTS equipment_placement_test_cases (
  equipment_placement_test_case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  worklist_sha256 varchar(64) NOT NULL,
  name varchar(300) NOT NULL,
  input_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  rooms jsonb NOT NULL DEFAULT '[]'::jsonb,
  equipment_type_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  expected_results jsonb NOT NULL DEFAULT '[]'::jsonb,
  notes text,
  status varchar(30) NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','reviewed','rejected')),
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_equipment_placement_test_cases_batch
  ON equipment_placement_test_cases(worklist_sha256, status, created_at DESC);

CREATE TABLE IF NOT EXISTS equipment_placement_test_runs (
  equipment_placement_test_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  worklist_sha256 varchar(64) NOT NULL,
  result_sha256 varchar(64) NOT NULL,
  case_count integer NOT NULL DEFAULT 0,
  passed_case_count integer NOT NULL DEFAULT 0,
  failed_case_count integer NOT NULL DEFAULT 0,
  state_mismatch_case_count integer NOT NULL DEFAULT 0,
  marker_mismatch_case_count integer NOT NULL DEFAULT 0,
  constraint_mismatch_case_count integer NOT NULL DEFAULT 0,
  result_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  review_status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (review_status IN ('pending','reviewed')),
  human_decision varchar(30)
    CHECK (
      human_decision IS NULL
      OR human_decision IN ('accepted_regression','rejected_regression')
    ),
  review_notes text,
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_equipment_placement_test_run_result_sha
  ON equipment_placement_test_runs(result_sha256);

CREATE INDEX IF NOT EXISTS idx_equipment_placement_test_runs_batch
  ON equipment_placement_test_runs(worklist_sha256, created_at DESC);
