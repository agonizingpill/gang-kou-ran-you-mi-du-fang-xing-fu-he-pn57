// Render smoke test: blends page render() produces HTML for every plan state.
import*as blends from '/workspace/frontend/src/pages/blends.js';
const base={tanks:[],lines:[{id:1,code:'FL-V01',allowed_grade:'VLSFO',state:'idle',capacity_lpm:1000}],berths:[{id:1,code:'BT-01',max_draft:10,active:true}],grades:{VLSFO:{density_min:925,density_max:1010,viscosity_min:10,viscosity_max:380,sulfur_max:.5}},blends:[],blendSelected:1};
const j={grade:'VLSFO',reference_count:60,threshold:-2.388,threshold_quantile:.05,bandwidth:.3,kernel:'gaussian',spec:{density_min:925,density_max:1010,viscosity_min:10,viscosity_max:380,sulfur_max:.5},formula:'分罐升数=申请量×罐可用量/Σ罐可用量',tanks:[{tank_code:'TK-06',sample_code:'FS-01',sample_status:'qualified',available_liters:50000,density_15:980}],combos_evaluated:5,excluded_out_of_spec:1,excluded_insufficient:1,generated_at:'2026-11-18T01:00:00+00:00',notes:['存在单罐可满足申请量']};
const cand={id:11,plan_id:1,rank:1,verdict:'ok',mix_density:979.429,mix_viscosity:130,mix_sulfur:.35,score:-.9,threshold:-2.388,components:[{tank_id:1,tank_code:'TK-06',sample_id:1,sample_code:'FS-01',liters:42857.143,ratio:.714286,density:980,viscosity:130,sulfur:.35},{tank_id:2,tank_code:'TK-08',sample_id:2,sample_code:'FS-02',liters:17142.857,ratio:.285714,density:978,viscosity:130,sulfur:.35}]};
const comp={id:1,plan_id:1,tank_id:1,sample_id:1,tank_code:'TK-06',sample_code:'FS-01',liters:42857.143,ratio:.714286,density_snapshot:980,viscosity_snapshot:130,sulfur_snapshot:.35};
const snap={code:'BP-0001',grade:'VLSFO',liters:60000,vessel:'澄海99',candidate_rank:1,mix_density:979.429,mix_viscosity:130,mix_sulfur:.35,score:-.9,threshold:-2.388,verdict:'ok',components:[{tank_code:'TK-06',sample_code:'FS-01',liters:42857.143,ratio:.714286,density_snapshot:980,before_liters:50000,after_liters:7142.857}],line:{code:'FL-V01',allowed_grade:'VLSFO',capacity_lpm:1000},berth:{code:'BT-01',max_draft:10},window:{starts_at:'2026-11-25T00:00:00+00:00',ends_at:'2026-11-25T04:00:00+00:00',draft:6},mix_retest:{density:979.4,note:'混合实样复检合格',by:'admin@chenggang.local',at:'2026-11-18T02:00:00+00:00'},released_by:'admin@chenggang.local',at:'2026-11-18T02:00:00+00:00'};
const plan=(state,extra={})=>({id:1,code:'BP-0001',grade:'VLSFO',liters:60000,vessel:'澄海99',state,selected_candidate_id:11,line_id:1,berth_id:1,starts_at:'2026-11-25T00:00:00+00:00',ends_at:'2026-11-25T04:00:00+00:00',draft:6,retest_density:null,retest_note:'',retest_by:'',released_by:'',cancelled_by:'',completed_note:'',judgment:j,release_snapshot:null,candidate_count:1,line_code:'FL-V01',berth_code:'BT-01',selected_verdict:'ok',mix_density:979.429,candidates:[cand],components:[comp],...extra});
let fail=0;
for(const[state,extra]of[['candidates',{}],['reserved',{}],['pending_retest',{selected_verdict:'low_likelihood'}],['released',{release_snapshot:snap,released_by:'admin@chenggang.local'}],['completed',{release_snapshot:snap,completed_note:'完工释放'}],['cancelled',{cancelled_by:'admin@chenggang.local'}]]){
    for(const role of['admin','chemist','viewer']){
        try{
            const html=blends.render({...base,blendDetail:plan(state,extra)},{role,email:role+'@x'});
            if(!html.includes('BP-0001'))throw new Error('missing plan code');
            if(state==='candidates'&&!html.includes('候选配方'))throw new Error('missing candidates');
            if(state==='released'&&!html.includes('已 放 行'))throw new Error('missing stamp');
            console.log(`  PASS render ${state} as ${role} (${html.length}b)`);
        }catch(e){fail++;console.log(`  FAIL render ${state} as ${role}: ${e.message}`)}
    }
}
// empty states
try{blends.render({...base,blendDetail:null,blends:[]},{role:'admin'});console.log('  PASS render empty')}catch(e){fail++;console.log('  FAIL empty: '+e.message)}
try{const h=blends.render({...base,blendDetail:plan('candidates',{candidates:[],candidate_count:0})},{role:'admin'});if(!h.includes('没有满足用量与规格'))throw 0;console.log('  PASS render no-candidates')}catch(e){fail++;console.log('  FAIL no-candidates')}
console.log(fail?`RENDER: ${fail} failed`:'RENDER: all passed');
process.exit(fail?1:0);
