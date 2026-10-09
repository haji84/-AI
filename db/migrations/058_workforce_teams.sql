-- Human grouping reuses canonical history; never grants roles or creates crew/rosters.
CREATE TABLE workforce_teams (
 team_id uuid PRIMARY KEY,
 organization_id uuid NOT NULL REFERENCES organization_units(organization_id),
 code varchar(100) NOT NULL,
 name varchar(200) NOT NULL,
 active boolean NOT NULL DEFAULT true,
 reason text NOT NULL,
 created_by uuid NOT NULL REFERENCES app_users(user_id),
 version bigint NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 CONSTRAINT uq_workforce_team_code UNIQUE(organization_id,code)
);
CREATE INDEX ix_workforce_teams_organization_id ON workforce_teams(organization_id);
CREATE TABLE workforce_team_memberships (
 membership_id uuid PRIMARY KEY,
 team_id uuid NOT NULL REFERENCES workforce_teams(team_id),
 employee_id uuid NOT NULL REFERENCES employees(employee_id),
 assignment_id uuid NOT NULL REFERENCES employee_assignments(assignment_id),
 assignment_version bigint NOT NULL,
 assignment_snapshot jsonb NOT NULL,
 valid_from date NOT NULL,
 valid_to date,
 active boolean NOT NULL DEFAULT true,
 reason text NOT NULL,
 created_by uuid NOT NULL REFERENCES app_users(user_id),
 version bigint NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 CONSTRAINT uq_workforce_team_membership UNIQUE(team_id,employee_id,assignment_id,assignment_version,valid_from),
 CONSTRAINT ck_workforce_team_membership_dates CHECK(valid_to IS NULL OR valid_to>=valid_from)
);
CREATE INDEX ix_workforce_team_memberships_team_id ON workforce_team_memberships(team_id);
CREATE INDEX ix_workforce_team_memberships_employee_id ON workforce_team_memberships(employee_id);
CREATE TABLE workforce_team_changes (
 change_id uuid PRIMARY KEY,
 team_id uuid NOT NULL REFERENCES workforce_teams(team_id),
 membership_id uuid REFERENCES workforce_team_memberships(membership_id),
 action varchar(100) NOT NULL,
 actor_id uuid NOT NULL REFERENCES app_users(user_id),
 reason text NOT NULL,
 before_data jsonb,
 after_data jsonb NOT NULL,
 evidence_sha256 varchar(64) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_workforce_team_changes_team_id ON workforce_team_changes(team_id);
CREATE FUNCTION reject_workforce_team_change_mutation() RETURNS trigger AS $$
BEGIN
 RAISE EXCEPTION 'workforce team change history is immutable' USING ERRCODE='23514';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER workforce_team_change_immutable BEFORE UPDATE OR DELETE ON workforce_team_changes
 FOR EACH ROW EXECUTE FUNCTION reject_workforce_team_change_mutation();
