from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict
class Clean(BaseModel):model_config=ConfigDict(str_strip_whitespace=True)
class BlendIn(Clean):
    code:str=Field(min_length=2,max_length=70)
    grade:Literal['VLSFO','MGO']
    liters:Decimal=Field(gt=0,le=100000000,max_digits=14,decimal_places=3)
    vessel:str=Field(min_length=2,max_length=120)
class BlendSelect(Clean):
    candidate_id:int=Field(gt=0)
    line_id:int=Field(gt=0)
    berth_id:int=Field(gt=0)
    starts_at:datetime
    ends_at:datetime
    draft:Decimal=Field(gt=0,le=30,max_digits=8,decimal_places=3)
class BlendRetest(Clean):
    density:Decimal=Field(gt=0,le=1500,max_digits=10,decimal_places=3)
    note:str=Field(min_length=8,max_length=2000)
class BlendComplete(Clean):completion_note:str=Field(min_length=8,max_length=600)
