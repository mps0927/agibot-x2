"""Robot-side ROS worker. Startup/teardown in default mode send no control request."""
import base64
import json
import math
import os
import queue
import signal
import sys
import threading
import time
from collections import deque
from pathlib import Path
import hashlib

from capabilities import DEFAULT_PROFILE, DIRECTIONS, MODES, PRESETS, validate_profile, validate_velocity, velocity, prepare_preset_request
from control_policy import permissions, command_allowed, MC_REJECTIONS,seat_hold_check,SEAT_MODE,active_locomotion_allowed
from posture_actions import POSTURES,validate_posture_request,prepare_posture_request
from sdk_catalog import READ_QUERIES
from lidar import CloudRelay,DEFAULT_TOPIC,validate_topic
from sensors import SensorRegistry,DEFAULT_CAMERA,IMAGES,lidar_choice,camera_jpeg
from sensors import describe,POINTCLOUD
from sensor_bridge import SensorBridge
from sensor_cdr import deserialize_sensor


def finish_native_request(state,context,code,sdk_state,service,event):
    """Release request ownership on SDK reply, without asserting physical completion."""
    accepted=code==0 and sdk_state in (1,200,300,400)
    result=dict(name=context.get('name'),request_id=context.get('request_id'),code=code,
                sdk_state=sdk_state,accepted=accepted,service=service,physical_outcome='NOT_VERIFIED')
    state.update(gesture=None,arm_pending=False,native_result=result)
    if not accepted:
        state['armed']=False
        state['error']='제조사 모션 요청 거부 · code '+str(code)+' · state '+str(sdk_state)
    event('arm_action_ack',**result)


def main():
    # Vendor FastDDS prints discovery logs on stdout. Keep the JSON transport on
    # its own descriptor, and suppress native discovery logs in this worker only.
    output = os.fdopen(os.dup(1), 'w', buffering=1)
    sink = os.open('/dev/null', os.O_WRONLY)
    os.dup2(sink, 1)
    os.dup2(sink, 2)
    stop = threading.Event()
    output_events=queue.Queue(maxsize=100)
    output_latest={}
    output_lock=threading.Lock()
    output_wake=threading.Event()
    def emit(value):
        line=json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n'
        if value.get('type') in ('state','camera_frame','lidar_frame'):
            with output_lock:output_latest[value['type']]=line
        else:
            try:output_events.put_nowait(line)
            except queue.Full:stop.set()
        output_wake.set()
    def write_output():
        try:
            while not stop.is_set():
                output_wake.wait(.05);output_wake.clear()
                while not output_events.empty():output.write(output_events.get_nowait())
                with output_lock:
                    lines=[output_latest.pop(k) for k in ('state','camera_frame','lidar_frame') if k in output_latest]
                for line in lines:output.write(line)
        except (BrokenPipeError,OSError):stop.set()
    threading.Thread(target=write_output,daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_:stop.set())
    signal.signal(signal.SIGINT, lambda *_:stop.set())
    incoming = queue.Queue(maxsize=100)
    def read_input():
        try:
            for line in sys.stdin:
                if len(line)>16384:continue
                try:incoming.put(json.loads(line),timeout=.2)
                except (ValueError,queue.Full):pass
        finally:stop.set()
    threading.Thread(target=read_input,daemon=True).start()

    import rclpy
    from rclpy.qos import qos_profile_sensor_data,QoSProfile,ReliabilityPolicy,DurabilityPolicy
    from rosidl_runtime_py.convert import message_to_ordereddict as asdict
    from aimdk_msgs.srv import GetMcAction, GetAllJointState, GetRobotResources
    from aimdk_msgs.msg import JointStateArray, HandStateArray, PmuState
    from sensor_msgs.msg import CompressedImage, Imu, PointCloud2
    from rosidl_runtime_py.utilities import get_message
    from rclpy.serialization import deserialize_message
    scopes=permissions(os.environ.get('X2_ALLOW_CONTROL')=='1',os.environ.get('X2_ALLOW_PRESETS')=='1',os.environ.get('X2_ALLOW_SEAT_HOLD')=='1',os.environ.get('X2_ALLOW_POSTURES')=='1')
    enabled=any(scopes.values())
    from aimdk_msgs.srv import SetMcPresetMotion
    motion_class=type(SetMcPresetMotion.Request().motion)
    installed_motion_ids={getattr(motion_class,k) for k in dir(motion_class) if k.isupper() and type(getattr(motion_class,k)) is int}
    available_presets={k:v for k,v in PRESETS.items() if v['motion'] in installed_motion_ids}
    rclpy.init()
    node = rclpy.create_node('x2_dashboard_worker', start_parameter_services=False, enable_rosout=False)
    try:sdk_version=(Path(os.environ.get('X2_SDK_ROOT',str(Path.home()/'aimdk')))/'version').read_text().strip()[:256]
    except OSError:sdk_version='NOT_CONFIRMED'
    state = dict(type='state', backend='aimdk_ros2_humble', sdk_version=sdk_version,
                 worker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 model='X2 Ultra t2d5', fsm=None, fsm_at=0., ready=False, armed=False,
                 moving=False, gesture=None, arm_pending=False,native_result=None,seat_hold_pending=False,posture_pending=None,error='',
                 profile=dict(DEFAULT_PROFILE), arm_actions={k:v['id'] for k,v in available_presets.items()},
                 custom_actions={}, hand_status='확인 중', battery_percent=None,
                 joint_values={}, telemetry={}, sdk_queries={},sdk_services={},read_only=not enabled,
                 control_permissions=scopes,control_requests_sent=0, mode_changes_sent=0, velocity_publications=0)
    mode_at = 0.
    leg_at=0.
    camera = dict(message=None, at=0., sequence=0,source_hz=0.,fps=30,topic=DEFAULT_CAMERA,generation=0,error='')
    sensors=SensorRegistry();sensor_subscriptions={};camera_subscription=None
    native_counts={};unsupported_sensors=set();bridge_types={};bridge=None
    image_times=deque(maxlen=90)
    desired = [0.,0.,0.]
    hold_at = hold_start = 0.
    hold_limit=DEFAULT_PROFILE['burst_seconds']
    must_release = False
    registered = False
    command_busy = False
    mode_target=None
    posture_deadline=0.
    source = 'sdk_x2_dashboard_'+str(os.getpid())
    seen_ids = set()
    outstanding = {}
    clients = {name:node.create_client(typ,'/aimdk_5Fmsgs/srv/'+name) for name,typ in
               [('GetMcAction',GetMcAction),('GetAllJointState',GetAllJointState),('GetRobotResources',GetRobotResources)]}
    import aimdk_msgs.srv as service_types
    for name in READ_QUERIES:
        typ=getattr(service_types,name,None)
        if typ is not None:clients[name]=node.create_client(typ,'/aimdk_5Fmsgs/srv/'+name)
    publisher = None
    def event(event_name, **details):emit(dict(type='event',event=event_name,at=time.time(),**details))
    def timestamp(request):
        for field in ('request','header'):
            obj=getattr(request,field,None)
            if hasattr(obj,'stamp'):obj.stamp=node.get_clock().now().to_msg()
            elif hasattr(obj,'header') and hasattr(obj.header,'stamp'):obj.header.stamp=node.get_clock().now().to_msg()
    def read_response(name,response):
        nonlocal mode_at,mode_target
        if name in READ_QUERIES:
            state['sdk_queries'][name]=dict(received_at=time.time(),response=asdict(response))
            return
        if name=='GetMcAction':
            if response.header.code!=0:raise ValueError('모드 조회 응답 오류')
            state['fsm']=response.info.action_desc;state['fsm_code']=response.header.code
            state['fsm_status']=response.info.status.value
            mode_at=time.monotonic();state['fsm_at']=time.time()
            if mode_target and state['fsm']==mode_target and state['fsm_status']==100:
                state['seat_hold_pending']=False
                event('mode_observed',target_fsm=mode_target);mode_target=None
            pending=state.get('posture_pending')
            if pending and state['fsm']==pending['completion_mode'] and state['fsm_status']==100:
                event('posture_completed',name=pending['name'],target_fsm=pending['completion_mode'],physical_outcome='MODE_OBSERVED')
                state['posture_result']=dict(pending,status='COMPLETED_MODE_OBSERVED')
                state['posture_pending']=None;state['error']=''
            elif pending and state['fsm']==pending['action_desc']:
                pending['phase']='EXECUTING'
        elif name=='GetAllJointState':
            for field in ('arm_joints','leg_joints','waist_joints','head_joints'):
                for j in getattr(response,field):state['joint_values'][j.name]=dict(position=j.position,velocity=j.velocity,error_code=j.error_code)
        elif name=='GetRobotResources':
            if response.header.header.code!=0:raise ValueError('리소스 조회 응답 오류')
            state['custom_actions']={r.current_version.name or r.resource_key:dict(
                name=r.current_version.name or r.resource_key,resource_key=r.resource_key,
                version=r.current_version.version,time=10.,completion_tracking=False)
                for r in response.robot_resources}
    def query(name):
        if name in outstanding or not clients[name].service_is_ready():return
        req=clients[name].srv_type.Request();timestamp(req)
        outstanding[name]=(clients[name].call_async(req),time.monotonic())
    def joints(group,message):
        nonlocal leg_at
        if group=='leg':leg_at=time.monotonic()
        for j in message.joints:state['joint_values'][j.name]=dict(position=float(j.position),velocity=float(j.velocity),error_code=int(j.error_code))
    def hands(message):
        left,right=message.left_hand_type.value,message.right_hand_type.value
        state['hand_status']=f'L:{left} / R:{right}'+(' · NONE' if left==right==0 else '')
        state['hand_types']=[left,right]
        state['hand_joint_counts']=[len(message.left_hands),len(message.right_hands)]
    def pmu(message):
        state['battery_percent']=int(message.battery_remaining_capacity_percentage)
        state['battery_temperature']=float(message.battery_temperature)
    def image(message,generation,transport='ros2'):
        if generation!=camera['generation']:return
        now=time.monotonic();image_times.append(now)
        hz=(len(image_times)-1)/(image_times[-1]-image_times[0]) if len(image_times)>1 and image_times[-1]>image_times[0] else 0.
        sensors.offer(camera['topic'],message,transport)
        camera.update(message=message,at=now,sequence=camera['sequence']+1,frame_id=message.header.frame_id,source_hz=round(hz,1))
    def imu(message):
        q=message.orientation
        yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
        state['telemetry']['imu']=dict(yaw_rad=yaw,leg_dq_max=max((abs(j['velocity']) for k,j in state['joint_values'].items() if any(x in k for x in ('hip','knee','ankle'))),default=0.))
    for group in ('arm','leg','waist','head'):
        node.create_subscription(JointStateArray,'/aima/hal/joint/'+group+'/state',lambda m,g=group:joints(g,m),qos_profile_sensor_data)
    node.create_subscription(HandStateArray,'/aima/hal/joint/hand/state',hands,qos_profile_sensor_data)
    node.create_subscription(PmuState,'/aima/hal/pmu/state',pmu,qos_profile_sensor_data)
    node.create_subscription(Imu,'/aima/hal/imu/torso/state',imu,qos_profile_sensor_data)
    def select_camera(selected,request_id=None):
        nonlocal camera_subscription
        spec=sensors.entries.get(selected)
        if selected!=DEFAULT_CAMERA and (not spec or not spec['preview'] or spec['publishers']<1):
            raise ValueError('수신 가능한 카메라를 선택하세요.')
        datatype=spec['datatype'] if spec else 'sensor_msgs/msg/CompressedImage'
        if datatype not in IMAGES:raise ValueError('카메라 영상 형식이 올바르지 않습니다.')
        generation=camera['generation']+1
        subscription=node.create_subscription(get_message(datatype),selected,lambda m,g=generation:image(m,g),qos_profile_sensor_data)
        previous=camera_subscription;camera_subscription=subscription
        camera.update(message=None,at=0.,source_hz=0.,topic=selected,generation=generation,error='');image_times.clear()
        if previous is not None:node.destroy_subscription(previous)
        event('camera_selected',topic=selected,generation=generation,request_id=request_id,control_request_sent=False)
    select_camera(DEFAULT_CAMERA)
    def send_camera():
        previous=0
        while not stop.is_set():
            began=time.monotonic();snapshot=camera.copy()
            if snapshot['message'] is not None and snapshot['sequence']!=previous and began-snapshot['at']<2:
                try:
                    jpeg=camera_jpeg(snapshot['message'])
                    if snapshot['generation']==camera['generation']:
                        spec=sensors.entries.get(snapshot['topic'],{})
                        emit(dict(type='camera_frame',jpeg=base64.b64encode(jpeg).decode(),at=time.time(),sequence=snapshot['sequence'],frame_id=snapshot['frame_id'],topic=snapshot['topic'],source_hz=snapshot['source_hz'],preview_fps=snapshot['fps'],label=spec.get('label','전면 RGB'),kind=spec.get('kind','camera')))
                    previous=snapshot['sequence']
                except Exception as exc:camera['error']=str(exc)
            stop.wait(max(.001,1/snapshot['fps']-(time.monotonic()-began)))
    threading.Thread(target=send_camera,daemon=True).start()

    lidar=CloudRelay(os.environ.get('X2_LIDAR_TOPIC',DEFAULT_TOPIC))
    lidar_subscription=None
    # BEST_EFFORT/VOLATILE accepts both reliable/transient-local vendor streams
    # and SensorDataQoS streams. Depth 1 prevents an old-cloud backlog.
    lidar_qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.BEST_EFFORT,durability=DurabilityPolicy.VOLATILE)
    def select_lidar(selected,request_id=None):
        nonlocal lidar_subscription
        selected=validate_topic(selected)
        known=dict(node.get_topic_names_and_types()).get(selected,[])
        if known and known!=['sensor_msgs/msg/PointCloud2']:
            raise ValueError('선택한 토픽의 메시지가 PointCloud2가 아닙니다.')
        generation=lidar.generation+1
        def receive_cloud(message,g=generation,t=selected):
            if g==lidar.generation:sensors.offer(t,message)
            lidar.offer(message,g)
        subscription=node.create_subscription(PointCloud2,selected,receive_cloud,lidar_qos)
        lidar.select(selected)
        previous=lidar_subscription;lidar_subscription=subscription
        if previous is not None:node.destroy_subscription(previous)
        event('lidar_subscription',topic=selected,generation=generation,request_id=request_id,control_request_sent=False)
    try:select_lidar(lidar.topic)
    except Exception as exc:
        with lidar.lock:lidar.error=str(exc)
    def send_lidar():
        while not stop.is_set():
            try:
                frame=lidar.take_frame()
                if frame is not None:
                    while len(json.dumps(frame,separators=(',',':')).encode())>128*1024 and len(frame['points'])>1:
                        frame['points']=frame['points'][::2]
                    emit(frame)
            except Exception as exc:
                with lidar.lock:lidar.error=str(exc)
            stop.wait(.2)
    lidar_thread=threading.Thread(target=send_lidar,daemon=True);lidar_thread.start()
    lidar_graph=dict(available_topics=[],publishers=0)
    def sensor_topics():
        topics=dict(node.get_topic_names_and_types())
        if bridge:
            for selected,types in bridge.topics():topics.setdefault(selected,types)
        return list(topics.items())
    def sensor_publishers(selected):
        return max(node.count_publishers(selected),int(bool(bridge and bridge.available(selected))))
    def inspect_lidar():
        try:
            topics=sensor_topics()
            chosen=lidar_choice(topics,sensor_publishers,lidar.topic,DEFAULT_TOPIC)
            if chosen!=lidar.topic:select_lidar(chosen)
            lidar_graph.update(available_topics=[name for name,types in topics
                if 'sensor_msgs/msg/PointCloud2' in types and 'lidar' in name.lower()],
                publishers=sensor_publishers(lidar.topic),native_publishers=node.count_publishers(lidar.topic),
                transport='bridge' if bridge and bridge.available(lidar.topic) and node.count_publishers(lidar.topic)==0 else 'ros2')
        except Exception as exc:lidar_graph['graph_error']=str(exc)

    def inspect_sensors():
        nonlocal native_counts
        topics=sensor_topics();native_counts={selected:node.count_publishers(selected) for selected,_ in topics}
        sensors.discover(topics,sensor_publishers)
        for selected,spec in sensors.entries.items():
            if not spec['publishers'] or selected in sensor_subscriptions or spec['datatype'] in IMAGES or spec['kind'] in ('lidar','video_info','raw_info'):continue
            try:
                sensor_subscriptions[selected]=node.create_subscription(get_message(spec['datatype']),selected,
                    lambda m,t=selected:sensors.offer(t,m),qos_profile_sensor_data)
            except (AttributeError,ImportError):
                sensors.errors[selected]='설치 SDK에 이 센서 데이터의 메시지 정의가 없습니다.'
                unsupported_sensors.add(selected);sensor_subscriptions[selected]=None
            except Exception as exc:sensors.errors[selected]=str(exc)
        if sensor_publishers(camera['topic'])==0:
            fallback=next((topic for topic,spec in sensors.entries.items()
                if spec['preview'] and spec['publishers']>0 and spec['kind']=='camera' and topic.endswith('/compressed')),None)
            if fallback and fallback!=camera['topic']:select_camera(fallback)

    def bridge_wanted(item):
        selected=item['topic'];datatype=item['schemaName'];spec=describe(selected,datatype)
        if not spec or spec['kind'] in ('video_info','raw_info'):return False
        if native_counts.get(selected,0)>0 and selected not in unsupported_sensors:return False
        if datatype in IMAGES:return selected==camera['topic']
        if datatype==POINTCLOUD:return selected==lidar.topic
        return spec['kind']!='lidar'

    def bridge_message(item,payload):
        selected=item['topic'];datatype=item['schemaName']
        if datatype not in bridge_types:
            try:bridge_types[datatype]=get_message(datatype)
            except (AttributeError,ImportError):bridge_types[datatype]=None
        typ=bridge_types[datatype]
        try:
            if typ is not None:message=deserialize_message(payload,typ)
            else:
                # Large telemetry is summarized at most twice per second.
                if time.monotonic()-sensors.sample_at.get(selected,-1)<.5:return
                message=deserialize_sensor(payload,datatype,item.get('schema',''))
            if datatype in IMAGES:
                if selected==camera['topic']:image(message,camera['generation'],'bridge')
            elif datatype==POINTCLOUD:
                if selected==lidar.topic:
                    sensors.offer(selected,message,'bridge');lidar.offer(message,lidar.generation)
            else:sensors.offer(selected,message,'bridge')
        except Exception as exc:sensors.errors[selected]='센서 값 해석 오류: '+str(exc)[:160]

    bridge=SensorBridge(bridge_wanted,bridge_message)
    inspect_sensors();bridge.start()

    # Creating mutation clients and a publisher is deferred until explicit
    # --allow-control startup. Registration is deferred again until operator arm.
    if scopes['presets']:
        from aimdk_msgs.srv import ExecuteActionResource
        for name,typ in [('SetMcPresetMotion',SetMcPresetMotion),('ExecuteActionResource',ExecuteActionResource)]:
            clients[name]=node.create_client(typ,'/aimdk_5Fmsgs/srv/'+name)
    if scopes['seat_hold'] or scopes['mode_switch']:
        from aimdk_msgs.srv import SetMcAction
        clients['SetMcAction']=node.create_client(SetMcAction,'/aimdk_5Fmsgs/srv/SetMcAction')
    if scopes['movement']:
        from aimdk_msgs.srv import SetMcInputSource
        from aimdk_msgs.msg import McLocomotionVelocity
        for name,typ in [('SetMcInputSource',SetMcInputSource)]:
            clients[name]=node.create_client(typ,'/aimdk_5Fmsgs/srv/'+name)
        publisher=node.create_publisher(McLocomotionVelocity,'/aima/mc/locomotion/velocity',qos_profile_sensor_data)
    def publish_velocity(vector):
        if not scopes['movement'] or not registered or publisher is None:return
        msg=McLocomotionVelocity();msg.header.stamp=node.get_clock().now().to_msg();msg.source=source
        msg.forward_velocity,msg.lateral_velocity,msg.angular_velocity=vector
        publisher.publish(msg);state['velocity_publications']+=1
    def release(disarm=False):
        nonlocal desired,must_release
        was_moving=any(desired) or state['moving']
        desired=[0.,0.,0.];state['moving']=False;must_release=False;state['must_release']=False
        if was_moving:publish_velocity(desired)
        if disarm:state['armed']=False
        event('disarmed' if disarm else 'stop_ack',publication='ZERO_VELOCITY' if was_moving else 'NO_MOTION_SENT',native_preset_may_continue=bool(state['gesture']))
    def continuing_walk():
        now=time.monotonic()
        return active_locomotion_allowed(state['fsm'],state.get('fsm_status'),now-mode_at,
            state['armed'],any(desired),now-hold_at,now-hold_start)
    def require_ready(continuation=False):
        if not enabled:raise ValueError('읽기 전용: 실행 허용으로 시작하지 않았습니다.')
        if time.monotonic()-mode_at>2:raise ValueError('최신 모드 응답이 없습니다.')
        stable=state['fsm'] in ('STAND_DEFAULT','LOCOMOTION_DEFAULT') and state.get('fsm_status')==100
        if not stable and not (continuation and continuing_walk()):raise ValueError('현재 '+str(state['fsm'])+' · 안정 서기와 모드 실행 상태를 확인하세요.')
        if state['gesture'] or command_busy or state['posture_pending'] or state['seat_hold_pending']:raise ValueError('이전 요청의 SDK 응답 또는 자세 전환을 기다리세요.')
    def mutate(name,request,callback,context=None):
        nonlocal command_busy
        if not enabled:raise ValueError('읽기 전용입니다.')
        if not clients[name].service_is_ready():raise ValueError(name+' 서비스가 준비되지 않았습니다.')
        timestamp(request);command_busy=True;state['control_requests_sent']+=1
        future=clients[name].call_async(request)
        event('sdk_request_sent',service=name,request_sequence=state['control_requests_sent'],
              request_id=(context or {}).get('request_id'),name=(context or {}).get('name'),sdk_request=asdict(request))
        def done(f):
            nonlocal command_busy
            command_busy=False
            try:callback(f.result())
            except Exception as e:
                state['error']=str(e);state['armed']=False;state['arm_pending']=False
                if name=='SetMcAction':state['posture_pending']=None;state['seat_hold_pending']=False
                event('sdk_response_error',service=name,error=str(e))
        future.add_done_callback(done)
    def arm_response(response):
        nonlocal registered
        if response.response.header.code!=0:raise ValueError('입력 소스 등록 실패')
        registered=True;state['armed']=True;state['error']='';event('armed')
    def native_response(response,context):
        finish_native_request(state,context,response.response.header.code,response.response.state.value,
                              'SetMcPresetMotion',event)
    def handle(msg):
        nonlocal desired,hold_at,hold_start,must_release,mode_target,posture_deadline,hold_limit
        if not isinstance(msg,dict):raise ValueError('요청은 JSON 객체여야 합니다.')
        ident=msg.get('request_id')
        if ident and ident in seen_ids:return
        if ident:
            if len(seen_ids)>2000:seen_ids.clear()
            seen_ids.add(ident)
        action=msg.get('action')
        if not command_allowed(action,scopes,msg.get('mode')):raise ValueError('대시보드 실행 권한 잠금: '+str(action))
        if action=='lidar_frame_request':lidar.request(ident);return
        if action=='camera_select':
            try:select_camera(msg.get('topic'),ident)
            except Exception as exc:event('camera_select_error',request_id=ident,error=str(exc))
            return
        if action=='lidar_topic':
            try:select_lidar(msg.get('topic'),ident);inspect_lidar()
            except Exception as exc:event('lidar_subscription_error',request_id=ident,error=str(exc))
            return
        if action=='configure':state['profile']=validate_profile(msg.get('profile'));return
        if action in ('stop','release','disarm'):
            release(action!='release');return
        if action=='gesture_release':
            event('native_motion_status',note='프리셋은 자동 취소되지 않습니다. 즉시 멈추려면 리모컨 정지를 사용하세요.');return
        if not enabled:raise ValueError('읽기 전용: 로봇 제어 요청을 전송하지 않았습니다.')
        if action=='posture':
            now=time.monotonic();name=msg.get('name')
            if command_busy or any(state.get(k) for k in ('moving','gesture','arm_pending','seat_hold_pending','posture_pending')):
                raise ValueError('다른 동작 또는 모드 전환이 진행 중입니다.')
            outcome=validate_posture_request(name,state['fsm'],state.get('fsm_status'),now-mode_at,
                now-leg_at if leg_at else None,state['joint_values'],msg.get('confirmed') is True)
            if outcome=='ALREADY_ACTIVE':event('posture_already_active',name=name,control_request_sent=False);return
            spec=POSTURES[name]
            req=prepare_posture_request(SetMcAction.Request(),name,source)
            def posture_response(response):
                code=response.response.header.code;status=response.response.status.value
                event('mode_ack',name=name,target_fsm=spec['action_desc'],completion_mode=spec['completion_mode'],code=code,status=status,
                    message=response.response.message,service='SetMcAction',request_id=msg.get('request_id'),physical_outcome='NOT_VERIFIED')
                if code!=0 or status!=1:
                    state['posture_pending']=None
                    raise ValueError(spec['label']+' 요청 거부 · code '+str(code)+' · '+(response.response.message or MC_REJECTIONS.get(code,'성공 응답 없음')))
                if state['posture_pending']:state['posture_pending']['phase']='ACCEPTED'
            mutate('SetMcAction',req,posture_response,msg)
            state['mode_changes_sent']+=1;state['armed']=False;state['error']=''
            state['posture_pending']=dict(name=name,action_desc=spec['action_desc'],completion_mode=spec['completion_mode'],phase='SENT',request_id=msg.get('request_id'))
            posture_deadline=now+30
            return
        if action=='seat_hold':
            now=time.monotonic()
            if state['gesture'] or state['arm_pending'] or state['moving'] or command_busy or state['seat_hold_pending'] or state['posture_pending']:
                raise ValueError('다른 동작 또는 모드 전환이 진행 중입니다.')
            outcome=seat_hold_check(state['fsm'],now-mode_at,msg.get('confirmed') is True,
                now-leg_at if leg_at else None,state['joint_values'])
            if outcome=='ALREADY_ACTIVE':event('seat_hold_already_active',control_request_sent=False);return
            req=SetMcAction.Request();req.source=source;req.command.action_desc=SEAT_MODE
            def seat_response(response):
                nonlocal mode_target
                code=response.response.header.code;status=response.response.status.value
                event('mode_ack',target_fsm=SEAT_MODE,code=code,status=status,message=response.response.message,
                      service='SetMcAction',physical_outcome='NOT_VERIFIED')
                if code!=0 or status!=1:
                    state['seat_hold_pending']=False
                    raise ValueError('착석 고정 요청 거부 · code '+str(code)+' · '+(response.response.message or MC_REJECTIONS.get(code,'성공 응답 없음')))
                mode_target=SEAT_MODE;state['error']=''
            mutate('SetMcAction',req,seat_response,msg)
            state['mode_changes_sent']+=1;state['seat_hold_pending']=True
            return
        if action=='set_mode':
            spec=MODES.get(msg.get('mode'))
            if not spec or msg.get('confirmed') is not True or msg.get('condition_confirmed') is not True:raise ValueError('모드와 지지 조건 확인이 필요합니다.')
            if time.monotonic()-mode_at>2 or state['gesture'] or command_busy or state['posture_pending']:raise ValueError('모드 전환 전 최신 상태와 이전 동작 종료를 확인하세요.')
            if spec.get('from') and state['fsm'] not in spec['from']:raise ValueError('현재 자세에서 이 모드 전환은 제공하지 않습니다. 리모컨을 사용하세요.')
            release(True);req=SetMcAction.Request();req.source=source;req.command.action_desc=spec['id']
            def mode_response(response):
                nonlocal mode_target
                code=response.response.header.code;status=response.response.status.value
                event('mode_ack',target_fsm=spec['id'],code=code,status=status,message=response.response.message,service='SetMcAction',physical_outcome='NOT_VERIFIED')
                if code!=0 or status!=1:raise ValueError('제조사 모드 전환 거부 · code '+str(code)+' · '+MC_REJECTIONS.get(code,response.response.message or '성공 상태 응답 없음'))
                mode_target=spec['id']
            state['mode_changes_sent']+=1
            mutate('SetMcAction',req,mode_response);return
        if action=='hold' and must_release:return
        require_ready(continuation=action=='hold')
        if action=='arm':
            if msg.get('confirmed') is not True or msg.get('expected_fsm')!=state['fsm']:raise ValueError('현재 자세와 현장 확인을 다시 확인하세요.')
            if registered or not scopes['movement']:state['armed']=True;state['error']='';event('armed',scope='presets' if not scopes['movement'] else 'full');return
            req=SetMcInputSource.Request();req.action.value=1001;req.input_source.name=source;req.input_source.priority=30;req.input_source.timeout=300
            mutate('SetMcInputSource',req,arm_response);return
        if not state['armed']:raise ValueError('제어를 먼저 활성화하세요.')
        if action=='hold':
            vector=validate_velocity(msg['velocity']) if msg.get('velocity') is not None else velocity(msg['direction'],state['profile'])
            if not any(desired):
                hold_limit=msg.get('burst_seconds',state['profile']['burst_seconds'])
                if type(hold_limit) not in (int,float) or not math.isfinite(hold_limit) or not .1<=hold_limit<=5:raise ValueError('이동 시간은 0.1~5초 범위여야 합니다.')
                hold_start=time.monotonic()
            desired=list(vector);hold_at=time.monotonic();state['moving']=any(vector);state['requested_velocity']=list(vector);return
        if action=='gesture':
            spec=available_presets.get(msg.get('name'))
            if not spec:raise ValueError('설치 SDK에서 확인되지 않은 프리셋입니다. 버전 호환을 먼저 확인하세요.')
            release(False);req=prepare_preset_request(SetMcPresetMotion.Request(),spec['name'],state['arm_actions'])
            mutate('SetMcPresetMotion',req,lambda response:native_response(response,msg),msg)
            state['gesture']=spec['name'];state['arm_pending']=True;state['native_result']=None;return
        if action=='custom_motion':
            spec=state['custom_actions'].get(msg.get('name'))
            if not spec or msg.get('confirmed') is not True:raise ValueError('기기에서 조회한 저장 동작만 실행할 수 있습니다.')
            req=ExecuteActionResource.Request();req.resource_key=spec['resource_key'];req.resource_version=spec['version']
            req.meta=json.dumps({'resource_type':'BODY_MONTION' if 'onnx' in spec['resource_key'] else 'ARM_MONTION'})
            def resource_response(response):
                finish_native_request(state,msg,response.header.header.code,response.header.status.value,
                                      'ExecuteActionResource',event)
            mutate('ExecuteActionResource',req,resource_response,msg)
            state['gesture']=spec['name'];state['arm_pending']=True;state['native_result']=None;return
        raise ValueError('직접 관절 실행은 제공하지 않습니다.' if action=='arm_joint_pose' else '알 수 없는 요청입니다.')
    next_mode=next_state=next_joints=next_resources=next_velocity=next_diagnostics=0.
    try:
        while not stop.is_set() and rclpy.ok():
            rclpy.spin_once(node,timeout_sec=.005);now=time.monotonic()
            for name,(future,began) in list(outstanding.items()):
                if future.done():
                    try:read_response(name,future.result())
                    except Exception as e:event('query_error',service=name,error=str(e))
                    del outstanding[name]
                elif now-began>2:
                    clients[name].remove_pending_request(future);del outstanding[name]
                    event('query_timeout',service=name)
            if now>=next_mode:query('GetMcAction');next_mode=now+1
            if now>=next_joints:query('GetAllJointState');next_joints=now+5
            if now>=next_resources:query('GetRobotResources');next_resources=now+30
            if now>=next_diagnostics:
                for name in READ_QUERIES:
                    if name in clients:query(name)
                state['sdk_services']={name:client.service_is_ready() for name,client in clients.items()}
                inspect_lidar()
                inspect_sensors()
                next_diagnostics=now+5
            while not incoming.empty():
                try:handle(incoming.get_nowait())
                except Exception as e:event('command_rejected',error=str(e));state['error']=str(e)
            if state['posture_pending'] and now>posture_deadline:
                pending=state['posture_pending'];state['posture_pending']=None
                state['posture_result']=dict(pending,status='OUTCOME_UNKNOWN')
                state['error']='자세 전환 완료를 30초 안에 확인하지 못했습니다. 실제 로봇 자세를 확인하세요. 자동 재전송하지 않습니다.'
                event('posture_timeout',name=pending['name'],error=state['error'])
            state['ready']=enabled and now-mode_at<2 and state['fsm'] in ('STAND_DEFAULT','LOCOMOTION_DEFAULT') and state.get('fsm_status')==100
            if any(desired) and not continuing_walk():release(True)
            if any(desired) and now-hold_start>=hold_limit:
                release(False);must_release=True;state['must_release']=True
            if any(desired) and now>=next_velocity:publish_velocity(desired);next_velocity=now+.02
            if now>=next_state:
                state['lidar']=dict(lidar.status(),**lidar_graph)
                state['sensors']=sensors.snapshot()
                state['sensor_bridge']=dict(connected=bridge.connected,error=bridge.error)
                state['camera_selected']=camera['topic'];state['camera_error']=camera['error']
                state['camera_age_ms']=int((now-camera['at'])*1000) if camera['at'] else None
                state['mode_age_ms']=int((now-mode_at)*1000) if mode_at else None
                state['leg_age_ms']=int((now-leg_at)*1000) if leg_at else None
                state['camera_source_hz']=camera['source_hz'];state['camera_preview_fps']=camera['fps']
                emit(state);next_state=now+.25
    finally:
        stop.set();bridge.close();lidar_thread.join(timeout=1)
        if any(desired):publish_velocity([0.,0.,0.])
        event('worker_exit',control_requests_sent=state['control_requests_sent'],velocity_publications=state['velocity_publications'])
        node.destroy_node();rclpy.shutdown()

if __name__=='__main__':
    main()
