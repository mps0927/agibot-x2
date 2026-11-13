"""Exercise the worker's actual RPC boundary with fake SDK clients, no robot I/O."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace as Obj
import unittest

from control_policy import validate_preset_dispatch


class PresetMCPolicy(unittest.TestCase):
    def boundary(self, **changes):
        tree=ast.parse(Path(__file__).with_name('x2_worker.py').read_text(encoding='utf-8'))
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        mutate=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='mutate')
        # Only detach the closure's busy flag; retain the real validation, RPC
        # call and response/error callback, including their ordering.
        mutate.body=[n for n in mutate.body if not isinstance(n,ast.Nonlocal)]
        state=dict(fsm='STAND_DEFAULT',fsm_status=100,armed=True,control_requests_sent=0,
                   mode_changes_sent=0,error='')
        state.update(changes)
        sent=[];events=[];callbacks=[]
        def client(service):
            def call(request):
                sent.append(service)
                return Obj(add_done_callback=callbacks.append)
            return Obj(service_is_ready=lambda:True,call_async=call)
        services=('SetMcPresetMotion','ExecuteActionResource','SetMcAction','SetMcInputSource')
        namespace=dict(enabled=True,state=state,mode_at=10.,time=Obj(monotonic=lambda:10.1),
                       clients={name:client(name) for name in services},
                       timestamp=lambda request:None,asdict=lambda request:{},
                       validate_preset_dispatch=validate_preset_dispatch,
                       event=lambda event_name,**details:events.append((event_name,details)))
        exec(compile(ast.Module(body=[mutate],type_ignores=[]),'<actual-worker-rpc>','exec'),namespace)
        return namespace,state,sent,callbacks

    def test_native_motion_uses_one_sdk_rpc_and_retains_mc_mode(self):
        for mode in ('STAND_DEFAULT','LOCOMOTION_DEFAULT'):
            for action,service in (('gesture','SetMcPresetMotion'),('custom_motion','ExecuteActionResource')):
                with self.subTest(mode=mode,action=action):
                    ns,state,sent,_=self.boundary(fsm=mode)
                    ns['mutate'](service,Obj(),lambda response:None,dict(action=action,name='fixture'))
                    self.assertEqual(sent,[service])
                    self.assertEqual(state['fsm'],mode)
                    self.assertEqual(state['mode_changes_sent'],0)

    def test_preset_cannot_dispatch_mode_switch_or_input_source_changes(self):
        for action in ('gesture','custom_motion'):
            for service in ('SetMcAction','SetMcInputSource'):
                with self.subTest(action=action,service=service):
                    ns,state,sent,_=self.boundary()
                    with self.assertRaises(ValueError):
                        ns['mutate'](service,Obj(),lambda response:None,dict(action=action))
                    self.assertEqual(sent,[])
                    self.assertEqual(state['control_requests_sent'],0)
        for context in (None,{},dict(action='set_mode')):
            ns,_,sent,_=self.boundary()
            with self.assertRaises(ValueError):ns['mutate']('SetMcPresetMotion',Obj(),None,context)
            self.assertEqual(sent,[])

    def test_non_balancing_modes_and_stale_or_disarmed_state_cannot_dispatch(self):
        changes=[dict(fsm=mode) for mode in ('PASSIVE_DEFAULT','DAMPING_DEFAULT','JOINT_DEFAULT','SIT_JOINT_DEFAULT',None)]
        changes += [dict(fsm_status=200),dict(armed=False)]
        for change in changes:
            ns,state,sent,_=self.boundary(**change)
            with self.assertRaises(ValueError):
                ns['mutate']('SetMcPresetMotion',Obj(),None,dict(action='gesture'))
            self.assertEqual(sent,[])
            self.assertEqual(state['control_requests_sent'],0)
        ns,state,sent,_=self.boundary()
        for age in (-1,2.01,math.nan,math.inf,True,None):
            with self.subTest(age=age),self.assertRaises(ValueError):
                validate_preset_dispatch('SetMcPresetMotion',dict(action='gesture'),state,age)
        ns['mode_at']=0.
        with self.assertRaises(ValueError):ns['mutate']('ExecuteActionResource',Obj(),None,dict(action='custom_motion'))
        self.assertEqual(sent,[])

    def test_sdk_error_does_not_trigger_a_mode_switch_fallback(self):
        ns,state,sent,callbacks=self.boundary()
        def rejected(response):raise ValueError('SDK fixture rejected')
        ns['mutate']('SetMcPresetMotion',Obj(),rejected,dict(action='gesture'))
        callbacks[0](Obj(result=lambda:Obj()))
        self.assertEqual(sent,['SetMcPresetMotion'])
        self.assertEqual(state['fsm'],'STAND_DEFAULT')
        self.assertFalse(state['armed'])
        self.assertIn('fixture rejected',state['error'])

    def test_explicit_operator_shutdown_still_uses_its_separate_path(self):
        ns,state,sent,_=self.boundary(fsm='SIT_JOINT_DEFAULT',armed=False)
        ns['mutate']('SetMcAction',Obj(),lambda response:None,dict(action='set_mode',mode='zero_torque'))
        self.assertEqual(sent,['SetMcAction'])


if __name__=='__main__':unittest.main()
