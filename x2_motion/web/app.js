const $ = id => document.getElementById(id);
let socket, state = {}, config = {}, frame = null, result = null;
let activeDirection = null, activeKey = null, holdTimer = null, noticeTimer;
let inFlight = false;
let instructionEpoch=0;
let profileDirty=false,manualModes={};
let registeredMotions=null, jointCatalog=null, jointPreview=null;
const names = {forward:'전진',backward:'후진',left:'왼쪽 이동',right:'오른쪽 이동',turn_left:'왼쪽 회전',turn_right:'오른쪽 회전'};
const gestures = {wave_left:'왼손 흔들기',wave_right:'오른손 흔들기',handshake_left:'왼손 악수',handshake_right:'오른손 악수',raise_left:'왼팔 들기',raise_right:'오른팔 들기',salute_right:'오른손 경례',bow:'인사'};
const keyDirections = {w:'forward',ArrowUp:'forward',s:'backward',ArrowDown:'backward',a:'left',ArrowLeft:'left',d:'right',ArrowRight:'right',q:'turn_left',e:'turn_right'};
const modeLabels={STAND_DEFAULT:'안정 서기',LOCOMOTION_DEFAULT:'보행',SIT_JOINT_DEFAULT:'착석 고정',SIT_UP_DEFAULT:'일어서는 중',SIT_DOWN_DEFAULT:'앉는 중',PASSIVE_DEFAULT:'영토크',DAMPING_DEFAULT:'댐핑',JOINT_DEFAULT:'서기 준비'};
const canExecute=()=>!config.read_only&&$('physical').checked;
function notify(text) { $('notice').textContent=text; $('notice').hidden=false; clearTimeout(noticeTimer); noticeTimer=setTimeout(()=>$('notice').hidden=true,6000); }
function send(value) { if(socket?.readyState===WebSocket.OPEN){socket.send(JSON.stringify(value));return true;}return false; }
async function api(path, data, isForm=false) {
  const response=await fetch(path,{method:'POST',headers:isForm?{}:{'Content-Type':'application/json'},body:isForm?data:JSON.stringify(data||{})});
  const value=await response.json(); if(!response.ok) throw Object.assign(Error(value.error||`요청 실패 (${response.status})`),{errorType:value.error_type}); return value;
}
function endHold(disarm=false,reason='release') {
  const wasManual=activeDirection!==null;
  const hasControl = state.controller==='you' || wasManual;
  clearInterval(holdTimer); holdTimer=null; activeDirection=null; activeKey=null;
  document.querySelectorAll('.dir').forEach(x=>x.classList.remove('held'));
  if(hasControl&&(disarm||wasManual))send({action:disarm?'disarm':'release',reason});
}
function startHold(direction) {
  if(!config.control_permissions?.movement || !state.armed || state.controller!=='you' || activeDirection) return;
  const speed=(state.profile||{})[direction.startsWith('turn_')?'yaw_rps':['left','right'].includes(direction)?'lateral_mps':'forward_mps'];
  if(speed===0){notify('이 방향의 속도가 0입니다. 이동 수치 조절에서 속도를 설정하세요.');return;}
  activeDirection=direction;
  document.querySelector(`[data-direction="${direction}"]`)?.classList.add('held');
  send({action:'hold',direction});
  holdTimer=setInterval(()=>send({action:'hold',direction}),80);
}
function stop() { instructionEpoch++;endHold();send({action:'stop'}); }
function update() {
  if(typeof updateModelPickerBusy==='function')updateModelPickerBusy();
  if(typeof updateRobotOverview==='function')updateRobotOverview(state);
  const connected=state.connected && socket?.readyState===WebSocket.OPEN;
  $('connection').textContent=config.mode==='replay'?'저장 사진 · 실물 미연결':config.read_only?(connected?'● X2 연결 · 읽기 전용':'X2 연결 확인 중 · 읽기 전용'):connected?(state.fsm===null?'SSH 연결 · 운동 RPC 응답 대기':'● AGIBOT X2 연결됨'):'AGIBOT X2 연결 확인 중';
  $('connection').className='badge '+(connected?'ok':'bad');
  $('fsm').textContent=(state.recorded_state?'기록 · ':'')+(modeLabels[state.fsm]||state.fsm||'—');$('fsm').title=state.fsm||'모드 응답 대기';
  const ours=state.armed && state.controller==='you';
  $('arm').disabled=!connected || (!state.ready&&!ours) || (!$('physical').checked&&!ours) || state.controller==='other' || (!ours&&!!state.gesture);
  $('arm').textContent=ours?'제어 해제':'제어 활성화';
  $('control-status').textContent=state.error || (config.read_only?'읽기 전용으로 실행 중입니다.':!connected?'X2 연결을 기다리는 중입니다.':state.controller==='other'?'다른 창에서 제어 중입니다.':!state.ready?`현재 ${state.fsm??'조회 중'} · 내장 프리셋 실행은 안정 서기 응답을 기다립니다.`:state.gesture?`${gestures[state.gesture]||state.gesture} · SDK 응답을 기다립니다.`:ours?'활성화됨 · 허용된 프리셋을 선택하세요.':'현장 조건을 확인한 뒤 프리셋을 선택하세요.');
  document.querySelectorAll('.dir').forEach(x=>x.disabled=!config.control_permissions?.movement||!ours||!!state.gesture||state.execution_source==='plan');
  $('execute-instruction').disabled=!connected || !state.ready || !canExecute() || state.controller==='other' || inFlight;
  $('infer').disabled=inFlight;
  const profile=state.profile||{forward_mps:.2,lateral_mps:.1,yaw_rps:.5,burst_seconds:1};
  $('limit-forward').textContent=profile.forward_mps.toFixed(2)+' m/s';$('limit-lateral').textContent=profile.lateral_mps.toFixed(2)+' m/s';$('limit-yaw').textContent=profile.yaw_rps.toFixed(2)+' rad/s';$('limit-burst').textContent=profile.burst_seconds?profile.burst_seconds.toFixed(1)+'초':'시간 상한 없음';
  if(!profileDirty)document.querySelectorAll('[data-setting]').forEach(x=>x.value=profile[x.dataset.setting]);
  $('apply-settings').disabled=!connected||state.controller==='other'||state.moving||!!state.gesture;
  $('rotation-estimate').textContent=profile.yaw_rps>0?`현재 속도에서 1바퀴는 약 ${(2*Math.PI/profile.yaw_rps).toFixed(1)}초, 2바퀴는 약 ${(4*Math.PI/profile.yaw_rps).toFixed(1)}초가 필요합니다.`:'회전 속도가 0으로 설정되어 있습니다.';
  updateMode();
  document.querySelectorAll('[data-gesture]').forEach(x=>x.disabled=!config.control_permissions?.presets||!connected||!state.ready||!canExecute()||state.controller==='other'||inFlight||!!state.gesture||!state.arm_actions?.[x.dataset.gesture]);
  $('custom-play').disabled=!config.control_permissions?.presets||!connected||!state.ready||!canExecute()||state.controller==='other'||!!state.gesture||!state.custom_actions?.[$('custom-select').value];
  $('custom-stop').disabled=!connected;
  $('arm-progress').textContent=state.gesture?`${gestures[state.gesture]||state.gesture} · SDK 응답 대기`:'';
  document.querySelectorAll('.motion-execute').forEach(x=>x.disabled=!config.control_permissions?.presets||!connected||!state.ready||!canExecute()||state.controller==='other'||!!state.gesture||inFlight||!(x.dataset.kind==='custom_motion'?state.custom_actions?.[x.dataset.name]:state.arm_actions?.[x.dataset.name]));
  const progress=state.pipeline_status;
  if(progress){
    const labels={idle:'대기',arming:'자동 제어 활성화',completed:'계획 처리 종료',inference:'VLM 분석 중',proposal:'계획 생성',no_action:'동작 제안 없음',dispatch:'AGIBOT X2 전송 중',accepted:'AGIBOT X2 요청 수락',stopped:'0 속도 응답 수신',rejected:'요청 실패',blocked:'실행 보류',failed:'분석 실패',invalid_plan:'계획 변환 오류',unsupported:'실행기 미지원',clarify:'지시 확인 필요',analysis_only:'관측 분석'};
    $('pipeline-stage').textContent=labels[progress.stage]||progress.stage;
    $('pipeline-message').textContent=progress.message;
    $('pipeline-progress').dataset.stage=progress.stage;
  }
  document.querySelectorAll('.execute-step').forEach(x=>x.disabled=!connected||!state.ready||!canExecute()||state.controller==='other'||!result?.executable);
  $('joint-preview').disabled=!jointCatalog;
  $('joint-execute').disabled=true;
  $('joint-execute').title='X2 관절 목표는 미리보기만 제공합니다.';
  $('joint-receipt').textContent=jointPreview?JSON.stringify(jointPreview,null,2):'슬라이더 값을 미리보기하세요.';
  if(ours && state.must_release && activeDirection){endHold();notify(`${profile.burst_seconds.toFixed(1)}초 시간 상한으로 정지했습니다. 버튼을 놓았다가 다시 누르세요.`);}
  if(!ours && activeDirection) endHold();
  const events=(state.events||[]).slice(-8).reverse();
  const observed=(state.events||[]).filter(e=>e.event==='motion_observation').at(-1);
  const imu=state.telemetry?.imu;
  $('motion-feedback').textContent=observed?`최근 관측: 회전 변화 ${observed.yaw_delta_deg??'미수신'}° · 추정 이동 ${observed.odom_distance_m??'미수신'}m (동작 완료 판정 아님)`:imu?`IMU yaw ${(imu.yaw_rad*180/Math.PI).toFixed(1)}° · 최대 다리 속도 ${Number(imu.leg_dq_max||0).toFixed(3)} rad/s`:'IMU·추정 위치 피드백 수신 대기';
  const sdkEvents=(state.events||[]).filter(e=>e.api_id||e.service||e.topic||['arm_action_ack','arm_release_ack','custom_stop_ack','stop_ack','mode_ack'].includes(e.event));if(sdkEvents.length)$('sdk-request').textContent=JSON.stringify(sdkEvents.slice(-8),null,2);
  if(events.length) { $('events').replaceChildren(...events.map(e=>{const el=document.createElement('span');el.className='event';el.textContent=`${new Date((e.local_at||e.at)*1000).toLocaleTimeString('ko-KR')} · ${e.event}${e.code!==undefined?' / '+e.code:''}${e.error?' / '+e.error:''}`;return el;})); }
}
function connect() {
  socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws`);
  socket.onopen=()=>loadConfig();
  socket.onmessage=event=>{const value=JSON.parse(event.data);if(value.type==='state'){state=value;update();}else if(value.type==='error')notify(value.message);};
  socket.onclose=()=>{state={connected:false};endHold();update();setTimeout(connect,2500);};
  socket.onerror=()=>socket.close();
}
setInterval(()=>send({action:'ping'}),200);
$('physical').addEventListener('change',()=>{if(!$('physical').checked){instructionEpoch++;endHold(true);}update();});
$('arm').onclick=()=>{if(state.armed&&state.controller==='you'){instructionEpoch++;endHold(true);}else send({action:'arm',confirmed:$('physical').checked});};
$('stop').onclick=stop; $('pad-stop').onclick=stop;
document.querySelectorAll('.dir').forEach(button=>{
  button.addEventListener('pointerdown',e=>{e.preventDefault();button.setPointerCapture(e.pointerId);startHold(button.dataset.direction);});
  for(const event of ['pointerup','pointercancel','lostpointercapture'])button.addEventListener(event,()=>{if(activeDirection)endHold(false,event);});
  button.addEventListener('contextmenu',e=>e.preventDefault());
});
async function ensureControl(){
  if(state.armed&&state.controller==='you')return;
  if(!canExecute()||!state.connected||!state.ready)throw Error('현장 확인과 X2 운동제어 연결을 확인하세요.');
  if(state.controller==='other')throw Error('다른 창에서 제어 중입니다.');
  if(!send({action:'arm',confirmed:true}))throw Error('AGIBOT X2 연결을 확인하세요.');
  const deadline=Date.now()+4000;
  while(!(state.armed&&state.controller==='you')){
    if(Date.now()>deadline||socket?.readyState!==WebSocket.OPEN)throw Error('AGIBOT X2 제어 활성화 응답을 받지 못했습니다.');
    await new Promise(resolve=>setTimeout(resolve,50));
  }
}
document.querySelectorAll('[data-gesture]').forEach(button=>button.onclick=async()=>{try{if(button.dataset.gesture==='release_arm'){send({action:'gesture_release'});return;}await ensureControl();endHold();send({action:'gesture',name:button.dataset.gesture});}catch(e){notify(e.message);}});
$('custom-play').onclick=async()=>{try{await ensureControl();endHold();send({action:'custom_motion',name:$('custom-select').value,confirmed:true});}catch(e){notify(e.message);}};
$('custom-stop').onclick=()=>notify('이동 정지는 Space입니다. 이미 시작된 X2 프리셋은 이 버튼으로 중단되지 않습니다. 현장의 리모컨 정지 절차를 사용하세요.');
$('custom-select').onchange=()=>{const spec=registeredMotions?.actions?.[1]?.find(x=>x.name===$('custom-select').value);$('custom-description').textContent=spec?`${spec.name} · 등록 시간 ${spec.time}초 · 로봇에 저장된 전체 동작을 재생합니다.`:'로봇 등록 목록을 기다립니다.';update();};
document.querySelectorAll('[data-setting]').forEach(input=>input.oninput=()=>{profileDirty=true;});
$('apply-settings').onclick=()=>{const profile={};for(const x of document.querySelectorAll('[data-setting]')){if(!x.checkValidity()){x.reportValidity();return;}profile[x.dataset.setting]=Number(x.value);}if(send({action:'configure',profile})){profileDirty=false;notify('이동 설정 적용을 요청했습니다. 표시되는 현재 값을 확인하세요.');}};
function updateMode(){
  const m=manualModes[$('mode-select').value];
  if(!m)return;
  const reason=!config.control_permissions?.mode_switch?'대시보드에서 모드 전환이 잠겨 있습니다.':
    !state.connected?'로봇 연결을 기다리고 있습니다.':
    typeof state.fsm!=='string'?'현재 로봇 모드 수신을 기다리고 있습니다.':
    state.controller==='other'?'다른 창에서 제어 중입니다.':
    state.gesture||state.arm_pending?'이전 모션 요청의 SDK 응답을 기다리고 있습니다.':
    m.from&&!m.from.includes(state.fsm)?'현재 모드에서는 이 전환을 요청할 수 없습니다.':
    !$('mode-confirm').checked?'아래에서 선택 모드의 자세·지지 조건을 확인해 주세요.':'';
  $('mode-condition').textContent=`${m.label} · ${m.condition}${reason?' · '+reason:' · 전환 요청 가능'}`;
  $('apply-mode').disabled=!!reason;
  $('apply-mode').title=reason||`${m.label} 모드 전환 요청`;
}
$('mode-select').onchange=()=>{$('mode-confirm').checked=false;updateMode();};$('mode-confirm').onchange=updateMode;
$('apply-mode').onclick=()=>{const confirmed=$('mode-confirm').checked;if(!confirmed||$('apply-mode').disabled)return;send({action:'set_mode',mode:$('mode-select').value,confirmed,condition_confirmed:confirmed});$('mode-confirm').checked=false;updateMode();};
document.addEventListener('keydown',e=>{
  if(e.code==='Escape'){instructionEpoch++;endHold(true);return;}
  if(['TEXTAREA','INPUT','SELECT'].includes(e.target.tagName))return;
  if(e.code==='Space'){e.preventDefault();stop();return;}
  const key=e.key.length===1?e.key.toLowerCase():e.key, direction=keyDirections[key];
  if(direction){e.preventDefault();if(!e.repeat&&!activeDirection){startHold(direction);activeKey=key;}}
});
document.addEventListener('keyup',e=>{const key=e.key.length===1?e.key.toLowerCase():e.key;if(key===activeKey)endHold();});
window.addEventListener('blur',()=>{if(activeDirection)endHold(true,'manual_blur');});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&activeDirection)endHold(true,'manual_hidden');});
window.addEventListener('beforeunload',()=>{instructionEpoch++;endHold(true);socket?.close();});

$('camera').onerror=()=>setTimeout(()=>{$('camera').src='/camera/stream/head_color?retry='+Date.now();},2500);
function setFrame(value) {frame=value;$('frame').src=value.url;$('frame').hidden=false;$('frame-empty').hidden=true;$('frame-info').textContent=`${value.source} · ${new Date(value.captured_at*1000).toLocaleTimeString('ko-KR')}${value.sensor_frame?' · #'+value.sensor_frame:''}`;}
$('capture').onclick=async()=>{try{$('capture').disabled=true;setFrame(await api('/api/capture'));notify('이 RGB 프레임을 지시와 함께 보냅니다.');}catch(e){notify(e.message);}finally{$('capture').disabled=false;}};
$('image').onchange=async()=>{if(!$('image').files[0])return;try{const form=new FormData();form.append('image',$('image').files[0]);setFrame(await api('/api/upload',form,true));}catch(e){notify(e.message);}finally{$('image').value='';}};
async function submitInstruction(execute=false){
  if(inFlight)return;
  if(!$('instruction').value.trim()){notify('텍스트 지시를 입력하세요.');$('instruction').focus();return;}
  if(execute&&(!canExecute()||!state.connected||!state.ready)){notify('현장 확인과 X2 운동제어 연결을 확인하세요.');return;}
  if(execute&&state.controller==='other'){notify('다른 대시보드 창에서 제어 중입니다.');return;}
  const myEpoch=++instructionEpoch;
  inFlight=true;update();$('infer').textContent='장면과 지시 처리 중…';
  try{
    if(execute&&state.controller==='you')send({action:'disarm'});
    if(!frame||frame.source==='Text only'||(frame.source==='X2 Head RGB'||frame.source==='AGIBOT X2 Head RGB')){try{setFrame(await api('/api/capture'));}catch(e){frame={frame_id:null,source:'Text only'};$('frame').hidden=true;$('frame-empty').hidden=false;$('frame-info').textContent='텍스트만 전달 · 카메라 미수신';notify('카메라를 받지 못해 사용자 텍스트만 모델에 전달합니다.');}}
    result=await api('/api/infer',{instruction:$('instruction').value,frame_id:frame.frame_id,model:$('model').value.trim(),include_lidar:$('include-lidar').checked,execute_requested:execute});
    $('result').hidden=false;$('scene').textContent=result.scene;$('explanation').textContent=result.explanation;
    $('result-meta').textContent=`${result.model} · ${result.plan_status||'plan'}${result.recording?' · 기록 '+result.recording.run_id:''}`;
    setVerdict(result.plan_status,result.decision_reason,result.execution_block_reason);
    $('plan-json').textContent=JSON.stringify({plan_status:result.plan_status,decision_reason:result.decision_reason,actions:result.actions},null,2);
    if(result.decision_reason)$('explanation').textContent+='\nVLM 실행 판단: '+result.decision_reason;if(result.sdk_requests)$('planned-sdk-request').textContent=JSON.stringify(result.sdk_requests,null,2);
    $('actions').replaceChildren();
    if(!result.actions.length){const el=document.createElement('p');el.className='no-action';el.textContent='이동 명령 미전송: VLM이 동작을 제안하지 않았습니다. 위 판단 이유와 실제 주변 환경을 확인하세요.';$('actions').append(el);}
    result.actions.forEach((action,index)=>{
      const row=document.createElement('div');row.className='action-row';const text=document.createElement('div');const name=document.createElement('b');name.textContent=`${index+1}. ${action.type==='gesture'?(gestures[action.name]||action.name):action.type==='custom_motion'?action.name:action.type==='mode'?(manualModes[action.name]?.label||action.name):action.type==='stop'?'정지':(names[action.direction]||'이동')}${action.type==='move'?' · ['+action.velocity.join(', ')+'] m/s, m/s, rad/s':''}${['gesture','custom_motion'].includes(action.type)?' · SDK 응답 후 요청 해제':action.seconds?' · '+action.seconds+'초':''}`;const reason=document.createElement('small');reason.textContent=action.reason;text.append(name,reason);
      const button=document.createElement('button');button.className='execute-step';button.textContent='이 단계 실행';button.onclick=()=>{endHold();if(send({action:'plan_step',plan_id:result.plan_id,index,confirmed:$('physical').checked,support_confirmed:$('joint-support-confirmed').checked})){}else notify('대시보드 연결이 끊겨 전송하지 못했습니다.');};row.append(text,button);$('actions').append(row);
    });update();
    if(execute&&result.actions.length){
      if(myEpoch!==instructionEpoch){notify('지시가 취소됐습니다. VLM 계획만 표시하며 실행하지 않습니다.');return;}
      if(result.executable){
        endHold();
        if(send({action:'plan_execute',plan_id:result.plan_id,confirmed:$('physical').checked,support_confirmed:$('joint-support-confirmed').checked})){
          notify('전체 계획을 순서대로 실행 요청했습니다.');
        }else notify('대시보드 연결이 끊겨 전송하지 못했습니다.');
      }else notify(!result.executable?'계획 실행 보류: '+(result.execution_block_reason||result.execution_info||'실행기 상태를 확인하세요.'):'AGIBOT X2 상태를 확인하세요.');
    }
  }catch(e){result=null;notify(e.message);$('result').hidden=false;setVerdict('error',e.message);$('scene').textContent=e.message;$('explanation').textContent=e.errorType==='plan_validation'?'VLM은 응답했습니다. 마지막 모델 요청의 model_response와 validation_error에서 계획 변환 원인을 확인할 수 있습니다. AGIBOT X2에는 동작을 전송하지 않았습니다.':'요청 오류 내용을 확인하세요. 마지막 모델 요청에서 응답 유무를 확인할 수 있습니다.';$('result-meta').textContent=e.errorType==='plan_validation'?'계획 변환 오류':'요청 실패';$('actions').replaceChildren();$('plan-json').textContent='';}finally{inFlight=false;$('infer').textContent='계획만 보기';update();}
}
$('infer').onclick=()=>submitInstruction(false);
$('execute-instruction').onclick=()=>submitInstruction(true);
function setVerdict(status,reason,blockReason){
  const v=$('verdict');if(!v)return;
  const map={ready:['AI 실행 가능','READY','ok'],blocked:['실행 거절','BLOCKED','bad'],unsupported:['미지원 명령','UNSUPPORTED','warn'],clarify:['확인 필요','CLARIFY','warn'],analysis_only:['관측만','ANALYSIS','neutral'],error:['요청 실패','ERROR','bad']};
  const m=map[status]||['판정',String(status||'').toUpperCase()||'PLAN','neutral'];
  v.hidden=false;v.dataset.kind=m[2];
  $('verdict-badge').textContent=m[1];
  $('verdict-title').textContent=status==='ready'?m[0]:m[0]+' — 왜?';
  $('verdict-reason').textContent=reason||blockReason||'모델이 사유를 제시하지 않았습니다.';
}
async function pollCamera(){try{const response=await fetch('/api/camera/status'),data=await response.json(),rgb=data.cameras?.head_color;const ready=rgb&&!rgb.error&&rgb.silent_ms!==null&&rgb.silent_ms<1000;$('camera-status').textContent=data.replay?'저장 사진 · 실물 미연결':ready?`원본 ${rgb.source_hz??'—'} / 미리보기 ${rgb.hz} fps`:'카메라 대기';$('camera-status').className='badge '+(ready?'ok':'bad');$('camera-error').hidden=ready;$('camera-error').textContent=ready?'':(rgb?.error||data.error||'카메라 수신을 기다리는 중입니다.')+' 카메라가 없으면 사용자 텍스트만 모델에 전달합니다.';}catch{}setTimeout(pollCamera,2500);}
function drawLidar(cloud){
  const canvas=$('lidar-canvas'),ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height,scale=26;
  ctx.fillStyle='#f0f5fa';ctx.fillRect(0,0,w,h);ctx.strokeStyle='#cedae5';ctx.lineWidth=1;
  for(let r=1;r<=5;r++){ctx.beginPath();ctx.arc(w/2,h/2,r*scale,0,Math.PI*2);ctx.stroke();}
  ctx.beginPath();ctx.moveTo(w/2,0);ctx.lineTo(w/2,h);ctx.moveTo(0,h/2);ctx.lineTo(w,h/2);ctx.stroke();
  ctx.fillStyle='#17314a';ctx.font='12px Consolas';ctx.fillText('센서 좌표 XY · 1m / ring',12,20);
  if(!cloud){ctx.fillText('라이다 점군 수신 대기',24,h/2-10);return;}
  ctx.fillStyle='#2459d4';for(const p of cloud.points||[]){if(p.length>=3&&p.every(Number.isFinite))ctx.fillRect(w/2+p[0]*scale,h/2-p[1]*scale,2,2);}
  ctx.fillStyle='#ad352b';ctx.beginPath();ctx.arc(w/2,h/2,4,0,Math.PI*2);ctx.fill();
  ctx.fillStyle='#17314a';ctx.fillText(`${cloud.frame_id||'sensor'} · ${cloud.points_total||0} points · ${cloud.age_ms||0} ms`,12,h-12);
}
async function pollLidar(){
  try{const r=await fetch('/api/lidar/status'),v=await r.json();const ready=!!v.ready;
    $('lidar-status').textContent=ready?'점군 수신 중':v.connected?'점군 수신 대기':'로봇 연결 대기';
    $('lidar-status').className='badge '+(ready?'ok':'');
    $('lidar-message').textContent=ready?`${v.sampled_points}개 점 · ${v.source_hz}Hz · ${v.age_ms}ms 전 수신`:v.error||'ROS 2 점군을 기다리는 중입니다.';
    $('include-lidar').disabled=!ready;if(!ready)$('include-lidar').checked=false;
    if(ready){const fr=await fetch('/api/lidar/frame');drawLidar(fr.ok?await fr.json():null);}else drawLidar(null);
  }catch{drawLidar(null);}setTimeout(pollLidar,document.hidden?3000:200);
}
function renderJointControls(){
  if(!jointCatalog)return;
  const root=$('joint-controls');const previous={};root.querySelectorAll('[data-joint-number]').forEach(input=>{previous[input.dataset.jointNumber]={value:input.value,enabled:root.querySelector(`[data-joint-enabled="${input.dataset.jointNumber}"]`)?.checked};});root.replaceChildren();
  for(const group of ['leg','arm','waist','head']){
    const section=document.createElement('section');section.className='joint-group';
    const heading=document.createElement('h4');heading.textContent=({leg:'다리 12관절',arm:'팔 14관절',waist:'허리 3관절',head:'머리 관절'})[group];section.append(heading);
    for(const name of jointCatalog.groups[group]){
      const spec=jointCatalog.joints[name],row=document.createElement('label');row.className='joint-row';
      const enabled=document.createElement('input');enabled.type='checkbox';enabled.dataset.jointEnabled=name;enabled.checked=previous[name]?.enabled??false;
      const title=document.createElement('span');title.textContent=name;
      const slider=document.createElement('input');slider.type='range';slider.min=spec.lower;slider.max=spec.upper;slider.step='0.01';slider.value=previous[name]?.value??'0';slider.dataset.joint=name;slider.disabled=!enabled.checked;
      const number=document.createElement('input');number.type='number';number.min=spec.lower;number.max=spec.upper;number.step='0.01';number.value=previous[name]?.value??'0';number.dataset.jointNumber=name;number.disabled=!enabled.checked;
      enabled.onchange=()=>{slider.disabled=number.disabled=!enabled.checked;jointPreview=null;update();};
      slider.oninput=()=>{number.value=slider.value;jointPreview=null;update();};number.oninput=()=>{if(number.checkValidity()){slider.value=number.value;jointPreview=null;update();}};
      row.append(enabled,title,slider,number);section.append(row);
    }
    root.append(section);
  }
}
function readJointPose(){
  const joints={};document.querySelectorAll('[data-joint-number]').forEach(input=>{if(document.querySelector(`[data-joint-enabled="${input.dataset.jointNumber}"]`)?.checked&&input.value!=='')joints[input.dataset.jointNumber]=Number(input.value);});
  return {joints,seconds:Number($('joint-seconds').value)};
}
async function previewJoints(){try{jointPreview=await api('/api/joints/preview',readJointPose());notify(`typed target 검증 완료 · ${jointPreview.target_sha256.slice(0,12)}…`);update();}catch(e){jointPreview=null;notify(e.message);update();}}
$('joint-preview').onclick=previewJoints;
$('joint-support-confirmed').onchange=update;
$('joint-execute').onclick=()=>notify('X2 관절 목표는 미리보기만 제공합니다.');
async function loadCapabilities(){try{const r=await fetch('/api/capabilities'),v=await r.json();$('command-catalog').textContent=JSON.stringify(v.planner_capabilities||v.catalog,null,2);$('system-prompt').textContent=v.system_prompt;manualModes=v.catalog.manual_modes||{};Object.assign(gestures,Object.fromEntries(Object.entries(v.catalog.gestures||{}).map(([k,x])=>[k,x.label||k])));jointCatalog=v.joint_contract||v.catalog.joint_pose;renderJointControls();if(!$('mode-select').options.length)for(const [name,spec]of Object.entries(manualModes)){const option=document.createElement('option');option.value=name;option.textContent=spec.label;$('mode-select').append(option);}updateMode();}catch{}setTimeout(loadCapabilities,10000);}
async function loadConfig(){
  try{
    const response=await fetch('/api/config'),value=await response.json();config=value;
    $('physical').disabled=!!value.read_only;
    if(value.operator_ready)$('physical').checked=true;
    if(value.read_only)$('physical').checked=false;
    if(value.mode==='offline'){
      $('camera').hidden=true;$('camera').onerror=null;$('camera').removeAttribute('src');
      $('camera').parentElement.dataset.offline='true';$('view-label').textContent='OFFLINE · 로컬 분석';
    }else{
      $('camera').hidden=false;delete $('camera').parentElement.dataset.offline;
      $('camera').src='/camera/stream/head_color';
      if(value.mode==='replay'){$('view-label').textContent='RECORDED · 실물 미연결';$('capture').textContent='현재 프레임 사용';}
    }
    if(typeof configureModelPicker==='function')configureModelPicker(value.pipeline);else{$('model').value=value.pipeline.model;$('model').disabled=value.pipeline.provider!=='OpenRouter';}
    $('pipeline-status').textContent=value.pipeline.configured?`${value.pipeline.provider} 준비됨`:'키 설정 필요';
    $('pipeline-status').className='badge '+(value.pipeline.configured?'ok':'bad');update();
  }catch(e){notify(e.message);}
}
loadConfig();
loadCapabilities();
function renderMotions(){
  if(!registeredMotions)return;
  const presets=registeredMotions.actions?.[0]||[],custom=registeredMotions.actions?.[1]||[];
  $('preset-count').textContent=`${presets.length}개${registeredMotions.recorded?' · 저장 목록':''}`;
  $('motion-library-title').textContent=`등록 모션 전체 · 프리셋 ${presets.length} / 사용자 정의 ${custom.length}${registeredMotions.recorded?' · 저장 목록':''}`;
  const quickOrder=['raise_left','raise_right','wave_left','wave_right'];
  const quick=quickOrder.map(name=>presets.find(p=>p.name===name)).filter(Boolean);
  const signature=quick.map(p=>p.name).join('|');
  if($('quick-presets').dataset.signature!==signature){
    $('quick-presets').dataset.signature=signature;
    $('quick-presets').replaceChildren(...quick.map(p=>{const b=document.createElement('button');b.dataset.gesture=p.name;b.textContent=p.label;b.disabled=true;b.onclick=async()=>{try{await ensureControl();endHold();send({action:'gesture',name:p.name});}catch(e){notify(e.message);}};return b;}));
  }
  $('quick-presets').hidden=!quick.length;
  $('custom-controls').hidden=!custom.length;
  const filter=$('motion-search').value.toLowerCase(),items=[...presets.map(x=>({...x,category:'프리셋'})),...custom.map(x=>({...x,category:'사용자 정의'}))];
  $('motion-library').replaceChildren(...items.filter(x=>`${x.id??''} ${x.name} ${x.display_name||''}`.toLowerCase().includes(filter)).map(x=>{const el=document.createElement('div');el.className='motion-entry';const title=document.createElement('b');title.textContent=`${x.id!==undefined?'#'+x.id+' · ':''}${x.display_name||x.name}`;const meta=document.createElement('small');meta.textContent=[x.category,x.category==='프리셋'?(x.sdk_binding_present?'설치 SDK 상수 확인 · 재생 미검증':'SDK 버전 호환 미확인'):x.support_status||''].filter(Boolean).join(' · ');const reason=document.createElement('small');reason.className='motion-block-reason';reason.dataset.name=x.name;reason.textContent=x.block_reason||'';const button=document.createElement('button');button.className='motion-execute';button.dataset.name=x.name;button.dataset.kind=x.category==='사용자 정의'?'custom_motion':'gesture';button.title=x.block_reason||'현장 조건 확인 후 요청';button.textContent=x.category==='사용자 정의'?'전체 모션 재생':'프리셋 실행';button.onclick=async()=>{try{await ensureControl();endHold();send({action:button.dataset.kind,name:x.name,confirmed:true});}catch(e){notify(e.message);}};el.append(title,meta,reason,button);return el;}));
  const selected=$('custom-select').value;
  $('custom-select').replaceChildren(...custom.map(spec=>{const option=document.createElement('option');option.value=spec.name;option.textContent=spec.name;return option;}));
  if(custom.some(x=>x.name===selected))$('custom-select').value=selected;
  if(custom.length)$('custom-select').onchange();
  update();
}
$('motion-search').oninput=renderMotions;
fetch('/api/motions').then(r=>r.json()).then(v=>{registeredMotions=v;renderMotions();}).catch(()=>{});
connect();pollCamera();pollLidar();
setInterval(()=>fetch('/api/motions').then(r=>r.json()).then(v=>{registeredMotions=v;renderMotions();}).catch(()=>{}),10000);

async function pollModelRequest(){try{const r=await fetch("/api/pipeline/request"),v=await r.json();$("model-request").textContent=JSON.stringify(v,null,2);}catch{}setTimeout(pollModelRequest,2500);}
$("copy-prompt").onclick=async()=>{try{await navigator.clipboard.writeText($("system-prompt").textContent);notify("현재 시스템 메시지를 복사했습니다.");}catch{notify("시스템 메시지 텍스트를 선택해 복사하세요.");}};
pollModelRequest();
