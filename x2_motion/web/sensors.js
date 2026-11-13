/* Robot sensor inventory and selected-camera control; no motion requests. */
let sensorSnapshot=null,sensorSignature='';
const sensorCards=new Map();
const sensorKinds={camera:'RGB 카메라',depth:'깊이 카메라',lidar:'라이다',imu:'자세·가속도',calibration:'카메라 렌즈',touch:'터치',gnss:'위치',power:'전원',joint:'관절',audio:'오디오',status:'장치 상태',video_info:'영상 형식',raw_info:'원본 패킷 형식'};

async function chooseSensorCamera(topic){
  try{
    await api('/api/camera/select',{topic});
    frame=null;result=null;
    update();
    $('view').value=topic;
    $('camera').src='/camera/stream/head_color?camera='+Date.now();
    const selected=sensorSnapshot?.sensors.find(item=>item.topic===topic);
    $('view-label').textContent=selected?.label||'카메라';
    notify((selected?.label||'카메라')+' 영상을 기다립니다.');
  }catch(error){notify(error.message);}
}
$('view').onchange=()=>chooseSensorCamera($('view').value);

function visibleSensorCameras(sensors){
  return sensors.filter(item=>item.preview&&(!item.topic.endsWith('/rgb_image')||
    !sensors.some(other=>other.topic===item.topic+'/compressed'&&other.publishers>0)));
}

function renderSensorInventory(data){
  sensorSnapshot=data;
  const sensors=data.sensors||[],receiving=sensors.filter(item=>item.receiving).length;
  $('sensor-summary').textContent=data.connected?`수신 중 ${receiving} / 전체 ${sensors.length}`:'로봇 연결 대기';
  const cameras=visibleSensorCameras(sensors),signature=JSON.stringify(sensors.map(item=>[item.topic,item.datatype]));
  if(signature!==sensorSignature){
    sensorSignature=signature;sensorCards.clear();$('sensor-list').replaceChildren();
    for(const item of sensors){
      const card=document.createElement('article');card.className='sensor-card';
      const title=document.createElement('h3');title.textContent=item.label;
      const description=document.createElement('p');description.textContent=`${item.location} · ${sensorKinds[item.kind]||item.kind}`;
      const status=document.createElement('p');status.setAttribute('role','status');
      const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='현재 값 · 연결 정보';
      const values=document.createElement('pre');details.append(summary,values);card.append(title,description,status);
      let button;
      if(item.preview){button=document.createElement('button');button.textContent='영상 보기';button.onclick=()=>chooseSensorCamera(item.topic);card.append(button);}
      card.append(details);$('sensor-list').append(card);sensorCards.set(item.topic,{status,values,button});
    }
  }
  const cameraSignature=JSON.stringify(cameras.map(item=>[item.topic,item.publishers>0]));
  if(cameras.length&&$('view').dataset.sensorSignature!==cameraSignature){
    $('view').replaceChildren(...cameras.map(item=>{const option=document.createElement('option');option.value=item.topic;option.textContent=item.label;option.disabled=!item.publishers;return option;}));
    $('view').dataset.sensorSignature=cameraSignature;
  }
  if(cameras.some(item=>item.topic===data.camera_selected))$('view').value=data.camera_selected;
  for(const item of sensors){
    const refs=sensorCards.get(item.topic);if(!refs)continue;
    refs.status.className=item.receiving?'sensor-receiving':'sensor-waiting';
    refs.status.textContent=!data.connected?'로봇 연결 대기':item.error?item.error:item.receiving?
      `수신 중 · ${item.hz} Hz · ${item.age_ms}ms 전`:item.publishers>0?
      (item.metadata_only?'데이터 형식 정보':item.preview?'연결 가능 · 영상 보기를 선택하세요.':'데이터 수신 대기'):'로봇에서 데이터가 공개되기를 기다립니다.';
    refs.values.textContent=JSON.stringify({topic:item.topic,type:item.datatype,publishers:item.publishers,value:item.value},null,2);
    if(refs.button){refs.button.disabled=!data.connected||item.publishers<1;refs.button.textContent=item.topic===data.camera_selected?'현재 영상':'영상 보기';}
  }
}

$('save-sensors').onclick=()=>{
  if(!sensorSnapshot)return;
  const blob=new Blob([JSON.stringify({...sensorSnapshot,saved_at:new Date().toISOString()},null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='x2-sensors-'+Date.now()+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};

async function pollSensors(){
  try{const response=await fetch('/api/sensors');if(response.ok)renderSensorInventory(await response.json());}catch{}
  setTimeout(pollSensors,document.hidden?5000:2000);
}
pollSensors();
