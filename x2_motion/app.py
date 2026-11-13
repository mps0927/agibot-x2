"""AGIBOT X2 port of the team's G1 dashboard, serving the same web workspace."""
import argparse
import asyncio
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import shlex
import time
import uuid
from collections import deque

import asyncssh
from aiohttp import web
from PIL import Image

from dashboard_base import Dashboard, make_app
from capabilities import DEFAULT_PROFILE, PRESETS, MODES, DIRECTIONS, preset_mapping
from sdk_catalog import sdk_inventory
from control_policy import permissions, command_allowed, preset_block_reason, seat_hold_check, SEAT_MODE
from worker_deploy import install_worker
from pipeline import load_openrouter_config
from posture_actions import posture_guide,validate_posture_request,POSTURES
from vlm_recording import save_json
from configuration import ROOT,DEFAULT_PORT,load_config,remote_paths,ssh_options
from model_catalog import OpenRouterModels
from lidar import CloudCache,DEFAULT_TOPIC,validate_topic,FRESH_MS
from sensors import DEFAULT_CAMERA

HERE = Path(__file__).parent.resolve()


class RemoteProcess:
    def __init__(self, connection, process):
        self.connection, self.process = connection, process
        self.stdin, self.stdout, self.stderr = process.stdin, process.stdout, process.stderr
    @property
    def returncode(self):
        return self.process.returncode
    def terminate(self):
        self.process.terminate()
        self.connection.close()
    async def wait(self):
        await self.process.wait_closed()
        self.connection.close()
        await self.connection.wait_closed()


class X2Dashboard(Dashboard):
    def __init__(self,args):
        if getattr(args,'replay',None):
            args.offline=True;args.allow_control=False;args.allow_presets=False;args.allow_seat_hold=False;args.allow_posture_actions=False
        env_file=getattr(args,'env_file',None)
        load_config(env_file)
        super().__init__(args)
        self.model_catalog=OpenRouterModels()
        self.lidar=CloudCache()
        self.lidar_session=uuid.uuid4().hex
        self.lidar_subscriptions={}
        self.camera_subscriptions={}
        self.camera_topic=DEFAULT_CAMERA
        self.camera_epoch=0
        self.scopes=permissions(getattr(args,'allow_control',False),getattr(args,'allow_presets',False),getattr(args,'allow_seat_hold',False),getattr(args,'allow_posture_actions',False))
        args.read_only=not any(self.scopes.values())
        self.camera_fps=30
        self.latest_jpeg=None
        self.camera_received=0.
        self.camera_meta={}
        self.preview_condition=asyncio.Condition()
        self.preview_jpeg=None
        self.preview_sequence=0
        self.preview_task=None
        self.camera_arrivals=deque(maxlen=90)
        self.preview_arrivals=deque(maxlen=90)
        self.camera_hz=0.

    async def start(self,application):
        await super().start(application)
        if not getattr(self.args,'offline',False):self.tasks.append(asyncio.create_task(self.poll_lidar()))
        replay=getattr(self.args,'replay',None)
        if not replay:return
        root=Path(replay)
        snapshot=json.loads((root/'state.json').read_text(encoding='utf-8'))
        frame=json.loads((root/'frame.json').read_text(encoding='utf-8'))
        self.state=dict(snapshot,connected=False,ready=False,armed=False,moving=False,gesture=None,arm_pending=False,
            seat_hold_pending=False,posture_pending=None,error='',recorded_state=True,control_permissions=self.scopes,
            control_requests_sent=0,mode_changes_sent=0,velocity_publications=0)
        self.state_at=time.monotonic();self.latest_jpeg=(root/'rgb.jpg').read_bytes()
        self.preview_jpeg=await asyncio.to_thread(self.resize_preview,self.latest_jpeg)
        self.camera_received=time.monotonic()
        self.camera_meta=dict(source='Recorded X2 RGB',camera_session='offline-replay',sensor_frame=frame.get('sensor_frame'),
            recorded_captured_at=frame.get('captured_at'),recorded=True)

    async def connect_worker(self):
        connection=await asyncssh.connect(**ssh_options())
        remote_home,remote_sdk=remote_paths();remote_worker=remote_home+'/agibot_dashboard'
        flags=f"X2_ALLOW_CONTROL={int(self.scopes['movement'])} X2_ALLOW_PRESETS={int(self.scopes['presets'])} X2_ALLOW_SEAT_HOLD={int(self.scopes['seat_hold'])} X2_ALLOW_POSTURES={int(self.scopes['posture_actions'])} X2_LIDAR_TOPIC="+shlex.quote(self.lidar.topic)
        command='set -e\nsource /opt/ros/humble/setup.bash\nsource '+shlex.quote(remote_sdk+'/install/setup.bash')+'\nexec env PYTHONUNBUFFERED=1 X2_SDK_ROOT='+shlex.quote(remote_sdk)+' '+flags+' python3 '+shlex.quote(remote_worker+'/x2_worker.py')
        try:
            await install_worker(connection,HERE,target=remote_worker)
            process=await connection.create_process('bash --noprofile --norc -c '+shlex.quote(command),encoding=None)
        except BaseException:
            connection.close();await connection.wait_closed();raise
        return RemoteProcess(connection,process)

    async def invalidate_connection(self):
        self.camera_epoch+=1
        self.lidar.clear()
        self.lidar_session=uuid.uuid4().hex
        self.latest_jpeg=None
        self.preview_jpeg=None
        self.camera_arrivals.clear();self.preview_arrivals.clear()
        if self.preview_task:
            self.preview_task.cancel()
            await asyncio.gather(self.preview_task,return_exceptions=True)
            self.preview_task=None
        self.camera_received=0.
        await super().invalidate_connection()

    def accept_camera(self,data):
        if data.get('topic') and data['topic']!=self.camera_topic:return
        try:
            jpeg=base64.b64decode(data['jpeg'],validate=True)
            if not jpeg.startswith(b'\xff\xd8') or len(jpeg)>6*1024*1024:return
        except (ValueError,KeyError):return
        now=time.monotonic()
        self.camera_arrivals.append(now)
        self.camera_hz=self.rate(self.camera_arrivals)
        self.latest_jpeg=jpeg
        self.camera_received=now
        self.camera_meta=dict(source=data.get('label') or 'X2 Head RGB',sensor_kind=data.get('kind','camera'),sensor_frame=data.get('sequence'),
                              camera_session='x2-live',topic=data.get('topic'),sensor_frame_name=data.get('frame_id'),
                              source_hz=data.get('source_hz'),preview_fps=data.get('preview_fps',self.camera_fps))
        if data.get('kind')=='depth':
            self.camera_meta.update(rendering='Depth visualization: brighter means closer, invalid samples are black, display range 0 to 6 meters.',depth_display_max_m=6)
        if not self.preview_task or self.preview_task.done():
            self.preview_task=asyncio.create_task(self.prepare_preview())

    @staticmethod
    def rate(samples):
        return round((len(samples)-1)/(samples[-1]-samples[0]),1) if len(samples)>1 and samples[-1]>samples[0] else 0.

    @staticmethod
    def resize_preview(jpeg):
        with Image.open(io.BytesIO(jpeg)) as picture:
            # libjpeg decodes at half resolution before the small final resize.
            # Full-resolution bytes remain untouched for capture and VLM input.
            picture.draft('RGB',(1280,960))
            picture.thumbnail((1280,960),Image.Resampling.BILINEAR);buffer=io.BytesIO()
            picture.convert('RGB').save(buffer,format='JPEG',quality=80)
            return buffer.getvalue()

    async def prepare_preview(self):
        # Keep only the latest frame. Resize once off the event loop and share
        # the result across viewers; slow viewers skip frames independently.
        while self.latest_jpeg and not self.closing:
            original=self.latest_jpeg
            topic=self.camera_topic
            jpeg=await asyncio.to_thread(self.resize_preview,original)
            if topic!=self.camera_topic or self.latest_jpeg is None:continue
            async with self.preview_condition:
                self.preview_jpeg=jpeg;self.preview_sequence+=1
                self.preview_arrivals.append(time.monotonic())
                self.preview_condition.notify_all()
            if self.latest_jpeg is original:break

    async def send(self,msg):
        if msg.get('action')=='arm_joint_pose':
            raise ValueError('대시보드 실행기에서 직접 관절 제어를 구현·검증하지 않아 미리보기만 제공합니다.')
        if not command_allowed(msg.get('action'),self.scopes,msg.get('mode')):
            raise ValueError('이 대시보드에서 해당 제어 권한이 잠겨 있습니다. 실행 설정을 확인하세요.')
        if msg.get('action')=='gesture' and msg.get('name') not in self.state.get('arm_actions',{}):
            raise ValueError('설치 SDK에서 확인된 프리셋만 요청할 수 있습니다.')
        outgoing=dict(msg)
        outgoing.setdefault('request_id',uuid.uuid4().hex)
        await super().send(outgoing)
        if getattr(self,'active_run_manifest',None):self.append_capture_event(self.active_run_manifest,'worker_command_sent',command=outgoing)

    async def config(self,request):
        profile=self.state.get('profile',DEFAULT_PROFILE)
        return web.json_response(dict(pipeline=self.pipeline.info(),mode='replay' if getattr(self.args,'replay',None) else 'offline' if self.args.offline else 'ssh-direct',
            robot=os.environ.get('X2_SSH_HOST','10.0.1.41'),instance_id=getattr(self.args,'instance_id',''),translation_mps=profile['forward_mps'],yaw_rps=profile['yaw_rps'],
            max_burst_seconds=profile['burst_seconds'],operator_ready=False,read_only=self.args.read_only,
            joint_pose_enabled=False,robot_id='agibot_x2_ultra_t2d5',control_permissions=self.scopes,
            camera_fps=self.camera_fps,seat_hold_supported=self.scopes['seat_hold']))

    async def motions(self,request):
        available=preset_mapping(self.state.get('arm_actions',{}))
        if not self.state.get('connected') and not self.state.get('recorded_state'):available={}
        common=preset_block_reason(self.state.get('fsm'),self.scopes,self.state.get('connected',False),bool(self.state.get('gesture')))
        presets=[dict(p,display_name=p['label'],sdk_binding_present=True,
                      block_reason=common) for p in available.values()]
        custom=list(self.state.get('custom_actions',{}).values())
        return web.json_response(dict(actions=[presets,custom],executor_actions={k:p['motion'] for k,p in available.items()},
            connected=bool(self.state.get('connected')),recorded=bool(self.state.get('recorded_state')),
            provenance='Installed SDK bindings only; live GetRobotResources for custom actions',
            preset_execution_verified=False,custom_list_received=bool(self.state.get('connected'))))

    async def action_map(self,request):
        mapped=preset_mapping(self.state.get('arm_actions',{}))
        return web.json_response(dict(schema='x2.action-map.v1',sdk_version=self.state.get('sdk_version'),
            connected=bool(self.state.get('connected')),required_modes=['STAND_DEFAULT','LOCOMOTION_DEFAULT'],
            allowed_action_types=['gesture','custom_motion','move','stop'],mappings=mapped,
            movement=dict(topic='/aima/mc/locomotion/velocity',directions=list(DIRECTIONS),permission=self.scopes['movement']),
            manual_modes=MODES,manual_postures=POSTURES,seat_hold=dict(action_desc=SEAT_MODE,service='/aimdk_5Fmsgs/srv/SetMcAction'),
            physical_execution_verified=False,completion_tracking='operator_confirmation',
            example=dict(scene='관찰한 장면',explanation='오른손 인사',plan_status='ready',decision_reason='현장 준비와 모드 조건 충족',
                         actions=[dict(type='gesture',name='wave_right',reason='사용자의 인사 지시')])) )

    async def sdk_map(self,request):
        return web.json_response(sdk_inventory(self.state))

    async def camera_status(self,request):
        if getattr(self.args,'replay',None):
            return web.json_response(dict(replay=True,cameras=dict(head_color=dict(hz=0,source_hz=0,configured_fps=30,silent_ms=0,error=None))))
        age=int((time.monotonic()-self.camera_received)*1000) if self.camera_received else None
        return web.json_response(dict(cameras=dict(head_color=dict(hz=self.rate(self.preview_arrivals),transport_hz=self.camera_hz,
            source_hz=self.camera_meta.get('source_hz'),configured_fps=self.camera_fps,silent_ms=age,
            error=None if self.latest_jpeg else self.state.get('camera_error') or '선택한 카메라 영상을 기다리는 중입니다.')),
            topic=self.camera_topic,label=self.camera_meta.get('source'),connected=self.sensor_connected()))

    def sensor_state_updated(self):
        selected=self.state.get('lidar',{}).get('topic')
        if selected and selected!=self.lidar.topic:self.lidar.select(selected)
        camera=self.state.get('camera_selected')
        if camera and camera!=self.camera_topic:
            self.camera_epoch+=1
            self.camera_topic=camera;self.latest_jpeg=None;self.preview_jpeg=None;self.camera_received=0.
            self.camera_arrivals.clear();self.preview_arrivals.clear();self.camera_meta={}
            self.frames.clear();self.plans.clear()

    async def sensor_status(self,request):
        connected=self.sensor_connected();delay=(time.monotonic()-self.state_at)*1000 if self.state_at else 0
        sensors=[]
        for spec in self.state.get('sensors',[]):
            age=spec.get('age_ms')
            sensors.append(dict(spec,age_ms=int(age+delay) if age is not None else None,
                receiving=bool(connected and age is not None and age+delay<2000)))
        return web.json_response(dict(connected=connected,sensors=sensors,camera_selected=self.camera_topic))

    async def select_camera(self,request):
        data=await request.json();topic=data.get('topic')
        if not self.sensor_connected():raise ValueError('로봇 연결 후 카메라를 선택하세요.')
        match=next((spec for spec in self.state.get('sensors',[]) if spec['topic']==topic),None)
        if not match or not match.get('preview') or match.get('publishers',0)<1:raise ValueError('수신 가능한 카메라를 선택하세요.')
        ident=uuid.uuid4().hex;future=asyncio.get_running_loop().create_future();self.camera_subscriptions[ident]=future
        try:
            await self.send(dict(action='camera_select',topic=topic,request_id=ident))
            result=await asyncio.wait_for(future,3)
            if result.get('event')!='camera_selected':raise ValueError(result.get('error') or '카메라를 전환하지 못했습니다.')
        finally:self.camera_subscriptions.pop(ident,None)
        self.camera_epoch+=1
        self.camera_topic=topic;self.latest_jpeg=None;self.preview_jpeg=None;self.camera_received=0.
        self.camera_arrivals.clear();self.preview_arrivals.clear();self.camera_meta={}
        self.frames.clear();self.plans.clear()
        return web.json_response(dict(status='SUBSCRIBED',topic=topic,control_request_sent=False))

    async def capture(self,request):
        if not getattr(self.args,'replay',None) and (not self.state.get('connected') or not self.latest_jpeg or time.monotonic()-self.camera_received>2):
            raise ValueError('최신 X2 RGB 프레임이 없습니다.')
        return web.json_response(self.store_frame(self.latest_jpeg,dict(self.camera_meta),persist=True))

    async def stream(self,request):
        if getattr(self.args,'replay',None):return web.Response(body=self.preview_jpeg,content_type='image/jpeg')
        if request.match_info['view']!='head_color':raise web.HTTPNotFound(text='현재 수신 중인 카메라는 전면 RGB입니다.')
        response=web.StreamResponse(headers={'Content-Type':'multipart/x-mixed-replace; boundary=x2frame','Cache-Control':'no-store'})
        await response.prepare(request)
        try:
            sequence=-1
            while not self.closing:
                async with self.preview_condition:
                    try:await asyncio.wait_for(self.preview_condition.wait_for(lambda:self.preview_jpeg is not None and self.preview_sequence!=sequence),2)
                    except asyncio.TimeoutError:continue
                    jpeg=self.preview_jpeg;sequence=self.preview_sequence
                await response.write(b'--x2frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(jpeg)).encode()+b'\r\n\r\n'+jpeg+b'\r\n')
        except (ConnectionError,asyncio.CancelledError):pass
        return response

    async def seat_hold(self,request):
        if not self.state.get('connected') or not self.state_at or time.monotonic()-self.state_at>1:
            raise ValueError('최신 X2 상태를 기다리세요.')
        data=await request.json()
        mode_age=self.state.get('mode_age_ms');leg_age=self.state.get('leg_age_ms');delay=time.monotonic()-self.state_at
        outcome=seat_hold_check(self.state.get('fsm'),None if mode_age is None else mode_age/1000+delay,
            confirmed=data.get('confirmed') is True,leg_age=None if leg_age is None else leg_age/1000+delay,joints=self.state.get('joint_values',{}))
        if outcome=='ALREADY_ACTIVE':
            return web.json_response(dict(status=outcome,fsm=SEAT_MODE,control_request_sent=False,message='이미 착석 고정 상태입니다. 추가 모드 명령을 전송하지 않았습니다.'))
        if self.owner or (self.plan_task and not self.plan_task.done()) or self.state.get('gesture') or self.state.get('arm_pending') or self.state.get('seat_hold_pending'):
            raise ValueError('다른 제어 또는 모드 전환의 종료를 기다리세요.')
        await self.send(dict(action='seat_hold',confirmed=True))
        return web.json_response(dict(status='REQUEST_SENT',fsm=SEAT_MODE,control_request_sent=True,
            message='착석 고정을 한 번 요청했습니다. SDK 응답과 현재 모드가 SIT_JOINT_DEFAULT로 바뀌는지 확인하세요.'),status=202)

    async def posture(self,request):
        return web.json_response(posture_guide(request.match_info['name']))

    async def execute_posture(self,request):
        name=request.match_info['name'];data=await request.json()
        if not self.state.get('connected') or not self.state_at or time.monotonic()-self.state_at>1:raise ValueError('최신 로봇 상태를 기다리세요.')
        delay=time.monotonic()-self.state_at;mode_age=self.state.get('mode_age_ms');leg_age=self.state.get('leg_age_ms')
        outcome=validate_posture_request(name,self.state.get('fsm'),self.state.get('fsm_status'),
            None if mode_age is None else mode_age/1000+delay,None if leg_age is None else leg_age/1000+delay,
            self.state.get('joint_values',{}),data.get('confirmed') is True)
        if outcome=='ALREADY_ACTIVE':return web.json_response(dict(status=outcome,control_request_sent=False,message='이미 목표 모드입니다. 추가 명령을 보내지 않았습니다.'))
        if (self.plan_task and not self.plan_task.done()) or any(self.state.get(k) for k in ('moving','gesture','arm_pending','seat_hold_pending','posture_pending')):
            raise ValueError('이전 동작·모드 전환의 완료를 기다리세요.')
        if self.owner:
            raise ValueError('현재 조종 창에서 제어를 해제한 뒤 자세 전환을 요청하세요.')
        await self.send(dict(action='posture',name=name,confirmed=True))
        return web.json_response(dict(status='REQUEST_SENT',action_desc=POSTURES[name]['action_desc'],completion_mode=POSTURES[name]['completion_mode'],
            control_request_sent=True,message=POSTURES[name]['label']+' SDK 요청을 한 번 전송했습니다. 현재 모드와 실제 자세를 확인하세요.'),status=202)

    async def lidar_status(self,request):
        connected=self.sensor_connected();ready=self.lidar.ready(connected)
        metadata=self.state.get('lidar',{})
        if metadata.get('topic')!=self.lidar.topic:metadata={}
        frame=self.lidar.frame or {}
        if not connected:error='로봇 전원과 LAN 연결을 확인하세요. 연결되면 라이다 점군을 자동 구독합니다.'
        elif metadata.get('error'):error=metadata['error']
        elif self.lidar.age_ms() is not None and self.lidar.age_ms()>=FRESH_MS:error='라이다 점군 수신이 멈췄습니다. 센서 발행 상태를 확인하세요.'
        elif self.lidar.frame is not None and not frame.get('points'):error='점군은 수신했지만 표시할 유효 XYZ 좌표가 없습니다.'
        elif metadata.get('publishers')==0:error='로봇 SDK에서 이 점군 토픽을 발행하지 않습니다. 로봇의 라이다 드라이버·센서 설정 확인이 필요합니다.'
        else:error='로봇에서 PointCloud2 점군을 기다리는 중입니다.'
        return web.json_response(dict(connected=connected,ready=ready,topic=self.lidar.topic,
            expected_topic=DEFAULT_TOPIC,sensor=dict(model='RoboSense E1R',presence='X2_ULTRA_VENDOR_SPEC'),
            available_topics=metadata.get('available_topics',[]),publishers=metadata.get('publishers'),
            source_hz=metadata.get('source_hz',0),preview_hz_limit=5,age_ms=self.lidar.age_ms(),
            frame_id=frame.get('frame_id'),points_total=frame.get('points_total',0),
            sampled_points=len(frame.get('points',[])),error='' if ready else error))

    def sensor_connected(self):
        return bool(self.state.get('connected') and self.state_at and (time.monotonic()-self.state_at)*1000<FRESH_MS)

    def accept_lidar(self,data):
        self.lidar.accept(dict(data,session_id=self.lidar_session))

    def lidar_event(self,data):
        if data.get('event') in ('camera_selected','camera_select_error'):
            future=self.camera_subscriptions.get(data.get('request_id'))
            if future and not future.done():future.set_result(data)
            return
        if data.get('event') not in ('lidar_subscription','lidar_subscription_error'):return
        future=self.lidar_subscriptions.get(data.get('request_id'))
        if future and not future.done():future.set_result(data)

    async def poll_lidar(self):
        while not self.closing:
            try:
                pending=self.lidar.pending
                if self.sensor_connected() and (not pending or time.monotonic()-pending[1]>=FRESH_MS/1000):
                    ident=uuid.uuid4().hex
                    self.lidar.request(ident)
                    await super().send(dict(action='lidar_frame_request',request_id=ident))
            except (RuntimeError,OSError,asyncio.TimeoutError,asyncssh.Error):
                self.lidar.pending=None
            await asyncio.sleep(.2)

    def lidar_observation(self):
        return self.lidar.observation(self.sensor_connected())

    async def lidar_frame(self,request):
        return web.json_response(self.lidar.snapshot(self.sensor_connected()))
    async def lidar_topic(self,request):
        data=await request.json();topic=validate_topic(data.get('topic'))
        if not self.sensor_connected():raise ValueError('로봇이 연결되면 점군 토픽을 선택할 수 있습니다.')
        candidates=self.state.get('lidar',{}).get('available_topics',[])
        if topic!=DEFAULT_TOPIC and topic not in candidates:raise ValueError('조회된 LiDAR 점군 토픽을 선택하세요.')
        ident=uuid.uuid4().hex;future=asyncio.get_running_loop().create_future();self.lidar_subscriptions[ident]=future
        try:
            await self.send(dict(action='lidar_topic',topic=topic,request_id=ident))
            result=await asyncio.wait_for(future,3)
            if result.get('event')!='lidar_subscription':raise ValueError(result.get('error') or '점군 구독을 변경하지 못했습니다.')
            self.lidar.select(topic)
        finally:self.lidar_subscriptions.pop(ident,None)
        return web.json_response(dict(status='SUBSCRIBED',topic=topic,control_request_sent=False))

    async def infer(self,request):
        response=await super().infer(request)
        data=json.loads(response.text)
        native=[a for a in data['actions'] if a['type'] in ('gesture','custom_motion')]
        if native and len(data['actions'])!=1:
            data.update(executable=False,execution_block_reason='프리셋 완료 조회 바인딩이 없어 프리셋은 한 번에 한 동작만 요청할 수 있습니다.')
            self.plans[data['plan_id']]['plan_status']='blocked'
        disallowed=[a for a in data['actions'] if not command_allowed({'move':'hold','gesture':'gesture','custom_motion':'custom_motion','stop':'stop'}.get(a['type'],'arm_joint_pose'),self.scopes)]
        if disallowed:
            data.update(executable=False,execution_block_reason='현재 실행 권한에서 지원하지 않는 동작입니다. 실행 설정과 동작 목록을 확인하세요.')
            self.plans[data['plan_id']]['plan_status']='blocked'
        if data.get('recording'):save_json(Path(data['recording']['directory'])/'result.json',data)
        return web.json_response(data)

    async def status(self,request):
        reason=preset_block_reason(self.state.get('fsm'),self.scopes,self.state.get('connected',False),bool(self.state.get('gesture')))
        return web.json_response(dict(self.state,read_only=self.args.read_only,control_permissions=self.scopes,
            preset_block_reason=reason,seat_hold_supported=self.scopes['seat_hold'],seat_hold_block_reason='착석 고정 요청에는 착석·지지 확인과 최신 상태가 필요합니다.',
            restrictions=[dict(layer='내장 프리셋 API',reason='SetMcPresetMotion의 문서상 조건은 안정 서기입니다. PDF의 착석 상체 제어는 별도 텔레옵 경로이며, 앉아서 팔을 움직일 수 없다는 뜻은 아닙니다.'),
                dict(layer='설치 SDK 버전',reason='설치 SDK에서 정확한 매핑이 확인된 프리셋을 표시합니다. SDK 응답을 받으면 요청 잠금을 자동으로 해제합니다.'),
                dict(layer='대시보드 설정',reason='현재 권한: '+', '.join(k for k,v in self.scopes.items() if v)+'. 직접 관절 실행은 미리보기만 제공합니다.'),
                dict(layer='착석 고정',reason='↑ + × 후 실제 조회한 SIT_JOINT_DEFAULT로 SetMcAction을 요청합니다. 코드상 연결됐으며 기기의 수락 여부와 실제 모드는 별도로 확인합니다.')],
            received_age_ms=int((time.monotonic()-self.state_at)*1000) if self.state_at else None,
            events=list(self.events)))

    async def model_settings(self,request):
        data=await request.json()
        key=data.get('key','')
        if not isinstance(key,str) or not 1<=len(key.strip())<=500:raise ValueError('OpenRouter API 키를 입력하세요.')
        self.pipeline.key=key.strip()
        return web.json_response(dict(configured=True,persisted=False))

    async def models(self,request):
        if self.pipeline.endpoint:
            return web.json_response(dict(enabled=False,models=[],selected=self.pipeline.model,provider='HTTP pipeline'))
        data=await self.model_catalog.list(self.session,self.pipeline.key,request.query.get('refresh')=='1')
        self.pipeline.model_parameters={model['id']:model['supported_parameters'] for model in data['models']}
        return web.json_response(dict(data,enabled=True,selected=self.pipeline.model,provider='OpenRouter'))


def create_app(args):
    dashboard=X2Dashboard(args)
    application=make_app(dashboard)
    application['dashboard']=dashboard
    application.router.add_get('/api/status',dashboard.status)
    application.router.add_get('/api/action-map',dashboard.action_map)
    application.router.add_get('/api/sdk-map',dashboard.sdk_map)
    application.router.add_get('/api/models',dashboard.models)
    application.router.add_get('/api/sensors',dashboard.sensor_status)
    application.router.add_post('/api/camera/select',dashboard.select_camera)
    application.router.add_post('/api/settings/model',dashboard.model_settings)
    application.router.add_post('/api/seat-hold',dashboard.seat_hold)
    application.router.add_get('/api/postures/{name}',dashboard.posture)
    application.router.add_post('/api/postures/{name}',dashboard.execute_posture)
    return application

def parse_args(argv=None):
    config_parser=argparse.ArgumentParser(add_help=False)
    config_parser.add_argument('--env-file',default=os.environ.get('X2_ENV_FILE',str(ROOT/'.env')))
    config_args,_=config_parser.parse_known_args(argv);load_config(config_args.env_file)
    parser=argparse.ArgumentParser(description='AGIBOT X2 dashboard; read-only by default')
    parser.add_argument('--port',type=int,default=int(os.environ.get('X2_PORT',DEFAULT_PORT)))
    parser.add_argument('--bind',choices=('127.0.0.1','0.0.0.0'),default=os.environ.get('X2_BIND','127.0.0.1'))
    parser.add_argument('--instance-id',default=uuid.uuid4().hex,help=argparse.SUPPRESS)
    parser.add_argument('--allow-control',action='store_true',help='Enable explicit operator requests; never performs startup motion')
    parser.add_argument('--allow-presets',action='store_true',help='Allow operator presets without enabling locomotion or general mode switches')
    parser.add_argument('--allow-seat-hold',action='store_true',help='Allow seated preparation request after posture/support checks')
    parser.add_argument('--allow-posture-actions',action='store_true',help='Enable chair get-up/sit-down and manual mode requests')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--replay',help='Read a saved robot_snapshot directory without connecting or controlling hardware')
    parser.add_argument('--origin',default='')
    parser.add_argument('--env-file',default=config_args.env_file,help='Local configuration file (never executed as shell code)')
    args=parser.parse_args(argv)
    if not 1<=args.port<=65535:parser.error('port must be 1..65535')
    if args.offline or args.replay:
        args.offline=True;args.allow_control=False;args.allow_presets=False;args.allow_seat_hold=False;args.allow_posture_actions=False
    args.read_only=not(args.allow_control or args.allow_presets or args.allow_seat_hold or args.allow_posture_actions)
    args.operator_ready=False
    return args

if __name__=='__main__':
    args=parse_args()
    web.run_app(create_app(args),host=args.bind,port=args.port,access_log=None,shutdown_timeout=3)
