# 다음 작업 (2026-08-26 기준)

> **문서 지도 — 이 문서의 역할과 다른 3개 문서와의 관계**
> 이 문서는 **현재 상태와 다음에 할 일**만 담는다 — 최신 회귀 결과, 이번 회차에 바꾼 것, 남은 문제, P0/P1/P2, **사용자 판단이 필요한 항목(5절)**, 다음 세션용 프롬프트(6절).
> **영구 규칙**은 `AGENTS.md`, **영구 구현 규칙과 사고 이력**은 `..\지식\[자동화 운영 지침] ...md`, **지난 회차의 누적 실측 기록**(컨트롤 ID·확정한 제품 동작)은 `NEXT_TASK.md` 에 둔다 — 그 셋에 속하는 내용을 여기에 쌓지 않는다.
> **읽는 순서 — `README.md` 최상단 "온보딩 요약" → `AGENTS.md` → 이 문서 → `[자동화 운영 지침]`(상단 "증상 → 원인 → 조치" 색인부터) → 필요할 때 `NEXT_TASK.md` 검색.**

---

## 1. 현재 상태

| 항목 | 값 | 근거 |
|---|---|---|
| 기준 문서 | `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC` — **TC 37건** | 2026-08-24 `TC_XIPL_compatibility_07` 추가 |
| 자동화 범위 | 완전자동 **20** / 부분자동 7 / 수동 10 (+ 보조 4) | `python run.py list` |
| 코드 규모 | Python **27,440줄** / 모듈 79개 (core 35 · tests 31 · `run.py` · `tools/` 12) | 2026-08-26 재실측 |
| 회귀 밖 단독 점검 | **설치 패키지 검증** `verify-install-package` — 설치하지 않고 Welcome~Summary 확인 | 2026-08-26 추가 |
| 추적성 | TC 37건 중 24건에 사양 인용 68건, 위반 0 | `python tools/traceability.py` |
| 단위 시험 | **71건** 전부 통과 | `python -m unittest discover -s tests -p "test_*.py"` |
| **최신 전체 회귀** | **2026-08-26 18:52~20:28 (26차)** — TC 27건: PASS 22 / FAIL 2 / MANUAL 2 / BLOCKED 1, 검증 275개: PASS 261 / FAIL 7 / MANUAL 3 / SKIP 1 / BLOCKED 3, **96.3분**<br>남은 FAIL 2건은 **둘 다 제품 결함**이고 자동화 결함은 0건이다 | `Reports/Result_20260826_202818.json` |

### 24차 회귀의 FAIL 2건

| TC | 성격 | 내용 |
|---|---|---|
| `TC_Basic_WorkFlow_14` Step 7 | **제품 결함** (계속 보고) | UPS 설정은 저장·재기동 유지되지만 Export 파일에 포함되지 않아 `EATON El`이 Import 후 `None`으로 남는다. DB 7개 변경 항목과 38개 설정 섹션은 모두 정상 복원 |
| `TC_XIPL_compatibility_03` Step 9 | **제품 결함** (계속 보고) | Apply 후 재진입하면 3D 파라미터가 기본값으로 복귀. 사양서1 277쪽 SRS 03-50-230 위반. 완화하지 않는다 |

> 검증 FAIL 7건 중 **2건은 "미수행"** 이다 — 중단된 TC 의 남은 Step 을 채운 것이라
> 제품 결함 판정이 아니다(2.2 참고).

### 회귀 이력 (최근 3회)

| 회차 | 일시 | TC 판정 | 검증 | 소요 | 비고 |
|---|---|---|---|---|---|
| 22차 | 08-25 08:19 | PASS 19 / FAIL 3 / MANUAL 5 | 267개 | 104.6분 | WF14 개선 전 기준 |
| 23차 | 08-25 18:34 | PASS 19 / FAIL 3 / MANUAL 3 / BLOCKED 2 | 272개 | 93.5분 | XIPL_06 Save As 자동화 결함 발견 |
| **24차** | **08-25 20:44** | **PASS 20 / FAIL 2 / MANUAL 3 / BLOCKED 2** | **271개** | **94.1분** | XIPL_06 수정 후 PASS. 남은 FAIL 2 = 제품 결함 |

---

## 1-A. 2026-08-25 오후 회차 — `TC_Basic_WorkFlow_14` 집중 개선

### 최종 결정: 목록 스크롤은 차기 개선

스크롤 목록은 같은 가상 `ListItem` HWND/ID를 재사용해 조금 내린 뒤 일부 행만 읽고도
끝으로 오인했다. 사용자 지시에 따라 이 불완전한 스크롤은 제거했다. 현재 화면에 보이는
값과 DB 전수 대조는 자동 수행하고, 화면 아래 숨은 행의 상세값은 결과에 `MANUAL`로
기록한다. 해제 조건은 스크롤 위치 또는 첫/마지막 실제 문구로 이동을 증명하고, 겹치는
행을 제거하면서 끝 행 도달을 보장하는 전용 탐색기와 전후 DB 무변경 시험이다.

결과 CSV/JSON/TXT/HTML은 공통 실행환경·메타데이터와 함께 각 Check에 원본 체크리스트의
`수행 절차`, `기준 기대 결과`, `자동화 기대값`을 나란히 표시한다. `BLOCKED`도 SKIP과
분리하고 MANUAL/SKIP/BLOCKED에는 사유·해제 조건·이 실행으로 말할 수 없는 것을 남긴다.

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

## 1-B. 2026-08-26 — 설치 패키지 검증(회귀 밖 단독 점검) 신설

**무엇을 만들었나.** 신규 설치용 `Install.exe` 패키지를 **설치하지 않고** 사양서·
매뉴얼과 대조하는 단독 점검을 추가했다.

```
python run.py verify-install-package                      # 경로·옵션을 물어본다
python run.py verify-install-package --package "<폴더>"    # 경로를 묻지 않는다
python run.py verify-install-package --language 한국어 --theme "Dark Violet" --kiosk Use
python run.py verify-install-package --probe-options       # 드롭다운 목록 전문 대조(느리다)
```

**라이선스는 자동화가 넣지 않는다**(2026-08-26 사용자 지시). 실제 설치에 쓰이는
값이라 사람이 설치 화면에서 직접 넣고 Next 까지 누른다. 자동화는 Hardware Key 와
입력칸 구조만 확인하고 **화면이 Summary 로 넘어갈 때까지 기다린다** — 기다리는 동안
인스톨러가 띄우는 안내(잘못된 라이선스 등)를 터미널에 그대로 전하되 **닫지는 않는다.**

| 파일 | 역할 |
|---|---|
| `core/installer_ui.py` | Install Wizard 전용 UI 드라이버 (컨트롤 지도 · 페이지 판정 · 콤보 실측) |
| `tests/install_package.py` | 판정 7종 (`Pkg_Static_01~03`, `Pkg_Wizard_01~05`) |
| `tests/install_package_flow.py` | 대화형 실행 흐름 (경로·옵션·라이선스를 사람에게 묻는다) |

**회귀에 넣지 않은 이유.** 회귀는 **이미 설치된** Viewer 를 대상으로 돌고, 이 점검은
**설치 이전** 패키지를 본다. 전제도 대상도 다르다. `run.py` 는 이 명령을 `Context`
생성 **이전**에 가로챈다 — `Context` 는 `BellalunData` 를 못 찾으면 예외를 던지는데,
신규 설치 점검은 바로 그 폴더가 없는 PC 에서 도는 일이기 때문이다.

### 실측으로 확정한 인스톨러 동작 (전부 `Bellalun1.0.12.105` 실물)

| 항목 | 실측값 | 근거 문서 |
|---|---|---|
| 설치 단계 | 신규 설치 6개 (Welcome/Configure Path/Register Options/Input License/Summary/Install Software) | SRS 08-10-10, 업그레이드는 3개(08-10-20) |
| Default Language | English · 한국어 · 日本語 · Русский (기본 English) | SRS 01-10-30 |
| Default Theme | Pure White · Dark Violet · Light Violet (기본 Pure White) | SRS 01-10-20 |
| KIOSK Option | Use · Not Use | SRS 08-10-10 |
| KIOSK 기본값 | 레지스트리 `Winlogon\Shell` 에 뷰어 경로가 있으면 Use, 아니면 Not Use | SRS 08-10-10 — 실측 PC 는 Shell 미설정이라 Not Use |
| Viewer 경로 | `C:\Program Files\Bellalun` | SRS 08-10-10 |
| Database 경로 | `D:\BellalunData` | SRS 08-10-10 |
| 라이선스 | 입력칸 4개, 자릿수 **4-5-4-5 = 18자** (`EM_GETLIMITTEXT` 실측) | 안내 문구 "18-character license key" 와 일치 |
| 라이선스 미입력 | Next 가 막히고 `Please enter license key` 팝업 | SRS 08-10-10 "사용 가능한 라이선스를 입력하지 않으면 설치를 진행할 수 없다" |
| EULA 비동의 | Next 가 막힘 | Service Manual 설치 절차 |
| Install Package 버전 | 1.0.3.0 | 사양서2 버전 관리표 (뷰어 V1.0.12 ↔ V1.0.3) |
| 코드 서명 | Valid / `Vieworks Co., Ltd` | SRS 08-10-10 |
| Summary 항목 | Operation System · Viewer Version · Database Location · Viewer Location · Default Language · Default Theme · License · XIPL License · XIPL Tomo License **(KIOSK 없음)** | 매뉴얼 "설치 정보를 확인하고 Install" |
| XIPL 라이선스 | Viewer 라이선스로 **자동 발급되어 Summary 에 표시** | SRS 08-10-10 "Viewer 라이선스를 사용하여 XIPL 라이선스를 자동 발급 등록한다" |
| Summary 버튼 | 이 화면에서 Next 가 **Install** 로 표시된다 | Service Manual 설치 절차 |

### 첫 실행으로 찾은 것

- **제품/패키지 결함 — `Support\XIPLInstall.reg` 누락.** `Install.xml` 이
  `regedit /s "[RunningDirectory]Support\XIPLInstall.reg"` 로 실행하는 파일이 패키지에
  없다(참조 18건 중 1건). 사양서2 SRS 08-10-10 도 "XIPL 설치 후 registry 변경 -
  XIPLInstall.reg 실행" 으로 명시한다. 같은 방식으로 참조되는 `shell_Kiosk.reg` /
  `shell_NoKiosk.reg` 는 들어 있고, **압축 해제 전 원본 zip 에도 없어** 해제 누락이
  아니다.
- **Summary 가 KIOSK 선택을 표시하지 않는다(MANUAL).** Register Options 에서 KIOSK
  Option 을 고를 수 있는데 Summary 에는 그 값이 없다. 실측한 Summary 항목은 Operation
  System / Viewer Version / Database Location / Viewer Location / Default Language /
  Default Theme / License / XIPL License / XIPL Tomo License **9개뿐**이다. 매뉴얼은
  "설치 정보를 확인하고 Install 버튼을 클릭" 이라고 하지만 **어떤 항목이 실려야 하는지는
  사양서·매뉴얼에 정의가 없어** 결함으로 단정하지 않고 사실만 남긴다.
- **안내 문구와 화면 구성 불일치(MANUAL).** Register Options 안내 문구는
  *"Please select viewer mode, image processing parameter..."* 라고 하지만 화면 항목은
  Default Language / Default Theme / KIOSK Option 3개뿐이다. 문구 정정인지 항목 누락인지
  사양 확인이 필요하다(컨트롤 ID 도 1402 가 결번이다).
- **설치 로그 — 처음에 오판했다(정정).** SRS 08-10-10 의 표기
  `C:\Documents\Bellalun\InstallLog` 를 **드라이브 루트의 절대경로로 읽어** "폴더가 없다 =
  로그가 생성되지 않는다" 고 판정했다. 실제 위치는 **로그인 사용자의 Documents 폴더
  아래**(`C:\Users\<계정>\Documents\Bellalun\InstallLog`)이고, 로그는 사양대로 정상
  생성되고 있었다 — 창만 띄웠다 닫아도 파일이 하나 생기고(242바이트), 실제 설치를 하면
  단계별 기록이 쌓인다(2,228바이트). 2026-08-26 사용자가 실제 경로를 알려 주어 바로잡았다.
  경로는 이제 셸에 물어 해석하고(`install_package.install_log_dir`), 판정도 MANUAL 이
  아니라 **PASS/FAIL 로 확정**한다.

### 사용자 지시로 바꾼 동작 (2026-08-26 2차)

- **라이선스 자동 입력을 뺐다.** 사람이 직접 넣고 Next 를 누르며, 자동화는 안내 후
  Summary 도달을 기다린다. 같은 이유로 "미입력 상태에서 Next" 시도도 뺐다 — 사람이
  입력하려는 화면에 자동화가 팝업을 띄우게 된다.
- **Register Options 에서 항목을 전부 눌러 보지 않는다.** 고를 값이 정해져 있으면
  드롭다운을 **한 번만** 열어 항목 수를 세고 화면을 캡처한 뒤, 사양 목록에서의 위치로
  원하는 값을 눌러 고른다. 누른 뒤 콤보 값을 읽어 검증하므로 순서가 바뀐 빌드에서도
  조용히 틀리지 않는다(어긋나면 전수 순회로 폴백). 항목당 30초 → **2.5초.**
  목록 전문 대조가 필요하면 `--probe-options`.
- **Summary 를 스크롤하며 확인한다.** 본문이 한 화면에 안 들어가서 위에서 아래로
  훑으며 캡처한다(판정 자체는 `WM_GETTEXT` 전문으로 하므로 스크롤 위치와 무관).
- **Welcome 문구 검증을 넓혔다.** EULA.txt 전문 대조에 더해 분량(1,000자 이상),
  치환 문자(U+FFFD) 유무, 첫 문장, `ARTICLE 1`·`SOFTWARE LICENSE` 포함 여부를 보고
  본문을 **끝까지** 스크롤하며 캡처한다(29KB · 24장 · 17초, `ARTICLE 7` 종료 문구까지
  닿는 것을 실측했다). 처음에 캡처 상한을 12로 뒀더니 **화면이 중간에서 멈췄고**
  사용자가 곧바로 알아봤다 — 상한은 60으로 올렸고, 그래도 걸리면 판정 `actual` 에
  "상한에 걸려 뒷부분이 남았을 수 있다" 고 적는다. 조용히 자르지 않는다.
- **라이선스는 값을 대조하지 않는다.** 사람이 직접 넣은 값이라 자동화에 기대값이
  없다. Summary 에서 **입력 여부와 4-5-4-5 형식만** 보고, 기록에는 첫 칸만 남기고 가린다.

---

### 만들면서 고친 자동화 쪽 결함 (제품 결함 아님)

- **`core.ui.children()` 의 중복이 컨트롤을 가렸다.** 재귀 평탄화가 같은 컨트롤을 여러 번
  담아, 좌표로 정렬해 앞 4개를 자르니 1·2번 입력칸이 두 번씩 들어가고 3·4번이 잘렸다.
  라이선스 자릿수가 `4-5-4-5` 가 아니라 `4-4-5-5` 로 읽혔다. `InstallerUi._tree()` 가
  hwnd 로 중복을 없앤다 — **모든 컨트롤 조회는 이 함수를 거친다.**
- **커스텀 버튼은 누름 시간이 짧으면 무시한다.** `ViewerUi.click()`(down→up 0.06초)으로
  Next 는 눌리는데 Back 은 눌리지 않아 "Back 이 매뉴얼과 달리 동작하지 않는다"고 오판할
  뻔했다. 0.2초로 늘리자 정상 동작했다. `InstallerUi.hold_click()` 이 이 시간을 잡는다.
- **입력이 끊긴 실행에서 무한 루프.** 경로를 되묻는 루프가 stdin 이 닫힌 실행(파이프)에서
  빠져나오지 못했다. `_ask()` 가 EOF 를 기억하고(`input_closed()`) 되묻는 루프가 그것을
  보게 했다. `--package` 로 아예 묻지 않고 돌릴 수도 있다.

---

## 1-C. 2026-08-26 — 회귀 전제(DB 환경) 자동 복구

**계기.** 신규 설치를 마친 PC 에서 뷰어가 더블클릭해도 뜨지 않았다. 원인이 두 겹이었다.

| | 원인 | 근거 |
|---|---|---|
| 1 | `MSSQL$BELLALUN` 서비스가 `Stopped` + `Manual` | 뷰어 로그 `Database service is stopped.` (`CViewerApp::CheckDatabaseServer`), 4회 시도 모두 동일 + 크래시 덤프 4개 |
| 2 | **DB 데이터 파일이 하나도 없음** | `Unable to open the physical file "D:\BellalunData\Database\ACCOUNT.mdf". Operating system error 2`, `DATA` 는 `SUSPECT` |

이전 설치가 남긴 SQL 인스턴스 때문에 인스톨러가 `CheckFile`(master.mdf) 조건으로 **MSSQL
설치를 건너뛰었고**, 서비스가 꺼진 채로 Viewer 설치가 돌아 **DB 가 만들어지지 않았는데
설치는 "Succeed to all install program" 으로 끝났다.** 설치 로그에 MSSQL·DB 초기화 단계는
아예 기록되지 않는다.

**조치한 것 (회귀가 같은 지점에서 멈추지 않게)**

- `core/dbreset.ensure_database_service(ctx)` 신설 — DB 서비스를 `Running` 으로 만들고
  수동 시작이면 자동 시작으로 돌린다. **바꾼 내용을 반환**한다.
- `run.py` 의 `AUTOMATION_ENVIRONMENT` 점검에 `DB 서비스` 판정 추가 — 실행 명령(run-*)은
  **자동 복구하고 그 사실을 판정 `actual` 에 적는다.** `portability-check` 는 진단
  전용이라 **고치지 않고 FAIL 로 알리기만** 한다.
- `restore_baseline` 이 **데이터 파일 없는 DB 도 되살린다** — `SET SINGLE_USER` 가
  실패하면 `DROP DATABASE` 후 `RESTORE ... WITH REPLACE, MOVE`. 이 경로가 없어서
  그날 `reset-environment` 가 죽었다.
- `reset-environment` 는 복구 내역(서비스 변경 / 새로 만든 DB)을 콘솔에 출력한다.

**검증 (실측)**

```
[정지 상태로 되돌림]  STOPPED / DEMAND_START
[자동 복구]           STOPPED -> RUNNING, DEMAND_START -> AUTO_START
[DB 접속]             ping 성공, DATA.SOFTWARE_VERSION = 1.0.12.105
[portability-check]   FAIL 로 알리고 상태를 바꾸지 않음 (진단 전용 원칙 지킴)
```

복구 후 뷰어가 정상 기동해 로그인 화면까지 올라오는 것을 확인했다(테마 Pure White,
`Running in demo mode.` 안내).

**남은 QA 발견** — 설치 프로그램이 **DB 초기화 실패를 감지하지 못하고 "완료" 로 끝낸다.**
DB 가 하나도 없는데 설치 성공으로 기록되고, 설치 로그에도 그 단계가 남지 않아 사용자는
실행해 봐야 안다. 사양 확인이 필요하다.

---

## 1-C-2. 2026-08-26 — 26차 회귀 FAIL 3건 원인 규명과 수정

사용자가 지목한 세 건을 조사했다. **회차 비교가 성격을 갈랐다.**

| 회차 | Install_02 | WorkFlow_14 | XIPL_06 |
|---|---|---|---|
| 08-25 22:19 | PASS | FAIL | PASS |
| 08-26 14:16 | **FAIL** | FAIL | **FAIL** |

Install_02 와 XIPL_06 은 **어제 통과했다가 오늘 실패**했고, 그 사이 사건은
**오늘 오전의 Bellalun 재설치(11:03~11:08)** 다.

### ① `TC_Basic_Install_02` — 자동화 문제(제품 정상). **고쳤다**

재설치 중 VC++ 재배포가 갱신되며 **표시명이 바뀌었다.**

```
config 패턴 : *Visual C++ 2015-2022 Redistributable*   -> 0건
실제 설치명 : Microsoft Visual C++ v14 Redistributable (x64) - 14.50.35719
              Microsoft Visual C++ v14 Redistributable (x86) - 14.50.35719
```

설치 로그에도 `Succeed to install program (VC 2015 2022 Redistributable x64)` 로
정상 설치가 찍혀 있다. **제품은 멀쩡한데 자동화가 옛 이름으로 찾아 못 본 것**이고,
`stop_on_fail` 때문에 Step 2~4 가 미수행 FAIL 로 채워져 5건이 됐다.

**수정** — 이름은 느슨하게(`Visual C++` + `Redistributable`) 보고 **메이저 버전으로
확정**한다(`tests/install.vcredist_entries`). 2015/2017/2019/2022 는 모두 v14
런타임이라 14.x 이고, 2005/2010/2012/2013 은 8/10/11/12 라 자연히 걸러진다.
기준은 `config.json > prerequisites.vcredist_min_major`(기본 14).
**실행해 확인: `install_02` 전체가 PASS 로 돌아왔다**(x64/x86 모두 탐지).

### ② `TC_Basic_WorkFlow_14` — **제품 결함이 맞다. 그대로 보고한다**

```
Setting > Device > UPS   기대: EATON El   실제: None
```

2026-08-26 재확인: `CONFIGURATION` DB 에 **UPS 관련 컬럼 0건 / 테이블 0건 /
`EATON` 문자열 0건.** 즉 UPS 설정은 설정 DB 가 아닌 곳에 저장되고, Export(`.vms`)
는 설정 DB 백업 기반이라 **처음부터 Export 대상이 아니다.** 그런데 재기동 후에는
값이 남으므로 **저장은 되는 설정**이다 — Import 로 되돌릴 방법이 없다.

사양서1 60절이 Export 대상을 *"Study 정보를 제외한 **모든** 설정 정보"* 로 정의하므로
**사양 불일치**다. 화면상 멀쩡해 보이는 이유는 값이 그 자리에 잘 남아 있기 때문이고,
문제는 **Export/Import 왕복에서 사라진다**는 것이다. 완화하지 않는다.

### ③ `TC_XIPL_compatibility_06` — 자동화 문제(간헐). **고쳤다**

```
RuntimeError: XIPL helper Save As 대화상자를 유일하게 찾지 못했습니다(후보 0개)
```

**Save As 버튼은 눌렀는데 대화상자가 안 잡혔다.** 실패 직전 증거 캡처
(`Evidence/Viewer_XIPL/TC_XIPL_compatibility_06_preview.png`)를 보면 PIM 편집기의
값 편집(Contrast)이 **아직 열려 있다** — `save_as()` 주석이 이미 경고하는 "편집 커밋
직후 WPF 재배치" 구간과 겹쳤다.

문제는 그다음이었다. 예전 구현은 **고정 0.8초 뒤 한 번만 보고 없으면 즉시 실패**했다
— 이 저장소 운영 지침 1절 '상태 기반 대기' 를 지키지 않은 유일한 자리였고, 어제
PASS / 오늘 FAIL 이 그 간헐성을 그대로 보여준다.

**수정** — 대화상자를 **나타날 때까지 다시 확인**한다(`dialog_timeout=12`, 0.3초 간격).
찾으면 즉시 진행하므로 정상 회차는 느려지지 않고, 실패 메시지에는 몇 초를 기다렸는지
남긴다.

---

## 1-F. 2026-08-27 — Dose SR 은 **전송 경로가 달랐다** (내 오판을 바로잡음)

**사용자 지적으로 사양을 확인해 바로잡았다.** 앞 회차에 "제품이 Dose SR 을 전송
큐에 넣지 않는다, 사양 확인 필요" 라고 보고했는데 **틀렸다.** 사양은 이미 명확했고,
**자동화가 사양이 금지한 경로로 시험하고 있었다.**

### 사양 (사양서1, 두 곳)

> **전송되는 경우**: *"Send Dose SR 옵션이 활성화되어 있을 때, 아래의 경우에 Dose SR
> 을 전송한다. ○ **Examine Mode 에서 자동 전송 옵션이 활성화**되어 있을 때.
> ○ **Examined 모드에서 모든 영상을 전송**할 때."*
>
> **전송되지 않는 경우**: *"Dose SR 은 **검사가 종료될 때만** 전송이 된다.
> (**Examine/View 모드에서 Send/Multi-Send 버튼을 클릭했을 때는 Dose SR 을 전송하지
> 않는다**)"*

`WF_06` 은 `open_test_study` 로 검사를 **View 모드로 열고** Send 했다 — 사양이
"전송하지 않는다" 고 명시한 바로 그 경로다. 개정본 Step 1 도 *"**Examined 창에서**
검사를 선택한다"* 이므로 체크리스트와도 어긋나 있었다.

**증거는 이미 회귀 안에 있었다.** `WF_07`(검사 종료 Auto Send)은 Queue 에
`DataType=1` 행이 잡히고 `...88.67`(RDSR)을 수신했고, `WF_15`(Examined 전송)의 수신
UID 에는 `...3767.1.1` 이 있었다 — 사양서1 이 말한 *"Dose SR 은 영상 Instance UID
마지막에 '.1.1' 을 붙인다"* 그대로다. **두 사양 경로에서는 진작 오고 있었다.**

### 고친 것 세 가지 (모두 실행해 확인)

| | 문제 | 조치 |
|---|---|---|
| 1 | View 모드에서 Send | `flows.send_examined_study` 신설 — **Examined 툴바 Send(2189)** 경로. `send_and_verify` 에 `sender` 를 받아 TC 가 경로를 고른다 |
| 2 | Dose SR UID 가 "DB 에 없는 UID" 로 FAIL | Dose SR 은 영상이 아니라 제품이 만드는 보고서라 `INSTANCE` 에 행이 없다. **영상 UID 대조에서 제외**하고 개수를 `actual` 에 남긴다 |
| 3 | Queue 에서 RDSR 을 0건으로 셈 | 제품이 Queue 의 `ClassUID` 를 **채우지 않는다**(실측 전부 `None`). 구분자는 `DataType`(0=영상, 1=Dose SR) — `sv.is_dose_sr_row` 로 바꿨다 |

### Examined 툴바 — **툴팁으로 확정**했다 (아이콘으로는 구분 불가)

| ID | 툴팁 |
|---|---|
| **2189** | **Send** |
| 2190 | Multi Send |
| 2196 | Pre-send Preview |
| 2188 | Print |
| 2191 | Export |
| 2197 | Move Image |

`flows.py` 가 남긴 전례(2196 을 아이콘만 보고 '검사 내 검색' 으로 오인)를 따라
같은 방법을 썼다. Print/Export 가 확정돼 **3D-W 를 Print/Export 로 넓힐 때 바로 쓸 수
있다.**

### 결과 — `WF_06` 이 처음으로 완전 통과

```
Step 2 전송  : 4건, modalities ['MG','SR'], SOP Class 3종(MG/DBT/RDSR)
Step 3 Queue : image_rows=3, rdsr_rows=1                    PASS
Step 4 수신  : image_objects=3, rdsr_objects=1              PASS
Step 5 RDSR  : PatientID/StudyInstanceUID 일치, mismatch=[]  PASS
```

BLOCKED 3건이 모두 사라졌다. **Dose SR 은 제품 결함이 아니었다.**

---

## 1-E. 2026-08-26 — 26차 회귀(Storage 전환 후) 결과와 후속 수정

**1차 회귀 (18:27 종료, 95.8분)** — TC 27건 PASS 21 / FAIL 4 / MANUAL 2.
`Install_02` 와 `XIPL_06` 은 **오늘 고친 것이 회귀에서도 통해 FAIL 목록에서 사라졌다.**
대신 **3D-W 픽스처 확장의 파급**으로 세 곳이 드러났고, 전부 고쳐 개별 검증했다.

| 증상 | 원인 | 조치 |
|---|---|---|
| `WF_05`/`WF_06` Step 3 — Queue 3건 중 마지막이 `State=1` | 수신은 안정됐는데 **Queue 상태 갱신이 늦었다.** 전송 객체가 늘어(3D-W) 드러났다 | `wait_queue_settled` 신설 — Queue 가 전부 Done 이 될 때까지 상태를 보고 기다린다 |
| `send_and_verify` 의 `received_objects` 가 실제와 다름(1 vs 4) | **수신을 먼저 세고 전송을 나중에 봤다.** 전송 중인데 서명이 잠깐 멈춘 것을 "안정" 으로 오판 | **순서를 뒤집었다** — Queue 등록(`wait_queue_registered`) → Queue 완료 → 그 다음 수신 확정 |
| `XIPL_03` Step 1 — Raw 가 2건이라 `len == 1` 실패 | 3D-W 추가로 Raw 가 3D-N/3D-W 두 건 | 3D-N 의 Raw(첫 건)를 대상으로 삼고, 전체를 `actual` 에 남긴다 |

### 2차 회귀 결과 (20:28 종료, 96.3분) — **자동화 결함 0**

수정을 넣고 다시 돌렸다.

| | 1차 (18:27) | 2차 (20:28) |
|---|---|---|
| TC | PASS 21 / FAIL 4 / MANUAL 2 / BLOCKED 0 | **PASS 22 / FAIL 2 / MANUAL 2 / BLOCKED 1** |
| 검증 | PASS 243 / FAIL 23 | **PASS 261 / FAIL 7** |

판정이 바뀐 것은 둘뿐이고 둘 다 의도한 방향이다.

- `WF_05` **FAIL -> PASS** (Queue 대기·순서 수정)
- `WF_06` **FAIL -> BLOCKED** (Queue 문제는 사라지고 **원래 상태인 Dose SR 미수신**만 남음)

**남은 FAIL 2건은 둘 다 제품 결함**이다.

| TC | 내용 | 사양 근거 |
|---|---|---|
| `WF_14` Step 7 | UPS 설정이 Export/Import 로 복원되지 않음 | 사양서1 60절 "Study 정보를 제외한 모든 설정 정보" |
| `XIPL_03` Step 9 | Apply 후 Recon/Syn 10개 값이 기본값으로 되돌아감 | 사양서1 277쪽 SRS 03-50-230 |

**Station Name 이 회귀에서 실제로 대조됐다** — 기준 스냅샷 갱신이 통했다.

```
WF_04 Step 5  기대 AUTOSTN_260826  실제 ['AUTOSTN_260826']  PASS
WF_05 Step 5  기대 AUTOSTN_260826  실제 ['AUTOSTN_260826']  PASS
WF_06 Step 5  기대 AUTOSTN_260826  실제 ['AUTOSTN_260826']  PASS
```

**3D-W 도 Send 까지 이어졌다.**

```
WF_02 Step 5  3D-W 등록 3스텝 / 영상 {0:1, 1:2, 2:2, 3:2}      PASS
WF_05 Step 4  3D-N / 3D-W 각각 수신 확인
              recon_series [{54:1}, {55:1}] received_recon=2   PASS
```

---

### 공유 Storage SCP 라서 생긴 문제 (Bunny 에는 없던 것)

`WF_06` 이 **다른 PC 가 보낸 객체** 때문에 FAIL 했다.

```
received_patient_ids: ['DATA_FLOW_MWL_01', 'VXVUE_260826_182948']
not_in_db: {'PatientID': ['VXVUE_260826_182948'], ...}
```

10.13.0.222 는 **여러 PC 가 함께 쓰는 SCP** 다. 우리가 보내는 사이에 VXvue 시험이
보낸 객체가 섞여 "DB 에 없는 UID" 로 판정됐다. 그래서 수신 판정을 **환자 단위로
좁혔다** — `received(ctx, patient_id)` / `wait_received_stable(ctx, patient_id)`.
폴링도 서버 전체 서명 대신 **그 환자의 인스턴스 수**를 보므로, 남이 보내는 동안에도
안정을 찾는다. 다운로드도 우리 스터디만 받아 더 빠르다.

**남은 주의 — `clear_received` 는 아직 서버 전체를 지운다.** 개별 스터디 삭제 API 가
없어(`DELETE /api/studies` 만 존재) 전송 전 초기화가 **다른 사람의 수신 데이터까지
지운다.** 지금은 환자 필터가 있어 판정에는 문제가 없지만, **공유 서버에서 남의 데이터를
지우는 것 자체가 위험**하다. 서버에 스터디 단위 삭제가 생기면 그것으로 바꾸고,
그때까지는 초기화를 생략할지 사용자와 정해야 한다.

### Dose SR — **원래부터 오지 않았다** (내 변경과 무관)

`WF_06` 의 Dose SR 판정 이력을 전 회차에서 뽑아 보니 계속 BLOCKED 였다.

```
20260825_221901 (Bunny 시절)  DSR: BLOCKED / BLOCKED / BLOCKED
20260826_141622               DSR: BLOCKED / BLOCKED / BLOCKED
20260826_184622 (Storage 전환) DSR: BLOCKED / BLOCKED / BLOCKED
DICOM_STORAGE_QUEUE DataType 분포: {0: 3}   <- DataType=1(Dose SR) 행이 0건
```

즉 **제품이 Dose SR 을 전송 큐에 넣지 않는다.** Storage 설정은
`SendDoseSR=1` 로 켜져 있고(`WF_06` Step 0 PASS), **서버는 RDSR 을 받을 수 있다**
— 전환 검증 때 `1.2.840.10008.5.1.4.1.1.88.67` 객체를 실제로 내려받아 파싱했다.
**받는 쪽이 아니라 보내는 쪽 문제**이므로 사양 확인이 필요하다.

### `XIPL_03` — 이제 진짜 결함까지 도달한다

Step 1 을 고치자 Step 4/6/7/8 이 PASS 하고 **Step 9 에서 FAIL** 한다.

```
Step 9 Apply 후 TEST_3D 값 유지: retained=False
  Contrast 14->10, Sharpness 16->20, Background Masking 'Not use'->'Use'
```

이것이 README 7절에 적힌 **기존 제품 결함**이다(사양서1 277쪽 SRS 03-50-230
"Apply를 누르게 되면 해당 img 파일에 영상 조정 파라미터 값들이 저장된다" 위반).
예전에는 Step 1 에서 막혀 이 결함을 **확인조차 못 했다** — 고친 덕에 제 자리에서
드러난다.

---

## 1-D. 2026-08-26 — Storage 서버 전환(Bunny -> STORAGE_SCP)과 Send TC 고도화

**무엇이 바뀌었나.** 수신 측 Storage SCP 를 로컬 애플리케이션 Bunny 에서
**원격 웹 서버**로 바꿨다(사용자 지시). **PC 에 Bunny 를 띄우지 않는다.**

| | 이전 | 지금 |
|---|---|---|
| AE Title | `Bunny` | `STORAGE_SCP` |
| 주소 | `127.0.0.1:3000` | `10.13.0.222:11116` (TLS 21116) |
| 수신 확인 | `C:\Program Files (x86)\Bunny\Temp` 파일 스캔 | HTTP API `http://10.13.0.222:5003` |
| 기동 | `ensure_bunny` 가 실행 | **띄울 것이 없다** — `ensure_storage_reachable` 이 도달 가능만 본다 |

**핵심 설계 — 판정 강도를 그대로 유지했다.** 서버 API 는 series 단위까지만 주는데
이 저장소의 Send 판정은 **SOP Instance UID / SOP Class 단위**로 원본과 대조한다.
그래서 `/api/studies/<uid>/download` 로 ZIP 을 받아 `core/dicomlite` 로 파싱한다
(`core/storagescp.py`). 반환 형식이 예전 `dicomlite.scan_dir` 과 같아
**`send_and_verify` 의 판정 로직은 한 줄도 바꾸지 않았다.**

폴링은 서버가 주는 `/api/studies/signature`(`"건수|최근수신시각"`)로 한다 — 회차마다
ZIP 을 받으면 비싸다. 서명이 3회 연속 같으면 **그때 한 번만** 내려받아 확정한다.

### 실측으로 확인한 것 (2026-08-26)

```
scp-status : {"ae_title":"STORAGE_SCP","host":"10.13.0.222","port":11116,
              "running":true,"tls_running":true,"tls_port":21116}
download -> ZIP -> dicomlite 파싱:
  SOPClass=1.2.840.10008.5.1.4.1.1.88.67   Modality=SR   <- RDSR (Dose SR)
  SOPClass=1.2.840.10008.5.1.4.1.1.1.2     Modality=MG   <- 2D
  SOPClass=1.2.840.10008.5.1.4.1.1.13.1.3  Modality=MG   <- 3D 토모(DBT)
```

**Dose SR 수신이 실제로 된다**(사용자 확인 요청 사항). 세 SOP Class 모두
`send_verify` 의 기존 상수와 일치한다.

### Station Name — 사용자 의도와 사양이 다르다

"MWL 로 만든 환자의 station 값이 잘 send 되는지" 확인하려 했는데, **사양은 그
값을 전송에 쓰지 않는다고 정한다.**

> 사양서2 `06. DICOM` MWL 절: *"Worklist에 표기된 Station Name은 **MWL List에서만
> 사용된다.** 그 외의 Station Name은 **Setting > General > DICOM에 설정된 Station
> Name**을 사용한다."*
> Storage IOD 표: `Station Name (0008,1010) 3 VNAP **From Config**`

그래서 판정을 **"수신 객체의 StationName 이 Setting 값과 같은가"** 로 세웠다 —
MWL 오더의 값이 여기 나오면 그것이 사양 위반이다(`sv.configured_station_name`).
`dicomlite.TAGS` 에 `StationName (0008,1010)` 을 추가해 SOP 단위로 읽는다.

Type 3 / VNAP 이라 **설정이 비면 값이 없는 것이 정상**이므로, 빈 값일 때는 FAIL 이
아니라 SKIP 으로 남기고 무엇을 해야 확인되는지 적는다. 현재 이 PC 의
`CONFIGURATION.DICOM_COMMON.StationName` 은 빈 값이다.

### 2D / 3D-N / 3D-W 를 모두 수신 검증

- `WF_02` 가 픽스처에 **3D-W 스텝을 하나 더** 만든다(개정본 판정 Step 2~5 가 끝난
  **뒤에** 덧붙이므로 기존 판정에 영향이 없다). `config.json >
  test_data.include_3d_wide` 로 끌 수 있다.
- `viewer_processing.open_test_study` 가 **2 또는 3 스텝**을 받도록 넓혔고, 3스텝이면
  `step_3d_w` 를 함께 준다. 예전에는 정확히 2 를 요구해 3D-W 를 넣는 순간 이
  픽스처를 쓰는 모든 TC 가 열리지도 못했다.
- `WF_05` 에 **3D-N / 3D-W 각각 수신** 판정을 넣었다. 두 모드는 SOP Class 가 DBT 로
  같아 객체만으로는 구분되지 않으므로 **DB Series 로 되짚는다.**
- `WF_05` / `WF_06` 은 원래 `expect_count=None` 으로 **DB 에서 기대값을 계산**하므로
  픽스처가 늘어도 자동으로 대응된다. 손댈 필요가 없었다.

### 실행 결과 (2026-08-26 16:20~16:44, 실측)

준비 3건을 채우고 Send 경로를 끝까지 돌렸다. **전부 PASS.**

| 단계 | 결과 |
|---|---|
| `setup-dicom` | MWL/Storage/Print 등록 + **C-ECHO 전부 성공** |
| Storage 등록 | `Key=21 STORAGE / STORAGE_SCP / 10.13.0.222:11116 / SCPUseType=0`, 전송 옵션 **Dose SR = Send** |
| Station Name | Setting > DICOM > General 에 `AUTOSTN_260826` 지정(UI 로만 변경, DB 직접 수정 없음) |
| `run-wf01` | MWL 검사(Key=49) + Local 검사(Key=50) 생성 |
| `run-wf02` | **3D-W 포함 픽스처 생성** — `Instances=7` (2D 1 + 3D-N 3 + 3D-W 3) |
| `run-wf04` | **2D Send → 새 서버 수신 확인, 식별 Tag 4종 일치, Station Name 일치** |
| `run-xipl-06` | **PASS** — Save As 폴링 수정이 실제로 동작 |

### Station Name — 사양대로 동작하는 것을 실증했다

MWL 오더는 `station_name="MAMMO"` 로 만들었는데, 수신 객체에는 **Setting 값**이 실렸다.

```
received_station_names  : ['AUTOSTN_260826']
configured_station_name : 'AUTOSTN_260826'
[PASS] Step 5 수신 객체의 Station Name
```

사양서2 *"Worklist에 표기된 Station Name은 MWL List에서만 사용된다"* 가 그대로
확인됐다. MWL 값(`MAMMO`)이 나왔다면 사양 위반이었을 것이다 — 대조군이 정확히 갈렸다.

### 도중에 발견해 고친 것 — `WF_02` Step 8 의 하드코딩

3D-W 를 추가하자 `Step 8 검사 종료 후 Examined 재조회` 만 FAIL 했다. 촬영·저장은
정상이었고(`Instances=7`), 판정이 **`Instances == 4` 를 박아 두고 있었다**
(2D 1 + 3D-N 3). 픽스처를 넓히면 같이 넓혀야 하는 자리다 —
`test_data.include_3d_wide` 로 기대값을 계산하게 고쳤다.

### 회귀에서도 Station 을 검증한다 — 기준 스냅샷을 갱신했다 (2026-08-26)

전체 회귀는 시작할 때 DB 를 기준 스냅샷으로 되돌린다. 예전 스냅샷(2026-08-14)의
`DICOM_COMMON.StationName` 이 비어 있어 Send TC 의 Station 판정이 매 회귀 SKIP 으로
남을 상황이었다. **사용자 지시로 기준 스냅샷을 Station Name 이 든 상태로 갱신했다.**

갱신 절차 — **순서가 중요하다.** 그때의 DB 를 그대로 뜨면 안 된다.

1. 기존 `.bak` 4개를 `Baseline\_backup_20260826_before_station\` 으로 백업
2. `run.py reset-environment` — **기존 기준으로 되돌려 깨끗한 상태**를 만든다
   (그 시점 DB 에는 그날 만든 검사·영상 7건이 있었다. 그대로 뜨면 회귀 기준이
   오염된다)
3. Setting > DICOM > General 에서 `AUTOSTN_260826` 지정 (**UI 로만** 변경)
4. `run.py snapshot-baseline` — 새 기준 저장
5. **복원해서 확인** — `reset-environment` 후 `StationName='AUTOSTN_260826'`,
   `STUDY=0 / INSTANCE=0` 을 실측했다. 값은 살아 있고 검사 데이터는 깨끗하다.

이제 회귀가 복원해도 Station Name 이 남으므로, Send TC 의 Station 판정이 SKIP 이
아니라 **실제 대조**로 돈다.

**되돌리려면** `Baseline\_backup_20260826_before_station\*.bak` 를 `Baseline\` 에
덮어쓴다.

---

### 실행 전 필요한 준비 (2026-08-26 현재 미충족)

Baseline 복원 뒤라 아래가 비어 있다. 실제 Send TC 를 돌리기 전에 채워야 한다.

- 픽스처 `DATA_FLOW_MWL_01` 없음 -> `run-wf01` + `run-wf02`
- 설정된 활성 Storage 없음(`SCPUseType=0`) -> `setup-storage`
- `StationName` 빈 값 -> Setting > General > DICOM 에 값 지정(그래야 Station 판정이 SKIP 을 벗어난다)

---

## 2. 이번 회차에 한 일 (2026-08-24 ~ 08-25)

### 2.0 문서 고도화 Phase 1 + 자동화 구조 보강 Phase 2

- Phase 1: README 온보딩, 4개 문서 지도, 자동화 범위 전수표, 증상→원인→조치
  색인, 문서 수명 정책과 `Archive/` 이관을 반영했다.
- MD→HTML 자동 렌더러를 **2026-08-26에 도입했다**(`tools/render_docs.py`). 원본이
  `..\프로젝트_상세.md` 하나뿐이 되어 "손으로 유지 중인 HTML을 자동 변환물이 덮는다"는
  기존 우려가 없어졌다. 같은 날 `tools_*.py` 10개를 `tools/`로 모으고 접두사를 뗐다.
  `tools/check_docs_sync.py`가 상세 원본이 저장소 문서보다 최신인지와 HTML 재생성
  누락을 함께 검사한다.
- `tools/run_regression.py`가 회귀 Python 바깥에서 실행을 감시한다. 새 전체 회귀
  리포트가 없으면 비정상 종료로 확정해 상태 파일·Windows 알림을 남기고 Viewer를
  안전 종료한다.
- TC 사이에서 Viewer가 사라지면 WER 덤프로 실제 크래시 여부를 구분해 판정에 남기고
  다음 TC용으로 재기동한다(`run.py::recover_viewer_after_termination`).
- `tools/automation_status.py` / `check_automation_status.cmd N`은 개별 TC나 전제 실패
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
| 8 | `tools/check_regression_names.py` 가 **무력화**됐다 | 회귀 사슬을 참조 목록으로 바꾸자 세는 이름이 0개가 되고 통과 메시지는 그대로 나왔다. 0개면 실패로 만들었다 |
| 9 | 로그인 시 **비밀번호를 3번 입력**했다 | PW 필드는 password 스타일이라 `WM_GETTEXT` 가 빈 문자열을 준다. "확인 불가"를 "실패"로 단정한 것이 원인. 재시도를 로그인 단위로 옮겼다 |
| 10 | 저장소의 유일한 단위 시험이 **실패 상태로 방치**돼 있었다 | 아무도 돌리지 않았다. 사전 검사에 넣었다 |

### 2.4 추가한 것

| 파일 | 용도 |
|---|---|
| `core/imginfo.py` | 제품 `.img` 꼬리의 `<INFORMATION>` XML 판독(3D Recon 파라미터). DB 에 없는 근거다 |
| `traceability.json` + `tools/traceability.py` | 사양↔TC 양방향 추적성. 인용을 **매번 원문과 대조**한다. 위조 7건 주입 검출 확인 |
| `core/viewer_processing.wait_new_group()` | 고정 `settle` 대신 DB 도착 조건 대기. 2D 각 2.9초(고정 14초 대비) / 3D 29.5·39.7초(**고정 20초는 오히려 부족했다**) |
| `tests/test_imginfo_and_waits.py` | 단위 시험 26건 |
| `run.py probe-preset3d` | 3D Preset 목록 컨트롤 실측용 조회 전용 프로브 |
| `..\프로젝트_상세.md` / `.html` | **기본 문서**(프로젝트 루트, 저장소 밖). 상세를 먼저 갱신하고 `python tools/render_docs.py` 로 HTML 재생성. README 는 그 축약형 |

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

먼저 auto/AGENTS.md, auto/NEXT_WORK.md, auto/NEXT_TASK.md, ..\프로젝트_상세.md,
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
- 긴 실행 전에 반드시: py_compile, tools/check_module_attrs.py,
  tools/check_regression_names.py, tools/traceability.py,
  python -m unittest discover -s tests -p "test_*.py"
- 고친 뒤 전체 회귀를 1회 돌리고 실제 결과만 기록해라.
- 문서를 갱신해라. 순서가 있다: ..\프로젝트_상세.md(**기본 문서** — 먼저 갱신)
  → python tools/render_docs.py → README.md(그 포트폴리오 축약형, 최신 회귀 1건)
  → NEXT_WORK.md, NEXT_TASK.md, automation_scope.json, traceability.json,
  지식/[자동화 구현 현황]. 상세와 HTML 은 auto/ 안에 만들지 마라.
- git status/diff/remote 검토 후 관련 파일만 commit 하고 git push origin main.
  Force Push·history 재작성 금지. config.json, Reports/, Evidence/, Log/, Cache/,
  Temp/, work/ 는 커밋하지 마라.
- 테스트하지 않은 것을 성공했다고 기록하지 마라.
```
