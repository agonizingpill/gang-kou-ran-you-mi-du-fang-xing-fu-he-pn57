"""E2E tests for multi-tank blending against the running app on :18231."""
import json,threading,httpx

B='http://127.0.0.1:18231'
def login(email):
    r=httpx.post(B+'/auth/login',json={'email':email,'password':'Harbor2026!'})
    return {'Authorization':'Bearer '+r.json()['token']}
ADMIN,CHEM,VIEW=login('admin@chenggang.local'),login('chemist@chenggang.local'),login('viewer@chenggang.local')
passed=failed=0
def check(name,cond,extra=''):
    global passed,failed
    if cond:passed+=1;print(f'  PASS {name}')
    else:failed+=1;print(f'  FAIL {name} {extra}')
def post(path,body,h,expect=None):
    r=httpx.post(B+path,json=body,headers=h)
    return r
def tanks():
    return {t['code']:t for t in httpx.get(B+'/tanks',headers=ADMIN).json()}
def plan(pid):
    return httpx.get(B+f'/blend-plans/{pid}',headers=ADMIN).json()

print('== TC1 创建配油方案，候选生成与判定依据 ==')
r=post('/blend-plans',{'code':'BP-0001','grade':'VLSFO','liters':60000,'vessel':'澄海99 / CG-9001'},CHEM)
check('化验员可创建',r.status_code==200,r.text[:200])
p1=r.json();pid1=p1['id']
check('状态candidates',p1['state']=='candidates')
check('生成候选配方',p1['candidate_count']>=1,json.dumps(p1.get('judgment',{}),ensure_ascii=False)[:300])
j=p1['judgment']
check('判定依据含参考数/阈值/规格',j['reference_count']==60 and 'threshold' in j and j['spec']['density_max']==1010)
check('判定依据含配比公式与评估计数','formula' in j and j['combos_evaluated']>=1)
ok=[c for c in p1['candidates'] if c['verdict']=='ok']
check('存在可直接预留配方',len(ok)>=1)
c1=next(c for c in p1['candidates'] if {x['tank_code'] for x in c['components']}=={'TK-06','TK-08'})
check('TK-06+TK-08配比按可用量比例',abs(c1['components'][0]['liters']-42857.143)<0.01 and abs(c1['components'][1]['liters']-17142.857)<0.01,json.dumps(c1['components']))
check('混合密度加权约979.43',abs(c1['mix_density']-979.429)<0.01,c1['mix_density'])
check('配比合计=申请量',abs(sum(x['liters'] for x in c1['components'])-60000)<0.001)

print('== TC2 权限与编号唯一 ==')
r=post('/blend-plans',{'code':'BP-V','grade':'VLSFO','liters':100,'vessel':'测试船'},VIEW)
check('观察员不可创建',r.status_code==403,r.text[:120])
r=post('/blend-plans',{'code':'BP-0001','grade':'VLSFO','liters':100,'vessel':'测试船'},CHEM)
check('单号重复被拒',r.status_code==409,r.text[:120])

print('== TC3 选定配方整单预留 ==')
sel={'candidate_id':c1['id'],'line_id':1,'berth_id':1,'starts_at':'2026-11-25T08:00','ends_at':'2026-11-25T12:00','draft':6}
r=post(f'/blend-plans/{pid1}/select',sel,CHEM)
check('选定预留成功',r.status_code==200,r.text[:200])
p1=plan(pid1)
check('状态reserved',p1['state']=='reserved')
check('组件落账2条',len(p1['components'])==2)
tk=tanks()
check('TK-06预留42857.143',abs(tk['TK-06']['reserved_liters']-42857.143)<0.01,tk['TK-06'])
check('TK-08预留17142.857',abs(tk['TK-08']['reserved_liters']-17142.857)<0.01)
r=post(f'/blend-plans/{pid1}/select',sel,CHEM)
check('重复选定被拒',r.status_code==409)

print('== TC4 普通调拨扣除预留量 ==')
sid=[s for s in httpx.get(B+'/samples',headers=ADMIN).json() if s['code']=='FS-20261117-01'][0]['id']
r=post('/transfers',{'code':'TR-OVER','sample_id':sid,'liters':8000,'vessel':'v1'},CHEM)
check('超可用(含预留)申请被拒',r.status_code==409,r.text[:120])
r=post('/transfers',{'code':'TR-OK','sample_id':sid,'liters':7000,'vessel':'v1'},CHEM)
check('余量内申请成功',r.status_code==200,r.text[:120])

print('== TC5 低似然配方待复检，不能直接放行 ==')
r=post('/blend-plans',{'code':'BP-0002','grade':'VLSFO','liters':50000,'vessel':'澄海66 / CG-6602'},CHEM)
p2=r.json();pid2=p2['id']
low=[c for c in p2['candidates'] if c['verdict']=='low_likelihood' and {x['tank_code'] for x in c['components']}=={'TK-09','TK-10'}]
check('生成低似然候选',len(low)==1,json.dumps([c['verdict'] for c in p2['candidates']]))
c2=low[0]
check('低似然评分低于阈值',c2['score']<c2['threshold'],f"score={c2['score']:.2f} thr={c2['threshold']:.2f}")
sel2={'candidate_id':c2['id'],'line_id':1,'berth_id':2,'starts_at':'2026-11-26T08:00','ends_at':'2026-11-26T12:00','draft':6}
r=post(f'/blend-plans/{pid2}/select',sel2,CHEM)
check('低似然配方可预留',r.status_code==200,r.text[:200])
check('状态pending_retest',r.json()['state']=='pending_retest')
r=post(f'/blend-plans/{pid2}/release',{'density':1006,'note':'混合实样复检密度在规格内，准予放行'},ADMIN)
check('低似然直接放行被拒',r.status_code==409 and '复检' in r.json()['detail'],r.text[:150])
r=post(f'/blend-plans/{pid2}/retest',{'density':1020,'note':'混合实样复检密度超出等级规格上限'},ADMIN)
check('超规格复检确认被拒',r.status_code==409)
check('仍为pending_retest',plan(pid2)['state']=='pending_retest')
r=post(f'/blend-plans/{pid2}/retest',{'density':1006,'note':'混合实样复检密度1006在VLSFO规格内，解除低似然限制'},ADMIN)
check('复检确认转reserved',r.status_code==200 and r.json()['state']=='reserved',r.text[:150])

print('== TC6 放行原子性：分罐扣量+占用管线泊位，任一失效全部不生效 ==')
r=post(f'/blend-plans/{pid2}/release',{'density':800,'note':'故意超规格密度验证不放行'},ADMIN)
check('放行复检超规格整体拒',r.status_code==409)
check('管线仍空闲',httpx.get(B+'/fuel-lines',headers=ADMIN).json()[0]['state']=='idle')
r=post(f'/blend-plans/{pid2}/release',{'density':1006,'note':'混合实样复检合格，主管放行'},ADMIN)
check('放行成功',r.status_code==200,r.text[:200])
tk=tanks()
check('TK-09扣至5000',abs(tk['TK-09']['liters']-5000)<0.01,tk['TK-09'])
check('TK-10扣至5000',abs(tk['TK-10']['liters']-5000)<0.01,tk['TK-10'])
check('管线FL-V01占用',httpx.get(B+'/fuel-lines',headers=ADMIN).json()[0]['state']=='busy')
snap=plan(pid2)['release_snapshot']
check('放行快照含分罐前后量',snap and len(snap['components'])==2 and 'before_liters' in snap['components'][0])
check('快照含混合实样复检与泊位窗口',snap['mix_retest']['density']==1006 and snap['berth']['code']=='BT-02')
r=post(f'/blend-plans/{pid2}/release',{'density':1006,'note':'重试放行请求验证幂等'},ADMIN)
tk2=tanks()
check('重试放行被拒且不重复扣量',r.status_code==409 and abs(tk2['TK-09']['liters']-5000)<0.01,f'{r.status_code}')

print('== TC7 管线占用使另一单放行整体失效 ==')
r=post(f'/blend-plans/{pid1}/release',{'density':979.4,'note':'混合实样复检合格'},ADMIN)
check('管线忙时放行被拒',r.status_code==409 and '管线' in r.json()['detail'],r.text[:150])
tk=tanks()
check('TK-06未扣量',abs(tk['TK-06']['liters']-50000)<0.01)
r=post(f'/blend-plans/{pid2}/complete',{'completion_note':'输油完工，管线冲洗合格'},ADMIN)
check('完工释放管线',r.status_code==200 and httpx.get(B+'/fuel-lines',headers=ADMIN).json()[0]['state']=='idle')
r=post(f'/blend-plans/{pid1}/release',{'density':979.4,'note':'混合实样复检合格，主管放行'},ADMIN)
check('管线空闲后放行成功',r.status_code==200,r.text[:150])
tk=tanks()
check('TK-06扣至7142.857',abs(tk['TK-06']['liters']-7142.857)<0.01,tk['TK-06'])
check('TK-08扣至2857.143',abs(tk['TK-08']['liters']-2857.143)<0.01)
check('放行后预留清零',abs(tk['TK-06']['reserved_liters'])<0.001 and abs(tk['TK-08']['reserved_liters'])<0.001)

print('== TC8 撤销释放预留，重试不重复 ==')
r=post('/blend-plans',{'code':'BP-0003','grade':'VLSFO','liters':8000,'vessel':'v3'},CHEM)
pid3=r.json()['id'];c3=r.json()['candidates'][0]
r=post(f'/blend-plans/{pid3}/select',{'candidate_id':c3['id'],'line_id':1,'berth_id':1,'starts_at':'2026-12-01T08:00','ends_at':'2026-12-01T12:00','draft':6},CHEM)
check('BP-0003预留成功',r.status_code==200,r.text[:150])
res_before={k:v['reserved_liters'] for k,v in tanks().items()}
r=post(f'/blend-plans/{pid3}/cancel',None,CHEM)
check('撤销成功',r.status_code==200 and r.json()['state']=='cancelled')
res_after={k:v['reserved_liters'] for k,v in tanks().items()}
check('撤销后预留清零',all(abs(v)<0.001 for v in res_after.values()),json.dumps(res_after))
r=post(f'/blend-plans/{pid3}/cancel',None,CHEM)
check('重复撤销被拒不重复释放',r.status_code==409)
r=post(f'/blend-plans/{pid1}/cancel',None,ADMIN)
check('已放行不可撤销',r.status_code==409)

print('== TC9 并发抢量：整单预留成功或失败 ==')
r=post('/blend-plans',{'code':'BP-0004','grade':'VLSFO','liters':15000,'vessel':'v4'},CHEM);pid4=r.json()['id'];cand4=r.json()['candidates'][0]['id']
r=post('/blend-plans',{'code':'BP-0005','grade':'VLSFO','liters':15000,'vessel':'v5'},CHEM);pid5=r.json()['id'];cand5=r.json()['candidates'][0]['id']
# 可用合计 7142.857+2857.143+5000+5000=20000，两单各15000仅一单可成
def do_select(pid,cand,out):
    r=post(f'/blend-plans/{pid}/select',{'candidate_id':cand,'line_id':1,'berth_id':1,'starts_at':'2026-12-05T08:00','ends_at':'2026-12-05T12:00','draft':6},CHEM)
    out.append((pid,r.status_code))
out=[]
ts=[threading.Thread(target=do_select,args=(pid4,cand4,out)),threading.Thread(target=do_select,args=(pid5,cand5,out))]
[t.start() for t in ts];[t.join() for t in ts]
res=dict(out)
check('并发预留恰一单成功',sorted(res.values())==[200,409],out)
winner=pid4 if res[pid4]==200 else pid5
loser=pid5 if res[pid4]==200 else pid4
lcand=cand5 if res[pid4]==200 else cand4
tot=sum(v['reserved_liters'] for v in tanks().values())
check('预留总量恰为15000',abs(tot-15000)<0.01,tot)
r=post(f'/blend-plans/{winner}/cancel',None,ADMIN)
check('胜单撤销释放',r.status_code==200)
r=post(f'/blend-plans/{loser}/select',{'candidate_id':lcand,'line_id':1,'berth_id':1,'starts_at':'2026-12-05T08:00','ends_at':'2026-12-05T12:00','draft':6},CHEM)
check('释放后另一单可预留',r.status_code==200,r.text[:150])
post(f'/blend-plans/{loser}/cancel',None,ADMIN)

print('== TC10 放行与撤销并发只执行一方 ==')
r=post('/blend-plans',{'code':'BP-0006','grade':'VLSFO','liters':10000,'vessel':'v6'},CHEM);pid6=r.json()['id'];cand6=r.json()['candidates'][0]['id']
post(f'/blend-plans/{pid6}/select',{'candidate_id':cand6,'line_id':1,'berth_id':1,'starts_at':'2026-12-06T08:00','ends_at':'2026-12-06T12:00','draft':6},CHEM)
out=[]
def do_release():out.append(('release',post(f'/blend-plans/{pid6}/release',{'density':979,'note':'混合实样复检合格，放行'},ADMIN).status_code))
def do_cancel():out.append(('cancel',post(f'/blend-plans/{pid6}/cancel',None,ADMIN).status_code))
ts=[threading.Thread(target=do_release),threading.Thread(target=do_cancel)]
[t.start() for t in ts];[t.join() for t in ts]
check('放行/撤销恰一方成功',sorted(x[1] for x in out)==[200,409],out)
st=plan(pid6)['state']
check('终态一致',st in('released','cancelled'),st)
if st=='released':
    check('放行生效后撤销无效',post(f'/blend-plans/{pid6}/cancel',None,ADMIN).status_code==409)
    check('重复放行无效',post(f'/blend-plans/{pid6}/release',{'density':979,'note':'重试放行验证幂等'},ADMIN).status_code==409)
    post(f'/blend-plans/{pid6}/complete',{'completion_note':'完工释放管线泊位'},ADMIN)
else:
    check('撤销后放行无效',post(f'/blend-plans/{pid6}/release',{'density':979,'note':'撤销后重试放行验证幂等'},ADMIN).status_code==409)

print('== TC11 泊位窗口重叠拦截（含V3调拨交叉） ==')
r=post('/blend-plans',{'code':'BP-0007','grade':'VLSFO','liters':5000,'vessel':'v7'},CHEM);pid7=r.json()['id'];cand7=r.json()['candidates'][0]['id']
r=post(f'/blend-plans/{pid7}/select',{'candidate_id':cand7,'line_id':1,'berth_id':1,'starts_at':'2026-11-25T10:00','ends_at':'2026-11-25T14:00','draft':6},CHEM)
check('与在持配油窗口重叠被拒',r.status_code==409 and '重叠' in r.json()['detail'],r.text[:150])
# V3 调拨窗口与配油在持窗口交叉
sid2=[s for s in httpx.get(B+'/samples',headers=ADMIN).json() if s['code']=='FS-TK08-01'][0]['id']
r=post('/transfers',{'code':'TR-V3','sample_id':sid2,'liters':1000,'vessel':'v8'},CHEM)
tid=r.json()['id']
r=post('/vessel-windows',{'transfer_id':tid,'berth_id':1,'starts_at':'2026-11-25T09:00','ends_at':'2026-11-25T10:30','draft':5},CHEM)
wid=r.json()['id']
r=post(f'/vessel-windows/{wid}/confirm',None,ADMIN)
check('V3窗口与配油预留重叠被拒',r.status_code==409 and '配油' in r.json()['detail'],r.text[:150])

print('== TC12 配油引用油样冻结复检 ==')
sid3=[s for s in httpx.get(B+'/samples',headers=ADMIN).json() if s['code']=='FS-EDGE-09'][0]['id']
r=httpx.put(B+f'/samples/{sid3}/retest',json={'density':1004,'note':'试图修订已被配油方案引用的油样'},headers=ADMIN)
check('被引用油样复检冻结',r.status_code==409 and '配油' in r.json()['detail'],r.text[:150])

print('== TC13 列表与详情查看（观察员只读） ==')
lst=httpx.get(B+'/blend-plans',headers=VIEW)
check('观察员可查看列表',lst.status_code==200 and len(lst.json())>=6)
d=httpx.get(B+f'/blend-plans/{pid1}',headers=VIEW).json()
check('详情含候选与判定依据',len(d['candidates'])>=1 and d['judgment']['reference_count']==60)
check('详情含放行快照',d['release_snapshot']['vessel']=='澄海99 / CG-9001')

print('== TC14 普通调拨放行时也扣除在持预留 ==')
smgo=[s for s in httpx.get(B+'/samples',headers=ADMIN).json() if s['code']=='FS-MGO-01'][0]['id']
r=post('/transfers',{'code':'TR-HOLD','sample_id':smgo,'liters':30000,'vessel':'大船 / DH-01'},CHEM)
check('预留前大额申请成功',r.status_code==200,r.text[:150]);tid14=r.json()['id']
r=post('/blend-plans',{'code':'BP-M01','grade':'MGO','liters':20000,'vessel':'澄海18 / CG-1801'},CHEM)
pidm=r.json()['id'];cm=r.json()['candidates'][0]
r=post(f'/blend-plans/{pidm}/select',{'candidate_id':cm['id'],'line_id':2,'berth_id':2,'starts_at':'2026-12-10T08:00','ends_at':'2026-12-10T12:00','draft':5},CHEM)
check('MGO配油预留成功',r.status_code==200,r.text[:150])
r=post(f'/transfers/{tid14}/release',None,ADMIN)
check('放行期核量扣除预留给拒',r.status_code==409 and '预留' in r.json()['detail'],r.text[:150])
r=post(f'/blend-plans/{pidm}/cancel',None,ADMIN)
check('撤销配油释放MGO预留',r.status_code==200)
r=post('/line-permits',{'transfer_id':tid14,'line_id':2,'flush_liters':200,'clean_grade':'MGO'},CHEM)
pm=r.json()['id'];post(f'/line-permits/{pm}/approve',None,ADMIN)
r=post('/vessel-windows',{'transfer_id':tid14,'berth_id':2,'starts_at':'2026-12-11T08:00','ends_at':'2026-12-11T12:00','draft':5},CHEM)
wm=r.json()['id'];post(f'/vessel-windows/{wm}/confirm',None,ADMIN)
r=post(f'/transfers/{tid14}/release',None,ADMIN)
check('撤销后调拨放行成功',r.status_code==200,r.text[:150])

print('== TC15 储罐暂停拦截配油预留与放行 ==')
r=post('/blend-plans',{'code':'BP-0008','grade':'VLSFO','liters':9000,'vessel':'v9'},CHEM)
pid8=r.json()['id']
c8=next(c for c in r.json()['candidates'] if any(x['tank_code']=='TK-09' for x in c['components']))
tk09=[t for t in httpx.get(B+'/tanks',headers=ADMIN).json() if t['code']=='TK-09'][0]
httpx.patch(B+f"/tanks/{tk09['id']}/status",json={'status':'hold'},headers=ADMIN)
r=post(f'/blend-plans/{pid8}/select',{'candidate_id':c8['id'],'line_id':1,'berth_id':1,'starts_at':'2026-12-15T08:00','ends_at':'2026-12-15T12:00','draft':6},CHEM)
check('罐暂停拦截预留',r.status_code==409 and '暂停' in r.json()['detail'],r.text[:150])
httpx.patch(B+f"/tanks/{tk09['id']}/status",json={'status':'active'},headers=ADMIN)
c8ok=next(c for c in plan(pid8)['candidates'] if c['verdict']=='ok' and {x['tank_code'] for x in c['components']}=={'TK-06','TK-08'})
r=post(f'/blend-plans/{pid8}/select',{'candidate_id':c8ok['id'],'line_id':1,'berth_id':1,'starts_at':'2026-12-15T08:00','ends_at':'2026-12-15T12:00','draft':6},CHEM)
check('恢复后预留成功',r.status_code==200 and r.json()['state']=='reserved',r.text[:150])
tk08=[t for t in httpx.get(B+'/tanks',headers=ADMIN).json() if t['code']=='TK-08'][0]
httpx.patch(B+f"/tanks/{tk08['id']}/status",json={'status':'hold'},headers=ADMIN)
r=post(f'/blend-plans/{pid8}/release',{'density':979,'note':'暂停期间尝试放行验证'},ADMIN)
check('罐暂停拦截放行且全部不生效',r.status_code==409 and '暂停' in r.json()['detail'],r.text[:150])
check('暂停中预留仍在持',plan(pid8)['state']=='reserved')
httpx.patch(B+f"/tanks/{tk08['id']}/status",json={'status':'active'},headers=ADMIN)
r=post(f'/blend-plans/{pid8}/cancel',None,ADMIN)
check('恢复后撤销释放预留',r.status_code==200)

print(f'\nRESULT: {passed} passed, {failed} failed')
raise SystemExit(1 if failed else 0)
