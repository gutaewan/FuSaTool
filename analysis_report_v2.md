{
  "Functional Safety Quality Assurance Report": "",
  "Issue Categorization": "Functional Safety Issues",
  "Reported Issues": [
    {
      "Issue ID": "[S-01]",
      "Issue Type": "EngineHealthIssue",
      "Grouped Issue Type": "Condition Structuring Issues",
      "Details": "The following functional safety requirements have missing 'When' conditions within their associated logic: REQ-MCU-04, REQ-ADA-03, REQ-ESP-02, REQ-ADA-08, and REQ-ESP-07. These missing conditions may lead to improper system behavior or failure under specific operating conditions, potentially resulting in safety hazards."
    },
    {
      "Issue ID": "[S-01]",
      "Issue Type": "EngineHealthIssue",
      "Grouped Issue Type": "Condition Structuring Issues",
      "Details": "The missing 'When' conditions within the logic of these functional safety requirements may lead to undesired system behavior or failure, increasing the risk of safety incidents and potential non-compliance with safety standards."
    },
    "Resolutions and Recommendations"
    ]
  }

----------------------------------------

## 📊 Extracted MRS Data

| Req ID | Anchor | Action | When | Constraints | Verification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| REQ-VCU-01 | 가속 페달 센서(APS) | 출력값 차이가 5% 이상 발생하여, VCU는 즉시 토크 출력을 0Nm로 차단해야 한다. | 가속 페달 센서(APS) 1, 2번 채널 간의 출력값 차이가 5% 이상 발생하여, VCU는 즉시 토크 출력을 0Nm로 차단해야 한다. 이 경우는 100ms 이상 지속된다. | 100ms 이상 지속 | - |
| REQ-VCU-02 | Driver, Vehicle | Prioritize brake over accelerate | When driver steps on both gas and brake pedals simultaneously | - | Test |
| REQ-VCU-03 | 차량 | 변속 명령을 무시하고, 현재 기어를 유지해야 한다. | {'condition': '차량 속도가 5kph 이상'} | - | Test |
| REQ-VCU-04 | VCU | enter Limp-home mode, limit speed | E2E communication with monitoring node is interrupted for more than 200ms | 200ms | - |
| REQ-VCU-05 | 에어백 제어기(ACU) | HVIL 회로를 개방한다. | 에어백 제어기(ACU)로부터 충돌 신호(Hard Crash) 수신 시 | 10ms 이내 | - |
| REQ-VCU-06 | 경사로 밀림 방지(HAC) 기능 | 유압 제어 실패 감지 | 경사로 밀림 방지(HAC) 기능 동작 중 | - | Test |
| REQ-BMS-01 | BMS | 차단 | {'Condition or trigger': '어떤 셀이라도 전압이 4.25V를 초과하는 과충전 상태가 1초 이상 지속된다.'} | - | {'How to verify': 'Unknown or not specified.'} |
| REQ-BMS-02 | 배터리 | SOC(충전량)가 5% 이하로 떨어지면, 출력을 제한하여 | 배터리 SOC(충전량)가 5% 이하로 떨어지면 | - | 테스트 |
| REQ-BMS-03 | 배터리 팩 내부 냉각수 누수 센서 | 작동하면, 주기적으로(100ms 간격) 체크하고, 경고등을 점등한다. | 배터리 팩 내부 냉각수 누수 센서가 작동하면 | - | 테스트 |
| REQ-BMS-04 | Car C | Adjust current level | Cell temperature reaches 60 degrees | Within 1 second (FTTI) | Test |
| REQ-BMS-05 | 특정 셀 전압 센서 | 고장(Open/Short) 시, 대체하여 모니터링, 충전 금지 | 특정 셀 전압 센서 고장(Open/Short) | - | Test |
| REQ-MCU-01 | IGBT 접합부 | 모터 출력을 제한하다 | IGBT 접합부 온도(Tj)가 150도를 초과할 경우 | 온도 상승분에 비례하여 선형적으로 | - |
| REQ-MCU-02 | D단(Drive) | 차량이 뒤로 10cm 이상 밀린다., 인버터는 즉시 정방향 토크를 인가한다. | 차량이 뒤로 10cm 이상 밀린 경우 | - | - |
| REQ-MCU-03 | 3상 단락(Phase Short) | 트럭 모터의 높은 역기전력을 고려하여 20ms 이내에 모든 하단 IGBT를 켜는 ASC(Active Short Circuit) 제어 | 3상 단락(Phase Short) 발생 시 | 20ms | - |
| REQ-MCU-04 | 모터 위치 센서(Resolver) | CRC 에러가 연속 3회 발생하며, 토크 제어를 중단하고, 안전 상태로 전환한다. | - | - | - |
| REQ-MCU-05 | 인버터 | DC Link 커패시터의 잔류 전압 방전 | 시동 꺼짐(IG Off) 후 | 5초 이내에 60V 미만으로 | - |
| REQ-ADA-01 | 라이다(Lidar) | 시야가 50% 이상 가려질 경우, 자율주행 기능을 해제하고 운전자에게 제어권을 이양한다. | Occlusion | - | - |
| REQ-ADA-02 | 레이더 시스템 | 제동 보류, AEB 기능 작동 보류 | 레이더 신호 간섭(Jamming)이 의심될 경우 | - | - |
| REQ-ADA-03 | 차선 이탈 방지 보조(LKA) 시스템 | 생성하는 조향 토크 | - | {'초과': '3Nm'} | - |
| REQ-ADA-04 | Autonomous Emergency Braking (AEB) | Send deceleration request to VCU, Perform independent braking | AEB activation decision is made | Within 50ms response (Ack) from VCU | Test |
| REQ-ADA-05 | 주차 보조 시스템 | 데이터 무시 | 초음파 센서 데이터가 유효 범위를 벗어난 경우 | - | - |
| REQ-ADA-06 | 카메라, 레이더 | 퓨전 데이터 불일치(Noise), Fail-safe 경고 띄우기, 기능 비활성화 | 카메라와 레이дер 간의 퓨전 데이터 불일치(Noise)가 임계치를 넘으면 | - | 테스트 |
| REQ-ESP-01 | 운전자, ABS 펌프 | 가동하여, 브레이크 압력을 증감 | when the emergency braking is triggered (급제동 시) | {'frequency': '초당 10회 이상'} | - |
| REQ-ESP-02 | SUV 차량의 전복(Rollover) | 감지되면, 가하여 차량 자세를 안정화한다. | - | - | - |
| REQ-ESP-03 | Wheel speed sensor | Hold the brake pressure, Limit ABS function | During a short circuit (single wire) of the wheel speed sensor | - | Test |
| REQ-ESP-04 | 트레일러 | 감지 시, 좌우 바퀴에 비대칭 제동력을 가한다., 진동을 억제한다. | 트레일러 연결 상태에서 | - | - |
| REQ-ESP-05 | 통신 지연으로 인해 상위 제어기 | EBD(전자식 제동력 배분) | 통신 지연으로 인해 상위 제어기 지령을 받지 못할 경우 | - | - |
| REQ-VCU-07 | VCU | 제한하다(토크 요구), 활성화하다(운전자 경고) | {'condition': 'BPS 신호가 100ms 동안 유효하지 않거나 범위를 벗어난다.'} | {'time': '150ms'} | Test |
| REQ-ADA-07 | ADAS_Main | send AEB braking request to VCU, ignore request, transition to backup braking mode | sending a message to VCU | - | check CRC and message counter of sent messages, verify backup braking mode activation |
| REQ-BMS-06 | BMS | reduce, charging current | in case of overheating concern | - | - |
| REQ-VCU-08 | VCU | open HVIL | collision signal received | 50ms or less | - |
| REQ-VCU-09 | HAC (경사로 밀림 방지) 기능 | 차량 구동을 제한 | {'type': 'condition', 'value': '유압 제어 실패가 감지된다.'} | - | - |
| REQ-ESP-06 | ESP, VCU | 유지, 비활성화 | 차량 속도 신호가 100ms 이상 갱신되지 않을 경우 | 500ms까지만 | - |
| REQ-ADA-08 | ADAS_Main | 유지, 객체 인식 주기를 40ms 이하로 유지, 카메라 프레임 버퍼를 3프레임으로 저장(링 버퍼) | - | 40ms 이하 | Test |
| REQ-ADA-09 | 레이더, AEB | 작동 | 보행자 충돌 위험이 감지되면 | - | - |
| REQ-BMS-07 | BMS, VCU | receive Charge_Enable signal, close charging relay | When receiving the Charge_Enable signal from VCU | {'duration': '200ms'} | Inspection |
| REQ-ADA-10 | 시스템 | 조인 개입 | 조향 보조 기능이 활성화된 경우 | - | - |
| REQ-ESP-07 | ABS | control brake pressure | - | 10 times per second | - |

> **Note**: 'Anchor' and 'Action' fields may contain multiple values separated by commas.
