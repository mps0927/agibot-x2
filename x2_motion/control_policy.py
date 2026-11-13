"""Application permissions and posture checks; never bypasses MC rejection."""
import math
SEAT_MODE = 'SIT_JOINT_DEFAULT'
STABLE_MODES = ('STAND_DEFAULT', 'LOCOMOTION_DEFAULT')

def active_locomotion_allowed(mode,status,mode_age,armed,has_velocity,hold_age,elapsed):
    """Continue an existing velocity stream across the normal STAND -> WALK transition."""
    if not armed or not has_velocity or mode_age is None or mode_age>2 or hold_age>.30:
        return False
    if mode in STABLE_MODES and status==100:
        return True
    return mode=='LOCOMOTION_DEFAULT' and status==200 and 0<=elapsed<2.0

MC_REJECTIONS = {
    2:'요청 형식 또는 입력 소스가 올바르지 않음', 3:'기기 설정에 등록되지 않은 동작',
    4:'현재 자세에서 허용되지 않는 동작', 5:'복구 동작 진행 중', 6:'제조사 안전 보호가 전환을 거부함',
    7:'부팅·초기화 진행 중', 8:'이동 중이라 전환 불가', 9:'다른 동작 재생 중',
    10:'현재 모드에서 해당 모드로 전환 경로가 없음',
}

def permissions(full=False, presets=False,seat=False,postures=False):
    return dict(movement=bool(full), presets=bool(full or presets),
                mode_switch=bool(full or postures),seat_hold=bool(seat or postures),posture_actions=bool(postures))

def command_allowed(action, scopes, mode=None):
    if action in ('stop','release','disarm','gesture_release','configure','lidar_topic','lidar_frame_request','camera_select'):
        return True
    if action=='arm':return scopes['movement'] or scopes['presets']
    if action=='hold':return scopes['movement']
    if action in ('gesture','custom_motion'):return scopes['presets']
    if action=='seat_hold':return scopes['seat_hold']
    if action=='posture':return scopes.get('posture_actions',False)
    if action=='set_mode':return scopes['seat_hold'] if mode=='seat_hold' else scopes['mode_switch']
    return False

def seat_hold_check(mode, mode_age,confirmed=False,leg_age=None,joints=None):
    if mode==SEAT_MODE:
        if mode_age is None or mode_age>2:raise ValueError('최신 착석 모드 응답을 기다리세요.')
        return 'ALREADY_ACTIVE'
    if mode not in ('PASSIVE_DEFAULT','DAMPING_DEFAULT'):raise ValueError('이미 의자에 앉은 영토크·댐핑 상태에서만 착석 고정을 요청하세요. 일어서기·앉기 동작은 실행하지 않습니다.')
    if confirmed is not True:raise ValueError('의자에 앉아 있고 등받이와 보조자가 지지하는지 확인하세요.')
    if mode_age is None or mode_age>2 or leg_age is None or leg_age>1.5:raise ValueError('최신 모드와 다리 관절 상태를 기다리세요.')
    for side in ('left','right'):
        hip=(joints or {}).get(side+'_hip_pitch_joint',{});knee=(joints or {}).get(side+'_knee_joint',{})
        values=[hip.get('position'),knee.get('position'),hip.get('velocity'),knee.get('velocity')]
        if any(type(x) not in (int,float) or not math.isfinite(x) for x in values):raise ValueError('착석을 확인할 다리 관절값이 없습니다.')
        if hip.get('error_code')!=0 or knee.get('error_code')!=0:raise ValueError('다리 관절 오류를 확인하세요.')
        if hip['position']>=-.4 or knee['position']<=.7:raise ValueError('다리 관절값이 착석 준비 범위가 아닙니다.')
        if max(abs(hip['velocity']),abs(knee['velocity']))>.2:raise ValueError('다리가 움직이고 있습니다. 안정된 후 다시 요청하세요.')
    return 'REQUEST_ALLOWED'

def preset_block_reason(mode, scopes, connected=True, busy=False):
    if not connected:return '로봇 연결과 최신 상태를 기다리는 중입니다.'
    if not scopes['presets']:return '대시보드 설정에서 프리셋 실행이 잠겨 있습니다.'
    if busy:return '이전 모션 요청의 SDK 응답을 기다리는 중입니다.'
    if mode not in STABLE_MODES:return '현재 '+str(mode)+' · 내장 프리셋은 운영자가 안정 서기를 준비한 뒤 요청할 수 있습니다. VLM은 기립·모드 전환을 수행하지 않습니다.'
    return ''

PLAN_TTL_SECONDS=30

def validate_plan_execution(plan,actions,state,state_age,scopes,now):
    from capabilities import preset_mapping
    if now-plan['created']>PLAN_TTL_SECONDS:raise ValueError('계획 생성 후 30초가 지났습니다. 최신 장면으로 다시 생성하세요.')
    if not state.get('connected') or state_age>1:raise ValueError('최신 로봇 상태를 기다리세요.')
    if state.get('fsm') not in STABLE_MODES or state.get('fsm_status')!=100:
        raise ValueError('운영자가 안정 서기를 준비하고 모드 실행 상태를 확인하세요.')
    if state.get('gesture') or state.get('arm_pending'):raise ValueError('이전 모션 요청의 SDK 응답을 기다리고 있습니다.')
    if state.get('fsm')!=plan.get('fsm'):raise ValueError('계획 생성 후 모드가 바뀌었습니다. 다시 생성하세요.')
    if plan.get('sdk_version')!=state.get('sdk_version'):raise ValueError('SDK 버전이 바뀌었습니다. 다시 생성하세요.')
    mapped=preset_mapping(state.get('arm_actions',{}))
    for action in actions:
        kind=action.get('type')
        command={'gesture':'gesture','custom_motion':'custom_motion','move':'hold','stop':'stop'}.get(kind)
        if not command or not command_allowed(command,scopes):raise ValueError('이 계획에 실행 권한이 없는 동작이 있습니다.')
        if kind=='gesture':
            spec=mapped.get(action.get('name'))
            if not spec or action.get('action_id')!=spec['motion']:raise ValueError('프리셋 매핑이 바뀌었습니다. 다시 생성하세요.')
        if kind=='custom_motion' and action.get('name') not in state.get('custom_actions',{}):raise ValueError('저장 모션 목록이 바뀌었습니다.')
