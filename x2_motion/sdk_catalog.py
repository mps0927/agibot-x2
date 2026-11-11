"""Versioned SDK coverage; a declared interface is not an executable capability."""
import json
from pathlib import Path
from functools import lru_cache
from capabilities import preset_mapping, MODES
from posture_actions import POSTURES

READ_QUERIES=('GetCurrentInputSource','GetHandType','GetSystemState','GetVolume','GetMute')
HANDLERS={
    'GetMcAction':('read','현재 운용 모드','x2_worker.read_response'),
    'GetAllJointState':('read','관절 상태','x2_worker.read_response'),
    'GetRobotResources':('read','사용자 모션 목록','x2_worker.read_response'),
    **{name:('read',label,'x2_worker.read_response') for name,label in zip(READ_QUERIES,('현재 제어 소스','손 장착 종류','시스템 상태','스피커 음량','음소거 상태'))},
    'SetMcInputSource':('control','제어 활성화','x2_worker.handle:arm'),
    'SetMcAction':('control','서기·앉기·착석 고정·운용 모드','x2_worker.handle:posture/seat_hold/set_mode'),
    'SetMcPresetMotion':('control','설치 SDK 프리셋','x2_worker.handle:gesture'),
    'ExecuteActionResource':('control','기기에 등록된 사용자 모션','x2_worker.handle:custom_motion'),
}
REFERENCE_REASONS={
    'MigrateSystemState':'시스템 서비스 전환은 MC 중지 등 운용 환경에 영향을 줍니다. 별도 시스템 관리 절차가 필요합니다.',
    'GetStoredMapByName':'지도 이름과 맵 서비스 연결이 필요합니다. 저장 지도는 아직 조회하지 않았습니다.',
    'SetAgentPropertiesRequest':'기기 에이전트 구성 API이며 대시보드 운동제어 경로에 연결하지 않았습니다.',
}

@lru_cache(maxsize=1)
def definition():
    return json.loads((Path(__file__).parent/'sdk_interfaces.json').read_text(encoding='utf-8'))

def sdk_inventory(state):
    source=definition();connected=bool(state.get('connected'))
    services=[]
    for item in source['services']:
        handler=HANDLERS.get(item['name']);runtime=state.get('sdk_services',{}).get(item['name'])
        services.append(dict(item,coverage='mapped' if handler else 'reference',
            operation=handler[0] if handler else 'reference',label=handler[1] if handler else item['name'],
            handler=handler[2] if handler else None,
            service_ready=runtime if connected else None,
            reason='' if handler else REFERENCE_REASONS.get(item['name'],'음성·표정·미디어 인터페이스입니다. 요청 스키마는 보관했으며 실행기는 연결하지 않았습니다.')))
    return dict(schema='x2.sdk-map.v1',sdk_version=source['sdk_version'],connected=connected,
        services=services,topics=source['topics'],
        summary=dict(service_total=len(services),service_mapped=sum(x['coverage']=='mapped' for x in services),
            preset_mapped=len(preset_mapping(state.get('arm_actions',{})))),
        presets=preset_mapping(state.get('arm_actions',{})),manual_modes=MODES,postures=POSTURES,
        queries=state.get('sdk_queries',{}),physical_execution_verified=False,
        joint_control=dict(coverage='preview',reason='HAL 관절 명령은 MC 제어와 다른 운용 경로입니다. 직접 실행은 연결하지 않았습니다.'),
        lidar=dict(coverage='reference',reason='센서 네트워크는 확인했으나 PointCloud2 수신은 미확인입니다.'))
