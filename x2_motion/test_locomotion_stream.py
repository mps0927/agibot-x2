import ast,math,unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from capabilities import DEFAULT_PROFILE,velocity,validate_velocity,validate_profile,resolve_move,planner_catalog
from control_policy import active_locomotion_allowed

class LocomotionStream(unittest.TestCase):
    def test_controller_rate_reaches_both_sdk_rotation_fields_and_zero_stop(self):
        tree=ast.parse(Path(__file__).with_name('x2_worker.py').read_text(encoding='utf-8'))
        main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='main')
        publish=next(node for node in main.body if isinstance(node,ast.FunctionDef) and node.name=='publish_velocity')
        messages=[];stamp=Obj(sec=1,nanosec=0)
        namespace=dict(scopes={'movement':True},registered=True,source='rotation-fixture',
            publisher=Obj(publish=messages.append),state={'velocity_publications':0},
            node=Obj(get_clock=lambda:Obj(now=lambda:Obj(to_msg=lambda:stamp))),
            McLocomotionVelocity=lambda:Obj(header=Obj()))
        exec(compile(ast.Module(body=[publish],type_ignores=[]),'<actual-worker-publisher>','exec'),namespace)
        for direction in ('turn_left','turn_right'):
            vector=validate_velocity(velocity(direction,DEFAULT_PROFILE))
            namespace['publish_velocity'](vector)
        namespace['publish_velocity']([0.,0.,0.])
        self.assertEqual([(m.forward_velocity,m.lateral_velocity,m.angular_velocity) for m in messages],
                         [(0.,0.,.97),(0.,0.,-.97),(0.,0.,0.)])
        self.assertTrue(all(m.source=='rotation-fixture' and m.header.stamp is stamp for m in messages))
        self.assertEqual(namespace['state']['published_velocity'],[0.,0.,0.])
        self.assertEqual(namespace['state']['velocity_publications'],3)

    def test_rotation_limit_does_not_raise_translation_limits(self):
        self.assertEqual(validate_velocity([.3,-.3,.97]),(.3,-.3,.97))
        self.assertEqual(validate_velocity([0,0,-.97]),(0.,0.,-.97))
        validate_profile(dict(DEFAULT_PROFILE,yaw_rps=.97))
        for vector in ([.31,0,0],[0,-.31,0],[0,0,.98],[0,0,-.98],[0,0,math.nan],[0,0,True]):
            with self.subTest(vector=vector),self.assertRaises(ValueError):validate_velocity(vector)
        for rate in (.98,1.0,math.inf):
            with self.assertRaises(ValueError):validate_profile(dict(DEFAULT_PROFILE,yaw_rps=rate))

    def test_vlm_rotation_uses_the_same_reference_and_limit(self):
        catalog=planner_catalog(profile=DEFAULT_PROFILE)
        self.assertEqual(catalog['moves']['turn_left'],(0.,0.,.97))
        self.assertEqual(catalog['moves']['turn_right'],(0.,0.,-.97))
        for rate in (-.97,.97):
            self.assertEqual(resolve_move(dict(velocity=[0,0,rate],seconds=1.),DEFAULT_PROFILE)['velocity'],[0.,0.,rate])
        with self.assertRaises(ValueError):resolve_move(dict(velocity=[0,0,.98],seconds=1.),DEFAULT_PROFILE)

    def test_stand_to_walk_transition_keeps_existing_held_command(self):
        for mode,status in (('STAND_DEFAULT',100),('LOCOMOTION_DEFAULT',200),('LOCOMOTION_DEFAULT',100)):
            self.assertTrue(active_locomotion_allowed(mode,status,.1,True,True,.08,.5))

    def test_transition_cannot_start_a_new_command_or_survive_lost_control(self):
        self.assertFalse(active_locomotion_allowed('LOCOMOTION_DEFAULT',200,.1,True,False,.08,.5))
        self.assertFalse(active_locomotion_allowed('LOCOMOTION_DEFAULT',200,.1,False,True,.08,.5))
        self.assertFalse(active_locomotion_allowed('LOCOMOTION_DEFAULT',200,.1,True,True,.31,.5))
        self.assertFalse(active_locomotion_allowed('LOCOMOTION_DEFAULT',200,2.1,True,True,.08,.5))

    def test_unknown_protected_and_long_transitions_still_stop(self):
        for mode,status,elapsed in (('LOCOMOTION_DEFAULT',300,.1),('STAND_DEFAULT',200,.1),
                                    ('PASSIVE_DEFAULT',100,.1),('SIT_DOWN_DEFAULT',200,.1),
                                    ('LOCOMOTION_DEFAULT',200,2.01)):
            self.assertFalse(active_locomotion_allowed(mode,status,.1,True,True,.08,elapsed))

if __name__=='__main__':unittest.main()
