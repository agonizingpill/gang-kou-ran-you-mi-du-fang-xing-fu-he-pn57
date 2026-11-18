from itertools import combinations
from datetime import datetime,timezone
from decimal import Decimal,ROUND_DOWN
from fastapi import HTTPException
from sqlalchemy import select,func
from .models import Tank,FuelSample
from .harbor_models import FuelLine,Berth,VesselWindow
from .blend_models import BlendPlan,BlendCandidate,BlendComponent
from .transfer_service import obj,get,audit
from .density_model import within_spec,grade_model,score_density
from .constants import GRADES
from .harbor_service import stamp

RESERVING=('reserved','pending_retest')
WINDOW_HOLDING=('reserved','pending_retest','released','completed')
FREEZING=('reserved','pending_retest','released','completed')
MAX_CANDIDATES=40
def now():return datetime.now(timezone.utc).isoformat()
def reserved_liters(s,tank_id,exclude_plan=None):
    q=select(func.coalesce(func.sum(BlendComponent.liters),0)).join(BlendPlan,BlendComponent.plan_id==BlendPlan.id).where(BlendComponent.tank_id==tank_id,BlendPlan.state.in_(RESERVING))
    if exclude_plan:q=q.where(BlendPlan.id!=exclude_plan)
    return Decimal(str(s.scalar(q)))
def available_liters(s,tank):return tank.liters-reserved_liters(s,tank.id)
def effective_density(x):return x.retest_density if x.retest_density is not None else x.density_15
def plan_view(s,x):
    d={**obj(x),'candidate_count':s.scalar(select(func.count()).select_from(BlendCandidate).where(BlendCandidate.plan_id==x.id))}
    d['line_code']=s.get(FuelLine,x.line_id).code if x.line_id else None
    d['berth_code']=s.get(Berth,x.berth_id).code if x.berth_id else None
    if x.selected_candidate_id:
        c=s.get(BlendCandidate,x.selected_candidate_id)
        d['selected_verdict']=c.verdict if c else None
        d['mix_density']=float(c.mix_density) if c else None
    return d
def detail(s,x):
    cands=[obj(c)for c in s.scalars(select(BlendCandidate).where(BlendCandidate.plan_id==x.id).order_by(BlendCandidate.rank))]
    comps=[{**obj(c),'tank_code':s.get(Tank,c.tank_id).code,'sample_code':s.get(FuelSample,c.sample_id).code}for c in s.scalars(select(BlendComponent).where(BlendComponent.plan_id==x.id).order_by(BlendComponent.tank_id))]
    return {**plan_view(s,x),'candidates':cands,'components':comps}
def latest_qualified(s,tank_id):
    return s.scalar(select(FuelSample).where(FuelSample.tank_id==tank_id,FuelSample.reference==False,FuelSample.status.in_(['qualified','retested'])).order_by(FuelSample.id.desc()).limit(1))
def allocate(liters,avails):
    total=sum(avails)
    if liters>total:return None
    shares=[(liters*a/total).quantize(Decimal('.001'),rounding=ROUND_DOWN)for a in avails]
    rem=liters-sum(shares)
    for i in sorted(range(len(avails)),key=lambda i:avails[i]-shares[i],reverse=True):
        if rem<=0:break
        add=min(rem,avails[i]-shares[i]);shares[i]+=add;rem-=add
    if rem>0 or any(x<=0 for x in shares):return None
    return shares
def generate(s,plan):
    sources=[]
    for t in s.scalars(select(Tank).where(Tank.grade==plan.grade,Tank.status=='active').order_by(Tank.id)):
        x=latest_qualified(s,t.id)
        if not x:continue
        avail=available_liters(s,t)
        if avail<=0:continue
        sources.append({'tank':t,'sample':x,'avail':avail,'density':effective_density(x)})
    try:refs,values,scaler,model,threshold=grade_model(s,plan.grade)
    except ValueError as e:raise HTTPException(409,str(e))
    basis={'grade':plan.grade,'reference_count':len(refs),'threshold':threshold,'threshold_quantile':.05,'bandwidth':.3,'kernel':'gaussian','standardized':True,'seed':42,'spec':GRADES[plan.grade],'fit_scope':'reference=True且同燃油等级；候选配比不参与拟合','formula':'分罐升数=申请量×罐可用量/Σ罐可用量；混合密度/黏度/硫=Σ(分罐升数×对应值)/申请量','tanks':[{'tank_code':w['tank'].code,'sample_code':w['sample'].code,'sample_status':w['sample'].status,'available_liters':float(w['avail']),'density_15':float(w['density']),'viscosity':float(w['sample'].viscosity),'sulfur':float(w['sample'].sulfur)}for w in sources],'single_tank_sufficient':any(w['avail']>=plan.liters for w in sources),'combos_evaluated':0,'excluded_insufficient':0,'excluded_out_of_spec':0,'generated_at':now(),'notes':[]}
    found=[]
    for size in range(2,min(4,len(sources))+1):
        for combo in combinations(sources,size):
            basis['combos_evaluated']+=1
            shares=allocate(plan.liters,[w['avail']for w in combo])
            if not shares:basis['excluded_insufficient']+=1;continue
            mix_d=(sum(sh*w['density']for sh,w in zip(shares,combo))/plan.liters).quantize(Decimal('.001'))
            mix_v=(sum(sh*w['sample'].viscosity for sh,w in zip(shares,combo))/plan.liters).quantize(Decimal('.001'))
            mix_s=(sum(sh*w['sample'].sulfur for sh,w in zip(shares,combo))/plan.liters).quantize(Decimal('.0001'))
            if not within_spec(plan.grade,mix_d,mix_v,mix_s):basis['excluded_out_of_spec']+=1;continue
            score=score_density(scaler,model,mix_d)
            found.append({'components':[{'tank_id':w['tank'].id,'tank_code':w['tank'].code,'sample_id':w['sample'].id,'sample_code':w['sample'].code,'liters':float(sh),'ratio':float((sh/plan.liters).quantize(Decimal('.000001'))),'density':float(w['density']),'viscosity':float(w['sample'].viscosity),'sulfur':float(w['sample'].sulfur)}for sh,w in zip(shares,combo)],'mix_density':mix_d,'mix_viscosity':mix_v,'mix_sulfur':mix_s,'score':score,'verdict':'ok'if score>=threshold else'low_likelihood'})
    found.sort(key=lambda c:(c['verdict']!='ok',-c['score']))
    if not found:
        if not sources:basis['notes'].append('同等级没有带合格油样的可调拨储罐')
        elif sum(w['avail']for w in sources)<plan.liters:basis['notes'].append('同等级可用总量不足申请量，即使全部混合也无法满足')
        if basis['excluded_out_of_spec']:basis['notes'].append('部分配比混合后超出等级密度/黏度/硫规格，已筛除')
        if not basis['notes']:basis['notes'].append('满足用量与规格的配比不存在')
    if basis['single_tank_sufficient']:basis['notes'].append('存在单罐可满足申请量，普通调拨更合适；配油方案仍按多罐生成')
    return basis,found[:MAX_CANDIDATES]
def create_plan(s,d,u):
    plan=BlendPlan(code=d.code,grade=d.grade,liters=d.liters,vessel=d.vessel,state='candidates');s.add(plan);s.flush()
    basis,found=generate(s,plan);plan.judgment=basis
    for i,c in enumerate(found):s.add(BlendCandidate(plan_id=plan.id,components=c['components'],mix_density=c['mix_density'],mix_viscosity=c['mix_viscosity'],mix_sulfur=c['mix_sulfur'],score=c['score'],threshold=basis['threshold'],verdict=c['verdict'],rank=i+1))
    s.flush();audit(s,u,'blend_planned',f'{plan.code}:{len(found)}个候选配方');return detail(s,plan)
def berth_overlap(s,berth_id,start,end,exclude_plan=None):
    for w in s.scalars(select(VesselWindow).where(VesselWindow.berth_id==berth_id,VesselWindow.state.in_(['confirmed','in_use','completed'])).execution_options(populate_existing=True)):
        if datetime.fromisoformat(w.starts_at)<end and datetime.fromisoformat(w.ends_at)>start:raise HTTPException(409,'同泊位受油时间与已确认调拨窗口重叠')
    for p in s.scalars(select(BlendPlan).where(BlendPlan.berth_id==berth_id,BlendPlan.state.in_(WINDOW_HOLDING)).execution_options(populate_existing=True)):
        if p.id!=exclude_plan and datetime.fromisoformat(p.starts_at)<end and datetime.fromisoformat(p.ends_at)>start:raise HTTPException(409,'同泊位受油时间与在持配油方案窗口重叠')
def lock_tanks(s,ids):
    return{t.id:t for t in s.scalars(select(Tank).where(Tank.id.in_(ids)).order_by(Tank.id).with_for_update().execution_options(populate_existing=True))}
def select_candidate(s,plan_id,d,u):
    plan=get(s,BlendPlan,plan_id,True)
    if plan.state!='candidates':raise HTTPException(409,'配方已选定或已结案，不能重复预留')
    cand=s.scalar(select(BlendCandidate).where(BlendCandidate.id==d.candidate_id,BlendCandidate.plan_id==plan.id))
    if not cand:raise HTTPException(404,'候选配方不属于该配油申请')
    line=get(s,FuelLine,d.line_id)
    if line.allowed_grade!=plan.grade:raise HTTPException(409,'管线允许等级与配油等级不符')
    berth=get(s,Berth,d.berth_id);start,end=stamp(d.starts_at),stamp(d.ends_at)
    if end<=start:raise HTTPException(409,'受油结束时间须晚于开始')
    if not berth.active:raise HTTPException(409,'泊位已停用')
    if d.draft>berth.max_draft:raise HTTPException(409,'船舶吃水超过泊位上限')
    if end<=datetime.now(timezone.utc):raise HTTPException(409,'受油预约已过期，不能预留')
    tanks=lock_tanks(s,sorted(c['tank_id']for c in cand.components))
    for c in cand.components:
        t=tanks[c['tank_id']]
        if t.status!='active':raise HTTPException(409,f'{t.code}暂停调拨，整单预留失败')
        if Decimal(str(c['liters']))>t.liters-reserved_liters(s,t.id):raise HTTPException(409,f'{t.code}扣除他单预留后可用量不足，整单预留失败')
    berth=get(s,Berth,d.berth_id,True)
    if not berth.active or d.draft>berth.max_draft:raise HTTPException(409,'泊位状态或吃水条件不满足')
    berth_overlap(s,berth.id,start,end)
    for c in cand.components:
        s.add(BlendComponent(plan_id=plan.id,tank_id=c['tank_id'],sample_id=c['sample_id'],liters=Decimal(str(c['liters'])),ratio=Decimal(str(c['ratio'])),density_snapshot=Decimal(str(c['density'])),viscosity_snapshot=Decimal(str(c['viscosity'])),sulfur_snapshot=Decimal(str(c['sulfur']))))
    plan.selected_candidate_id=cand.id;plan.line_id=line.id;plan.berth_id=berth.id;plan.starts_at=start.isoformat();plan.ends_at=end.isoformat();plan.draft=d.draft
    plan.state='reserved'if cand.verdict=='ok'else'pending_retest'
    audit(s,u,'blend_reserved'if plan.state=='reserved'else'blend_pending_retest',f'{plan.code}:配方#{cand.rank}');return detail(s,plan)
def selected_candidate(s,plan):
    c=s.get(BlendCandidate,plan.selected_candidate_id)
    if not c:raise HTTPException(409,'配方尚未选定候选方案')
    return c
def confirm_retest(s,plan_id,d,u):
    plan=get(s,BlendPlan,plan_id,True)
    if plan.state!='pending_retest':raise HTTPException(409,'仅低似然待复检配方需要混合实样复检确认')
    cand=selected_candidate(s,plan)
    if not within_spec(plan.grade,d.density,cand.mix_viscosity,cand.mix_sulfur):raise HTTPException(409,'混合实样复检密度超出本等级规格，配方保持待复检')
    plan.retest_density=d.density;plan.retest_note=d.note;plan.retest_by=u['email'];plan.state='reserved'
    audit(s,u,'blend_retested',f'{plan.code}:{d.density}');return detail(s,plan)
def release(s,plan_id,d,u):
    plan=get(s,BlendPlan,plan_id,True)
    if plan.state=='pending_retest':raise HTTPException(409,'低似然配方须先完成混合实样复检确认，不能直接放行')
    if plan.state!='reserved':raise HTTPException(409,'配方已放行、已完工或已撤销，不能重复扣减')
    cand=selected_candidate(s,plan)
    if not within_spec(plan.grade,d.density,cand.mix_viscosity,cand.mix_sulfur):raise HTTPException(409,'混合实样复检密度不满足等级规格，全部不生效')
    comps=s.scalars(select(BlendComponent).where(BlendComponent.plan_id==plan.id).order_by(BlendComponent.tank_id)).all()
    tanks=lock_tanks(s,[c.tank_id for c in comps])
    for c in comps:
        t=tanks[c.tank_id]
        if t.status!='active':raise HTTPException(409,f'{t.code}暂停调拨，全部不生效')
        if t.liters<c.liters:raise HTTPException(409,f'{t.code}罐内可用量不足预留量，全部不生效')
    line=get(s,FuelLine,plan.line_id,True)
    if line.allowed_grade!=plan.grade:raise HTTPException(409,'管线允许等级与配油等级不符，全部不生效')
    if line.state!='idle':raise HTTPException(409,'管线正在占用，全部不生效')
    berth=get(s,Berth,plan.berth_id,True);start,end=datetime.fromisoformat(plan.starts_at),datetime.fromisoformat(plan.ends_at)
    if not berth.active or plan.draft>berth.max_draft or end<=datetime.now(timezone.utc):raise HTTPException(409,'受油泊位/吃水或预约有效期不满足，全部不生效')
    berth_overlap(s,berth.id,start,end,plan.id)
    minutes=Decimal(str((end-start).total_seconds()/60))
    if plan.liters>minutes*line.capacity_lpm:raise HTTPException(409,'受油窗口不足以按管线额定流量完成配油，全部不生效')
    comp_views=[]
    for c in comps:
        t=tanks[c.tank_id];before=t.liters;t.liters-=c.liters
        comp_views.append({'tank_code':t.code,'sample_code':s.get(FuelSample,c.sample_id).code,'liters':float(c.liters),'ratio':float(c.ratio),'density_snapshot':float(c.density_snapshot),'before_liters':float(before),'after_liters':float(t.liters)})
    line.state='busy';plan.state='released';plan.released_by=u['email']
    if plan.retest_density is None:plan.retest_density=d.density;plan.retest_note=d.note;plan.retest_by=u['email']
    plan.release_snapshot={'code':plan.code,'grade':plan.grade,'liters':float(plan.liters),'vessel':plan.vessel,'candidate_rank':cand.rank,'mix_density':float(cand.mix_density),'mix_viscosity':float(cand.mix_viscosity),'mix_sulfur':float(cand.mix_sulfur),'score':cand.score,'threshold':cand.threshold,'verdict':cand.verdict,'components':comp_views,'line':{'code':line.code,'allowed_grade':line.allowed_grade,'capacity_lpm':float(line.capacity_lpm)},'berth':{'code':berth.code,'max_draft':float(berth.max_draft)},'window':{'starts_at':plan.starts_at,'ends_at':plan.ends_at,'draft':float(plan.draft)},'mix_retest':{'density':float(d.density),'note':d.note,'by':u['email'],'at':now()},'released_by':u['email'],'at':now()}
    audit(s,u,'blend_released',f'{plan.code}:{plan.liters}L');s.flush();return detail(s,plan)
def cancel(s,plan_id,u):
    plan=get(s,BlendPlan,plan_id,True)
    if plan.state in('released','completed'):raise HTTPException(409,'配方已放行扣量，不能撤销')
    if plan.state=='cancelled':raise HTTPException(409,'配方已撤销，不能重复操作')
    plan.state='cancelled';plan.cancelled_by=u['email']
    audit(s,u,'blend_cancelled',plan.code);return detail(s,plan)
def complete(s,plan_id,d,u):
    plan=get(s,BlendPlan,plan_id,True)
    if plan.state!='released':raise HTTPException(409,'仅已放行配油可完工释放资源，不能重复操作')
    line=get(s,FuelLine,plan.line_id,True);line.state='idle'
    plan.state='completed';plan.completed_note=d.completion_note
    audit(s,u,'blend_completed',f'{plan.code} / {d.completion_note}');return detail(s,plan)
