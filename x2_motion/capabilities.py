"""X2 catalog: documented presets and live LinkCraft resources are distinct."""
import math
from joint_contract import catalog as joint_catalog
from posture_actions import POSTURES
from punch import NAME as PUNCH_NAME, local_catalog

# The robot's RC log recorded pure yaw at 0.9756205446533405 rad/s.
# Match the observed controller rate approximately, including VLM commands.
# MC LOW allows +/-1; this application caps yaw at +/-0.97 rad/s.
DEFAULT_PROFILE = dict(forward_mps=.20, lateral_mps=.10, yaw_rps=.97, burst_seconds=1.0)
PROFILE_LIMITS = dict(forward_mps=(0,.30), lateral_mps=(0,.30), yaw_rps=(0,.97), burst_seconds=(.1,5.0))
VELOCITY_LIMITS=(.30,.30,.97)
DIRECTIONS = dict(forward=(1,0,0), backward=(-1,0,0), left=(0,1,0), right=(0,-1,0), turn_left=(0,0,1), turn_right=(0,0,-1))
PRESETS = {}
def _preset(key, label, motion, areas):
    for area, suffix in areas:
        name = key + ('_'+suffix if suffix else '')
        PRESETS[name] = dict(name=name, label=label + ({1:' · 왼손',2:' · 오른손',3:' · 양손'}.get(area,'')),
                             id=motion, motion=motion, area=area, time=None,
                             support_status='문서 정의 · 실물 실행 미검증', required_mode='STAND_DEFAULT')
_sides=[(1,'left'),(2,'right')]
for key,label,ident in [('wave','손 흔들기',1002),('handshake','악수',1003),('raise','한쪽 팔 들기',1001),('air_kiss','손키스',1004),('salute','경례',1013),('high_five','하이파이브',1008),('chest_wave','가슴 높이 손 흔들기',1011)]:
    _preset(key,label,ident,_sides)
_preset('heart','하트',1007,_sides+[(3,'both')])
_preset('hands_up','팔 들기',1010,_sides+[(3,'both')])
for key,label,ident in [('clap','박수',3017),('hug','포옹',3008),('cheer','응원',3011),('goodbye','작별 인사',3031),('light_wave','Dynamic light wave',3007),('cross_arms','팔짱',3009),('bow','인사',3001),('scratch_head','머리 긁기',3024),('grab_hips','엉덩이 잡기',3025)]:
    _preset(key,label,ident,[(11,'')])
GESTURES={name:dict(id=p['id'],label=p['label']) for name,p in PRESETS.items()}
MODES={
 'stable_stand':dict(id='STAND_DEFAULT',label='안정 서기',condition='이미 서 있고 양발 접지·지지·모든 조종 입력 정지를 확인',from_=['JOINT_DEFAULT','LOCOMOTION_DEFAULT','STAND_DEFAULT']),
 'position_stand':dict(id='JOINT_DEFAULT',label='서기 준비 · 위치제어',condition='서 있는 로봇의 하중을 지지하고 관절 주변 공간 확보',from_=['STAND_DEFAULT','LOCOMOTION_DEFAULT','JOINT_DEFAULT']),
 'damping':dict(id='DAMPING_DEFAULT',label='댐핑',condition='의자 또는 크레인이 로봇 하중을 지지함'),
 'zero_torque':dict(id='PASSIVE_DEFAULT',label='영토크 · 힘 해제',condition='힘이 풀려도 쓰러지지 않도록 로봇 하중 지지'),
}
for spec in MODES.values():
    if 'from_' in spec:spec['from']=spec.pop('from_')

def validate_profile(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULT_PROFILE):raise ValueError('이동 설정 네 값을 모두 입력하세요.')
    for name,(lo,hi) in PROFILE_LIMITS.items():
        x=value[name]
        if type(x) not in (int,float) or not math.isfinite(x) or not lo<=x<=hi:raise ValueError(f'{name}: {lo}~{hi} 범위를 사용하세요.')
    return {k:float(v) for k,v in value.items()}

def velocity(direction,profile):
    x,y,yaw=DIRECTIONS[direction]
    return x*profile['forward_mps'],y*profile['lateral_mps'],yaw*profile['yaw_rps']

def validate_velocity(value):
    if not isinstance(value,(list,tuple)) or len(value)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>limit for x,limit in zip(value,VELOCITY_LIMITS)):
        raise ValueError('전후·좌우 속도는 절댓값 0.30 m/s, 회전은 절댓값 0.97 rad/s 이하의 유한 수여야 합니다.')
    return tuple(float(x) for x in value)

def resolve_move(action,profile):
    vector=validate_velocity(action.get('velocity'));seconds=action.get('seconds')
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not .1<=seconds<=5:
        raise ValueError('X2 이동 계획에는 0.1~5초의 명시적 시간이 필요합니다.')
    return dict(type='move',direction='vector',velocity=list(vector),seconds=float(seconds),reason=str(action.get('reason',''))[:300])

def sdk_requests(actions):
    out=[]
    for action in actions:
        kind=action['type']
        if kind=='gesture':
            p=PRESETS[action['name']];out.append(dict(service='/aimdk_5Fmsgs/srv/SetMcPresetMotion',motion=p['motion'],area=p['area'],interrupt=False,status='PROPOSAL'))
        elif kind in ('move','stop'):out.append(dict(topic='/aima/mc/locomotion/velocity',source='sdk_x2_dashboard',velocity=action.get('velocity',[0,0,0]),seconds=action.get('seconds'),status='PROPOSAL'))
        elif kind=='mode':out.append(dict(service='/aimdk_5Fmsgs/srv/SetMcAction',action_desc=MODES[action['name']]['id'],status='MANUAL_ONLY'))
        elif kind=='arm_joint_pose':out.append(dict(kind='joint_preview',executable=False,target_sha256=action.get('target_sha256')))
        elif kind=='custom_motion':out.append(dict(service='/aimdk_5Fmsgs/srv/ExecuteActionResource',name=action['name'],status='PROPOSAL'))
    return out

def preset_mapping(arm_actions):
    """Only bind exact names/IDs observed in the installed SDK."""
    return {name:dict(spec,service='/aimdk_5Fmsgs/srv/SetMcPresetMotion',interrupt=False,
                      binding_verified=True,physical_execution_verified=False)
            for name,spec in PRESETS.items()
            if type((arm_actions or {}).get(name)) is int and arm_actions[name]==spec['motion']}

def prepare_preset_request(request,name,arm_actions):
    spec=preset_mapping(arm_actions).get(name)
    if not spec:raise ValueError('설치 SDK의 정확한 프리셋 매핑이 없습니다.')
    request.motion.value=spec['motion'];request.area.value=spec['area'];request.interrupt=False
    return request

def catalog(arm_actions=None,profile=None,custom_actions=None):
    profile=profile or DEFAULT_PROFILE
    mapped=preset_mapping(arm_actions)
    custom_actions={k:v for k,v in (custom_actions or {}).items() if k!=PUNCH_NAME}
    return dict(schema='x2.commands.v1',robot='AGIBOT X2 Ultra',profile=profile,profile_limits=PROFILE_LIMITS,
                moves={n:velocity(n,profile) for n in DIRECTIONS},gestures={n:GESTURES[n] for n in mapped},
                manual_modes=MODES,custom_motions=custom_actions or {},joint_pose=joint_catalog(),local_joint_presets=local_catalog(),
                preset_provenance='Vendor documentation; execution not verified',stop=True,arbitrary_joint_control=False,
                preset_completion_tracking=False,preset_request_release='sdk_response',simultaneous_move_and_gesture=False)

def planner_catalog(arm_actions=None,profile=None,custom_actions=None,control_permissions=None):
    result=catalog(arm_actions,profile,custom_actions)
    result['local_joint_presets']={name:spec for name,spec in result['local_joint_presets'].items() if spec['executable']}
    mapped=preset_mapping(arm_actions)
    result.update(axes=dict(x='forward positive',y='left positive',yaw='counterclockwise positive'),
                  move_parameters=dict(velocity='[vx m/s, vy m/s, yaw rad/s], absolute bounds [0.30, 0.30, 0.97]',seconds='0.1 to 5 seconds, required'),
                  gestures={n:PRESETS[n]['label'] for n in mapped},
                  gesture_sdk_map={n:dict(service=p['service'],motion=p['motion'],area=p['area'],interrupt=False,
                      required_mode=p['required_mode'],binding_verified=True,physical_execution_verified=False) for n,p in mapped.items()},
                  execution_composition='Sequential. Native preset must be the only action until completion tracking is available.',
                  modes='Manual panel only; do not propose mode changes',joint_pose_execution='preview only')
    result['operator_only_postures']={name:dict(label=p['label'],controller=p['controller'],sdk_callable=True,
        action_desc=p['action_desc'],completion_mode=p['completion_mode'],manual_button_only=True) for name,p in POSTURES.items()}
    if control_permissions is not None:
        result['execution_permissions']=control_permissions
        if not control_permissions.get('movement'):
            result['moves']={};result['move_parameters']={'enabled':False}
        if not control_permissions.get('presets'):result['preset_execution_enabled']=False
    return result
