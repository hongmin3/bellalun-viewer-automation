# 다음 작업 인수인계

## 다음 우선순위

### 0. [완료] 개정본 체크리스트로 TC 번호 전면 재정렬 (2026-08-19)

**기준 문서는 `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx`(시트 `개정 TC`)
하나다.** `AGENTS.md` 0절에 못박았다.

`지식\(TC) R-23-2346_...xlsx`는 **다른 문서**다. 같은 형태의 TC ID를 쓰지만 번호
매핑이 다르다. 이 둘을 혼동해 정상 구현된 `WF_02`를 "범위 불일치"로 잘못 강등한 적이
있다(사용자가 바로잡아 줬다). 확인해 보니 어긋난 것은 WF02 하나가 아니었다.

| 개정본 | Title | 코드가 쓰던 옛 번호 | 구현 파일 |
|---|---|---|---|
| WF_02 | 공통 2D/3D 검사 촬영 및 Tool 적용 | WF_02 (일치) | `tests/workflow02.py` |
| WF_03 | Image Overlay 및 Print Overlay 설정 | WF_04 | `tests/overlay_flows.py` |
| WF_04 | 2D 수동 DICOM Send | WF_05 | `tests/send_flows.py` |
| WF_08 | 2D/3D Film Print | WF_03 | `tests/workflow03.py` |
| WF_09 | Normal 및 Anonymous Export | WF_10 | `tests/dataflow.py`(판정부) |
| WF_10 | MWL Hospital Code와 Procedure 매핑 | WF_11 | `tests/settings.py`(판정부) |
| WF_11 / WF_12 | Image / Study Reject 및 Restore | WF_12 / WF_13 | `tests/dataflow.py`(판정부) |
| WF_13 | 계정 추가·수정 및 로그인 | WF_14 | `tests/settings.py`(판정부) |
| WF_14 | Setting Export 및 Import | WF_15 | `tests/settings.py`(판정부) |
| WF_16 | Kiosk 및 System Launcher | WF_18 | `tests/settings.py`(판정부) |

**적용한 것**

- `automation_scope.json`을 개정본에서 **직접 생성**했다(36 TC = FULL 12 / PARTIAL 4
  / MANUAL 20). 각 항목에 `title`을 넣어 개정본과 대조 가능하게 했다.
- 모듈의 `TCResult` ID, `run.py` 명령, 회귀 실행 순서를 개정본 번호로 재정렬했다.
  `run-wf03`=Overlay 설정, `run-wf04`=2D Send, **`run-wf08`=Film Print**(신설).
  이전 `run-wf05`는 없어졌다.
- 개정본에 없는 3D-N/3D-W 촬영은 TC 번호를 떼고 보조 항목
  `AUTOMATION_3D_ACQUISITION_3DN/_3DW`로 분리했다(`run-sys3d` 유지).
- `core/checklist.py`가 개정본(`개정 TC` 시트)에 결과를 기록한다.
- `overlay_flows.py`를 개정본 WF_03의 6단계 구조로 재작성했다. Send 판정은 WF_04가,
  Film 표시 확인은 WF_08이 하므로 중복을 제거하고 참조로 바꿨다.

**개정본에 없어 빠진 항목**: 이전 scope의 `WF_17`, `WF_18`,
`TC_System_compatibility_03/04`. 개정본 WorkFlow는 16까지이고
`TC_System_compatibility_*` 계열이 없다.

**개정본에만 있어 새로 등록한 항목**: `WF_16`(Kiosk 및 System Launcher).

### 1. [완료] `TC_XIPL_compatibility_04` 회귀 전용 실패 해결 (2026-08-19)

회귀 8·10·11차에서 3회 연속 같은 지점에서 실패했다. **원인은 저장 확인 팝업이었다.**

```
There are changes. Do you like to save them?    [Yes] [No]
```

`Close`를 누르면 제품이 이 팝업을 띄우는데 아무도 답하지 않아 모달이 이후 모든
클릭을 삼켰다. `close_examine`은 종료 옵션 팝업(버튼 3개)만 알고 있어 버튼이 3개
미만이면 그냥 반환했다. 이 팝업은 Yes/No 2개다.

회귀에서만 터진 이유: 직전 `XIPL_03`이 Post Reconstruction 파라미터를 변경해
"변경사항"이 생긴다. 단독 실행에는 변경이 없어 팝업이 뜨지 않는다.

**두 번 잘못 짚은 기록** (같은 실수를 반복하지 않기 위해 남긴다)

1. "대기 부족" → `_need` 상한 8초 → 20초. 같은 실패.
2. "검사가 열려 화면에 닿을 수 없다" → 보류 복구 분기 추가. 조건을 직접 만들어
   끄고 비교하니 없어도 정상 동작 → 제거.
3. 세 번째 추측 대신 `flows._screen_context`로 실패 시점 랜드마크·대화상자 문구·
   전체 화면 캡처를 남기게 했다. **다음 회귀에서 캡처가 답을 줬다.**

**첫 수정도 발동하지 않았다.** 이 팝업은 `WM_GETTEXT`로 문구를 읽을 수 없다
(`dialog.text` / `dialog_text` 모두 빈 문자열 — 실측). 문구 검사가 항상 실패해
핸들러가 건너뛰었다. `flows.read_dialog_message()`가 **OCR로** 읽도록 바꿔 해결했다.

**실측값** (2026-08-19)

```
팝업 rect : (728, 440, 1192, 641)
버튼      : id=501 Yes (좌, x=835) / id=500 No (우, x=965)
문구 영역 : 팝업 높이의 30~70% 구간, OCR psm 6
```

**문구 확인을 포기할 수 없는 이유**: 같은 상황에서 뜨는
`This study will be deleted. Are you sure?`도 버튼 구성이 **동일**하다(좌 501 / 우 500).
문구를 모른 채 좌측을 누르면 **검사가 삭제된다.** 그래서
`confirm_unsaved_changes`는 OCR 문구를 확인하고, 삭제 확인 팝업이면 손대지 않고,
**문구를 확정하지 못하면 클릭하지 않고 FlowError로 중단한다.**

**저장 여부는 Yes(저장)** — `close_examine`이 데이터를 잃지 않는 Suspend를 택하는
것과 같은 원칙이다. 공용 픽스처의 영상 조정 상태를 `WF_02` Expected 6/7과 `WF_08`
Film 비교가 근거로 쓰므로 버리면 뒤 TC가 흔들린다. `save_changes` 파라미터로 노출했다.

결과: `XIPL_04` PASS, 회귀 12차 `PASS 140 / FAIL 1`.

### 1-1. [완료] `XIPL_01` W1/W2 OCR 오독 대응 (2026-08-19)

XIPL_04를 고치자 XIPL_01이 실패했다. 원인은 **OCR 오독**이었다.

```
기대={'w1': 24380,  'w2': 66648}
실제={'w1': 243380, 'w2': 66648}     <- 3이 하나 더. w2는 정확히 일치
```

이 TC는 개정본 Expected 3("뷰어에 표시된 Histogram/Window Level과 XIPL의 값이 동일")
때문에 **양쪽 모두 화면 숫자를 OCR로 읽어** 비교한다. 단발 오독에 판정이 흔들리면
안 되므로, **불일치 시 양쪽을 재캡처해 다시 읽고** 시도 기록을 `actual`에 남긴다.
값이 정말 다르면 재판독해도 계속 다르므로 결함이 감춰지지 않는다.

### 2. [완료] Send 판정을 개정본 요구대로 강화 (2026-08-19)

이전 판정은 개정본 요구보다 느슨했다. 개정본 `WF_04` Expected를 항목별로 대조해
고쳤다.

| 개정본 Expected | 이전 | 지금 |
|---|---|---|
| 3. Queue 상태가 **Done** | Queue 등록만 확인 | `DICOM_STORAGE_QUEUE.State=7` 대조 |
| 4. 2D 객체 **1개** 수신 | ">=1건" | **정확히 1건** (`expect_count`) |
| 5. **4개 태그** 비교 | SOP UID + Patient ID | Patient ID / Study / Series / SOP UID |
| 2. **Selected Images** | all + selected 둘 다 | Selected만 (All은 `WF_06`) |

**수신 개수 버그**도 함께 고쳤다. 이전 대기 루프가 UID 하나만 보이면 즉시 break 해서
SCP 로그에 C-STORE 5건인데 판정에는 전부 "수신 1건"으로 기록됐다.
`_wait_received_stable()`이 개수가 3회 연속 같을 때까지 기다려 확정한다 — 이게 없으면
Selected(1개)와 All(전체)의 차이를 검증할 수 없다.

`WF_06`(All Images 및 Dose SR)도 신규 구현했다(`run-wf06`). Queue의 Image/DSR은
`ClassUID`로 구분한다(`DataType` 컬럼도 있지만 값의 의미를 실측 확정하지 못해
추측하지 않았다). RDSR 미수신 시 Demo 촬영 전제 문제이므로 MANUAL로 보고한다.

### 그 밖의 다음 후보

`TC_Basic_WorkFlow_04` / `05`는 **구현 완료**(아래 참고).

1. **WF05의 View창/Examined Send 경로** — Examine 경로(1148)는 자동화됐지만 나머지
   두 경로의 Send 진입점을 아직 못 찾았다. Examined 툴바 14개에는 Send가 없다.
2. ~~**`DICOM_STORAGE` 중복 정리**~~ — **해소 확인(2026-08-18 17:15 실측).**
   기준 스냅샷 복원 + `setup-dicom` 1회 실행 후 세 테이블 모두 1행이다
   (`DICOM_STORAGE` Key=17 BUNNY_TEST / `DICOM_PRINT` Key=13 PRINT_TEST /
   `DICOM_MWL` Key=6 MWL_TEST). 즉 `setup-dicom`이 매 실행마다 추가하는 게
   아니라, 이전에 본 7행은 **복원 전 누적분**이었다. 회귀는 항상 복원으로
   시작하므로 추가 조치가 필요 없다.
3. `TC_Basic_WorkFlow_06`(3D Send) — WF05 구조를 그대로 재사용할 수 있다.
4. `tests/dataflow.py`의 WF_07/10/12/13 판정 로직에 UI 드라이버 붙이기.
   WF10(익명 Export)은 `core/export_manager.py`의 `ANONYMOUS`(1031)를 쓰면 된다.

## 사양 대조로 확인한 불일치 — Storage Transfer Syntax (2026-08-18)

**확인 필요(제품 담당자 판단 대상).** 자동화 판정으로는 올리지 않고 기록만 한다.

DICOM Conformance Statement V1.3W1 "Association Initiation Policy / Proposed
Presentation Context Table"에 따르면 네트워크 Storage SCU가 제안하는 Transfer
Syntax는 다음 두 가지뿐이다.

| Abstract Syntax | Transfer Syntax |
|---|---|
| Digital Mammography X-ray Image Storage - For Presentation (`1.2.840.10008.5.1.4.1.1.1.2`) | Implicit VR LE (`1.2.840.10008.1.2`), Explicit VR LE (`1.2.840.10008.1.2.1`) |
| Breast tomosynthesis Image Storage (`1.2.840.10008.5.1.4.1.1.13.1.3`) | 같음 |
| X-Ray Radiation Dose SR Storage (`1.2.840.10008.5.1.4.1.1.88.67`) | 같음 |

같은 문서에서 **JPEG은 General Purpose DVD-RAM/USB 매체 저장 프로파일에만**
나온다. 네트워크 전송용 JPEG 계열 Transfer Syntax(`1.2.840.10008.1.2.4.*`)는
문서 전체에 **한 번도 선언돼 있지 않다**(grep으로 확인).

그런데 제품 `Setting > DICOM > Storage`의 Transfer Syntax 옵션(컨트롤 `2459`)에는
JPEG2000을 선택할 수 있고, 이 상태로 Send하면 conformant SCP 상대로 전송이
**실패**한다 — Bunny 로그 `1 - Rejected`, Viewer 로그 `Not Support class`.

확인할 것:
1. 이 옵션이 사양에서 빠진 것인지(문서 누락), 아니면 UI가 선언 범위 밖의 값을
   노출하는 것인지.
2. 노출이 의도된 것이라면 Conformance Statement에 추가돼야 한다.

자동화 쪽 조치: `tests/send_flows.py:_ensure_transfer_syntax`가 전송 전에
**선언된 값(Implicit VR LE)으로 되돌린다.** 테스트 SCP에 맞춘 우회가 아니라
사양 준수 상태를 만드는 것이므로 그대로 유지한다.

## 현재 검증된 상태 (2026-08-19 갱신)

- 저장소: GitHub `hongmin3/bellalun-viewer-automation`, 브랜치 `main`.
  로컬 경로는 PC마다 다르므로 문서에 하드코딩하지 않는다.
- 자동화 범위 총 39건 = **FULL 10 / PARTIAL 18 / MANUAL 11**
  (`python run.py list`로 확인).
- **FULL**: Install_01/02, WF_01/03, XIPL_01/02/03/04/05/06.
  `WF_02`는 체크리스트 원문과 구현 범위가 달라 **MANUAL로 내렸다**(위 0절 참고).
- `TC_XIPL_compatibility_05`는 2026-08-18 **전 단계 PASS**로 검증됐다. 시험 파라미터
  (`TEST_QC_2D_M.pim`/`TEST_QC_3D.eap`)는 제품 기본값 복사로 자동 생성한다.
  다만 그 내용이 Q.C 임계값 판정에 적절한지는 사용자 확인이 필요하다.
- `TC_XIPL_compatibility_06`의 이전 블로커(Noise reduction 슬라이더 OCR)는
  해결됐다. 원인은 타이밍/프로세스 경합이 아니라 Tesseract `--psm` 선택이었고
  (`psm 7`이 한 자리 숫자를 빈 문자열로 버림), `_ocr_integer`를 psm 6/7/8 다수결
  투표로 교체했다. 상세는 운영 지침 7절.
- `TC_XIPL_compatibility_03`은 Step 9가 **FAIL로 나오는 것이 정상**이다(제품 실제
  동작을 정확히 잡아낸 결과, GPU 무관 — 절대 완화하지 않는다). Step 10은 GPU
  미탑재 환경에서 SKIP된다.
- **보조 항목**: `AUTOMATION_3D_ACQUISITION_3DN`(3D-Narrow) / `_3DW`(3D-Wide) —
  `tests/system_compat.py`, `python run.py run-sys3d`. 개정본 TC가 아니다(0절).
  등록·Demo F8 촬영·`INSTANCE_GROUP.Type`/`ExposureMode`(`1/1`=3D-N, `1/2`=3D-W)는
  자동 판정하고, 장비 LCD·2430 패들·회전 각도는 MANUAL로 분리 기록한다. 그래서
  종합 판정은 MANUAL이다.
- 검증된 서버 등록값:
  - MWL: `MWL_TEST / MWL_SCP / 10.13.0.222:11112`
  - Storage: `BUNNY_TEST / Bunny / 127.0.0.1:3000` (유일한 `Use=1` Storage)
  - Print: `PRINT_TEST / PRINT_SCP / 10.13.0.222:11113`
- `setup-dicom`은 Storage뿐 아니라 **MWL도** `Use=1`로 자동 활성화한다
  (Print는 DB에 Use 컬럼이 없어 제외).
- `run.py`는 `data_dir`이 PC마다 다른 드라이브(C:/D:)에 있어도 모든 드라이브를
  탐색해 찾는다(`_resolve_data_dir`).

## 이 PC에서 아직 준비되지 않은 것

- (해결됨) DB 기준 스냅샷은 저장소 상위 `Baseline\` 폴더에서 자동으로 찾아
  복원한다. 2026-08-18 회귀에서 `AUTOMATION_ENVIRONMENT_RESET`이 PASS로 확인됐다.

- (해결됨) `TC_XIPL_compatibility_04`의 시험 Preset은 이제 **UI로 자동 삭제**한다
  (`tests/xipl_flows.py::_delete_test_presets`). 행은 `Type=0 AND Roll IN ('RL','RM')`
  으로 식별하고(제품 기본 Preset은 Roll이 비어 있다), 삭제 전후 전체 Key 집합을
  비교해 의도한 Key만 사라졌는지 확인한다. `core/db.py`는 여전히 조회 전용이다.

## 회귀 7차 (2026-08-18 16:56) — 연쇄 실패와 그 수정

`PASS 30 / FAIL 10` (17 TC). **FAIL 10건 전부가 첫 FAIL 하나의 결과였다.**
자세한 경위와 교훈은 `지식/[자동화 운영 지침]` 11절 사례를 볼 것. 요약:

`DB 복원(프로세스 전체 종료)` → `cold_start(force_restart=True)`로 재기동 →
로그인 성공 → **`ensure_patient_screen`이 화면이 그려지기 전 t=0에 판단** →
`open_main_menu`가 상태바를 못 찾고 15초 뒤 사망 → DICOM 등록 실패 →
MWL 미등록(`DB=[]`) → WF01/02/03/04, XIPL 01/02/03/06, WF05 연쇄 FAIL.

실측 기동 소요는 **약 36초**였다. 예산 부족이 아니라 **기다리지 않은 것**이다.

### 수정 (모두 실제 경로로 검증)

| 문제 | 조치 | 검증 |
|---|---|---|
| 화면 그려지기 전 조작 | `flows.wait_known_screen()` 추가, `ensure_patient_screen`이 랜드마크 출현까지 상한 60초 대기 | `setup-dicom` 재실행 → 해당 단계 **36.6s PASS** (이전 53.6s FAIL) |
| `Bellalun Service`를 죽이고 안 되살림 | 서비스는 SCM(`net stop`)으로 내리고 `start_app_services()`로 `finally`에서 복구 + RUNNING 확인 | `RUNNING → STOPPED → RUNNING` 왕복 실측 |
| 실패 시 진단 정보 유실 | `setup_all`이 기동 로그 + 마지막 화면 스크린샷을 남김 | 캡처 동작 확인 |
| 리포트가 연쇄를 안 드러냄 | 상단에 `[ 먼저 볼 것 ] 가장 앞선 FAIL` 추가 | 실패 리포트 재생성으로 확인 |
| 스텝 밖 소요시간 은폐 | TC 전체와 스텝 합계 차이가 5초 넘으면 명시 | — |
| `ui_flows.py`의 6초 고정 sleep | `statusbar.wait_ready()`로 아이콘 출현 대기로 교체 | 5초 이상 고정 sleep **0건** |
| Examined 창 컨트롤 즉시 판정 | `flows.wait_controls()`로 상한 대기 (`viewer_processing`, `overlay_flows`) | — |
| `_open_examined`가 `open_main_menu` 반환값 무시 | 실패 지점을 정확히 보고 | — |

### 읽는 사람을 위한 규칙

**FAIL 개수보다 가장 앞선 FAIL을 먼저 본다.** 그리고 **한 실행 안에서 뒤 TC가
통과했다는 사실은 앞 TC 실패를 환경 문제에서 제외하는 근거가 아니다** — 7차에서
`TC_XIPL_04/05`가 PASS해서 "환경은 정상"으로 보였지만, 그때쯤 Viewer가 이미 떠
있어 재사용된 것뿐이었다.

## 최신 회귀 결과 (2026-08-18 12:10)

**PASS 121 / FAIL 1 / MANUAL 6 / SKIP 1.** FAIL 1건은
`TC_XIPL_compatibility_03 Step 9`로 **제품 실제 결함을 잡아낸 정상 결과**다
(Apply 후 재진입 시 값이 기본값 복귀). GPU 무관하며 **절대 완화하지 않는다.**

- WF02 Window Level의 간헐 FAIL은 해소됐다. 원인은 Overlay가 꺼져 판정 근거
  (W1/W2)를 못 읽던 것이었고, WF02가 Overlay를 직접 보장하고 판정을 사양 기준
  (값 증감)으로 바꾼 뒤 연속 PASS한다. 다시 FAIL하면 먼저
  `CONFIGURATION.OVERLAY_ITEM`의 FieldID 113/134를 확인할 것.
- `TC_XIPL_compatibility_04`는 검증 9단계 전부 PASS이며 종합 MANUAL은 시험
  Preset 수동 삭제 안내 때문이다(회귀는 DB 복원으로 자동 해소).

## (해결됨) TC_04 반복 실행 — 2026-08-18 검증 완료

Preset UI 자동 삭제에 이어, 재실행을 막던 대화상자 2개를 처리해 **검증 8단계
전부 PASS / 3회 연속 재실행 성공**을 실측했다.

- `handle_duplicate_patient`가 `cls == "Button"`만 찾아 커스텀 버튼
  ("Use existing data")을 못 눌렀다 → 모달이 남아 이후 클릭이 전부 막혔고,
  그게 오해를 낳은 `Step 등록 실패: 0->4`의 정체였다(센 4개는 잔여 검사의 기본
  Procedure RCC/LCC/RMLO/LMLO). 이제 대화상자 **아래쪽 절반**에서 좌→우로 골라
  (제목줄 X 오클릭 방지) 누르고 **닫혔는지 확인**한다.
- TC_04가 검사를 닫지 않고 끝나 재실행 시 Examine 모드에서 시작됐다 →
  시작 시 잔여 검사를 닫는다(Q.C와 같은 종류의 전제 조건).
- 영상 없는 검사를 Close하면 `This study will be deleted. Are you sure?`가 뜬다
  → `flows.confirm_study_delete`가 처리(**사용자 승인**: 영상 없는 검사 삭제 허용.
  영상이 있으면 이 확인 자체가 뜨지 않는다). TC_04는 삭제 전후 STUDY Key를
  대조해 자기 환자 것 외에 사라지면 실패시킨다.

## Examined 화면 툴바 — 클릭으로 확인한 실측 결과 (2026-08-18)

메인 메뉴 > View 로 열리는 **Examined** 창의 우측 아이콘 툴바(y 256~296).
x좌표 = 화면 왼→오 순서.

| x | ctrl_id | 확인 방법 | 실제 기능 |
|---|---|---|---|
| 1190 | 2181 | 미확인 | `+` (추가) |
| 1236 | 2183 | 미확인 | 분할 보기 |
| 1282 | 2189 | 미확인 | 목록 보기 |
| 1328 | 2190 | 미확인 | 상세 목록 |
| 1374 | 2196 | 미확인 | 검사 내 검색(돋보기) |
| 1420 | 2188 | 미확인 | 프린터로 추정 |
| 1466 | 2191 | 미확인 | CD/디스크로 추정 |
| 1512 | **2184** | **클릭 확인** | **`Import Study`** (전송 아님! 아이콘 추정이 틀렸다) |
| 1558 | **2197** | **클릭 확인** | **`All Images` / `Selected` / `Cancel` 선택 대화상자** |
| 1604 | 2185 | 미확인 | 연필(편집) — 건드리지 말 것 |
| 1650 | 2186 | 미확인 | 휴지통(삭제) — **절대 누르지 말 것** |
| 1696 | 2193 | 미확인 | 자물쇠(잠금) — 건드리지 말 것 |
| 1742 | 2195 | 미확인 | ? |
| 1788 | 2192 | 미확인 | 열린 폴더 |

**교훈**: 아이콘 모양으로 추정한 기능이 실제와 달랐다(2184를 Send로 추정했으나
`Import Study`였다). 나머지도 **추정을 신뢰하지 말고 눌러서 확인**할 것. 단
삭제/잠금/편집 후보(2185/2186/2193)는 데이터를 훼손할 수 있으니 hover나 다른
방법으로 먼저 식별하라.

### `2197`은 `Move Image` — DICOM Send가 아니다 (클릭으로 확정)

`2197`을 누르면 **"Do you want to move all images of this study?"** 와
`All Images`(502) / `Selected`(501) / `Cancel`(500)이 뜬다. 여기서 `All Images`를
누르면 **`Move Image` 창**(다른 검사로 영상을 옮기는 기능)이 열린다. 문구의
"move"가 말 그대로였다.

확정 방법과 결과(2026-08-18 실측): Bunny(Storage SCP)를 `ensure_bunny()`로 띄우고
수신 폴더를 비운 뒤 `All Images`를 눌렀으나 **30초 동안 수신 파일 0개**였고 대신
`Move Image` 창이 떴다. 따라서 이 경로는 WF05가 찾는 DICOM Send가 아니다.
`Cancel`로 안전하게 빠져나왔다(아무것도 옮기지 않았다).

`Move Image` 창 컨트롤: 검색어 `2178`, 기간 사용자지정 `1109`, 돋보기 `2069`,
**Move `2071`**, **Cancel `1102`**.

**주의**: `All Images` / `Selected` 문구가 WF05 Step 5와 똑같아서 **이 대화상자를
Send로 오인하기 쉽다.** WF05의 Selected/All 선택은 다른 버튼에서 나오는 별개
대화상자일 가능성이 크다.

### `2191` = **Export Manager** — WF04의 Export 진입점 (확정)

`2191`을 누르면 **별도 최상위 창** `Export Manager`가 열린다
(프로세스 `EXPORT.MANAGER.exe`). Viewer 프로세스가 아니라 **`ViewerUi("EXPORT.MANAGER")`
로 따로 붙어야** 컨트롤이 열거된다(Viewer 쪽 `ui.controls()`로는 안 보인다).

**사용자 질문에 대한 답 — 폴더 선택 창은 뜨지 않는다.**
경로 Edit(`1023`)에 **`C:\BellalunData\Export`가 이미 채워져 있다.**
`CONFIGURATION.EXPORT.ExportDirPath`가 `None`이어도 제품이 이 기본 경로를 쓴다.
즉 사용자가 원한 "제품 기본 경로 사용"이 그대로 동작한다. config에 경로를
하드코딩할 필요가 없다.

**Export Manager 컨트롤 (2026-08-18 실측)**

| 영역 | ctrl_id | 비고 |
|---|---|---|
| File Format | `1009`/`1011`/`1014`/`1012`/`1013`/`1015`/`1010` | DICOM/DICOMDIR/JPEG/BMP/TIF8/TIF16/RAW/IMG 7개 TextButton |
| Export Path 드라이브 | `1019` | `C:\` 드롭다운 |
| **Export Path** | **`1023` (cls=Edit)** | **`C:\BellalunData\Export` 기본값** |
| Type | `1025` Processed / `1024` Not Processed / `1026` Synthetic | CheckBox |
| DICOM Option | `1027` Dose SR / `1032` Portable Viewer / `1021` 언어 | |
| Study List | `1033` (ListCtrl) | 선택된 검사 표시 |
| **Anonymous** | **`1031`** | CheckBox — WF10(익명 Export)에 필요 |
| Burning Option | `1028` Annotations / `1029` Label / `1030` Information | |
| Collimation / Transfer Syntax / Language | `1021`(Cut) / `1020`(Implicit) `1034`(Slider) / `1022`(Default) | |
| **Start** | **`1017`** | |
| **Cancel** | **`1018`** | |

실측 시 Start를 누르지 않고 `1018`로 취소했다(아무것도 내보내지 않음).

### `2192` = 검사 폴더 열기 (확정)

Windows 탐색기로 `<data_dir>\Image\Study<Key>_<날짜시각>` 을 연다. Export가 아니다.
부수 확인: 검사 폴더에는 `DoseSR_<StudyKey>.dcm` 과 `Image<InstanceKey>` 파일들이
들어 있다(실측: Study48 → DoseSR_48.dcm + Image79~82).

### `2195` = 폴더 찾아보기 (확정) — 그리고 Examined 툴바에 **Send는 없다**

`2195`는 Windows "폴더 찾아보기" 대화상자를 띄운다(폴더 지정용 보조 기능).

**따라서 Examined 툴바 14개 중 DICOM Send는 없다.** 클릭으로 확정된 것:

| ctrl_id | 실제 기능 |
|---|---|
| 2184 | Import Study |
| 2191 | **Export Manager** ← WF04 Export |
| 2192 | 검사 폴더 열기(탐색기) |
| 2195 | 폴더 찾아보기 |
| 2197 | Move Image |
| 2185 / 2186 / 2193 | 편집 / 삭제 / 잠금 — **건드리지 말 것** |
| 2181 / 2183 / 2189 / 2190 / 2196 / 2188 | 추가 / 분할 / 목록 / 상세목록 / 검색 / 프린터(추정) |

**WF05의 Send 3경로는 다른 화면에 있다.** 확인된 출발점:

- **Examine 화면**: `flows.EXAMINE["tool_send"]` = **1148** (이미 알려져 있고,
  Export Manager 열거 중에도 우측 툴 레일에 1148이 보였다)
- **View 화면**: 검사를 열어(View 버튼) 영상 표시 상태에서 우측 툴 레일의 1148을
  쓰는 구조로 추정 — 확인 필요
- **Examined 화면**: 툴바에 Send가 없으므로, 검사를 **선택만 한 상태**에서
  다른 경로(컨텍스트 메뉴 우클릭 등)를 확인해야 한다

다음 세션은 **1148(Examine)부터** 구현하는 것이 가장 확실하다. `_send_common`
판정 로직이 이미 있으니, 드라이버만 붙이면 WF05의 첫 경로가 완성된다.

### Import Study 대화상자 컨트롤 (2184)

| ctrl_id | rect | 용도 |
|---|---|---|
| 2062 | `(611,327,676,361)` | 드라이브 선택(`C:\`) |
| 2065 | `(686,327,1265,361)` | 경로 입력 |
| 2064 | `(833,741,953,791)` | Import |
| **1102** | `(968,741,1088,791)` | **Close** |

### Examined 목록 띄우기 — 해결 (2026-08-18 실측)

**검색 버튼과 새로고침 버튼을 혼동한 것이 원인이었다.**

| ctrl_id | rect | 실제 기능 |
|---|---|---|
| **2179** | `(1239,122,1305,188)` | **검색(돋보기)** — 이걸 눌러야 목록이 채워진다 |
| 2180 | `(1315,133,1359,177)` | 새로고침 — 눌러도 목록이 안 채워짐 |

`2180`을 검색으로 착각해 계속 눌렀고, 그래서 "완료 검사가 DB에 있는데 목록이 비어
있다"는 잘못된 관찰을 했다. `2179`를 누르면 검사 카드가 정상 표시된다
(실측: 기간 Today·필터 All 상태에서 6건 표시).

부수 확인:
- 기간 버튼은 Patient 화면과 같은 ID: Today `1106` / Week `1107` / Month `1108` /
  사용자지정 `1109`.
- 좌측 필터 드롭다운 `2200`의 항목은 **All / Rejected / No Rejected / Suspended /
  Locked** (기본 All이라 필터가 원인은 아니었다).
- 목록 영역은 `StudyListScrollWnd`(rect `(116,314,1615,905)`)이고 **카드가 커스텀
  렌더링**이라 행이 개별 컨트롤로 열거되지 않는다 → 카드 선택은 좌표 클릭 또는
  OCR(`vp.click_viewer_text`)로 해야 한다.
- `StudyStatus` 실측값: 1=진행 중, 3=완료, 4=보류.

## WF04 / WF05 구현 완료 (2026-08-18)

| TC | 명령 | 자동 판정 |
|---|---|---|
|  |  | Image Overlay 추가, Print Overlay 등록·선택, DICOM Send, Export |
|  |  | Storage Transfer Syntax, Examine Send (All Images / Selected) |

둘 다 에 포함된다. 새 모듈: ,
, , ,
.

### 이 과정에서 확정한 실측 지식

- **Send 전제**: 영상을 선택해야 Send(1148)가 활성화된다. 첫 클릭이 삼켜지므로
  대화상자 등장을 확인하며 재시도해야 한다. 범위 선택은 =502 /
  =501 / =500.
- **전송 실패의 진짜 원인은 Transfer Syntax였다.** Viewer가 JPEG2000
  ()을 제안하면 Bunny가 Presentation Context를
  한다. Storage 옵션 를 Implicit VR LE로 맞춰야 한다.
  (SOP Class나 Bunny setting.txt는 원인이 아니었다 — 둘 다 검증해 배제했다.)
- **Bunny 수신 폴더는 ** 다(는 비어 있음). config 수정 완료.
- **Export Manager는 별도 프로세스** 다.
  로 붙어야 컨트롤이 보인다. 경로 Edit()에
  제품 기본값 가 이미 채워져 있고 **폴더 선택 창은 안 뜬다.**
- **Export 완료 안내 팝업의 OK를 눌러야** 창이 닫힌다. 방치하면 모달이 이후
  클릭을 삼키고, Close 버튼도 먹지 않는다.
- **Export 성공 판정은 파일 목록 차집합으로 하면 안 된다.** 같은 검사를 다시
  내보내면 같은 경로에 덮어쓰므로 크기·mtime까지 비교해야 한다.
- **Overlay FieldID 실측**: Dose kVp=115, Dose mAs=118 (Patient ID=1,
  Patient Name=2, Birth Date=15, Sex/Age=100, Histogram=113, W1/W2=134).
- **Examined 검색은 **(돋보기). 은 새로고침이라 목록이 안 채워진다.

## 실행 전 필수 확인 (실패 시 최우선 원인)

`VIEWER.exe`는 매니페스트가 `requireAdministrator`라 항상 High Integrity로
실행된다. 자동화 파이썬이 Medium이면 화면 캡처·컨트롤 열거는 정상인데 **클릭만
조용히 실패**해 엉뚱한 증상으로 보인다. UI TC가 갑자기 전부 깨지면 코드보다
권한을 먼저 확인한다(운영 지침 6절).

## 자주 쓰는 명령

```powershell
python run.py list
python run.py run-regression
python run.py run-xipl-06
python run.py run-sys3d
python run.py run-wf04
python run.py run-wf08
python run.py snapshot-baseline
python run.py reset-environment
python run.py setup-dicom
```

실제 `config.json`과 생성된 증적/리포트는 의도적으로 로컬 파일이며 Git에서
제외된다. 보존하고, 저장소 템플릿은 `config.example.json`만 사용한다.

## 마무리 규칙

작업이 끝나면 이 파일을 다음 TC 기준으로 갱신하거나 제거하고, `AGENTS.md`에 따라
검증·커밋·푸시한다. 로컬 설정과 런타임 증적은 커밋하지 않는다. 계속 적용해야 하는
규칙은 이 파일이 아니라 `..\지식\`의 운영 지침/구현 현황 문서에 반영한다.
