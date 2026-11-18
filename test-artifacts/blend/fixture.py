"""Fixture: qualify received samples via real KDE compare; add edge-density tanks/samples.

Simulates the worker (Redis unavailable in this sandbox) by calling density_model.compare
directly. Edge samples (1005/1008) are within hard spec but far from the reference
distribution, so they become 'retested' (chemist retest clears anomaly on hard spec only).
"""
import json,os,sys
sys.path.insert(0,'/workspace/backend')
os.environ['DATABASE_URL']='postgresql+psycopg://bunker@127.0.0.1:15432/bunker'
from sqlalchemy import select
from src.database import Session
from src.models import Tank,FuelSample
from src.density_model import compare

def qualify(s,code,force_retested=False):
    x=s.scalar(select(FuelSample).where(FuelSample.code==code))
    score,thr,passed,ev=compare(s,x)
    x.log_density,x.threshold=score,thr
    x.status='qualified' if passed else 'anomaly'
    x.evidence=json.dumps(ev,ensure_ascii=False)
    if force_retested and not passed:
        x.status='retested';x.retest_density=x.density_15
        x.retest_note='复测确认密度在等级硬规格内，人工解除异常（测试夹具）'
    print(f'{code}: status={x.status} score={score:.3f} thr={thr:.3f}')

with Session.begin() as s:
    for code,grade,liters in [('TK-09','VLSFO',30000),('TK-10','VLSFO',30000),('TK-M02','MGO',20000)]:
        if not s.scalar(select(Tank).where(Tank.code==code)):
            s.add(Tank(code=code,grade=grade,liters=liters,status='active'))
    s.flush()
    t={x.code:x for x in s.scalars(select(Tank))}
    for code,tk,d,v,su in [('FS-TK08-01','TK-08',978,130,.35),('FS-EDGE-09','TK-09',1005,130,.35),('FS-EDGE-10','TK-10',1008,130,.35),('FS-MGO-02','TK-M02',848,4,.06)]:
        if not s.scalar(select(FuelSample).where(FuelSample.code==code)):
            s.add(FuelSample(code=code,tank_id=t[tk].id,density_15=d,viscosity=v,sulfur=su,status='received',reference=False,evidence='',retest_note=''))
    s.flush()
    for code in ['FS-20261117-01','FS-MGO-01','FS-TK08-01','FS-MGO-02']:
        qualify(s,code)
    qualify(s,'FS-OFF')  # 1035 超规格 → anomaly，供回归测试复检
    for code in ['FS-EDGE-09','FS-EDGE-10']:
        qualify(s,code,force_retested=True)
print('FIXTURE OK')
