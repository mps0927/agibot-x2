/* Local joint preset preview. Never substitute a same-named vendor resource. */
(() => {
  let data=null,started=null,animation=null;
  const canvas=document.getElementById('punch-preview'),ctx=canvas.getContext('2d');
  function draw(at=0){
    if(!data)return;
    const frames=data.preview,frame=frames[Math.min(100,Math.round(at/data.profile.seconds*100))];
    const points=frames.flatMap(x=>x.points),xs=points.map(p=>p[0]),zs=points.map(p=>p[2]);
    const minX=Math.min(-.12,...xs)-.06,maxX=Math.max(.45,...xs)+.06,minZ=Math.min(...zs)-.08,maxZ=Math.max(...zs)+.08;
    const scale=Math.min((canvas.width-70)/(maxX-minX),(canvas.height-55)/(maxZ-minZ));
    const xy=p=>[35+(p[0]-minX)*scale,canvas.height-30-(p[2]-minZ)*scale];
    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.strokeStyle='#bac9dc';ctx.lineWidth=1;ctx.beginPath();
    frames.forEach((f,i)=>{const p=xy(f.points.at(-1));i?ctx.lineTo(...p):ctx.moveTo(...p);});ctx.stroke();
    ctx.strokeStyle='#5366cc';ctx.lineWidth=7;ctx.beginPath();
    frame.points.forEach((p,i)=>i?ctx.lineTo(...xy(p)):ctx.moveTo(...xy(p)));ctx.stroke();
    for(const p of frame.points){ctx.fillStyle='#23394e';ctx.beginPath();ctx.arc(...xy(p),4,0,Math.PI*2);ctx.fill();}
    ctx.fillStyle='#485c70';ctx.font='14px sans-serif';ctx.fillText('측면 X-Z · 손목 궤적 · 전방 →',16,23);
    document.getElementById('punch-frame').textContent=`${at.toFixed(1)} / ${data.profile.seconds.toFixed(1)}초 · ${data.start_source==='measured'?'최근 조회 각도':'영점 참고 각도'} 기준 · 설계 목표속도 상한 ${data.profile.rate} rad/s`;
  }
  window.updatePunchControls=()=>{
    const button=document.getElementById('punch-execute');
    button.hidden=false;
    button.disabled=true; // No MC-preserving joint transport is connected yet.
    button.title=data?.registration?.block_reason||'프리셋 등록 상태를 확인 중입니다.';
  };
  async function refresh(){
    try{
      const r=await fetch('/api/punch');if(!r.ok)throw Error('펀치 시작 관절값을 확인하세요.');
      const next=await r.json();if(!animation)data=next;else{data.replay_available=next.replay_available;data.replay_note=next.replay_note;}document.getElementById('punch-status').textContent=data.replay_note;
      if(!animation)draw();window.updatePunchControls();
    }catch(e){cancelAnimationFrame(animation);animation=null;data=null;document.getElementById('punch-status').textContent=e.message;window.updatePunchControls();}
    setTimeout(refresh,5000);
  }
  document.getElementById('punch-preview-play').onclick=()=>{
    if(!data)return;cancelAnimationFrame(animation);started=performance.now();
    function tick(now){const at=Math.min(data.profile.seconds,(now-started)/1000);draw(at);
      if(at<data.profile.seconds)animation=requestAnimationFrame(tick);else animation=null;}
    animation=requestAnimationFrame(tick);
  };
  refresh();
})();
