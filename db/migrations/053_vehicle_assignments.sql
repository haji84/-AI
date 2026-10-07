-- Bounded current Vehicle-to-OrganizationUnit registry metadata.
-- Human-recorded reference text is not verified original-document evidence.
CREATE TABLE operation_vehicle_assignment_changes (
    assignment_change_id UUID DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    vehicle_id UUID NOT NULL REFERENCES operation_vehicles(vehicle_id),
    action VARCHAR(20) NOT NULL,
    before_organization_id UUID REFERENCES organization_units(organization_id),
    after_organization_id UUID REFERENCES organization_units(organization_id),
    before_organization JSON,
    after_organization JSON,
    vehicle_version_before BIGINT NOT NULL,
    vehicle_version_after BIGINT NOT NULL,
    changed_by UUID NOT NULL REFERENCES app_users(user_id),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    reason TEXT NOT NULL,
    source_evidence TEXT NOT NULL,
    human_acknowledged BOOLEAN NOT NULL,
    CONSTRAINT uq_vehicle_assignment_version UNIQUE(vehicle_id, vehicle_version_after),
    CONSTRAINT ck_vehicle_assignment_action CHECK(action IN ('assign','unassign')),
    CONSTRAINT ck_vehicle_assignment_versions CHECK(vehicle_version_before >= 1 AND vehicle_version_after = vehicle_version_before + 1),
    CONSTRAINT ck_vehicle_assignment_target CHECK((action = 'assign' AND after_organization_id IS NOT NULL AND after_organization IS NOT NULL) OR (action = 'unassign' AND after_organization_id IS NULL AND after_organization IS NULL)),
    CONSTRAINT ck_vehicle_assignment_before CHECK((before_organization_id IS NULL) = (before_organization IS NULL)),
    CONSTRAINT ck_vehicle_assignment_reason CHECK(length(trim(reason)) > 0 AND length(reason) <= 4000),
    CONSTRAINT ck_vehicle_assignment_evidence CHECK(length(trim(source_evidence)) > 0 AND length(source_evidence) <= 4000),
    CONSTRAINT ck_vehicle_assignment_human CHECK(human_acknowledged = true)
);

CREATE FUNCTION preserve_vehicle_assignment_history() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
    RAISE EXCEPTION 'vehicle assignment history is immutable; record an explicit correction' USING ERRCODE = '23514';
    RETURN OLD;
END;
$guard$;

CREATE TRIGGER vehicle_assignment_history_immutable
BEFORE UPDATE OR DELETE ON operation_vehicle_assignment_changes
FOR EACH ROW EXECUTE FUNCTION preserve_vehicle_assignment_history();
