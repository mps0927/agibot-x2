"""Punch authoring is bounded and read-only; replay requires a robot resource."""
import argparse
import csv
import io
import math
from pathlib import Path
import unittest
from aiohttp.test_utils import TestClient, TestServer
from app import create_app
from capabilities import catalog, planner_catalog
from joint_contract import JOINTS
from punch import RIGHT, GUARD, EXTEND, RATE, build_profile, sample, arm_points, resource_binding, export_csv


def arm_resource(key='linkcraft_arm_test'):
    return {'punch_right':dict(name='punch_right',resource_key=key,version='test-v1')}


class PunchTrajectory(unittest.TestCase):
    def test_return_and_peak_rate_are_valid_for_every_right_arm_joint(self):
        start=dict.fromkeys(RIGHT,0.)
        profile=build_profile(start)
        self.assertEqual([k['phase'] for k in profile['keyframes']],['start','guard','extend','recover','return'])
        self.assertEqual(sample(profile,0.),start)
        for a,b in zip(profile['keyframes'],profile['keyframes'][1:]):
            self.assertGreater(b['at'],a['at'])
            for name in RIGHT:
                self.assertLessEqual(1.875*abs(b['joints'][name]-a['joints'][name])/(b['at']-a['at']),RATE+1e-9)
        self.assertEqual(sample(profile,profile['seconds']),start)
        for i in range(1001):
            pose=sample(profile,profile['seconds']*i/1000)
            self.assertEqual(set(pose),set(RIGHT))
            for name,q in pose.items():
                self.assertGreaterEqual(q,JOINTS[name]['lower'])
                self.assertLessEqual(q,JOINTS[name]['upper'])

    def test_measured_start_is_preserved_and_invalid_g1_elbow_is_rejected(self):
        a=dict(GUARD);a[RIGHT[0]]=-.5
        p=build_profile(a)
        self.assertEqual(sample(p,p['seconds']),a)
        self.assertNotEqual(p['target_sha256'],build_profile(GUARD)['target_sha256'])
        for bad in [dict(a,right_elbow_joint=.35),dict(a,right_elbow_joint=math.nan),{RIGHT[0]:0.},dict(a,right_elbow_joint=True)]:
            with self.assertRaises(ValueError):build_profile(bad)
        for at in [-1,math.nan,math.inf,p['seconds']+1,True]:
            with self.assertRaises(ValueError):sample(p,at)

    def test_fk_extension_moves_wrist_forward_and_csv_has_only_right_arm(self):
        self.assertGreater(arm_points(EXTEND)[-1][0]-arm_points(GUARD)[-1][0],.1)
        p=build_profile(GUARD)
        rows=list(csv.reader(io.StringIO(export_csv(p))))
        self.assertEqual(rows[0],['seconds',*RIGHT])
        self.assertEqual([float(v) for v in rows[1][1:]],[GUARD[n] for n in RIGHT])
        self.assertEqual([float(v) for v in rows[-1][1:]],[GUARD[n] for n in RIGHT])
        self.assertAlmostEqual(float(rows[-1][0]),p['seconds'],places=5)

    def test_missing_or_whole_body_resource_is_never_advertised_for_punch(self):
        for resources in ({},arm_resource('LINKCRAFT_ONNX_BODY'),{'punch_right':{}}, {'punch_right':dict(resource_key='arm',version='')}):
            self.assertIsNone(resource_binding(resources))
            self.assertNotIn('punch_right',planner_catalog(custom_actions=resources)['custom_motions'])
        resources=arm_resource()
        self.assertEqual(resource_binding(resources)['resource_type'],'ARM_MONTION')
        self.assertIn('punch_right',catalog(custom_actions=resources)['custom_motions'])


class PunchAPI(unittest.IsolatedAsyncioTestCase):
    async def test_preview_and_download_send_no_robot_request(self):
        args=argparse.Namespace(offline=True,allow_control=False,origin='',env_file=str(Path(__file__).parent/'missing-fixture.env'))
        app=create_app(args);d=app['dashboard'];owner=d.owner
        async with TestClient(TestServer(app)) as client:
            for suffix in ('','?format=json','?format=csv'):
                response=await client.get('/api/punch'+suffix)
                self.assertEqual(response.status,200)
                if 'csv' in suffix:
                    self.assertTrue(response.content_type.startswith('text/csv'))
                    self.assertIn('right_elbow_joint',await response.text())
                else:
                    data=await response.json()
                    self.assertFalse(data['control_request_sent'])
                    self.assertFalse(data['replay_available'])
                    self.assertEqual(data['start_source'],'reference_zero')
                    self.assertEqual(len(data['preview']),101)
            self.assertEqual(d.owner,owner)
            self.assertEqual(d.state.get('control_requests_sent',0),0)
            self.assertIn((await client.post('/api/punch',json={})).status,(403,405))


if __name__=='__main__': unittest.main()
