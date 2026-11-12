"""Bounded PointCloud2 preview over the existing robot SSH connection."""
import math
import re
import struct
import threading
import time
from collections import deque

DEFAULT_TOPIC = '/aima/hal/sensor/lidar_chest_front/lidar_pointcloud'
MAX_POINTS = 3000
FRESH_MS = 1500


def validate_topic(topic):
    if (not isinstance(topic, str) or len(topic) > 256 or '__' in topic or
            not re.fullmatch(r'(?:/[A-Za-z_][A-Za-z0-9_]*)+', topic)):
        raise ValueError('ROS 2 점군 토픽 이름을 확인하세요.')
    return topic


def point_summary(points):
    """Distances are in the native sensor frame, from a sampled cloud only."""
    return dict(sampled_points=len(points),
                nearest_sample_m=round(min((math.hypot(*p) for p in points), default=0), 3) if points else None,
                bounds_m={axis: [min(p[i] for p in points), max(p[i] for p in points)]
                          for i, axis in enumerate(('x', 'y', 'z'))} if points else {})


def decode_pointcloud(message):
    """Read float32/64 XYZ with row padding and endianness; no numpy/ROS dependency."""
    width, height = int(message.width), int(message.height)
    step, row = int(message.point_step), int(message.row_step)
    total = width * height
    if min(width, height, step, row) < 0 or total > 2_000_000 or step > 1024:
        raise ValueError('PointCloud2 크기가 지원 범위를 벗어났습니다.')
    if (total and (not step or row < width * step)) or len(message.data) > 16 * 1024 * 1024:
        raise ValueError('PointCloud2 행 간격 또는 데이터 크기가 올바르지 않습니다.')
    required = (height - 1) * row + width * step if total else 0
    if len(message.data) < required:
        raise ValueError('PointCloud2 데이터가 잘렸습니다.')
    fields = {f.name: f for f in message.fields}
    readers = []
    for axis in ('x', 'y', 'z'):
        field = fields.get(axis)
        if field is None or field.datatype not in (7, 8) or field.count != 1:
            raise ValueError('PointCloud2에 float32/64 XYZ 필드가 필요합니다.')
        reader = struct.Struct(('>' if message.is_bigendian else '<') + ('f' if field.datatype == 7 else 'd'))
        if field.offset < 0 or field.offset + reader.size > step:
            raise ValueError('PointCloud2 XYZ 필드 위치가 올바르지 않습니다.')
        readers.append((field.offset, reader))
    raw = memoryview(message.data)
    points = []
    stride = max(1, math.ceil(total / MAX_POINTS))
    for index in range(0, total, stride):
        offset = (index // width) * row + (index % width) * step
        xyz = [reader.unpack_from(raw, offset + position)[0] for position, reader in readers]
        if all(math.isfinite(v) and abs(v) <= 10000 for v in xyz):
            points.append([round(v, 4) for v in xyz])
    stamp = message.header.stamp
    return dict(frame_id=message.header.frame_id, stamp=dict(sec=int(stamp.sec), nanosec=int(stamp.nanosec)),
                points_total=total, points=points, summary=point_summary(points))


class CloudRelay:
    """ROS callbacks only replace one message; conversion runs on a separate thread."""
    def __init__(self, topic=DEFAULT_TOPIC):
        self.lock = threading.Lock()
        self.generation = 0
        self.select(topic)

    def select(self, topic):
        with self.lock:
            self.topic = validate_topic(topic)
            self.generation += 1
            self.message = None
            self.at = 0.
            self.sequence = self.sent = 0
            self.arrivals = deque(maxlen=30)
            self.error = ''
            self.pending = None
            return self.generation

    def request(self, request_id):
        with self.lock:
            self.pending = (request_id, self.sequence, self.generation)

    def offer(self, message, generation):
        with self.lock:
            if generation != self.generation:
                return
            self.message = message
            self.at = time.monotonic()
            self.sequence += 1
            self.arrivals.append(self.at)

    def take_frame(self):
        with self.lock:
            if self.message is None or not self.pending or self.sequence <= self.pending[1]:
                return None
            message, at, sequence, generation, topic = self.message, self.at, self.sequence, self.generation, self.topic
            request_id = self.pending[0]
            self.pending = None
            self.sent = sequence
        if (time.monotonic() - at) * 1000 >= FRESH_MS:
            return None
        try:
            frame = decode_pointcloud(message)
        except (ValueError, TypeError, AttributeError, struct.error) as exc:
            with self.lock:
                if generation == self.generation:
                    self.error = str(exc)
            return None
        with self.lock:
            if generation != self.generation:
                return None
            self.error = ''
        return dict(frame, type='lidar_frame', topic=topic, generation=generation, sequence=sequence,frame_request_id=request_id,
                    source_age_ms=int((time.monotonic() - at) * 1000))

    def status(self):
        with self.lock:
            hz = ((len(self.arrivals) - 1) / (self.arrivals[-1] - self.arrivals[0])
                  if len(self.arrivals) > 1 and self.arrivals[-1] > self.arrivals[0] else 0.)
            return dict(topic=self.topic, generation=self.generation, source_hz=round(hz, 1),
                        receive_age_ms=int((time.monotonic() - self.at) * 1000) if self.at else None,
                        error=self.error)


class CloudCache:
    def __init__(self, topic=DEFAULT_TOPIC):
        self.select(topic)

    def select(self, topic):
        self.topic = validate_topic(topic)
        self.clear()

    def clear(self):
        self.frame = None
        self.at = 0.
        self.pending = None

    def request(self, request_id):
        self.pending=(request_id,time.monotonic())

    def accept(self, data):
        points = data.get('points')
        age = data.get('source_age_ms')
        if (not self.pending or data.get('frame_request_id') != self.pending[0] or
                (time.monotonic()-self.pending[1])*1000 >= FRESH_MS or
                data.get('topic') != self.topic or not isinstance(points, list) or len(points) > MAX_POINTS or
                type(age) not in (int, float) or not math.isfinite(age) or age < 0):
            return False
        if any(not isinstance(p, list) or len(p) != 3 or
               any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 10000 for v in p) for p in points):
            return False
        self.frame = dict(data, summary=point_summary(points))
        self.at = self.pending[1]
        self.pending = None
        return True

    def age_ms(self):
        return int((time.monotonic() - self.at) * 1000) if self.frame else None

    def ready(self, connected):
        return bool(connected and self.frame and self.frame['points'] and self.age_ms() < FRESH_MS)

    def snapshot(self, connected):
        if not self.ready(connected):
            raise ValueError('최신 LiDAR 점군이 없습니다. 로봇 연결과 점군 수신 상태를 확인하세요.')
        return dict(self.frame, age_ms=self.age_ms())

    def observation(self, connected):
        frame = self.snapshot(connected)
        return dict(enabled=True, topic=frame['topic'], frame_id=frame['frame_id'], stamp=frame['stamp'],
                    session_id=frame['session_id'],generation=frame['generation'],frame_request_id=frame['frame_request_id'],
                    sequence=frame['sequence'], age_ms=frame['age_ms'], points_total=frame['points_total'],
                    **frame['summary'], coordinate_system='native_sensor', synchronized_with_rgb=False,
                    interpretation='Sampled sensor-frame distances; no robot-frame clearance or collision guarantee.')
