"""Evidence snapshots, draft authority and immutable approved inquiry revisions."""
from datetime import datetime
from sqlalchemy import BigInteger,Boolean,CheckConstraint,DateTime,ForeignKey,JSON,String,Text,Uuid
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import uuid_str,now_utc
class Versioned:
 version:Mapped[int]=mapped_column(BigInteger,nullable=False,default=1)
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now_utc)
 updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now_utc)
class Inquiry(Versioned,Base):
 __tablename__='inquiries'
 inquiry_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
 year:Mapped[int]=mapped_column(BigInteger,nullable=False,index=True)
 question:Mapped[str]=mapped_column(Text,nullable=False)
 draft:Mapped[str]=mapped_column(Text,nullable=False,default='')
 claims:Mapped[list]=mapped_column(JSON,nullable=False,default=list)
 status:Mapped[str]=mapped_column(String(20),nullable=False,default='draft')
 revision_of:Mapped[str|None]=mapped_column(ForeignKey('inquiries.inquiry_id'))
 provenance:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
 review_snapshot:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
 reviewed_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
 reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
 approved_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
 approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
 created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
 deleted:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False)
 __table_args__=(CheckConstraint('year BETWEEN 1900 AND 2200',name='ck_inquiry_year'),CheckConstraint("status IN ('draft','reviewed','approved')",name='ck_inquiry_status'),CheckConstraint("status <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",name='ck_inquiry_human'))
class InquiryEvidence(Base):
 __tablename__='inquiry_evidence'
 evidence_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
 inquiry_id:Mapped[str]=mapped_column(ForeignKey('inquiries.inquiry_id'),nullable=False,index=True)
 source_type:Mapped[str]=mapped_column(String(50),nullable=False)
 source_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),nullable=False)
 document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
 excerpt:Mapped[str]=mapped_column(Text,nullable=False)
 snapshot:Mapped[dict]=mapped_column(JSON,nullable=False)
 query_parameters:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
 created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
 retrieved_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now_utc)
class InquiryCandidate(Base):
 __tablename__='inquiry_candidates'
 candidate_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
 inquiry_id:Mapped[str]=mapped_column(ForeignKey('inquiries.inquiry_id'),nullable=False,index=True)
 draft:Mapped[str]=mapped_column(Text,nullable=False)
 claims:Mapped[list]=mapped_column(JSON,nullable=False,default=list)
 model:Mapped[str]=mapped_column(String(200),nullable=False)
 model_version:Mapped[str]=mapped_column(String(200),nullable=False)
 input_provenance:Mapped[dict]=mapped_column(JSON,nullable=False)
 confidence:Mapped[str|None]=mapped_column(String(50))
 generated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now_utc)
 created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
class InquiryRenderedForm(Base):
 __tablename__='inquiry_rendered_forms'
 rendered_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
 inquiry_id:Mapped[str]=mapped_column(ForeignKey('inquiries.inquiry_id'),nullable=False)
 form_template_id:Mapped[str]=mapped_column(ForeignKey('form_templates.form_template_id'),nullable=False)
 document_id:Mapped[str]=mapped_column(ForeignKey('documents.document_id'),nullable=False)
 manifest:Mapped[dict]=mapped_column(JSON,nullable=False)
 created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now_utc)
