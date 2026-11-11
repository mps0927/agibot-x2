"""SDK responses release request locks without a manual completion command."""
import unittest
from capabilities import DEFAULT_PROFILE,resolve_move
from control_policy import permissions,command_allowed
from x2_worker import finish_native_request

class NativeRequestLifecycle(unittest.TestCase):
    def test_native_and_custom_replies_clear_busy_state_and_keep_request_identity(self):
        for service in ('SetMcPresetMotion','ExecuteActionResource'):
            with self.subTest(service=service):
                state=dict(gesture='wave_right',arm_pending=True,armed=True,error='')
                events=[];context=dict(name='wave_right',request_id='current-request')
                finish_native_request(state,context,0,1,service,lambda event,**details:events.append((event,details)))
                self.assertIsNone(state['gesture']);self.assertFalse(state['arm_pending'])
                self.assertTrue(state['armed']);self.assertTrue(state['native_result']['accepted'])
                self.assertEqual(state['native_result']['request_id'],'current-request')
                self.assertEqual(state['native_result']['physical_outcome'],'NOT_VERIFIED')
                self.assertEqual(events[0][0],'arm_action_ack')

    def test_sdk_failure_does_not_remain_locked_or_claim_acceptance(self):
        for code,sdk_state in ((9,1),(0,2),(0,3),(0,4),(0,5),(0,100),(0,0)):
            with self.subTest(code=code,sdk_state=sdk_state):
                state=dict(gesture='wave_right',arm_pending=True,armed=True,error='')
                finish_native_request(state,dict(name='wave_right'),code,sdk_state,'SetMcPresetMotion',lambda *a,**kw:None)
                self.assertIsNone(state['gesture']);self.assertFalse(state['arm_pending'])
                self.assertFalse(state['armed']);self.assertFalse(state['native_result']['accepted'])
                self.assertIn('거부',state['error'])

    def test_manual_completion_command_is_removed(self):
        self.assertFalse(command_allowed('acknowledge_motion_complete',permissions(full=True)))

    def test_default_forward_speed_uses_sdk_example_but_explicit_speed_is_preserved(self):
        self.assertEqual(DEFAULT_PROFILE['forward_mps'],.2)
        action=resolve_move(dict(velocity=[.1,0,0],seconds=1),DEFAULT_PROFILE)
        self.assertEqual(action['velocity'],[.1,0.,0.])

if __name__=='__main__':unittest.main()
