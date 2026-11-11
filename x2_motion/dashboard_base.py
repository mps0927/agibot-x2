"""Single-host dashboard with a local browser and direct SSH to X2."""
import asyncio
from collections import deque
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
import uuid

import asyncssh
from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
from PIL import Image

from capabilities import DIRECTIONS
from capabilities import GESTURES, MODES, DEFAULT_PROFILE, catalog, planner_catalog, validate_profile
from control_policy import validate_plan_execution, PLAN_TTL_SECONDS
from vlm_recording import begin_run,save_json
from pipeline import Pipeline, PlanValidationError, runtime_system_prompt
from joint_contract import (
    preview as preview_joint_pose,
    catalog as joint_catalog,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE


class Dashboard:
    def __init__(self, args):
        self.args = args
        self.pipeline = Pipeline()
        self.process = None
        self.session = None
        self.clients = set()
        self.owner = None
        self.owner_beat = 0.
        self.state = dict(connected=False, fsm=None, ready=False, armed=False, moving=False)
        self.state_at = 0.
        self.events = deque(maxlen=20)
        self.frames = {}
        self.plans = {}
        self.plan_task = None
        self.tasks = []
        self.write_lock = asyncio.Lock()
        self.infer_lock = asyncio.Lock()
        self.closing = False
        self.reconnect_delay = 3.
        self.pipeline_status = dict(stage="idle", message="지시를 입력하고 분석 또는 실행을 선택하세요.")
        self.capture_root = ROOT / "artifacts" / "camera_captures"

    async def progress(self, stage, message, **details):
        self.pipeline_status = dict(stage=stage, message=message, at=time.time(), **details)
        self.events.append(dict(type="event", event="pipeline_" + stage,
                                local_at=time.time(), **details))
        await self.broadcast()

    async def start(self, app):
        self.session = ClientSession(timeout=ClientTimeout(total=60))
        if getattr(self.args,"offline",False):
            self.state.update(connected=False,ready=False,offline=True)
            return
        self.tasks = [asyncio.create_task(self.maintain_worker()), asyncio.create_task(self.watchdog())]

    async def connect_worker(self):
        raise NotImplementedError("Use the X2Dashboard SSH adapter")

    async def invalidate_connection(self):
        await self.cancel_plan()
        self.owner = None
        self.state_at = 0.
        self.state = dict(connected=False, fsm=None, ready=False, armed=False, moving=False,
                          reconnecting=not self.closing)
        # Observations/plans from a previous robot session cannot be executed.
        self.frames.clear()
        self.plans.clear()
        await self.broadcast()

    async def maintain_worker(self):
        while not self.closing:
            await self.invalidate_connection()
            readers = []
            process = None
            try:
                process = self.process = await self.connect_worker()
                readers = [asyncio.create_task(self.read_worker(process)),
                           asyncio.create_task(self.read_errors(process))]
                await readers[0]
            except asyncio.CancelledError:
                raise
            except (OSError, RuntimeError, asyncssh.Error) as exc:
                print("X2 connection:", str(exc), flush=True)
            finally:
                for task in readers:
                    task.cancel()
                await asyncio.gather(*readers, return_exceptions=True)
                if process and process.returncode is None:
                    if process.stdin:
                        process.stdin.close()
                    with contextlib.suppress(ProcessLookupError):
                        process.terminate()
                    await process.wait()
                if self.process is process:
                    self.process = None
                await self.invalidate_connection()
            if not self.closing:
                await asyncio.sleep(self.reconnect_delay)

    async def close(self, app):
        self.closing = True
        await self.cancel_plan()
        with contextlib.suppress(Exception):
            await self.send(dict(action="disarm"))
        for ws in list(self.clients):
            await ws.close()
        if self.process:
            process = self.process
            process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), 3)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()
                await process.wait()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.session.close()

    async def send(self, msg):
        if not self.process or self.process.returncode is not None:
            raise RuntimeError("X2 SSH 연결이 끊겼습니다.")
        if msg.get("action") in ("arm", "hold", "gesture", "custom_motion", "set_mode") and (
                not self.state.get("connected") or time.monotonic() - self.state_at > 1.):
            raise RuntimeError("X2의 최신 상태를 기다리는 중입니다. 제어를 다시 활성화하세요.")
        async with self.write_lock:
            self.process.stdin.write((json.dumps(msg) + "\n").encode())
            await asyncio.wait_for(self.process.stdin.drain(), 1)

    async def read_worker(self, process=None):
        process = process or self.process
        try:
            async for line in process.stdout:
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if data.get("type") == "camera_frame":
                    self.accept_camera(data)
                    continue
                if data.get("type") == "state":
                    self.state = dict(data, connected=True)
                    self.state_at = time.monotonic()
                else:
                    self.events.append(dict(data, local_at=time.time()))
                    if getattr(self,'active_run_manifest',None):
                        self.append_capture_event(self.active_run_manifest,'worker_feedback',feedback=data)
                    if data.get("event") == "disarmed" and not (self.plan_task and not self.plan_task.done()):
                        self.owner = None
                    if data.get("event") == "velocity_ack":
                        accepted = data.get("code") == 0
                        self.pipeline_status = dict(stage="accepted" if accepted else "rejected",
                            message="X2 이동 요청 수락 · 실제 이동은 현장에서 확인하세요." if accepted
                            else "X2이 이동 요청을 거부했습니다.", code=data.get("code"), at=time.time())
                    elif data.get("event") == "arm_request_sent":
                        self.pipeline_status=dict(stage="dispatch",message="팔/사용자 모션 요청 전송 · 전체 동작의 응답을 기다리는 중입니다.",at=time.time())
                    elif data.get("event") == "arm_action_ack":
                        self.pipeline_status = dict(stage="accepted" if data.get("code") == 0 else "rejected",
                            message="X2 팔 동작 요청 응답 · 실제 동작을 확인하세요.", code=data.get("code"), at=time.time())
                    elif data.get("event") == "arm_release_ack":
                        self.pipeline_status = dict(stage="stopped" if data.get("code") == 0 else "rejected",
                            message="X2 팔 복귀 요청 응답 · 실제 복귀를 확인하세요.", code=data.get("code"), at=time.time())
                    elif data.get("event") == "stop_ack" and self.pipeline_status.get("stage") == "accepted" and data.get("code") == 0:
                        self.pipeline_status = dict(stage="stopped", message="X2 0 속도 응답 수신 · 실제 정지를 확인하세요.",
                                                    code=0, at=time.time())
                    elif data.get("event") in ("stop_failed", "rejected"):
                        self.pipeline_status = dict(stage="rejected", message=data.get("error") or "정지 응답을 받지 못했습니다.",
                                                    at=time.time())
                    elif data.get("event") == "mode_ack":
                        self.pipeline_status=dict(stage="accepted" if data.get("code")==0 and data.get("status")==1 else "rejected",
                            message="모드 전환 요청 응답 · 실제 FSM과 자세를 확인하세요.",
                            target_fsm=data.get("target_fsm"),code=data.get("code"),at=time.time())
                    elif data.get("event") == "joint_action_ack":
                        self.pipeline_status = dict(stage="accepted" if data.get("code") == 0 else "rejected",
                            message="X2 관절 요청 응답을 확인하세요.",
                            target_sha256=data.get("target_sha256"), receipt=data.get("receipt"), at=time.time())
                await self.broadcast()
        finally:
            self.owner = None
            self.state.update(connected=False, ready=False, armed=False, moving=False)
            await self.broadcast()

    async def read_errors(self, process=None):
        process = process or self.process
        async for line in process.stderr:
            # SSH diagnostics contain no key material; keep out of browser logs.
            print("X2 SSH:", line.decode(errors="replace").strip(), flush=True)

    async def broadcast(self):
        for ws in list(self.clients):
            with contextlib.suppress(Exception):
                await ws.send_json(dict(type="state", **{k: v for k, v in self.state.items() if k not in ("type","controller","execution_source","events","pipeline_status")},
                    controller="you" if self.owner is ws else "other" if self.owner else "none",
                    execution_source="plan" if self.plan_task and not self.plan_task.done() else "manual" if self.owner else "none",
                    events=list(self.events), pipeline_status=self.pipeline_status))

    async def watchdog(self):
        while True:
            await asyncio.sleep(.1)
            planned=self.plan_task and not self.plan_task.done()
            if self.owner and ((not planned and time.monotonic() - self.owner_beat > 1.0) or
                               time.monotonic() - self.state_at > 1.5):
                await self.cancel_plan()
                self.owner = None
                with contextlib.suppress(Exception):
                    await self.send(dict(action="disarm"))

    async def cancel_plan(self):
        task, self.plan_task = self.plan_task, None
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def run_step(self, ws, action):
        kind = action.get("type", "move")
        if kind == "stop":
            await self.send(dict(action="stop"))
            return
        if kind=="mode":
            await self.send(dict(action="set_mode",mode=action["name"],confirmed=True,condition_confirmed=True))
            return
        if kind in ('gesture','custom_motion'):
            began=time.monotonic()
            await self.progress('dispatch','매핑된 프리셋 한 개를 요청합니다. 실제 종료 확인 전까지 다음 동작을 기다립니다.',
                                kind=kind,command=action['name'])
            await self.send(dict(action=kind,name=action['name'],confirmed=True))
            while self.owner is ws and not ws.closed:
                if self.state.get('error'):raise RuntimeError(self.state['error'])
                if self.state_at>=began and (self.state.get('gesture') or self.state.get('arm_pending')):return
                if time.monotonic()-began>3:raise RuntimeError('프리셋 요청 상태를 확인하지 못했습니다. 현장에서 실제 동작을 확인하세요.')
                await asyncio.sleep(.025)
            return
        end = time.monotonic()+action["seconds"] if action["seconds"] is not None else None
        try:
            await self.progress("dispatch", "X2에 계획의 한 단계를 전달하고 있습니다.",
                                kind=kind, command=action.get("direction") or action.get("name"), seconds=action["seconds"],velocity=action.get("velocity"))
            if kind == "arm_joint_pose":
                raise ValueError("X2 관절 목표는 미리보기만 제공합니다.")
            while (end is None or time.monotonic() < end) and self.owner is ws and not ws.closed:
                if not self.state.get("armed") or self.state.get("error"):
                    raise RuntimeError(self.state.get("error") or "X2 제어가 해제됐습니다.")
                await self.send(dict(action="hold",direction=action.get("direction","vector"),velocity=action["velocity"],burst_seconds=action['seconds']))
                await asyncio.sleep(.08)
        finally:
            with contextlib.suppress(Exception):
                await self.send(dict(action="gesture_release" if kind in ("gesture","custom_motion") else "release"))

    async def run_plan(self,ws,actions):
        try:
            for action in actions:
                if self.owner is not ws or ws.closed:return
                await self.run_step(ws,action)
                if action.get("type")=="stop":return
                if action.get("type") in ("gesture","custom_motion"):
                    # Wait for the native trajectory/release; never overlap base motion.
                    while self.owner is ws and (self.state.get("gesture") or self.state.get("arm_pending")):
                        if self.state.get("error"):raise RuntimeError(self.state["error"])
                        await asyncio.sleep(.05)
                if self.state.get("error"):raise RuntimeError(self.state["error"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.progress("rejected",str(exc))

    async def execute_approved_plan(self,ws,actions):
        """One explicit execute request owns arm -> dispatch -> cleanup on server.

        Browser focus/JavaScript timer throttling does not cancel an approved plan.
        Stop, WebSocket loss and stale robot feedback still cancel it.
        """
        run_manifest=actions[0].get('run_manifest') if actions else None
        self.active_run_manifest=run_manifest
        try:
            began=time.monotonic()
            expected=self.state.get("fsm")
            await self.progress("arming","VLM ready · X2 제어 활성화 후 실행합니다.")
            await self.send(dict(action="arm",confirmed=True,expected_fsm=expected))
            deadline=began+3
            while not (self.state.get("armed") and self.state_at>=began):
                if self.owner is not ws or ws.closed:return
                if time.monotonic()>deadline:raise RuntimeError("X2 제어 활성화 응답을 받지 못했습니다.")
                await asyncio.sleep(.025)
            await self.run_plan(ws,actions)
            if self.owner is ws and self.pipeline_status.get("stage")!="rejected":
                await self.progress("completed","계획 전송·응답 처리 종료 · 실제 동작 결과는 현장에서 확인하세요.")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.progress("rejected",str(exc))
        finally:
            if self.owner is ws:
                with contextlib.suppress(Exception):await self.send(dict(action="disarm"))
                self.owner=None
                await self.broadcast()
            if getattr(self,'active_run_manifest',None)==run_manifest:self.active_run_manifest=None

    async def websocket(self, request):
        origin = request.headers.get("Origin", "")
        expected = self.args.origin or "http://" + request.host
        if origin != expected:
            raise web.HTTPForbidden(text="Same-origin browser required")
        ws = web.WebSocketResponse(heartbeat=.5, max_msg_size=8192)
        await ws.prepare(request)
        self.clients.add(ws)
        await self.broadcast()
        try:
            async for item in ws:
                if item.type != WSMsgType.TEXT:
                    continue
                msg = None
                try:
                    msg = json.loads(item.data)
                    action = msg.get("action")
                    if getattr(self.args,"read_only",False) and action in ("arm","hold","gesture","custom_motion","set_mode","plan_step","plan_execute","joint_execute"):
                        raise ValueError("제어 잠금: 읽기 전용 분석 모드입니다.")
                    if action == "ping":
                        if self.owner is ws:
                            self.owner_beat = time.monotonic()
                        continue
                    if action == "arm":
                        if self.owner and self.owner is not ws:
                            raise ValueError("다른 창에서 제어 중입니다.")
                        if not self.state.get("ready") or (time.monotonic() - self.state_at > 1):
                            raise ValueError("X2 운동제어 상태를 확인하세요.")
                        if msg.get("confirmed") is not True:
                            raise ValueError("현장 준비 확인이 필요합니다.")
                        self.owner, self.owner_beat = ws, time.monotonic()
                        await self.send(dict(action="arm", confirmed=True, expected_fsm=self.state["fsm"]))
                    elif action in ("configure","set_mode"):
                        if self.owner and self.owner is not ws:raise ValueError("다른 창에서 제어 중입니다.")
                        if action=="configure":
                            if self.plan_task and not self.plan_task.done():raise ValueError("계획 실행이 끝난 뒤 설정을 변경하세요.")
                            await self.send(dict(action="configure",profile=validate_profile(msg.get("profile"))))
                        else:
                            if msg.get("mode") not in MODES or msg.get("confirmed") is not True or msg.get("condition_confirmed") is not True:
                                raise ValueError("선택 모드의 자세·지지 조건을 확인하세요.")
                            await self.cancel_plan()
                            await self.send(dict(action="set_mode",mode=msg["mode"],confirmed=True,condition_confirmed=True))
                            self.owner=None
                    elif action == "acknowledge_motion_complete":
                        if msg.get("confirmed") is not True:
                            raise ValueError("현장에서 프리셋 종료를 확인하세요.")
                        await self.send(dict(action=action, confirmed=True))
                        await self.progress('completed','운영자가 실제 프리셋 종료를 확인했습니다.',physical_verification='OPERATOR_ONLY')
                        self.owner = None
                    elif action in ("stop", "disarm", "gesture_release"):
                        await self.cancel_plan()
                        await self.send(dict(action=action))
                        self.owner = None
                    elif action in ("plan_step","plan_execute"):
                        if self.owner and self.owner is not ws:raise ValueError("다른 창에서 제어 중입니다.")
                        if self.owner is not ws and msg.get("confirmed") is not True:
                            raise ValueError("실행 요청의 현장 확인이 필요합니다.")
                        plan=self.plans.get(msg.get("plan_id"))
                        if not plan:raise ValueError("계획을 찾을 수 없습니다. 다시 생성하세요.")
                        if plan["plan_status"]!="ready":
                            raise ValueError("VLM 실행 보류: "+(plan.get("decision_reason") or plan["plan_status"]))
                        if not self.state.get("ready") or (time.monotonic()-self.state_at>1):
                            raise ValueError("X2 운동제어 상태를 확인하세요.")
                        if self.plan_task and not self.plan_task.done():raise ValueError('현재 계획의 처리 또는 종료 확인을 기다리세요.')
                        actions=[dict(a,source_frame=plan.get("frame_id") or plan.get("source"),run_manifest=plan.get('capture_manifest'),
                                      vlm_raw=plan.get("vlm_raw"),
                                      support_confirmed=msg.get("support_confirmed") is True)
                                 for a in plan["actions"]]
                        if any(a.get("type") == "arm_joint_pose" for a in actions):
                            raise ValueError("X2 관절 목표는 미리보기만 제공합니다.")
                        if action=="plan_step":
                            index=msg.get("index")
                            if type(index) is not int or not 0<=index<len(actions):raise ValueError("잘못된 단계입니다.")
                            actions=[actions[index]]
                        requested={msg['index']} if action=='plan_step' else set(range(len(plan['actions'])))
                        if requested & plan['used']:raise ValueError('이미 실행 요청한 계획입니다. 새 계획을 생성하세요.')
                        validate_plan_execution(plan,actions,self.state,time.monotonic()-self.state_at,self.scopes,time.monotonic())
                        self.append_capture_event(plan.get("capture_manifest"),"execution_requested",
                            request_type=action,action_index=msg.get("index") if action=="plan_step" else None,
                            actions=actions,fsm=self.state.get("fsm"))
                        plan['used'].update(requested)
                        await self.cancel_plan()
                        self.owner,self.owner_beat=ws,time.monotonic()
                        self.plan_task=asyncio.create_task(self.execute_approved_plan(ws,actions))
                        await self.broadcast()
                    elif action == "joint_execute":
                        raise ValueError("X2 관절 목표는 미리보기만 제공합니다.")
                    elif action in ("hold", "release", "gesture", "custom_motion"):
                        if self.owner is not ws:
                            raise ValueError("먼저 제어를 활성화하세요.")
                        self.owner_beat = time.monotonic()
                        await self.cancel_plan()
                        if action == "gesture":
                            if msg.get("name") not in self.state.get("arm_actions", {}):
                                raise ValueError("현재 X2에서 조회된 팔 동작이 아닙니다.")
                            await self.send(dict(action="gesture", name=msg["name"], seconds=2.0))
                        elif action=="custom_motion":
                            if msg.get("confirmed") is not True or msg.get("name") not in self.state.get("custom_actions",{}):
                                raise ValueError("현재 등록된 사용자 모션과 전체 동작 공간을 확인하세요.")
                            await self.send(dict(action="custom_motion",name=msg["name"],confirmed=True))
                        else:
                            if action == "hold" and msg.get("direction") not in DIRECTIONS:
                                raise ValueError("잘못된 방향입니다.")
                            outgoing=dict(action=action,direction=msg.get("direction"),reason=str(msg.get("reason","release"))[:80])
                            if action=="hold" and msg.get("velocity") is not None:
                                from capabilities import validate_velocity
                                outgoing["velocity"]=validate_velocity(msg["velocity"])
                            await self.send(outgoing)
                    else:
                        raise ValueError("알 수 없는 요청입니다.")
                except (ValueError, RuntimeError, TypeError, AttributeError) as exc:
                    if isinstance(msg, dict) and msg.get("action") == "plan_step":
                        await self.progress("blocked", str(exc))
                    await ws.send_json(dict(type="error", message=str(exc)))
        finally:
            self.clients.discard(ws)
            if self.owner is ws:
                await self.cancel_plan()
                self.owner = None
                with contextlib.suppress(Exception):
                    await self.send(dict(action="disarm"))
        return ws

    def persist_camera_frame(self, jpeg, meta):
        now = datetime.now(timezone.utc)
        capture_id = now.strftime("%Y%m%dT%H%M%S_%fZ_") + uuid.uuid4().hex[:8]
        output = self.capture_root / capture_id
        output.mkdir(parents=True, exist_ok=False)
        image_path = output / "head_color.jpg"
        image_path.write_bytes(jpeg)
        manifest_path = output / "capture_manifest.json"
        manifest = dict(schema="x2.camera.capture.v1", capture_id=capture_id,
            saved_at_utc=now.isoformat(), source=meta.get("source"),
            sensor_frame=meta.get("sensor_frame"), camera_session=meta.get("camera_session"),
            captured_at=meta.get("captured_at"), image_file=image_path.name,
            bytes=len(jpeg), sha256=hashlib.sha256(jpeg).hexdigest(), events=[])
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return dict(local_capture_id=capture_id,local_capture_dir=str(output),
                    local_image_path=str(image_path),local_manifest_path=str(manifest_path))

    def append_capture_event(self, manifest_path, event, **details):
        if not manifest_path:return
        path=Path(manifest_path)
        try:
            manifest=json.loads(path.read_text(encoding="utf-8"))
            manifest.setdefault("events",[]).append(dict(event=event,at_utc=datetime.now(timezone.utc).isoformat(),**details))
            temporary=path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            temporary.replace(path)
        except (OSError,ValueError,TypeError):
            # Camera logging must not turn a valid stop/control request into motion failure.
            return

    def store_frame(self, jpeg, meta, persist=False):
        while len(self.frames) >= 12:
            self.frames.pop(next(iter(self.frames)))
        frame_id = uuid.uuid4().hex
        frame_meta=dict(meta,captured_at=time.time())
        if persist:frame_meta.update(self.persist_camera_frame(jpeg,frame_meta))
        self.frames[frame_id] = dict(jpeg=jpeg, meta=frame_meta,
                                    created=time.monotonic())
        return dict(frame_id=frame_id, url="/api/frames/" + frame_id + ".jpg", **self.frames[frame_id]["meta"])

    async def capture(self, request):
        raise NotImplementedError("X2 adapter must provide capture")

    async def upload(self, request):
        reader = await request.multipart()
        field = await reader.next()
        if not field or field.name != "image":
            raise ValueError("관점 이미지를 선택하세요.")
        content = bytearray()
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > 6 * 1024 * 1024:
                raise ValueError("이미지는 6MB 이하여야 합니다.")
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 20_000_000:
                raise ValueError("이미지 해상도가 너무 큽니다.")
            image = image.convert("RGB")
            image.thumbnail((1280, 1280))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85)
        return web.json_response(self.store_frame(out.getvalue(), dict(source="Uploaded POV")))

    async def frame(self, request):
        frame = self.frames.get(request.match_info["id"])
        if not frame:
            raise web.HTTPNotFound()
        return web.Response(body=frame["jpeg"], content_type="image/jpeg")

    async def camera_status(self, request):
        raise NotImplementedError("X2 adapter must provide camera_status")

    async def stream(self, request):
        raise NotImplementedError("X2 adapter must provide stream")

    async def infer(self, request):
        if self.infer_lock.locked():
            raise ValueError("이전 VLM 요청을 처리 중입니다.")
        data = await request.json()
        frame = self.frames.get(data.get("frame_id"))
        if not frame and data.get("frame_id"):
            raise ValueError("관점 이미지를 새로 선택하거나 RGB 프레임을 다시 캡처하세요.")
        if not frame:
            frame=dict(jpeg=None,meta=dict(source="Text only",image_available=False,captured_at=time.time()),created=time.monotonic())
        try:recording=begin_run(getattr(self.args,'vlm_record_root',HERE/'artifacts'/'vlm_runs'),frame,data)
        except OSError as e:raise RuntimeError('VLM 입력 기록을 저장하지 못했습니다. 저장 공간과 권한을 확인하세요.') from e
        frame=dict(frame,meta=dict(frame['meta'],local_manifest_path=recording['manifest_path'],vlm_run_id=recording['run_id']))
        fsm = self.state.get("fsm")
        sdk_version=self.state.get('sdk_version')
        profile=dict(self.state.get("profile",DEFAULT_PROFILE))
        lidar = {"enabled":False}
        if data.get("include_lidar") is True:
            raise ValueError("현재 X2에서 수신된 LiDAR 점군이 없습니다.")
        async with self.infer_lock:
            await self.progress("inference", "텍스트와 선택한 관점 이미지를 VLM에 전달했습니다.",
                                model=data.get("model") or self.pipeline.model)
            try:
                result = await self.pipeline.infer(self.session, data.get("instruction"), frame["jpeg"],
                    frame["meta"], dict(fsm=fsm, hand_status=self.state.get("hand_status"), sdk_version=sdk_version, battery_percent=self.state.get("battery_percent"), read_only=self.args.read_only,control_permissions=self.scopes,arm_actions=self.state.get("arm_actions", {}),custom_actions=self.state.get("custom_actions",{}),
                        operator_confirmed=getattr(self.args,"operator_ready",False) or self.owner is not None,
                        lidar=lidar,profile=profile), data.get("model"))
            except PlanValidationError as exc:
                save_json(Path(recording['directory'])/'error.json',dict(error_type='plan_validation',error=str(exc)))
                save_json(Path(recording['directory'])/'model_request.json',self.pipeline.last_request)
                self.append_capture_event(frame["meta"].get("local_manifest_path"),"inference_failed",
                    instruction=data.get("instruction"),model=data.get("model") or self.pipeline.model,
                    execute_requested=data.get("execute_requested") is True,error_type="plan_validation",error=str(exc))
                await self.progress("invalid_plan", "VLM 응답은 받았으나 계획 변환에 실패했습니다: "+str(exc))
                raise
            except Exception as exc:
                save_json(Path(recording['directory'])/'error.json',dict(error_type=type(exc).__name__,error=str(exc)))
                self.append_capture_event(frame["meta"].get("local_manifest_path"),"inference_failed",
                    instruction=data.get("instruction"),model=data.get("model") or self.pipeline.model,
                    execute_requested=data.get("execute_requested") is True,error_type="pipeline",error=str(exc))
                await self.progress("failed", "VLM 요청 실패 · 응답의 오류 내용을 확인하세요.")
                raise
        save_json(Path(recording['directory'])/'model_request.json',self.pipeline.last_request)
        save_json(Path(recording['directory'])/'model_response.json',(self.pipeline.last_request or {}).get('model_response'))
        plan_id = uuid.uuid4().hex
        while len(self.plans)>=12:self.plans.pop(next(iter(self.plans)))
        self.plans[plan_id] = dict(actions=result["actions"], created=time.monotonic(),
            fsm=fsm,sdk_version=sdk_version,used=set(),source=frame["meta"]["source"],frame_id=data.get("frame_id"),frame_created=frame["created"],recording=recording,
            plan_status=result.get("plan_status","blocked"),decision_reason=result.get("decision_reason",""), execution_info=result.get("execution_info", ""),
            capture_manifest=frame["meta"].get("local_manifest_path"),
            vlm_raw=(self.pipeline.last_request or {}).get("model_response"),
            target_sha256=next((a.get("target_sha256") for a in result["actions"]
                                if a.get("type") == "arm_joint_pose"), None))
        self.plans[plan_id]["profile"]=profile
        self.append_capture_event(frame["meta"].get("local_manifest_path"),"inference_completed",
            instruction=data.get("instruction"),model=data.get("model") or self.pipeline.model,
            execute_requested=data.get("execute_requested") is True,plan_id=plan_id,
            plan_status=result.get("plan_status"),decision_reason=result.get("decision_reason"),
            actions=result.get("actions"),sdk_requests=result.get("sdk_requests"))
        has_joint_pose = any(a.get("type") == "arm_joint_pose" for a in result["actions"])
        executable = (bool(result["actions"]) and result.get("plan_status")=="ready" and self.state.get("ready",False)
                      and not getattr(self.args,"read_only",False) and not has_joint_pose)
        if getattr(self.args,"read_only",False):runtime_reason="현재 읽기 전용 분석 모드로 실행이 잠겨 있습니다."
        elif not self.state.get("ready",False):runtime_reason="X2 운동 RPC/운용 모드가 준비되지 않았습니다."
        elif has_joint_pose:runtime_reason="X2 관절 목표는 미리보기만 제공합니다."
        elif result.get("plan_status")!="ready":runtime_reason=result.get("decision_reason") or result.get("explanation") or "VLM이 실행을 승인하지 않았습니다."
        else:runtime_reason=""
        no_action_stage=result.get("plan_status") if result.get("plan_status") in ("unsupported","clarify","blocked","analysis_only") else "no_action"
        no_action_message=(result.get("decision_reason") or result.get("explanation")) if no_action_stage!="no_action" else None
        await self.progress("proposal" if result["actions"] and executable else "blocked" if result["actions"] else no_action_stage,
            "실행 가능한 계획이 생성됐습니다." if result["actions"] and executable
            else "계획은 생성됐지만 실행을 보류했습니다: " + runtime_reason if result["actions"]
            else (no_action_message+" · X2 동작 요청은 보내지 않았습니다.") if no_action_message
            else "VLM이 이동 제안을 생성하지 않았습니다. 아래 판단 이유를 확인하세요. X2 이동 요청은 보내지 않았습니다.",
            actions=len(result["actions"]), explanation=result["explanation"], plan_id=plan_id)
        return web.json_response(dict(result, plan_id=plan_id, frame_id=data.get("frame_id"),
                                      model=data.get("model") or self.pipeline.model,
                                      target_sha256=self.plans[plan_id].get("target_sha256"),
                                      executable=executable, execution_block_reason="" if executable else runtime_reason,
                                      expires_seconds=PLAN_TTL_SECONDS,recording=recording))

    async def config(self, request):
        raise NotImplementedError("X2 adapter must provide config")

    async def capabilities(self, request):
        return web.json_response(dict(catalog=catalog(self.state.get("arm_actions",{}),self.state.get("profile",DEFAULT_PROFILE),self.state.get("custom_actions",{})),
                                      planner_capabilities=planner_catalog(self.state.get("arm_actions",{}),self.state.get("profile",DEFAULT_PROFILE),self.state.get("custom_actions",{}),self.scopes),
                                      joint_contract=joint_catalog(),
                                      system_prompt=runtime_system_prompt(dict(self.state,control_permissions=self.scopes,read_only=self.args.read_only)), fsm=self.state.get("fsm")))

    async def joint_preview(self, request):
        data = await request.json()
        result = preview_joint_pose(data)
        return web.json_response(result)

    async def pipeline_request(self,request):
        return web.json_response(self.pipeline.last_request or dict(provider=self.pipeline.info()["provider"],
            model=self.pipeline.model,messages=[dict(role="system",content=runtime_system_prompt(dict(self.state,control_permissions=self.scopes,read_only=self.args.read_only)))],
            note="아직 전송한 요청이 없습니다. 현재 런타임 시스템 메시지입니다."))

    async def motions(self,request):
        raise NotImplementedError("X2 adapter must provide motions")

    async def lidar_status(self, request):
        raise NotImplementedError("X2 adapter must provide lidar_status")

    async def lidar_frame(self, request):
        raise NotImplementedError("X2 adapter must provide lidar_frame")

    async def lidar_topic(self, request):
        raise NotImplementedError("X2 adapter must provide lidar_topic")

def make_app(dashboard):
    async def index(request):
        return web.FileResponse(HERE / "web" / "index.html")
    async def favicon(request):
        return web.Response(status=204)
    @web.middleware
    async def guard(request, handler):
        hostname = urlsplit("//" + request.host).hostname
        custom = urlsplit(dashboard.args.origin).netloc if dashboard.args.origin else None
        if hostname not in ("localhost", "127.0.0.1", "::1") and request.host != custom:
            raise web.HTTPForbidden(text="Local dashboard only")
        if request.method == "POST":
            expected = dashboard.args.origin or "http://" + request.host
            if request.headers.get("Origin") != expected:
                raise web.HTTPForbidden(text="Same-origin browser required")
        try:
            response = await handler(request)
        except PlanValidationError as exc:
            return web.json_response(dict(error=str(exc),error_type="plan_validation"),status=422)
        except (ValueError, RuntimeError, KeyError, asyncio.TimeoutError) as exc:
            return web.json_response(dict(error=str(exc) or "요청 시간이 초과됐습니다."), status=400)
        except (ConnectionError, OSError):
            return web.json_response(dict(error="로봇 연결을 확인하세요."), status=503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        return response
    app = web.Application(middlewares=[guard], client_max_size=7 * 1024 * 1024)
    app.on_startup.append(dashboard.start)
    app.on_cleanup.append(dashboard.close)
    app.router.add_get("/", index)
    app.router.add_get("/favicon.ico", favicon)
    app.router.add_static("/static/", HERE / "web")
    app.router.add_get("/ws", dashboard.websocket)
    app.router.add_get("/api/config", dashboard.config)
    app.router.add_get("/api/capabilities", dashboard.capabilities)
    app.router.add_get("/api/pipeline/request",dashboard.pipeline_request)
    app.router.add_get("/api/motions",dashboard.motions)
    app.router.add_get("/api/lidar/status", dashboard.lidar_status)
    app.router.add_get("/api/lidar/frame", dashboard.lidar_frame)
    app.router.add_post("/api/lidar/topic", dashboard.lidar_topic)
    app.router.add_get("/api/camera/status", dashboard.camera_status)
    app.router.add_get("/camera/stream/{view}", dashboard.stream)
    app.router.add_post("/api/capture", dashboard.capture)
    app.router.add_post("/api/upload", dashboard.upload)
    app.router.add_post("/api/joints/preview", dashboard.joint_preview)
    app.router.add_get("/api/frames/{id}.jpg", dashboard.frame)
    app.router.add_post("/api/infer", dashboard.infer)
    return app
