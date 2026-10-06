from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator
from decimal import Decimal,InvalidOperation
class Strict(BaseModel):
 model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Version(Strict):
 expected_version:int=Field(ge=1)
class Action(Version):
 reason:str=Field(min_length=1,max_length=4000)
class InquiryInput(Strict):
 year:int=Field(ge=1900,le=2200)
 question:str=Field(min_length=1,max_length=20000)
class Operand(Strict):
 evidence_id:str
 value:str=Field(min_length=1,max_length=100)
 unit:str=Field(default='',max_length=100)
 @field_validator('value')
 @classmethod
 def exact(cls,v):
  try:
   d=Decimal(v)
   if not d.is_finite() or len(d.as_tuple().digits)>60 or abs(d.adjusted())>60:raise ValueError('bounded finite decimal required')
  except InvalidOperation:raise ValueError('finite decimal required')
  return v
class Claim(Operand):
 text:str=Field(min_length=1,max_length=100)
 formula:Literal['identity','sum','difference','product','quotient']='identity'
 operands:list[Operand]=Field(default_factory=list,max_length=50)
class InquiryPatch(Version):
 year:int|None=Field(None,ge=1900,le=2200)
 question:str|None=Field(None,min_length=1,max_length=20000)
 draft:str|None=Field(None,max_length=50000)
 claims:list[Claim]|None=Field(None,max_length=500)
class EvidenceInput(Version):
 source_type:Literal['document','personnel','emergency','facility','contract','finance','incident','vehicle','asset','workforce','legal','fire']
 source_id:str
 query_parameters:dict=Field(default_factory=dict)
 excerpt:str=Field(min_length=1,max_length=10000)
class CandidateAction(Action):
 candidate_id:str
class RenderInput(Strict):
 form_template_id:str
