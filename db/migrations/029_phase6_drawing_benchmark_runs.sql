-- Migration 029: Phase 6 drawing benchmark run registry.

CREATE TABLE IF NOT EXISTS drawing_benchmark_runs (
  drawing_benchmark_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  benchmark_format varchar(120) NOT NULL,
  dataset_label varchar(300) NOT NULL,
  manifest_sha256 varchar(64),
  result_sha256 varchar(64) NOT NULL,
  drawing_count integer NOT NULL DEFAULT 0,
  result_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  review_status varchar(30) NOT NULL DEFAULT 'pending'
    CHECK (review_status IN ('pending','reviewed')),
  human_decision varchar(30)
    CHECK (human_decision IS NULL OR human_decision IN ('accepted_baseline','rejected_baseline')),
  review_notes text,
  version bigint NOT NULL DEFAULT 1,
  created_by uuid REFERENCES app_users(user_id),
  reviewed_by uuid REFERENCES app_users(user_id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_drawing_benchmark_result_sha
  ON drawing_benchmark_runs(result_sha256);

CREATE INDEX IF NOT EXISTS idx_drawing_benchmark_created
  ON drawing_benchmark_runs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_drawing_benchmark_review
  ON drawing_benchmark_runs(review_status, created_at DESC);
