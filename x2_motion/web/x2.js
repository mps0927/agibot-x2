'use strict';
let robotFacts={};
function updatePostureControls(){
  const v=robotFacts,permission=v.control_permissions||{};
  const fresh=v.connected&&v.received_age_ms!==null&&v.received_age_ms<1000&&v.mode_age_ms<2000;
  const busy=!!v.posture_pending||v.seat_hold_pending||!!v.gesture||v.arm_pending||v.moving||state.controller==='other'||state.armed;
  const supported=document.getElementById('posture-support').checked;
  document.getElementById('seat-hold').disabled=!fresh||!permission.seat_hold||busy||!['SIT_JOINT_DEFAULT','PASSIVE_DEFAULT','DAMPING_DEFAULT'].includes(v.fsm)||(!document.getElementById('seat-support').checked&&v.fsm!=='SIT_JOINT_DEFAULT');
  document.getElementById('stand-up-execute').disabled=!fresh||!permission.posture_actions||busy||!supported||v.fsm!=='SIT_JOINT_DEFAULT';
  document.getElementById('sit-down-execute').disabled=!fresh||!permission.posture_actions||busy||!supported||v.fsm!=='STAND_DEFAULT';
}
async function refreshRobotFacts(){
  try{
    const r=await fetch('/api/status'),v=await r.json();robotFacts=v;
    document.getElementById('robot-facts').textContent=[
      `기종 ${v.model||'X2 Ultra t2d5'}`,
      `SDK ${v.sdk_version||'조회 중'}`,
      `모드 ${v.fsm||'응답 대기'}`,
      `배터리 ${v.battery_percent??'—'}%`,
      `손 ${v.hand_status||'조회 중'}`,
      `제어 요청 ${v.control_requests_sent??0}건 · 속도 발행 ${v.velocity_publications??0}건`
    ].join('  |  ');
    document.getElementById('live-joints').textContent=JSON.stringify(v.joint_values||{},null,2);
    document.getElementById('preset-finished').disabled=!v.gesture;
    document.getElementById('preset-block-reason').textContent=v.preset_block_reason||'안정 서기 응답 정상 · 현장 조건 확인 후 프리셋을 요청할 수 있습니다.';
    document.querySelectorAll('[data-gesture]').forEach(button=>{
      button.title=v.preset_block_reason||(!v.arm_actions?.[button.dataset.gesture]?'설치 SDK에 동작 상수가 없습니다.':'현장 조건 확인 후 요청');
    });
    document.querySelectorAll('.motion-block-reason').forEach(el=>{
      el.textContent=!v.connected?'로봇 연결 후 SDK 매핑 확인':!v.arm_actions?.[el.dataset.name]?'설치 SDK 동작 상수 없음 · 버전 호환 확인 필요':v.preset_block_reason||'';
    });
    const active=v.connected&&v.fsm==='SIT_JOINT_DEFAULT'&&v.mode_age_ms<2000;
    document.getElementById('seat-status').textContent=active?'현재 착석 고정 활성 · SIT_JOINT_DEFAULT':v.seat_hold_block_reason;
    if(v.seat_hold_pending)document.getElementById('seat-status').textContent='착석 고정 응답·모드 전환 확인 중';
    if(v.error)document.getElementById('seat-status').textContent=v.error;
    document.getElementById('sdk-restrictions').replaceChildren(...(v.restrictions||[]).map(item=>{
      const p=document.createElement('p'),b=document.createElement('b');b.textContent=item.layer+' · ';p.append(b,document.createTextNode(item.reason));return p;
    }));
    document.getElementById('robot-facts').dataset.connected=String(!!v.connected);
    updatePostureControls();
    document.getElementById('preparation-state').textContent=(v.recorded_state?'저장된 상태 · ':!v.connected?'연결 대기 · ':'')+(modeLabels[v.fsm]||v.fsm||'—');
    if(v.recorded_state){
      document.querySelector('.camera-overlay span:last-child').textContent='RGB · RECORDED';
      document.querySelector('.camera-note').textContent='저장된 RGB 사진입니다. 실시간 영상이 아니며, 선택한 사진으로 VLM 분석을 진행할 수 있습니다.';
    }
    document.getElementById('posture-progress').textContent=v.posture_pending?`${v.posture_pending.name} · ${v.posture_pending.phase} · 현재 ${v.fsm}`:v.error||((v.posture_result?.status==='COMPLETED_MODE_OBSERVED')?`모드 전환 확인: ${v.fsm} · 실제 자세도 확인하세요.`:'');
    const labels={movement:'이동·회전',presets:'프리셋',posture_actions:'기립·착석',seat_hold:'착석 고정',mode_switch:'모드 전환'};
    document.getElementById('permission-summary').textContent='허용: '+(Object.entries(v.control_permissions||{}).filter(([,enabled])=>enabled).map(([key])=>labels[key]||key).join(' / ')||'조회만');
    document.getElementById('sdk-diagnostics').textContent=JSON.stringify(v.sdk_queries||{},null,2);

  }catch{robotFacts={};updatePostureControls();}
  setTimeout(refreshRobotFacts,2000);
}
document.getElementById('use-current-joints').onclick=async()=>{
  try{
    const r=await fetch('/api/status'),v=await r.json();
    if(!v.connected)throw Error('실물 상태가 연결되지 않았습니다.');
    document.querySelectorAll('[data-joint-number]').forEach(input=>{
      const name=input.dataset.jointNumber,j=v.joint_values?.[name];
      if(j&&Number.isFinite(j.position)){
        input.value=String(j.position);
        const slider=document.querySelector(`[data-joint="${name}"]`);
        if(slider&&input.checkValidity())slider.value=input.value;
      }
    });
    jointPreview=null;update();notify('실측 관절값을 입력했습니다. 미리볼 관절을 선택하세요.');
  }catch(e){notify(e.message);}
};
document.getElementById('seat-hold').onclick=async()=>{
  try{const v=await api('/api/seat-hold',{confirmed:document.getElementById('seat-support').checked});notify(v.message);document.getElementById('seat-status').textContent=v.message;}
  catch(e){notify(e.message);document.getElementById('seat-status').textContent=e.message;}
};
document.getElementById('preset-finished').onclick=()=>{
  if(confirm('실제 로봇의 프리셋 동작이 끝난 것을 현장에서 확인했나요? 이 버튼은 동작을 정지시키지 않습니다.'))
    send({action:'acknowledge_motion_complete',confirmed:true});
};
document.getElementById('save-model-key').onclick=async()=>{
  const input=document.getElementById('model-key');
  try{await api('/api/settings/model',{key:input.value});input.value='';await loadConfig();notify('모델 키를 현재 프로세스에 적용했습니다. 파일에는 저장하지 않습니다.');}
  catch(e){notify(e.message);}
};
refreshRobotFacts();
async function refreshActionMap(){
  try{
    const response=await fetch('/api/action-map'),v=await response.json();
    document.getElementById('mapping-status').textContent=`${v.connected?'연결됨':'실물 미연결'} · 설치 SDK 매핑 ${Object.keys(v.mappings).length}개 · 실제 재생 여부는 별도 확인`;
    document.getElementById('vlm-action-map').textContent=JSON.stringify(Object.fromEntries(Object.entries(v.mappings).map(([name,p])=>[name,{label:p.label,motion:p.motion,area:p.area,interrupt:p.interrupt}])),null,2);
    const inventory=await (await fetch('/api/sdk-map')).json();
    document.getElementById('sdk-coverage').textContent=`SDK 서비스 ${inventory.summary.service_total}개 스키마 정리 · 실행/조회 연결 ${inventory.summary.service_mapped}개. 나머지 인터페이스의 미연결 이유는 전체 JSON에서 확인할 수 있습니다.`;
    document.getElementById('sdk-service-list').replaceChildren(...inventory.services.filter(s=>s.coverage==='mapped').map(s=>{
      const row=document.createElement('div');row.className='sdk-service-row';const title=document.createElement('b'),status=document.createElement('small');
      title.textContent=s.label;status.textContent=s.name+' · '+(s.service_ready===true?'서비스 응답 가능':s.service_ready===false?'서비스 미연결':'기기 연결 후 확인');row.append(title,status);return row;
    }));
  }catch{}
  setTimeout(refreshActionMap,10000);
}
refreshActionMap();

async function showPostureGuide(name){
  try{
    const response=await fetch('/api/postures/'+name),v=await response.json();
    if(!response.ok)throw Error(v.error||'절차를 읽지 못했습니다.');
    const root=document.getElementById('posture-guide');root.replaceChildren();root.hidden=false;
    const title=document.createElement('b');title.textContent=v.label+' · '+v.controller;
    const steps=document.createElement('ol');for(const step of v.steps){const item=document.createElement('li');item.textContent=step;steps.append(item);}
    const reason=document.createElement('p');reason.textContent='SDK 연결 · '+v.reason;
    root.append(title,steps,reason);
    document.getElementById('posture-dialog').showModal();
  }catch(e){notify(e.message);}
}
document.getElementById('sit-down-guide').onclick=()=>showPostureGuide('sit_down');
document.getElementById('stand-up-guide').onclick=()=>showPostureGuide('stand_up_from_seat');

document.getElementById('close-posture-guide').onclick=()=>document.getElementById('posture-dialog').close();

async function executePosture(name){
  try{
    const result=await api('/api/postures/'+name,{confirmed:document.getElementById('posture-support').checked});
    document.getElementById('posture-progress').textContent=result.message;notify(result.message);
  }catch(e){notify(e.message);document.getElementById('posture-progress').textContent=e.message;}
}
document.getElementById('stand-up-execute').onclick=()=>executePosture('stand_up_from_seat');
document.getElementById('sit-down-execute').onclick=()=>executePosture('sit_down');
document.getElementById('seat-support').onchange=updatePostureControls;
document.getElementById('posture-support').onchange=updatePostureControls;
document.getElementById('prepare-posture').onclick=()=>document.getElementById('posture-controls').scrollIntoView({behavior:'smooth',block:'start'});
