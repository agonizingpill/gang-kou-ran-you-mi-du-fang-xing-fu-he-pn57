"""Regression: existing transfer/permit/window/receipt/reconciliation flows still work."""
import httpx
B='http://127.0.0.1:18231'
def login(e):return {'Authorization':'Bearer '+httpx.post(B+'/auth/login',json={'email':e,'password':'Harbor2026!'}).json()['token']}
ADMIN,CHEM=login('admin@chenggang.local'),login('chemist@chenggang.local')
passed=failed=0
def check(n,c,x=''):
    global passed,failed
    if c:passed+=1;print(f'  PASS {n}')
    else:failed+=1;print(f'  FAIL {n} {x}')

samples={s['code']:s for s in httpx.get(B+'/samples',headers=ADMIN).json()}
sid=samples['FS-MGO-01']['id']
r=httpx.post(B+'/transfers',json={'code':'TR-REG','sample_id':sid,'liters':2000,'vessel':'回归船 / RG-01'},headers=CHEM)
check('普通调拨申请',r.status_code==200,r.text[:150]);tid=r.json()['id']
r=httpx.post(B+'/line-permits',json={'transfer_id':tid,'line_id':2,'flush_liters':200,'clean_grade':'MGO'},headers=CHEM)
check('清线计划',r.status_code==200,r.text[:150]);pid=r.json()['id']
r=httpx.post(B+f'/line-permits/{pid}/approve',headers=ADMIN)
check('主管许可',r.status_code==200,r.text[:150])
r=httpx.post(B+'/vessel-windows',json={'transfer_id':tid,'berth_id':1,'starts_at':'2026-12-20T08:00','ends_at':'2026-12-20T12:00','draft':5},headers=CHEM)
check('窗口登记',r.status_code==200,r.text[:150]);wid=r.json()['id']
r=httpx.post(B+f'/vessel-windows/{wid}/confirm',headers=ADMIN)
check('窗口确认(无配油冲突)',r.status_code==200,r.text[:150])
before=[t for t in httpx.get(B+'/tanks',headers=ADMIN).json() if t['code']=='TK-M01'][0]['liters']
r=httpx.post(B+f'/transfers/{tid}/release',headers=ADMIN)
check('调拨放行',r.status_code==200,r.text[:150])
after=[t for t in httpx.get(B+'/tanks',headers=ADMIN).json() if t['code']=='TK-M01'][0]['liters']
check('扣量2000',abs(before-after-2000)<0.001,f'{before}->{after}')
r=httpx.post(B+f'/transfers/{tid}/release',headers=ADMIN)
check('重复放行拒绝',r.status_code==409)
r=httpx.post(B+'/loading-reconciliations',json={'transfer_id':tid,'meter_before':10000,'meter_after':12010,'vessel_received_liters':2010},headers=CHEM)
check('对账登记',r.status_code==200,r.text[:150]);rid=r.json()['id']
r=httpx.post(B+f'/loading-reconciliations/{rid}/close',headers=ADMIN)
check('容差内结案并释放资源',r.status_code==200,r.text[:150])
check('管线已释放',httpx.get(B+'/fuel-lines',headers=ADMIN).json()[1]['state']=='idle')
# 收油流程
r=httpx.post(B+'/tank-receipts',json={'code':'RC-REG','tank_id':3,'grade':'MGO','liters':1000,'density_15':851,'viscosity':4,'sulfur':.06},headers=CHEM)
check('收油计划',r.status_code==200,r.text[:150]);rc=r.json()['id']
r=httpx.post(B+f'/tank-receipts/{rc}/inspect',headers=CHEM)
check('化验核对',r.status_code==200,r.text[:150])
r=httpx.post(B+f'/tank-receipts/{rc}/receive',headers=ADMIN)
check('主管入罐',r.status_code==200,r.text[:150])
# 异常样复检流程（未被配油引用）
anom=[s for s in httpx.get(B+'/samples',headers=ADMIN).json() if s['status']=='anomaly']
r=httpx.put(B+f"/samples/{samples['FS-OFF']['id']}/retest",json={'density':984,'note':'重新取中层油样复测合格'},headers=CHEM)
check('异常样复检',r.status_code==200 and r.json()['status']=='retested',r.text[:150])
print(f'\nREGRESSION RESULT: {passed} passed, {failed} failed')
raise SystemExit(1 if failed else 0)
