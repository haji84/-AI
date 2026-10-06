-- One department binding per dedicated department database.
CREATE TABLE IF NOT EXISTS tenant_identity (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    tenant_id VARCHAR(36) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL
);
