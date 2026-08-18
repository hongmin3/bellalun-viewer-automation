# Next automation handoff

## Next priority

`TC_Basic_WorkFlow_04` / `TC_Basic_WorkFlow_05`를 구현한다. 설계는 아래
"다음 작업: TC_Basic_WorkFlow_04 / 05 (사용자 확정 설계)" 절에 사용자 확인을 받아
확정돼 있으니 **그대로 따르고 임의로 바꾸지 않는다.** 시작 전 체크리스트 원문도
다시 확인한다.

먼저 처리할 것: 아래 "새로 드러난 이슈 (TC_04 Step 6)".

## Current verified state (2026-08-14, 2차)

- 저장소: GitHub `hongmin3/bellalun-viewer-automation`, 브랜치 `main`.
  로컬 경로는 PC마다 다르므로 문서에 하드코딩하지 않는다.
- 자동화 범위 총 39건 = **FULL 11 / PARTIAL 18 / MANUAL 10**
  (`python run.py list`로 확인).
- **FULL**: Install_01/02, WF_01/02/03, XIPL_01/02/03/04/05/06.
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
- **신규**: `TC_System_compatibility_03`(3D-Narrow 촬영) /
  `04`(3D-Wide 촬영) — `tests/system_compat.py`, `python run.py run-sys3d`.
  등록·Demo F8 촬영·`INSTANCE_GROUP.Type`/`ExposureMode`(`1/1`=3D-N, `1/2`=3D-W)는
  자동 판정하고, 장비 LCD·2430 패들·회전 각도는 MANUAL로 분리 기록한다. 그래서
  종합 판정은 MANUAL이다.
- Verified servers:
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

## 다음 작업: TC_Basic_WorkFlow_04 / 05 (사용자 확정 설계)

체크리스트 원문과 2026-08-18 사용자 확인 결과다. **임의로 바꾸지 말 것.**

### WF04 (Overlay)
원문 Step: (1) Setting-Display-Overlay에 Image Overlay 추가 (2) Setting-DICOM-Print
에 Print Overlay 추가 후 Print의 Overlay 항목에서 선택 (3) DICOM Send/Print/Export 확인.
Expected: Overlay 항목이 포함된 채 Image 전송. 시스템정보 compression/HVL/AGD/Thickness,
환자정보 ID/birthdate.

- **범위: Send + Print + Export 전부 자동화**(사용자 확정).
- **Print Overlay는 WF03가 이미 6개를 등록**하고 그 6개가 Expected Result와 정확히
  일치한다(`core/print_overlay.py::PRINT_ITEMS` = Patient ID, Birth Date, Thickness,
  Compression Force, HVL, AGD). 재사용한다.
- **Image Overlay에 추가할 2개 = `Dose kVp` + `Dose mAs`**(사용자 선택). 카탈로그에
  실재함을 실측 확인했고, Procedure 패널에 28 kVp / 32 mAs로 값이 보여 화면·전송
  양쪽 검증이 쉽다. 현재 Image Overlay에는 Patient ID/Patient Name/Birth Date/
  Sex·Age/Histogram/Window Level(W1/W2) 6개가 들어 있다(FieldID 1,2,15,100,113,134).
- Image Overlay 카탈로그 목록은 `ctrl_id 2382`(ListCtrl, 실측 rect 418,161~718,875)이며
  **Thickness / Compression Force / HVL / AGD가 목록 맨 끝 4개**로 실재한다.
- **Export 경로**: 제품 기본값을 쓴다(사용자 의견). `CONFIGURATION.EXPORT.ExportDirPath`가
  현재 `None`이고 `<data_dir>\Export` 폴더는 이미 존재한다. 경로를 config에
  하드코딩하지 말고 DB에서 읽어 비어 있으면 `<data_dir>\Export`로 간주한다.
  **미확인**: `None`일 때 Export가 폴더 선택 창을 띄우는지 실측해야 한다.
  띄운다면 사용자에게 다시 확인할 것.

### WF05 (DICOM Send 2D)
원문 Step: (1) DICOM Storage 등록 (2) Examine창에서 Send (3) View창에서 Send
(4) Examined에서 Send (5) Selected/All Images. Expected: 선택 영상이 등록된 SCP로 전송.

- **범위: 3개 화면 전부 + Selected/All 둘 다**(사용자 확정).
- **대상 영상: 기존 픽스처(DATA_FLOW_MWL_01)의 2D 원본(InstanceType=0)**(사용자 확정).
- 판정 로직은 이미 있다 — `tests/dataflow.py::_send_common`이 Queue 변화와
  **수신 객체의 PatientID/Study·Series·SOP UID를 DB와 대조**한다. 드라이버(실제 UI
  Send 흐름)만 새로 만들면 된다.
- 수신 폴더는 `config.json > dicom.received_root` = `C:\Program Files (x86)\Bunny\Receive`
  (현재 비어 있음). Storage는 `BUNNY_TEST / Bunny / 127.0.0.1:3000`.
- Examine 화면의 Send 버튼은 `flows.EXAMINE["tool_send"]` = 1148.

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

### 남은 Send/Export 후보 (아직 미확인)

`2184`=Import, `2197`=Move로 밝혀졌으므로 Send/Export는 다음 중에 있다.
**삭제·잠금·편집 후보(2185/2186/2193)는 건드리지 말 것.**

| ctrl_id | x | 아이콘 | 비고 |
|---|---|---|---|
| 2188 | 1420 | 프린터 | Print 가능성 높음 |
| 2191 | 1466 | CD/디스크 | 미디어 내보내기(=Export?) |
| 2195 | 1742 | ? | 미확인 |
| 2192 | 1788 | 열린 폴더 | Export 가능성 |

또한 **Examine 화면의 Send 버튼(`flows.EXAMINE["tool_send"]` = 1148)** 이 이미
알려져 있다. WF05 원문이 "Examine창 / View창 / Examined" 세 경로를 요구하므로,
가장 확실한 1148(Examine)부터 구현하고 나머지 두 경로의 버튼을 위 후보에서
클릭으로 확정하는 순서가 안전하다.

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

## WF04 착수 시 첫 할 일 (2026-08-18 실측 진행분)

`core/flows.py`에 **Export 관련 헬퍼가 아직 하나도 없다.** 그래서 WF04는 Export
드라이버를 새로 만들어야 한다.

실측으로 확인된 것:

- **Setting > Study 페이지에는 Export 설정이 없다.** 하위가 General /
  Study Delete / Reject-Retake 뿐이다. 따라서 `CONFIGURATION.EXPORT`의
  Format/Processed/Anonymous/PortableViewer 등은 **Export를 실행할 때 뜨는
  대화상자**에서 고르는 값으로 보인다(별도 Setting 페이지가 아님).
- `CONFIGURATION.EXPORT.ExportDirPath`는 현재 `None`이고
  `<data_dir>\Export` 폴더는 이미 존재한다.

남은 확인 사항:

1. Export를 어디서 호출하는지(Examine / View / Examined 화면의 어느 버튼) 및
   컨트롤 ID.
2. `ExportDirPath`가 `None`인 상태에서 **폴더 선택 창이 뜨는지.** 뜨면 사용자에게
   다시 확인할 것 — 사용자는 "제품 기본 경로 사용"을 원했고, 임의로 경로를
   정하지 않는다.
3. 실제로 `<data_dir>\Export`에 쓰는지 대조.

## 실행 전 필수 확인 (실패 시 최우선 원인)

`VIEWER.exe`는 매니페스트가 `requireAdministrator`라 항상 High Integrity로
실행된다. 자동화 파이썬이 Medium이면 화면 캡처·컨트롤 열거는 정상인데 **클릭만
조용히 실패**해 엉뚱한 증상으로 보인다. UI TC가 갑자기 전부 깨지면 코드보다
권한을 먼저 확인한다(운영 지침 6절).

## Useful commands

```powershell
python run.py list
python run.py run-regression
python run.py run-xipl-06
python run.py run-sys3d
python run.py snapshot-baseline
python run.py reset-environment
python run.py setup-dicom
```

실제 `config.json`과 생성된 증적/리포트는 의도적으로 로컬 파일이며 Git에서
제외된다. 보존하고, 저장소 템플릿은 `config.example.json`만 사용한다.

## Completion rule

작업이 끝나면 이 파일을 다음 TC 기준으로 갱신하거나 제거하고, `AGENTS.md`에 따라
검증·커밋·푸시한다. 로컬 설정과 런타임 증적은 커밋하지 않는다. 계속 적용해야 하는
규칙은 이 파일이 아니라 `..\지식\`의 운영 지침/구현 현황 문서에 반영한다.
