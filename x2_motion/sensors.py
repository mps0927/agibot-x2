"""Read-only sensor discovery, bounded telemetry, and camera conversion."""
import math
import time
from collections import deque

BASE='/aima/hal/sensor/'
DEFAULT_CAMERA=BASE+'rgb_head_front_center/rgb_image/compressed'
POINTCLOUD='sensor_msgs/msg/PointCloud2'
IMAGES={'sensor_msgs/msg/CompressedImage','sensor_msgs/msg/Image'}

DEVICES={
    'rgb_head_front_center':('머리 정면 RGB','머리 정면','camera'),
    'stereo_head_front_left':('전면 스테레오 왼쪽','머리 전면 왼쪽','camera'),
    'stereo_head_front_right':('전면 스테레오 오른쪽','머리 전면 오른쪽','camera'),
    'rgb_head_rear':('후면 RGB','머리 뒤쪽','camera'),
    'rgbd_head_front':('전면 RGB-D','머리 전면','camera'),
    'stereo_head_front':('스테레오','머리 전면','imu'),
    'lidar_chest_front':('가슴 라이다','가슴 전면','lidar'),
    'touch_head':('머리 터치','머리','touch'),
    'gnss':('GNSS 위치','GNSS 수신기','gnss'),
}

EXPECTED=[(DEFAULT_CAMERA,'sensor_msgs/msg/CompressedImage')]
for device in ('stereo_head_front_left','stereo_head_front_right','rgb_head_rear','rgbd_head_front'):
    EXPECTED.append((BASE+device+'/rgb_image/compressed','sensor_msgs/msg/CompressedImage'))
EXPECTED += [(BASE+'rgbd_head_front/depth_image','sensor_msgs/msg/Image'),
    (BASE+'lidar_chest_front/lidar_pointcloud',POINTCLOUD),
    (BASE+'lidar_chest_front/imu','sensor_msgs/msg/Imu'),
    (BASE+'stereo_head_front/imu','sensor_msgs/msg/Imu'),
    (BASE+'rgbd_head_front/imu','sensor_msgs/msg/Imu'),
    ('/aima/hal/imu/chest/state','sensor_msgs/msg/Imu'),
    ('/aima/hal/imu/torso/state','sensor_msgs/msg/Imu'),
    (BASE+'touch_head','aimdk_msgs/msg/TouchState'),
    (BASE+'gnss','sensor_msgs/msg/NavSatFix')]


def describe(topic,datatype):
    """Classify data sources only. Commands/playback are deliberately excluded."""
    if topic.startswith(BASE):
        device=topic[len(BASE):].split('/')[0]
        label,location,kind=DEVICES.get(device,(device,'센서','status'))
        if datatype in IMAGES:
            if '/depth_image' in topic:label+=' · 깊이';kind='depth'
            else:
                kind='camera'
                if datatype=='sensor_msgs/msg/Image':label+=' · 원본 영상'
        elif datatype.endswith('/Imu'):label+=' · IMU';kind='imu'
        elif datatype.endswith('/CameraInfo'):
            label+=(' · 깊이 렌즈 정보' if '/depth_camera_info' in topic else ' · 컬러 렌즈 정보' if '/rgb_camera_info' in topic else ' · 렌즈 정보');kind='calibration'
        elif datatype==POINTCLOUD:
            kind='lidar'
            if topic.endswith('_down_sampling'):label+=' · 경량 점군'
        elif datatype.endswith('/LidarRawData'):kind='raw_info';label+=' · 원본 패킷 정보'
        elif datatype.endswith('/ModuleInfo'):kind='status';label+=' · 장치 상태'
        elif 'H265' in datatype:kind='video_info';label+=' · H.265'
    elif topic.startswith('/aima/hal/imu/'):
        label='가슴 IMU' if '/chest/' in topic else '몸통 IMU';location='가슴' if '/chest/' in topic else '몸통';kind='imu'
    elif topic=='/aima/hal/pmu/state':label,location,kind='배터리·전원','몸통 배터리','power'
    elif topic.startswith('/aima/hal/joint/') and topic.endswith('/state'):
        group=topic.split('/')[-2]
        label={'arm':'팔','leg':'다리','hand':'손','head':'머리','waist':'허리',
               'ddcu_joint':'DDCU 보조 관절 상태','udcu_joint':'UDCU 보조 관절 상태'}.get(group,group)
        if group not in ('ddcu_joint','udcu_joint'):label+=' 관절'
        location='관절';kind='joint'
    elif topic.startswith('/aima/hal/monitor/'):
        label,location,kind='관절 제어기 '+topic.rsplit('/',1)[-1],'몸통','status'
    elif topic in ('/aima/hal/audio/capture','/aima/hal/audio/play_state','/aima/hal/audio/volume'):
        label,location,kind={'capture':('마이크 수신','머리','audio'),'play_state':('스피커 상태','머리','audio'),'volume':('스피커 음량','머리','audio')}[topic.rsplit('/',1)[-1]]
    else:return None
    if topic==BASE+'module_info':label='센서 모듈 상태'
    return dict(id=topic,topic=topic,datatype=datatype,label=label,location=location,kind=kind,
                preview=datatype in IMAGES)


def lidar_choice(topics,publishers,current,preferred):
    candidates=sorted(name for name,types in topics if POINTCLOUD in types and 'lidar' in name.lower() and publishers(name)>0)
    if preferred in candidates:return preferred
    if current in candidates:return current
    return candidates[0] if candidates else current


def bounded_value(value,depth=0):
    if value is None or isinstance(value,(bool,str,int)):return value[:200] if isinstance(value,str) else value
    if isinstance(value,float):return value if math.isfinite(value) else None
    if depth>=4:return {'type':type(value).__name__}
    if isinstance(value,dict):return {str(key):bounded_value(item,depth+1) for key,item in list(value.items())[:20]}
    if hasattr(value,'get_fields_and_field_types'):
        return {name:bounded_value(getattr(value,name),depth+1) for name in list(value.get_fields_and_field_types())[:20]}
    if hasattr(value,'__len__'):
        size=len(value)
        if isinstance(value,(bytes,bytearray,memoryview)) or size>32:return {'count':size}
        return [bounded_value(item,depth+1) for item in value]
    return str(value)[:200]


class SensorRegistry:
    def __init__(self):
        self.entries={};self.samples={};self.arrivals={};self.at={};self.sample_at={};self.errors={};self.transport={}

    def discover(self,topics,publishers):
        entries={}
        for topic,types in topics:
            for datatype in types:
                spec=describe(topic,datatype)
                if spec:entries[topic]=dict(spec,publishers=publishers(topic),observed=True);break
        for topic,datatype in EXPECTED:
            if topic not in entries:entries[topic]=dict(describe(topic,datatype),publishers=0,observed=False)
        self.entries=entries

    def offer(self,topic,message,transport='ros2'):
        now=time.monotonic();self.at[topic]=now
        self.transport[topic]=transport
        self.arrivals.setdefault(topic,deque(maxlen=60)).append(now)
        if now-self.sample_at.get(topic,-1)>=.5:
            self.samples[topic]=bounded_value(message);self.sample_at[topic]=now
        self.errors.pop(topic,None)

    def snapshot(self):
        now=time.monotonic();result=[]
        for topic,spec in self.entries.items():
            times=self.arrivals.get(topic,[]);age=int((now-self.at[topic])*1000) if topic in self.at else None
            hz=round((len(times)-1)/(times[-1]-times[0]),1) if len(times)>1 and times[-1]>times[0] else 0.
            result.append(dict(spec,age_ms=age,hz=hz,receiving=age is not None and age<2000,
                metadata_only=spec['kind'] in ('video_info','raw_info'),
                transport=self.transport.get(topic),
                value=self.samples.get(topic),error=self.errors.get(topic,'')))
        return sorted(result,key=lambda item:(item['kind'],item['label'],item['topic']))


def camera_jpeg(message):
    """Preserve native JPEG; render raw color/depth images only when selected."""
    import io
    from PIL import Image
    if not hasattr(message,'encoding'):
        data=bytes(message.data)
        if data.startswith(b'\xff\xd8'):return data
        with Image.open(io.BytesIO(data)) as image:
            out=io.BytesIO();image.convert('RGB').save(out,format='JPEG',quality=85);return out.getvalue()
    width,height,step=message.width,message.height,message.step
    if not 0<width*height<=20_000_000 or len(message.data)>32*1024*1024:raise ValueError('카메라 영상 크기를 확인하세요.')
    encoding=message.encoding.lower()
    if encoding in ('16uc1','mono16','32fc1'):
        import numpy as np
        dtype=np.dtype(('>' if message.is_bigendian else '<')+('f4' if encoding=='32fc1' else 'u2'))
        values=np.ndarray((height,width),dtype=dtype,buffer=message.data,strides=(step,dtype.itemsize))
        values=values[::max(1,height//480),::max(1,width//640)].astype(float)
        if encoding!='32fc1':values/=1000.
        valid=np.isfinite(values)&(values>0)
        gray=np.where(valid,255*(1-np.clip(np.nan_to_num(values,nan=6,posinf=6)/6,0,1)),0).astype('uint8')
        image=Image.fromarray(gray).convert('RGB')
    elif encoding in ('rgb8','bgr8','rgba8','bgra8','mono8','8uc1'):
        bands={'rgb8':3,'bgr8':3,'rgba8':4,'bgra8':4,'mono8':1,'8uc1':1}[encoding]
        mode='L' if bands==1 else 'RGB' if bands==3 else 'RGBA'
        raw={'rgb8':'RGB','bgr8':'BGR','rgba8':'RGBA','bgra8':'BGRA'}.get(encoding,'L')
        image=Image.frombytes(mode,(width,height),bytes(message.data),'raw',raw,step).convert('RGB')
    else:raise ValueError('이 카메라 인코딩은 미리보기를 지원하지 않습니다: '+encoding)
    image.thumbnail((1280,960));out=io.BytesIO();image.save(out,format='JPEG',quality=85);return out.getvalue()
