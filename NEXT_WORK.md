# 다음 작업 (2026-08-31 후반 기준)

> **문서 지도 — 이 문서의 역할과 다른 3개 문서와의 관계**
> 이 문서는 **현재 상태와 다음에 할 일**만 담는다 — 최신 회귀 결과, 이번 회차에 바꾼 것, 남은 문제, P0/P1/P2, **사용자 판단이 필요한 항목(5절)**, 다음 세션용 프롬프트(6절).
> **영구 규칙**은 `AGENTS.md`, **영구 구현 규칙과 사고 이력**은 `..\지식\[자동화 운영 지침] ...md` 에 있다. 과거에 실측으로 확정한 컨트롤 ID·제품 동작은 **코드 상수·docstring** 과 `automation_scope.json` / `traceability.json` 에 있고, 그 경위는 `git log` 로 찾는다(2026-08-28 부로 `NEXT_TASK.md` 는 폐지).
> **읽는 순서 — `README.md` 최상단 "온보딩 요약" → `AGENTS.md` → 이 문서 → `[자동화 운영 지침]`(상단 "증상 → 원인 → 조치" 색인부터).**

---

## 1. 현재 상태

| 항목 | 값 | 근거 |
|---|---|---|
| 기준 문서 | `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC` — TC 37건 | `WF_14` Step 3 문구는 2026-08-28 사용자 승인으로 수정(원본은 `..\Baseline\Checklist_개정본_20260828_WF14Step3수정전.xlsx`) |
| 자동화 범위 | 완전자동 20 / 부분자동 7 / 수동 10 (+ 보조 4) | `python run.py list` |
| **최신 전체 회귀** | 26차, 2026-08-26 18:52~20:28 — TC 27건: PASS 22 / FAIL 2 / MANUAL 2 / BLOCKED 1, 검증 275개: PASS 261 / FAIL 7 / MANUAL 3 / SKIP 1 / BLOCKED 3, 96.3분. 남은 FAIL 2건은 둘 다 제품 결함 | `Reports/Result_20260826_202818.json` |
| 문서 구조 | `AGENTS.md`/`README.md`/`NEXT_WORK.md`/`..\프로젝트_상세.md` 4개로 유지. `NEXT_TASK.md`·`PORTABILITY_AUDIT.md`·`tools/prune_docs.py` 는 2026-08-28 폐지(아래 2절) | `AGENTS.md` "문서 수명 정책" |
| **08-28 이후 전체 회귀 미실행** | 08-28~09-01 수정 사항 중 `WF_07`/`XIPL_04`(2-C절)·`WF_10`(2-D절)·`cold_start` 모니터 가드(2-E절)·`WF_14` 목록 열거(9개 페이지 전부 해결, 2-D~2-J절)는 개별 라이브 검증 완료. `WF_04→06`/`WF_13`/`WF_15` 재검증이 남아 그 뒤 전체 회귀 재실행 예정(4절 참고) | — |
| **실행 PC 변경(08-31)** | 이식성 시험 겸 **다른 PC**(`HOST=ADMIN`, 프로필 `C:\Users\ksj74`)로 옮겨 수행했다. 이전 PC를 막던 화면 잠금·로그인 실패는 **이 PC에서 재현되지 않았다** — `portability-check` PASS(관리자 True, 1920x1080/96DPI, 필수 경로 4종, DB 서비스 RUNNING), 잠금 화면 창 없음, `cold_start` 로그인 정상, DICOM 서버 5개 포트 모두 도달 | 아래 2-C절 |

---

## 2. 2026-08-28 회차 — 버그 수정 및 문서 구조 정리

### 코드 수정 (검증 상태 포함)

| 수정 | 내용 | 검증 |
|---|---|---|
| `WF_04` 종료 시 View 닫기 | `flows.close_view_study` 추가. `WF_04`가 View 로 연 검사를 닫지 않고 끝나 뒤따른 `WF_06`이 Examined 검색 컨트롤(2177/2178/2179)을 못 찾던 문제 | 코드 반영. `run-wf04`→`run-wf06` 연쇄 재검증 대기 |
| 로그인 ID 콤보 견고화 | `flows.select_login_id` — OCR 선택 실패 시 항목을 하나씩 눌러 `current_login_id()`로 확인하며 재시도(`_click_general_param_combo`와 같은 방식) | 코드 반영. `run-wf13` 재검증 대기 |
| `XIPL_04` 2D Default Parameter 원복 | Step 1 이 바꾼 `PROCEDURE_COMMON.DefaultImgProcess` 를 `finally`에서 UI로 원복(`_restore_default_2d_param`) | **`run-xipl-04` 전 Step PASS, 원복도 `Standard_Default_M.pim`으로 확인(2026-08-28)** |
| `XIPL_05` Q.C 채점을 좌표 대신 임계값으로 | 화면 절대좌표 대신 `CONFIGURATION.QC_COMMON`의 합격 기준을 DB로 읽어 OCR로 경계값을 고르고, 합격/불합격 경계 양쪽을 검증(5절 ① 판단 반영 — Result는 별도 항목으로 분리) | **PASS(MANUAL 1) 확인(2026-08-28 재검증).** Step 3~5 전부 PASS. Fiber 콤보에 기준(4.0) 미만 항목 자체가 없어 불합격 경계 하나만 MANUAL — 자동화 결함이 아니라 콤보 항목 구성의 한계(3절 #1) |
| `WF_15` Dose Overlay 전제 자체 보장 | 단독 실행 시 `WF_03`을 거치지 않으면 선량 Overlay(115/118)가 없어 Step 3 이 전제 미충족으로 FAIL 하던 것을, `vp.add_image_overlay_items`로 멱등하게 준비 | 코드 반영. `run-wf15` 단독 실행 재검증 대기 |
| `core/ui.py` 포그라운드 잠금 타임아웃 | `force_foreground`가 `SPI_FOREGROUNDLOCKTIMEOUT`을 0으로 낮췄다가 복원 — 잠금이 남아 있으면 `AttachThreadInput`을 붙여도 전환이 거부됨 | 코드 반영 |
| `core/ui.py` 클릭 가드 — 다중 모니터 겹침 인식 | `require_front_for_pointer`가 "다른 창이 최전면"이라는 사실만으로 막던 것을, **그 창이 클릭 좌표를 실제로 화면에서 덮고 있는지**까지 확인하도록 바꿈(`_rect_contains_point`). 다른 모니터의 창은 Viewer를 가리지 않으므로 막지 않는다(2026-08-28 사용자 지시) | `run-xipl-05` 재검증으로 확인 |
| `core/ui.py` `bring_to_front`가 항상 메인 프레임만 올리던 문제 | Q.C 테스트 창처럼 메인 프레임과 다른 최상위 창을 조작 중일 때, 최전면 복구가 메인 프레임을 올려 오히려 그 창을 가리는 문제를 고침 — 클릭 좌표를 실제로 담고 있는 창(`_window_at_point`)을 우선 올린다 | `run-xipl-05` 재검증으로 확인 |
| `tests/xipl_flows.py` `_qc_recover` 1회 클릭 → 재시도 루프 | Q.C 콤보 팝업이 마우스를 잡고 있을 때 첫 클릭이 Cancel이 아니라 팝업만 닫아, 창이 안 닫힌 채 남던 문제. Cancel이 안 보일 때까지(최대 3회) 반복 | `run-xipl-05` 재검증으로 확인 — 이제 Step 4·5까지 정상 진행 |
| `WF_10` 비기본 Procedure 매핑 | Hospital Code `HC`를 기본값 `Routine Mammography` 대신 `Mammography (Rt)`에 매핑한다. 기본값 사용 시 매핑 실패가 제품 기본값으로 가려질 수 있어 거짓 PASS를 막기 위한 변경 | 코드 반영. `run-wf10`으로 MappingKey, Study ProcedureKey, Step 수와 Examine 준비 상태 재검증 대기 |
| `cold_start` 주 모니터 이탈 중단 | Viewer 창이 주 모니터 좌표 범위 밖이면 강제 이동하지 않고 오류로 중단한다. 다중 모니터/DPI 가상화에서 자동 이동이 잘못된 모니터로 창을 옮긴 사례를 방지 | **2026-08-31 라이브 검증 완료(2-E절).** 검증 중 재사용 경로가 이 검사를 건너뛴다는 결함이 드러나 `flows.require_primary_monitor()`로 공용화해 고쳤다 |
| 로그인 전용 스모크 도구 | `_login_check.py`가 TC 수행 없이 `cold_start()`를 1회 호출해 Viewer 실행·로그인만 확인 | 코드 반영. 위 창 위치 보호 로직의 좁은 스모크 검증에 사용 가능 |

### 중단된 전체 회귀

- 2026-08-28 15:16경 `python tools/run_regression.py`로 전체 회귀를 시작했으나 세션 만료 후
  사용자 요청으로 감시 프로세스와 `run.py run-regression` 자식 프로세스를 종료했다.
- 종료 직전 생성물 메타데이터는 `Evidence/Flow/14_Setting` 갱신을 보이지만 완료 리포트가
  아니므로 `WF_14` 완료/PASS나 새 전체 회귀 결과로 기록하지 않는다.
- 아래 미검증 변경을 개별 검증한 뒤 전체 회귀를 처음부터 다시 실행해야 한다.

### 문서 구조 정리 (2026-08-28)

- **`NEXT_TASK.md`(542줄) 삭제.** 절별로 코드 대조해 실측 지식(컨트롤 ID·DB 구조·`.img` 구조 등)이 이미 `core/flows.py`, `core/imginfo.py`, `core/export_manager.py`, `tests/xipl_flows.py`, `automation_scope.json`에 옮겨져 있음을 확인한 뒤 지웠다. Dose SR MANUAL 사유 등 일부 내용은 이미 아래 3절/1-F(git 이력)로 대체돼 있었다.
- **`PORTABILITY_AUDIT.md` 삭제.** 아무 문서·코드도 참조하지 않는 고아 파일이었고, 내용은 `README.md` "다른 PC로 옮길 때" 절에 이미 반영돼 있었다.
- **`tools/prune_docs.py` 삭제.** "끝난 기록을 `Archive/`로 내린다"는 옛 정책 도구인데, 새 정책("문서는 4개로 유지, 완료 기록은 git 이력에 맡긴다")으로 대체됐다. 이미 내려간 `Archive/*.md` 2개는 과거 기록으로 그대로 둔다.
- `tests/workflow13.py`의 `NEXT_TASK.md` 참조를 이 문서 5절로 옮겼다.

---

## 2-B. 2026-08-29~31 회차 — 자동화 구조 리팩터링과 병목 실측 (이번 세션 핵심)

### 병목 실측 (추측 아님 — 26차 회귀 로그 분석)

26차 전체 회귀 리포트(`Reports/Result_20260826_202818.json`, 96.3분/27 TC)의 TC별·Step별
`duration_seconds`를 분석해 실제 병목 순위를 확보했다.

- TC 총시간 순위(내림차순): `WF_14` 1068초(FAIL) > `WF_03` 500초 > `XIPL_07` 424초 >
  `WF_13` 348초 > `WF_02` 324초 > `XIPL_04` 319초 > `WF_09` 269초 > `WF_10` 231초 >
  `WF_07` 210초 > `XIPL_05` 206초 ...
- **`NEXT_WORK.md`(이 문서)에 08-28까지 적혀 있던 "`flows.demo_acquire_step(settle=14)`가
  `WF_01`/`WF_02`/`run-sys3d`에 남아 있다"는 서술은 구식이었다.** 실제로 확인해 보니
  `WF_02`는 이미 `settle=0` + DB 폴링(`_wait_types`, 상태 기반)으로 바뀌어 있었다. 회귀에
  실제로 고정 대기가 남아 있던 곳은 `WF_07`(`tests/workflow07.py` Step 4)과
  `XIPL_04`(`tests/xipl_flows.py::compatibility_04`) 두 곳뿐이었다. `run-sys3d`(명시적
  settle=20)와 `run-ui`/`run-auto`는 애초에 **회귀에 포함되지 않는 별도 명령**이다.

### 코드 리팩터링

| 변경 | 내용 | 검증 상태 |
|---|---|---|
| 공용 DB 폴링 헬퍼 신설 | `core/flows.py::instance_type_counts`/`wait_instance_types` 추가. `tests/workflow02.py`와 `tests/system_compat.py`가 각자 들고 있던 **완전히 동일한** `_instance_counts`/`_wait_types` 구현(SQL·폴링 로직 100% 동일, diff로 확인)을 이 공용 함수 위임으로 교체 | **동작 변경 없는 기계적 중복 제거** — 정적 검사·단위시험(89건)만으로 충분하다고 판단해 커밋 완료. 별도 라이브 재검증 불필요 |
| `WF_07`/`XIPL_04` 고정 대기 → 상태 기반 대기 | `core/viewer_processing.wait_new_group`(이미 존재, 단위시험 있음, `TC_XIPL_compatibility_07`이 이미 실사용 중이고 2026-08-24 실측 검증된 함수 — 2D 2.8~2.9초/3D-N 29.5초/3D-W 39.7초)을 재사용해 두 콜사이트에 적용. `demo_acquire_step`의 기본값(14초) 자체는 안 건드리고, 두 콜사이트 모두 `settle=0`으로 호출해 우회한 뒤 `wait_new_group`이 대기를 전담하도록 바꿨다. 새로 만든 대기 로직이 아니라 이미 다른 TC에서 라이브 검증된 함수를 재사용하는 방식으로 리스크를 낮췄다 | 코드 반영, 정적 검사·단위시험 통과. **`run-wf07`/`run-xipl-04` 라이브 재검증 미완료 — 최우선 남은 일** |

### 라이브 검증 시도와 환경 문제 (2026-08-30~31)

- `run-wf10` 실행 시도 2회 모두 **작업 PC 물리 콘솔 화면이 잠금 상태**라 `cold_start`가
  비밀번호 입력 전 Viewer를 최전면으로 올리지 못해 즉시 실패했다(자동화 결함 아님).
- 08-30 13:46경 화면이 실제로 풀린 순간을 포착해(포그라운드 창 목록에 잠금 화면이 없고
  탐색기·Outlook·Edge 등 정상 창 확인) `portability-check`까지는 통과했으나, 약 2분 뒤
  `run-wf10`이 다시 잠금 화면에 막혔다. **재잠금 주기가 매우 짧아(수 분) TC 하나를 끝까지
  못 돌릴 수 있다.**
- 08-31 05:06경 다시 풀린 순간에 `run-wf07`을 시도했으나, 이번엔 잠금 화면이 아니라
  `cold_start` **로그인 단계 자체가 3회 모두 실패**했다(내가 바꾼 Step 4는 실행되지도
  못함). 오류 메시지에 "가려서 실패"·"팝업 문구" 상세가 없어 포커스 탈취/팝업 때문이
  아니라 원인 불명이다. 잠금 해제 직후 Outlook/Teams/Edge/메모장/cmd 등 업무용 창이
  다수 열려 있어 **실사용자가 이 PC를 동시에 쓰고 있을 가능성**이 있다 — 자동화의 물리
  키/마우스 입력과 실사용자의 조작이 서로 간섭했을 수 있다(단정 아님).
- **결론: 이 PC는 현재 무인 UI 자동화를 안정적으로 수행하기 어려운 상태다.** 화면 잠금
  정책 조정 또는 자동화 실행 동안 PC를 비워 두는 조치가 필요할 수 있다. 이는 자동화나
  제품의 결함이 아니라 실행 환경 문제다.

---

## 2-C. 2026-08-31 회차 — 다른 PC에서 P0 #1 라이브 재검증 완료 (이번 세션)

이식성 시험을 겸해 **다른 PC**에서 수행했다. 2-B절의 `wait_new_group` 전환을 실제 UI로
끝까지 돌려 **판정 동일성과 단축 시간을 처음으로 실측**했다.

### 결과 — 판정 동일, 실측 단축

| 구간 | 26차(고정 대기) | 08-31(`wait_new_group`) | 차이 | 판정 |
|---|---|---|---|---|
| `WF_07` Step 4 (2D 1회 촬영) | 23.1초 | 12.9초 | **−10.2초** | 26차와 동일 PASS 11/11 |
| `TC_XIPL_compatibility_04` Step 6 (기본 Step 비우기 + Preset A/B 촬영) | 144.7초 | 99.1초 | **−45.6초** | 26차와 동일 전 Step PASS |

`wait_new_group`이 보고한 실제 대기는 2D 기준 **2.8초** — 2026-08-24 실측치(2.8~2.9초)와
일치했다. 리포트: `Reports/Result_20260831_085640.json`(WF_07),
`Reports/Result_20260831_085032.json`(XIPL_04).

### 이번에 고친 것 — 고정 대기가 가려 주던 "클릭이 삼켜짐"

`XIPL_04`는 첫 실행에서 Step 5 직후 `View Position dialog did not open`으로 **재현성 있게**
실패했다. 원인은 이미 저장소에 기록돼 있던 동작이다 —
`core/viewer_processing.add_view_position`에는 2026-08-24 실측으로 확인된
"촬영 직후 `+`를 누르면 툴팁만 뜨고 다이얼로그가 안 열린다(클릭이 삼켜진다)"에 대한
3회 재시도가 있었는데, **같은 클릭을 재시도 없이 하던
`tests/xipl_flows._add_view_position_by_alias`** 에는 그 보호가 없었다. 고정 대기 14초가
우연히 가려 주고 있다가, 대기를 걷어내자 드러난 것이다.

→ 재시도 로직을 `core/viewer_processing.open_view_position_dialog`로 뽑아 두 콜사이트가
같은 것을 쓰도록 합쳤다(진짜 동일한 클릭·동일한 실패 모드라 합쳤다). 재실행에서
`XIPL_04` 전 Step PASS, `WF_07` PASS 11/11을 확인했다.

**교훈: DB 행 도착은 "다음 UI 조작을 받을 준비"까지 보장하지 않는다.** 고정 대기를
상태 기반 대기로 바꿀 때는 대기 직후의 첫 UI 조작이 재시도를 갖고 있는지 함께 봐야 한다.

### 이식성 관찰 (다른 PC에서 처음 확인한 것)

- **`reset-environment`의 기준 스냅샷에는 DICOM 서버 등록이 없다**(`DICOM_STORAGE` 0행).
  전체 회귀는 복원 직후 `DICOM_Server_Setup`(`setup_all`)이 이 전제를 만들지만, TC 단독
  실행에는 그 단계가 없다. 그래서 복원 직후 `run-wf07`이 Step 0 전제 `{'storage': None}`
  으로 FAIL 했다 — 자동화 결함이 아니라 **단독 실행 시 `setup-storage` 선행 필요**다.
  `README.md` "다른 PC로 옮길 때"에 반영했다.
- DB 데이터 파일이 없는 PC에서도 `reset-environment`가 `.bak`에서 4개 DB를 새로 만들었다
  (드라이브 문자 비의존 `WITH MOVE`가 실제로 동작함을 확인).
- 이 PC에는 UPS 장치가 없어 Viewer 상태바에 `Failed to communication with UPS.`가 상시
  표시된다. TC 판정에는 영향이 없었다(3-A의 UPS Export 결함과는 별개 사안).
- `WF_07` Step 7(전송 영상 수신 확인)이 7.6초 → 40.2초로 늘었다. 네트워크·Storage SCP
  응답 차이로 보이며 판정은 PASS로 동일하다.

### 이어서 고친 것 — `close_examine` no-dialog 경로 (사용자 승인 후 진행)

`WF_07`은 첫 실행에서 Step 5(검사 종료)가 1회 실패했고 재실행 2회는 PASS 했다(재현율 1/3).
증거 캡처에 Close 버튼 위 툴팁("Send & Close")만 뜨고 검사는 Examine 에 남아
`STUDY.StudyStatus=1` 이 유지됐다 — 위 `+` 클릭과 **같은 "클릭이 삼켜짐" 계열**이다.

사용자 승인(2026-08-31)으로 고쳤다. 다만 `close_examine` 은 **팝업 없이 정상 종료되는
경로가 따로 있어**(미촬영 Step 이 없을 때) 무조건 다시 누르면 다음 검사를 건드릴 수 있다.
그래서 "아직 Examine 인가"를 판별해야 하는데, **화면 판별 수단 두 가지를 실측으로 배제**했다.

| 후보 | 실측 결과 | 판정 |
|---|---|---|
| Close 버튼(2204) 가시성 | Examine 이 **아닌** 화면에서도 `visible=True` | 쓸 수 없음 |
| 상태 배너(2202) 픽셀 OCR | 종료 직후 다른 창이 배너를 가려 `'icine —'` 같은 쓰레기를 읽음. 문구도 `Ready` / `Xray Block` / `Not Examine Mode` 로 여럿 | 쓸 수 없음 |

→ **제품 상태 변경은 UI(Close 클릭)로, 성공 판별만 DB(`STUDY.StudyStatus`)로** 한다
(저장소 규칙: DB 로 제품 동작을 모사하지 않고 검증에 쓴다). `core/flows.py` 에
`STUDY_STATUS_EXAMINING`(=1, 실측) / `study_status` / `wait_study_closed` /
`close_examine_confirmed` 를 추가하고 `WF_07` Step 5 를 여기에 붙였다.

**재시도 조건은 두 가지를 모두 만족할 때뿐이다** — 종료 옵션 팝업이 안 떴고(`dialog=False`),
확인 시간 안에 `StudyStatus` 가 1 에서 벗어나지 않았을 때. 상한 3회.

검증: 단위시험 5건 신설(`tests/test_close_examine_confirm.py` — 삼켜짐 재클릭 / 팝업 경로
비재시도 / 팝업 없이 정상 종료 비재시도 / 상한 / 행 없음을 "닫힘"으로 오인 안 함),
`run-wf07` **3회 연속 PASS**(모두 `attempts: 1`, 확인 비용 0.3초).

> **정직한 한계: 간헐 실패가 재현되지 않아 재시도 경로 자체는 라이브로 타 보지 못했다.**
> 정상 경로가 영향을 받지 않는다는 것만 라이브로 확인했다. 전체 회귀에서 `closed.attempts`
> 값을 관찰해 실제로 재시도가 걸리는지 계속 본다(판정 `actual` 에 그대로 실린다).

---

## 2-D. 2026-08-31 회차(이어짐) — `run-wf10` 완료 확인, `WF_14` 재검증에서 자동화 결함 발견

Claude Desktop 세션이 세션 한도로 중단된 뒤 이어받았다. **대화 내용 자체는 복구할 수
없어**, git 커밋 이력·커밋 안 된 `README.md` diff·`Reports/`의 타임스탬프만으로
직전 세션이 어디까지 했는지 재구성했다(아래 내용은 전부 리포트 JSON으로 재확인함).

### `run-wf10`(P0 #3) 완료 — 선행 조건 정정

`setup-storage` 뒤 `run-wf10` 시도(09:36)는 Step 3 Hospital Code Mapping 콤보(2453)가
비활성이라 열리지 않고 FAIL 했다(`Reports/Result_20260831_093609.json`) — Storage만
등록되고 **MWL이 없어서** 이 콤보를 못 쓴 것이다. `setup-dicom`(MWL+Storage+Print 전부
등록)으로 바꿔 재실행하자 **PASS 11/11**(`Reports/Result_20260831_094332.json`) —
HC 저장, `Mammography (Rt)` 매핑, MWL Hospital Code Mapping 태그 `(0032,1064)` 설정,
MWL 처방 등록·Patient List 조회, `STUDY.ProcedureKey` 반영, Examine Step 등록·촬영
준비까지 전부 확인됐다. `README.md` "다른 PC로 옮길 때"를 `setup-storage`→`setup-dicom`
기준으로 정정했다(2-C절 서술은 구식이 됐다 — TC 단독 실행 전 `setup-dicom`을 쓴다).

### `run-wf14`(P0 #2) 연속 3회 — 목표 증상 미재현, 다른 결함 2건 발견

`reset-environment` 없이(직전 `run-wf10`이 이미 DB를 건드린 상태에서) `run-wf14`를
연속 3회 실행했다(10:09/10:40/11:13, 각 1251~1925초). **3-C가 찾던 "`my_settings`(193)
미발견" 진입 실패는 3회 모두 재현되지 않았다** — 대신 매번 Step 7에서 다른 이유로
FAIL 했다.

| 회차 | Step 7 FAIL 내용 | 원인 |
|---|---|---|
| 1차 | "설정 테이블 전수 대조" — 13개 섹션 불일치(`dicom_common`/`dicom_mwl`/`dicom_print_dicom`/`dicom_storage`/`export_cfg`/`overlay_item`/`print_overlay`/`print_overlay_item`/`procedure_common`/`qc_common`/`system_common`/`tool_button`/`view_position_preset`) | **미확정.** DICOM 관련 섹션이 다수 포함돼 있는데, 직전 09:48에 `setup-dicom`을 다시 돌렸다 — Export 기준점과 Import 후 대조 사이에 별개 원인으로 DICOM 설정이 바뀌었을 가능성과, 진짜 Import 복원 결함일 가능성을 아직 못 나눴다. 라이브 재검증 필요 |
| 2·3차 | "목록 전 행 열거 완주" — `patient.physician`/`display.overlay`/`display.lut`/`procedure.procedure`/`dicom.print_overlay`/`dicom.tag_mapping`/`qc.scheduler` 등 다수 페이지에서 열거한 행 수가 DB 원천 행 수와 다름. 이어서 `KeyError: 'changed'` 로 TC 자체가 중단됨(3-B와 다른, **자동화 코드 결함**) | 아래 참고 |

**`KeyError: 'changed'` 원인을 찾아 고쳤다(이번 세션).** `tests/workflow14.py:547~559`가
`core/setting_lists.compare_sweep()`의 반환값에서 존재하지 않는 `"changed"` 키를
참조하고 있었다 — 실제 반환 키는 집계용 `"changed_total"`(정수)과 페이지별
`"pages"[페이지]["changed"]`(목록)뿐이다(`compare()`는 `"changed"`가 있지만
`compare_sweep()`은 없다 — 두 함수를 혼동한 것으로 보인다). 2026-08-27에 이
Step 7(c)를 자동화하면서 들어간 결함으로 보이며, Step 7(a)("설정 테이블 전수 대조")가
먼저 FAIL 해 TC가 조기 중단되는 경로에서는 이 줄에 도달하지 않아 지금까지 드러나지
않았다. `lc["changed"]` → `lc["changed_total"]`로, `lc["changed"][:20]` →
페이지별 `changed`를 펼친 목록으로 고쳤다. 회귀 방지용 단위시험 2건을
`tests/test_setting_lists.py`에 추가했다(`CompareSweepTest`). 정적 검사 전부 통과,
단위시험 96건 OK. **이 픽스 자체는 아직 라이브로 재검증하지 못했다** — 다음 `run-wf14`
실행에서 Step 7(c)까지 정상적으로 판정(PASS/FAIL 무엇이든 예외 없이)이 나오는지 확인해야
한다.

**다음에 할 것**: `run-wf14`를 다시 돌려 (1) `KeyError`가 사라졌는지, (2) 목록 행 수
불일치·설정 테이블 불일치가 재현되는지(진짜 결함인지 `setup-dicom` 타이밍 오염인지),
(3) 원래 3-C 증상(`my_settings` 진입 실패)이 나오는지를 함께 본다.

### 목록 열거 읽기 결함의 근본 원인 (2026-08-31, 라이브 조사로 확정)

`system.account`/`patient.physician` 두 페이지를 대상으로, 로그인된 Viewer에 직접
붙어 `visible_rows()`가 잡은 행의 자식 컨트롤과 화면 픽셀(OCR)을 각각 읽는 일회성
진단을 수행했다(진단 스크립트는 결과만 남기고 삭제 — 저장소에 두지 않았다). **원인이
두 가지 섞여 있었다.**

**원인 A — 행이 owner-draw 라 자식 창이 없다.** `system.account`의 두 행(hwnd
1379950 / 4984968)은 `core.ui.children(row.hwnd, 3)`으로 자식을 열거하면 **0개**다.
그런데 그 rect 를 그대로 OCR 하면 `'service service Servi... O'` / `'admin admin
Admin O User'` — **service/admin 두 계정이 실제로 화면에 그려져 있다.** 즉 이 행은
Win32 자식 창이 아니라 **한 창 안에 직접 그려지는(owner-draw) 콘텐츠**이고,
`row_signature()`가 전제하는 "자식 컨트롤의 `WM_GETTEXT`" 로는 원천적으로 읽을 수
없다. `dicom.mwl`/`dicom.storage`/`dicom.print` 처럼 행 수가 DB 와 우연히 일치하는
페이지도 "문구를 읽지 못한 행"으로는 여전히 잡히는 것과 일치한다 — **행 식별 자체가
전 페이지에서 안 되고 있었다.**

**원인 B — `patient.physician`은 애초에 엉뚱한 목록을 보고 있다.** 이 페이지에서
`visible_rows()`가 잡은 "3행"을 OCR 하면 `'1. Scheduled Performing Physician (MWL)'`
/ `'2. Performing Physician (MWL)'` / `'3. service (Current User)'` — **실존 의사
명단이 아니라 MWL 역할 매핑 옵션 콤보**다. `PHYSICIAN` 테이블이 0행인 것과 이 "3행"은
애초에 무관하다 — `expected_row_count()`가 비교 대상으로 삼은 화면 요소 자체가
틀렸다.

**두 원인 모두 `stop=False`인 서브체크 안에 갇혀 있어 다른 판정(Step 7(c) 실제 값
대조)을 오염시키지 않는다** — 그래서 2026-08-27 도입 이후 계속 이 상태였는데도
드러나지 않았다. **제품 결함이 아니라 자동화의 읽기 방식이 이 컨트롤 구조에
안 맞는 것이다.**

**개선 방향(구현 전, 사용자 합의 필요)**: (1) `row_signature()`를 자식 텍스트 대신
`core/uitext.ocr()`(이미 `setting_values.py`가 값 콤보에 쓰고 있다)로 다시 설계하되,
2026-08-25 오인(스크롤로 같은 HWND 재사용)이 재발하지 않게 스크롤 전후 겹침 증명은
그대로 유지해야 한다. (2) `patient.physician`을 포함해 `LIST_PAGES`의 각 페이지가
실제로 `ROW_COUNT_QUERIES`가 가리키는 DB 테이블과 같은 화면 요소를 보고 있는지
하나씩 재확인해야 한다(다른 페이지도 같은 오탐이 있을 수 있다 — 아직 다 확인 안 함).
이 자체가 `core/setting_lists.py` 전반의 재설계라 세션당 하나에 집중한다는 원칙에
따라 별도 세션/작업으로 진행하는 편이 낫다.

### 라이브 재검증 결과(같은 세션, 09:48 `setup-dicom` 이후 처음 완주한 실행)

`run-wf14`를 다시 돌렸다(`Reports/Result_20260831_115710.json`, 1819초). 결과:

- **`KeyError: 'changed'` 픽스가 라이브로 확인됐다.** Step 7(c) "Setting 목록 행 상세값
  복원"이 예외 없이 **PASS**로 판정됐다(123행/1820항목 비교, 달라진 항목 0). 이전
  3회 실행을 막던 자동화 결함은 해소됐다.
- **TC 전체는 FAIL로 끝났지만 원인은 이미 알려진 별개의 제품 결함이다** — `device.ups`의
  UPS Setting 값(`EATON El` → `None`)이 Export/Import로 복원되지 않았다. 이것은 3-A /
  B.22에 이미 "완화하지 않는다"로 기록된 제품 결함과 **정확히 같은 것**이다. 새로 생긴
  문제가 아니다.
- **원래 3-C 증상(`my_settings`(193) 진입 실패)은 이번에도 재현되지 않았다** — 이제
  연속 4회(1251/1913/1925/1819초) 모두 미재현이다.
- **새로 드러난 문제 — "목록 전 행 열거 완주" 서브체크가 계속 FAIL 한다.**
  `patient.physician`/`display.overlay`/`display.lut`/`procedure.procedure`/
  `dicom.print_overlay`/`dicom.tag_mapping`/`qc.scheduler` 등 대부분의 목록 페이지에서
  "문구를 읽지 못한 행"(서명이 빈 행) 수가 두 자릿수로 나오고, 열거한 행 수가 DB
  원천 행 수(`core/setting_lists.ROW_COUNT_QUERIES`)와도 다르다. **Import 전(Step 0
  근거 수집)과 Import 후(Step 7) 양쪽에서 완전히 동일한 패턴으로 나타난다** — 즉
  Export/Import와 무관하게 이 화면의 행 텍스트를 읽는 메커니즘 자체가 불완전하다.
  이 서브체크는 `stop=False`라 TC를 중단시키지 않고, 실제 값 대조(Step 7(c), 위에서
  PASS)는 "불완전한 열거는 근거로 안 쓴다"는 설계 덕에 오염되지 않았다 — 그래서 지금까지
  드러나지 않은 채 방치돼 있었다. **2026-08-27에 이 서브체크가 자동화된 뒤 실제로 통과한
  기록을 찾지 못했다** — 계속 이 상태였을 가능성이 있다. 원인 후보(확인 안 됨): 목록
  행의 서명 추출 방식(`core/setting_lists.py::_screen`)이 특정 컨트롤 구조에서 문구를
  못 읽는다 / DB 원천 카운트 쿼리가 화면에 보이는 것과 다른 대상을 센다(필터·중복 등).
  **라이브로 원인을 확인해야 한다 — 추측하지 않는다.**

---

## 2-E. 2026-08-31 회차(이어짐) — 주 모니터 가드 검증에서 **가드가 절반만 걸려 있었음**을 발견

P0 "주 모니터 밖/안 조건에서 `cold_start` 안전 중단과 정상 로그인 확인"을 수행했다.

### 모니터가 1개인 PC 에서 이 항목을 검증한 방법

이 PC 는 모니터가 1개다(`EnumDisplayMonitors` 1개, 가상 화면 = 주 모니터 1920x1080).
그런데 가드 조건이 **좌표 기반**(`0 <= left < max_w and 0 <= top < max_h`)이라,
창을 음수 좌표로 옮기면 멀티 모니터 없이도 **같은 분기를 그대로 탄다.** 그래서
`SetWindowPos` 로 Viewer 창을 `(-600, 100)` 으로 옮긴 뒤 `cold_start` 를 호출하고,
끝나면 원위치로 되돌리는 일회성 진단으로 확인했다.

> 다만 이것은 가드의 **판정 분기**를 태운 것이지, 멀티 모니터/DPI 가상화 상황 자체를
> 재현한 것은 아니다. 그 조합은 이 PC 에서 재현할 수 없다.

### 발견 — 재사용 경로는 가드를 **아예 평가하지 않았다**

첫 실행에서 창을 `(-600, 100)` 에 두고 `cold_start(force_restart=False)` 를 불렀는데
**중단하지 않고 정상 반환**했다. 원인은 배치였다 — 가드가 `cold_start` 의 기동/로그인
경로에만 있었고, **이미 떠 있는 Viewer 를 재사용하는 분기가 그보다 먼저 `return`** 한다.

영향 범위가 작지 않다. `config.json` 의 `viewer.force_restart` 는 `None`(=재사용)이고,
`cold_start` 호출부 중 `force_restart=True` 를 주지 않는 것들 — `WF_01`, `WF_05`,
`run-ui` 등 — 은 **창이 어긋나 있어도 그대로 진행**했다는 뜻이다. 좌표 기반 자동화가
어긋난 창에서 도는 것을 막으려고 만든 가드인데 정작 가장 흔한 경로에서 안 걸렸다.

### 수정과 재검증

가드를 `core/flows.require_primary_monitor(ui)` 로 뽑아 **기동 경로와 재사용 경로가 같은
검사를 쓰게** 했다. 재사용 경로에서는 팝업 정리(`watchdog.DialogGuard.sweep`, 클릭이
일어난다)보다 **먼저** 확인한다 — 어긋난 창에서 클릭부터 하면 안 되기 때문이다.

| 조건 | 결과 |
|---|---|
| 창 `(-600, 100)` + 재사용 경로 | **중단** — "주 모니터 ... 밖에 있습니다(현재 rect=(-600, 100, 1320, 1180))", **창 위치 그대로**(자동화가 옮기지 않음) |
| 창 `(0, 0)` + 재사용 경로 | 정상 재사용·로그인 (`_login_check.py`) |
| 창 `(0, 0)` + 기동 경로(`force_restart=True`) | 정상 종료·재기동·로그인 (리팩터링이 기동 경로를 깨지 않았는지 확인) |

회귀 방지 단위시험 7건 신설(`tests/test_primary_monitor_guard.py`) — 안/밖/우측 이탈/창
미발견에 더해, **재사용 경로가 검사를 거친다는 것**과 **클릭보다 먼저 막는다는 것**을
고정했다. 정적 검사 전부 통과, 단위시험 96 → **103건 OK**.

---

## 2-F. 2026-09-01 회차 — `dicom.tag_mapping`/`qc.scheduler` 원인 확정(P0 #1)

5절 ⑦에서 미해결로 남긴 두 페이지를 라이브로 재조사했다. 잡음 패턴을
`tool.predefined_text`(해결됨)와 직접 비교하니 **다른 종류**였다 — 매 화면의
**마지막 행**에서만 단어 **중간** 글자가 바뀌었다(`"Age"`→`"Aae"`). 첫 진단
(행 높이 비교)은 라이브 재검증에서 곧바로 "변화 없음"으로 틀렸음이 드러났다 —
`GetWindowRect`는 잘린 행도 명목상 크기 그대로 보고한다. 재진단으로 행을
감싸는 `ScrollWnd`(뷰포트) rect와 행 rect를 직접 대조하니, 마지막 행이
뷰포트 아래로 12px 튀어나와 있었다(뷰포트 bottom=460, 행 bottom=472) — 그
튀어나온 부분을 OCR 하며 단어가 깨진 것이었다. 상세 경위·컨트롤 트리 실측은
`../프로젝트_상세.md` B.28 참고.

`core/setting_lists.py`에 `_list_viewport()`(행과 좌우 경계가 일치하는
`ScrollWnd`를 찾는다)와 `_confidently_visible()`(뷰포트 밖으로 튀어나온 행을
화면에서 뺀다)을 추가해 `_screen()`에 적용했다. 단위시험 9건 신설
(`ConfidentlyVisibleTest`/`ListViewportTest`), 119 → **128건 OK**.

**라이브 재검증(`Reports/Result_20260831_194615.json`, `run-wf14` 단독
실행)** — `dicom.tag_mapping` **17/17 완전 일치**(불완전 목록에서 빠짐),
`qc.scheduler` 20/23 → **21/23**(스크롤이 실제 바닥까지 도달 확인). 남은
2행 격차는 DB 직접 조회로 확인했다 — Gantry 그룹이 DB엔 12개 코드(51~62)가
있는데 화면엔 정확히 10개 행만 그려진다. 스크롤 결함이 아니라
`display.overlay`와 같은 개념 불일치(유형③) 후보로 재분류했다 — 원인 확정은
아직(P0 #1로 다음 세션에 넘김). 전체 판정은 여전히 FAIL(원인은 3-A UPS 제품
결함, 회귀 없음), Step 7(c) "Setting 목록 행 상세값 복원"은 PASS(128행/1768
항목, 달라진 항목 0)로 비교 폭도 넓어졌다(122→128행).

---

## 2-G. 2026-09-01 회차(이어짐) — `display.overlay`는 "설계 차이"가 아니라 교차 오염이었다(P0 #2)

5절 ⑦은 `display.overlay`(화면 28 vs DB 8)를 "화면은 표시 가능 카탈로그, DB는
실제로 켜진 것만 저장 — 개념이 달라 쿼리로 못 고친다"로 결론짓고, 항목별
추가/미추가 상태를 Import 전후로 비교하는 새 검증 설계가 필요하다고 남겼다.
**이 결론이 틀렸다는 것을 라이브로 확인했다.**

컨트롤 트리를 덤프해 보니 이 페이지엔 독립된 목록이 **셋**(후보 카탈로그
`OVERLAY_LIST_AVAILABLE`, 실제 활성 목록 `OVERLAY_LIST_TOP`/`OVERLAY_LIST_BOTTOM`)
있었다. 실측: DB `OVERLAY_ITEM` 8행(Top 6 + Bottom 2), 화면 카탈로그는 스크롤
전 20행 표시. `visible_rows()`는 패널 전체를 훑어 셋을 안 가리고 섞는다 — 실측
20(카탈로그) + 6(Top) + 2(Bottom) = **정확히 28**. 예전 "28"은 카탈로그
크기가 아니라 **세 목록이 섞인 우연의 합**이었다. `../지식/` Service Manual
4.4.2 의 진짜 카탈로그는 34개 항목이라 애초에 28과도 맞지 않았다 — 즉
`procedure.procedure`/`dicom.print_overlay`(교차 오염, 유형④)와 **같은
종류의 버그**였다.

`core/setting_lists.py`에 `_collect_overlay()`를 추가했다 —
`setting_values.pane_controls(pane, depth=6)`가 `children(pane.hwnd, depth)`일
뿐이라는 점을 이용해, Top/Bottom 컨트롤(`ui.by_id()`로 직접 찾음)을 그대로
`pane` 삼아 기존 `collect()`를 두 번 돌리고(카탈로그는 제외) 결과를 병합한다
— 새 스캔 로직 없이 기존 함수 재사용만으로 해결했다. `sweep()`이
`display.overlay` 키를 만나면 이 경로를 쓴다. 단위시험 3건 신설
(`CollectOverlayTest`), 128 → **131건 OK**.

**라이브 검증(`Reports/Result_20260831_204935.json`)** — `display.overlay`
열거 8 / DB 8 **완전 일치, 불완전 목록에서 빠짐.** 전체 판정 여전히
FAIL(원인 3-A UPS, 회귀 없음). Step 7(c) 비교 행 수는 128→**108행**으로
줄었다 — 카탈로그의 정적인 20행이 매번 "안 바뀜"으로 비교에 끼어 실제
검증력 없이 수만 채우고 있었을 뿐이라, 이 감소는 회귀가 아니라 **의미
없는 비교 대상이 빠진 것**이다(판정은 PASS, 달라진 항목 0 그대로).

상세 경위는 `../프로젝트_상세.md` B.29 참고.

---

## 2-H. 2026-09-01 회차(이어짐) — 교차 오염 3곳 중 1곳(`procedure.procedure`) 완료, 2곳은 대응 관계 미확정으로 보류(P0 #3 일부)

B.29 의 해법("대상 컨트롤을 `ui.by_id()`로 직접 찾아 `pane` 삼기")이 나머지
교차 오염 페이지에도 통하는지 `procedure.procedure`/`dicom.print_overlay`/
`patient.physician` 셋의 컨트롤 트리를 라이브로 덤프했다.

**`procedure.procedure` — 같은 패턴으로 바로 풀렸다.** 독립된 `ListCtrl`이
정확히 둘이다 — Procedure 카탈로그(id=2560, 실측 15행=DB `PROCEDURE_INFO`와
일치)와 View Position 약어 목록(id=2561, 실측 4행 — RCC/LCC/RMLO/LMLO,
Procedure 와 무관). `visible_rows()`가 둘을 섞어 15+4=19행으로 잡았다.
`core/setting_lists.py`에 `SINGLE_LIST_CONTROL = {"procedure.procedure": 2560}`
매핑과 `sweep()` 라우팅을 추가했다 — `_collect_overlay()`처럼 두 목록을
병합할 필요가 없는 **단순한 경우**라 더 가벼운 전용 경로를 뒀다(대상
컨트롤 하나만 찾아 기존 `collect()`에 그대로 넘긴다). 단위시험 2건 신설
(`SingleListControlTest`), 131 → **133건 OK**.

**라이브 검증(`Reports/Result_20260831_221745.json`)** — `procedure.procedure`
열거 15 / DB 15 **완전 일치, 불완전 목록에서 빠짐.** 전체 판정 여전히
FAIL(3-A UPS, 회귀 없음). Step 7(c) 비교 행 수 108→**104행**(줄어든 4행 =
이 페이지에서 빠진 View Position 약어 행 — B.29 와 같은 이유로 회귀 아님).

**`dicom.print_overlay`/`patient.physician` — 이번엔 보류.** 둘 다
`procedure.procedure`보다 목록이 더 많고(넷) 어떤 목록이 DB 판정 대상과
대응하는지 자체가 불확실했다.

- `dicom.print_overlay`: 독립된 `ListCtrl` 넷 — Overlay 이름(id=2485, 현재
  1행), 후보 필드 카탈로그(id=2489, 20행 이상), "추가된 필드" 슬롯으로
  보이는 목록 셋(id=2486/2487/2488, 이번 실측에서 **셋 다 0행**). DB
  `PRINT_OVERLAY_ITEM`이 이 셋 중 무엇과 대응하는지, 혹은 선택된 Overlay에
  실제로 필드가 하나도 안 붙어 있어 셋 다 비어 보이는 것인지 미확정.
- `patient.physician`: 2x2 그리드 `ListCtrl` 넷 중 셋이 비고, 하나(id=2321)만
  3행(MWL 역할 매핑 콤보 — B.24 에서 이미 "실제 의사 명단이 아니다"로 확인된
  것과 같은 컨트롤)을 담는다. DB `PHYSICIAN` 은 0행인데, 이 화면에 진짜
  "의사 명단"에 대응하는 그리드가 있는지, 아니면 이 화면 자체가 역할
  매핑만 다뤄 대응하는 목록이 원천적으로 없는지도 미확정이다.

**추측으로 고치지 않고 조사 결과만 남긴다.** 다음 조사는 각 목록에 항목을
하나씩 추가해 보며 DB 어느 테이블/컬럼이 바뀌는지 실측하는 방식
(B.29 의 `_overlay_positions()`처럼)이 되어야 한다. 상세 경위는
`../프로젝트_상세.md` B.30 참고.

---

## 2-I. 2026-09-01 회차(이어짐) — 보류했던 2곳(`dicom.print_overlay`/`patient.physician`) 완료(P0 #3 마무리)

2-H에서 "대응 관계부터 실측으로 확정해야 한다"고 남긴 두 페이지를 데이터를
손대지 않고(라벨 OCR·DB 조회·조회성 행 선택만으로) 확정했다.

**`patient.physician` — 라벨을 읽으니 바로 풀렸다.** 4개 그리드 라벨을
OCR로 읽으니 "Referring Physician"(id=2318)/"Reading Physician"(id=2319)/
"Performing Physician"(id=2320, 셋 다 현재 0행)/"Performing Physician Order"
(id=2321, 3행 — B.24 에서 이미 확인된 MWL 역할 매핑 콤보, Physician 명단
아님)였다. 진짜 대상 2318+2319+2320 의 합(0)이 DB `PHYSICIAN`(0행)과
일치한다 — **"오탐"이 아니라 `procedure.procedure`와 같은 교차 오염**이었다.

**`dicom.print_overlay` — 행 선택이 필요한 한 단계가 더 있었다.** 2-H에서
"셋 다 0행"으로 봤던 목록 셋(id 2486/2487/2488)은 좌측 Overlay 이름 목록
(id=2485)에서 행을 선택해야만 채워지는 상세 목록이었다(선택 전엔 비어
있는 게 정상). DB `PRINT_OVERLAY`(Overlay 1개, `TC_WF03_OVERLAY`)/
`PRINT_OVERLAY_ITEM`(Position 0/1/2 각 2개, 총 6행)을 직접 조회한 뒤 이름
목록 첫 행을 클릭(조회성 선택)하니 세 목록이 정확히 2/2/2로 채워졌다.

`core/setting_lists.py`에 `_collect_multi_list()`(선택 없이 여러 목록을
합침, `patient.physician`)와 `_collect_print_overlay()`(이름마다 선택하며
Position 목록을 모음, `dicom.print_overlay`)를 추가했다.

**부수 발견 — `walk()`의 오래된 결함.** `patient.physician`을 고친 첫
검증에서 개수는 0/0으로 맞는데도 "불완전"으로 남았다 — `walk()`가 행을
하나도 못 찾으면 이유를 안 따지고 항상 실패로 처리하고 있었다(지금까지
다룬 모든 목록이 DB 원천 1행 이상이라 이 전제가 늘 맞았을 뿐, 진짜 0행
페이지가 처음 나오며 깨졌다). `expected_count==0`일 때만 빈 목록을 완전한
열거로 인정하도록 고쳤다(`_collect_multi_list()`도 합계 0일 때만 개별에
0을 넘기도록 맞췄다). 단위시험 133 → **144건 OK**.

**라이브 검증(`Reports/Result_20260901_010617.json`)** — `dicom.print_overlay`
6/6, `patient.physician` 0/0 **둘 다 완전 일치, 불완전 목록에서 빠짐.**
문제 있던 9개 페이지 중 **8개 완료**(남은 것은 `qc.scheduler` 하나뿐).
전체 판정 여전히 FAIL(3-A UPS, 회귀 없음), Step 7(c) 비교 행 수
104→**89행**(의미 없던 비교 대상이 더 빠진 것 — B.29/B.30 과 같은 이유,
회귀 아님). 상세 경위는 `../프로젝트_상세.md` B.31 참고.

---

## 2-J. 2026-09-01 회차(이어짐) — `qc.scheduler`는 넷과 달리 진짜 제품 설계 차이였다(P0 #1 마무리, 9/9 완료)

마지막 남은 페이지(`qc.scheduler`, 21/23)를 조사했다. 앞선 넷(display.overlay
/procedure.procedure/dicom.print_overlay/patient.physician)이 전부 "개념
불일치/오탐"으로 잘못 결론 났다가 실제로는 교차 오염이었던 전례가 있어,
**이번에도 성급히 "설계 차이"로 단정하지 않고 같은 순서(라이브 컨트롤 트리
확인 → 사양서 대조)를 그대로 밟았다.**

**라이브로 먼저 확인** — 이 페이지에도 다른 `ListCtrl` 6개(2x3 그리드,
`patient.physician`과 비슷한 레이아웃)가 있었지만 **전부 비어 있었고**,
실제로 열거되는 20~21행은 전부 진짜 QC 테스트 이름이었다 — 교차 오염이
아니었다.

**사양서에서 결정적 근거 확인** — `../지식/Bellalun Viewer 사양서2(260710).txt`
8492~8511행: "Setting > Q.C. > Scheduler — 일반/`-d` 모드에서는 `Geometry
Calibration(Tomo)` 항목이 안 보이고, 내부 `-m`(서비스/공장) 플래그로 실행할
때만 보인다." `../지식/Bellalun Viewer Service Manual.V1.0.12W1_KO_완료.txt`
3749행: "연결된 VDMS 시스템이 지원하지 않는 Q.C 항목은 목록에 표시되지
않는다." 사양서 개정 이력에 "지원하지 않는 QC 항목 삭제"라는 문구가 하나 더
있어 둘째 항목도 같은 종류로 보이지만 정확한 이름은 `../지식/`에서 못
찾았다.

**결론 — 이번엔 진짜였다.** DB `QC_SCHEDULE`(23행)은 "이 기종이 지원할 수
있는 QC 유형의 전체 카탈로그"이고 화면은 "이 연결·이 실행 모드에서 실제로
켤 수 있는 것"만 보여준다. `core/setting_lists.py`의 `ROW_COUNT_QUERIES`에서
`"qc.scheduler"` 항목을 뺐다(매핑 없는 다른 페이지와 같은 처리 — 정지·연속
증명만으로 판정, 근거는 주석에 남김). 회귀 방지 단위시험 2건 신설, 144 →
**146건 OK**.

**라이브 검증(`Reports/Result_20260901_022050.json`)** — "불완전 페이지":
**`[]`**. 문제 있던 9개 페이지가 **전부** 완료됐다. 전체 판정 여전히
FAIL(3-A UPS, 회귀 없음), Step 7(c) 비교 행 수 89행 그대로(개수 증명만
뺀 변경이라 상세값 비교 대상 자체는 안 바뀐다 — 예상대로).

상세 경위는 `../프로젝트_상세.md` B.32 참고.

---

## 3. 남은 문제

| # | 문제 | 우선순위 |
|---|---|---|
| 1 | `TC_XIPL_compatibility_05` Fiber 콤보에 합격 기준(4.0) 미만 항목이 없어 불합격 경계 검증이 MANUAL로 남는다(TC 전체는 정상적으로 MANUAL 판정까지 끝난다 — 크래시 아님, 2026-08-28 재검증) | P2 |
| 2 | `TC_XIPL_compatibility_03` Step 9 — 제품 결함. 완화하지 않는다 | 제품 수정 대기 |
| 3 | 3D Preset 목록·추가·삭제 컨트롤 ID 미실측 → "새 Preset 이 Default 를 물려받는가" 미판정 | P1 |
| 4 | `flows.demo_acquire_step(settle=14)` 고정 대기 — **2026-08-31 라이브 재검증 완료(2-C절).** 회귀에 남아 있던 두 콜사이트(`tests/workflow07.py` WF_07 Step 4, `tests/xipl_flows.py::compatibility_04` XIPL_04)를 `core/viewer_processing.wait_new_group` 상태 기반 대기로 바꿨고, 실제 UI 실행에서 **판정 동일(WF_07 PASS 11/11, XIPL_04 전 Step PASS) + WF_07 Step 4 −10.2초 / XIPL_04 Step 6 −45.6초**를 실측했다. 전환 과정에서 드러난 `_add_view_position_by_alias` 재시도 누락은 `open_view_position_dialog` 공용화로 고쳤다. `run-sys3d`(`tests/system_compat.py:207`, 명시적 settle=20)와 `run-ui`/`run-auto`(`tests/ui_flows.py:206`)는 회귀 밖 별도 명령이라 후순위(P2)로 남긴다 | 완료(P2 잔여) |
| 5 | 중단 정책 때문에 `XIPL_03` Step 10 의 "GPU 없음 SKIP" 기록이 사라진다 | P2(맞바꾼 것) |
| 6 | 추적성 미연결 13건 — `Install_01` 외 12건은 전부 미구현 | P2 |
| 7 | **UPS 설정이 Setting Export/Import 범위 밖이다** — 아래 3-A | 제품 수정 대기 |
| 8 | **Setting 페이지 순회 중 Viewer 가 종료되는 경우가 있다**(간헐) — 아래 3-B | 조사 계속 |
| 9 | **`WF_14` 진입이 간헐적으로 실패한다**(`my_settings` ID 193 미발견) — 아래 3-C. **연속 3회 재실행(2026-08-31)으로도 이 증상 자체는 재현되지 않았다** — 대신 다른 결함 2건이 나왔다(아래 2-D절) | P0 |
| 10 | ~~`WF_10`의 `HC` → `Mammography (Rt)` 비기본 Procedure 매핑 변경이 미검증~~ — **2026-08-31 완료.** `run-wf10` PASS 11/11(`Reports/Result_20260831_094332.json`) — HC 저장, `Mammography (Rt)` 매핑, MWL Hospital Code Mapping 태그 `(0032,1064)`, MWL 처방 등록·조회, `STUDY.ProcedureKey` 반영, Examine Step 등록·촬영 준비까지 전부 확인됐다. **선행 조건 정정**: `setup-storage`만으로는 부족하다 — MWL이 없으면 Step 3의 Hospital Code Mapping 콤보(2453)가 비활성이라 열리지 않고 FAIL 한다(`Result_20260831_093609.json`). `setup-dicom`(MWL+Storage+Print)으로 바꾸자 PASS 했다. `README.md`에 반영 | 완료 |
| 11 | ~~`cold_start` 주 모니터 이탈 중단 로직이 미검증~~ — **2026-08-31 검증 완료 및 결함 수정**(2-E절). 밖: 안전 중단 + 창 위치 유지, 안: 정상 로그인, 기동 경로도 정상. 검증 중 **재사용 경로(`force_restart=False`, 기본값)가 검사를 건너뛰던 것**을 찾아 고쳤다 | 완료 |
| 12 | ~~작업 PC 물리 접근 문제(08-30~31)~~ — **2026-08-31에 다른 PC로 옮겨 해소.** 새 PC에서는 화면 잠금·로그인 실패가 재현되지 않았고 `portability-check`와 `cold_start` 로그인이 정상이었다(2-C절). 이전 PC로 돌아가면 3-D가 다시 유효하다 | 해소(환경 이전) |

### 3-A. UPS 설정이 Export/Import 로 복원되지 않는다 (제품 결함, 사용자 확인 완료)

`Setting > Device > UPS` 값은 저장은 되지만 `.vms` 20개 항목·DB 3종·`ExternalInput.xml`·
레지스트리 어디에도 실리지 않는다(전수 확인). 사양서1 60절은 Export 대상을 "Study 정보를
제외한 모든 설정 정보"로 정의하므로 `WF_14` Step 7 판정에 넣었고 완화하지 않는다.

### 3-B. Setting 전 페이지 순회 중 Viewer 가 종료된다 (간헐, 원인 미특정)

51개 페이지를 읽은 뒤 Q.C. 그룹에서 4회 재현됐으나, 그룹 순서를 뒤집으면 56페이지
모두 정상이었다(GDI/USER 핸들이 더 높은데도). 최소 재현(3페이지)으로는 재현되지 않는다
— 간헐적이다. `read_all`이 소멸을 감지하면 순회를 멈추고 `viewer_died`를 남기며, `WF_14`는
재기동해 본 시험을 끝까지 수행한다. 페이지당 GDI 약 50·USER 약 82 증가가 함께 관측된다.

### 3-C. `WF_14` 진입 실패 — `my_settings`(193) 미발견 (간헐)

같은 코드로 19분 전 실행은 PASS(18/18)했는데 다음 실행이 진입에서
`System 설정 'my_settings'(ID 193)을 찾지 못했습니다`로 실패했다(정리/원복은 정상 수행).
3-B와 같은 계열(Setting 진입 직후 화면 불안정)일 수 있으나 진입과 순회-중은 다르므로
단정하지 않는다.

**2026-08-31 연속 3회 재실행 결과 — 이 증상 자체는 재현되지 않았다.** 대신 아래
2-D절의 결함 2건이 나왔다. 진입 실패 재현율은 여전히 미확정이므로 3-C는 열어 둔다.

### 3-D. 작업 PC 물리 접근 문제 (신규, 2026-08-30~31 관측)

`progress.md` "알려진 문제" 참고. 요약:

1. 화면이 수 분 단위의 짧은 주기로 잠겼다 풀렸다를 반복한다(포그라운드 창 타이틀이
   "Windows 기본 잠금 화면"이었다가 사라지고 다시 나타남을 반복 관측).
2. 풀린 순간에도 자동화가 끝까지 갈 시간이 부족했다 — `portability-check` 통과 후
   약 2분 만에 재잠금.
3. 한 번은 재잠금이 아니라 `cold_start` 로그인 자체가 3회 모두 실패했다(팝업/포커스
   탈취 흔적 없음). 잠금 해제 직후 Outlook/Teams/Edge 등 업무용 창이 열려 있어
   **실사용자가 이 PC를 동시에 쓰고 있을 가능성**이 있다.

**판단**: 자동화나 제품의 결함이 아니라 실행 환경 문제로 본다. 화면 잠금을 억지로
자동 해제하는 코드는 자격증명이 필요한 보안 동작이라 만들지 않았고, 재잠금을 "기다려
우회"하는 긴 재시도도 근거 없는 타임아웃이 되므로 넣지 않았다. **다음 세션은 이 PC가
자동화 전용으로 충분히 오래 비어 있는 시간대인지부터 확인하고**, 그렇지 않다면 먼저
사용자에게 확인을 구해야 한다.

---

## 4. 우선순위

### P0

0. **매 세션 첫 단계 — 실행 PC가 자동화를 수행할 수 있는 상태인지 확인한다.**
   `portability-check`의 "관리자 권한"이 True인지 보고, 포그라운드 창 타이틀이 잠금
   화면이 아닌지 + `EnumWindows`로 잠금 화면 창이 없는지 확인한다(타이틀이 빈 hwnd=0
   만으로 "풀렸다"고 판단하지 않는다). 2026-08-31에 옮긴 PC(`HOST=ADMIN`)에서는 잠금
   문제가 재현되지 않았다(2-C절). 이전 PC로 돌아가면 3-D가 다시 유효하다.
   TC 단독 실행에서 DICOM 전송·MWL을 쓰면 **`setup-dicom`을 먼저 한 번 돌린다**(2-D절 —
   `setup-storage`만으로는 MWL이 빠져 `run-wf10`류가 FAIL 한다).
1. ~~`run-wf07`/`run-xipl-04` `wait_new_group` 전환 재검증~~ — **2026-08-31 완료**
   (2-C절: 판정 동일, WF_07 Step 4 −10.2초 / XIPL_04 Step 6 −45.6초).
2. ~~`WF_14` 재검증~~ — **2026-08-31 완료**(2-D절). `KeyError: 'changed'` 픽스가
   라이브로 확인됐고(Step 7(c) 예외 없이 PASS), 3-C가 찾던 진입 실패 증상은 **연속 4회
   모두 미재현**이다. TC 자체는 FAIL 로 끝났지만 원인은 이미 알려진 제품 결함
   (`device.ups` UPS 설정이 Export/Import 로 복원되지 않음 — 3-A). **남은 것은 "목록 전
   행 열거 완주" 서브체크**로, 근본 원인까지 확정됐고 수정 방향은 5절 ⑦의 사용자 판단
   대기 항목이다.
3. ~~`run-wf10`으로 `HC`가 비기본 Procedure `Mammography (Rt)`에 실제 매핑되고 해당
   Procedure Step이 등록되는지 검증한다.~~ — **2026-08-31 완료**(2-D절). PASS 11/11.
   선행 조건은 `setup-storage`가 아니라 `setup-dicom`이다.
4. ~~주 모니터 밖/안 조건에서 `cold_start` 안전 중단과 정상 로그인 확인~~ —
   **2026-08-31 완료 및 결함 수정**(2-E절). 검증 과정에서 **재사용 경로
   (`force_restart=False`, `config.json` 기본값)가 가드를 아예 평가하지 않는다**는 것이
   드러나 `flows.require_primary_monitor()` 로 공용화해 고쳤고, 밖/안/기동 경로 세 조건을
   모두 라이브로 확인했다.
5. 남은 미검증 항목(`run-wf04`→`run-wf06` 연쇄, `run-wf13`, `run-wf15` 단독 실행)을
   재검증한 뒤 전체 회귀 1회 실행. `run-xipl-05`는 2026-08-28 확인 완료.

### P1

6. **자동화 리팩터링과 속도 개선을 계속 다음 개발의 중심으로 둔다.** WF_07/XIPL_04
   전환의 라이브 재검증(위 P0 #1)이 끝나면, `run-sys3d`/`run-ui`(회귀 밖 명령)에 남은
   `demo_acquire_step` 고정 대기도 `wait_new_group`으로 바꿀지 판단한다. 판정 기준·
   Workflow 순서·제품 상태 변경 방식은 유지하고, 변경 전후 실행 시간과 동일 판정 결과를
   함께 검증한다.
7. `python run.py probe-preset3d` 로 3D-N/3D-W Preset 목록 컨트롤 실측 → `core/flows.py`
   상수로 기록.
8. 그 위에 "새 3D Preset 이 그 시점 Default 를 물려받는가"(Service Manual 근거)를
   `XIPL_07` 에 추가.

### P2

9. ~~`flows.close_examine` 의 no-dialog 경로 상태 신호화~~ — **2026-08-31 완료**(2-C절). `WF_07` 외 다른 `close_examine` 호출부(`WF_04`/`WF_10`/`XIPL` 등)도 같은 `close_examine_confirmed` 로 옮길지는 전체 회귀에서 재시도가 실제로 걸리는지 본 뒤 판단한다 — 지금은 근거 없이 넓히지 않는다.
10. 추적성 미확정 중 `Install_01` — 검증 대상 Release Note 를 받으면 확보 가능.
11. `XIPL_05` Fiber 콤보 항목 구성 재검토(3절 #1) — 급하지 않다.

---

## 5. 사용자 판단이 필요한 항목

### ① `Install_01` — 검증 대상 Release Note

`config.json > release_note` 가 2026-08-10 캡처 baseline 이고 `_source` 에 "교체
필요" 로 표시돼 있다. 실제 검증 대상 Release Note 를 주시면 `Install_01` 을
MANUAL → 자동 판정으로 올리고 추적성도 연결할 수 있다.

### ② `Install_02` — 지원 OS Build 목록과 DICOM 어댑터 별칭

`config.json > prerequisites.dicom_nic_alias` 와 지원 OS Build 기준을 주시면
현재 SKIP 인 항목을 자동 판정으로 바꿀 수 있다.

### ③ 중단 정책이 맞바꾼 것

FAIL 이 나면 그 TC 를 중단하므로 첫 FAIL 뒤의 판정 정보는 수집되지 않는다(3절 #5).
원하시면 `config.json > regression.stop_tc_on_fail` 을 `false` 로 두면 예전처럼 끝까지
수행한다.

### ④ `TC_Basic_WorkFlow_13` Step 4~6 — 로그인 계정 전환을 자동화할지

로그오프 후 시험 계정으로 로그인하면 회귀의 나머지 TC 가 권한이 제한된 계정으로
실행된다. 중간에 실패하면 로그인 상태를 복구하지 못해 뒤따르는 TC 가 연쇄로 무너진
전례가 있다(회귀 7·13·14차). 복구 절차를 합의한 뒤에만 붙인다.

### ⑤ 스테일 브랜치 `agent/add-next-task-handoff` 삭제

2026-08-11 에 판 작업용 브랜치이고 `main`의 조상(고유 커밋 0개, `git diff` 비어 있음
— 2026-08-25 실측)이라 지워도 내용은 잃지 않는다. 로컬·`origin` 양쪽에 남아 있다.
승인하시면:

```bash
git branch -d agent/add-next-task-handoff
git push origin --delete agent/add-next-task-handoff
```

### ⑥ ~~`close_examine` no-dialog 경로를 고칠지~~ — 2026-08-31 승인·완료

사용자가 "① OCR 판별 후 재시도"를 골랐고, 실측해 보니 OCR(배너 2202)이 종료 직후 다른 창에
가려 깨져 쓸 수 없었다. 같은 목적(삼켜졌을 때만 재시도)을 더 확실한 신호인
`STUDY.StudyStatus` 로 달성했다 — 2-C절 참고. 판별 수단을 바꾼 이유를 함께 보고했다.

### ⑦ `WF_14` "목록 전 행 열거 완주" 서브체크를 어떻게 고칠지 (합의 대기)

근본 원인은 2026-08-31에 라이브로 확정됐다(2-D절). 두 가지가 섞여 있다.

- **A. 행이 owner-draw 라 자식 창이 없다.** `system.account` 의 행은
  `core.ui.children(row.hwnd, 3)` 으로 자식이 **0개**인데 그 rect 를 OCR 하면
  `service`/`admin` 이 실제로 그려져 있다. `row_signature()` 가 전제하는
  "자식 컨트롤 `WM_GETTEXT`" 로는 **원천적으로** 읽을 수 없다.
- **B. `patient.physician` 은 애초에 다른 화면 요소를 보고 있다.** `visible_rows()` 가
  잡은 "3행"은 의사 명단이 아니라 MWL 역할 매핑 콤보다 — `PHYSICIAN` 테이블(0행)과
  무관하다.

**제품 결함이 아니라 자동화의 읽기 방식이 이 컨트롤 구조에 안 맞는 것이다.** 두 원인
모두 `stop=False` 서브체크 안에 갇혀 다른 판정(Step 7(c) 실제 값 대조, PASS)을 오염시키지
않아 2026-08-27 도입 이후 드러나지 않았다.

범위가 `core/setting_lists.py` 전반의 재설계라 방향을 먼저 정하는 편이 낫다.

1. **전면 재설계(권장, 사용자 승인 2026-08-31).** `row_signature()` 를 `core/uitext.ocr()`
   기반으로 다시 만들고(`setting_values.py` 가 이미 값 콤보에 OCR 을 쓴다), `LIST_PAGES`
   의 각 페이지가 `ROW_COUNT_QUERIES` 가 가리키는 DB 테이블과 **같은 화면 요소**를 보는지
   전수 재확인한다. 2026-08-25 오인(스크롤로 같은 HWND 재사용)이 재발하지 않게 스크롤
   전후 겹침 증명은 유지한다.
2. **범위 축소.** 읽을 수 있는 페이지만 남기고 owner-draw 페이지는 `LIST_PAGES` 에서
   빼거나 MANUAL 로 내린다. 빠르지만 커버리지가 줄고, "왜 뺐는지"를 근거로 남겨야 한다.
3. **보류.** 지금은 `stop=False` 라 다른 판정을 오염시키지 않으므로 전체 회귀를 먼저
   돌리고, 회귀 결과를 보고 우선순위를 다시 정한다.

#### 13개 페이지 전수 라이브 확인 결과 (2026-08-31, 옵션 1 착수 전 정찰)

옵션 1을 시작하기 전에 `LIST_PAGES` 13개 페이지 전부를 로그인된 Viewer에서 OCR로
읽어 실제 화면 요소를 확인했다(스크롤 전 1회차 스냅샷, 진단 스크립트는 삭제).
**"OCR 로 바꾸면 다 해결된다"가 아니라 페이지마다 원인이 다른 4가지 유형이 섞여
있었다** — 그래서 옵션 1의 실제 범위는 처음 생각보다 크다.

| 유형 | 해당 페이지 | 증상 | 필요한 조치 |
|---|---|---|---|
| ① 정상 — OCR 만으로 해결 — **2026-08-31 완료** | `system.account`(2/2 일치), `dicom.mwl`/`dicom.storage`/`dicom.print`(각 1/1 일치) | 자식 창이 없어 텍스트를 못 읽을 뿐, 화면 요소·개수는 이미 맞다 | `row_signature()` OCR 전환 + 스크롤 단축 + 위치 기반 키징으로 완료. 라이브 검증: 4곳 모두 "불완전" 목록에서 빠짐, 전체 판정 회귀 없음 |
| ③-a `display.lut` — **2026-08-31 완료** | `display.lut`(3/12 → 3/3) | `../지식/` Service Manual 실측 + DB 직접 조회로 확정 — `LUT_ITEM`은 LUT **개수**가 아니라 LUT 곡선의 **제어점**을 저장한다(`LUTKey`+`Order`+`X`+`Y`, LUT 3개 × 점 4개 = 12행). 화면의 3행(ScreenLUT/StorageLUT/ProcessLUT)과 비교하려면 `COUNT(DISTINCT LUTKey)`를 써야 했다 | `ROW_COUNT_QUERIES["display.lut"]` 쿼리 수정. 라이브 검증: "불완전" 목록에서 빠짐(`Reports/Result_20260831_153657.json`), 전체 판정 회귀 없음 |
| ② 내용은 맞는데 스크롤이 끝까지 못 감 — **전부 완료(2026-08-31/09-01)** | ~~`tool.predefined_text`(5/7)~~→**7/7**, ~~`study.reject_retake`(5/7)~~→**7/7**, ~~`dicom.tag_mapping`(9/17)~~→**17/17**(2026-09-01, 뷰포트 클리핑 수정), ~~`qc.scheduler`(20→21/23)~~→**완료**(스크롤은 진짜 바닥까지 도달, 남은 2행 격차는 스크롤 문제가 아니라 제품이 의도적으로 숨기는 항목임을 사양서로 확정 — B.32/2-J절, 개수 증명만 뺐다) | `../지식/` Service Manual 실측으로 **추정이 아니라 확정**됐다 — 화면에서 읽은 항목이 사양서에 적힌 전체 목록의 **정확히 앞부분과 순서까지 일치**한다(`predefined_text` 기본 7종 L/R/LCC/RCC/LMLO/**RMLO/IMPLANT** 중 앞 5개, `reject_retake` 사유 Type 7종 중 앞 5개 — 나머지 2종은 **Double Exposure, Others**, `tag_mapping` Internal Tag 17종 중 앞 8개). `dicom.tag_mapping`은 근본 원인이 스크롤 잡음이 아니라 **뷰포트 클리핑**이었다(2-F절) — 고친 뒤 17/17 완전 일치. `qc.scheduler`의 남은 2행은 사양서2 8492~8511행("일반/-d 모드에서 Geometry Calibration(Tomo) 항목이 안 보임")·Service Manual 3749행("지원 안 하는 QC 항목은 표시 안 됨")으로 확정된 제품 설계다(B.32) | `tag_mapping`: `_list_viewport()`/`_confidently_visible()`. `qc.scheduler`: `ROW_COUNT_QUERIES`에서 매핑을 뺐다(정지·연속 증명만으로 판정 — 매핑 없는 다른 페이지와 같은 처리, 근거는 주석에 남김) |
| ~~③ DB 카운트가 화면과 다른 것을 센다(개념 불일치)~~ → **④로 재분류, 2026-09-01 완료** | ~~`display.overlay`(화면 28 vs DB 8)~~→**8/8** | ~~`../지식/` Service Manual·Operation Manual에 명시적으로 확인됨 — 화면은 "표시 가능 항목"(고정 카탈로그), DB `OVERLAY_ITEM`은 "실제로 추가한 것"만 저장 — 같은 것을 세고 있지 않다~~ **이 결론 자체가 틀렸다(2-G절/`../프로젝트_상세.md` B.29).** 라이브로 컨트롤 트리를 덤프해 보니 이 페이지엔 독립된 목록이 **셋**(카탈로그/Top/Bottom) 있고, `visible_rows()`가 셋을 안 가리고 섞은 것뿐이었다(실측 카탈로그 화면표시분 20 + Top 6 + Bottom 2 = 28 — "28"은 카탈로그 크기가 아니라 우연의 합). `../지식/` Service Manual 4.4.2 의 진짜 카탈로그는 34개라 애초에 28과도 안 맞았다 | `_collect_overlay()`가 카탈로그를 빼고 Top+Bottom만 훑도록 고쳤다(④와 동일한 "범위 제한" 해법). 라이브 검증: "불완전" 목록에서 빠짐(`Reports/Result_20260831_204935.json`), 전체 판정 회귀 없음 |
| ~~④ 화면에 서로 다른 목록이 섞여 잡힘(교차 오염)~~ → **2026-09-01 완료** | ~~`procedure.procedure`(Procedure 카탈로그 14~15개 + 우측 View Position 약어 4개가 뒤섞여 19개로 잡힘)~~→**15/15**, ~~`dicom.print_overlay`(독립된 `ListCtrl` 넷)~~→**6/6**(Overlay 이름 목록에서 행을 선택해야 Position 목록 셋이 채워짐을 실측으로 확인, B.31) | `visible_rows()` 가 페이지 전체에서 `ListItem` 텍스트만 보고 잡아, 같은 화면의 다른 목록(측면 패널)까지 함께 주워 담는다. `display.overlay`(위 ③→④)도 같은 원인이었다 | `procedure.procedure`: `SINGLE_LIST_CONTROL` + `sweep()` 라우팅. `print_overlay`: `_collect_print_overlay()`가 Overlay 이름마다 행을 선택하며 Position 목록 셋(id 2486/2487/2488)을 모은다(카탈로그·이름 목록 자체는 제외) |
| ~~⑤ 화면 요소 자체가 틀림(오탐)~~ → **2026-09-01 완료, 실제로는 ④와 같은 교차 오염이었다** | ~~`patient.physician`(2x2 그리드 `ListCtrl` 넷 중 셋은 비어 있고 하나만 3행)~~→**0/0**. 라벨을 OCR로 읽으니 진짜 대상은 "Referring/Reading/Performing Physician"(id 2318/2319/2320, 셋 다 0행) 이었고, 걸리던 3행짜리 그리드는 "Performing Physician Order"(id 2321, MWL 역할 매핑 콤보 — B.24 에서 이미 확인된 것과 같은 컨트롤)였다 | 대상 컨트롤을 처음부터 잘못 잡고 있었다 — "오탐"이 아니라 ④와 같은 교차 오염이었다(B.31) | `_collect_multi_list(ui, (2318, 2319, 2320), ...)`로 진짜 세 목록만 합쳐 훑는다. 부수적으로 `walk()`가 "행 0개 = 무조건 실패"로 처리하던 결함도 발견해 `expected_count==0`일 때만 빈 목록을 완전한 열거로 인정하도록 고쳤다 |

**결론(2026-09-01 갱신)**: ①(4곳)·③-a(`display.lut`)·②의 3곳
(`tool.predefined_text`/`study.reject_retake`/`dicom.tag_mapping`)·구
③(`display.overlay`, ④로 재분류)·**④(`procedure.procedure`/`dicom.print_overlay`)·
구⑤(`patient.physician`, 실제론 ④와 같은 교차 오염)까지 전부 완료됐다 —
**9곳 전부 완료됐다.** `qc.scheduler`만 넷(②의 tag_mapping 제외)과 달리
진짜 제품 설계 차이였다 — 사양서2·Service Manual로 "일부 QC 항목은 연결
모델/실행 모드에 따라 의도적으로 숨겨진다"는 것을 확정하고, 그 페이지만
개수 증명을 뺐다(B.32/2-J절). "목록 전 행 열거 완주" 서브체크는 이제 9개
페이지 전부 자동화 결함 없이 정상 판정된다.

#### 옵션 1 착수 — OCR 폴백 구현, 그런데 라이브 검증에서 새 문제를 만났다 (2026-08-31)

사용자가 "가능한 만큼 다"(②③④⑤ 포함)를 승인해 `row_signature()`에 OCR 폴백을
구현했다(자식 컨트롤 텍스트가 없을 때만 `core/uitext.ocr()`로 읽는다. 자식 텍스트가
있는 페이지는 그대로 두어 속도·정확도를 안 건드렸다). `_screen`/`walk`/`collect`/
`sweep`에 `tesseract_exe`를 threading 했고, `tests/workflow14.py`의 두 `sweep()`
호출부에 이미 있던 `tess` 변수를 연결했다. 단위시험 3건 신설
(`tests/test_setting_lists.py::RowSignatureOCRTest` — 자식 텍스트가 있으면 OCR을
안 부른다 / 없으면 OCR로 폴백한다 / OCR도 실패하면 빈 문자열). 정적 검사 전부 통과,
단위시험 96 → **106건 OK**.

**라이브 재검증(`Reports/Result_20260831_132230.json`) 결과 — 예상과 다른 새 문제가
나왔다.**

- **좋아진 것(확인됨)**: `dicom.mwl`/`dicom.storage`/`dicom.print` 3곳이 "불완전"
  목록에서 완전히 빠졌다 — 유형 ①에서 예측한 대로다.
- **예상과 다르게 `system.account`는 여전히 FAIL 한다 — 이번엔 다른 이유로.**
  자식 텍스트 대신 OCR로 읽게 됐더니, **똑같은 화면을 두 번 OCR 해도 매번 문구가
  똑같이 안 나온다.** 실측: `'service service Servi... O'` (1회차) →
  `'service service Servi... O | ea'` (스크롤 뒤 재확인, 사실상 같은 화면인데 노이즈
  문자 `"| ea"`가 붙었다). `overlap()`은 **완전 일치**를 요구하므로 이 한 글자 차이가
  "겹치는 행이 없다"(건너뛰었을 가능성)로 잡혀 매번 FAIL 한다. 같은 패턴이
  `tool.predefined_text`/`study.reject_retake`/`procedure.procedure`/
  `dicom.print_overlay`/`dicom.tag_mapping`/`qc.scheduler`에서도 나타났다 — 전부
  "스크롤 1회째에 이전 화면과 겹치는 행이 없다"로 FAIL.
- **더 걱정되는 점 — 이 노이즈가 실제 판정(Step 7(c))의 신뢰도도 갉아먹을 수 있다.**
  `compare()`/`compare_sweep()`는 **서명(=signature) 문자열을 dict 키로 써서** 대조
  전후 같은 행을 짝짓는다. OCR 노이즈로 같은 행이 대조 전/후에 다른 서명을 내면,
  그 행은 "값이 같다"도 "값이 다르다"도 아니고 **조용히 짝이 안 맞아 비교 대상에서
  빠진다.** 실측: 이번 실행에서 Step 7(c)가 비교한 행 수가 **109개로 줄었다**
  (직전 KeyError 픽스 검증 때는 123개, 2026-08-31 05:57 리포트) — PASS 자체는 여전히
  났지만(달라진 항목 0), **무엇을 비교했는지의 폭이 줄었다는 뜻**이라 이 하락이
  OCR 노이즈 때문인지 이번 실행에서 실제로 더 적게 나온 것인지 아직 확정하지
  않았다.
- 위 문제는 3중 증명 중 "정지 증명"/"연속 증명"이 **정확히 일치**를 요구하도록
  설계됐기 때문이다(2026-08-25 재발 방지 — 아무 문구나 비슷하면 같다고 보면 실제로
  건너뛴 행도 "같다"고 오판할 수 있다). OCR은 캡처마다 결과가 미세하게 달라질 수
  있어(안티에일리어싱·포커스 하이라이트·커서 등) **애초에 "정확히 일치"라는 전제와
  안 맞는 입력**이다.

**해결 — 사용자가 "범위 축소"를 선택(2026-08-31).** `walk()`에 "OCR 로 읽었고
+ 첫 화면에서 이미 DB 원천 행 수와 정확히 같은 개수를 봤을 때만" 재확인 스크롤을
건너뛰는 조건을 추가했다(자식 텍스트 기반 목록은 기존 3중 증명을 그대로 다 거친다 —
동작 변경 없음). 라이브 재검증(`Reports/Result_20260831_140841.json`)에서
`system.account`/`dicom.mwl`/`dicom.storage`/`dicom.print` 4곳이 "불완전" 목록에서
완전히 빠졌고 전체 판정(19 PASS/4 FAIL)은 그대로 유지됐다(회귀 없음). 단위시험
4건 신설(`WalkOCRShortCircuitTest`).

**이어서 발견한 잔여 문제 — Step 7(c) 실제 값 비교의 비교 대상 행 수가 조용히
줄었다.** `compare()`/`compare_sweep()`은 서명 문자열을 **딕셔너리 키**로 써서
Export 전/후 두 번의 `sweep()` 호출(서로 다른 시점, 훨씬 떨어진 Step) 사이에서 같은
행을 짝짓는다. OCR 노이즈로 같은 행이 두 시점에 다른 문구로 읽히면 **값이 안 바뀐
행도 짝이 안 맞아 조용히 비교 대상에서 빠진다**(FAIL 로도 안 드러난다). 실측:
`KeyError` 픽스만 있던 시점(OCR 이전) 123행 비교 → OCR 폴백 도입 후 **109행**으로
줄었다(스크롤 단축 여부와 무관 — 단축은 같은 스윕 안의 문제만 막고, 이건 서로 다른
스윕 사이의 문제라 못 막는다).

**조치(사용자 승인 후 진행) — OCR 로 읽은 행은 서명 대신 위치를 키로 쓴다.**
`../프로젝트_상세.md` B.14("식별 컬럼이 없으면 행 순서로 짝짓는다")와 같은 해법이다.
`collect()`의 `on_row`가 `_child_signature(row) is None`(=OCR 로 읽었다)이면
`<OCR 행 #N>`(N=열거 순서)을 키로 쓰고, 문구 재확인("앞 행을 누르며 목록이
움직였는지")도 생략한다 — OCR 문구 자체가 불안정해 그 재확인이 오히려 오탐을
만들기 때문이다. 자식 텍스트 기반 행은 기존 방식(서명 키 + 재확인) 그대로다.
단위시험 2건 신설(`CollectOCRKeyingTest`).

**라이브 재검증(`Reports/Result_20260831_145217.json`) — 109 → 117행으로
회복됐다.** 123행에는 못 미친다. 남은 6행 격차는 OCR 노이즈가 아니라 **아직
손대지 않은 구조적 문제**(②스크롤이 DB 개수까지 못 내려가는 페이지들의 전/후 노출
범위 차이, ④교차 오염된 두 목록의 항목 수가 시점마다 다를 수 있음)로 보인다 —
이 픽스의 책임 범위(노이즈로 인한 짝 어긋남) 밖이다. 전체 판정은 여전히 19 PASS/4
FAIL 로 동일(회귀 없음), "달라진 항목"/"한쪽에만 있는 페이지"는 여전히 비어 있다
(PASS 유지).

정적 검사 전부 통과, 단위시험 96 → **112건 OK**(OCR 폴백 3 + 스크롤 단축 4 + 키징
2건).

#### `display.lut` 완료 + 스크롤 잡음 내성(fuzzy 매칭) 구현 (2026-08-31, 이어진 세션)

사용자가 "구조적 문제 중 정보를 주면 풀리는 게 있냐"고 물어 `../지식/` 사양서를
전수 조사하고 DB를 직접 조회했다(결과는 5절 ⑦ "13개 페이지 전수 라이브 확인
결과" 표 참고). **`display.lut`는 그 자리에서 바로 고쳤다**(`LUT_ITEM`이 LUT
개수가 아니라 곡선 제어점을 저장 — `COUNT(DISTINCT LUTKey)`로 수정, 라이브
검증 완료, "불완전" 목록에서 빠짐).

**스크롤 미완주 4곳은 사양서로 "제품이 일부만 보여준다"가 아니라 "자동화가
스크롤을 끝까지 못 한다"임이 확정됐다** — 라이브로 스크롤 메커니즘 자체를
확인했다(`tool.predefined_text`). 같은 5개 HWND 가 **가상 목록으로 재사용**되며
(2026-08-25 문서에 이미 기록된 패턴) 매 스크롤마다 정확히 1행씩 새 내용으로
바뀐다(`L,R,LCC,RCC,LMLO` → `R,LCC,RCC,LMLO,RMLO` → `LCC,RCC,LMLO,RMLO,IMPLANT`).
**스크롤 자체는 정상 작동한다** — 막힌 것은 순수하게 OCR 잡음이 정지/연속
증명(완전 일치 요구)을 깨는 문제였다. 잡음 패턴도 확인했다 — **항상 진짜
문구 뒤에 짧은 잡음이 붙는다**(`"LCC"`→`"LCC i"`, `"RCC"`→`"RCC (]"`, 대개
1~2자, 정규화 후에는 더 짧아진다).

**조치 — 접두사 관계 + 작은 길이 차이 상한으로 fuzzy 매칭.** `_rows_match(a, b,
fuzzy)`를 추가해 `fuzzy=True`(OCR 기반)일 때만 정규화 후 한쪽이 다른 쪽의
접두사이고 길이 차이가 `MAX_OCR_NOISE_CHARS`(=2) 이하면 같은 행으로 본다.
`fuzzy=False`(자식 텍스트, 잡음 없음)는 기존처럼 완전 일치만 인정해 2026-08-25
재발 방지 설계를 그대로 지킨다. **상한을 2로 낮게 잡은 이유** — `"ACR
Phantom"` 대 `"ACR Phantom (3D-N)"`처럼 접두사 관계지만 **실제로 다른 행**인
경우(QC Scheduler에 있음)가 정규화 후 3자 차이라, 상한을 3 이상으로 잡으면
이 둘을 같다고 오판해 진짜 건너뛴 행을 놓칠 위험이 있다. `overlap()`과
"정지 증명"(스크린 비교) 양쪽에 적용했다. 단위시험 7건 신설
(`RowsMatchFuzzyTest` 5건 — 실측 잡음 샘플이 전부 통과하는지, `"ACR Phantom"`
류 오판이 없는지 포함, `WalkFuzzyIntegrationTest` 2건 — `tool.predefined_text`
실측 시퀀스로 7개 전부 복원되는지, fuzzy 를 켜도 진짜 skip 은 여전히 잡히는지).
정적 검사 전부 통과, 단위시험 112 → **119건 OK**.

**라이브 재검증(`Reports/Result_20260831_161812.json`, 1937초) — 2곳 완료,
2곳 부분 개선.**

| 페이지 | 전 | 후 | 상태 |
|---|---|---|---|
| `tool.predefined_text` | 5/7 | **7/7** | 완료 |
| `study.reject_retake` | 5/7 | **7/7** | 완료 |
| `dicom.tag_mapping` | 8/17 | 9/17 | 부분 개선(원인 미확정) |
| `qc.scheduler` | 20/23 | 20/23 | 무변화(원인 미확정) |

전체 판정은 여전히 19 PASS/4 FAIL(회귀 없음), Step 7(c) 비교 행 수는
117→**122행**으로 더 회복됐다(원래 기준 123행에 근접). `tag_mapping`/
`qc.scheduler`가 왜 fuzzy 매칭으로도 완전히 안 풀렸는지는 **아직 조사하지
않았다** — 다음에 할 것.

#### `dicom.tag_mapping`/`qc.scheduler` 원인 확정 및 수정 (2026-09-01)

라이브로 두 페이지를 스크롤하며 화면 서명을 전부 출력해 `tool.predefined_text`
(해결됨)와 잡음 패턴을 직접 비교했다. **패턴 자체가 달랐다** —
`tool.predefined_text`는 진짜 문구 **뒤**에 잡음이 붙었는데, 이 둘은 매
화면의 **마지막 행**에서만 단어 **중간** 글자가 바뀌었다(`"Age"`→`"Aae"`,
`"Study"`→`"Studv"`). 기존 fuzzy 매칭(접두사+길이차)이 전제하는 패턴과
달라 안 걸러진 것이었다.

첫 진단(행 높이 비교, 뷰포트 아래로 잘린 행은 짧게 보고될 것이라 추정)은
라이브 재검증에서 **틀린 것으로 드러났다** — `core.ui.GetWindowRect`는
잘린 행도 명목상 크기(35px) 그대로 보고한다. 컨트롤 트리를 덤프해 행을
감싸는 `ScrollWnd`(뷰포트)를 찾아 그 rect와 행 rect를 직접 대조하니,
마지막 행(rect top=437~bottom=472)이 뷰포트 bottom(460)보다 12px 튀어
나와 있었다 — 이 튀어나온 부분(23px만 실제로 그려짐)을 OCR 하면서 단어
중간이 깨진 것이다. 상세 경위는 `../프로젝트_상세.md` B.28 참고.

`_list_viewport()`가 행과 좌우 경계가 일치하는 `ScrollWnd`를 찾고,
`_confidently_visible()`이 뷰포트 상하 경계를 벗어나는 행을 화면에서 뺀다
(`core/setting_lists.py`, `_screen()`에 적용). 뷰포트를 못 찾으면
아무것도 빼지 않는다.

**라이브 재검증(`Reports/Result_20260831_194615.json`) — `dicom.tag_mapping`
17/17 완전 해결(gap 0), `qc.scheduler` 20/23 → 21/23 개선(gap 0, 스크롤이
실제 바닥까지 도달 확인).** `qc.scheduler`의 남은 2행 격차는 DB
`QC_SCHEDULE.QCType`을 직접 조회해 확인했다 — Gantry 그룹이 DB엔 12개
코드(51~62)가 있는데 화면엔 정확히 10개 행만 그려진다. 스크롤 결함이
아니라 `display.overlay`와 같은 개념 불일치(유형③) 후보로 재분류한다 —
별도 조사가 더 필요하다(사양서/DB로 이 2개 코드의 정체 확인).

전체 판정은 여전히 FAIL(원인은 3-A UPS 제품 결함, 회귀 없음), Step 7(c)
"Setting 목록 행 상세값 복원"은 PASS(128행/1768항목, 달라진 항목 0)로
비교 폭도 더 넓어졌다(122→128행). 단위시험 119 → **128건 OK**.

---

## 6. 다음 세션용 프롬프트

```text
Bellalun Viewer QA 자동화를 이어서 진행해줘.

이전 세션(2026-08-31)에서 P0 #1~#4를 전부 끝냈다:
- #1 WF_07/XIPL_04 wait_new_group 전환 (판정 동일 + 실측 단축, 2-C절)
- #2 run-wf14의 KeyError 자동화 결함 수정 (2-D절)
- #3 run-wf10 비기본 Procedure 매핑 검증 (PASS 11/11, 2-D절)
- #4 cold_start 주 모니터 가드 — 재사용 경로가 가드를 아예 평가하지 않던 결함 발견·수정
  (2-E절)

그 다음 "목록 전 행 열거 완주" 서브체크(WF_14 Step 7)를 깊게 팠다 — 사용자가
"구조적 문제 중 정보를 주면 풀리는 게 있냐"고 물어 `../지식/` 사양서를 전수 조사하고
DB를 직접 조회했다. **문제 있던 9개 페이지를 전부 완전히 해결했다**(system.account,
dicom.mwl/storage/print — OCR 폴백 + 위치 기반 키징; display.lut — DB 쿼리가 곡선
제어점을 세고 있던 버그 수정; tool.predefined_text, study.reject_retake, dicom.tag_mapping
— tag_mapping 은 스크롤 잡음이 아니라 **뷰포트 클리핑**이 근본 원인이었다(2026-09-01,
2-F절/`../프로젝트_상세.md` B.28), 17/17 완전 일치; display.overlay/procedure.procedure/
dicom.print_overlay/patient.physician — 넷 다 "개념 불일치"나 "오탐"으로 처음
결론지었다가 실제로는 **같은 종류의 교차 오염**(화면에 목적이 다른 목록 여러 개가
섞여 `visible_rows()`가 구분 못 함)이었음이 라이브 컨트롤 트리 조사로 드러났다
(2-G~2-I절/B.29~B.31), 각각 8/8·15/15·6/6·0/0 완전 일치; **qc.scheduler — 넷과
달리 이번엔 진짜 제품 설계 차이였다**(사양서2 8492~8511행·Service Manual 3749행이
"일부 QC 항목은 연결 모델/실행 모드에 따라 의도적으로 숨겨진다"고 명시 — 라이브로
교차 오염 없음도 먼저 확인한 뒤 사양서로 최종 확정, 2-J절/B.32), 개수 증명만 뺐다).
매 단계 라이브로 재검증했고 전체 판정(원인은 이미 알려진 UPS 제품 결함)은 한 번도
안 바뀌었다(회귀 없음). 자세한 경위는 NEXT_WORK.md 5절 ⑦과 2-D~2-J절,
`../프로젝트_상세.md` B.23~B.32를 참고해라.

먼저 auto/AGENTS.md, auto/progress.md, auto/NEXT_WORK.md(전체, 특히 5절 ⑦)를 읽어
상태를 파악해라. TC 원문은 Bellalun_Viewer_기본기능_Checklist_개정본.xlsx의
`개정 TC` 시트만 기준으로 삼는다. 전체 저장소나 Reports/Evidence/Log를 무조건 탐색하지
마라.

**0단계 - 환경 확인 (가장 먼저, 매번)**
python run.py portability-check 의 "관리자 권한"이 True 인지 확인해라. 그리고 물리
콘솔 화면이 잠겨 있는지 확인해라 - GetForegroundWindow 타이틀이 "Windows 기본 잠금
화면"인지, 또는 EnumWindows로 그 타이틀을 가진 창이 있는지 본다(타이틀이 비어 있는
hwnd=0 만으로 "풀렸다"고 판단하지 마라). 잠겨 있으면 UI 자동화를 억지로 실행하지 말고
그 사실만 보고해라.

**TC를 단독 실행할 때의 전제(2026-08-31 실측)**
reset-environment가 복원하는 기준 스냅샷에는 DICOM 서버 등록이 없다(MWL/Storage/Print
모두 0행). DICOM 전송이나 MWL을 쓰는 TC(run-wf07/run-wf10 등)를 단독으로 돌리기 전에
python run.py setup-dicom 을 한 번 실행해라(setup-storage는 Storage만 등록해 MWL이
필요한 TC가 FAIL 한다).

**관찰을 이어갈 것**
close_examine 의 삼켜진 클릭은 flows.close_examine_confirmed 로 고쳤지만(팝업이 안 뜨고
StudyStatus 도 안 바뀐 경우에만 재시도), **간헐 실패가 재현되지 않아 재시도 경로 자체는
라이브로 타 보지 못했다.** 전체 회귀 결과에서 WF_07 Step 5 판정의 closed.attempts 값을
확인해라 - 1보다 크면 실제로 삼켜진 클릭을 복구한 것이다.

P0 (환경이 확인되면 이 순서로 — "목록 전 행 열거 완주" 서브체크는 9개 페이지
전부 끝났으니 이제 나머지 재검증으로 넘어간다)
1. 나머지 재검증 - run-wf04 -> run-wf06 (close_view_study), run-wf13 (로그인 콤보),
   run-wf15 (Dose Overlay 전제). 여기부터가 다음 세션의 첫 실행 항목이다.
   run-xipl-05/wf07/xipl-04/wf10/wf14 는 2026-08-28~09-01 확인 완료.
2. XIPL_05 불합격 경계 검증(3절 #1) - Fiber 콤보 항목 구성을 다시 확인해라.
3. 전부 통과하면 전체 회귀를 처음부터 1회 돌려 실제 완료 결과만 기록해라. 시작 전에
   적용한 변경·변경 전후 실행 시간·판정 동일성·남은 위험·예상 소요 시간·Viewer/화면
   준비 조건을 먼저 보고하고 진행해라.

**작업 방식 참고**
- 세션이 길어질 수 있다 — 라이브 UI 자동화 1회(run-wf14 등)가 20~30분씩 걸린다. 실행
  전에 마우스/키보드를 점유한다는 것을 알리고, 여러 개를 동시에 돌리지 마라(충돌한다).
- **하나의 CLI 세션(프로세스)이 끝나면 그 안에서 띄운 백그라운드 작업도 함께 끊긴다.**
  20~30분 걸리는 라이브 실행(run-wf14 등)은 `Start-Process -WindowStyle Hidden`으로
  세션과 완전히 분리된 OS 프로세스로 띄우고, 표준출력/에러를 파일로 리다이렉트해라
  (2026-09-01에 harness 자체의 백그라운드 추적이 세션 경계에서 한 번 끊긴 전례가 있다
  — 로그가 프로세스 종료 시점에야 플러시되니 중간 확인은 프로세스 생존 여부/CPU 시간
  변화로 판단해라).
- "구조적 문제/원인 불명"에 부딪히면 추측보다 먼저 `../지식/`(Service Manual·Operation
  Manual·사양서)과 DB를 직접 조회해 확인해라 — 이번 세션에서 그렇게 12곳을 풀었다.
- **고친 뒤 바로 라이브로 재검증해라 — 첫 진단이 틀릴 수 있다.** 2026-09-01에
  `dicom.tag_mapping`의 첫 수정(행 높이 비교)은 라이브 재검증에서 곧바로 "변화 없음"이
  드러나 틀린 전제(Win32 rect는 클리핑을 반영하지 않는다)였음을 알게 됐다 — 재진단
  (뷰포트 rect 대조)으로 다시 고쳐 해결했다. 코드만 보고 "이걸로 맞겠지"라고 다음
  단계로 넘어가지 않는다.
- **"설계 차이라 못 고친다"/"오탐이다"는 결론도 검증 대상이다.** `display.overlay`
  ("개념 불일치, 새 검증 필요")와 `patient.physician`("대상 컨트롤 자체가 틀렸다,
  오탐") 둘 다 그랬다 — 라이브로 컨트롤 트리를 덤프하고 라벨을 OCR로 읽어 보니
  실제로는 넷 다(`procedure.procedure`/`dicom.print_overlay` 포함) **같은 교차
  오염 버그**였다(2-G~2-I절). `display.overlay`의 근거 숫자("28")가 사양서 수치
  (34)와도 안 맞았는데 그 불일치를 미리 짚지 못했다 — 결론에 쓴 숫자·판단이 실제로
  무엇을 근거로 하는지 항상 라이브로 재확인해라.
- **개수가 이미 맞아도 끝난 게 아니다.** `patient.physician`의 대응 관계를
  확정한 뒤(0=0) "다 됐다"고 봤는데, 라이브 재검증에서 `walk()`가 "행이 0개면
  무조건 실패"로 처리하는 별개의 오래된 결함을 만났다(지금까지 다룬 목록이 전부
  DB 원천 1행 이상이라 이 전제가 안 깨졌을 뿐이다). 매 수정 뒤 라이브 재검증을
  거르지 않는 습관이 이번에도 숨은 문제를 잡아냈다(2-I절).
- 범위가 예상보다 커지면(이번 세션의 OCR 수정처럼) 중간에 멈추고 사용자에게 범위를
  확인해라 — 계속 "가능한 만큼" 넓히기보다 단계별로 승인받는 편이 나았다.

추가 리팩터링·속도 개선 (P0 항목이 안정적으로 통과한 뒤에)
- run-sys3d/run-ui(회귀 밖 명령)에 남은 demo_acquire_step 고정 대기도 wait_new_group으로
  바꿀지 판단해라 - 급하지 않다(P2). 바꾼다면 **대기 직후의 첫 UI 조작이 재시도를 갖고
  있는지 반드시 함께 확인해라** - 08-31에 XIPL_04가 정확히 그 이유로 실패했다.
- python run.py probe-preset3d 로 3D-N/3D-W Preset 목록 컨트롤 실측 -> XIPL_07에
  "새 Preset이 그 시점 Default를 물려받는가" 판정 추가.
- 반복되는 로그인·화면 진입·환자 검색·정리 흐름 중 아직 안 합친 것이 있는지 조사하되,
  진짜 동일한 로직만 합쳐라(비슷해 보여도 completed 여부·option·wait 값이 TC마다 다르면
  억지로 합치지 마라).
- 리팩터링은 작은 단위로 나누고 각 단위마다 정적 검사, 관련 개별 TC, 변경 전후 실행
  시간 비교를 수행해라. 동작을 바꾸지 않는 순수 기계적 중복 제거는 라이브 검증 없이
  정적 검사+단위시험만으로 커밋해도 되지만, 대기 방식처럼 실제 동작이 바뀌는 변경은
  반드시 라이브로 재검증한 뒤에만 "완료"로 기록해라.

검증·Git
- 긴 실행 전에 반드시: py_compile, tools/check_module_attrs.py,
  tools/check_self_attrs.py, tools/check_cleanup_stop.py,
  tools/check_regression_names.py, tools/traceability.py,
  python -m unittest discover -s tests -p "test_*.py"
  (`tests/install_package_flow.py:310` 경고는 기존 것이라 무시해도 된다 - 범위 밖 코드는
  근거 없이 건드리지 마라.)
- 문서를 갱신해라. 순서: ..\프로젝트_상세.md(기본 문서 - 먼저 갱신) ->
  python tools/render_docs.py -> README.md(포트폴리오 축약형) -> NEXT_WORK.md -> progress.md,
  필요할 때만 automation_scope.json/traceability.json.
- git status/diff/remote 검토 후 관련 파일만 commit 하고 같은 작업에서 별도 재승인 없이
  일반 push까지 수행해라. push한 브랜치와 commit SHA를 보고해라.
  Force Push·history 재작성 금지. config.json, Reports/, Evidence/, Log/, Cache/,
  Temp/, work/ 는 커밋하지 마라.
- 테스트하지 않은 것을 성공했다고 기록하지 마라. 이전 세션에서 이미 구현된 것과 이번
  세션에서 새로 한 것을 최종 보고에서 구분해라.
```
