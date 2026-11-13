import io,json,struct,time,unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from PIL import Image
from sensors import SensorRegistry,DEFAULT_CAMERA,POINTCLOUD,describe,lidar_choice,bounded_value,camera_jpeg
from lidar import DEFAULT_TOPIC


class SensorContracts(unittest.TestCase):
    def test_device_names_and_command_exclusion(self):
        for device in ('rgb_head_front_center','stereo_head_front_left','stereo_head_front_right','rgb_head_rear','rgbd_head_front'):
            item=describe('/aima/hal/sensor/'+device+'/rgb_image/compressed','sensor_msgs/msg/CompressedImage')
            self.assertEqual(item['kind'],'camera');self.assertTrue(item['preview']);self.assertNotEqual(item['label'],device)
        self.assertEqual(describe('/aima/hal/sensor/rgbd_head_front/depth_image','sensor_msgs/msg/Image')['kind'],'depth')
        self.assertIsNone(describe('/aima/hal/joint/arm/command','aimdk_msgs/msg/JointCommandArray'))
        self.assertIsNone(describe('/aima/hal/audio/playback','aimdk_msgs/msg/AudioPlayback'))

    def test_discovery_does_not_claim_that_a_subscriber_is_a_sensor(self):
        registry=SensorRegistry();registry.discover([(DEFAULT_TOPIC,[POINTCLOUD])],lambda _:0)
        entry=next(item for item in registry.snapshot() if item['topic']==DEFAULT_TOPIC)
        self.assertEqual(entry['publishers'],0);self.assertFalse(entry['receiving']);self.assertIsNone(entry['value'])
        self.assertFalse(next(item for item in registry.snapshot() if item['topic']==DEFAULT_CAMERA)['observed'])

    def test_receiving_values_expire_and_json_stays_bounded(self):
        class Message:
            header=NS();value=float('nan');data=bytes(1000000)
            def get_fields_and_field_types(self):return dict(value='float',data='bytes')
        registry=SensorRegistry();topic='/aima/hal/imu/torso/state'
        registry.discover([(topic,['sensor_msgs/msg/Imu'])],lambda _:1)
        registry.offer(topic,Message())
        entry=next(item for item in registry.snapshot() if item['topic']==topic)
        self.assertTrue(entry['receiving']);self.assertEqual(entry['value']['data'],{'count':1000000})
        self.assertIsNone(entry['value']['value']);self.assertLess(len(json.dumps(entry,allow_nan=False)),1000)
        registry.at[topic]=time.monotonic()-3
        self.assertFalse(next(item for item in registry.snapshot() if item['topic']==topic)['receiving'])

    def test_lidar_is_automatically_selected_from_real_publishers(self):
        alternate='/sensor/lidar/points';camera='/sensor/rgbd/points'
        topics=[(alternate,[POINTCLOUD]),(camera,[POINTCLOUD]),(DEFAULT_TOPIC,[POINTCLOUD])]
        counts={alternate:1,camera:1,DEFAULT_TOPIC:0}
        self.assertEqual(lidar_choice(topics,counts.get,DEFAULT_TOPIC,DEFAULT_TOPIC),alternate)
        counts[DEFAULT_TOPIC]=1
        self.assertEqual(lidar_choice(topics,counts.get,alternate,DEFAULT_TOPIC),DEFAULT_TOPIC)
        self.assertEqual(lidar_choice([],lambda _:0,DEFAULT_TOPIC,DEFAULT_TOPIC),DEFAULT_TOPIC)

    def test_native_jpeg_is_preserved_and_raw_rgb_padding_is_respected(self):
        out=io.BytesIO();Image.new('RGB',(4,4),'blue').save(out,format='JPEG');jpeg=out.getvalue()
        self.assertEqual(camera_jpeg(NS(data=jpeg)),jpeg)
        message=NS(width=2,height=2,step=8,encoding='rgb8',is_bigendian=False,
                   data=bytes([255,0,0]*2+[0,0]+[255,0,0]*2+[0,0]))
        with Image.open(io.BytesIO(camera_jpeg(message))) as picture:
            self.assertEqual(picture.size,(2,2));self.assertGreater(picture.getpixel((0,0))[0],200)

    def test_unknown_camera_encoding_is_rejected(self):
        with self.assertRaises(ValueError):camera_jpeg(NS(width=1,height=1,step=1,encoding='unknown',data=b'1'))


if __name__=='__main__':unittest.main()
