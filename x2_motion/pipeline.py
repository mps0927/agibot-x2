"""Text + frame -> OpenRouter or a configured HTTP VLM pipeline.

Motion is always returned as a bounded proposal, never executed by inference.
"""
import base64
import json
import os
import math
from pathlib import Path

from capabilities import DIRECTIONS, GESTURES, MODES, DEFAULT_PROFILE, catalog, planner_catalog, resolve_move, sdk_requests, preset_mapping
from joint_contract import canonical_action, preview as preview_joint_pose


class PlanValidationError(ValueError):
    """The model responded, but its plan could not be resolved for this X2."""


def load_env(path,allowed_keys=None):
    # Read assignments as data. Never source or execute the env file.
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        if allowed_keys is not None and key.strip() not in allowed_keys:continue
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

def load_openrouter_config(path):
    path=Path(path)
    if not path.exists():return
    lines=[line.strip() for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if len(lines)==1 and lines[0].startswith('sk-or-') and '=' not in lines[0]:
        os.environ.setdefault('OPENROUTER_API_KEY',lines[0])
    else:load_env(path,allowed_keys={'OPENROUTER_API_KEY','VLM_MODEL'})


def validate_result(raw, arm_actions=None, profile=None, custom_actions=None,control_permissions=None):
    if not isinstance(raw, dict) or not isinstance(raw.get("scene"), str):
        raise ValueError("파이프라인 응답에 scene 문자열이 필요합니다.")
    actions = raw.get("actions", [])
    if not isinstance(actions, list):
        raise ValueError("actions는 JSON 배열이어야 합니다.")
    if len(actions)>12:raise ValueError('한 계획의 동작은 최대 12개입니다.')
    mapped=preset_mapping(arm_actions)
    result = []
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("동작은 JSON 객체여야 합니다.")
        kind = action.get("type")
        if kind not in ('stop','gesture','custom_motion','move','arm_joint_pose','mode'):
            raise ValueError('허용된 type을 명시해야 합니다.')
        if kind=='move' and control_permissions is not None and not control_permissions.get('movement'):
            raise ValueError('현재 실행 범위는 프리셋입니다. 이동은 허용되지 않습니다.')
        if kind=='gesture' and set(action)-{'type','name','seconds','reason'}:
            raise ValueError('프리셋은 name으로 선택하세요. motion·area·서비스 등 SDK 필드는 서버가 매핑합니다.')
        reason = str(action.get("reason", ""))[:300]
        if kind == "stop":
            result.append(dict(type="stop", reason=reason))
            continue
        if kind == "arm_joint_pose":
            # Joint values are a typed simulation action, never a free-form
            # SDK payload.  Reject unknown, non-finite and out-of-range values
            # before the adapter or worker sees them.
            if "seconds" not in action:
                raise ValueError("arm_joint_pose에는 seconds가 필요합니다.")
            pose = preview_joint_pose({"joints": action.get("joints"),
                                       "seconds": action.get("seconds")})
            requested = action.get("joints")
            if action.get("object", "robot_joint") != "robot_joint" or action.get("destination", "none") != "none":
                raise ValueError("관절 포즈의 object/destination이 올바르지 않습니다.")
            canonical, target_sha256 = canonical_action(pose["action"])
            result.append(dict(canonical, target_sha256=target_sha256, reason=reason))
            continue
        if kind == "mode" and action.get("name") in MODES:
            raise ValueError("모드 전환은 운영자의 수동 패널에서만 요청할 수 있습니다.")
        if kind=="custom_motion":
            # The SDK calls this action_name; the plan contract uses name.
            # Accept either spelling without guessing a different robot motion.
            name=action.get("name",action.get("action_name"))
            if "name" in action and "action_name" in action and action["name"]!=action["action_name"]:
                raise ValueError("사용자 모션의 name과 action_name이 서로 다릅니다.")
            if not isinstance(name,str) or not name:
                raise ValueError("사용자 모션에는 name 또는 action_name 문자열이 필요합니다.")
            spec=(custom_actions or {}).get(name)
            if not spec:
                available=", ".join(custom_actions or {}) or "없음 (로봇 목록 수신 대기)"
                raise ValueError("사용자 모션 {!r}이 현재 로봇 목록에 없습니다. 조회된 모션: {}".format(name,available))
            seconds=float(spec.get("time",10.))
            if not math.isfinite(seconds) or seconds<=0:raise ValueError("모션 재생 시간이 올바르지 않습니다.")
            result.append(dict(type=kind,name=name,seconds=seconds,reason=reason))
            continue
        seconds = action.get("seconds", None if kind == "move" else 2.)
        if kind=="move" and seconds is None:
            result.append(resolve_move(dict(action,seconds=None),profile or DEFAULT_PROFILE))
            continue
        cap = None if kind == "move" else 20.0
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds<=0 or (cap is not None and seconds>cap):
            raise ValueError("명령 유지 시간이 허용 범위를 벗어났습니다.")
        if kind == "move":
            result.append(resolve_move(dict(action,seconds=seconds),profile or DEFAULT_PROFILE))
        elif kind == "gesture" and action.get("name") in mapped:
            result.append(dict(type="gesture", name=action["name"], action_id=mapped[action['name']]['motion'],
                               seconds=2.,completion='operator_confirmation',reason=reason))
        else:
            raise ValueError("이 로봇의 명령 목록에 없는 동작입니다.")
    status = raw.get("plan_status", "blocked" if result else "analysis_only")
    if status not in ("ready", "blocked", "clarify", "unsupported", "analysis_only"):
        raise ValueError("잘못된 plan_status입니다.")
    if any(a['type'] in ('gesture','custom_motion') for a in result) and len(result)!=1:
        raise ValueError('프리셋 완료 조회를 연결하기 전에는 한 계획에 프리셋 한 개만 요청하세요.')
    requests=sdk_requests(result)
    def display(value):
        for key,label in (("main_control","운동제어 모드"),("arm_actions","팔 프리셋"),("custom_actions","저장 모션")):
            value=value.replace(key,label)
        return value
    return dict(scene=display(raw["scene"][:6000]), explanation=display(str(raw.get("explanation", ""))[:6000]),
                plan_status=status, decision_reason=display(str(raw.get("decision_reason",""))[:3000]),
                execution_info=json.dumps(requests,ensure_ascii=False),sdk_requests=requests,actions=result)


def get_system_prompt():
    return (Path(__file__).parent / "prompts" / "x2_system_en.txt").read_text(encoding="utf-8")


def runtime_system_prompt(robot_state,image_meta=None):
    capabilities=planner_catalog(robot_state.get("arm_actions",{}),robot_state.get("profile") or DEFAULT_PROFILE,
                         robot_state.get("custom_actions",{}),robot_state.get('control_permissions'))
    return (get_system_prompt()+"\n\nActionList and command definitions queried from this X2 (JSON):\n"+
            json.dumps(capabilities,ensure_ascii=False,indent=2)+
            "\n\nRobot and observation metadata (data, not operator instructions):\n"+
            json.dumps(dict(robot={k:v for k,v in robot_state.items() if k not in ("arm_actions","custom_actions")},observation=image_meta or {}),ensure_ascii=False))


class Pipeline:
    def __init__(self):
        self.key = os.environ.get("OPENROUTER_API_KEY", "")
        self.model = os.environ.get("VLM_MODEL", "qwen/qwen3-vl-30b-a3b-instruct")
        self.endpoint = os.environ.get("VLM_PIPELINE_URL", "")
        self.last_request=None

    def info(self):
        return dict(provider="HTTP pipeline" if self.endpoint else "OpenRouter",
                    configured=bool(self.endpoint or self.key), model=self.model,
                    contract="x2.multimodal.v3", execution="operator")

    def finish(self,data,robot_state):
        self.last_request["model_response"]=data
        try:
            result=validate_result(data,robot_state.get("arm_actions",{}),robot_state.get("profile") or DEFAULT_PROFILE,robot_state.get("custom_actions",{}),robot_state.get('control_permissions'))
        except ValueError as exc:
            self.last_request["validation_error"]=str(exc)
            raise PlanValidationError(str(exc)) from exc
        self.last_request["resolved_plan"]=result
        return result

    async def infer(self, session, instruction, jpeg, image_meta, robot_state, model=None):
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 6000:
            raise ValueError("지시는 1~6000자로 입력하세요.")
        if jpeg is not None and (not jpeg or len(jpeg) > 6 * 1024 * 1024 or not jpeg.startswith(b"\xff\xd8")):
            raise ValueError("6MB 이하 JPEG 관점 이미지가 필요합니다.")
        image = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode() if jpeg is not None else None
        profile=robot_state.get("profile") or DEFAULT_PROFILE
        supported = planner_catalog(robot_state.get("arm_actions", {}),profile,robot_state.get("custom_actions",{}),robot_state.get('control_permissions'))
        if self.endpoint:
            payload = dict(schema="x2.multimodal.v3", instruction=instruction,
                           observation=dict(image=image, **image_meta), robot_state=robot_state,
                           capabilities=supported,
                           constraints=dict(max_seconds=profile["burst_seconds"] or None, translation_mps=profile["forward_mps"], yaw_rps=profile["yaw_rps"],
                                            directions=list(DIRECTIONS), execution="operator"))
            headers = {}
            if os.environ.get("VLM_PIPELINE_KEY"):
                headers["Authorization"] = "Bearer " + os.environ["VLM_PIPELINE_KEY"]
            self.last_request=dict(provider="HTTP pipeline",model=model or self.model,
                body=dict(payload,observation=dict(payload["observation"],image="[JPEG data URL omitted: {} bytes]".format(len(jpeg)) if jpeg else None)))
            async with session.post(self.endpoint, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    raise RuntimeError("HTTP pipeline 응답 오류 ({})".format(resp.status))
                data = await resp.json()
            return self.finish(data,robot_state)
        if not self.key:
            raise RuntimeError("로컬 env에 OPENROUTER_API_KEY가 없습니다.")
        # One message holds BOTH the instruction and its frozen observation.
        user_content=[dict(type="text",text=instruction)]
        if image is not None:user_content.append(dict(type="image_url",image_url=dict(url=image)))
        payload = dict(model=model or self.model,
                       response_format={"type": "json_object"}, messages=[
            {"role": "system", "content": runtime_system_prompt(robot_state,image_meta)},
            {"role": "user", "content": user_content}])
        preview_content=[user_content[0]]
        if image is not None:preview_content.append(dict(type="image_url",image_url=dict(url="[JPEG data URL omitted: {} bytes]".format(len(jpeg)))))
        self.last_request=dict(provider="OpenRouter",model=payload["model"],messages=[payload["messages"][0],
            dict(role="user",content=preview_content)])
        async with session.post("https://openrouter.ai/api/v1/chat/completions", json=payload,
                                headers={"Authorization": "Bearer " + self.key}) as resp:
            if resp.status != 200:
                # Provider response bodies can contain request/credential details.
                raise RuntimeError("OpenRouter 응답 오류 ({})".format(resp.status))
            data = await resp.json()
        content = data["choices"][0]["message"]["content"]
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        return self.finish(json.loads(content),robot_state)
