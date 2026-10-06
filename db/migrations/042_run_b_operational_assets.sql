-- Run B operational assets: distinct shared SKU, batch and physical stock ledger.
-- Follows verified canonical main maximum 041 (Run A personnel); source IDs reuse common/operations tables.


CREATE TABLE operational_assets (
	asset_id UUID NOT NULL, 
	code VARCHAR(100) NOT NULL, 
	name VARCHAR(300) NOT NULL, 
	category VARCHAR(20) NOT NULL, 
	unit VARCHAR(100) NOT NULL, 
	reorder_threshold NUMERIC(14, 3) NOT NULL, 
	active BOOLEAN NOT NULL, 
	document_id UUID, 
	notes TEXT, 
	next_pressure_test_on DATE, 
	next_use_on DATE, 
	next_calibration_on DATE, 
	next_service_on DATE, 
	retired_reason TEXT, 
	retired_by UUID, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (asset_id), 
	CONSTRAINT ck_asset_category CHECK (category IN ('durable','consumable','drug')), 
	CONSTRAINT ck_asset_threshold CHECK (reorder_threshold >= 0), 
	UNIQUE (code), 
	FOREIGN KEY(document_id) REFERENCES documents (document_id), 
	FOREIGN KEY(retired_by) REFERENCES app_users (user_id)
);

CREATE TABLE asset_locations (
	location_id UUID NOT NULL, 
	code VARCHAR(100) NOT NULL, 
	name VARCHAR(300) NOT NULL, 
	building_id UUID, 
	vehicle_id UUID, 
	active BOOLEAN NOT NULL, 
	notes TEXT, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (location_id), 
	UNIQUE (code), 
	FOREIGN KEY(building_id) REFERENCES facilities (building_id), 
	FOREIGN KEY(vehicle_id) REFERENCES operation_vehicles (vehicle_id)
);

CREATE TABLE asset_lots (
	lot_id UUID NOT NULL, 
	asset_id UUID NOT NULL, 
	batch_code VARCHAR(200) NOT NULL, 
	expires_on DATE, 
	provenance TEXT NOT NULL, 
	document_id UUID, 
	expiry_approved_by UUID, 
	expiry_approved_at TIMESTAMP WITH TIME ZONE, 
	active BOOLEAN NOT NULL, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (lot_id), 
	CONSTRAINT uq_asset_batch UNIQUE (asset_id, batch_code), 
	CONSTRAINT uq_lot_asset UNIQUE (lot_id, asset_id), 
	CONSTRAINT ck_lot_expiry_human CHECK (expires_on IS NULL OR (expiry_approved_by IS NOT NULL AND expiry_approved_at IS NOT NULL)), 
	FOREIGN KEY(asset_id) REFERENCES operational_assets (asset_id), 
	FOREIGN KEY(document_id) REFERENCES documents (document_id), 
	FOREIGN KEY(expiry_approved_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_asset_lots_asset_id ON asset_lots (asset_id);

CREATE TABLE asset_balances (
	balance_id UUID NOT NULL, 
	asset_id UUID NOT NULL, 
	lot_id UUID NOT NULL, 
	location_id UUID NOT NULL, 
	quantity NUMERIC(14, 3) NOT NULL, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (balance_id), 
	CONSTRAINT fk_balance_lot_asset FOREIGN KEY(lot_id, asset_id) REFERENCES asset_lots (lot_id, asset_id), 
	CONSTRAINT uq_lot_location UNIQUE (lot_id, location_id), 
	CONSTRAINT ck_asset_balance_nonnegative CHECK (quantity >= 0), 
	FOREIGN KEY(asset_id) REFERENCES operational_assets (asset_id), 
	FOREIGN KEY(location_id) REFERENCES asset_locations (location_id)
);

CREATE INDEX ix_asset_balances_asset_id ON asset_balances (asset_id);

CREATE TABLE asset_loans (
	loan_id UUID NOT NULL, 
	asset_id UUID NOT NULL, 
	lot_id UUID NOT NULL, 
	location_id UUID NOT NULL, 
	borrower_employee_id UUID NOT NULL, 
	quantity NUMERIC(14, 3) NOT NULL, 
	outstanding_quantity NUMERIC(14, 3) NOT NULL, 
	loaned_on DATE NOT NULL, 
	due_on DATE, 
	reason TEXT NOT NULL, 
	created_by UUID NOT NULL, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (loan_id), 
	CONSTRAINT fk_loan_lot_asset FOREIGN KEY(lot_id, asset_id) REFERENCES asset_lots (lot_id, asset_id), 
	CONSTRAINT uq_loan_lineage UNIQUE (loan_id, asset_id, lot_id), 
	CONSTRAINT ck_asset_loan_quantity CHECK (quantity > 0 AND outstanding_quantity >= 0 AND outstanding_quantity <= quantity), 
	CONSTRAINT ck_asset_loan_due CHECK (due_on IS NULL OR due_on >= loaned_on), 
	FOREIGN KEY(asset_id) REFERENCES operational_assets (asset_id), 
	FOREIGN KEY(location_id) REFERENCES asset_locations (location_id), 
	FOREIGN KEY(borrower_employee_id) REFERENCES employees (employee_id), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_asset_loans_asset_id ON asset_loans (asset_id);

CREATE TABLE asset_movements (
	movement_id UUID NOT NULL, 
	asset_id UUID NOT NULL, 
	lot_id UUID NOT NULL, 
	location_id UUID NOT NULL, 
	to_location_id UUID, 
	kind VARCHAR(30) NOT NULL, 
	quantity NUMERIC(14, 3) NOT NULL, 
	unit VARCHAR(100) NOT NULL, 
	cost NUMERIC(14, 2) NOT NULL, 
	loan_id UUID, 
	handler_employee_id UUID, 
	incident_id UUID, 
	document_id UUID, 
	idempotency_key VARCHAR(200) NOT NULL, 
	request_sha256 VARCHAR(64) NOT NULL, 
	reason TEXT NOT NULL, 
	created_by UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	occurred_on DATE NOT NULL, 
	asset_version BIGINT NOT NULL, 
	PRIMARY KEY (movement_id), 
	CONSTRAINT fk_movement_lot_asset FOREIGN KEY(lot_id, asset_id) REFERENCES asset_lots (lot_id, asset_id), 
	CONSTRAINT fk_movement_loan_lineage FOREIGN KEY(loan_id, asset_id, lot_id) REFERENCES asset_loans (loan_id, asset_id, lot_id), 
	CONSTRAINT ck_asset_movement_kind CHECK (kind IN ('receive','issue','transfer','loan','return','disposal','expiry_writeoff')), 
	CONSTRAINT ck_asset_movement_positive CHECK (quantity > 0 AND cost >= 0), 
	CONSTRAINT ck_asset_transfer_location CHECK ((kind = 'transfer' AND to_location_id IS NOT NULL AND to_location_id <> location_id) OR (kind <> 'transfer' AND to_location_id IS NULL)), 
	CONSTRAINT ck_asset_movement_loan CHECK (kind NOT IN ('loan','return') OR loan_id IS NOT NULL), 
	FOREIGN KEY(asset_id) REFERENCES operational_assets (asset_id), 
	FOREIGN KEY(location_id) REFERENCES asset_locations (location_id), 
	FOREIGN KEY(to_location_id) REFERENCES asset_locations (location_id), 
	FOREIGN KEY(handler_employee_id) REFERENCES employees (employee_id), 
	FOREIGN KEY(incident_id) REFERENCES operation_incidents (incident_id), 
	FOREIGN KEY(document_id) REFERENCES documents (document_id), 
	UNIQUE (idempotency_key), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE INDEX ix_asset_movements_asset_id ON asset_movements (asset_id);

CREATE TABLE asset_services (
	service_id UUID NOT NULL, 
	asset_id UUID NOT NULL, 
	kind VARCHAR(30) NOT NULL, 
	performed_on DATE NOT NULL, 
	description TEXT NOT NULL, 
	cost NUMERIC(14, 2) NOT NULL, 
	document_id UUID, 
	lot_id UUID, 
	location_id UUID, 
	quantity NUMERIC(14, 3), 
	next_pressure_test_on DATE, 
	next_use_on DATE, 
	next_calibration_on DATE, 
	next_service_on DATE, 
	status VARCHAR(20) NOT NULL, 
	review_snapshot JSON NOT NULL, 
	reviewed_by UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	reason TEXT, 
	created_by UUID NOT NULL, 
	movement_id UUID, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (service_id), 
	CONSTRAINT fk_service_lot_asset FOREIGN KEY(lot_id, asset_id) REFERENCES asset_lots (lot_id, asset_id), 
	CONSTRAINT ck_asset_service_kind CHECK (kind IN ('inspection','repair','renewal','pressure_test','calibration','disposal','expiry_writeoff')), 
	CONSTRAINT ck_asset_service_cost CHECK (cost >= 0), 
	CONSTRAINT ck_asset_service_status CHECK (status IN ('draft','reviewed','approved','cancelled')), 
	CONSTRAINT ck_asset_service_human CHECK (status <> 'approved' OR (reviewed_by IS NOT NULL AND approved_by IS NOT NULL AND approved_at IS NOT NULL)), 
	CONSTRAINT ck_asset_service_writeoff CHECK (kind NOT IN ('disposal','expiry_writeoff') OR (lot_id IS NOT NULL AND location_id IS NOT NULL AND quantity > 0)), 
	FOREIGN KEY(asset_id) REFERENCES operational_assets (asset_id), 
	FOREIGN KEY(document_id) REFERENCES documents (document_id), 
	FOREIGN KEY(location_id) REFERENCES asset_locations (location_id), 
	FOREIGN KEY(reviewed_by) REFERENCES app_users (user_id), 
	FOREIGN KEY(approved_by) REFERENCES app_users (user_id), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id), 
	FOREIGN KEY(movement_id) REFERENCES asset_movements (movement_id)
);

CREATE INDEX ix_asset_services_asset_id ON asset_services (asset_id);

CREATE TABLE asset_import_previews (
	preview_id UUID NOT NULL, 
	dataset VARCHAR(30) NOT NULL, 
	schema_version VARCHAR(30) NOT NULL, 
	filename TEXT NOT NULL, 
	file_sha256 VARCHAR(64) NOT NULL, 
	document_id UUID, 
	row_data JSON NOT NULL, 
	created_by UUID NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	applied_ids JSON NOT NULL, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (preview_id), 
	CONSTRAINT ck_asset_import_status CHECK (status IN ('preview','applied')), 
	CONSTRAINT ck_asset_import_dataset CHECK (dataset IN ('registry','locations','lots','movements','services')), 
	FOREIGN KEY(document_id) REFERENCES documents (document_id), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);
