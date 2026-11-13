/* Shared camera selection; /sensor adds inventory without a control WebSocket. */
(()=>{
  const $=id=>document.getElementById(id),inventory=$('sensor-list'),detail=!!inventory;
  const cards=new Map(),kinds={camera:'RGB 카메라',depth:'깊이 카메라',lidar:'라이다',imu:'자세·가속도',calibration:'카메라 렌즈',touch:'터치',gnss:'위치',power:'전원',joint:'관절',audio:'오디오',status:'장치 상태',video_info:'영상 형식',raw_info:'원본 패킷 형식'};
  let snapshot=null,signature='',selected='',selecting=false,noticeTimer,retryTimer;
  function notify(text){
    const notice=$('notice');if(!notice)return;
    notice.textContent=text;notice.hidden=false;clearTimeout(noticeTimer);
    noticeTimer=setTimeout(()=>notice.hidden=true,6000);
  }
  function syncCamera(topic,force=false){
    const item=snapshot?.sensors?.find(sensor=>sensor.topic===topic);
    if($('view')&&item)$('view').value=topic;
    if($('view-label'))$('view-label').textContent=item?.label||'카메라';
    if(snapshot?.connected&&(force||topic!==selected)){
      selected=topic;
      if(!detail||!document.hidden){$('camera').src='/camera/stream/head_color?camera='+Date.now();$('camera').hidden=false;}
      window.dispatchEvent(new CustomEvent('x2:camera-selected',{detail:{topic,label:item?.label}}));
    }
  }
  async function chooseCamera(topic){
    if(selecting)return;
    selecting=true;$('view').disabled=true;
    try{
      const response=await fetch('/api/camera/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic})});
      const result=await response.json();if(!response.ok)throw Error(result.error||'카메라를 선택하지 못했습니다.');
      if(snapshot)snapshot.camera_selected=topic;
      syncCamera(topic,true);notify(($('view-label')?.textContent||'카메라')+' 영상을 기다립니다.');
      if(snapshot)render(snapshot);
    }catch(error){if(selected)$('view').value=selected;notify(error.message);}
    finally{selecting=false;$('view').disabled=!snapshot?.connected;}
  }
  if($('view'))$('view').onchange=()=>chooseCamera($('view').value);
  function filterInventory(){
    if(!inventory)return;
    const query=($('sensor-search')?.value||'').trim().toLocaleLowerCase();let count=0;
    for(const refs of cards.values()){refs.card.hidden=!refs.search.includes(query);if(!refs.card.hidden)count++;}
    $('sensor-empty').hidden=!cards.size||count>0;
    $('sensor-filter-summary').textContent=cards.size?`${count}개 표시 / 전체 ${cards.size}개`:'';
  }
  function render(data){
    snapshot=data;
    const sensors=data.sensors||[],receiving=sensors.filter(item=>item.receiving).length;
    if($('sensor-summary'))$('sensor-summary').textContent=data.connected?`수신 중 ${receiving} / 전체 ${sensors.length}`:'로봇 연결 대기';
    if($('sensor-connection')){$('sensor-connection').textContent=data.connected?'● AGIBOT X2 연결됨':'로봇 연결 대기';$('sensor-connection').className='badge '+(data.connected?'ok':'bad');}
    if($('save-sensors'))$('save-sensors').disabled=!sensors.length;
    const nextSignature=JSON.stringify(sensors.map(item=>[item.topic,item.datatype]));
    if(inventory&&nextSignature!==signature){
      signature=nextSignature;cards.clear();inventory.replaceChildren();
      for(const item of sensors){
        const card=document.createElement('article');card.className='sensor-card';
        const title=document.createElement('h3');title.textContent=item.label;
        const description=document.createElement('p');description.textContent=`${item.location} · ${kinds[item.kind]||item.kind}`;
        const status=document.createElement('p');status.setAttribute('role','status');
        const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='현재 값 · 연결 정보';
        const values=document.createElement('pre');details.append(summary,values);card.append(title,description,status);
        let button;
        if(item.preview){button=document.createElement('button');button.textContent='영상 보기';button.onclick=()=>chooseCamera(item.topic);card.append(button);}
        card.append(details);inventory.append(card);
        cards.set(item.topic,{card,status,values,button,search:[item.label,item.location,item.kind,kinds[item.kind],item.topic].join(' ').toLocaleLowerCase()});
      }
      if(!sensors.length){const empty=document.createElement('p');empty.className='subtle';empty.textContent='로봇 연결 후 장치 목록을 가져옵니다.';inventory.append(empty);}
      filterInventory();
    }
    const cameras=sensors.filter(item=>item.preview&&(!item.topic.endsWith('/rgb_image')||!sensors.some(other=>other.topic===item.topic+'/compressed'&&other.publishers>0)));
    const view=$('view'),cameraSignature=JSON.stringify(cameras.map(item=>[item.topic,item.publishers>0]));
    if(view){
      if(cameras.length&&view.dataset.sensorSignature!==cameraSignature){
        view.replaceChildren(...cameras.map(item=>{const option=document.createElement('option');option.value=item.topic;option.textContent=item.label;option.disabled=!item.publishers;return option;}));
        view.dataset.sensorSignature=cameraSignature;
      }
      view.disabled=selecting||!data.connected||!cameras.some(item=>item.publishers>0);
      if(data.camera_selected)syncCamera(data.camera_selected);
    }
    for(const item of sensors){
      const refs=cards.get(item.topic);if(!refs)continue;
      refs.status.className=item.receiving?'sensor-receiving':'sensor-waiting';
      refs.status.textContent=!data.connected?'로봇 연결 대기':item.error?item.error:item.receiving?
        `수신 중 · ${item.hz} Hz · ${item.age_ms}ms 전`:item.publishers>0?
        (item.metadata_only?'데이터 형식 정보':item.preview?'연결 가능 · 영상 보기를 선택하세요.':'데이터 수신 대기'):'로봇에서 데이터가 공개되기를 기다립니다.';
      refs.values.textContent=JSON.stringify({topic:item.topic,type:item.datatype,publishers:item.publishers,value:item.value},null,2);
      if(refs.button){refs.button.disabled=selecting||!data.connected||item.publishers<1;refs.button.textContent=item.topic===data.camera_selected?'현재 영상':'영상 보기';}
    }
  }
  if($('sensor-search'))$('sensor-search').oninput=filterInventory;
  if($('save-sensors'))$('save-sensors').onclick=()=>{
    if(!snapshot)return;
    const blob=new Blob([JSON.stringify({...snapshot,saved_at:new Date().toISOString()},null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='x2-sensors-'+Date.now()+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  async function cameraStatus(){
    if(!detail)return;
    try{
      const response=await fetch('/api/camera/status');if(!response.ok)throw Error('카메라 상태를 가져오지 못했습니다.');
      const data=await response.json(),camera=data.cameras?.head_color;
      const ready=data.connected&&camera&&!camera.error&&camera.silent_ms!==null&&camera.silent_ms<2000;
      $('camera-status').textContent=ready?`미리보기 ${camera.hz??'—'} fps`:'영상 수신 대기';
      $('camera-status').className='badge '+(ready?'ok':'bad');$('camera-error').hidden=ready;
      $('camera-error').textContent=data.connected?(camera?.error||'선택한 카메라 영상을 기다립니다.'):'로봇 연결 후 카메라 영상을 표시합니다.';
      if(!data.connected){$('camera').hidden=true;$('camera').removeAttribute('src');selected='';}
    }catch{$('camera-status').textContent='서버 연결 확인 중';}
    setTimeout(cameraStatus,document.hidden?5000:2000);
  }
  if(detail){
    $('camera').onerror=()=>{clearTimeout(retryTimer);retryTimer=setTimeout(()=>{if(snapshot?.connected&&!document.hidden)syncCamera(snapshot.camera_selected,true);},2500);};
    document.addEventListener('visibilitychange',()=>{if(document.hidden)$('camera').removeAttribute('src');else if(snapshot?.connected)syncCamera(snapshot.camera_selected,true);});
    cameraStatus();
  }
  async function poll(){
    try{const response=await fetch('/api/sensors');if(!response.ok)throw Error('센서 상태를 가져오지 못했습니다.');render(await response.json());}
    catch{
      if($('sensor-summary'))$('sensor-summary').textContent='서버 연결 확인 중';
      if($('sensor-connection')){$('sensor-connection').textContent='서버 연결 확인 중';$('sensor-connection').className='badge bad';}
      if($('view'))$('view').disabled=true;
      for(const refs of cards.values()){refs.status.textContent='서버 연결 확인 중';refs.status.className='sensor-waiting';if(refs.button)refs.button.disabled=true;}
    }
    setTimeout(poll,document.hidden?5000:2000);
  }
  poll();
})();
