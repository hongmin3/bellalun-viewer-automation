# NEXT_TASK.md — 아카이브 (끝난 기록)

> `tools_prune_docs.py` 가 옮겨 담는다. **읽는 비용을 줄이려고 내린 것이지
> 지운 것이 아니다** — 원문 그대로이고 Git 이력에도 남아 있다.
> 새 세션은 이 파일을 읽지 않아도 된다. 과거 경위를 되짚을 때만 검색한다.

<!-- 2026-08-25 이관 — NEXT_TASK.md -->

<!-- 이관 사유: 해결 표시 -->
### 0. [완료] 개정본 체크리스트로 TC 번호 전면 재정렬 (2026-08-19)

**기준 문서는 `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx`(시트 `개정 TC`)
하나다.** `AGENTS.md` 0절에 못박았다.

`지식\(TC) R-23-2346_...xlsx`는 **다른 문서**다. 같은 형태의 TC ID를 쓰지만 번호
매핑이 다르다. 이 둘을 혼동해 정상 구현된 `WF_02`를 "범위 불일치"로 잘못 강등한 적이
있다(사용자가 바로잡아 줬다). 확인해 보니 어긋난 것은 WF02 하나가 아니었다.

| 개정본 | Title | 코드가 쓰던 옛 번호 | 구현 파일 |
|---|---|---|---|
| WF_02 | 공통 2D/3D 검사 촬영 및 Tool 적용 | WF_02 (일치) | `tests/workflow02.py` |
| WF_03 | Image Overlay 및 Print Overlay 설정 | WF_04 | `tests/workflow03.py` |
| WF_04 | 2D 수동 DICOM Send | WF_05 | `tests/workflow04.py` |
| WF_08 | 2D/3D Film Print | WF_03 | `tests/workflow03.py` |
| WF_09 | Normal 및 Anonymous Export | WF_10 | `tests/dataflow.py`(판정부) |
| WF_10 | MWL Hospital Code와 Procedure 매핑 | WF_11 | `tests/settings.py`(판정부) |
| WF_11 / WF_12 | Image / Study Reject 및 Restore | WF_12 / WF_13 | `tests/dataflow.py`(판정부) |
| WF_13 | 계정 추가·수정 및 로그인 | WF_14 | `tests/settings.py`(판정부) |
| WF_14 | Setting Export 및 Import | WF_15 | `tests/settings.py`(판정부) |
| WF_16 | Kiosk 및 System Launcher | WF_18 | `tests/workflow16.py`(수동 판정만 기록) |

**적용한 것**

- `automation_scope.json`을 개정본에서 **직접 생성**했다(36 TC = FULL 12 / PARTIAL 4
  / MANUAL 20). 각 항목에 `title`을 넣어 개정본과 대조 가능하게 했다.
- 모듈의 `TCResult` ID, `run.py` 명령, 회귀 실행 순서를 개정본 번호로 재정렬했다.
  `run-wf03`=Overlay 설정, `run-wf04`=2D Send, **`run-wf08`=Film Print**(신설).
  이전 `run-wf05`는 없어졌다.
- 개정본에 없는 3D-N/3D-W 촬영은 TC 번호를 떼고 보조 항목
  `AUTOMATION_3D_ACQUISITION_3DN/_3DW`로 분리했다(`run-sys3d` 유지).
- `core/checklist.py`가 개정본(`개정 TC` 시트)에 결과를 기록한다.
- WF_03 모듈(현 `tests/workflow03.py`)을 개정본 WF_03의 6단계 구조로 재작성했다. Send 판정은 WF_04가,
  Film 표시 확인은 WF_08이 하므로 중복을 제거하고 참조로 바꿨다.
  > **2026-08-21 정정**: 이 판단은 뒤에 바뀌었다. 개정본 WF_03 Step 6 은 **Film
  > 창의 표시**를 확인하는 것이고 WF_08 이 보는 것은 **실제 Print 출력물**이라
  > 대상이 다르다. 그래서 WF_03 이 Film 창을 직접 열어 영역별 Overlay 를 OCR 로
  > 대조한다(중복 아님). 판독 코드는 `core/print_overlay.py` 에 두어 WF_08 과
  > 공용한다. 이 절 아래 내용은 2026-08-19 시점의 기록으로 남겨 둔다.

**개정본에 없어 빠진 항목**: 이전 scope의 `WF_17`, `WF_18`,
`TC_System_compatibility_03/04`. 개정본 WorkFlow는 16까지이고
`TC_System_compatibility_*` 계열이 없다.

**개정본에만 있어 새로 등록한 항목**: `WF_16`(Kiosk 및 System Launcher).

<!-- 이관 사유: 해결 표시 -->
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

<!-- 이관 사유: 해결 표시 -->
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

<!-- 이관 사유: 해결 표시 -->
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

<!-- 이관 사유: 해결 표시 -->
### 3. [완료] WF_05 / WF_06 / WF_09 구현과 사양서 인용 체계 (2026-08-19)

**사양서를 코드에서 검색할 수 있게 만들었다.** `pypdf`(MIT, 순수 Python)를
`requirements.txt`에 추가하고 `core/specs.py`를 만들었다. `portability-check`가
네 패키지(Pillow / pytesseract / openpyxl / pypdf) 설치 여부를 점검한다.

```python
specs.search(ctx, "익명")   # -> [{'source':'사양서1','page':134,'srs':[...],'text':...}]
specs.cite(ctx, "Recon")    # -> 판정 note에 넣을 한 줄 인용문
```

사양서에는 요구사항마다 `SRS 01-10-10` 형태의 ID가 붙어 있다. 절 번호보다 정확해
`note`에는 **쪽 번호와 SRS ID를 함께** 적는다. 추출 텍스트는 `.txt`로 캐시되므로
이후에는 grep도 된다(사양서1이 336쪽이라 매번 뽑으면 느리다).

**이걸로 답을 찾은 두 건**

1. `WF_05` 3D 전송 대상 — 사양서1 **125쪽**(SRS 06-30-30 문맥):
   "3D 영상은 Recon 영상이 전송된다. Recon 영상이 없을 경우 영상은 전송되지 않는다."
   체크리스트 Test Data가 "사양 추가 확인 필요"로 남긴 의문의 답이다. Conformance
   Statement가 For Processing(Raw)을 선언하지 않는 것, 실측(DB 4건 중 2D·Recon
   2건만 수신)과 모두 일치한다.
2. `WF_09` 익명화 기대값 — 사양서1 **134쪽**: "Anonymous 체크 시, Patient ID 및
   Patient Name은 Unknown으로 표시". 처음엔 "사양에 명시돼 있지 않다"고 보고
   '원본과 다르다'로만 판정했는데 **틀렸다.** `Unknown` 정확 대조로 바꿨고,
   132쪽의 경로 규칙(`Unknown_Unknown\Anonymous_[StudyKey]`)도 참고 판정에 넣었다.
   실측이 사양서와 완전히 일치했다(PASS 12/12).

**구현 결과**

| TC | 명령 | 실측 |
|---|---|---|
| `WF_05` 3D 수동 DICOM Send | `run-wf05` | PASS (received_types = 2D·Recon, 누락 0) |
| `WF_06` All Images 및 Dose SR | `run-wf06` | 자동 PASS, RDSR 미수신은 MANUAL |
| `WF_09` Normal 및 Anonymous Export | `run-wf09` | **PASS 12/12** |

`export_manager`에 `set_path()` / `set_anonymous()` / `is_checked()`를 추가했다.
WF_09는 Normal과 Anonymous를 **서로 다른 경로**로 내보내야 한다(같은 경로면 덮어써서
두 결과를 비교할 수 없다).

<!-- 이관 사유: 해결 표시 -->
### 4. [완료] 로그인 화면이 다른 창에 가려지는 경우 (2026-08-19)

**사용자 지적**: 로그인 화면에서 다른 실행 프로그램이나 파일 탐색기가 Viewer를
가리면 로그인을 제대로 수행하지 못한다. 비밀번호는 **물리 키 입력**이라 포커스가
다른 창에 있으면 키가 그 창으로 들어간다. 화면 캡처는 되므로 증상이 "로그인 실패"로만
보인다.

**최종 구현** (`ui.bring_to_front()` + `cold_start` 로그인 루프)

1. 로그인 직전에 Viewer를 전면으로 올린다. `SetForegroundWindow`는 Windows가 무시할
   수 있으므로 **올라왔는지 확인**한다(최대 4회).
2. 판정은 **프로세스(PID) 기준**이다. `hwnd` 동일성으로 보면 Viewer가 로그인 화면·
   대화상자에서 다른 최상위 창을 전면에 두는 정상 상황을 "가려졌다"고 오판한다.
3. 셸 창(`Program Manager` / `Progman` / `WorkerW` / `Shell_TrayWnd`)은 **가림으로
   보지 않는다.**
4. **전면화에 실패해도 중단하지 않는다.** 결과를 기동 로그에 남기고 진행한다.
   로그인이 **최종 실패했을 때** 그 시점의 최전면 창 제목·PID를 오류 메시지에 실어
   "가려져서 실패했는지"를 알 수 있게 한다.

**두 번 실패한 기록** (같은 실수를 반복하지 않기 위해 남긴다)

처음에는 "전면화 실패 시 FlowError로 중단"으로 만들었다. 그런데 이 PC에서는 가림을
**재현할 수 없어서**(Viewer가 전면을 강하게 유지) 실패 분기를 실측하지 못한 상태로
넣었다. 결과:

- 회귀 13차: `name 'os' is not defined` — `core/flows.py`에 `import os`가 없는데
  스크린샷 경로를 만들었다. **컴파일은 통과했다.** 14개 TC 연쇄 FAIL.
- 회귀 14차: import를 고쳤는데 같은 지점에서 또 실패 —
  `가리고 있는 창: 'Program Manager' (PID 7108)`. 데스크톱 셸을 가림으로 오판했다.
  Viewer를 새로 띄운 직후에는 최전면이 데스크톱인 정상 순간이 있다.

**얻은 규칙**(운영 지침에 반영): 재현할 수 없는 상황에는 **중단이 아니라 진단**을
넣는다. 그리고 컴파일은 import 누락을 잡지 못하므로 바꾼 모듈은 실제로 호출해 본다.

**검증**: `setup-dicom` 실행으로 `cold_start` 로그인 경로를 실제로 통과함을 확인했다
(PASS 14 / FAIL 0, 기동 로그에 전면 경고 없음). **가림 자체는 여전히 재현하지
못했으므로**, 실제로 가려진 환경을 만나면 오류 메시지의 창 제목과
`Evidence/ui/login_not_foreground.png`를 먼저 확인할 것.

<!-- 이관 사유: 해결 표시 -->
### 5. [완료] Image Overlay를 Bottom에 배치 + 리포트 수치 오해 수정 (2026-08-19)

**① 리포트의 "PASS 160"이 TC 개수로 오해됐다** (사용자 지적). 그 값은 **Step(체크)
단위**였다. 리포트 머리글을 두 줄로 분리했다.

```
 TC 건수   : 20
 TC 판정   : PASS 13 / FAIL 1 / MANUAL 6 / SKIP 0   (TC 단위)
 검증 판정 : PASS 160 / FAIL 1 / MANUAL 10 / SKIP 1   (Step 단위, 총 172개 체크)
```

README에는 과거 9개 회차를 리포트 JSON에서 재계산해 두 층을 함께 적었다. 그 과정에서
**체크 수 자체가 연쇄 실패의 신호**라는 것이 드러났다 — 정상 172개, 연쇄 실패 시 49개.

**② Dose kVp / Dose mAs 를 Bottom 에 배치** (사용자 확정).

실측한 컨트롤과 DB 값:

```
2382 Available   2380 Top 목록      2381 Bottom 목록
2383 Add Top     2384 Remove Top
2385 Add Bottom  2386 Remove Bottom
OVERLAY_ITEM.Position:  0 = Top, 1 = Bottom
```

버튼 ID는 **눌러서 DB로 확인**했다. `Dose mA`(116)를 2385로 넣으니 `Position=1`이
되고 2386으로 빼니 사라졌다. 이 저장소에서 아이콘 추측이 여러 번 틀렸으므로
(2184=Import, 2197=Move Image) 반드시 실측한다.

`add_image_overlay_items(ui, db, labels, position="bottom")`이고, 판정은 저장 여부만
보지 않고 **Position 까지 대조**한다. 위치를 확인하지 않으면 Top 에 들어가도 PASS 가
되어 요구사항을 놓친다.

**내가 만든 버그와 수정** (같은 실수를 반복하지 않기 위해 남긴다)

첫 구현에서 `Patient ID`(FieldID 1)와 `Patient Name`(2)이 **삭제됐다.** 행에서
FieldID 를 화면으로 읽을 수 없다는 이유로 "위에서부터 한 건씩 지운다"는 **임의 규칙**을
만든 것이 원인이다. Dose kVp(Order=6)/mAs(Order=7)를 지우려다 Order 0·1 을 지웠다.
**"불확실하면 추측하지 않는다"는 규칙을 내가 어겼다.**

수정:
- `OVERLAY_ITEM.Order`가 표시 순서이므로 그 값으로 **정확한 행 인덱스를 계산**한다.
- **Order 가 큰 것부터** 지운다. 위쪽을 먼저 지우면 아래 항목 인덱스가 당겨진다.
- 중간에 DB 를 확인하지 않는다 — **Setting 변경은 Update 를 누를 때까지 DB 에
  반영되지 않는다**(실측). 검증은 저장 뒤 한 번 한다.
- 저장 뒤 `unintended_loss`로 **의도하지 않은 삭제를 검출**해 발생 시 즉시 중단한다.

**③ 부수 발견 — Setting 이탈 시 저장 확인 팝업**

작업이 중단된 상태에서 Setting 을 벗어나려 하자 `Do you want to save changed
configuration?`(3버튼: 좌 502 Yes / 중 501 No / 우 500 Cancel)이 떠 **모달이 이후 모든
클릭을 삼켰다**(`메인 메뉴가 열리지 않았습니다`로 죽음). `flows.confirm_config_save()`를
추가하고 `ensure_patient_screen`이 Setting 을 닫을 때 호출한다. 기본값은 **No** —
자동화의 의도한 설정 변경은 항상 `setting_update()`로 명시적으로 저장하므로, 이 팝업이
뜨는 것은 그 경로를 타지 않은 잔여 변경이라는 뜻이다. 문구를 OCR 로 확정하지 못하면
누르지 않는다(3버튼 팝업은 검사 종료 옵션과 구성이 같다).

**검증 (영향 범위만, 약 18분)**

전체 회귀(60분)를 돌리지 않았다. `add_image_overlay_items` 호출부가 `WF_03` 한 곳뿐이라
나머지 TC 는 이 변경과 무관하다.

```bash
python run.py setup-dicom && python run.py run-wf01 && python run.py run-wf02 && python run.py run-wf03
```

결과: `WF_03` PASS 4 / MANUAL 2, `added={115:(1,0), 118:(1,1)}`,
`unintended_loss=[]`, Top 항목(1/2/15/100/113/134) 전부 유지.

**단독 검증 시 주의**: `WF_03/04/05/06/08/09`는 `DATA_FLOW_MWL_01` 픽스처를 요구한다.
DB 를 복원한 직후에 단독 실행하면 `Viewer XIPL fixture not found`로 죽는다. 위
사슬(`setup-dicom → run-wf01 → run-wf02`)을 먼저 돌려 전제를 만든다.

<!-- 이관 사유: 해결 표시 -->
### 6. [완료] Print Overlay를 Header/Top/Bottom에 분리 + Header 표시 설정 (2026-08-19)

사용자 요청: "print overlay를 만들때도 Header/top/bottom 에 나눠서 셋팅되도록 한번
고도화해줄 수 있을까? top 말고도 다른 영역에도 잘 셋팅되는지 확인하고 싶어서."

**① 영역 분리.** 사양서1 305쪽 SRS 04-20-10 "Overlay로 표시할 항목 설정
(Header / Top / Bottom)". 컨트롤과 `Position` 값은 **넣어 보고 DB로 확인**했다.

| 영역 | 목록 | 추가 | 제거 | `PRINT_OVERLAY_ITEM.Position` | 항목 |
|---|---|---|---|---|---|
| Header | 2486 | 2501 | 2502 | **2** | Patient ID, Birth Date |
| Top | 2487 | 2503 | 2504 | **0** | Thickness, Compression Force |
| Bottom | 2488 | 2505 | 2506 | **1** | HVL, AGD |

화면은 위에서 Header / Top / Bottom 순인데 값은 **2 / 0 / 1**이다. 추측했으면 틀렸다.

항목 배분은 사양이 정한다 — 297쪽 "**영상별로 값이 다를 수 있는 항목은 Header에
삽입할 수 없다**"(허용 목록에 Patient ID / Patient Birthdate가 있다). 그래서
Thickness·압박력·HVL·AGD는 Top/Bottom에만 넣는다.

**② Header가 필름에 나오지 않았다** — 원인은 제품이 아니라 설정이었다.

DB에는 `Position=2`로 정상 저장돼 있는데 필름 OCR은 `'LCC'`만 읽혔다. 원인은 같은
화면 우측 Option의 **`Header Layout` 표시 위치가 `None`**. 사양서1 **297쪽**이
"None으로 설정한 경우 표시되지 않는다"고 적어 둔 정상 동작이다. **사용자가 설정
화면을 보고 먼저 찾아냈다.**

`core/print_overlay.py`에 `ensure_header_layout()`을 추가했다.

- `HeaderPosition`을 `Top`으로 설정하고 **DB 값으로 확인**한다.
  실측 매핑: `0 = None / 1 = Top / 2 = Bottom`.
- `HeaderLayout`은 항목 수를 담을 **최소 칸수**를 계산한다(`required_header_layout`).
  297쪽 "**Layout 한 칸당 한 항목씩 표시한다**" — Header 항목 2개 → `1 X 2`.
  칸이 항목보다 적으면 넘치는 항목이 조용히 사라진다.
- 표시 위치가 `None`이면 Layout 콤보가 **회색 비활성**이다(실측). 그래서 위치를
  먼저 고른다.
- `ensure_print_overlay`는 항목 배치만 보지 않고 `HeaderPosition`/`HeaderLayout`
  까지 대조한다. 항목은 맞고 Header 설정만 다르면 **그것만** 고친다.

**콤보 항목 순서를 믿지 않는다.** 표시 위치 콤보의 두 번째 항목을 눌렀더니
`HeaderPosition`이 Top(1)이 아니라 Bottom(2)이 됐다. 그래서 `_pick_combo_by_text`가
**항목 문구를 OCR로 읽어** 원하는 것을 고르고, 못 찾으면 아무것도 누르지 않고 읽은
문구를 붙여 실패시킨다. 실제 판독값: 위치 `['top']`, Layout `['1x1','1x2']`.

**③ 판정을 영역별로 바꿨다.** 그전에는 필름 우상단 한 곳만 크롭해 전체 텍스트를
훑었기 때문에 **6개가 전부 Top에 몰려 있어도 통과**했다 — 영역을 나눈 의미가 판정에
없었다. `print_overlay.film_regions()`가 영역별 crop box를 돌려주고,
`tests/workflow03.py`가 영역별로 읽어 그 영역의 값이 있는지 따로 판정한다.

Header 밴드 높이는 상수로 박지 않고 **사양 공식**으로 계산한다 — 296쪽 "Header
영역은 (전체 필름 높이의 3% × 선택한 Header Layout의 행수)". 실측 필름(723×904)의
Header 텍스트가 y 8–23에서 끝나고 공식값 27px과 일치했다. Top 밴드는 Header 높이에
얹어 잡는다(Header를 끄면 아래 항목이 그만큼 올라온다).

```
Header  (0,   0, 723,  27)   'DATA_FLOW_MWL_01 1980/01/01'        <- 라벨 없이 값만
Top     (578, 72, 723, 117)  '0.0 cm' / '35 N'                    <- 라벨 없이 값만
Bottom  (361,840, 723, 904)  'HVL: Not valid' / 'AGD: Not valid'  <- 라벨: 값
```

Top 값은 필름에서 **7px 높이**라 기존 배율(6배)로는 아예 읽히지 않았다. 배율 하나에
의존하면 흔들려서(8배에서 `MWL`이 `MIWL`로 읽힘) **배율 12·8·5로 읽고 하나라도
기대값과 일치하면 통과**로 본다. 기대값은 `PatientID`/`PatientBirthDate`를 **DB에서**
가져와 만들므로 느슨해지지 않는다 — 다른 환자의 필름은 어느 배율에서도 일치하지
않는다. 판독본 전부와 영역별 크롭 이미지를 증거로 남긴다.

같은 비율이 Film 창(723×904)과 Print 서버 웹 프리뷰(1280×1600) 양쪽에서 통한다.

**얻은 규칙**: 설정한 값이 화면에 안 보이면 **항목이 아니라 "표시 스위치"를 먼저
본다.** 제품을 의심하기 전에 설정 화면을 캡처해 눈으로 본다.

<!-- 이관 사유: 해결 표시 -->
### 7. [완료] 자동화 모듈 파일명을 TC 번호와 1:1 맵핑 (2026-08-19)

사용자 요청: "자동화코드는 workflow01.py workflow02.py 처럼 tc번호랑 맵핑해주면
좋을것 같아."

| 이전 | 담당 TC | 이후 |
|---|---|---|
| `tests/workflow03.py` | **WF_08** | `tests/workflow08.py` |
| `tests/overlay_flows.py` | WF_03 | `tests/workflow03.py` |
| `tests/export_flows.py` | WF_09 | `tests/workflow09.py` |
| `tests/send_flows.py` | WF_04 / 05 / 06 | `tests/workflow04.py` / `05` / `06` |
| (공용 Send 판정) | — | `core/send_verify.py` |

`workflow03.py` 가 `WF_08`(Film Print)을 담고 있어 **이름이 정면으로 오해를
부르는 상태**였다. `send_flows.py` 는 세 TC가 한 파일에 섞여 있었다.

옮기면서 TC 절차가 아니라 인프라에 해당하는 부분(Queue 상태·수신 객체·식별 Tag
대조)만 `core/` 로 내렸고, 모듈 밖에서 쓰는 헬퍼는 앞 밑줄을 떼어 공개 이름으로
바꿨다(`_send_and_verify` -> `send_and_verify`).

**분할에서 실제 버그가 나왔고 `ast` 검사가 잡았다.** 새 모듈에 `flows` / `os` /
`vp` / `ensure_bunny` / `PASS` / `MANUAL` import 가 빠져 있었다. `py_compile` 은
통과한다(AGENTS.md 8항의 그 사례). 회귀 사슬의 WF_08 호출 이름도 어긋나 있었다.

<!-- 이관 사유: 해결 표시 -->
### 8. [완료] WF_13 계정 추가·수정 1~3단계 자동화 (2026-08-19)

`run-wf13` 실측: **PASS 4 / FAIL 0 / MANUAL 3**.

실측으로 확정한 제품 동작 세 가지 — 전부 추측하면 틀렸을 것들이다.

1. **`ACCOUNT.Group` = Service 3 / Admin 2 / User 1.** 콤보 라벨을 OCR 로 읽고
   (`['service','admin','user']`) 실제로 만들어 DB 값을 확인했다.
2. **계정 삭제 확인 팝업은 좌=Yes(501) / 우=No(500).**
   `ui.dismiss_dialog()` 는 No 를 눌러 삭제가 되지 않았다. 문구는
   "Are you sure you want to delete this account?" 다(캡처로 확인). 검사 삭제와
   같은 버튼 구성이라 `flows.confirm_study_delete` 를 재사용한다.
3. **계정 수정 시 Password 를 다시 입력해야 저장된다.** 계정을 선택하면
   Password / Check Password 가 비워진 상태로 표시되는데, 비운 채 Update 하면
   **조용히 저장되지 않는다.** 팝업 문구가 `WM_GETTEXT` 로 안 읽혀
   "(문구 미노출)" 만 남아 원인을 몰랐고, **Update 결과 팝업을 OCR 로 읽도록
   고쳐서** 찾았다. 같은 함정이 다른 Setting 화면에도 있을 수 있다.

`+` 는 인라인 편집이 아니라 **New Account 모달**을 띄운다(2288~2292 / OK 1101 /
Cancel 1102). 우측 Properties(2283~2287)는 선택된 계정의 표시·수정용이다.

**4~6단계는 붙이지 않았다.** 로그인 계정을 바꾸면 회귀의 뒤따르는 TC 가 제한
권한으로 돌고, 중간 실패 시 복구가 불가능하다(회귀 7·13·14차 연쇄 실패의 교훈).

<!-- 이관 사유: 해결 표시 -->
### 14. WF_10 — MWL 커스텀 태그 등록 방법 (해소됨, 2026-08-20)

아래 항목은 **해소됐다.** `core/mwl.py` 를 읽어 보니 처방 등록이 가능하다.
자세한 것은 15항 참고.

`Setting > DICOM > MWL` 의 `Hospital Code Mapping` 콤보(**2453**)와 순서는 확정했다
(등록된 Hospital Code 가 없으면 콤보가 아예 열리지 않는다).

**남은 것**: "MWL 서버에 임의의 코드로 커스텀 태그를 만들고 값을 넣는" 부분.
현재 `core/mwl.py` 가 처방을 만들 수 있는지, 아니면 별도 도구(Bunny 설정 화면 등)를
쓰는지 알려 주시면 붙이겠습니다.

<!-- 이관 사유: 해결 표시 -->
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

<!-- 2026-08-26 이관 — NEXT_TASK.md -->

<!-- 이관 사유: 해결 표시 -->
### 9. 미구현 TC의 진입점 실측 (2026-08-19) — 다음에 이어서 하면 된다 [완료]

캡처의 화면 라벨과 rect 를 대조해 확정했다. `core/flows.py` 에 상수로 기록했다.

| 화면 | 확정한 것 |
|---|---|
| Setting > System 하위 | 186 General / 187 Security / 188 Region / 189 System Info. / 190 Software Info. / **191 Account** / 192 License / **193 My Settings** / 194 CS |
| Setting > Study 하위 | 209 General / 210 Study Delete / **211 Reject/Retake** |
| Account | 2280 목록 / 2281 + / 2282 휴지통 / 2283~2287 Properties |
| New Account 모달 | 2288 ID / 2289 Name / 2290 PW / 2291 Check PW / 2292 Group / 1101 OK / 1102 Cancel |
| My Settings | **2293 Export / 2294 Import** |
| Reject/Retake | 2421·2422 Reject previous image on retake / 2423 Use reject reason / 2424 Use retake reason / 2425 Always display rejected images / 2426 Reasons 목록 / 2427 추가 / 2428 삭제 |
| Patient 화면 | **1100 Emergency**(사이렌 아이콘) |
| DICOM General | 2444 Study close option / 2446·2445 Send urgent patient automatically / 2448·2447 Validate study instance UID / 2449 Allow long accession number |

**WF_11/12 전제조건은 이미 충족돼 있다** — Use reject reason ✓, Always display
rejected images ✓, Reason 5건(Artifacts / Mispositioning / Patient Movement /
Mechanical Failure / Inappropriate Processing). 자동화는 이 전제를 **바꾸지 않고
확인**하면 된다.

**남은 미지: Reject 실행 버튼.** Examined 툴바 14개(2181·2183·2189·2190·2196·
2188·2191·2184·2197·2185·2186·2193·2195·2192)에는 없다. 검사를 연 화면에서
찾아야 한다. 이번에는 Examined 목록이 기본 필터로 비어 나와(0행) 검사를 열지
못했다 — `tests/workflow08.py` 의 `_examined_search(ui, PATIENT_ID)` 로 환자 ID 를
넣고 조회해야 한다.

<!-- 이관 사유: 해결 표시 -->
### 12. WF_13 완전 자동화 + WF_15 구현 (2026-08-20) [완료]

**WF_13 은 이제 FULL 이다.** 사용자가 사양서1 78~80쪽 권한 표를 이미지로 확인해 줘서
기대값이 확정됐고, 실측이 **56/56 일치**했다.

남은 4개 그룹의 페이지 ID 를 실측해 9개 그룹 56개가 전부 맵에 들어왔다.

| 그룹 | 페이지 ID (화면 순서) |
|---|---|
| System | 186 187 188 189 190 191 192 193 194 |
| Patient | 195 196 197 198 199 **228 235 236** |
| Display | 200 201 202 203 204 |
| Tool | 205 206 207 208 |
| Study | 209 210 211 |
| Procedure | 212 213 214 215 |
| DICOM | 216~225 |
| Device | **234 226 230 231 229 232 233 227** |
| Q.C. | 238 239 240 241 242 |

**ID 가 화면 순서와 무관하다.** Device 는 순서가 완전히 뒤섞였고 Patient 의 뒤쪽 세
항목은 228/235/236 으로 떨어져 있다. 연속이라고 추정했으면 전부 틀렸다. 각 항목을
OCR 로 읽어 사양서 표 순서와 짝지어 확정했다.

**새로 확정한 제품 동작**: 사양의 `O`/`X` 는 "보이지만 비활성"이 아니라
**"메뉴가 아예 표시되지 않는다"** 다. 표에 명시가 없어 추측하지 않고 실측했다.
User 에게 보이는 것은 `system>software_info / account / cs / security`,
`tool>image_tool`, `procedure>hospital_code`, `qc>regular_inspection` 뿐이고 나머지
49개는 표시되지 않는다.

로그인 관련으로 두 가지를 잡았다.

1. **ID 입력창은 목록형이다** — 사양서1 78쪽 "기존에 등록했던 계정 목록이 표시되며,
   목록 중에 선택해서 로그인할 수 있다. ID를 사용자의 직접 입력이 아니라 목록 중에
   선택하는 방법을 사용하여 사용자의 오입력을 방지한다." `ui.login` 이 계정 전환을
   일부러 막고 있어(그 가드는 옳다) `flows.select_login_id` 를 만들어 항목 문구를
   OCR 로 읽어 고르고, `cold_start` 가 로그인 직전에 호출한다.
2. **그 콤보는 긴 ID 를 잘라서 보여준다** — `TEST_USER_FLOW` -> `TEST_USE`.
   완전일치 비교가 불가능해 접두사 비교로 바꿨다(최소 4자). `service` 는
   `TEST_USER_FLOW` 의 접두사가 아니므로 엉뚱한 계정으로 진행하는 것은 그대로 막힌다.

**WF_15 도 구현했다**(PARTIAL, PASS 6 / MANUAL 4). 자세한 것은 커밋 메시지 참고.

<!-- 이관 사유: 해결 표시 -->
### 13. WF_11 / WF_12 — Reject 진입점을 아직 못 찾았다 (물어볼 것) [완료]

찾아본 곳과 결과를 남긴다. **추측으로 누르지 않았다** — 인접한 휴지통(2186)/
잠금(2193)을 잘못 누르면 데이터가 훼손된다.

| 확인한 곳 | 결과 |
|---|---|
| Examined 툴바 16개 | Reject 없음. `2196` 이 Pre-send Preview 로 밝혀졌고(사용자 확인) 나머지도 기능이 다르다 |
| 검사 카드 **우클릭** | 컨텍스트 메뉴가 뜨지 않는다(`ui.right_click` 을 새로 만들어 확인) |
| 검사를 **View 로 열은 화면** 하단 | `2122` Raw / `2123` Recon / `2124` Syn. — 3D 영상 종류 전환이고 Reject 아니다. Examine 모드의 Retake(2205)는 View 모드에 아예 없다 |

**남은 후보**: Examined 창 썸네일 패널(`2198`)의 각 썸네일에 붙은 작은 아이콘들.
사용자가 보낸 캡처에서 `LCC` / `LCC (3D-N)` 썸네일 우하단에 아이콘 두세 개가 보였다
(업로드 화살표 / 프린터 / 시계 모양). 그중 하나가 Reject 일 수 있지만 아이콘 추정은
이 저장소에서 두 번 틀렸다(2184, 2196).

**물어볼 것**: Image Reject 와 Study Reject 는 어디에서 실행하나요? Pre-send Preview
처럼 **툴팁이 보이는 캡처 한 장**이면 바로 확정됩니다. 썸네일의 작은 아이콘 중
하나인가요, 아니면 Examine(추가 촬영) 모드에서 하는 건가요?

판정부는 이미 준비돼 있어(`tests/dataflow.py` 의 `workflow_11_evaluate` /
`workflow_12_evaluate` / `*_mid_evaluate`) 진입점만 알면 바로 붙습니다.

<!-- 이관 사유: 해결 표시 -->
### 15. WF_10 진행 상황 (2026-08-20) — Code 셀 편집만 남았다 [완료]

**core/mwl.py 는 이미 처방을 등록할 수 있다.** 내가 "처방을 만들 수 있는지 확인이
필요하다"고 적었던 것은 코드를 먼저 읽지 않은 탓이다. `POST /worklist/new` 와
`make_mg_order(..., hospital_code=...)` 가 있고 Hospital Code 를
`rp_code_value`(Requested Procedure Code Value)로 넣는다.

실측해 확정한 것 (`core/flows.py` 에 기록)

| 화면 | 확정 |
|---|---|
| Setting > Procedure > Hospital Code (215) | 2557 목록(Code / Procedure·View Position / Type / Description) / 2558 추가 / 2559 삭제 |
| 새 행 | `+` 가 인라인 행을 만든다. Code 는 `Code`, `Code_1`, ... **자동 생성** |
| Procedure 열 | 톱니바퀴를 누르면 `View Position` 대화상자 |
| View Position 대화상자 | 탭 2082 Preset(2D) / 2083 Preset(3D-N) / 2084 Preset(3D-W) / **2086 Procedure** / 1101 OK / 1102 Cancel |
| Procedure 탭 | 목록 행 ctrl_id 가 `PROCEDURE_INFO.Key` 와 일치(1 Routine Mammography / 2 Mammography (Rt) / ...). 헤더도 id=1 이라 문구를 OCR 로 읽어 고른다 |
| DB | `HOSPITAL_CODE(Key, Code, Description, MappingKey, MappingType)` — 매핑은 MappingKey = PROCEDURE_INFO.Key |

**남은 미지 하나 — Code 셀 값을 바꾸는 방법.**
`Code`(자동 생성)를 `HC_FLOW_01` 로 바꿔야 하는데, 다음을 모두 시도해도 편집 모드가
열리지 않았다(진짜 `Edit` 클래스 컨트롤이 생기지 않고 셀 문구도 그대로였다).
  한 번 클릭 / 더블클릭 / 천천히 더블클릭 / F2 / Enter / 클릭 후 직접 타이핑

**물어볼 것**: Hospital Code 의 `Code` 값은 어떻게 입력하나요? 자동 생성 값
(`Code`, `Code_1`...)을 그대로 쓰는 것이 맞나요, 아니면 편집하는 별도 방법이
있나요? 자동 생성 값을 쓰는 것이 맞다면 TC 문서의 `HC_FLOW_01` 표기를 그에 맞게
보완하겠습니다(TC 번호는 건드리지 않습니다).

**이번에 낸 사고와 조치**: `+` 가 Update 없이도 DB 에 즉시 저장된다는 것을 모르고
프로브를 다섯 번 돌려 `HOSPITAL_CODE` 에 `Code`~`Code_4` 5행을 남겼다. UI 삭제로
전부 정리해 현재 0행이다. 재발 방지 규칙을 `AGENTS.md` 3항과 지식 운영 지침
10-1-2 / 10-1-3 절에 넣었다.

<!-- 이관 사유: 해결 표시 -->
### 11. 자매 프로젝트(VXvue) 개선안 검토 결과 (2026-08-20) [완료]

`..\..\VXvue에서_가져올_개선안.md` 를 검토했다. 8개 항목 중 **1번은 이 저장소에도
실재하는 버그**여서 즉시 고쳤다(커밋 참고). 나머지 판단은 아래와 같다.

| 항목 | 판단 | 근거 |
|---|---|---|
| 1. `specs.py` SRS 인용 오류 | **완료** | 실측으로 재현됐다. 버그가 셋이었다 — 위치 무시 정렬(SRS 2개 이상인 쪽 56개 중 36개 오작동), 3자리 끝 번호 절단(38건), 본문 교차참조를 근거로 착각. 인용 6건을 사양서 원문과 대조해 6/6 확인 |
| 2. `BLOCKED` 판정 추가 | **채택 권장** | 이 저장소도 `SKIP` 하나가 "환경상 정상적 건너뜀"과 "선행 조건 미구성으로 수행 불가"를 섞는다. WF_06 의 RDSR 미수신은 지금 `MANUAL` 인데 성격상 `BLOCKED` 다 |
| 7. note 에 해제 조건 + "말할 수 없는 것" | **채택 권장 — 가장 값싸고 효과 큼** | 특히 "이 실행으로는 무엇을 말할 수 없는가" 를 빠뜨리고 있었다. WF_06 RDSR MANUAL 이 그 사례다 — 검증하지 못했는데 "문제 없다"로 읽힐 수 있다 |
| 6. 환경 헤더를 4종 리포트 전부에 | 채택 | 간단하고, HTML 을 공유받은 사람이 되묻지 않게 된다 |
| 3. 파괴적 조작 `confirm` 인자 | **부분 채택** | `restore_baseline(ctx)` 에 `confirm` 을 붙이는 것은 타당하다. 다만 회귀는 매 실행 복원에 의존하므로 **플래그 필수화는 회귀 흐름을 바꾼다** — 기본 동작은 유지하고 `confirm` 만 추가하는 선에서 |
| 5. 좌표 → 속성 | **일부는 이미 적용** | 이 저장소는 컨트롤 ID + `rect` 기반이고, VXvue 의 1항(ListItem 행)·3항(ID 일관성)은 이미 쓰고 있다. **2항(화면 제목을 읽어 메뉴 지도를 실행 시점에 생성)은 새롭고 값이 크다** — 2026-08-19 에 Setting 하위 페이지 ID 를 캡처로 하나씩 확정한 작업이 자동화된다 |
| 4. 실패 시점 메모리 실측 | 우선순위 낮음 | 이 PC 에서 겪은 문제가 아니다. 비용이 낮아 넣어도 무해하다 |
| 8. 팝업 반복 상한 | 채택 권장 | 방어적이고 저렴하다. 지금 `dismiss_dialog` 계열에 상한이 일관되지 않다 |
| 8. 취소선(삭제 사양) 처리 | **확인 필요** | 방금 고친 인용 버그와 같은 계열이다. 취소선 사양을 근거로 쓰면 판정 자체가 틀린다. `pypdf` 텍스트 추출로 취소선이 보이지 않으므로, 인용한 쪽을 눈으로 확인하는 절차가 필요하다 |

<!-- 이관 사유: 해결 표시 -->
### 10. 사용자 답변 반영 (2026-08-20) [완료]

어제 남긴 질문 4건에 답을 받았다. 각각 무엇이 확정되고 무엇이 남았는지 적는다.

**① WF_13 Step 6 — 권한별 메뉴 범위: 확정.**
사양서1 **78~80쪽**에 "Setting에서 계정 그룹별로 사용할 수 있는 메뉴" 표가 있다.
근거 SRS 는 77쪽 제목 **`SRS 01-30-20`**("로그인한 계정의 권한 그룹에 따라 사용할 수
있는 기능을 제한한다").

`User` 그룹이 **O** 인 것만 추리면 다음과 같다. 나머지는 전부 **X** 다.

| Menu Group | User = O |
|---|---|
| System | Software Info. / Account / CS (Security 는 "Date/Time Change 만 사용, KIOSK 사용 중일 때만 버튼 활성화") |
| Tool | Image Tool |
| Procedure | Hospital Code |
| Q.C. | Regular Inspection ("Inspection Information 항목만 표시") |

이미 실측해 둔 System 페이지 ID 와 대조하면 기대값이 그대로 나온다 —
`190 Software Info.` / `191 Account` / `194 CS` 는 접근 가능, `186 General` /
`188 Region` / `189 System Info.` / `192 License` / `193 My Settings` 는 불가.

**남은 확인 하나**: 사양의 `O`/`X` 가 "메뉴가 안 보인다"인지 "보이지만 비활성"인지
명시돼 있지 않다. 추측하지 않고 `User` 로 로그인해 **실측**해서 확정한다.
로그인 복구는 `flows.cold_start(cfg, db, force_restart=True)` 로 한다 — Viewer 를
재시작하며 `config.json` 의 service 계정으로 다시 로그인하므로 확실하다.

**② WF_10 — Hospital Code Mapping: 진입점 확정.**
`Setting > DICOM > MWL` 우측의 콤보가 **`2453`** 이다(현재 값 `None`,
`flows.MWL_HOSPITAL_CODE_MAPPING`). 사진과 rect 가 정확히 일치한다.

**순서가 있다는 것을 실측으로 확인했다** — 등록된 Hospital Code 가 없으면 이 콤보를
눌러도 **목록이 아예 열리지 않는다.** 그래서 구현 순서는
`Setting > Procedure > Hospital Code(페이지 215)에서 HC_FLOW_01 생성`
→ `Procedure 매핑` → `2453 에서 그 코드 선택` → `콤보 목록의 항목을 기준으로 MWL
서버 커스텀 태그 구성` 이다.

**남은 것**: MWL 서버(`core/mwl.py`)에 커스텀 태그를 넣어 처방을 등록하는 부분.

**③ WF_15 — TC 를 수정했다.** 사용자 지시로 개정본 체크리스트 25행을 고쳤다.
원본은 `..\Baseline\Checklist_개정본_20260820_WF15수정전.xlsx` 로 백업했다.

이전 TC 는 "Apply preview position 을 켜고 Zoom/Pan/Rotation 을 바꿔 그 표시 위치가
수신 영상에 반영되는지"를 요구했는데, 수신 DICOM 의 어떤 값으로 판정할지 확정할 수
없어 막혀 있었다. 바뀐 TC 는 **Pre-send Preview 팝업의 표시 내용이 View/Examine
화면과 같은지**와 **Send 후 Queue·수신까지 정상인지**를 요구한다 — 둘 다 관찰
가능하다.

| 항목 | 이후 |
|---|---|
| Title | Pre-send Preview 표시 및 전송 |
| Step | 1. Examined 에서 검사 선택 / 2. Pre-send Preview 실행 / 3. 팝업의 Step 영상·Overlay 확인 / 4. View·Examine 화면과 비교 / 5. Preview 에서 Send / 6. Queue 상태 확인 / 7. Storage SCP 수신 확인 |
| Expected | 1. 대상 지정 / 2. 팝업 표시 / 3. 각 Step 영상과 Overlay 표시 / 4. View·Examine 과 동일한 구성 / 5. Queue 등록 / 6. Done / 7. 누락 없이 수신되고 식별 Tag 일치 |
| Test Data | 수신 경로의 TC 번호가 `..._17` 로 어긋나 있어 `..._15` 로 고쳤다 |

**④ WF_07 — 데이터 정리 불필요: 확정.**
"쌓이는건 문제가 없을것 같아 스터디가! 짜피 전체 회귀 돌릴때 db초기화를 하니깐!"
회귀는 `AUTOMATION_ENVIRONMENT_RESET` 에서 DB 기준 스냅샷을 복원하므로 Emergency
검사를 TC 안에서 지우지 않는다. **지우는 코드를 넣지 않는 것이 맞다** — 파괴적
동작을 늘리지 않는다.

<!-- 이관 사유: 해결 표시 -->
### 아직 못 찾은 것 — Pre-send Preview 버튼 (물어볼 것) [완료]

WF_15 를 구현하려면 Examined 화면의 **Pre-send Preview 진입점**이 필요한데
특정하지 못했다. 툴바 16개를 확대 캡처해 아이콘을 눈으로 확인했다
(`Evidence/ui/probe_examined_toolbar_zoom.png`).

| x | ctrl_id | 상태 |
|---|---|---|
| 108 | 2140 | 보기 전환 드롭 |
| 196 | 2200 | 데이터 소스 드롭(All) |
| 1190 | 2181 | `+` 미확인 |
| 1236 | 2183 | 분할 보기 미확인 |
| 1282 | 2189 | 목록 보기 미확인 |
| 1328 | 2190 | 상세 목록 미확인 |
| 1374 | 2196 | 검사 내 검색 미확인 |
| 1420 | **2188** | **Print** (WF_08 에서 확정) |
| 1466 | **2191** | **Export Manager** (확정) |
| 1512 | **2184** | **Import Study** (클릭 확정) |
| 1558 | **2197** | **Move Image** — DICOM Send 아님 (클릭 확정) |
| 1604 | 2185 | 연필(편집) — 누르지 않음 |
| 1650 | 2186 | 휴지통(삭제) — 누르지 않음 |
| 1696 | 2193 | 자물쇠(잠금) — 누르지 않음 |
| 1742 | 2195 | 폴더 찾아보기(확정)로 문서화됨. 다만 확대해 보니 아이콘이 "공 + 작은 목록" 모양으로 폴더와 무관해 보인다 — **이 확정이 틀렸을 가능성** |
| 1788 | 2192 | 열린 폴더 미확인 |

**물어볼 것**: Pre-send Preview 는 이 툴바의 몇 번째 버튼인가요? 아니면 검사 카드를
**우클릭**해서 나오는 메뉴, 혹은 Send 대화상자 안에 있나요? 화면을 보시면 바로 아실
것 같아서 여쭙습니다. 아이콘 모양으로 추정해 누르면 편집·삭제·잠금 버튼을 잘못
누를 수 있어 확인 전에는 시도하지 않겠습니다.

<!-- 이관 사유: 해결 표시 -->
### 사용자에게 물어볼 것 (2026-08-19) [완료]

1. **WF_13 4~6단계** — 시험 계정으로 로그인한 뒤 원래 계정으로 돌아오는 절차를
   어떻게 할까요? 회귀 중간에 실패하면 뒤따르는 TC 가 전부 무너지므로, 실패 시
   복구 방법(예: Viewer 재시작 후 service 로 재로그인)을 확정하고 싶습니다.
   그리고 **권한 그룹별로 어떤 메뉴가 보여야 하는지** 표가 있으면 6단계를
   자동 판정할 수 있습니다. 매뉴얼·사양서에서 찾지 못했습니다.
2. **WF_10** — "RIS/MWL 서버에 HC_FLOW_01이 포함된 처방을 등록한다"를 자동화하려면
   시험용 MWL 서버에 Hospital Code 를 넣어 처방을 만드는 방법이 필요합니다.
   현재 `core/mwl.py` 가 처방을 만들 수 있는지, 아니면 별도 도구를 쓰는지
   알려 주시면 구현하겠습니다.
3. **WF_15** — "수신 영상의 표시 결과가 Send Preview 의 위치와 일치한다"를 무엇으로
   판정할까요? 수신 DICOM 의 어떤 태그(예: Requested Image Size, Presentation
   State)로 확인하는 것이 맞는지 확정이 필요합니다.
4. **WF_07** — Emergency 검사는 실행마다 새 검사를 만듭니다. 회귀에서 데이터가
   쌓이는 것을 그대로 둘까요, 아니면 TC 끝에 지울까요?

<!-- 이관 사유: 해결 표시 -->
### 그 밖의 다음 후보 [완료]

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

<!-- 이관 사유: 해결 표시 -->
## 사양 대조로 확인한 불일치 — Storage Transfer Syntax (2026-08-18) [완료]

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

자동화 쪽 조치: `core/send_verify.py:ensure_transfer_syntax`가 전송 전에
**선언된 값(Implicit VR LE)으로 되돌린다.** 테스트 SCP에 맞춘 우회가 아니라
사양 준수 상태를 만드는 것이므로 그대로 유지한다.

<!-- 이관 사유: 해결 표시 -->
## 현재 검증된 상태 (2026-08-19 갱신) [완료]

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

<!-- 이관 사유: 해결 표시 -->
## 회귀 7차 (2026-08-18 16:56) — 연쇄 실패와 그 수정 [완료]

`PASS 30 / FAIL 10` (17 TC). **FAIL 10건 전부가 첫 FAIL 하나의 결과였다.**
자세한 경위와 교훈은 `지식/[자동화 운영 지침]` 11절 사례를 볼 것. 요약:

`DB 복원(프로세스 전체 종료)` → `cold_start(force_restart=True)`로 재기동 →
로그인 성공 → **`ensure_patient_screen`이 화면이 그려지기 전 t=0에 판단** →
`open_main_menu`가 상태바를 못 찾고 15초 뒤 사망 → DICOM 등록 실패 →
MWL 미등록(`DB=[]`) → WF01/02/03/04, XIPL 01/02/03/06, WF05 연쇄 FAIL.

실측 기동 소요는 **약 36초**였다. 예산 부족이 아니라 **기다리지 않은 것**이다.

<!-- 이관 사유: 해결 표시 -->
### 수정 (모두 실제 경로로 검증) [완료]

| 문제 | 조치 | 검증 |
|---|---|---|
| 화면 그려지기 전 조작 | `flows.wait_known_screen()` 추가, `ensure_patient_screen`이 랜드마크 출현까지 상한 60초 대기 | `setup-dicom` 재실행 → 해당 단계 **36.6s PASS** (이전 53.6s FAIL) |
| `Bellalun Service`를 죽이고 안 되살림 | 서비스는 SCM(`net stop`)으로 내리고 `start_app_services()`로 `finally`에서 복구 + RUNNING 확인 | `RUNNING → STOPPED → RUNNING` 왕복 실측 |
| 실패 시 진단 정보 유실 | `setup_all`이 기동 로그 + 마지막 화면 스크린샷을 남김 | 캡처 동작 확인 |
| 리포트가 연쇄를 안 드러냄 | 상단에 `[ 먼저 볼 것 ] 가장 앞선 FAIL` 추가 | 실패 리포트 재생성으로 확인 |
| 스텝 밖 소요시간 은폐 | TC 전체와 스텝 합계 차이가 5초 넘으면 명시 | — |
| `ui_flows.py`의 6초 고정 sleep | `statusbar.wait_ready()`로 아이콘 출현 대기로 교체 | 5초 이상 고정 sleep **0건** |
| Examined 창 컨트롤 즉시 판정 | `flows.wait_controls()`로 상한 대기 (`viewer_processing`, `tests/workflow03.py`) | — |
| `_open_examined`가 `open_main_menu` 반환값 무시 | 실패 지점을 정확히 보고 | — |

<!-- 이관 사유: 해결 표시 -->
### 읽는 사람을 위한 규칙 [완료]

**FAIL 개수보다 가장 앞선 FAIL을 먼저 본다.** 그리고 **한 실행 안에서 뒤 TC가
통과했다는 사실은 앞 TC 실패를 환경 문제에서 제외하는 근거가 아니다** — 7차에서
`TC_XIPL_04/05`가 PASS해서 "환경은 정상"으로 보였지만, 그때쯤 Viewer가 이미 떠
있어 재사용된 것뿐이었다.

<!-- 이관 사유: 해결 표시 -->
## 최신 회귀 결과 (2026-08-18 12:10) [완료]

**PASS 121 / FAIL 1 / MANUAL 6 / SKIP 1.** FAIL 1건은
`TC_XIPL_compatibility_03 Step 9`로 **제품 실제 결함을 잡아낸 정상 결과**다
(Apply 후 재진입 시 값이 기본값 복귀). GPU 무관하며 **절대 완화하지 않는다.**

- WF02 Window Level의 간헐 FAIL은 해소됐다. 원인은 Overlay가 꺼져 판정 근거
  (W1/W2)를 못 읽던 것이었고, WF02가 Overlay를 직접 보장하고 판정을 사양 기준
  (값 증감)으로 바꾼 뒤 연속 PASS한다. 다시 FAIL하면 먼저
  `CONFIGURATION.OVERLAY_ITEM`의 FieldID 113/134를 확인할 것.
- `TC_XIPL_compatibility_04`는 검증 9단계 전부 PASS이며 종합 MANUAL은 시험
  Preset 수동 삭제 안내 때문이다(회귀는 DB 복원으로 자동 해소).

<!-- 이관 사유: 해결 표시 -->
## WF04 / WF05 구현 완료 (2026-08-18) [완료]

| TC | 명령 | 자동 판정 |
|---|---|---|
|  |  | Image Overlay 추가, Print Overlay 등록·선택, DICOM Send, Export |
|  |  | Storage Transfer Syntax, Examine Send (All Images / Selected) |

둘 다 에 포함된다. 새 모듈: ,
, , ,
.

<!-- 이관 사유: 해결 표시 -->
### 이 과정에서 확정한 실측 지식 [완료]

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

