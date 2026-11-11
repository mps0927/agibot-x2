import unittest
from control_policy import active_locomotion_allowed

class LocomotionStream(unittest.TestCase):
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
