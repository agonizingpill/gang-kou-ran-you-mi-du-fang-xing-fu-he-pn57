from fastapi import APIRouter,Depends
from sqlalchemy import select
from .database import Session
from .security import current,allow
from .transfer_service import get
from .blend_models import BlendPlan
from .blend_schemas import BlendIn,BlendSelect,BlendRetest,BlendComplete
from . import blend_service as svc
router=APIRouter()
@router.get('/blend-plans')
def plans(u=Depends(current)):
    with Session() as s:return [svc.plan_view(s,x)for x in s.scalars(select(BlendPlan).order_by(BlendPlan.id.desc()))]
@router.get('/blend-plans/{id}')
def plan(id:int,u=Depends(current)):
    with Session() as s:return svc.detail(s,get(s,BlendPlan,id))
@router.post('/blend-plans')
def create(p:BlendIn,u=Depends(current)):
    allow(u,'admin','chemist')
    with Session.begin() as s:return svc.create_plan(s,p,u)
@router.post('/blend-plans/{id}/select')
def select_candidate(id:int,p:BlendSelect,u=Depends(current)):
    allow(u,'admin','chemist')
    with Session.begin() as s:return svc.select_candidate(s,id,p,u)
@router.post('/blend-plans/{id}/retest')
def retest(id:int,p:BlendRetest,u=Depends(current)):
    allow(u,'admin')
    with Session.begin() as s:return svc.confirm_retest(s,id,p,u)
@router.post('/blend-plans/{id}/release')
def release(id:int,p:BlendRetest,u=Depends(current)):
    allow(u,'admin')
    with Session.begin() as s:return svc.release(s,id,p,u)
@router.post('/blend-plans/{id}/cancel')
def cancel(id:int,u=Depends(current)):
    allow(u,'admin','chemist')
    with Session.begin() as s:return svc.cancel(s,id,u)
@router.post('/blend-plans/{id}/complete')
def complete(id:int,p:BlendComplete,u=Depends(current)):
    allow(u,'admin')
    with Session.begin() as s:return svc.complete(s,id,p,u)
