'use strict';
let modelChoices=[],selectedModel='',modelProvider='OpenRouter',modelLoading=false,modelLoaded=false,modelWarning='',modelScope='';
const modelSelectionKey='agibot-x2.openrouter-model';

function updateModelPickerBusy(){
  const unavailable=modelProvider!=='OpenRouter';
  $('model').disabled=unavailable||inFlight;
  $('model-search').disabled=unavailable||inFlight;
  $('refresh-models').disabled=unavailable||inFlight||modelLoading;
}

function renderModelChoices(){
  const select=$('model'),query=$('model-search').value.trim().toLowerCase();
  const filtered=modelChoices.filter(model=>`${model.name} ${model.id} ${model.provider}`.toLowerCase().includes(query));
  const groups=new Map();select.replaceChildren();
  if(!filtered.some(model=>model.id===selectedModel)){
    const current=document.createElement('option');current.value=selectedModel;
    const known=modelChoices.find(model=>model.id===selectedModel);
    current.textContent=`현재 선택 · ${known?.name||selectedModel}`;select.append(current);
  }
  for(const model of filtered){
    if(!groups.has(model.provider)){
      const group=document.createElement('optgroup');group.label=model.provider;groups.set(model.provider,group);select.append(group);
    }
    const option=document.createElement('option');option.value=model.id;option.textContent=`${model.name} · ${model.id}`;
    groups.get(model.provider).append(option);
  }
  select.value=selectedModel;
  const selected=modelChoices.find(model=>model.id===selectedModel);
  const details=[selectedModel];
  if(selected){
    details.push('이미지 입력');
    if(selected.context_length)details.push(`컨텍스트 ${selected.context_length.toLocaleString()} 토큰`);
    const price=selected.pricing_per_million;
    if(price?.prompt!=null&&price?.completion!=null){
      const usd=value=>'$'+value.toLocaleString('en-US',{maximumFractionDigits:5});
      details.push(`1M 토큰 입력 ${usd(price.prompt)} / 출력 ${usd(price.completion)}`);
    }
  }
  $('model-detail').textContent=details.join(' · ');
  $('model-list-status').textContent=modelLoading?'이미지 지원 모델을 불러오는 중…':modelProvider!=='OpenRouter'?'외부 파이프라인의 모델 설정을 사용합니다.':
    modelWarning||`${query?`검색 ${filtered.length} / `:''}이미지 지원 ${modelChoices.length}개${modelScope?' · '+modelScope:''} · 다음 요청에 적용`;
  updateModelPickerBusy();
}

async function refreshOpenRouterModels(force=false){
  if(modelProvider!=='OpenRouter'||modelLoading)return;
  modelLoading=true;renderModelChoices();
  try{
    const response=await fetch('/api/models'+(force?'?refresh=1':''));const data=await response.json();
    if(!response.ok)throw Error(data.error||'모델 목록을 불러오지 못했습니다.');
    modelChoices=data.models||[];modelWarning=data.warning||'';modelLoaded=true;
    modelScope=data.account_filtered?'계정 설정 반영':'OpenRouter 공개 목록';
  }catch(error){modelWarning=error.message+' · 목록 새로고침으로 다시 시도하세요.';}
  finally{modelLoading=false;renderModelChoices();}
}

function configureModelPicker(pipeline){
  modelProvider=pipeline.provider;
  if(!selectedModel){
    try{selectedModel=localStorage.getItem(modelSelectionKey)||'';}catch{}
    selectedModel=selectedModel||pipeline.model;
  }
  renderModelChoices();
  if(modelProvider==='OpenRouter'&&!modelLoaded)refreshOpenRouterModels();
}

$('model-search').oninput=renderModelChoices;
$('refresh-models').onclick=()=>refreshOpenRouterModels(true);
$('model').onchange=()=>{
  selectedModel=$('model').value;
  try{localStorage.setItem(modelSelectionKey,selectedModel);}catch{}
  renderModelChoices();
};
if(config.pipeline)configureModelPicker(config.pipeline);
