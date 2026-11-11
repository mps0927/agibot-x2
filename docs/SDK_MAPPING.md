# SDK 연결 범위

| 기능 | ROS 인터페이스 / 요청 |
|---|---|
| 현재 모드 | `GetMcAction` |
| 관절 상태 | `GetAllJointState` 및 HAL JointStateArray |
| 사용자 모션 | `GetRobotResources` → `ExecuteActionResource` |
| 제어 소스 | `GetCurrentInputSource` / `SetMcInputSource` |
| 기립·착석·모드 | `SetMcAction.command.action_desc` |
| 프리셋 | `SetMcPresetMotion.motion.value / area.value / interrupt=false` |
| 이동·회전 | `/aima/mc/locomotion/velocity` (`McLocomotionVelocity`) |
| 손·시스템·음량 조회 | `GetHandType`, `GetSystemState`, `GetVolume`, `GetMute` |
| 카메라 | `/aima/hal/sensor/rgb_head_front_center/rgb_image/compressed` |
| 배터리·IMU | `/aima/hal/pmu/state`, `/aima/hal/imu/torso/state` |

`/api/action-map`은 실제 연결 상태의 동작 매핑, `/api/sdk-map`은 전체 서비스 스키마 27개와 토픽 이름 35개 및 연결 범위를 반환한다. 서비스 12개는 실행/조회 처리기에 연결했고 음성·표정·지도·시스템 관리 등 나머지는 스키마와 미연결 이유를 표시한다.

기준 설치 SDK의 프리셋은 17개 조합이 정확히 매핑된다. 공식 문서에만 있거나 제어 영역이 불확실한 항목은 UI/VLM 목록에서 제외한다. 연결한 로봇에 설치된 SDK에서 지원 목록을 다시 확인하고, 문서의 동작과 제어 영역이 일치하는 항목을 매핑한다.

| 자세 | action_desc | 준비 모드 | 완료 모드 |
|---|---|---|---|
| 착석 자세 고정 | `SIT_JOINT_DEFAULT` | 이미 착석한 영토크·댐핑 | `SIT_JOINT_DEFAULT` |
| 의자 기립 | `SIT_UP_DEFAULT` | `SIT_JOINT_DEFAULT` | `STAND_DEFAULT` |
| 의자 착석 | `SIT_DOWN_DEFAULT` | `STAND_DEFAULT` | `SIT_JOINT_DEFAULT` |

의자 기립에 구형 숫자 `STAND_UP_DEFAULT=2005`를 사용하지 않는다. SDK 소스에서 이 값은 누운 자세 기립이다. 현재 문자열 매핑은 기기의 MC/RC 로그에서 확인한 전환 경로를 따른다.

SDK 수락은 물리 동작 완료가 아니다. 프리셋 완료 조회 바인딩이 없어 운영자의 종료 확인이 필요하며 한 계획에는 내장 프리셋 하나만 포함한다. 생성 후 30초가 지난 계획, 모드·SDK 버전·매핑이 바뀐 계획과 이미 요청한 계획은 재사용하지 않는다.
