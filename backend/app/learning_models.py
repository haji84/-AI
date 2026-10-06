"""Department-local corrections and immutable candidate/evaluation lineage."""
from sqlalchemy import BigInteger,Boolean,CheckConstraint,DateTime,ForeignKey,JSON,String,Text,Uuid,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import uuid_str,now_utc


class LearningCorrection(Base):
    __tablename__='learning_corrections'
    __table_args__=(CheckConstraint("review_status IN ('pending','approved','rejected')",name='learning_correction_review'),CheckConstraint('(synthetic AND source_document_id IS NULL) OR (NOT synthetic AND source_document_id IS NOT NULL)',name='learning_correction_source'))
    correction_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    task:Mapped[str]=mapped_column(String(80),nullable=False,index=True)
    source_document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
    source_sha256:Mapped[str|None]=mapped_column(String(64))
    synthetic:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False)
    input_text:Mapped[str]=mapped_column(Text,nullable=False)
    output_text:Mapped[str]=mapped_column(Text,nullable=False)
    review_status:Mapped[str]=mapped_column(String(20),nullable=False,default='pending')
    reason:Mapped[str]=mapped_column(Text,nullable=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    version:Mapped[int]=mapped_column(BigInteger,nullable=False,default=1)
    created_at:Mapped[object]=mapped_column(DateTime(timezone=True),default=now_utc)


class LearningEvaluationSet(Base):
    __tablename__='learning_evaluation_sets'
    __table_args__=(CheckConstraint("review_status IN ('pending','approved','rejected')",name='learning_set_review'),)
    evaluation_set_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    task:Mapped[str]=mapped_column(String(80),nullable=False,index=True)
    name:Mapped[str]=mapped_column(String(200),nullable=False)
    cases:Mapped[list]=mapped_column(JSON,nullable=False)
    cases_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    source_evidence:Mapped[list]=mapped_column(JSON,nullable=False,default=list)
    synthetic:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False)
    review_status:Mapped[str]=mapped_column(String(20),nullable=False,default='pending')
    reason:Mapped[str]=mapped_column(Text,nullable=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    version:Mapped[int]=mapped_column(BigInteger,nullable=False,default=1)
    created_at:Mapped[object]=mapped_column(DateTime(timezone=True),default=now_utc)


class LearningArtifact(Base):
    __tablename__='learning_artifacts'
    artifact_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    task:Mapped[str]=mapped_column(String(80),nullable=False,index=True)
    artifact:Mapped[dict]=mapped_column(JSON,nullable=False)
    artifact_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    training_evidence:Mapped[list]=mapped_column(JSON,nullable=False)
    synthetic:Mapped[bool]=mapped_column(Boolean,nullable=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    created_at:Mapped[object]=mapped_column(DateTime(timezone=True),default=now_utc)


class LearningEvaluation(Base):
    __tablename__='learning_evaluations'
    evaluation_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    artifact_id:Mapped[str]=mapped_column(ForeignKey('learning_artifacts.artifact_id'),nullable=False)
    evaluation_set_id:Mapped[str]=mapped_column(ForeignKey('learning_evaluation_sets.evaluation_set_id'),nullable=False)
    champion_artifact_id:Mapped[str|None]=mapped_column(ForeignKey('learning_artifacts.artifact_id'))
    champion_version:Mapped[int]=mapped_column(BigInteger,nullable=False)
    result:Mapped[dict]=mapped_column(JSON,nullable=False)
    result_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    created_at:Mapped[object]=mapped_column(DateTime(timezone=True),default=now_utc)


class LearningChampion(Base):
    __tablename__='learning_champions'
    task:Mapped[str]=mapped_column(String(80),primary_key=True)
    artifact_id:Mapped[str|None]=mapped_column(ForeignKey('learning_artifacts.artifact_id'))
    version:Mapped[int]=mapped_column(BigInteger,nullable=False,default=1)


class LearningTransition(Base):
    __tablename__='learning_transitions'
    __table_args__=(CheckConstraint("action IN ('promote','rollback')",name='learning_transition_action'),UniqueConstraint('task','applied_version',name='learning_transition_version'))
    transition_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    task:Mapped[str]=mapped_column(ForeignKey('learning_champions.task'),nullable=False,index=True)
    action:Mapped[str]=mapped_column(String(20),nullable=False)
    previous_artifact_id:Mapped[str|None]=mapped_column(ForeignKey('learning_artifacts.artifact_id'))
    selected_artifact_id:Mapped[str|None]=mapped_column(ForeignKey('learning_artifacts.artifact_id'))
    evaluation_id:Mapped[str|None]=mapped_column(ForeignKey('learning_evaluations.evaluation_id'))
    rollback_of:Mapped[str|None]=mapped_column(ForeignKey('learning_transitions.transition_id'))
    applied_version:Mapped[int]=mapped_column(BigInteger,nullable=False)
    reason:Mapped[str]=mapped_column(Text,nullable=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    created_at:Mapped[object]=mapped_column(DateTime(timezone=True),default=now_utc)
