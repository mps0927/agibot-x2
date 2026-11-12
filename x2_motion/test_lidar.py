import struct,time,unittest
from types import SimpleNamespace as NS
from lidar import CloudRelay,CloudCache,DEFAULT_TOPIC,decode_pointcloud,MAX_POINTS

def cloud(points,big=False,row_padding=0):
    endian='>' if big else '<'
    raw=b''.join(struct.pack(endian+'fff',*point) for point in points)+bytes(row_padding)
    return NS(width=len(points),height=1,point_step=12,row_step=len(raw),data=raw,is_bigendian=big,
              fields=[NS(name=k,datatype=7,count=1,offset=i*4) for i,k in enumerate('xyz')],
              header=NS(frame_id='lidar_chest_front',stamp=NS(sec=10,nanosec=30)))

class LiDARContract(unittest.TestCase):
    def test_binary_fields_endianness_filter_and_padding(self):
        for big in (False,True):
            result=decode_pointcloud(cloud([(1,2,3),(float('nan'),1,2)],big,16))
            self.assertEqual(result['points'],[[1.,2.,3.]])
            self.assertEqual(result['points_total'],2)
    def test_truncation_and_point_limit(self):
        message=cloud([(1,2,3)]);message.data=message.data[:4]
        with self.assertRaises(ValueError):decode_pointcloud(message)
        result=decode_pointcloud(cloud([(1,2,3)]*(MAX_POINTS*2)))
        self.assertLessEqual(len(result['points']),MAX_POINTS)
    def test_new_frame_only_and_expired_response_rejected(self):
        relay=CloudRelay();cache=CloudCache();generation=relay.generation
        relay.offer(cloud([(1,2,3)]),generation)
        relay.request('first');cache.request('first')
        self.assertIsNone(relay.take_frame())
        relay.offer(cloud([(4,5,6)]),generation);frame=relay.take_frame()
        self.assertTrue(cache.accept(frame));self.assertTrue(cache.ready(True))
        self.assertEqual(cache.snapshot(True)['points'],[[4.,5.,6.]])
        relay.request('old');cache.request('old');relay.offer(cloud([(1,1,1)]),generation)
        old=relay.take_frame();cache.pending=('old',time.monotonic()-2)
        self.assertFalse(cache.accept(old))
        cache.request('new');self.assertFalse(cache.accept(old))
        cache.clear();self.assertFalse(cache.ready(True))
    def test_old_generation_cannot_supply_new_subscription(self):
        relay=CloudRelay();old=relay.generation;relay.select(DEFAULT_TOPIC)
        relay.request('x');relay.offer(cloud([(1,2,3)]),old)
        self.assertIsNone(relay.take_frame())
