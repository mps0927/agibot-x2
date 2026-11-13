"""Local named joint preset, independent of vendor resource registration.

Trajectory generation sends no commands. Physical execution needs an adapter
which preserves native MC; a vendor resource with the same name is unrelated.
"""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from joint_contract import JOINTS, PROFILE

NAME = 'punch_right'
LABEL = '펀치 · 오른팔'
RIGHT = tuple('right_' + n + '_joint' for n in (
    'shoulder_pitch', 'shoulder_roll', 'shoulder_yaw', 'elbow',
    'wrist_yaw', 'wrist_pitch', 'wrist_roll'))
PRESET_PATH = Path(__file__).with_name('punch_right.json')
# Vendor X2_URDF-v1.3.0, torso -> right wrist; xyz metres, rpy radians.
CHAIN = (
    ((.00330093831251838, -.143030971450747, .241648201390685), (-.209442812383636, 0., 0.), (0, 1, 0)),
    ((-.000499999994070091, -.0495000000000002, 0.), (0., .000154003092926045, 0.), (1, 0, 0)),
    ((.000499999999999765, 0., -.121199999999934), (0., 0., 0.), (0, 0, 1)),
    ((.0139999999999662, -.0002000000000143, -.0829500000000745), (0., 0., 0.), (0, 1, 0)),
    ((-.0140000017961392, .000097526096753231, -.120694276209686), (0., 0., .0000327341906322599), (0, 0, 1)),
    ((0., 0., -.081799999999999), (0., 0., -.0000327341932546355), (0, 1, 0)),
    ((0., 0., 0.), (0., 0., 0.), (1, 0, 0)),
)


def _rotation(axis, angle):
    x, y, z = axis
    c, s, t = math.cos(angle), math.sin(angle), 1. - math.cos(angle)
    return ((t*x*x+c, t*x*y-s*z, t*x*z+s*y),
            (t*x*y+s*z, t*y*y+c, t*y*z-s*x),
            (t*x*z-s*y, t*y*z+s*x, t*z*z+c))


def _mul(a, b):
    return tuple(tuple(sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def _apply(a, v):
    return tuple(sum(a[i][k]*v[k] for k in range(3)) for i in range(3))


def arm_points(pose):
    rotation = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))
    position = (0., 0., 0.)
    points = []
    for name, (xyz, rpy, axis) in zip(RIGHT, CHAIN):
        delta = _apply(rotation, xyz)
        position = tuple(a+b for a, b in zip(position, delta))
        points.append(list(position))
        for direction, angle in zip(((0,0,1),(0,1,0),(1,0,0)), reversed(rpy)):
            rotation = _mul(rotation, _rotation(direction, angle))
        rotation = _mul(rotation, _rotation(axis, pose[name]))
    return points


def _pose(value):
    if not isinstance(value, dict) or set(value) != set(RIGHT):
        raise ValueError('오른팔 7관절의 시작 각도가 모두 필요합니다.')
    result = {}
    for name in RIGHT:
        q = value[name]
        if type(q) not in (int, float) or not math.isfinite(q) or not JOINTS[name]['lower'] <= q <= JOINTS[name]['upper']:
            raise ValueError(name + ': X2 관절 범위를 벗어났습니다.')
        result[name] = float(q)
    return result


def load_definition(path=PRESET_PATH):
    value=json.loads(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(value,dict) or value.get('schema')!='x2.local-joint-preset.v1' or value.get('name')!=NAME
            or value.get('robot_id')!=PROFILE['robot_id'] or value.get('units')!='radian'
            or value.get('interpolation')!='quintic' or value.get('required_controller')!='native_mc'
            or value.get('return_to_measured_start') is not True):
        raise ValueError('X2 로컬 펀치 프리셋 형식이 올바르지 않습니다.')
    rate=value.get('max_target_rate_rps')
    if type(rate) not in (int,float) or not math.isfinite(rate) or not 0<rate<=2:
        raise ValueError('펀치 설계 목표속도는 0 초과 2 rad/s 이하로 설정하세요.')
    poses=value.get('poses')
    if not isinstance(poses,dict) or set(poses)!={'guard','extend'}:
        raise ValueError('펀치 준비·뻗기 관절값이 필요합니다.')
    for target in poses.values():_pose(target)
    expected=[dict(phase=phase,target=target) for phase,target in
              [('guard','guard'),('extend','extend'),('recover','guard'),('return','measured_start')]]
    if value.get('steps')!=expected:raise ValueError('펀치는 준비·뻗기·회수·시작 자세 복귀 순서로 등록하세요.')
    return value


DEFINITION=load_definition()
RATE=DEFINITION['max_target_rate_rps']
GUARD=DEFINITION['poses']['guard']
EXTEND=DEFINITION['poses']['extend']


def local_catalog():
    return {NAME:dict(name=NAME,label=LABEL,source=PRESET_PATH.name,registered=True,
        joint_order=list(RIGHT),units='radian',max_target_rate_rps=RATE,
        executable=False,required_controller='native_mc',
        block_reason='기본 MC를 유지하는 관절 전송 어댑터가 아직 연결되지 않았습니다. 현재 확인한 SDK 1.0에는 상체 제어 API가 없습니다.')}


def build_profile(start):
    start = _pose(start)
    for pose in (GUARD, EXTEND): _pose(pose)
    frames = [dict(at=0., phase='start', joints=start)]
    for step in DEFINITION['steps']:
        phase=step['phase']
        target=start if step['target']=='measured_start' else DEFINITION['poses'][step['target']]
        previous = frames[-1]
        # Quintic interpolation peak rate = 1.875 * delta / duration.
        seconds = max(.35, 1.875*max(abs(target[n]-previous['joints'][n]) for n in RIGHT)/RATE)
        frames.append(dict(at=previous['at']+seconds, phase=phase, joints=dict(target)))
    identity = dict(schema='x2.local-joint-trajectory.v1', name=NAME, rate=RATE, keyframes=frames)
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',',':')).encode()).hexdigest()
    return dict(identity, label=LABEL, seconds=frames[-1]['at'], target_sha256=digest,
                joint_order=list(RIGHT), units='radian', active_group='right_arm',
                other_groups='retain current pose through native controller',
                interpolation='quintic', physical_execution_verified=False,
                preset_source=PRESET_PATH.name, export_format='LOCAL_JOINT_TRAJECTORY')


def sample(profile, at):
    if type(at) not in (int, float) or not math.isfinite(at) or not 0. <= at <= profile['seconds']:
        raise ValueError('궤적 시간 범위를 벗어났습니다.')
    frames = profile['keyframes']
    for a, b in zip(frames, frames[1:]):
        if at <= b['at']:
            u = (at-a['at'])/(b['at']-a['at'])
            weight = u*u*u*(10. + u*(-15. + 6.*u))
            return {n: a['joints'][n]+weight*(b['joints'][n]-a['joints'][n]) for n in RIGHT}
    return dict(frames[-1]['joints'])


def describe(state, fresh=False):
    measured = state.get('joint_values', {}) if fresh else {}
    values = {n: measured[n].get('position') for n in RIGHT if isinstance(measured.get(n), dict)}
    source = 'measured' if len(values) == len(RIGHT) else 'reference_zero'
    profile = build_profile(values if source == 'measured' else dict.fromkeys(RIGHT, 0.))
    registration=local_catalog()[NAME]
    return dict(profile=profile, start_source=source, registration=registration,
                replay_available=registration['executable'],
                control_request_sent=False,
                replay_note='오른팔 7관절 프리셋 로컬 등록 완료 · '+registration['block_reason'],
                preview=[dict(at=profile['seconds']*i/100, points=arm_points(sample(profile,profile['seconds']*i/100))) for i in range(101)])


def export_csv(profile):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['seconds', *RIGHT])
    count = math.ceil(profile['seconds']*50)
    for i in range(count+1):
        at = profile['seconds']*i/count
        pose = sample(profile, at)
        writer.writerow([round(at,6), *(round(pose[n],8) for n in RIGHT)])
    return output.getvalue()
