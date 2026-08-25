# 다음 작업 (2026-08-25 기준)

> **문서 지도 — 이 문서의 역할과 다른 3개 문서와의 관계**
> 이 문서는 **현재 상태와 다음에 할 일**만 담는다 — 최신 회귀 결과, 이번 회차에 바꾼 것, 남은 문제, P0/P1/P2, **사용자 판단이 필요한 항목(5절)**, 다음 세션용 프롬프트(6절).
> **영구 규칙**은 `AGENTS.md`, **영구 구현 규칙과 사고 이력**은 `..\지식\[자동화 운영 지침] ...md`, **지난 회차의 누적 실측 기록**(컨트롤 ID·확정한 제품 동작)은 `NEXT_TASK.md` 에 둔다 — 그 셋에 속하는 내용을 여기에 쌓지 않는다.
> **읽는 순서 — `README.md` 최상단 "온보딩 요약" → `AGENTS.md` → 이 문서 → `[자동화 운영 지침]`(상단 "증상 → 원인 → 조치" 색인부터) → 필요할 때 `NEXT_TASK.md` 검색.**

---

## 1. 현재 상태

| 항목 | 값 | 근거 |
|---|---|---|
| 기준 문서 | `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC` — **TC 37건** | 2026-08-24 `TC_XIPL_compatibility_07` 추가 |
| 자동화 범위 | 완전자동 **21** / 부분자동 6 / 수동 10 (+ 보조 4) | `python run.py list` |
| 코드 규모 | Python **24,971줄** / 모듈 73개 (core 34 · tests 28 · `run.py` · 도구 10) | 2026-08-25 재실측 |
| 추적성 | TC 37건 중 24건에 사양 인용 68건, 위반 0 | `python tools_traceability.py` |
| 단위 시험 | **64건** 전부 통과 | `python -m unittest discover -s tests -p "test_*.py"` |
| **최신 전체 회귀** | **2026-08-25 08:19~10:04 (22차)** — TC 27건: PASS 19 / FAIL 3 / MANUAL 5, 검증 267개: PASS 248 / FAIL 11 / MANUAL 7 / SKIP 1, **104.6분** | `Reports/Result_20260825_100414.json` |

### 22차 회귀의 FAIL 3건

| TC | 성격 | 내용 |
|---|---|---|
| `TC_XIPL_compatibility_03` Step 9 | **제품 결함** (계속 보고) | Apply 후 재진입하면 3D 파라미터가 기본값으로 복귀. 사양서1 277쪽 SRS 03-50-230 위반. 완화하지 않는다 |
| `TC_Basic_WorkFlow_13` Step 4 | **자동화 불안정** | 로그인 ID 콤보(2001)를 `TEST_USER_FLOW` 로 바꾸지 못했다(OCR 선택 실패). Step 1~3(계정 추가·권한·저장)은 PASS 였고 정리도 정상 수행됐다. 20차에서는 PASS 였다 |
| `TC_XIPL_compatibility_05` Step 4 | **판단 필요** (5절 ①) | 파라미터 적용은 정상(`TEST_QC_3D.eap`)인데 `QC_STUDY.Result` 가 `0`(Pass 아님). 판정이 채점 결과까지 요구한다 |

> 검증 FAIL 11건 중 **5건은 "미수행"** 이다 — 중단된 TC 의 남은 Step 을 채운 것이라
> 제품 결함 판정이 아니다(2.2 참고).

### 회귀 이력 (최근 3회)

| 회차 | 일시 | TC 판정 | 검증 | 소요 | 비고 |
|---|---|---|---|---|---|
| 20차 | 08-24 09:45 | PASS 20 / FAIL 2 / MANUAL 5 | 263개 | 108.9분 | XIPL_07 첫 회귀 투입. FAIL 2 = 제품 결함 1 + XIPL_07 원복 1 |
| 21차 | 08-24 11:57 | **PASS 6 / FAIL 19** | 198개 | 79.4분 | **붕괴.** DICOM 등록 실패를 중단 정책이 증폭 → 전제 게이트 도입 |
| **22차** | **08-25 08:19** | **PASS 19 / FAIL 3 / MANUAL 5** | **267개** | **104.6분** | 회복. XIPL_07 전 단계 PASS |

---

## 1-A. 2026-08-25 오후 회차 — `TC_Basic_WorkFlow_14` 집중 개선

사용자 요청 두 가지에서 시작했다.
"일단 개느림 / export 후 설정을 쫌 다양한 메뉴에서 여러가지를 바꿀 수 있도록 …
이 tc에서 이슈가 나왔던 경우가 많아서 참고해줘."

### 결과 (2026-08-25 14:20 단독 실행, 전 단계 PASS)

| 항목 | 전 | 후 |
|---|---|---|
| WF_14 소요 | 23.6분(회귀의 22.6%) | **약 16.5분** |
| Setting 전 페이지 판독 2회 | 17.7분 | **약 5.4분** (페이지당 5.41초 -> 2.19초) |
| Step 3 변경 범위 | 설정 **1개 / 1개 테이블** | **8개 / 7개 테이블 + UPS** |
| Step 7 이 실제로 검증하는 범위 | 그 1개 테이블 | 7개 테이블 + 화면 값 508항목 |

### 속도 — 추측하지 않고 분해해서 쟀다

페이지당 비용이 **단조 증가**했다(첫 페이지 0.50초 -> 여섯 번째 1.02초). 제품이
페이지마다 콘텐츠 패널을 새로 만들고 이전 것을 남겨 둬서 전체 컨트롤 트리가 계속
커지는데, `read_all` 이 페이지마다 그 트리를 **세 번** 훑고 있었다.
전체 트리 대신 **패널 하위**만 읽도록 바꿨다(`shallow` / `pane_control` /
`pane_controls`). 판정 값은 10페이지 대조에서 **차이 0**.

사용자가 화면을 보고 지적한 것도 고쳤다 — "왜 메뉴를 옮길때마다 좌측하단에 메뉴 탭
setting을 자꾸 누르는거야?" `read_all` 이 9개 그룹마다 `open_setting()` 을 무조건
불러 두 회차면 **18번 헛클릭**이었다. `open_setting` 을 멱등으로 만들어 8개
헬퍼가 한 번에 고쳐졌다.

### 변경 범위 — 왜 1개로는 안 되는가

Step 7 은 설정 테이블 **전수 대조**인데 **바꾸지 않은 영역은 그 판정이 아무것도
증명하지 못한다.** Import 가 `TOOL_COMMON` 을 통째로 건너뛰어도 그 테이블을
건드린 적이 없으면 통과한다. 즉 **변경 범위가 곧 실제 검증 범위**였다.
`core/setting_changes.py` 로 7개 메뉴 / 7개 설정 테이블 + UPS 를 바꾼다.
제외 항목(Theme / Language / Security / DICOM Port / Device 노출 인터록 /
자동 삭제)과 이유는 그 모듈 docstring 에 적었다.

### 실측으로 확정한 것

- **`ui.type_text` 는 Setting 숫자 Edit 에 먹지 않는다.** `Ctrl+A`+`Delete` 로
  지워지기까지 하고 문자는 안 들어가 빈 칸이 된다. 네 방법을 비교해 VK 원시 키만
  통하는 것을 확인했다.
- **컨트롤을 ID 로 고르면 안 된다.** 같은 페이지에 같은 ctrl_id 의 Edit 이 여럿
  있어 `next(...)` 가 조용히 다른 칸을 집는다. **DB 값으로 찾고, 후보가 하나가
  아니면 집지 않는다.**
- Setting 페이지를 51개 도는 동안 **GDI 객체 348 -> 2886, USER 객체 1433 -> 5610**
  으로 늘고 한 번도 반환되지 않는다(3절 4번).

---

## 2. 이번 회차에 한 일 (2026-08-24 ~ 08-25)

### 2.0 문서 고도화 Phase 1 + 자동화 구조 보강 Phase 2

- Phase 1: README 온보딩, 4개 문서 지도, 자동화 범위 전수표, 증상→원인→조치
  색인, 문서 수명 정책과 `Archive/` 이관을 반영했다.
- MD→HTML 자동 렌더러는 **도입하지 않았다.** `프로젝트 상세.html`을 직접 갱신하라는
  2026-08-24 사용자 지시와 충돌하고, 이미 유지 중인 HTML을 자동 변환물이 덮을 수
  있기 때문이다. 대신 `tools_check_docs_sync.py`가 기준 문서보다 오래된 HTML을
  경고한다.
- `tools_run_regression.py`가 회귀 Python 바깥에서 실행을 감시한다. 새 전체 회귀
  리포트가 없으면 비정상 종료로 확정해 상태 파일·Windows 알림을 남기고 Viewer를
  안전 종료한다.
- TC 사이에서 Viewer가 사라지면 WER 덤프로 실제 크래시 여부를 구분해 판정에 남기고
  다음 TC용으로 재기동한다(`run.py::recover_viewer_after_termination`).
- `tools_automation_status.py` / `check_automation_status.cmd N`은 개별 TC나 전제 실패
  리포트를 제외하고 마지막 **완료 전체 회귀**의 경과일을 알려 준다. 일일 작업
  스케줄은 이 PC에 임의 등록하지 않았으며, 필요하면 이 CMD를 Task Scheduler에
  연결한다.

### 2.1 `TC_XIPL_compatibility_07` — 신규 TC, 실행 검증 완료

개정본 33행에 추가한 **촬영 모드별 3D Default Recon Parameter 적용**(9단계).
단독 실행과 회귀 양쪽에서 **Step 1~9 전부 PASS** 를 실측했다.

실측으로 확정한 것 (자세한 표는 `NEXT_TASK.md`)

- `PROCEDURE_COMMON` 의 `DefaultReconNarrow` / `DefaultReconWide` — 모드별 독립 저장
- 3D Preset 은 모드별 22행, Positioning 11종이 사양서1 196쪽과 정확히 일치(FB/CV 없음)
- **3D-W 의 `EgpName` = `wide_standard.egp`** (3D-N 은 `narrow_standard.egp`)
- img 의 `ViewPosition/@Type` 도 모드를 구분(3D-N=1 / 3D-W=2)
- `XtpName` 은 두 모드 모두 **Preset 설정값** → `automation_scope.json` 의
  coverage.gap 이 실재함이 확인됐다

### 2.2 회귀 운영 방식 변경 (사용자 지시 3건)

1. **어떤 Step 이 FAIL 하면 그 TC 를 즉시 중단한다.** 어차피 사람이 볼 TC 이므로 남은
   Step 을 수행해 전체 시간을 늘리지 않는다. `config.json > regression.stop_tc_on_fail`
   로 끌 수 있다.
2. **중단된 TC 의 남은 Step 을 미수행(FAIL)으로 채운다.** 예전에는 리포트에 아예
   나오지 않아 "몇 단계까지 갔는지" 알 수 없었다. 단계 수는 기준 체크리스트에서 읽는다.
3. **전제 준비가 깨지면 회귀를 즉시 종료한다.** `AUTOMATION_ENVIRONMENT_RESET` /
   `DICOM_Server_Setup` 이 FAIL 이면 배너를 찍고 중단한다 — 서버가 등록되지 않으면
   이후 판정은 제품에 대해 아무것도 말해 주지 않는다. 21차가 그 낭비를 실증했다
   (실패 후 80분을 더 돌며 19개 TC 연쇄 FAIL).
4. **회귀가 끝나면 Viewer 를 종료한 뒤 결과를 출력하고 완료 배너를 찍는다.**
   열린 검사는 Suspend 로 보존한다. 배너에 집계·FAIL 목록·리포트 경로를 싣고 콘솔
   벨을 울린다.
5. **리포트의 `Step 0` 을 `보조` 로 표기.** 0 은 기준 체크리스트 Step 이 아닌 보조
   판정(파라미터 준비, 시험 전 값 기록, 중단 기록, 원복)이라는 뜻이다.

### 2.3 실행해서 찾아 고친 결함 (전부 실측)

| # | 결함 | 어떻게 드러났나 |
|---|---|---|
| 1 | `ensure_ready` 가 **로그인 실패를 삼켰다** | 15초 뒤 `open_main_menu` 가 엉뚱한 메시지로 죽었다. 이제 실패 지점에서 캡처하고 예외를 던진다 |
| 2 | 기동 팝업(`Running in demo mode.`)이 **로그인 화면을 가렸다** | 화면 대기가 180초를 다 쓰고 실패. 대기 중에도 팝업을 계속 걷어낸다 |
| 3 | Demo 안내가 **로그인 뒤에** 뜨는데 로그인 전에만 닫았다 | 모달이 이후 모든 클릭을 삼켰다. 로그인 후에도 걷어낸다 |
| 4 | Demo 촬영 직후 `+` 클릭이 **삼켜졌다** | 툴팁만 뜨고 다이얼로그가 안 열렸다. DB 행 도착은 "UI 가 다음 조작을 받을 준비"를 보장하지 않는다. 상한 3회 재시도 |
| 5 | Step 3 OCR 이 화면 문구와 달랐다 | `3D-N` 0건 / `(3D-N)` 1건. 캡처로 실제 판독을 확인해 고쳤다(추측하지 않았다) |
| 6 | 콤보에서 **다른 콤보의 표시값**을 눌렀다 | 좌표로 후보를 고르려던 시도가 **세 번 다 실패**(제약 없음 → `min_y` → `exclude_rects`). 이제 누른 뒤 표시값·DB 로 확인하고 재시도한다 |
| 7 | `install_01`/`install_02` 가 **`except` 없이** 회귀 첫 단계에 있었다 | 정적 감사로 발견. `guarded()` 로 호출 지점에서 일괄 보호 |
| 8 | `tools_check_regression_names.py` 가 **무력화**됐다 | 회귀 사슬을 참조 목록으로 바꾸자 세는 이름이 0개가 되고 통과 메시지는 그대로 나왔다. 0개면 실패로 만들었다 |
| 9 | 로그인 시 **비밀번호를 3번 입력**했다 | PW 필드는 password 스타일이라 `WM_GETTEXT` 가 빈 문자열을 준다. "확인 불가"를 "실패"로 단정한 것이 원인. 재시도를 로그인 단위로 옮겼다 |
| 10 | 저장소의 유일한 단위 시험이 **실패 상태로 방치**돼 있었다 | 아무도 돌리지 않았다. 사전 검사에 넣었다 |

### 2.4 추가한 것

| 파일 | 용도 |
|---|---|
| `core/imginfo.py` | 제품 `.img` 꼬리의 `<INFORMATION>` XML 판독(3D Recon 파라미터). DB 에 없는 근거다 |
| `traceability.json` + `tools_traceability.py` | 사양↔TC 양방향 추적성. 인용을 **매번 원문과 대조**한다. 위조 7건 주입 검출 확인 |
| `core/viewer_processing.wait_new_group()` | 고정 `settle` 대신 DB 도착 조건 대기. 2D 각 2.9초(고정 14초 대비) / 3D 29.5·39.7초(**고정 20초는 오히려 부족했다**) |
| `tests/test_imginfo_and_waits.py` | 단위 시험 26건 |
| `run.py probe-preset3d` | 3D Preset 목록 컨트롤 실측용 조회 전용 프로브 |
| `..\프로젝트 상세.html` | 운영 상세 문서(프로젝트 루트, 저장소 밖). **작업할 때마다 직접 갱신한다** |

### 2.5 정리

- 용어 `증적` → `증거` 통일(54회). 조사 오류 30여 곳도 diff 를 눈으로 보고 고쳤다
- 죽은 코드 `preview_and_apply` 삭제, 죽은 설정 키 `preview_3d_wait`/`apply_3d_wait` 교체
- 프로젝트 폴더 정리 486MB → 111MB (사용자 승인)

---

## 3. 남은 문제

| # | 문제 | 우선순위 |
|---|---|---|
| 1 | `TC_Basic_WorkFlow_13` Step 4 — 로그인 ID 콤보 OCR 선택이 불안정 | **P0** |
| 2 | `TC_XIPL_compatibility_05` Step 4 — Q.C 채점 결과 요구가 Demo 환경에서 불안정 | **P0**(판단 필요, 5절 ①) |
| 3 | `TC_XIPL_compatibility_03` Step 9 — 제품 결함. 완화하지 않는다 | 제품 수정 대기 |
| 4 | 3D Preset 목록·추가·삭제 컨트롤 ID 미실측 → "새 Preset 이 Default 를 물려받는가" 미판정 | P1 |
| 5 | `TC_XIPL_compatibility_04` 가 `DefaultImgProcess` 를 오염시킨 채 끝난다 | P1 |
| 6 | `flows.demo_acquire_step(settle=14)` 고정 대기가 WF_01/WF_02/run-sys3d 에 남아 있다 | P1 |
| 7 | 중단 정책 때문에 `XIPL_03` Step 10 의 "GPU 없음 SKIP" 기록이 사라졌다 | P2(맞바꾼 것) |
| 8 | 추적성 미연결 13건 — `Install_01` 외 12건은 전부 미구현 | P2 |
| 9 | Dose SR(RDSR) — Demo 촬영에서는 생성되지 않는다(전제 미충족) | P2 |
| 10 | **UPS 설정이 Setting Export/Import 범위 밖이다** — 아래 3-A | 제품 수정 대기 |
| 11 | **Setting 페이지 순회 중 Viewer 가 종료되는 경우가 있다**(간헐) — 아래 3-B | 조사 계속 |
| 12 | **`WF_14` 진입이 간헐적으로 실패한다** — 아래 3-C | **P0** |

### 3-A. UPS 설정이 Export/Import 로 복원되지 않는다 (사용자 제보 → 확인 완료)

사용자: *"ups의 setting export/import가 안되는건 이슈일껄? 기존이슈일꺼야"*

`Setting > Device > UPS` 의 `UPS Setting`(`None` / `EATON Ellipse ECO 650`)은
**저장은 되는데 Export 산출물 어디에도 들어가지 않는다.**

| 확인한 것 | 결과 |
|---|---|
| `.vms` 안 20개 항목 | UPS 관련 **0건** |
| `CONFIGURATION`/`ACCOUNT`/`PROCEDURE` 전 문자열 컬럼 | `UPS`/`EATON` **0건** |
| 세 DB 의 `%UPS%` 컬럼명 | **0건** |
| `Config/ExternalInput.xml` | ups/eaton/battery **0건** |
| 레지스트리 `HKLM\|HKCU\SOFTWARE\Vieworks` | UPS 값 **0건** |
| `UPSHandler\` 폴더 | 설정 파일 없음(exe/dll/log 뿐) |
| 값을 바꾸고 Update | 설정 섹션 **38개 중 0개** 변화 |
| 값을 바꾸고 Viewer 재기동 | **값이 남는다** (= 저장은 된다) |

사양서1 60절은 Export 대상을 "Study 정보를 제외한 모든 설정 정보" 로 정의한다.
`WF_14` Step 7 마지막에 판정으로 넣었고 **완화하지 않는다**
(`TC_XIPL_compatibility_03` Step 9 와 같은 취급).

같은 페이지의 `2537~2541`(Model / Serial No. / Battery Charged / Power State /
Remaining run time)은 **설정이 아니라 실시간 장치 상태**라 화면 값 대조에서 뺐다
(`setting_values.VOLATILE_CONTROLS`). UPS 미연결 때문에 `'0 %'`/`'Power Unknown'`
이 `'Not Connected'` 로 바뀌어 오탐을 냈다.

### 3-B. Setting 전 페이지 순회 중 Viewer 가 종료된다 (간헐, 원인 미특정)

**관찰된 것만** 적는다.

- 51개 페이지를 읽은 뒤 Q.C. 그룹에 들어가면 Viewer 가 사라졌다(4회 재현).
  Windows 오류 이벤트는 남지 않는다 — 크래시가 아니라 정상 종료 경로다.
- 그룹 순서를 **뒤집어** Q.C. 를 먼저 읽으면 56개 페이지가 모두 정상이었다
  (최종 GDI 3162 / USER 6147 로 오히려 더 높은데도). → Q.C. 고유 문제도,
  단순 자원 한도 문제도 아니다.
- `device.ups -> qc.setting_2d` 3페이지짜리 최소 재현으로는 **재현되지 않는다**
  (대조군 2개 포함 3케이스 모두 생존).
- 2026-08-25 14:20 실행에서는 56페이지 두 회차가 모두 정상이었다. **간헐적이다.**

`read_all` 이 Viewer 소멸을 감지해 순회를 멈추고 그 사실을 남기도록 했고
(`viewer_died`), `WF_14` Step 7 에 **순회 완주 여부**를 별도 판정으로 뒀다.
순회가 중단되면 화면 값 대조의 근거가 불완전하기 때문이다. TC 는 재기동해서
본 시험(Export/Import)을 끝까지 수행한다.

관련 관찰: Setting 페이지 51개를 도는 동안 **GDI 348 -> 2886 / USER 1433 -> 5610**
으로 늘고 반환되지 않는다(페이지당 GDI 약 50 · USER 약 82). 종료의 직접 원인으로
확정하지는 못했지만 함께 보고할 값이다.

### 3-C. `WF_14` 진입 실패 — `my_settings`(193) 미발견 (2026-08-25 14:39, 간헐)

**문서 정비 중 리포트를 대조하다 발견했다. 실행해서 만든 것이 아니라 남아 있던
리포트에서 읽은 사실이다.**

1-A 에 적은 `14:20 단독 실행, 전 단계 PASS`(`Result_20260825_142050.json` — PASS 18 /
FAIL 0)는 맞다. 그런데 그 **뒤에 한 번 더 돌린 14:39 실행**이 다르게 끝났다.

| 실행 | 리포트 | 결과 |
|---|---|---|
| 2026-08-25 14:20 | `Result_20260825_142050.json` | **PASS** 18 / FAIL 0 |
| 2026-08-25 14:39 | `Result_20260825_143949.json` | **FAIL** — PASS 10 / FAIL 5 |

14:39 의 실패 지점은 **본 시험이 아니라 진입**이다.

```
[FAIL] Step 0 TC_Basic_WorkFlow_14 실행:
       FlowError: System 설정 'my_settings'(ID 193)을 찾지 못했습니다.
```

Step 4~7 의 FAIL 4건은 중단 정책이 채운 **미수행**이다(14-14). 정리(원복)는 정상
수행됐다 — `system.general 12 / patient.patient_list 30 / display.overlay 10 /
procedure.general 100 / qc.setting_3d 1` 원복, 실패 0.

**아직 원인을 모른다.** 관측된 것만 적는다.

- 같은 코드로 19분 전 실행은 통과했다 → 코드 변경이 원인은 아니다.
- 실패 지점이 `Setting > System > My Settings` **페이지 진입**이라 3-B(전 페이지 순회
  중 Viewer 종료)와 같은 계열일 수 있다. 다만 3-B 는 순회 **중**이고 이것은 TC **진입**
  이라 같다고 단정하지 않는다.
- `work/wf14_run12.log` 가 0바이트다 — 그 뒤 한 번 더 시작했다가 끝나지 않았다.

**다음에 할 것**: `reset-environment` 후 `run-wf14` 를 연속 3회 돌려 재현율을 잰다.
재현되면 진입 경로에 "그 화면이 실제로 있는지" 확인을 붙인다(운영 지침 11절 — 조작
전에 화면이 존재하는지 확인한다). 재현되지 않으면 **중단이 아니라 진단**을 남긴다
(운영 지침 11절 사례).

---

## 4. 우선순위

### P0

1. **`WF_13` 로그인 ID 콤보 선택을 견고하게.** `flows.select_login_id` 는
   `uitext.pick_combo_by_text` 로 OCR 선택하는데 실패했다. `_click_general_param_combo`
   에 쓴 방식과 같게 — **고른 뒤 `ui.current_login_id()` 로 확인하고 틀리면 다음
   후보로 재시도** — 로 바꾼다. 확인 수단이 이미 있으므로(`current_login_id`)
   추가 근거가 필요 없다.
2. **`XIPL_05` Step 4 판정 재검토** — 5절 ①의 결정을 받은 뒤 반영한다.

### P1

3. `python run.py probe-preset3d` 로 3D-N/3D-W Preset 목록 컨트롤 실측 →
   `core/flows.py` 상수와 `NEXT_TASK.md` 에 기록.
4. 그 위에 "새 3D Preset 이 그 시점 Default 를 물려받는가"(Service Manual 근거)를
   `XIPL_07` 에 추가. 정리는 UI 삭제로 하고 삭제 전후 DB 를 대조한다.
5. `XIPL_04` 에 `DefaultImgProcess` 원복 추가. `reset-environment` → `run-xipl-04` →
   DB 확인까지 지나간 뒤에만 커밋.
6. `demo_acquire_step` 의 고정 대기를 `wait_new_group` 으로 전환. 호출부가
   WF_01/WF_02/run-sys3d 이므로 그 셋을 회귀 순서로 실제 지나가야 한다.

### P2

7. `flows.close_examine` 의 no-dialog 경로 상태 신호화.
8. 추적성 미확정 중 `Install_01` — 검증 대상 Release Note 를 받으면 확보 가능.
9. Dose SR 생성 조건 조사(`NEXT_TASK.md` 고도화 대기 1번).

---

## 5. 사용자 판단이 필요한 항목

### ① `TC_XIPL_compatibility_05` Step 4 — Q.C 채점 결과를 판정에 넣을 것인가

**현재 판정**: `applied_3d.parameter == "TEST_QC_3D.eap"` **그리고**
`QC_STUDY.Result == 1`(Pass).

**22차 실측**: 파라미터는 정상 적용됐는데 `Result = 0` 이라 FAIL.
20차에서는 `Result = 1` 이었다 — **회차마다 다르다.**

**쟁점**: 이 TC 의 제목은 "Q.C Default Image Process Parameter" 이고 개정본
Expected 4 는 *"3D Q.C 영상에 지정 Parameter가 적용된다"* 이다. **채점 통과(Pass)를
요구하지 않는다.** 그런데 자동화는 `Result == 1` 까지 요구한다. Demo 가상 촬영은
실제 팬텀이 아니므로 채점 결과가 보장되지 않는다.

**선택지**
- (A) **판정에서 `Result` 를 빼고** 파라미터 적용만 본다. 채점 결과는 `actual` 에
  관측값으로 남긴다. → 개정본 Expected 원문에 맞고 Demo 환경에서 안정적
- (B) 그대로 둔다. → 실제 팬텀 촬영 환경에서만 의미가 있고 Demo 에서는 계속 흔들린다
- (C) `Result` 를 별도 확인 항목으로 분리하고 Demo 환경에서는 SKIP(사유 기록)

**제 의견은 (A)** 입니다 — 개정본 Expected 가 요구하지 않는 것을 판정에 넣으면
제품이 정상인데 FAIL 이 납니다. 다만 **판정을 약하게 만드는 변경**이라 사용자
승인 없이 하지 않았습니다.

### ①-2 `TC_Basic_WorkFlow_14` Step 3 — 체크리스트 문구를 고칠 것인가

개정본 Step 3 원문은 *"Theme 또는 검증 대상 비파괴 설정 **1개**를 변경한다"* 인데
자동화는 **8개**(7개 테이블 + UPS)를 바꾼다. 이유는 1-A 에 적었다 — 1개만 바꾸면
Step 7 의 "전수 대조" 가 실제로는 그 한 테이블만 검증한다.

**원문은 손대지 않았다.** 문구를 실제 수행에 맞춰 고칠지는 판단이 필요하다.

- (A) 문구를 "검증 대상 비파괴 설정을 **여러 메뉴에서** 변경한다" 로 수정
- (B) 문구는 그대로 두고 자동화의 이탈을 문서로만 남긴다(현재 상태)

**제 의견은 (A)** 입니다 — 체크리스트를 사람이 손으로 수행할 때도 1개만 바꾸면
같은 이유로 검증이 얕아집니다. 다만 기준 문서 수정이라 승인 없이 하지 않았습니다.

### ②-2 UPS 설정 결함이 "기존 이슈" 가 맞는지

사용자가 "기존이슈일꺼야" 라고 하셨습니다. 사내 이슈 번호를 알려 주시면
`traceability.json` 에 연결해 두겠습니다. 지금은 관찰 사실만 적혀 있습니다.

### ② `Install_01` — 검증 대상 Release Note

`config.json > release_note` 가 2026-08-10 캡처 baseline 이고 `_source` 에 "교체
필요" 로 표시돼 있다. **실제 검증 대상 Release Note 를 주시면** `Install_01` 을
MANUAL → 자동 판정으로 올리고 추적성도 연결할 수 있다.

### ③ `Install_02` — 지원 OS Build 목록과 DICOM 어댑터 별칭

`config.json > prerequisites.dicom_nic_alias` 와 지원 OS Build 기준을 주시면
현재 SKIP 인 항목을 자동 판정으로 바꿀 수 있다.

### ④ 중단 정책이 맞바꾼 것

FAIL 이 나면 그 TC 를 중단하므로 **첫 FAIL 뒤의 판정 정보는 수집되지 않는다.**
예: `XIPL_03` 은 Step 9(제품 결함)에서 멈춰 Step 10 의 "GPU 없음 SKIP" 기록이
사라졌다. 시간을 아끼는 대신 그 TC 는 사람이 본다는 전제다. 원하시면
`config.json > regression.stop_tc_on_fail` 을 `false` 로 두면 예전처럼 끝까지
수행한다.

---

## 6. 다음 세션용 프롬프트

```text
Bellalun Viewer QA 자동화를 아래 경로에서 이어서 진행해줘.

프로젝트 루트: C:\Users\ksj74\OneDrive\Desktop\자동화\Bellalun Viewer
Git 저장소: 같은 경로의 auto

먼저 auto/AGENTS.md, auto/NEXT_WORK.md, auto/NEXT_TASK.md, ..\프로젝트 상세.html,
그리고 지식 폴더의 영구 지침 3종을 읽어 현재 상태와 규칙을 파악해라.
TC 원문은 Bellalun_Viewer_기본기능_Checklist_개정본.xlsx의 `개정 TC` 시트만 기준으로
삼는다(지식 폴더의 다른 체크리스트는 번호 매핑이 다르다).

가장 먼저 `python run.py portability-check` 의 "관리자 권한"이 True 인지 확인해라.
False 면 UI 자동화가 전부 차단되므로 그 사실을 먼저 보고하고 UI 가 필요 없는
작업만 진행해라.

P0
1. TC_Basic_WorkFlow_13 Step 4 의 로그인 ID 콤보 선택을 견고하게 고쳐라.
   flows.select_login_id 가 OCR 로 고르고 확인하지 않는다. tests/xipl_flows.py 의
   _click_general_param_combo 와 같은 방식(고른 뒤 ui.current_login_id() 로 확인,
   틀리면 다음 후보로 재시도)으로 바꾸고 reset-environment 후 run-wf13 으로 검증해라.
2. NEXT_WORK.md 5절 ①(XIPL_05 의 Q.C 채점 결과 판정)에 대한 사용자 답을 확인하고
   반영해라. 답이 없으면 그대로 두고 다시 물어라.

P1
3. python run.py probe-preset3d 로 3D-N/3D-W Preset 목록 컨트롤을 실측하고
   core/flows.py 상수와 NEXT_TASK.md 에 기록해라. 번호가 이어질 것이라 추측하지 마라.
4. 그 위에 "새 3D Preset 이 그 시점 Default Recon Parameter 를 물려받는가"를
   TC_XIPL_compatibility_07 에 추가해라(Service Manual 근거). 정리는 UI 삭제로 하고
   삭제 전후 DB 를 대조해 대상 외 삭제를 막아라.
5. TC_XIPL_compatibility_04 에 DefaultImgProcess 원복을 추가해라.
6. flows.demo_acquire_step 의 고정 대기(settle=14)를 wait_new_group 기반으로 바꿔라.
   호출부가 WF_01/WF_02/run-sys3d 이므로 그 셋을 회귀 순서로 실제 지나가라.

검증·Git
- 긴 실행 전에 반드시: py_compile, tools_check_module_attrs.py,
  tools_check_regression_names.py, tools_traceability.py,
  python -m unittest discover -s tests -p "test_*.py"
- 고친 뒤 전체 회귀를 1회 돌리고 실제 결과만 기록해라.
- 문서를 갱신해라: README.md(간결·최신 회귀 1건), ..\프로젝트 상세.html(직접 갱신,
  auto/ 안에 만들지 말 것), NEXT_WORK.md, NEXT_TASK.md, automation_scope.json,
  traceability.json, 지식/[자동화 구현 현황].
- git status/diff/remote 검토 후 관련 파일만 commit 하고 git push origin main.
  Force Push·history 재작성 금지. config.json, Reports/, Evidence/, Log/, Cache/,
  Temp/, work/ 는 커밋하지 마라.
- 테스트하지 않은 것을 성공했다고 기록하지 마라.
```
