"""Chair motion mappings confirmed in this robot's MC/RC logs."""
POSTURES={
    'sit_down':dict(label='의자에 앉기',controller='L2 + ←',sdk_callable=True,
        action_desc='SIT_DOWN_DEFAULT',completion_mode='SIT_JOINT_DEFAULT',
        required_mode='STAND_DEFAULT',
        steps=['높이 35–40cm의 등받이 의자를 준비하고 로봇이 앉을 위치에 맞춥니다.',
               '보조자가 뒤 손잡이를 잡고 지지하며 안정 서기 상태와 주변 공간을 확인합니다.',
               '컨트롤러 L2와 방향키 ←를 동시에 짧게 눌러 앉기를 실행합니다.',
               '몸통과 엉덩이가 의자에 안정적으로 지지됐는지 현장에서 확인합니다.'],
        reason='MC ActionRuler와 등록 로그에서 STAND_DEFAULT → SIT_DOWN_DEFAULT → SIT_JOINT_DEFAULT 경로 확인.'),
    'stand_up_from_seat':dict(label='의자에서 일어서기',controller='↑ + □',sdk_callable=True,
        action_desc='SIT_UP_DEFAULT',completion_mode='STAND_DEFAULT',
        required_mode='SIT_JOINT_DEFAULT',
        steps=['35–40cm 등받이 의자에서 착석 자세를 준비하고 양발 바닥이 지면에 닿는지 확인합니다.',
               '보조자가 뒤 손잡이로 지지하고 로봇 앞뒤 동작 공간을 확보합니다.',
               '앉은 자세 고정은 ↑ + ×입니다. 실제 일어서기는 ↑와 □를 동시에 짧게 누릅니다.',
               '실제 기립과 안정 서기 진입을 확인합니다. OmniHand 장착 기기는 누운 자세에서 기립시키지 않습니다.'],
        reason='실제 RC/MC 로그에서 SIT_JOINT_DEFAULT → SIT_UP_DEFAULT → STAND_DEFAULT 전환과 수락 응답 확인.'),
}

def posture_guide(name):
    if name not in POSTURES:raise ValueError('등록되지 않은 자세 동작입니다.')
    return dict(name=name,**POSTURES[name],control_request_sent=False,execution='SDK_MANUAL_BUTTON')

def prepare_posture_request(request,name,source):
    if name not in POSTURES:raise ValueError('등록되지 않은 자세 동작입니다.')
    request.source=source;request.command.action_desc=POSTURES[name]['action_desc']
    return request

def validate_posture_request(name,mode,mode_status,mode_age,leg_age,joints,confirmed):
    from control_policy import seat_hold_check
    if name not in POSTURES:raise ValueError('등록되지 않은 자세 동작입니다.')
    spec=POSTURES[name]
    if mode_age is None or mode_age>2 or mode_status!=100:raise ValueError('최신 모드의 실행 상태를 기다리세요.')
    if mode==spec['completion_mode']:return 'ALREADY_ACTIVE'
    if mode!=spec['required_mode']:raise ValueError('현재 '+str(mode)+' · 먼저 '+spec['required_mode']+' 모드를 준비하세요.')
    if confirmed is not True:raise ValueError('의자 위치·양발 접지·보조자 지지·주변 공간을 확인하세요.')
    if name=='stand_up_from_seat':
        # Reuse the seated-leg checks without the already-active shortcut.
        seat_hold_check('PASSIVE_DEFAULT',mode_age,True,leg_age,joints)
    else:
        import math
        if leg_age is None or leg_age>1.5:raise ValueError('최신 다리 관절 상태를 기다리세요.')
        for joint in (joints or {}).values():
            speed=joint.get('velocity')
            if type(speed) not in (int,float) or not math.isfinite(speed) or abs(speed)>.2:raise ValueError('로봇이 움직이고 있습니다. 정지 후 요청하세요.')
            if joint.get('error_code')!=0:raise ValueError('관절 오류를 확인하세요.')
        if not joints:raise ValueError('관절 상태를 기다리세요.')
    return 'REQUEST_ALLOWED'
