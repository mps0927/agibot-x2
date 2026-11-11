"""X2 Ultra t2d5 targets, derived from the vendor URDF; preview only."""
import hashlib
import json
import math
from pathlib import Path

PROFILE = json.loads((Path(__file__).parent / 'robot_profile.json').read_text(encoding='utf-8'))
JOINTS = PROFILE['joints']
Q_ORDER = list(JOINTS)


def validate_pose(value):
    if not isinstance(value, dict) or set(value) - {'joints', 'seconds'}:
        raise ValueError('관절 목표에는 joints와 seconds만 허용됩니다.')
    joints, seconds = value.get('joints'), value.get('seconds', 1.0)
    if not isinstance(joints, dict) or not joints or set(joints) - set(JOINTS):
        raise ValueError('현재 X2 프로필에 등록된 관절을 선택하세요.')
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not .1 <= seconds <= 5:
        raise ValueError('시간은 0.1~5초의 유한 수여야 합니다.')
    result = {}
    for name in Q_ORDER:
        if name not in joints:
            continue
        angle, spec = joints[name], JOINTS[name]
        if type(angle) not in (int, float) or not math.isfinite(angle) or not spec['lower'] <= angle <= spec['upper']:
            raise ValueError(f'{name}: URDF 허용 범위를 벗어난 목표입니다.')
        result[name] = float(angle)
    return dict(joints=result, seconds=float(seconds))


def canonical_action(value):
    if not isinstance(value, dict) or value.get('type') != 'arm_joint_pose' or value.get('object') != 'robot_joint' or value.get('destination') != 'none':
        raise ValueError('X2 typed joint target 형식이 올바르지 않습니다.')
    target = dict(type='arm_joint_pose', object='robot_joint', destination='none',
                  **validate_pose(dict(joints=value.get('joints'), seconds=value.get('seconds'))))
    identity = dict(robot_id=PROFILE['robot_id'], profile_version=PROFILE['profile_version'], target=target)
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return target, digest


def validate_physical_pose(value):
    canonical_action(value)
    raise ValueError('직접 관절 제어는 현재 SDK에서 실행을 잠갔습니다. 목표값 미리보기와 상태 조회를 사용하세요.')


def preview(value):
    action, digest = canonical_action(dict(type='arm_joint_pose', object='robot_joint', destination='none', **validate_pose(value)))
    return dict(action=action, target_sha256=digest, selected_joint_count=len(action['joints']),
                q_order=Q_ORDER, units='radian', robot_id=PROFILE['robot_id'],
                field_execution='PREVIEW_ONLY', executable=False)


def catalog():
    return dict(schema='x2.joint-pose.v1', robot_id=PROFILE['robot_id'], profile_version=1,
                units='radian', q_order=Q_ORDER, joints=JOINTS,
                groups={g:[n for n in Q_ORDER if JOINTS[n]['group'] == g] for g in ('leg','arm','waist','head')},
                physical_groups=[], physical_joint_count=0, field_execution='PREVIEW_ONLY',
                duration_seconds=dict(minimum=.1, maximum=5.0),
                note='t2d5 Ultra의 head_pitch는 인터페이스 예약 슬롯으로 프로필에서 제외했습니다.')
