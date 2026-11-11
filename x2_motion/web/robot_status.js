'use strict';

const jointStatusRows = new Map();
const jointGroupLabels = {left_arm:'왼팔',right_arm:'오른팔',left_leg:'왼다리',right_leg:'오른다리',waist:'허리',head:'머리'};
const jointPartLabels = {shoulder_pitch:'어깨 앞뒤',shoulder_roll:'어깨 좌우',shoulder_yaw:'어깨 회전',
  elbow:'팔꿈치',wrist_pitch:'손목 앞뒤',wrist_roll:'손목 좌우',wrist_yaw:'손목 회전',
  hip_pitch:'고관절 앞뒤',hip_roll:'고관절 좌우',hip_yaw:'고관절 회전',knee:'무릎',
  ankle_pitch:'발목 앞뒤',ankle_roll:'발목 좌우',waist_pitch:'허리 앞뒤',waist_roll:'허리 좌우',
  waist_yaw:'허리 회전',head_yaw:'머리 회전'};
const toDegrees = value => value * 180 / Math.PI;

function updateBatteryStatus(value) {
  const card=document.getElementById('battery-status');
  const percent=value.battery_percent;
  const available=typeof percent==='number'&&Number.isFinite(percent)&&percent>=0&&percent<=100;
  const fresh=!!value.connected&&value.received_age_ms!=null&&value.received_age_ms<1500;
  card.dataset.level=!available?'unknown':percent<=20?'low':percent<=50?'medium':'high';
  card.dataset.stale=String(!fresh);
  document.getElementById('battery-value').textContent=available?`${Math.round(percent)}%`:'—%';
  document.getElementById('battery-fill').style.width=available?`${percent}%`:'0%';
  document.getElementById('battery-caption').textContent=!available?'수신 대기':value.recorded_state?'저장된 잔량':fresh?'실시간 잔량':'최근 수신값';
  card.setAttribute('aria-label',available?`배터리 잔량 ${Math.round(percent)}퍼센트${fresh?'':' · 실시간 연결 대기'}`:'배터리 잔량 수신 대기');
}

function buildJointStatusRows() {
  if(!jointCatalog)return;
  const root=document.getElementById('live-joints');
  const signature=jointCatalog.q_order.join('|');
  if(root.dataset.signature===signature)return;
  root.dataset.signature=signature;root.replaceChildren();jointStatusRows.clear();
  for(const [group,label] of Object.entries(jointGroupLabels)) {
    const names=jointCatalog.q_order.filter(name=>{
      const spec=jointCatalog.joints[name];
      return ['waist','head'].includes(group)?spec.group===group:`${name.startsWith('left_')?'left':'right'}_${spec.group}`===group;
    });
    if(!names.length)continue;
    const section=document.createElement('section');section.className='live-joint-group';
    const heading=document.createElement('h3');heading.textContent=`${label} · ${names.length}`;section.append(heading);
    for(const name of names) {
      const spec=jointCatalog.joints[name];
      const row=document.createElement('label');row.className='live-joint-row';row.dataset.jointState='waiting';
      const caption=document.createElement('span');caption.className='live-joint-name';
      const short=name.replace(/^(left_|right_)/,'').replace(/_joint$/,'');
      caption.textContent=jointPartLabels[short]||short;caption.title=name;
      const output=document.createElement('output');output.className='live-joint-value';output.textContent='—';
      const slider=document.createElement('input');slider.type='range';slider.min=toDegrees(spec.lower);slider.max=toDegrees(spec.upper);
      slider.step='0.1';slider.disabled=true;slider.dataset.liveJoint=name;slider.setAttribute('aria-label',`${label} ${caption.textContent} 현재 각도`);
      const bounds=document.createElement('span');bounds.className='live-joint-bounds';
      const low=document.createElement('span'),status=document.createElement('span'),high=document.createElement('span');
      low.textContent=`${toDegrees(spec.lower).toFixed(0)}°`;high.textContent=`${toDegrees(spec.upper).toFixed(0)}°`;status.textContent='수신 대기';bounds.append(low,status,high);
      row.append(caption,output,slider,bounds);section.append(row);
      jointStatusRows.set(name,{row,output,slider,status,spec});
    }
    root.append(section);
  }
}

function updateJointStatus(value) {
  buildJointStatusRows();
  const joints=value.joint_values||{};let received=0,errors=0,outside=0;
  const fresh=!!value.connected&&value.received_age_ms!=null&&value.received_age_ms<1500;
  for(const [name,view] of jointStatusRows) {
    const joint=joints[name],position=joint?.position;
    const available=typeof position==='number'&&Number.isFinite(position);
    if(!available){view.row.dataset.jointState='waiting';view.output.textContent='—';view.status.textContent='수신 대기';continue;}
    received++;
    const error=typeof joint.error_code==='number'&&joint.error_code!==0;
    const outOfRange=position<view.spec.lower-.02||position>view.spec.upper+.02;
    errors+=Number(error);outside+=Number(outOfRange);
    const degrees=toDegrees(position);
    view.slider.value=degrees;view.output.textContent=`${degrees.toFixed(1)}°`;
    view.slider.setAttribute('aria-valuetext',`${degrees.toFixed(1)}도`);
    view.row.dataset.jointState=error?'error':outOfRange?'outside':fresh?'normal':'stale';
    view.status.textContent=error?`오류 ${joint.error_code}`:outOfRange?'표시 범위 초과':value.recorded_state?'저장된 값':fresh?'정상':'최근 수신값';
    view.row.title=`${name}\n${position.toFixed(4)} rad · ${Number.isFinite(joint.velocity)?joint.velocity.toFixed(3):'—'} rad/s`;
  }
  const count=document.getElementById('joint-health-count');
  count.textContent=errors?`오류 ${errors}`:outside?`범위 확인 ${outside}`:received?`${received}관절`:'조회 중';
  count.dataset.state=errors?'error':outside?'outside':fresh&&received?'normal':'waiting';
  const connection=value.recorded_state?'저장된 상태':fresh?'실시간 수신':'연결 대기 · 최근값 표시';
  document.getElementById('joint-status-summary').textContent=received?`${connection} · ${received}/${jointStatusRows.size}관절 · 오류 ${errors}개`:'관절 상태 수신 대기';
  document.getElementById('live-joints-raw').textContent=JSON.stringify(joints,null,2);
}

function updateRobotOverview(value) {updateBatteryStatus(value);updateJointStatus(value);}
function openJointStatus() {const dialog=document.getElementById('joint-status-dialog');if(!dialog.open)dialog.showModal();}
document.getElementById('open-joint-status').onclick=openJointStatus;
document.getElementById('open-joints-inline').onclick=openJointStatus;
document.getElementById('close-joint-status').onclick=()=>document.getElementById('joint-status-dialog').close();
