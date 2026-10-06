from datetime import date
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator,field_validator
from uuid import UUID
import re

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    @field_validator('building_id','finding_id','measure_id','rule_version_ids','evidence_document_ids','procedure_document_ids','document_ids','proof_document_ids',check_fields=False)
    @classmethod
    def identities(cls,value):
        if value is None:return value
        return [str(UUID(v)) for v in value] if isinstance(value,list) else str(UUID(value))

class CaseInput(Strict):
    building_id:str
    finding_id:str|None=None
    observed_on:date
    possible_issue:str=Field(min_length=1,max_length=10000)
    missing_information:list[str]=Field(default_factory=list,max_length=100)
    confirmation_steps:list[str]=Field(default_factory=list,max_length=100)
    rule_version_ids:list[str]=Field(default_factory=list,max_length=100)
    evidence_document_ids:list[str]=Field(default_factory=list,max_length=100)
    procedure_document_ids:list[str]=Field(default_factory=list,max_length=100)
    origin:Literal['human','ai']='human'
    ai_provenance:dict=Field(default_factory=dict)
    @model_validator(mode='after')
    def provenance(self):
        if self.origin=='ai' and not all(self.ai_provenance.get(k) for k in ('job_id','engine_version','model_version','source_hashes')):raise ValueError('AI candidate requires job/model/engine/source provenance')
        if self.origin=='ai':
            confidence=self.ai_provenance.get('confidence')
            hashes=self.ai_provenance.get('source_hashes')
            if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not 0<=confidence<=1:raise ValueError('AI confidence must be between0and1')
            if not isinstance(hashes,dict) or not hashes or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in hashes.values()):raise ValueError('AI source hashes must be original SHA256 values')
            for identity in hashes:str(UUID(identity))
        return self

class CasePatch(Strict):
    expected_version:int=Field(ge=1)
    observed_on:date|None=None
    possible_issue:str|None=Field(default=None,min_length=1,max_length=10000)
    missing_information:list[str]|None=Field(default=None,max_length=100)
    confirmation_steps:list[str]|None=Field(default=None,max_length=100)
    rule_version_ids:list[str]|None=Field(default=None,max_length=100)
    evidence_document_ids:list[str]|None=Field(default=None,max_length=100)
    procedure_document_ids:list[str]|None=Field(default=None,max_length=100)

class HumanAction(Strict):
    expected_version:int=Field(ge=1)
    reason:str=Field(min_length=1,max_length=4000)
    human_acknowledged:Literal[True]

class Revision(Strict):
    expected_version:int=Field(ge=1)
    reason:str=Field(min_length=1,max_length=4000)

class MeasureInput(Strict):
    expected_case_version:int=Field(ge=1)
    kind:Literal['guidance','order','disposition']
    instruction:str=Field(min_length=1,max_length=10000)
    official_reference:str|None=Field(default=None,max_length=400)
    due_on:date|None=None
    document_ids:list[str]=Field(default_factory=list,max_length=100)
    procedure_document_ids:list[str]=Field(default_factory=list,max_length=100)

class MeasurePatch(Strict):
    expected_version:int=Field(ge=1)
    instruction:str|None=Field(default=None,min_length=1,max_length=10000)
    official_reference:str|None=Field(default=None,max_length=400)
    due_on:date|None=None
    document_ids:list[str]|None=Field(default=None,max_length=100)
    procedure_document_ids:list[str]|None=Field(default=None,max_length=100)

class MeasureWithdrawal(HumanAction):
    proof_document_ids:list[str]=Field(min_length=1,max_length=100)

class CorrectionInput(Strict):
    expected_case_version:int=Field(ge=1)
    description:str=Field(min_length=1,max_length=10000)
    due_on:date|None=None
    measure_id:str|None=None

class CorrectionPatch(Strict):
    expected_version:int=Field(ge=1)
    description:str|None=Field(default=None,min_length=1,max_length=10000)
    due_on:date|None=None
    reason:str=Field(min_length=1,max_length=4000)

class CorrectionEvidence(HumanAction):
    evidence_document_ids:list[str]=Field(min_length=1,max_length=100)

class CorrectionResponse(CorrectionEvidence):
    response_text:str=Field(min_length=1,max_length=10000)

class CorrectionVerification(CorrectionEvidence):
    passed:bool
