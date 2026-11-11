import argparse,asyncio,base64,json,tempfile,unittest
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from app import create_app
from model_catalog import OpenRouterModels,vision_models
from pipeline import Pipeline

def model(ident='demo/vision',**changes):
    return dict(id=ident,name=ident,architecture=dict(input_modalities=['text','image'],output_modalities=['text']),
        endpoints=['/api/v1/chat/completions'],pricing=dict(prompt='0.000001',completion='0.000002'),
        context_length=32000,supported_parameters=['response_format'],**changes)

class ModelFiltering(unittest.TestCase):
    def test_only_image_text_chat_models_are_available(self):
        rows=[model(),model('demo/batch'),model('demo/text'),model('demo/generator'),model('demo/bad')]
        rows[1]['endpoints']=['/api/v1/batches']
        rows[2]['architecture']['input_modalities']=['text']
        rows[3]['architecture']['output_modalities']=['image']
        rows[4]['architecture']['input_modalities']=[{}]
        result=vision_models(dict(data=rows))
        self.assertEqual([m['id'] for m in result],['demo/vision'])
        self.assertEqual(result[0]['pricing_per_million'],dict(prompt=1.,completion=2.))

class ModelCatalogAPI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls=[];self.remote_status=200;self.tmp=tempfile.TemporaryDirectory()
        async def remote(request):
            self.calls.append((request.path,request.headers.get('Authorization'),dict(request.query)))
            if self.remote_status!=200 and request.path.endswith('/user'):return web.json_response({},status=self.remote_status)
            return web.json_response(dict(data=[model(),model('other/vision')]))
        upstream=web.Application();upstream.router.add_get('/api/v1/models',remote);upstream.router.add_get('/api/v1/models/user',remote)
        self.remote=TestServer(upstream);await self.remote.start_server()
        args=argparse.Namespace(offline=True,allow_control=False,allow_presets=False,origin='',operator_ready=False,
            vlm_record_root=Path(self.tmp.name))
        application=create_app(args);self.d=application['dashboard'];self.d.pipeline.key='fixture-only-key'
        self.d.model_catalog=OpenRouterModels(str(self.remote.make_url('/api/v1')).rstrip('/'))
        self.client=TestClient(TestServer(application));await self.client.start_server()
    async def asyncTearDown(self):
        await self.client.close();await self.remote.close();self.tmp.cleanup()

    async def test_catalog_is_cached_refreshable_key_scoped_and_contains_no_credentials(self):
        for _ in range(2):
            response=await self.client.get('/api/models');data=await response.json()
            self.assertEqual(response.status,200);self.assertEqual(data['count'],2)
            self.assertTrue(data['account_filtered']);self.assertNotIn('fixture-only-key',json.dumps(data))
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][1],'Bearer fixture-only-key')
        self.assertEqual(self.calls[0][2],dict(input_modalities='image',output_modalities='text'))
        await self.client.get('/api/models?refresh=1');self.assertEqual(len(self.calls),2)
        self.d.pipeline.key='second-fixture-key'
        await self.client.get('/api/models');self.assertEqual(len(self.calls),3)
        self.assertIsNone(self.d.process)

    async def test_missing_user_catalog_permission_falls_back_to_public_list_without_key(self):
        self.remote_status=403
        data=await (await self.client.get('/api/models')).json()
        self.assertFalse(data['account_filtered']);self.assertEqual(data['count'],2)
        self.assertEqual(len(self.calls),2);self.assertIsNone(self.calls[1][1])

    async def test_outage_keeps_previous_list_marked_stale(self):
        await self.client.get('/api/models');self.remote_status=503
        data=await (await self.client.get('/api/models?refresh=1')).json()
        self.assertTrue(data['stale']);self.assertEqual(data['count'],2);self.assertTrue(data['warning'])

    async def test_invalid_key_is_reported_without_leaking_it_or_using_public_fallback(self):
        self.remote_status=401
        response=await self.client.get('/api/models');data=await response.json()
        self.assertEqual(response.status,400);self.assertIn('401',data['error'])
        self.assertEqual(len(self.calls),1);self.assertNotIn('fixture-only-key',json.dumps(data))

class SelectedModelPayload(unittest.IsolatedAsyncioTestCase):
    async def test_selected_vision_model_and_image_reach_request_with_compatible_parameters(self):
        pipeline=Pipeline();pipeline.key='fixture-only-key';pipeline.endpoint=''
        pipeline.model_parameters={'demo/json':['response_format'],'other/vision':[]}
        sent=[]
        class Reply:
            status=200
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def json(self):return {'choices':[{'message':{'content':json.dumps(dict(scene='fixture',plan_status='analysis_only',actions=[]))}}]}
        class Session:
            def post(self,url,**kwargs):sent.append((url,kwargs));return Reply()
        for selected in ('demo/json','other/vision'):
            await pipeline.infer(Session(),'장면을 설명해',b'\xff\xd8fixture',{},dict(),model=selected)
            payload=sent[-1][1]['json']
            self.assertEqual(payload['model'],selected)
            self.assertEqual(payload['messages'][1]['content'][1]['type'],'image_url')
            self.assertEqual('response_format' in payload,selected=='demo/json')
            self.assertNotIn('fixture-only-key',json.dumps(pipeline.last_request))

if __name__=='__main__':unittest.main()
