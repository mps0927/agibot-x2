"""Discover image-input chat models; credentials stay on the local server."""
import asyncio,hashlib,math,re,time
from aiohttp import ClientError,ClientTimeout

MODEL_ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,199}\Z')

def vision_models(data):
    if not isinstance(data,dict) or not isinstance(data.get('data'),list):
        raise ValueError('OpenRouter 모델 목록 응답 형식이 올바르지 않습니다.')
    models={}
    for item in data['data']:
        if not isinstance(item,dict):continue
        model_id=item.get('id');architecture=item.get('architecture') or {}
        if not isinstance(model_id,str) or not MODEL_ID.fullmatch(model_id) or not isinstance(architecture,dict):continue
        inputs=architecture.get('input_modalities') or [];outputs=architecture.get('output_modalities') or []
        if not isinstance(inputs,list) or not isinstance(outputs,list) or not all(isinstance(x,str) for x in inputs+outputs):continue
        if not {'text','image'}.issubset(inputs) or 'text' not in outputs:continue
        endpoints=item.get('endpoints')
        if isinstance(endpoints,list) and '/api/v1/chat/completions' not in endpoints:continue
        pricing={}
        for key in ('prompt','completion'):
            try:
                number=float((item.get('pricing') or {}).get(key))
                if math.isfinite(number) and number>=0:pricing[key]=number*1000000
            except (TypeError,ValueError,AttributeError):pass
        parameters=item.get('supported_parameters') or []
        context=item.get('context_length')
        models[model_id]=dict(id=model_id,name=str(item.get('name') or model_id)[:240],provider=model_id.split('/',1)[0],
            context_length=context if type(context) is int and context>0 else None,
            pricing_per_million=pricing,supported_parameters=[p for p in parameters if isinstance(p,str)] if isinstance(parameters,list) else [],
            input_modalities=['text','image'],output_modalities=['text'])
    return sorted(models.values(),key=lambda model:(model['provider'].casefold(),model['name'].casefold(),model['id']))

class OpenRouterModels:
    def __init__(self,base_url='https://openrouter.ai/api/v1',ttl=300):
        self.base_url=base_url;self.ttl=ttl;self.lock=asyncio.Lock();self.cached=None;self.cached_at=0.;self.identity=None

    async def list(self,session,key='',refresh=False):
        identity=hashlib.sha256(key.encode()).digest()
        async with self.lock:
            if self.identity!=identity:self.cached=None;self.cached_at=0.;self.identity=identity
            if self.cached is not None and not refresh and time.monotonic()-self.cached_at<self.ttl:
                return dict(self.cached,cached=True,stale=False)
            try:
                account=bool(key)
                headers={'Authorization':'Bearer '+key} if key else {}
                path='/models/user' if account else '/models'
                async def fetch(path,headers):
                    async with session.get(self.base_url+path,params={'input_modalities':'image','output_modalities':'text'},
                        headers=headers,timeout=ClientTimeout(total=12),allow_redirects=False) as response:
                        if response.status!=200:return response.status,None
                        return response.status,await response.json()
                status,data=await fetch(path,headers)
                if account and status in (403,404):
                    account=False;status,data=await fetch('/models',{})
                if status!=200:raise RuntimeError('OpenRouter 모델 목록 조회 실패 ('+str(status)+')')
                models=vision_models(data)
                self.cached=dict(models=models,count=len(models),account_filtered=account,updated_at=time.time(),warning='')
                self.cached_at=time.monotonic()
                return dict(self.cached,cached=False,stale=False)
            except (ClientError,asyncio.TimeoutError,ValueError,RuntimeError) as exc:
                if self.cached is not None:
                    return dict(self.cached,cached=True,stale=True,warning='목록을 갱신하지 못해 이전 목록을 표시합니다.')
                if isinstance(exc,RuntimeError):raise
                raise RuntimeError('OpenRouter 모델 목록을 불러오지 못했습니다. 인터넷 연결을 확인하고 다시 시도하세요.') from None
