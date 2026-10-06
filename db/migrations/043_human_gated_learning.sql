-- Human correction / candidate / fixed evaluation / Champion lineage. No automatic promotion.

CREATE TABLE learning_artifacts (
	artifact_id UUID NOT NULL, 
	task VARCHAR(80) NOT NULL, 
	artifact JSON NOT NULL, 
	artifact_sha256 VARCHAR(64) NOT NULL, 
	training_evidence JSON NOT NULL, 
	synthetic BOOLEAN NOT NULL, 
	created_by UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (artifact_id), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
,
	CONSTRAINT learning_artifacts_task CHECK (task IN ('audio_correction', 'document_classification', 'document_correction', 'facility_linking', 'ocr', 'photo_classification', 'proper_names', 'workflow_pattern'))
);

CREATE INDEX ix_learning_artifacts_task ON learning_artifacts (task);

CREATE TABLE learning_evaluation_sets (
	evaluation_set_id UUID NOT NULL, 
	task VARCHAR(80) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	cases JSON NOT NULL, 
	cases_sha256 VARCHAR(64) NOT NULL, 
	source_evidence JSON NOT NULL, 
	synthetic BOOLEAN NOT NULL, 
	review_status VARCHAR(20) NOT NULL, 
	reason TEXT NOT NULL, 
	created_by UUID NOT NULL, 
	reviewed_by UUID, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (evaluation_set_id), 
	CONSTRAINT learning_set_review CHECK (review_status IN ('pending','approved','rejected')), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id), 
	FOREIGN KEY(reviewed_by) REFERENCES app_users (user_id)
,
	CONSTRAINT learning_evaluation_sets_task CHECK (task IN ('audio_correction', 'document_classification', 'document_correction', 'facility_linking', 'ocr', 'photo_classification', 'proper_names', 'workflow_pattern'))
);

CREATE INDEX ix_learning_evaluation_sets_task ON learning_evaluation_sets (task);

CREATE TABLE learning_champions (
	task VARCHAR(80) NOT NULL, 
	artifact_id UUID, 
	version BIGINT NOT NULL, 
	PRIMARY KEY (task), 
	FOREIGN KEY(artifact_id) REFERENCES learning_artifacts (artifact_id)
,
	CONSTRAINT learning_champions_task CHECK (task IN ('audio_correction', 'document_classification', 'document_correction', 'facility_linking', 'ocr', 'photo_classification', 'proper_names', 'workflow_pattern'))
);

CREATE TABLE learning_evaluations (
	evaluation_id UUID NOT NULL, 
	artifact_id UUID NOT NULL, 
	evaluation_set_id UUID NOT NULL, 
	champion_artifact_id UUID, 
	champion_version BIGINT NOT NULL, 
	result JSON NOT NULL, 
	result_sha256 VARCHAR(64) NOT NULL, 
	created_by UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (evaluation_id), 
	FOREIGN KEY(artifact_id) REFERENCES learning_artifacts (artifact_id), 
	FOREIGN KEY(evaluation_set_id) REFERENCES learning_evaluation_sets (evaluation_set_id), 
	FOREIGN KEY(champion_artifact_id) REFERENCES learning_artifacts (artifact_id), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
);

CREATE TABLE learning_corrections (
	correction_id UUID NOT NULL, 
	task VARCHAR(80) NOT NULL, 
	source_document_id UUID, 
	source_sha256 VARCHAR(64), 
	synthetic BOOLEAN NOT NULL, 
	input_text TEXT NOT NULL, 
	output_text TEXT NOT NULL, 
	review_status VARCHAR(20) NOT NULL, 
	reason TEXT NOT NULL, 
	created_by UUID NOT NULL, 
	reviewed_by UUID, 
	version BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (correction_id), 
	CONSTRAINT learning_correction_review CHECK (review_status IN ('pending','approved','rejected')), 
	CONSTRAINT learning_correction_source CHECK ((synthetic AND source_document_id IS NULL) OR (NOT synthetic AND source_document_id IS NOT NULL)), 
	FOREIGN KEY(source_document_id) REFERENCES documents (document_id), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id), 
	FOREIGN KEY(reviewed_by) REFERENCES app_users (user_id)
,
	CONSTRAINT learning_corrections_task CHECK (task IN ('audio_correction', 'document_classification', 'document_correction', 'facility_linking', 'ocr', 'photo_classification', 'proper_names', 'workflow_pattern'))
);

CREATE INDEX ix_learning_corrections_task ON learning_corrections (task);

CREATE TABLE learning_transitions (
	transition_id UUID NOT NULL, 
	task VARCHAR(80) NOT NULL, 
	action VARCHAR(20) NOT NULL, 
	previous_artifact_id UUID, 
	selected_artifact_id UUID, 
	evaluation_id UUID, 
	rollback_of UUID, 
	applied_version BIGINT NOT NULL, 
	reason TEXT NOT NULL, 
	created_by UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (transition_id), 
	CONSTRAINT learning_transition_action CHECK (action IN ('promote','rollback')), 
	CONSTRAINT learning_transition_version UNIQUE (task, applied_version), 
	FOREIGN KEY(task) REFERENCES learning_champions (task), 
	FOREIGN KEY(previous_artifact_id) REFERENCES learning_artifacts (artifact_id), 
	FOREIGN KEY(selected_artifact_id) REFERENCES learning_artifacts (artifact_id), 
	FOREIGN KEY(evaluation_id) REFERENCES learning_evaluations (evaluation_id), 
	FOREIGN KEY(rollback_of) REFERENCES learning_transitions (transition_id), 
	FOREIGN KEY(created_by) REFERENCES app_users (user_id)
,
	CONSTRAINT learning_transitions_task CHECK (task IN ('audio_correction', 'document_classification', 'document_correction', 'facility_linking', 'ocr', 'photo_classification', 'proper_names', 'workflow_pattern'))
);

CREATE INDEX ix_learning_transitions_task ON learning_transitions (task);
