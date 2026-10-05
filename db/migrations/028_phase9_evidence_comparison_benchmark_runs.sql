-- Migration 028: Phase 9 evidence-comparison benchmark run registry.
-- Benchmark evidence remains separate from reviewed investigation evidence and formal cause/report decisions.

CREATE TABLE IF NOT EXISTS fire_evidence_comparison_benchmark_runs (
  fire_evidence_comparison_benchmark_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  benchmark_format varchar(120) NOT NULL,
  dataset_label varchar(300) NOT NULL,
  manifest_sha256 varchar(64),
  result_sha256 varchar(64) NOT NULL,
  case_count integer NOT NULL DEFAULT 0,
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

CREATE UNIQUE INDEX IF NOT EXISTS uq_fire_evidence_comparison_benchmark_result_sha
  ON fire_evidence_comparison_benchmark_runs(result_sha256);

CREATE INDEX IF NOT EXISTS idx_fire_evidence_comparison_benchmark_created
  ON fire_evidence_comparison_benchmark_runs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_fire_evidence_comparison_benchmark_review
  ON fire_evidence_comparison_benchmark_runs(review_status, created_at DESC);
