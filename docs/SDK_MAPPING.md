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
| 라이다 점군 | `/aima/hal/sensor/lidar_chest_front/lidar_pointcloud` (`sensor_msgs/msg/PointCloud2`) |
| 배터리·IMU | `/aima/hal/pmu/state`, `/aima/hal/imu/torso/state` |

`/api/action-map`은 실제 연결 상태의 동작 매핑, `/api/sdk-map`은 전체 서비스 스키마 27개와 토픽 이름 35개 및 연결 범위를 반환한다. 서비스 12개는 실행/조회 처리기에 연결했고 음성·표정·지도·시스템 관리 등 나머지는 스키마와 미연결 이유를 표시한다.

기준 설치 SDK의 프리셋은 17개 조합이 정확히 매핑된다. 공식 문서에만 있거나 제어 영역이 불확실한 항목은 UI/VLM 목록에서 제외한다. 연결한 로봇에 설치된 SDK에서 지원 목록을 다시 확인하고, 문서의 동작과 제어 영역이 일치하는 항목을 매핑한다.

| 자세 | action_desc | 준비 모드 | 완료 모드 |
|---|---|---|---|
| 착석 자세 고정 | `SIT_JOINT_DEFAULT` | 이미 착석한 영토크·댐핑 | `SIT_JOINT_DEFAULT` |
| 의자 기립 | `SIT_UP_DEFAULT` | `SIT_JOINT_DEFAULT` | `STAND_DEFAULT` |
| 의자 착석 | `SIT_DOWN_DEFAULT` | `STAND_DEFAULT` | `SIT_JOINT_DEFAULT` |

의자 기립에 구형 숫자 `STAND_UP_DEFAULT=2005`를 사용하지 않는다. SDK 소스에서 이 값은 누운 자세 기립이다. 현재 문자열 매핑은 기기의 MC/RC 로그에서 확인한 전환 경로를 따른다.

모션 요청은 SDK 응답까지 추적하고 응답 후 요청 잠금을 자동으로 해제한다. SDK 요청 수락과 실제 동작 완료는 구분하며, 한 계획에는 내장 프리셋 하나만 포함한다. 생성 후 30초가 지난 계획, 모드·SDK 버전·매핑이 바뀐 계획과 이미 요청한 계획은 재사용하지 않는다.

이동은 `/aima/mc/locomotion/velocity`에 50 Hz로 발행한다. 기본 전후 속도는 설치 SDK의 `mc_locomotion_velocity.cpp` 예제를 따라 0.20 m/s로 설정한다. 명시적으로 요청한 속도는 유지한다. 제조사 안내에 따르면 기동 임계값은 펌웨어와 모델에 따라 달라진다. [이동 제어 문서](https://x2-aimdk.agibot.com/en/latest/Interface/control_mod/locomotion.html)를 참고한다.

안정 서기에서 시작한 속도 명령은 자동 보행 전환(`LOCOMOTION_DEFAULT`, 상태 200) 중에도 최대 2초 이내에서 이어 보낸다. 새 이동과 제어 활성화는 상태 100에서 시작한다. 기존 누름 시간 상한, 300ms 입력 만료, 최신 모드 확인과 정지 처리는 계속 적용한다.

라이다는 개발 보드의 PointCloud2를 구독하고 기존 SSH 연결로 대시보드에 전달한다. `/api/lidar/status`에서 연결·토픽·발행자·수신 상태를 조회하고, `/api/lidar/frame`에서 최대 3,000점의 최신 표본을 받는다. 워커가 실제 발행자가 있는 LiDAR 점군을 자동 선택한다. VLM 요청에 포함한 점군 요약과 표본은 해당 요청 폴더에 함께 저장한다. 센서 좌표의 표본이며 RGB와 시간 동기화하거나 로봇 기준 좌표로 변환하지 않는다.

`/api/sensors`는 위치·데이터 종류·발행자·최신 값·수신 속도를 제공한다. `/api/camera/select`는 조회된 영상 소스 중 하나로 전환하며 로봇 동작 명령을 보내지 않는다. SDK 메시지 정의가 없는 데이터는 해당 이유를 표시한다.

직접 ROS 그래프에서 보이지 않는 센서는 PC2에 기본 실행된 coBridge의 로컬 21274 포트를 읽기 전용으로 구독한다. 이 연결도 로봇 내부에서 처리하고 기존 SSH로 표본·영상·현재 값만 전달하므로 PC 대시보드 포트는 8766 하나다. 외부 메시지 발행·서비스 호출·파라미터 변경은 브리지 클라이언트에 구현하지 않는다. 설치 SDK에 없는 일부 상태 형식은 브리지가 제공한 ROS 메시지 설명으로 제한된 CDR1 해석을 수행한다.
