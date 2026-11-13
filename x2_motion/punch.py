"""Named X2 right-arm punch authoring; no HAL publishers or MC mode changes.

Replay uses only a robot-listed arm resource named punch_right. The trajectory
export is an authoring reference, not an undocumented LinkCraft import format.
"""
import csv
import hashlib
import io
import json
import math
from joint_contract import JOINTS

NAME = 'punch_right'
LABEL = '펀치 · 오른팔'
RATE = 2.0  # G1 authoring reference; physical resource playback has its own timing.
RIGHT = tuple('right_' + n + '_joint' for n in (
    'shoulder_pitch', 'shoulder_roll', 'shoulder_yaw', 'elbow',
    'wrist_yaw', 'wrist_pitch', 'wrist_roll'))
# X2 elbow flexion is negative; near-zero is extension. These are X2 targets,
# not a sign-flipped copy of G1's endpoints.
GUARD = dict(zip(RIGHT, (-.35, -.25, 0., -1.65, 0., 0., 0.)))
EXTEND = dict(zip(RIGHT, (-1.20, -.25, 0., -.15, 0., 0., 0.)))
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


def build_profile(start):
    start = _pose(start)
    for pose in (GUARD, EXTEND): _pose(pose)
    frames = [dict(at=0., phase='start', joints=start)]
    for phase, target in [('guard', GUARD), ('extend', EXTEND), ('recover', GUARD), ('return', start)]:
        previous = frames[-1]
        # Quintic interpolation peak rate = 1.875 * delta / duration.
        seconds = max(.35, 1.875*max(abs(target[n]-previous['joints'][n]) for n in RIGHT)/RATE)
        frames.append(dict(at=previous['at']+seconds, phase=phase, joints=dict(target)))
    identity = dict(schema='x2.punch.authoring.v1', name=NAME, rate=RATE, keyframes=frames)
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',',':')).encode()).hexdigest()
    return dict(identity, label=LABEL, seconds=frames[-1]['at'], target_sha256=digest,
                joint_order=list(RIGHT), units='radian', active_group='right_arm',
                other_groups='retain current pose through native controller',
                interpolation='quintic', physical_execution_verified=False,
                export_format='PROJECT_AUTHORING_REFERENCE')


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


def resource_binding(resources):
    value = (resources or {}).get(NAME)
    if not isinstance(value, dict): return None
    key, version = value.get('resource_key'), value.get('version')
    if not isinstance(key, str) or not key or 'onnx' in key.lower() or not isinstance(version, str) or not version:
        return None
    return dict(name=NAME, resource_key=key, version=version, service='ExecuteActionResource', resource_type='ARM_MONTION')


def describe(state, fresh=False):
    measured = state.get('joint_values', {}) if fresh else {}
    values = {n: measured[n].get('position') for n in RIGHT if isinstance(measured.get(n), dict)}
    source = 'measured' if len(values) == len(RIGHT) else 'reference_zero'
    profile = build_profile(values if source == 'measured' else dict.fromkeys(RIGHT, 0.))
    binding = resource_binding(state.get('custom_actions')) if fresh else None
    return dict(profile=profile, start_source=source, binding=binding,
                replay_available=binding is not None,
                control_request_sent=False,
                replay_note='로봇에 등록된 punch_right 팔 모션을 재생합니다. 미리보기 목표값을 직접 전송하지 않습니다.' if binding else
                            '오른팔 동작 설계가 준비됐습니다. 실물 재생에는 로봇에 등록된 punch_right 팔 모션이 필요합니다.',
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
