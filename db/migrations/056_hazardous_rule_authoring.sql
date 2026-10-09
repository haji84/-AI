-- Additive hazardous candidate Rule authoring; no legal policy or thresholds seeded.
ALTER TABLE legal_rules DROP CONSTRAINT ck_legal_rules_domain_v2;
ALTER TABLE legal_rules ADD CONSTRAINT ck_legal_rules_domain_v3 CHECK (domain IN (
    'submission_requirement', 'equipment_requirement', 'occupancy_classification',
    'equipment_placement', 'hazardous_requirement'
));
ALTER TABLE legal_rule_draft_candidates DROP CONSTRAINT ck_legal_rule_draft_candidates_domain_v2;
ALTER TABLE legal_rule_draft_candidates ADD CONSTRAINT ck_legal_rule_draft_candidates_domain_v3 CHECK (domain IN (
    'submission_requirement', 'equipment_requirement', 'occupancy_classification',
    'equipment_placement', 'hazardous_requirement'
));

CREATE TABLE hazardous_rule_approvals (
    legal_rule_version_id uuid PRIMARY KEY REFERENCES legal_rule_versions(legal_rule_version_id),
    rule_snapshot jsonb NOT NULL,
    source_snapshot jsonb NOT NULL,
    citations jsonb NOT NULL,
    approved_by uuid NOT NULL REFERENCES app_users(user_id),
    approved_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT hazardous_rule_approval_citations CHECK (jsonb_typeof(citations) = 'array' AND jsonb_array_length(citations) > 0)
);
CREATE FUNCTION hazardous_rule_approval_immutable() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
    RAISE EXCEPTION 'hazardous Rule approval evidence is immutable' USING ERRCODE='23514';
    RETURN OLD;
END;
$guard$;
CREATE TRIGGER hazardous_rule_approval_immutable BEFORE UPDATE OR DELETE ON hazardous_rule_approvals
    FOR EACH ROW EXECUTE FUNCTION hazardous_rule_approval_immutable();
