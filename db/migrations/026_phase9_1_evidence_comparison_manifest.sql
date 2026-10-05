-- Phase 9.1: allow idempotent AI evidence-comparison manifests.

ALTER TABLE fire_investigation_ai_manifests
  DROP CONSTRAINT IF EXISTS fire_investigation_ai_manifests_manifest_type_check;

ALTER TABLE fire_investigation_ai_manifests
  ADD CONSTRAINT fire_investigation_ai_manifests_manifest_type_check
  CHECK (
    manifest_type IN (
      'photo_analysis',
      'transcript',
      'statement_draft',
      'report_draft',
      'evidence_comparison'
    )
  );
