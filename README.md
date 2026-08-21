# Bellalun Viewer 기본기능 QA 자동화

의료영상 진단 소프트웨어(디지털 유방촬영 Viewer)의 **QA 체크리스트를 실제 UI로
자동 수행하고 Pass/Fail을 스스로 판정하는** 테스트 자동화 프레임워크입니다.

사람이 손으로 하루씩 돌리던 회귀 시험을, **명령 한 줄로 수행하고 근거까지 남기는**
자동화로 만들었습니다. 최신 전수 회귀는 111.3분이 걸렸습니다.

```bash
python run.py run-regression
```

---

## 1. 한눈에 보기

| 항목 | 내용 |
|---|---|
| 대상 | Bellalun Viewer 1.0.12 (Windows 데스크톱 의료영상 SW) |
| 기준 문서 | `Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` (시트 `개정 TC`) |
| 규모 | Python **19,702줄**(core 10,980 / tests 8,130 / `run.py` 592), 모듈 56개(core 31 / tests 24 / `run.py`) — 2026-08-21 `python tools_report_numbers.py Reports/Result_20260821_164016.json` 실측 |
| 시험 범위 | 개정본 체크리스트 **36개 TC** 전수 등록 — 완전자동 20 / 부분자동 6 / 수동 10 (+ 자동화 보조 4, 그중 2건은 회귀 제외) |
| 최신 전체 회귀 | 2026-08-21 16:40 — TC 26건 : PASS 20 / FAIL 1 / MANUAL 5 / SKIP 0 (111.3분) |
| 그 안의 검증 항목 | 검증 251개 : PASS 241 / FAIL 1 / MANUAL 7 / SKIP 2 |
| 남은 FAIL | `TC_XIPL_compatibility_03` Step 9 |
| 외부 의존성 | Pillow, pytesseract, openpyxl, pypdf **4개뿐** (§4 참고) |
| 자체 정적 검사 | `tools_check_module_attrs.py` — 모듈 속성 오염과 없는 이름 참조를 훑습니다(§6에서 실제로 잡힌 버그) / `tools_check_regression_names.py` — 회귀 블록이 쓰는 이름이 그 블록 안에서 묶였는지 |
| 수치 실측 도구 | `tools_report_numbers.py` — 문서에 적을 코드 규모·자동화 등급 건수·회귀 판정·소요 시간을 리포트 JSON 과 저장소에서 다시 계산해 출력합니다 |

### 이 자동화가 실제로 하는 일

명령을 넣으면 사람의 개입 없이 아래를 **순서대로 전부** 수행합니다.

```
DB를 기준 스냅샷으로 복원 → 시험 파라미터 재생성
  → Viewer 실행·로그인 → DICOM 서버 3종 등록 + C-ECHO 연결 확인
  → MWL 처방 조회·검사 생성 → 2D/3D 촬영(Demo) → Tool 적용 검증
  → Image/Print Overlay 설정 + 영상·Film 창 표시 OCR 대조
  → 2D/3D/All Images/Emergency DICOM Send + 수신 객체 식별 Tag 대조
  → DICOM Print 실제 출력 + 출력물 웹 프리뷰 OCR 대조
  → Export(Normal/Anonymous), Reject·Restore, 계정·권한, Setting Export/Import
  → XIPL 연동 6종(영상처리 파라미터 왕복 검증)
  → 리포트 4종(HTML·CSV·JSON·TXT) + 체크리스트 xlsx 결과 기록
```

---

## 2. 왜 만들었나 — 해결한 문제

이 제품의 QA에는 자동화를 어렵게 만드는 조건이 겹쳐 있었습니다.

| 문제 | 이 프로젝트의 해결 |
|---|---|
| 버튼 대부분이 **커스텀 렌더링**(`AfxWnd140u`)이라 표준 UI 자동화 도구가 인식 못 함 | `ctypes`로 Win32를 직접 다루고, 물리 마우스·키보드를 제어 |
| 화면 값이 **텍스트가 아니라 그림**으로 그려져 읽을 수 없음 | 좌표를 계산해 크롭 → Tesseract OCR, 다중 psm 다수결로 오독 방지 |
| "버튼 눌렀다"만으로는 기능 동작을 증명할 수 없음 | DB·제품 로그·생성 파일·UI 재진입값을 **교차 검증** |
| 시험마다 데이터가 쌓여 결과가 달라짐 | DB 기준 스냅샷 복원 + 시험 픽스처 자동 정리로 **반복 가능**하게 |
| 실제 X-ray 노출은 자동으로 쏠 수 없음 | Demo 모드(F8 가상 촬영)로 대체하고, **안전 게이트**로 실촬영을 차단 |

---

## 3. 아키텍처

### 3.1 파일명 ↔ TC 번호 맵핑

**`tests/workflowNN.py` 의 NN 이 체크리스트 TC 번호입니다.** 파일명만 보고 어느 TC
인지 알 수 있어야 하므로 1:1로 맞췄습니다.

| 파일 | 담당 TC | 내용 |
|---|---|---|
| `tests/workflow01.py` | `WF_01` | MWL 조회 + Local 검사 생성 |
| `tests/workflow02.py` | `WF_02` | 2D/3D 촬영 + Tool 적용 |
| `tests/workflow03.py` | `WF_03` | Image Overlay(Bottom) / Print Overlay(Header·Top·Bottom) 설정 + 영상·Film 창 표시 확인 |
| `tests/workflow04.py` | `WF_04` | 2D 수동 DICOM Send |
| `tests/workflow05.py` | `WF_05` | 3D 수동 DICOM Send |
| `tests/workflow06.py` | `WF_06` | All Images 및 Dose SR 전송 |
| `tests/workflow08.py` | `WF_08` | 2D/3D Film Print (영역별 출력물 대조) |
| `tests/workflow07.py` | `WF_07` | Emergency 검사 Auto Send |
| `tests/workflow09.py` | `WF_09` | Normal 및 Anonymous Export |
| `tests/workflow10.py` | `WF_10` | MWL Hospital Code와 Procedure 매핑 |
| `tests/workflow11.py` | `WF_11` | Image Reject 및 Restore |
| `tests/workflow12.py` | `WF_12` | Study Reject 및 Restore |
| `tests/workflow13.py` | `WF_13` | 계정 추가·수정 및 로그인 (권한 표 56개 항목 대조) |
| `tests/workflow14.py` | `WF_14` | Setting Export 및 Import (.vms 구성 + 설정 전수 복원 대조) |
| `tests/workflow15.py` | `WF_15` | Pre-send Preview 표시 및 전송 |
| `tests/workflow16.py` | `WF_16` | **사용자 지정 수동** — 제품을 조작하는 자동화 코드 없이 MANUAL 판정만 기록 |
| `tests/xipl_flows.py` | `XIPL_01~06` | XIPL 연동 6종 (한 흐름을 공유하므로 묶음) |
| `tests/install.py` | `Install_01/02/07/08/09` | 설치·환경 점검 |
| `tests/system_compat.py` | (보조) `AUTOMATION_3D_ACQUISITION_3DN/_3DW` | 3D-Narrow / 3D-Wide 촬영. 개정본 TC 가 아니며 **회귀에서 제외**(`run-sys3d` 단독) |

이 정리 전에는 **`tests/workflow03.py` 가 `WF_08`(Film Print)을 담고 있었습니다.**
이름이 정면으로 오해를 부르는 상태였고, `send_flows.py` 한 파일에 `WF_04`/`05`/`06`
세 TC가 섞여 있었습니다. 옮기면서 TC가 아니라 인프라에 해당하는 부분(Queue·수신
객체·식별 Tag 대조)은 `core/send_verify.py` 로 내렸습니다.

**미연결 모듈 정리 경과**: `tests/dataflow.py` 는 `WF_11`/`WF_12` 구현 때 판정부로
연결했습니다. `WF_14` 는 2026-08-21 에 `tests/workflow14.py` 로 드라이버와 판정을
함께 구현했습니다. `WF_16` 은 이후 사용자 지시로 전체 수동으로 바뀌어
`tests/workflow16.py` 에 MANUAL 판정만 남겼습니다. `tests/settings.py` 의 과거
pre/post 판정부는 실제 실행 경로가 아닙니다.

```
run.py                     CLI 진입점 · 환경 게이트(해상도/DPI/권한) · 리포트 생성
│
├── tests/                 TC별 시나리오와 Pass/Fail 판정 (위 맵핑표)
│
└── core/                  재사용 계층 (제품 조작 · 증거 수집)
    ├── ui.py              Win32 컨트롤 열거 · 물리 입력 · 화면 캡처
    ├── uitext.py          커스텀 렌더 컨트롤의 화면 텍스트 OCR · 문구로 항목 선택
    ├── image_overlay.py   영상 위 Image Overlay 크롭·OCR·항목 판정 (WF_03 / WF_15 공용)
    ├── flows.py           화면 전환 시나리오 (로그인·Setting·검사) + 컨트롤 맵
    ├── viewer_processing.py  영상처리 파라미터 UI + OCR 판독
    ├── viewer_tools.py    Tool(W/L·Zoom·Pan·Annotation) 적용 검증
    ├── xipl.py            XIPL Studio 제어 (WPF UI Automation)
    ├── print_overlay.py   Print Overlay 설정 + 출력물 영역별 대조
    ├── send_verify.py     DICOM Send 공용 판정 (Queue·수신 객체·식별 Tag)
    ├── export_manager.py  Export Manager 제어 (별도 프로세스)
    ├── specs.py           사양서 PDF 검색 (SRS 번호 인용)
    ├── setting_transfer.py Setting Export/Import 구동 (.vms 구성 검사)
    ├── setting_values.py  Setting 56개 페이지의 컨트롤 값 판독 · 항목 단위 대조
    ├── tc_modules.py      TC ID -> 구현 파일 지도 (리포트가 코드 위치를 보여준다)
    ├── snapshot.py        DB 전 구간 스냅샷 · 섹션 diff
    ├── db.py              DB 조회 (**조회 전용 — 아래 설계 원칙 참고**)
    ├── dbreset.py         기준 스냅샷 백업/복원
    ├── result.py          판정 누적 · 리포트 4종 생성
    └── checklist.py       체크리스트 xlsx에 결과 기록
```

### 3.2 지켜낸 설계 원칙

이 프로젝트에서 **의도적으로 지킨 규칙**들이며, 대부분 실패를 겪고 나서 규칙으로
승격시킨 것입니다.

**① DB는 조회 전용 — 상태 변경은 반드시 UI로**
`core/db.py`에는 `SELECT`만 있고 저장소 전체에 `INSERT`/`UPDATE`/`DELETE`가
**한 줄도 없습니다.** DB를 직접 고치면 "제품 UI가 그 동작을 실제로 했다"는 판정
근거가 무너지기 때문입니다. 시험 데이터 정리도 UI 버튼으로 합니다.

**② 판정 기준은 화면이 아니라 매뉴얼·사양서에서 가져온다**
TC를 새로 만들 때도, 기존 TC를 고도화할 때도 **먼저 근거 문서를 읽고** 시작합니다 —
체크리스트 원문(Step/Expected Result), Operation Manual(사용자 절차와 기대 동작),
Service Manual(Setting 항목의 의미와 선행조건), DICOM Conformance Statement(SOP
Class·Transfer Syntax), 제품 사양서.

TC 모듈 상단에 **체크리스트 원문과 인용한 문서·절 번호**를 적어 두는 것을 규칙으로
했습니다(`AGENTS.md` 2항). 판정 기준이 어디서 나왔는지 코드만 보고 추적할 수 있게
하는 장치입니다. 현재 `workflow01` / `workflow03` / `workflow04` / `workflow05` /
`workflow06` / `workflow08` / `workflow13` / `system_compat`에 적용돼 있고, 나머지
모듈은 개별 판정의 `note`에 근거를 남기는 방식이라 **상단 정리는 아직 진행 중**입니다.

화면을 보고 기준을 역산하면 **결함을 정상으로 인증해 버립니다.** 실제로 겪은 두 건:
Window Level은 매뉴얼이 *"W1/W2 값의 증가·감소"* 로 정의하는데 초기 구현은 "화면
픽셀이 몇 % 바뀌었나"라는 대리 지표를 써서 **정상 동작을 FAIL로 뒤집었고**, Q.C
파라미터는 형식을 확인하지 않고 만든 **깨진 파일이 콤보에 보인다는 이유로 PASS처럼
보였습니다.**

**③ 조작 전·후 모두 "상태"를 확인한다**
클릭만 보내고 결과를 확인하지 않는 코드는 단독 실행에서는 통과하고 **회귀에서만**
깨집니다. 그런 결함 5건(메뉴 토글, 콤보 스크롤, 저장 팝업, 카드 배치, 툴바 펼침)이
모두 같은 형태였습니다.

여섯 번째는 **거울상**이었습니다 — 조작 *후* 확인을 빠뜨린 게 아니라, 조작 *전*에
그 화면이 존재하는지 확인하지 않았습니다(§6 참고). 그래서 규칙을 양방향으로
바꿨습니다: **조작 전에 대상이 그려졌는지 기다리고, 조작 후에 의도한 상태가 됐는지
확인한다.**

**④ 환경 오염을 제품 결함처럼 보고하지 않는다**
이전 실행이 남긴 데이터 때문에 수행 불가한 경우는 `FAIL`이 아니라 무엇을 정리해야
하는지 알려주는 `MANUAL`로 분리합니다. QA 리포트의 신뢰도를 지키는 규칙입니다.

**⑤ 고정 sleep 금지 — 상태 기반 대기**
컨트롤 출현·팝업·로그 기록·파일 생성 등 **실제 증거**가 나타날 때까지 상한을 두고
polling합니다. 모든 대기에는 타임아웃이 있어 무한 대기가 없습니다. 현재 저장소에
**5초 이상의 고정 sleep은 0건**입니다.

---

## 4. 기술 선택과 이유

**외부 의존성을 4개로 억제** (`requirements.txt`: Pillow, pytesseract, openpyxl,
pypdf)

| 필요 기능 | 흔한 선택 | 이 프로젝트의 선택 | 이유 |
|---|---|---|---|
| Win32 UI 제어 | pywin32 | **`ctypes`** 직접 호출 | 설치 부담 제거, QA PC 이식성 |
| SQL Server 접근 | pyodbc | **PowerShell + .NET `SqlClient`** | Windows 기본 제공, 드라이버 설치 불필요 |
| DICOM 파싱 | pydicom | **자체 `dicomlite.py`** | 필요한 태그만 읽으면 충분 |
| 사양서 PDF 읽기 | PyMuPDF, pdfplumber | **`pypdf`** | MIT 라이선스, 순수 Python이라 빌드 도구 불필요 |

`pypdf`는 나중에 추가했습니다. 사양서가 `.pdf`라 grep이 되지 않아 **판정 근거를
코드에서 인용할 수 없었기** 때문입니다. `core/specs.py`가 사양서에서 문구를 찾아
**쪽 번호와 SRS ID까지** 돌려주고, 그 값을 판정의 `note`에 적습니다. 라이선스와
빌드 부담을 함께 본 결과 `pypdf`를 골랐습니다 — PyMuPDF는 AGPL/상용 이중
라이선스라 의료기기 QA 저장소에 넣기 부담스럽고, pdfplumber는 의존성이 더 깊습니다.

덕분에 새 QA PC에서 `pip install -r requirements.txt` 한 번으로 준비가 끝납니다.
`portability-check`가 **네 패키지의 설치 여부를 시작 시점에 점검**하고, 빠졌으면
설치 명령까지 알려줍니다.

**판정에 쓰는 증거 5종** — 하나에만 의존하지 않습니다.

1. **DB 조회** — 검사·영상 구조, UID 유일성, 설정 저장값
2. **제품 로그** — 적용된 파라미터명·수치 (타임스탬프로 시점 필터링)
3. **생성 파일** — 영상 파일, ImageAction 산출물, 해시·크기
4. **UI 재진입** — 저장 후 화면을 다시 열어 표시값 재확인
5. **화면 캡처 + OCR** — 커스텀 렌더링 값 판독, 증적 이미지 보존

---

## 5. 사용법

### 5.1 준비

```bash
python -m pip install -r requirements.txt
copy config.example.json config.json    # 계정·경로·서버 주소 입력
python run.py portability-check          # 해상도·DPI·권한·필수 경로 사전 점검
```

**필수 조건** (충족하지 않으면 자동화가 시작 시점에 명확히 FAIL시킵니다)

- **관리자 권한** — `VIEWER.exe`가 `requireAdministrator`라 항상 High Integrity로
  실행됩니다. 자동화가 일반 권한이면 Windows UIPI가 입력 주입을 막는데, 이때
  **화면 캡처는 되고 클릭만 조용히 실패**해 엉뚱한 증상으로 보입니다.
- **1920×1080 @ 100%(96 DPI)** — 좌표 기반 조작이 있어 시작 시 검사합니다.
- Tesseract-OCR, SQL Server 인스턴스, XIPL Studio (경로는 `config.json`)

### 5.2 실행

```bash
python run.py list                # 개정본 36개 TC + 보조 4개의 자동화 수준
python run.py run-regression      # 전체 회귀 (기준 복원부터 리포트까지)
```

개별 실행:

| 명령 | 내용 |
|---|---|
| `run.py setup-dicom` | MWL/Storage/Print 등록 + C-ECHO + DB/TCP 검증 |
| `run.py run-wf01` | WF_01 MWL 및 Local 검사 생성 |
| `run.py run-wf02` | WF_02 공통 2D/3D 촬영 및 Tool 적용 |
| `run.py run-wf03` | WF_03 Image Overlay 및 Print Overlay 설정 |
| `run.py run-wf04` | WF_04 2D 수동 DICOM Send (Selected Images) |
| `run.py run-wf05` | WF_05 3D 수동 DICOM Send |
| `run.py run-wf06` | WF_06 All Images 및 Dose SR 전송 |
| `run.py run-wf08` | WF_08 2D/3D Film Print (실제 출력물 대조) |
| `run.py run-wf09` | WF_09 Normal 및 Anonymous Export |
| `run.py run-wf07` | WF_07 Emergency 검사 Auto Send |
| `run.py run-wf10` | WF_10 MWL Hospital Code와 Procedure 매핑 |
| `run.py run-wf11` | WF_11 Image Reject 및 Restore |
| `run.py run-wf12` | WF_12 Study Reject 및 Restore |
| `run.py run-wf13` | WF_13 계정 추가·수정 및 로그인 (권한 표 56개 항목 대조) |
| `run.py run-wf14` | WF_14 Setting Export 및 Import (.vms 구성 + 설정 전수 복원) |
| `run.py run-wf15` | WF_15 Pre-send Preview 표시 및 전송 |
| `run.py run-wf16` | WF_16 사용자 지정 수동 판정 기록 (제품 UI 조작 없음) |
| `run.py run-xipl` | XIPL 연동 6종 (`-01`~`-06`로 개별 실행) |
| `run.py run-sys3d` | 보조: 3D-Narrow / 3D-Wide 촬영 검증 |
| `run.py list` | 개정본 36개 TC의 자동화 수준과 사유 |
| `run.py snapshot-baseline` | 현재 DB를 기준 스냅샷으로 저장 |
| `run.py reset-environment` | 기준 스냅샷으로 되돌리기 |

### 5.3 결과물

| 위치 | 내용 |
|---|---|
| `Reports/Result_<시각>.html` | **상세 리포트** — 아래 구성 |
| `Reports/Result_<시각>.json` | 기계 판독용 전체 판정·근거 |
| `Reports/Result_<시각>.csv` | 스프레드시트로 열어 볼 판정 표 |
| `Reports/Result_<시각>.txt` | 터미널에서 바로 읽는 요약 |
| `Reports/Checklist_Result_<시각>.xlsx` | 원본 TC 행 옆에 판정 열을 덧붙인 사본(원본은 수정하지 않음) |
| `Evidence/` | 단계별 화면 캡처 (실패 시 원인 추적용) |

HTML 리포트에 들어가는 것 (2026-08-21 확장)

- **요약 대시보드** — TC/검증 항목 집계 타일, PASS/FAIL/MANUAL/SKIP 비율 막대,
  실행 구간과 총 소요 시간
- **실행 환경 및 버전** — 수행 일시·호스트·실행 계정·**PC 제조사/모델·CPU(코어/
  스레드)·메모리·GPU·BIOS·OS Caption/Version/Build/Arch·OS 설치일·최근 부팅**·
  Python·해상도/DPI·관리자 권한·Viewer 파일 버전·Tesseract 버전·data_dir·
  SQL Server·기준 체크리스트 경로. 존재하는 경로는 **클릭하면 열린다**
  (Viewer 제품 로그와 증적 폴더 포함).
  PC/OS 정보를 **여기에** 싣는 이유: 지원 OS Build 기준이 문서상 확정되지 않아
  `Install_02` 의 확인 항목으로 두면 그 TC 가 영구히 MANUAL 로 남는데, 정작 필요한
  것은 "어떤 PC 에서 돌렸는가" 라는 기록이기 때문입니다(`core/sysinfo.pc_info`).
- **자동화 커버리지 총괄** — 기준 체크리스트 **36 TC 전부**를 분류해, 자동화하지
  못한 것의 **정확한 지점과 해제 조건**을 함께 싣습니다. 분류는
  자동 판정 / 부분 자동 / 미구현(구현 가능) / 실물 장비·촬영 환경 필요 /
  OS 신규 설치 환경 필요 / 파괴적 작업 / 판정 기준·문서 정보 미확정 /
  사용자 지정 수동. 사유는 리포트가 만들지 않고 `automation_scope.json` 의 각 TC
  `coverage` 항목에서 읽습니다 — 근거 없는 설명을 생성하지 않기 위해서입니다.
- **실패 항목 원인** — 앞선 FAIL 부터 읽도록 위에 모아 둔다(회귀의 연쇄 실패를
  제품 결함으로 오독하지 않기 위해)
- **수동 확인 / 미수행 사유와 해제 조건** — MANUAL/SKIP 을 **TC 단위로 한 행**씩
  모아 "무엇이 있으면 자동 판정할 수 있는가"를 적습니다(같은 사유가 여러 Step 에
  반복되면 접습니다). Step 단위로 펼치면 행이 수십 개가 되어 "어느 TC 가 왜 막혔나"가
  묻혔습니다.
- TC 별로: **기준 문서 원문**(Precondition / Step Description / Expected Result /
  Test Data)과 자동화 범위 사유, **자동화 코드 위치**, 시작·종료 시각과 소요 시간,
  단계별 기대값/실제값/판정 근거, 증적 파일 링크, **소요 시간 분해**(스텝별 + 스텝
  외 전제 준비 시간)

**단계별 판정 표의 열 폭**은 `table-layout:fixed` + `colgroup` 으로 고정해
**기대값과 실제값을 정확히 같은 폭**(각 27%)으로 만들고 판정 열을 46px 로 줄였습니다.
브라우저가 내용 길이로 폭을 재조정하면 긴 `actual` 이 기대값 열을 잡아먹어 두 값을
나란히 대조할 수 없기 때문입니다(1500px 폭 실측: 기대값 388px = 실제값 388px).

`python tools_report_numbers.py` 는 리포트 JSON 과 저장소에서 **문서에 적을 수치를
실측**해 출력합니다(코드 규모, 자동화 등급 건수, 커버리지 분류, TC/검증 판정, 소요
시간, FAIL 목록). 문서의 숫자를 손으로 옮겨 적다 낡는 것을 막기 위한 도구입니다.

리포트에는 판정만이 아니라 **무엇과 무엇을 대조했는지**가 함께 남습니다.

```
[PASS] Step 6 변경된 세부 설정이 대상 영상에 적용
  values: {'Contrast': 15, 'Sharpness': 10, 'Brightness': 10,
           'Tone type': 20, 'Noise reduction': 8}
  applied_log: {'parameter': 'TEST_XIPL_SAVED_M.pim', ...}
  note: Apply 후 Image Processing에 재진입하여 UI 표시값을 다시 읽어 비교
```

---

### 5.4 TC 를 새로 추가하는 법

이 저장소는 **파일명이 담당 TC 를 드러내는** 규칙을 씁니다(§3.1). 새 TC 를 붙일 때
순서는 다음과 같습니다.

1. **기준 문서에서 원문을 읽습니다.**
   `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx`(시트 `개정 TC`)에서 그 TC 행의
   Precondition / Step Description / Expected Result / Test Data 를 **그대로** 확인합니다.
   **TC ID 만 보고 Step 을 추측하면 안 됩니다** — `지식` 폴더의 다른 체크리스트는
   같은 ID 에 다른 내용이 붙어 있습니다(§6 참고).
2. **매뉴얼·사양서에서 기대 동작의 근거를 찾습니다.**
   `core/specs.py` 로 사양서 PDF 를 검색하면 쪽 번호와 SRS ID 가 함께 나옵니다.
   화면에서 보이는 동작으로 합격 기준을 역산하면 **결함을 정상으로 인증합니다.**
3. **`tests/workflowNN.py`** 를 만듭니다(`NN` = 체크리스트 TC 번호). 파일 최상단
   docstring 에 체크리스트 원문을 **변경 없이** 옮겨 적고, 판정 근거와 실측한 컨트롤
   ID 를 함께 적습니다.
4. **`run(ctx) -> TCResult`** 를 구현합니다. 각 Expected 한 줄이 하나의 Check 입니다.

   ```python
   r = TCResult("TC_Basic_WorkFlow_NN", "제목")
   r.assert_equal(3, "확인 항목", expected, actual, note="근거: 사양서1 60쪽 SRS ...")
   r.attach(screenshot_path)          # 증적
   r.manual(5, "항목", "사유 + **해제 조건** + **이 실행으로 말할 수 없는 것**")
   ```

   - **단순 클릭 성공을 PASS 로 쓰지 않습니다.** DB / 로그 / 수신 파일 / UI 재진입 중
     최소 하나로 교차 확인합니다.
   - **조작 후 확인 없는 코드를 넣지 않습니다.** 클릭을 보냈으면 의도한 상태가 됐는지
     확인하는 코드를 같이 넣습니다. 없으면 단독 실행은 통과하고 회귀에서만 깨집니다.
   - **`finally` 에서 상태를 되돌립니다.** 되돌리지 못하면 그 사실을 판정으로 남깁니다.
5. **`core/tc_modules.py`** 에 TC ID → 파일 목록을 등록합니다(리포트가 코드 위치를
   보여주는 근거).
6. **`automation_scope.json`** 에 등급(FULL/PARTIAL/MANUAL)과 **사유**를 적습니다.
   등급은 **실측으로 확인된 뒤에만** 올립니다.
7. **`run.py`** 에 `run-wfNN` 서브커맨드를 추가하고, 회귀에 포함할 것이면
   **회귀 블록 안에서** import 합니다(다른 분기의 import 는
   `UnboundLocalError` 를 만듭니다 — §6).
8. **검사를 돌립니다.**

   ```bash
   python -m py_compile tests/workflowNN.py
   python tools_check_module_attrs.py        # 모듈 속성 오염·없는 이름 참조
   python tools_check_regression_names.py    # 회귀 블록 이름 결속 (긴 실행 전 필수)
   ```
9. **회귀 시작 상태에서 검증합니다.** `ensure_*` 계열 헬퍼는 조건이 이미 충족되면
   건너뛰므로, 단독 실행 통과가 그 분기 검증을 뜻하지 않습니다.

   ```bash
   python run.py reset-environment    # 기준 스냅샷 복원
   python run.py run-wfNN
   ```
10. **문서를 갱신합니다** — 이 README(§3.1 맵핑표, §5.2 명령표, §9 등급 목록),
    `NEXT_TASK.md`, `..\지식\[자동화 구현 현황] ...md`.

### 5.5 문제 해결

| 증상 | 먼저 볼 것 |
|---|---|
| **클릭이 조용히 안 먹는다** (캡처는 되는데 창이 반응 없음) | **관리자 권한**. `python -c "import sys;sys.path.insert(0,'.');from core import sysinfo;print(sysinfo.is_elevated())"` 가 `False` 면 Windows UIPI 가 입력을 막고 있습니다. 코드보다 권한을 먼저 확인하십시오 |
| 좌표가 어긋난다 | `python run.py portability-check` — 1920x1080 @ 100%(96 DPI) 가 아니면 시작 시점에 FAIL 시킵니다 |
| OCR 이 "못 읽는다" | **캡처 이미지를 먼저 보십시오.** 타이밍/경합을 의심하기 전에. `Evidence/` 에 크롭 원본이 남습니다. 과거 두 번 모두 원인은 타이밍이 아니라 전처리(psm 선택, 명암 방향)였습니다 |
| 회귀가 첫 단계에서 무너진다 | 제품 서비스가 내려가 있을 수 있습니다. `AUTOMATION_ENVIRONMENT_RESET` 판정의 `services` 값을 보십시오 |
| 앞선 TC 실패 뒤 FAIL 이 줄줄이 | **가장 앞선 FAIL 부터** 읽으십시오. 리포트가 위에 모아 둡니다. "전제 미충족(fixture 없음 / 서버 미등록)" 문구가 보이면 제품 판정이 아닙니다 |
| "수신 객체가 정확히 N건" 이 틀린다 | 활성 Storage SCP 가 둘 이상일 수 있습니다. 리포트의 `[전제] 활성 Storage SCP 가 하나` 판정을 보고, `reset-environment` 후 `setup-dicom` 을 1회만 실행하십시오 |
| 검사 Preset·Hospital Code 가 남아 반복 실행이 막힌다 | `python run.py reset-environment` 로 DB 를 기준 스냅샷으로 되돌립니다 |
| 프로세스가 남았다 | 부록의 정리 명령 |
| `UnboundLocalError: ... run_xxx` | 같은 이름의 import 가 다른 분기에 있습니다. `python tools_check_regression_names.py` |
| 수동 WF_16 뒤 Kiosk 가 켜진 채로 남았다 | Viewer > Setting > System > Security 에서 KIOSK mode 를 Not use 로 바꾸고 Update 합니다. 자동화는 Kiosk 설정을 조작하지 않습니다 |

### 5.6 현재 제한사항

- **환경 고정**: Primary 1920x1080 @ 100%(96 DPI), 관리자 권한, Windows.
  다른 해상도/배율은 시작 시점에 거부합니다(조용히 오작동하지 않기 위해).
- **Demo(F8) 가상 촬영 환경**: 실제 X-ray 가 아니므로 **RDSR(Dose SR)이 생성되지
  않습니다.** `WF_06` Step 3~5, `WF_07` Step 6, `WF_15` Step 6 은 전제 미충족으로
  MANUAL 이고, **제품 결함으로 보고하지 않습니다.**
- **GPU 미탑재**: `XIPL_03` Step 10 은 Viewer 가 `No GPUS` 를 반환해 SKIP 됩니다.
  GPU 와 무관하게 성립해야 하는 판정(Apply 후 파라미터 유지)은 면제하지 않습니다.
- **실물 장비 없음**: Detector/Gantry, ACR Phantom, VIVIX-M Setup,
  Bellalun System Setup 이 없어 `Install_03~06`, `QC_01/02` 는 수동입니다.
- **판정 기준이 문서에 없는 것**: `Performance_01~03` 은 체크리스트 Test Data 가
  *"허용 기준: 추가 사양 확인 필요"* 라고 명시합니다. 기준 없이 측정값만 찍어
  PASS 라고 쓰지 않습니다.
- **파괴적 동작 제외**: 설치/Upgrade/Uninstall 실행, 시스템 재시작, PC 종료는
  자동화하지 않습니다(자동화 세션이 함께 죽고 무인 회귀가 중단됩니다).
  `WF_16`(Kiosk 및 System Launcher)은 Step 이 대부분 이 부류라 2026-08-21 부터
  **TC 전체를 수동**으로 둡니다(사용자 지정).
- **DICOM 전용 네트워크 어댑터가 없는 환경**: `Install_02` Step 4 는 검증 환경서가
  어댑터 별칭을 지정하지 않으면 **SKIP** 입니다(MANUAL 이 아닙니다 — 확인 대상이
  없다는 뜻). 실제 DICOM 통신 경로는 `DICOM_Server_Setup` 의 TCP 연결·C-ECHO 판정이
  매 회귀마다 실측으로 확인합니다.
- **Overlay 표시 판정은 "값"이 아니라 "항목"**: Demo 촬영에서는 선량 값이
  `-- kVp` 로 찍히므로 `WF_03` Step 5 는 **라벨 표시**로 판정합니다. 개정본
  Expected 5 가 요구하는 것도 "설정한 Image Overlay **항목**이 표시된다" 입니다.
  값 쪽은 환자 ID·생년월일을 DB 와 대조하는 교차 확인으로 따로 남깁니다.
- **`core/db.py` 는 조회 전용**입니다. 정리용으로도 DB 쓰기를 열지 않습니다 —
  모든 상태 변경은 UI 로 해서 증거 모델을 지킵니다.
- **마우스/키보드를 점유합니다**(부록 참고).

---

## 6. 실제로 잡아낸 결함

자동화의 가치는 **사람이 놓치는 것을 잡는 것**입니다.

### 제품 결함 (현재도 FAIL로 보고 중)

**`TC_XIPL_compatibility_03` Step 9** — 3D Post Reconstruction에서 파라미터 10개를
바꾸고 Apply한 뒤 재진입하면 **값이 전부 기본값으로 되돌아갑니다.**

```
기대: Background Masking 'Not use', Contrast 14, Sharpness 16 ...
실제: Background Masking 'Use',     Contrast 10, Sharpness 20 ...
```

GPU 유무와 무관한 결함이라, 이 판정은 **의도적으로 완화하지 않고** FAIL로 유지합니다.

### 사양 대조로 확인한 불일치 (제품 담당자 확인 대상)

**Storage Transfer Syntax가 Conformance Statement 선언 범위 밖입니다.**

DICOM Conformance Statement V1.3W1의 "Proposed Presentation Context Table"은 네트워크
Storage SCU가 제안하는 Transfer Syntax를 **Implicit VR LE / Explicit VR LE 두 가지로만**
선언합니다(영상·DBT·RDSR 전부). JPEG은 같은 문서에서 **DVD-RAM/USB 매체 저장
프로파일에만** 나오고, 네트워크용 JPEG UID(`1.2.840.10008.1.2.4.*`)는 문서 전체에
한 번도 선언돼 있지 않습니다.

그런데 제품 `Setting > DICOM > Storage`에서는 JPEG2000을 선택할 수 있고, 그 상태로
Send하면 conformant SCP가 거절합니다. 실제 SCP 로그로 확정했습니다.

```
Associate Request  (Implementation Class UID 1.3.6.1.4.1.19179.5)
  Abstract Syntax: 1.2.840.10008.5.1.4.1.1.1.2   Digital Mammography X-Ray Image Storage
  Transfer Syntax: 1.2.840.10008.1.2.4.90        JPEG 2000 Lossless
Associate Accept
  Presentation Context ID: 1 - Rejected
```

자동화는 전송 전에 **선언된 값으로 되돌립니다.** 테스트 SCP에 맞춘 우회가 아니라
사양 준수 상태를 만드는 것이므로, 이 조치는 그대로 유지합니다. 문서 누락인지 UI가
선언 범위 밖 값을 노출하는 것인지는 제품 담당자 확인이 필요해 `NEXT_TASK.md`에
기록만 남겼습니다.

### 기준 문서를 잘못 골라 정상 구현을 결함으로 판정한 일

**자동화가 아니라 제가 틀린 사례입니다.** `지식` 폴더의 다른 체크리스트
(`(TC) R-23-2346_...xlsx`)를 기준으로 착각해, 정상 구현된 `WorkFlow_02`(공통 2D/3D
촬영 및 Tool 적용)를 "체크리스트 원문은 Barcode/QR인데 구현이 다르다"며 등급을
`MANUAL`로 내렸습니다.

두 문서는 **같은 형태의 TC ID를 쓰지만 번호 매핑이 다릅니다.** 사용자가 바로잡아 준
뒤 확인해 보니 어긋난 것은 WF02 하나가 아니었습니다.

| 개정본 | 내용 | 코드가 쓰던 옛 번호 |
|---|---|---|
| `WF_03` | Image Overlay 및 Print Overlay 설정 | `WF_04` |
| `WF_04` | 2D 수동 DICOM Send | `WF_05` |
| `WF_08` | 2D/3D Film Print | `WF_03` |
| `WF_09` | Normal 및 Anonymous Export | `WF_10` |
| `WF_11/12` | Image / Study Reject 및 Restore | `WF_12/13` |
| `WF_16` | Kiosk 및 System Launcher | `WF_18` |

**판정 결과는 TC ID로 체크리스트 행에 기록됩니다.** 번호가 어긋나면 검증하지 않은
항목에 PASS가 찍힙니다. 그래서 `automation_scope.json`을 개정본에서 **직접 생성**하고,
모듈의 TC ID·`run.py` 명령·회귀 실행 순서를 전부 개정본 번호로 재정렬했습니다.
개정본에 없는 항목(3D-N/3D-W 촬영)은 TC 번호를 붙이지 않고 `AUTOMATION_*` 보조
항목으로 분리했습니다.

**얻은 규칙**: 기준 문서는 하나로 못박고, 그것을 `AGENTS.md` **0절**에 파일명과 시트명
까지 적는다. 비슷한 이름의 문서가 여러 개 있을 때 "관련 문서를 참고한다"는 지침은
아무것도 막아주지 못한다.

### 아이콘 모양으로 기능을 추정해 네 번 틀린 일

이 저장소에서 **같은 실수를 네 번** 했습니다. 커스텀 렌더링 UI라 컨트롤이 텍스트를
돌려주지 않아서, 아이콘 모양으로 기능을 추정해 기록한 것이 원인입니다.

| 컨트롤 | 제가 추정한 것 | 실제 (툴팁·클릭으로 확정) |
|---|---|---|
| `2184` | Send | **Import Study** |
| `2196` | 검사 내 검색 (목록+돋보기 아이콘) | **Pre-send Preview** |
| `2207` | Procedure 삭제 (휴지통) | **Left Implant** |
| `2186` | 휴지통(삭제) — "절대 누르지 말 것" | **Reject Study** (Rejected 검사 선택 시 `Restore Study`로 토글) |

마지막 사례가 특히 위험했습니다. `2186`을 "삭제 버튼"으로 알고 피하고 있었는데
실제로는 WF_12가 써야 하는 버튼이었습니다. 반대로 진짜 파괴적인 버튼을 안전하다고
기록했을 수도 있었습니다.

**대응**: `core/ui.py`에 `hover()`를 만들어 **누르기 전에 툴팁을 읽습니다.** 파괴적일
수 있는 아이콘은 클릭 대신 커서만 올려 확인합니다. `right_click()`과
`double_click()`도 함께 추가했는데, `double_click()`은 별도 이유가 있습니다 — `click()`
을 두 번 부르면 `settle` 때문에 간격이 400~900ms로 벌어져 **Windows가 더블클릭으로
인식하지 않습니다**(임계값 500ms). Hospital Code의 Code 셀이 "편집 불가"로 보였던
것이 이 때문이었습니다.

**같은 ID가 화면마다 다른 뜻인 경우도 있습니다.** 2026-08-21에 Film 창을 닫으려다
확인했습니다 — `501`/`500`은 Print 범위 선택에서 `Selected`/`Cancel`이지만, Film
종료 확인 대화상자에서는 **`Yes`/`No`** 입니다. ID로 골랐다면 정반대를 눌렀을
것입니다. 그래서 `uitext.pick_button()`을 만들어 **버튼 문구를 OCR로 읽어 후보가
하나일 때만** 누릅니다. 이 대화상자는 분홍 배경+흰 글자(Yes)와 흰 배경+분홍
글자(No)를 나란히 써서 `autocontrast` 하나로는 `ee` / `(me)`로 읽혔고, 반전과
임계값 이진화를 함께 시도해야 `Yes` / `No`가 읽혔습니다.

### 저장 시점을 가정해 사용자 DB를 오염시킨 일

**자동화가 아니라 제가 낸 사고입니다.** `Setting > Procedure > Hospital Code`의 `+`
버튼이 **Update 없이도 DB에 즉시 행을 만든다**는 것을 모른 채 프로브를 다섯 번
돌려, 사용자 DB에 `Code`~`Code_4` 5행을 남겼습니다. 프로브 주석에는 이렇게 적어
두었습니다 — **확인하지 않고 단정한 것입니다.**

> Update를 누르지 않으므로 DB에는 아무 변화가 없다.

Print Overlay와 Account는 Update까지 눌러야 저장되고, Hospital Code의 `+`는 즉시
저장되며, 같은 화면의 **셀 편집은 다시 Update가 필요합니다.** 화면마다, 조작마다
다릅니다.

정리마저 한 번 실패했습니다. `ui.click(row)`는 행 **중앙**을 누르는데 이 목록은 행
중앙 x가 정확히 톱니바퀴 버튼 위치였습니다. 행을 선택하려던 클릭이 대화상자를 열고,
그 위에 뜬 `"Please select item to add."` 팝업이 이후 삭제 클릭을 **전부 삼켰습니다.**
12번 반복해도 한 행도 지워지지 않은 이유입니다. 좌측 셀을 누르도록 고쳐 5행 전부
지웠고, 픽스처·Reject 상태·계정이 모두 정상임을 확인했습니다.

**얻은 규칙** (`AGENTS.md` 3항, 지식 운영 지침 10-1-2·10-1-3절):
"관찰만 한다"는 프로브도 앞뒤로 DB를 찍어 대조한다. 목록 행을 **선택**할 때는 눌러도
안전한 셀의 좌표를 rect에서 계산해 누른다. 되돌리기 어려운 조작 앞에서는 떠 있는
대화상자를 먼저 정리한다 — 모달 하나가 남으면 이후 클릭이 전부 무효가 되고, 그
증상은 "버튼이 동작하지 않는다"로 보여 원인을 엉뚱한 곳에서 찾게 됩니다.

### 미표시를 제품 문제로 의심하다 설정에서 원인을 찾은 일

`Print Overlay`를 `Header / Top / Bottom` 세 영역에 나눠 넣도록 고도화한 뒤,
**Header 항목만 필름에 나오지 않았습니다.** DB까지 확인해도 항목은 정상이었습니다.

```
PRINT_OVERLAY_ITEM   Position=2(Header)  FieldID=1(Patient ID), 15(Birth Date)   저장됨
필름 OCR             'LCC'                                                       Header 없음
```

원인은 같은 화면 우측 Option의 **`Header Layout` 표시 위치가 `None`** 이었습니다.
사양서1 **297쪽**이 이미 적어 둔 정상 동작입니다.

> Header가 표시될 수 있는 위치는 다음과 같다. **None으로 설정한 경우 표시되지
> 않는다.** None, Top, Bottom

**제품 결함이 아니었고, 자동화가 설정을 덜 한 것이었습니다.** 사용자가 설정 화면을
보고 먼저 찾아냈고, 저는 그 시점까지 항목 저장만 확인하고 있었습니다.

고친 내용은 사양에서 그대로 끌어왔습니다.

| 사양 근거 | 자동화가 하는 일 |
|---|---|
| 297쪽 "None으로 설정한 경우 표시되지 않는다" | `HeaderPosition`을 `Top`으로 설정하고 DB로 확인 |
| 297쪽 "**Layout 한 칸당 한 항목씩 표시한다**" | Header 항목 수(2개)를 담을 **최소 칸수**를 계산해 `1 X 2` 선택 |
| 296쪽 "Header 영역 = 전체 필름 높이의 3% × Layout 행수" | 필름 OCR의 Header 밴드 높이를 **상수 대신 이 공식으로** 계산 |
| 297쪽 "영상별로 값이 다를 수 있는 항목은 Header에 삽입할 수 없다" | Patient ID/Birth Date만 Header, Thickness·압박력·HVL·AGD는 Top/Bottom |

**콤보 항목 순서를 믿지 않게 된 계기이기도 합니다.** 표시 위치 콤보의 두 번째
항목을 눌렀더니 `HeaderPosition`이 `Top`(1)이 아니라 `Bottom`(2)이 됐습니다. 그래서
순서로 고르지 않고 **항목 문구를 OCR로 읽어** 원하는 것을 고르고, 저장 후 DB 값으로
확인합니다. 못 찾으면 아무것도 누르지 않고 읽은 문구를 붙여 실패시킵니다 — 엉뚱한
항목을 고르면 설정이 조용히 틀어집니다.

**판정도 함께 고쳤습니다.** 그전에는 필름 우상단 한 곳만 크롭해 전체 텍스트를 훑었기
때문에, 6개가 **전부 Top에 몰려 있어도 통과**했습니다. 영역을 나눈 의미가 판정에
없었던 것입니다. 이제 영역별로 크롭해 그 영역에서 값이 읽히는지 따로 판정하고,
크롭 이미지를 영역별 증적으로 남깁니다.

```
Header  (0,   0, 723,  27)   'DATA_FLOW_MWL_01 1980/01/01'   <- 라벨 없이 값만, 1 X 2 두 칸
Top     (578, 72, 723, 117)  '0.0 cm' / '35 N'               <- 라벨 없이 값만
Bottom  (361,840, 723, 904)  'HVL: Not valid' / 'AGD: Not valid'
```

Top 값은 필름에서 **7px 높이**로 렌더링돼 기존 배율로는 아예 읽히지 않았습니다.
배율 하나에 의존하면 판정이 흔들려서(8배에서 `MWL`이 `MIWL`로 읽힘) **배율 12·8·5로
읽고 하나라도 기대값과 일치하면 통과**로 봅니다. 기대값이 DB에서 온 환자 ID·생년월일
이라 이 방식이 판정을 느슨하게 만들지 않고, 판독본 전부를 리포트에 남겨 감사할 수
있게 했습니다. 같은 비율이 Film 창(723×904)과 Print 서버 웹 프리뷰(1280×1600)
양쪽에서 통합니다.

**얻은 규칙**: 설정한 값이 화면에 안 보이면 **항목이 아니라 "표시 스위치"를 먼저
본다.** 제품을 의심하기 전에 설정 화면을 캡처해 눈으로 본다.

### 세 번 만에 잡은 것 — 회귀에서만 실패하던 TC

`TC_XIPL_compatibility_04`가 회귀 8·10·11차에서 **3회 연속** 같은 지점에서 멈췄습니다.
단독 실행은 통과했습니다.

```
New Patient 탭 컨트롤(ID 2285)을 20초 동안 찾지 못했습니다.
현재 화면 랜드마크=['status_bar', 'examine']
```

**두 번 잘못 짚었습니다.**

1. "대기가 부족하다" → 상한을 8초에서 20초로 올렸습니다. 같은 실패였습니다.
2. "검사가 열려 있어 Patient 화면에 닿을 수 없다" → 열린 검사를 보류하는 복구 코드를
   넣었습니다. 그런데 같은 상태를 직접 만들어 **그 분기를 끄고 비교하니 없어도 정상
   동작**했습니다. 근거 없는 상태 변경 코드였으므로 제거했습니다.

세 번째 추측을 하는 대신 **증적을 강화했습니다.** 컨트롤 탐색 실패 시 화면 랜드마크와
함께 **열린 대화상자 문구와 전체 화면 캡처**를 남기게 했습니다. 다음 회귀에서 캡처가
답을 줬습니다.

> **There are changes. Do you like to save them?**  `[Yes]` `[No]`

`Close`를 누르면 제품이 이 팝업을 띄우는데 아무도 답하지 않아 **모달이 이후 모든
클릭을 삼켰습니다.** `close_examine`은 종료 옵션 팝업(Close/Suspend/Cancel, 버튼 3개)만
알고 있어서, 버튼이 3개 미만이면 그냥 반환했습니다. 이 팝업은 Yes/No 2개입니다.

회귀에서만 터진 이유는 직전 `XIPL_03`이 Post Reconstruction 파라미터를 변경해
"변경사항"이 생기기 때문입니다. 단독 실행에는 변경이 없어 팝업이 뜨지 않습니다.

**첫 수정도 발동하지 않았습니다.** 이 팝업은 `WM_GETTEXT`로 문구를 읽을 수 없습니다
(`dialog.text`, `dialog_text` 모두 빈 문자열 — 실측). 문구 검사가 항상 실패해
핸들러가 건너뛰었습니다. **OCR로 문구를 읽도록** 바꿔 해결했습니다.

**왜 문구 확인을 포기할 수 없었나** — 같은 상황에서 뜨는 다른 팝업과 버튼 구성이
같습니다.

| 팝업 | 좌측 `501` | 우측 `500` |
|---|---|---|
| There are changes. Do you like to save them? | Yes (저장) | No (버림) |
| This study will be deleted. Are you sure? | **Yes (검사 삭제)** | Cancel |

문구를 모른 채 좌측을 누르면 **검사가 삭제됩니다.** 그래서 OCR로 문구를 확인하고,
삭제 확인 팝업이면 손대지 않고, **문구를 확정하지 못하면 클릭하지 않고 중단**합니다.

결과: `XIPL_04` **PASS**(3회 연속 FAIL → PASS), 회귀 `PASS 124 → 140`.

**얻은 규칙**: 추정으로 방어 코드를 넣었다면 **그 분기가 실제로 필요했는지 끄고/켜고
비교해 확인한다.** 그리고 실패 메시지에는 "무엇을 못 찾았는가"와 함께 **"지금 무엇이
보이는가"**(랜드마크·대화상자 문구·캡처)를 남긴다 — 이 한 줄이 세 번째 추측을
막았습니다.

### 선행 도구의 오탐을 원인 쪽에서 없앤 것 (`WorkFlow_14`)

사내에 같은 목적의 선행 도구가 이미 있었습니다(Setting 화면 캡처-비교 프로그램).
`pyautogui` 절대좌표에
**Calibration**(사람이 Setting 창 좌상단/우하단과 각 탭 좌표를 지정해 json 저장)을
붙여 각 Setting 페이지를 캡처하고, Export/Import 전후 **이미지끼리** 비교해 CSV 통계와
`COMPOSITE_*` 차이 이미지를 남깁니다.

그 도구의 문서가 **스스로 한계를 적어 두었습니다.**

> "텍스트 커서가 캡처가 되면 같은 Setting 값을 가지고 있지만 Fail 로 인식"
> "Setting 창 로딩이 늦어진 Fail composite Image"
> "같은 PC/모니터 및 동일한 Calibration 이 수행된 이미지 데이터와 비교해야 정상 동작"

세 줄 모두 **픽셀을 값의 대리물로 쓴 결과**입니다. 그래서 증상을 완화하는 대신 원인을
없앴습니다.

| | 선행 도구 | 이 저장소 (`core/setting_values.py`) |
|---|---|---|
| 좌표 | 절대좌표 + 사람이 하는 Calibration | **컨트롤 ID**(Setting 9그룹 56페이지 실측 맵). 캡처 영역도 콘텐츠 패널 컨트롤의 rect 에서 계산 |
| 대기 | 고정 대기 | 보이는 컨트롤 수가 연속 2회 같아질 때까지 |
| 비교 대상 | 페이지 스크린샷 | **컨트롤별 값** — `Edit`/콤보는 `WM_GETTEXT`, 라디오/체크박스는 패널 1회 캡처의 픽셀 |
| 텍스트 커서 오탐 | 발생 | 값을 읽으므로 **원리적으로 발생하지 않음** |
| 결정적 근거 | 없음(이미지가 유일) | **DB 설정 테이블 전수 대조**(`snapshot.config_identical`, 38개 섹션) |

값을 직접 읽을 수 있는지 먼저 실측으로 확인했습니다. 커스텀 MFC 컨트롤이라
`BM_GETCHECK`/`BM_GETSTATE` 는 **라디오 8개 전부 0** 을 돌려주지만, `WM_GETTEXT` 는
`Edit` 을 정확히(`2240` → `'10'`), 콤보를 앞 8자로 **결정적으로**(`2241` →
`'Allow on'`, `2227` → `'Pure Whi'`) 돌려줍니다. 비교에는 그것으로 충분합니다.

첫 실행에서 FAIL 2건이 나왔고 **둘 다 제품이 아니라 자동화 결함**이었습니다.

1. `REGISTRATION_COMMON.LastAccNum`(마지막 발급 Accession Number, 진행 카운터)이
   설정 전수 대조에 섞여 있었습니다. 게다가 이 테이블은 `Key` 컬럼이 없어
   `snapshot._key_of` 가 행 전체를 JSON 으로 키를 만들었고, 그래서 **필드 하나가
   바뀌어도 "1행 삭제 + 1행 추가"** 로 보여 `VOLATILE_FIELDS` 예외가 적용되지
   않았습니다. 식별 컬럼이 없으면 행 순서로 짝짓도록 고치고 카운터를 제외했습니다.
2. `patient.general` 의 컨트롤 `2303` 이 회차 사이에 x 595 → **594**(1px) 움직여
   "한쪽에만 있음" 두 건으로 잡혔습니다. 같은 컨트롤 ID + 8px 이내 최근접으로
   짝짓게 하고, **허용 오차를 넘는 이동은 그대로 보고**합니다.

그리고 사양이 요구한 동작이 실제로 관측됐습니다. Import 직후 제품이
**"Please restart to apply the change. If you don't restart, the setting change may
be ignored."** 를 띄우고, 재시작 전까지 값이 그대로 유지되다가 재시작 후에
Export 시점 값으로 돌아왔습니다(`StorageWarning` 12 → 13 → 재시작 후 12).
사양서1 60절의 *"Import 한 설정은 Viewer를 재시작해야 적용된다"* 와 일치합니다.

### 사양서를 코드에서 인용할 수 있게 만든 것

체크리스트가 스스로 미확정을 표시한 항목이 있었습니다 — `WorkFlow_05`의 Test Data에
*"3D 대상: Recon 영상만 전송 여부는 검증 버전 사양 추가 확인 필요"*.

사양서는 `.pdf`라 grep이 되지 않아 근거를 대기 어려웠습니다. `pypdf`(MIT, 순수
Python)를 의존성에 추가하고 **`core/specs.py`** 를 만들어 해결했습니다.

```python
specs.search(ctx, "익명")
# [{'source': '사양서1', 'page': 134, 'srs': [...], 'text': '... Unknown으로 표시 ...'}]
```

사양서에는 요구사항마다 `SRS 01-10-10` 형태의 ID가 붙어 있어, 절 번호보다 정확하게
인용할 수 있습니다. 이걸로 **두 가지 답을 찾았습니다.**

**① 3D 전송 대상** — 사양서1 125쪽(SRS 06-30-30 문맥):

> "3D 영상은 Recon 영상이 전송된다. Recon 영상이 없을 경우 영상은 전송되지 않는다."

DICOM Conformance Statement가 For Processing(Raw)을 선언하지 않는 것과, 실측
(DB에 4건인데 2D·Recon 2건만 수신)이 모두 일치했습니다.

**② 익명화 기대값 — 제가 틀렸던 것을 정정했습니다.** 처음엔 "익명화 방식이 사양에
명시돼 있지 않다"고 보고 *"원본과 다르다"* 로만 판정했습니다. 사양서1 134쪽에
명문으로 있었습니다.

> "익명 처리되는 환자 정보: Patient ID, Patient Name, Accession Number, Other
> Patient ID, Other Patient Name, Birth Date, Age"
> "Anonymous 체크 시, **Patient ID 및 Patient Name은 Unknown으로 표시**"

판정을 `Unknown` 정확 대조로 바꾸고 132쪽의 경로 규칙까지 확인하게 했습니다.
실측 결과가 사양서와 완전히 일치했습니다 — `patient_ids: ['Unknown']`,
폴더 `Unknown_Unknown` / `Anonymous_48`.

**얻은 것**: 느슨한 판정("원본과 다르다")을 유지했다면 이 정확성을 확인할 수
없었습니다. 근거 문서를 읽을 수 있게 만드는 것 자체가 검증 강도를 올립니다.

### 예외처리를 넣다가 정상 실행을 막은 일 (회귀 2회 붕괴)

사용자가 *"로그인 화면이 다른 창에 가려져 로그인을 못 할 수 있으니 예외처리해 달라"*
고 요청했습니다. 비밀번호는 물리 키 입력이라 포커스가 다른 창에 있으면 키가 그쪽으로
들어가고, 화면 캡처는 되니 원인을 알기 어렵습니다 — 타당한 요청입니다.

그런데 **이 PC에서는 가림을 재현할 수 없었습니다.** 탐색기·메모장을 강제로 전면에
올려도 Viewer가 전면을 유지했습니다. 그 상태에서 *"전면화 실패 시 중단"* 로직을
넣었고, 회귀가 두 번 무너졌습니다(`PASS 160 → 30`).

| 회차 | 실패 메시지 | 원인 |
|---|---|---|
| 13차 | `name 'os' is not defined` | `os.path.join`을 쓰면서 `import os` 누락. **컴파일은 통과** |
| 14차 | `가리고 있는 창: 'Program Manager'` | `Program Manager`는 **Windows 데스크톱 셸**. 기동 직후 최전면이 데스크톱인 정상 순간에 발동 |

**무엇을 잘못 설계했나** — 목적은 "가려져서 실패했을 때 **원인을 알 수 있게**"였는데
"가려졌으면 **아예 중단**"으로 만들었습니다. 정상 실행을 막는 쪽이 훨씬 나쁩니다.

**재설계**: 셸 창은 가림으로 보지 않고, 전면화는 **시도하고 결과만 로그에 남기고
진행**합니다. 로그인이 최종 실패했을 때 그 시점의 최전면 창 정보를 오류에 실어
"가려져서 실패했는지"를 알 수 있게 합니다.

**규칙으로 승격한 것**

- **재현할 수 없는 상황에는 '중단'이 아니라 '진단'을 넣는다.** 실패 분기를 실측하지
  못했다면 그것이 정상 실행을 막을 수 있다고 가정한다.
- **컴파일은 import 누락을 잡지 못한다.** 바꾼 모듈은 실제로 import 해 호출해 보거나
  `ast`로 정의되지 않은 전역 이름을 훑는다.
- "무엇이 비정상인가"를 판단할 때 **OS/셸의 정상 상태를 목록으로 배제한다.**

한 가지는 잘 작동했습니다. 앞서 만든 리포트 상단 **`[먼저 볼 것] 가장 앞선 FAIL`이
두 번 모두 제 실수를 즉시 지목**했습니다. 14건의 FAIL 중 무엇을 먼저 봐야 하는지
헤매지 않았습니다.

### 자동화 자체의 함정 (수정 완료)

| 증상 | 실제 원인 |
|---|---|
| 슬라이더 값이 빈 문자열로 읽힘 | Tesseract `psm 7`이 **한 자리 숫자를 버림** (`8` → `''`). 다중 psm 다수결로 해결 |
| F8 촬영이 엉뚱한 스텝을 찍고도 성공 처리 | 스크롤 밖으로 잘린 카드를 클릭 — Win32가 여전히 `visible`로 보고 |
| 화면이 안 넘어감 | 저장 성공 팝업을 닫지 않아 **모달이 이후 클릭을 전부 삼킴** |
| 회귀에서만 XIPL 4건 붕괴 | 비밀번호 물리 입력 시 문자 유실 → 제한된 재시도로 해결 |
| Q.C 파라미터가 무효 | `.xtp`를 복사해 `.eap`로 이름만 바꿈 — **포맷이 다른 파일**(평문 XML vs 암호화 바이너리)임을 헤더 실측으로 확인 |
| DICOM Send가 수신 0건 | 전송 전에 Transfer Syntax를 보장하지 않음. DB를 기준 복원하면 제품 기본값(JPEG 2000 Lossless)으로 돌아가고 **conformant SCP가 Presentation Context를 거절** — SCP 로그의 `1 - Rejected`로 확정 |
| Send 범위 대화상자가 안 뜸 | 검사를 연 상태에서 Setting을 드나들어 **영상 선택이 풀림**(Send 버튼 비활성). 설정을 검사 열기 **전에** 하도록 순서 변경 |
| 체크리스트 결과가 8일간 미생성 | 기록 함수가 **어디서도 호출되지 않는 죽은 코드**였고, 설정 경로마저 다른 PC 것이었음. 두 겹의 문제가 서로를 가림 |
| New Patient 탭을 못 찾음 | 저장 확인 팝업을 방치해 **모달이 클릭을 전부 삼킴**. `dialog_text`가 빈 문자열이라 OCR로 문구를 읽어 구분 |
| Send 수신 개수가 항상 1건 | 대기 루프가 **첫 UID에서 즉시 break** — 개수가 안정될 때까지 기다리도록 수정. 이게 없으면 Selected(1개)와 All(전체)의 차이를 검증할 수 없음 |
| W1/W2 값 불일치로 FAIL | OCR이 `24380`을 `243380`으로 오독(`3` 중복). 양쪽 모두 화면 OCR이라 **불일치 시 재판독**하고 시도 기록을 남김 |

마지막 사례에서는 **오진을 두 번 거쳤습니다.** 처음엔 타이밍을 의심해 대기 상한을
늘렸지만 같은 실패였고, 다음엔 "검사가 열려 Patient 화면에 닿을 수 없다"고 추정해
검사를 보류하는 복구 코드를 넣었습니다. 그런데 조건을 직접 만들어 그 분기를 끄고
비교하니 **없어도 정상 동작**했습니다. 근거 없는 상태 변경 코드였으므로 제거하고,
실제로 필요한 한 줄만 남겼습니다. 이 경험을 규칙으로 승격했습니다 — *추정으로 넣은
방어 코드는 그 분기가 실제로 필요했는지 끄고/켜고 비교해 확인한다.*

특히 마지막 사례는 **자동화가 "통과한 것처럼 보이던" 위험**이었습니다. 잘못된 파일도
콤보 목록에 표시되어 선택됐기 때문에, 매뉴얼 원문과 파일 헤더를 실측해 바로잡았습니다.

### 첫 진단이 틀렸고, 측정이 그것을 잡아낸 것 (2026-08-21)

이 저장소에서 **가장 값진 종류의 사례**입니다. 그럴듯한 원인을 찾아 고쳤는데도
증상이 남아 있었고, 그 사실이 진짜 원인을 가리켰습니다.

**증상**: 전체 회귀에서 `WorkFlow_04`(2D Send) 이후 `CONFIGURATION.DICOM_STORAGE` 에
같은 서버(`BUNNY_TEST`)가 새 `Key` 로 늘어나고 둘 다 `Use=1` 이 됐습니다
(Key 17 → 18 → 20). "활성 Storage SCP 가 하나" 전제가 FAIL 해
`WorkFlow_05/06` 이 전제에서 멈추고 `WorkFlow_15` 는 아예 중단됐습니다.

**첫 진단 — 그럴듯했지만 틀렸습니다.** Transfer Syntax 콤보 항목을 고르는 코드가
팝업 rect 기준 **절대 좌표** `(가운데, top + 17)` 을 누르고 있었습니다. 빗나가면
팝업 뒤의 `+`(2431) 추가 버튼을 눌러 새 서버 행이 만들어질 수 있는 구조이고,
`AGENTS.md` 5절을 정면으로 어긴 한 줄이었으니 원인으로 지목하기 딱 좋았습니다.
그 코드를 OCR 문구 선택으로 바꾸고, `setup-dicom` 단계에서 Transfer Syntax 를 미리
확정하게 해서 뒤따르는 TC 가 Setting 을 열지 않도록 만들었습니다.

**그런데 연쇄를 다시 돌리니 `WorkFlow_04` 는 Setting 을 아예 열지 않았는데도
(`changed=False`) Key 18 이 또 생겼습니다.** 추정이 틀렸다는 증거입니다.

**측정으로 확정한 진짜 원인** — 세 가지 독립 근거

| # | 확인한 것 | 결과 |
|---|---|---|
| 1 | 두 행의 **전체 컬럼** 비교 | `SCPUseType` 만 다르다 (Key 17=`0`, Key 18=`1`). 나머지 18개 컬럼은 동일 |
| 2 | `DATA.DICOM_STORAGE_QUEUE` 의 전송 작업 행 | `OriginalStorageKey=17` / `StorageKey=18` — 제품이 전송을 큐에 넣을 때 **그 시점의 Storage 설정을 작업용 사본 행으로 복제**하고 원본을 가리킨다 |
| 3 | Setting 각 페이지 목록 | `Storage` 는 `SCPUseType=0` 행 1개만 표시. `Storage Group` / `Storage Commitment` / `Query·Retrieve` / `MPPS` 는 전부 0행 — 사본은 **어느 설정 화면에도 없다** |

즉 **제품 결함도 아니고 자동화 상태 누수도 아니었습니다.** 사용자가 나중에 서버
설정을 바꿔도 진행 중인 전송 작업이 자기 설정을 유지하도록 제품이 사본을 남기는
정상 동작입니다. 결함은 그 사본까지 "설정된 활성 Storage SCP" 로 세던
**판정 쿼리**였습니다 — `WHERE [Use]=1` 만 걸고 `SCPUseType` 을 보지 않은 것.

**진짜 원인을 가리킨 것은 자동 복구가 스스로 멈춘 메시지였습니다.**

```
UI 목록 1행과 DB 2행이 달라 행을 짝지을 수 없습니다. 자동 복구를 하지 않습니다.
```

Setting 화면에는 1행뿐인데 DB 에는 2행이라는 뜻이고, 그것이 "둘은 같은 종류가
아니다"를 말해 주었습니다. **애매하면 아무것도 하지 않게** 만들어 둔 것이 오진을
막았습니다 — 강제로 맞추는 복구였다면 설정 행을 지웠을 것입니다.

**고친 것**

1. 판정 쿼리를 `SCPUseType = 0` 으로 좁혔습니다(`ds.STORAGE_SCP_USE_TYPE`).
   `active_storage_rows` / `_stored_transfer_syntax` / `repair_storage_use` /
   `setup-dicom` 의 두 판정 / `WorkFlow_06`·`07` 의 `SendDoseSR` 전제까지 전부.
2. 사본 행은 **관측으로 남깁니다**(`ds.storage_job_copies` → 판정
   `actual.job_copies`). 근거를 남기지 않으면 다음 사람이 같은 오진을 반복합니다.
3. 설정 행이 그래도 여럿이면 **UI(Use 체크박스)로 하나만 남기고 DB 로 다시 확인**
   합니다. `core/db.py` 의 조회 전용 원칙은 그대로입니다 — DB 에 쓰지 않습니다.
   복구 내용은 `actual.repair` 에 남고, 복구까지 실패하면 FAIL 입니다.
4. 첫 진단에서 고친 두 가지는 **원인과 무관하지만 유지**합니다 — 절대 좌표 제거는
   `AGENTS.md` 5절 준수이고, `setup-dicom` 단계 확정은 위험한 UI 조작 횟수를
   줄입니다. 다만 **그것이 중복을 고쳤다고 적지 않습니다.**

**전제는 "드러내기"만으로 부족했습니다.** 이전 구현은 어긋난 상태를 FAIL 로 표시
하는 것까지만 했고, 그 결과 세 TC 가 **정작 검증해야 할 전송 판정을 하나도 수행하지
못했습니다.** 이 항목은 시험 대상이 아니라 전제(setup)이므로 "맞춰 놓고 그것을
확인"하는 것이 맞습니다. 복구 실패는 여전히 FAIL 입니다.

**규칙으로 승격한 것**: 판정 쿼리를 쓸 때 **그 테이블에 다른 용도의 행이 섞여 있는지
먼저 확인합니다.** 전체 컬럼을 뽑아 비교하면 구분 컬럼이 드러납니다. 그리고 열거값
전체를 문서로 확인하지 못했으면 **확인한 것만 적습니다** — 여기서는 `0` 의 의미만
세 근거로 확정했고 `1` 은 큐 행의 참조 관계로 관찰한 것이라고 주석에 명시했습니다.

### 새 Step 을 붙이고 **다음 TC** 를 깨뜨린 것 (2026-08-21)

`WorkFlow_03` Step 6 을 자동화하면서 Film 창을 열고 Overlay 를 OCR 한 뒤
**창을 닫지 않고** TC 를 끝냈습니다. 근거는 "다음 TC 가 `cold_start(force_restart=
True)` 로 Viewer 를 다시 띄우므로 남은 창은 사라진다" 였고, `WorkFlow_08` 도 실제로
Film 창을 열어 둔 채 끝냅니다.

**그 전제가 `WorkFlow_04` 에는 성립하지 않았습니다.** `WorkFlow_04` 는
`flows.cold_start(ctx.cfg, ctx.db)` — **`force_restart` 없이** 기존 Viewer 를
재사용합니다. 그래서 `ensure_patient_screen` 이 실패하고
(`landmarks=['status_bar','examine']`) 전제 단계에서 FAIL 했습니다.
**단독 실행에서는 드러나지 않고 연쇄에서만 깨지는 형태**입니다(§3.2의 4번 원칙).

고친 방법은 "닫기 버튼을 눌러 본다"가 아니라 **실측**이었습니다.

1. Film 창(`158 CWndFilmManager`)의 **자식에는 닫기 버튼이 없었습니다**
   (`166`/`167`/`162`/`203`/`201`만). 전체 화면을 캡처해 보고서야 Close 가
   다이얼로그 하단 우측의 별도 `TextButton` 이라는 것을 알았습니다.
2. 후보 두 개를 OCR 로 읽어 확정했습니다 — `1149`=`Print`, `1105`=`Close`.
   **ID 만 믿고 눌렀다면 실제 출력을 보낼 수 있었습니다.**
3. Close 를 누르면 확인 대화상자 `"Are you sure you want to close?"` 가 뜨고
   `Yes`=501 / `No`=500 입니다. 이 ID 는 **Print 범위 선택의
   `Selected`=501 / `Cancel`=500 과 같습니다** — 위치나 ID 로 골랐다면 정반대를
   누를 수 있었습니다.
4. 그 Yes/No 는 분홍 배경+흰 글자와 흰 배경+분홍 글자여서 `autocontrast` 하나로는
   `ee` / `(me)` 로 읽혔습니다. 반전·임계값 이진화 × psm 11/8/7/6 을 모두 시도해
   `Yes` / `No` 를 읽고, **후보가 하나일 때만** 누릅니다
   (`uitext.button_reads` / `uitext.pick_button`).
5. 마지막으로 정리 결과를 **판정으로** 남깁니다 — "Film 창 종료 후 Patient 화면
   복귀". 조작하고 확인하지 않으면 같은 실수가 반복됩니다.

### 가장 값진 사례: FAIL 10건의 원인이 1개였던 회귀

`PASS 121 → PASS 30`. 리포트만 보면 제품이 열 군데 깨진 것처럼 보였지만,
**전부 첫 FAIL 하나의 결과**였습니다. (이후 `PASS 121 → 124`로 회복했습니다.)

```
DB 복원(제품 프로세스 전체 종료) → Viewer 재기동 → 로그인 성공
  → 화면이 그려지기 전에 네비게이션 시작 → 상태바 못 찾고 15초 뒤 중단
  → DICOM 등록 실패 → MWL 서버 미등록
  → 이후 8개 TC가 "전제 미충족"으로 연쇄 FAIL
```

실제 기동 소요는 **약 36초**였습니다. 대기 예산이 부족한 게 아니라 **기다리지
않았던 것**입니다. 조작 후 확인을 빠뜨리는 기존 결함들의 **거울상** — 조작 *전에*
대상이 존재하는지 확인하지 않은 경우였습니다.

**오진하기 가장 쉬운 지점**: 같은 실행에서 뒤쪽 TC 두 건은 PASS했습니다. 그래서
"환경은 정상, 특정 TC만 문제"로 보입니다. 실제로는 그때쯤 Viewer가 이미 떠 있어
재사용됐을 뿐이었습니다.

여기서 얻은 것을 도구에 반영했습니다.

- 리포트 최상단에 **`[ 먼저 볼 것 ] 가장 앞선 FAIL`** 을 표시해 읽는 순서를 강제
- 기동 실패 시 **기동 로그와 마지막 화면 스크린샷**을 남김(이번엔 예외 문구만
  남아 추적이 어려웠습니다)
- 함께 드러난 뒷정리 결함도 수정: DB 복원이 `Bellalun Service`를 강제 종료하고
  **되살리지 않아** 회귀 종료 후에도 서비스가 내려가 있었습니다. 이제 SCM으로
  중지하고 복구까지 확인한 뒤, 그 상태를 리포트 판정으로 남깁니다.

---

## 7. AI(Claude Code)를 활용한 개발 방식

이 프로젝트는 **Claude Code를 페어 프로그래머로 사용해** 구조화했습니다. 단순히
"코드를 받아썼다"가 아니라, **AI가 잘 작동하는 작업 환경을 설계한 것**이 핵심입니다.

### 7.1 AI가 매 세션 같은 품질로 일하도록 만든 장치

세션이 끊기거나 다른 PC/계정으로 옮겨도 맥락이 유실되지 않게, 지식을 **문서 계층**으로
분리했습니다.

| 문서 | 역할 | 수명 |
|---|---|---|
| `AGENTS.md` | 작업 시작·검증·커밋 규칙 | 영구 |
| `..\지식\[자동화 운영 지침]` | 회차와 무관한 **규칙·설계 결정** (0절: 어떤 문서를 근거로 삼는가) | 영구 |
| `..\지식\[자동화 구현 현황]` | TC별 구현 수준 | 영구 |
| `NEXT_TASK.md` | 다음 우선순위와 미결정 사항 | 회차 |
| `인수인계_<날짜>.md` | 그 세션의 결과·근거·남은 일 | 회차 |

운영 지침에는 **실패에서 얻은 교훈을 규칙으로 승격**해 적어둡니다. 예를 들어
"OCR이 빈 값이면 타이밍을 의심하기 전에 **캡처 이미지를 눈으로 볼 것**"이라는 규칙은,
AI가 같은 오진(경합 조건으로 추정 → 불필요한 서브프로세스 우회책 작성)을 반복하지
않게 만든 실제 방지 장치입니다.

### 7.2 AI 결과물을 그대로 믿지 않는 검증 습관

AI 협업에서 가장 위험한 것은 **그럴듯하지만 틀린 진단**입니다. 이 프로젝트에서
실제로 겪고 대응한 사례:

- **오진 정정**: 인수인계에 "같은 프로세스에서는 실패, 새 프로세스에서는 성공하는
  캡처 경합"이라 기록돼 있었지만, 캡처를 저장해 눈으로 확인하니 값은 항상 선명했고
  원인은 OCR 모드였습니다. → 잘못된 우회책을 제거했습니다.
- **검증 경로 확인**: 단독 실행 통과를 근거로 "검증 완료"라 보고했으나, 해당 함수가
  *조건이 이미 충족되면 건너뛰는* 구조여서 **고친 분기를 타지 않았습니다.**
  이후 "회귀와 동일한 시작 상태를 만들어놓고 검증"을 규칙화했습니다.
- **근거 없는 상향 금지**: 한 TC를 근거 없이 `FULL`로 올린 것을 스스로 되돌리고,
  실측 PASS를 확인한 뒤에 다시 올렸습니다.
- **문서의 주장도 검증 대상**: "각 TC 모듈 최상단에 근거를 적어 두었다"고 쓴 직후
  실제로 세어 보니 5개 모듈뿐이어서 **문구를 사실에 맞게 내렸습니다.** 같은 방식으로
  코드 규모·회귀 실적·자동화 등급 건수를 전부 실측과 대조했고, 낡은 수치를
  고쳤습니다(README에 남아 있던 이전 회차 실적, 2026-08-14에 멈춘 구현 현황 문서).
- **"기능이 있다"는 서술도 실행으로 확인**: 리포트가 체크리스트 xlsx에 결과를
  기록한다고 문서에 적혀 있었지만, 호출부를 찾아보니 **아무도 부르지 않는 죽은
  코드**였습니다. 문서를 고치는 대신 기능을 되살렸습니다.

### 7.3 사람이 판단해야 하는 지점은 반드시 물어보고 설계

제품 도메인 지식이 필요한 결정은 AI가 추측하지 않도록 **질문 → 확인 → 설계** 순서를
지켰습니다. 실제로 이 방식으로 확정한 것들:

- Q.C 3D 파라미터가 `.eap`이어야 하는 이유 (매뉴얼 명칭 + 파일 헤더로 교차 확인)
- 시험 파라미터 `.pim` 파일명이 `_M`으로 끝나야 하는 제품 규칙
- **"Q.C 테스트는 열린 검사를 닫아야 실행된다"** — 도메인 지식이라 코드만 봐서는
  알 수 없었고, 이 한 가지로 막혀 있던 TC가 통과했습니다
- 빈 검사 삭제 확인 팝업을 자동으로 승인해도 되는지 (파괴적 동작이므로 사전 승인)

파일명 규칙 같은 것은 **주석으로만 적지 않고 코드가 스스로 검사**하게 만들었습니다.
`.pim` 상수가 `_M`으로 끝나지 않으면 import 시점에 실패합니다.

### 7.4 규칙은 문서에 적는 것으로 끝나지 않는다

"매뉴얼·사양서를 근거로 삼는다"는 규칙을 `AGENTS.md`에 **실행 가능한 절차**로
구체화하고(어느 문서에서 무엇을 확인하고, 판정의 `note`에 문서·절 번호를 남긴다),
곧바로 기존 코드가 그 규칙을 지키는지 점검했습니다. 결과가 §6에 있는 발견들입니다 —
**규칙을 적기만 했다면 아무것도 찾지 못했을 것입니다.**

부수 효과로 grep이 되지 않던 DICOM Conformance Statement(`.docx`)를 텍스트로
추출해 두었습니다. 그래야 다음 사람도 같은 대조를 할 수 있습니다.

---

## 8. 이식성 — 다른 QA PC에서 그대로 동작하게

QA PC마다 환경이 달라 자동화가 깨지는 일이 잦습니다. 이 프로젝트에서 해결한 것들:

- **드라이브 문자 차이** — `BellalunData`가 C:/D: 어디에 있어도 모든 드라이브를
  탐색해 찾습니다.
- **DB 기준 스냅샷 이식** — 세 가지 문제를 순차로 해결했습니다.
  ① 스냅샷 폴더를 저장소 위치 기준 상대경로로 탐색 (절대경로 하드코딩 제거)
  ② SQL Server가 **자기 서비스 계정으로** `.bak`을 열기 때문에 사용자 폴더를 못 읽음
     → 읽을 수 있는 위치로 복사 후 복원
  ③ `.bak`에 **백업 뜬 PC의 물리 경로가 박혀 있어** 드라이브가 다르면 실패
     → `sys.master_files`를 읽어 `WITH MOVE`를 동적 생성
- **체크리스트 원본 경로** — `config.json`에 **다른 PC 사용자의 Downloads 경로**가
  박혀 있어 이 PC에서는 파일이 없었고, 결과 기록이 **조용히 빠졌습니다**(마지막
  생성이 8일 전). DB 스냅샷과 같은 방식으로 저장소 상위의 `지식` 폴더에서 찾도록
  바꾸고, 못 찾으면 **이유를 출력**하게 했습니다. 침묵이 문제를 오래 숨겼기
  때문입니다.
- **설정 파일 분리** — 계정·서버 주소는 `config.json`(Git 제외), 저장소에는
  `config.example.json` 템플릿만 둡니다.
- **하드코딩 경로 제거(2026-08-21 점검)** — 호출되지 않는데 기본값에
  `D:\BellalunData\Image` 가 박혀 있던 함수 두 개를 지웠습니다. 인자 없이 부르면
  이 PC(`C:` 드라이브)에서 조용히 빈 결과를 돌려줬을 코드입니다. 필요해지면
  `run.py::_resolve_data_dir` 가 해석한 `ctx.cfg["data_dir"]` 을 넘겨 다시 만듭니다.
- **절대 데스크톱 좌표 제거(2026-08-21 점검)** — Q.C 캔버스 포커스 클릭 한 곳에
  `(760, 550)` 이 남아 있었습니다. 창 rect 에서 비율로 계산하도록 바꿨습니다.
  이제 저장소에 절대 데스크톱 좌표 클릭은 없습니다.
- **누적 상태에 대한 전제 확인(2026-08-21 점검)** — 단독 실행을 반복하면
  `DICOM_STORAGE` 에 같은 SCP 가 여러 행 쌓여 **모두 `Use=1`** 이 될 수 있습니다
  (실측 3행). 그러면 같은 영상이 여러 SCP 로 나가 "수신 객체가 정확히 N건" 판정이
  조용히 틀립니다. 이제 Send 계열 TC 가 **활성 SCP 가 하나인지 먼저 판정**하고,
  아니면 복구 명령과 함께 FAIL 로 드러냅니다.

---

## 9. 현재 상태와 남은 일

### 회귀 실적 추이 (모두 실측)

**두 층을 구분해 읽습니다.** `TC 판정`은 TC 하나의 종합 결과이고, `검증 판정`은 그
안의 Step(체크) 단위 결과입니다. TC 하나가 여러 체크를 담으므로 체크 수가 훨씬
많습니다 — 21개 TC가 176개 체크를 수행합니다. 리포트 머리글도 두 줄로 나눠 적습니다.

| 회차 | 일시 | TC | TC 판정 (P/F/M) | 체크 수 | 검증 판정 (P/F/M/S) | 비고 |
|---|---|---|---|---|---|---|
| 6차 | 08-18 12:10 | 15 | 9 / 1 / 5 | 129 | 121 / 1 / 6 / 1 | FAIL 1 = 제품 결함 |
| 7차 | 08-18 16:56 | 17 | 3 / 10 / 4 | 45 | 30 / 10 / 5 / 0 | **연쇄 실패** — 원인 1개 (§6) |
| 8차 | 08-18 17:52 | 17 | 9 / 4 / 4 | 135 | 121 / 5 / 8 / 1 | 기동·서비스 수정 |
| 10차 | 08-19 09:55 | 17 | 8 / 2 / 7 | 136 | 124 / 2 / 9 / 1 | Send·화면 이동 수정 |
| 11차 | 08-19 11:26 | 17 | 9 / 2 / 6 | 136 | 124 / 2 / 9 / 1 | 개정본 기준 TC 번호 전면 재정렬 |
| 12차 | 08-19 13:50 | 18 | 11 / 1 / 6 | 152 | 140 / 1 / 10 / 1 | 저장 확인 팝업 처리, WF_06 신규 |
| 13·14차 | 08-19 14:39·14:59 | 20 | 3 / 13 / 4 | 49 | 30 / 14 / 5 / 0 | **제가 넣은 로그인 가드가 정상 실행을 막음**(§6) |
| 15차 | 08-19 16:00 | 20 | 13 / 1 / 6 | 172 | 160 / 1 / 10 / 1 | 가드 재설계, WF_05·WF_09 신규 |
| 16차 | 08-19 20:18 | 21 | 13 / 2 / 6 | 176 | 163 / 2 / 10 / 1 | 파일명↔TC 맵핑, WF_13 신규. FAIL 2 = 제품 결함 1 + **제가 넣은 버그 1** |
| 17차 | 08-20 16:12 | 26 | 16 / 1 / 9 | 233 | 215 / 1 / 16 / 1 | WF_07/10/11/12/15 신규, 회귀를 개정본 TC 행 순서로 재배열. 80.1분. FAIL 1 = 제품 결함뿐 |
| 18차 | 08-21 13:04 | 28 | 17 / 4 / 7 | 254 | 232 / 5 / 16 / 1 | WF_14/WF_16 신규. 94.2분. FAIL 4 중 3건은 **Storage 활성 행 중복**(자동화 결함, §6) — WF_13 로그인 전환 결함은 이 회차에서 해소 |
| 19차 | 08-21 16:40 | 26 | 20 / 1 / 5 | 251 | 241 / 1 / 7 / 2 | Storage 설정 행/작업 사본 구분 수정, WF_03 Overlay 자동화, WF_16 전체 수동 전환. 111.3분. FAIL 1 = 기존 XIPL_03 Step 9 제품 결함 |

체크 수가 회차마다 다른 이유: 앞선 TC가 실패하면 뒤 TC가 전제 미충족으로 조기
중단되어 수행되는 체크 자체가 줄어듭니다(7차 45개, 13·14차 49개). **체크 수가
급감한 회차는 그 자체가 연쇄 실패의 신호입니다.**

> **중간 변경의 검증 범위**: Image Overlay를 Bottom에 배치한 변경과 Print Overlay
> 영역 분리는 전체 회귀가 아니라 **영향 범위만** 검증했습니다
> (`setup-dicom → run-wf01 → run-wf02 → run-wf03 → run-wf08`). 호출부가 그 TC들
> 뿐이어서 나머지는 무관합니다. 16차는 파일명 재배치가 전 모듈에 걸리므로 **전체
> 회귀**를 돌렸습니다(57분).
>
> 19차 전에는 **연쇄 재현**을 먼저 했습니다. Storage 중복은 단독 실행으로는
> 재현되지 않고 `WF_03` 이 Setting 을 쓴 뒤 `WF_04` 에서 나타났기 때문에,
> `reset-environment → setup-dicom → run-wf01 → run-wf02 → run-wf03 → run-wf04
> → run-wf05 → run-wf06` 을 실제로 지나간 뒤 DB 로 활성 행 수를 확인했습니다.
> **단독 실행 통과 ≠ 그 분기 검증** 이라는 규칙(§3.2)을 그대로 적용한 것입니다.

**16차의 FAIL 2건 중 1건은 제가 만든 버그입니다.** 숨기지 않고 적습니다.

`TC_Basic_WorkFlow_06`이 `'list' object is not callable`로 죽었습니다. 원인은
`send_flows.py`를 TC별 모듈로 나눌 때 쓴 자동 치환 스크립트였습니다. 공용 헬퍼
이름을 `sv.`로 한정하면서 **같은 이름의 지역 변수까지** 접두사를 붙였습니다.

```python
received = _received(ctx) or []      # 원본 — 지역 변수
sv.received = sv.received(ctx) or []  # 치환 결과 — 모듈 함수를 리스트로 덮어씀
```

`WF_05`가 먼저 실행되며 `send_verify.received`를 리스트로 덮어쓰고, 뒤이은 `WF_06`이
그 오염된 모듈을 물려받아 함수를 호출하려다 죽었습니다. **단독 실행에서는 드러나지
않고 회귀에서만 깨지는 형태**입니다(§6의 `XIPL_04`와 같은 부류).

`py_compile`과 `ast` 미정의 이름 검사 모두 통과했습니다 — 둘 다 "존재하는 이름에
대입하는 것"은 잡지 못합니다. 그래서 검사를 하나 더 만들었습니다:
`tools_check_module_attrs.py` 가 **모듈 속성에 대입하는 곳(`sv.<name> = ...`)**과
**참조하는 `sv.*` 이름이 실제로 모듈에 있는지**를 전수 확인합니다(44개 모듈 통과).

**고친 뒤의 검증도 한 번 잘못했습니다.** `run.py run-wf05` 와 `run.py run-wf06` 을
따로 돌려 "고쳤다"고 볼 뻔했는데, 둘은 **별도 프로세스**라 모듈 오염 경로를 아예
지나가지 않습니다. 회귀와 같은 조건은 **한 프로세스에서 이어 돌리는 것**입니다.
그래서 두 TC를 한 프로세스에서 호출하고, 사이사이 `callable(sv.received)` 를 확인해
오염이 재발하지 않는 것을 증거로 남겼습니다.

나머지 1건 `TC_XIPL_compatibility_03` Step 9는 **실제 제품 결함**입니다(Apply 후
파라미터 기본값 복귀). 의도적으로 완화하지 않습니다.

13·14차의 급락은 **제 실수**입니다. 숨기지 않고 §6에 경위를 적었습니다 — 재현할 수
없는 상황에 '중단' 로직을 넣은 것이 원인이었습니다.

### 완전 자동 (20건)

| TC | 내용 |
|---|---|
| `Install_01/02` | 설치 버전·패키지 구성, 실행 전 필수 환경 |
| `WorkFlow_01` | MWL 및 Local 검사 생성 |
| `WorkFlow_02` | 공통 2D/3D 검사 촬영 및 Tool 적용 |
| `WorkFlow_03` | Image Overlay(Bottom) 및 Print Overlay(Header/Top/Bottom) 설정 — **Step 1~6 전부** |
| `WorkFlow_05` | 3D 수동 DICOM Send (사양이 정한 Recon 수신 대조) |
| `WorkFlow_07` | Emergency 검사 Auto Send (**Send를 누르지 않고** 전송되는 것까지) |
| `WorkFlow_08` | 2D/3D Film Print (Header/Top/Bottom **영역별** 출력물 OCR·raster 대조) |
| `WorkFlow_09` | Normal 및 Anonymous Export (익명화 값까지 대조) |
| `WorkFlow_10` | MWL Hospital Code와 Procedure 매핑 (**1~7단계 전부**) |
| `WorkFlow_11` | Image Reject 및 Restore (사유 값까지 DB 대조) |
| `WorkFlow_12` | Study Reject 및 Restore (Rejected 필터로 목록 확인) |
| `WorkFlow_13` | 계정 추가·수정 및 로그인 (**권한 표 56개 항목** 실측 대조) |
| `WorkFlow_14` | Setting Export 및 Import (**.vms 구성 + 설정 전수 복원 대조**) |
| `XIPL_compatibility_01~06` | XIPL 연동 6종 (영상처리 파라미터 왕복 검증) |

`WorkFlow_10` 의 5~7단계는 2026-08-21 에 붙였습니다. 판정 기준을 **DB 주 판정 +
화면 보강**으로 확정했습니다 — Expected 6 은 `STUDY.HospitalCode` 와
`STUDY.ProcedureKey`(MWL 태그의 코드가 매핑된 Procedure 로 해석됐는가), Expected 7 은
Examine 의 Step 수를 `PROCEDURE_ITEMS` 행 수와 대조하고 상단 Ready 배너로 첫
Step/Preset 선택을 확인합니다. 이 판정이 **항상 참이 되는 종류가 아닌 근거**는
`WorkFlow_01` 이 Procedure 없는 MWL 처방에서 Step 수 0 을 확인하는 대조군이라는
점입니다.

`WorkFlow_14` 는 2026-08-21 신규입니다. 자세한 설계는 §6 "선행 도구의 오탐을 원인
쪽에서 없앤 것"을 보십시오.

`WorkFlow_03` 의 Step 5·6 은 2026-08-21 에 붙여 **전 단계 자동**이 됐습니다.

- **Step 5** (2D 영상의 Image Overlay 표시) — Examine 화면 영상 패널(컨트롤 203)의
  위·아래를 크롭해 OCR 하고, Step 1 이 Bottom 에 추가한 항목의 **라벨이 실제로
  찍히는지** 판정합니다. 개정본 Expected 5 가 요구하는 것은 "설정한 Image Overlay
  **항목**이 표시된다" 이지 값이 맞는지가 아닙니다. 이 PC 는 Demo(F8) 가상 촬영이라
  선량 값이 `-- kVp` / `-- mAs` 로 찍히므로(실측) **값 일치를 요구하면 정상 동작을
  실패로 판정**합니다. 값 쪽은 환자 ID·생년월일을 DB 와 대조하는 **교차 확인** 항목으로
  따로 남깁니다.
- **Step 6** (Film 창의 Print Overlay 표시) — Examined 에서 Print(2188) →
  Selected(501) 로 Film 창을 열고 Layout 1x1(1141)로 맞춘 뒤, Step 2 가 세 영역에
  저장한 6개 항목이 **영역별로** 찍히는지 OCR 로 대조합니다. 한 곳만 읽으면 6개가
  전부 Top 에 몰려 있어도 통과하므로 영역을 나눠 읽습니다.
  **`WorkFlow_08` 과 중복이 아닙니다** — 여기는 Film **창의 표시**를 보고,
  `WorkFlow_08` 은 실제 DICOM Print 를 수행해 **Print SCP 가 수신한 출력물**을 봅니다.

두 판정의 크롭·OCR 코드는 `core/image_overlay.py`(WF_15 와 공용)와
`core/print_overlay.py`(WF_08 과 공용)로 **하나만** 둡니다. 같은 판정을 두 곳에서
따로 구현하면 한쪽만 고쳐 다른 쪽이 조용히 낡습니다.

### 부분 자동 (6건)

`Install_07/08/09` — 설정·데이터 유지는 DB로 자동 판정하고, 설치·업그레이드·제거
실행 자체는 파괴적이라 수동입니다.

`WorkFlow_04`(2D 수동 DICOM Send) — 개정본이 요구하는 것을 그대로 판정합니다.
Selected Images로 전송 → Queue `State=Done` 확인 → 수신 객체 **정확히 1건** →
**식별 태그 4개**(Patient ID / Study·Series·SOP Instance UID)를 DB와 대조 →
수신 객체가 Digital Mammography X-Ray Image Storage인지 SOP Class로 확인.
전송 전 Transfer Syntax를 Conformance Statement 선언값으로 맞춥니다(§6).
Examined 창 진입 자체는 `open_test_study` 가 대신하므로 Step 1 의 UI 경로만
부분 자동입니다.

`WorkFlow_06`(All Images 및 Dose SR 전송) — All Images 전송과 Queue/수신 판정은
자동입니다. Queue의 Image/DSR 구분은 `ClassUID`로 하고, RDSR SOP Class UID는
체크리스트 Test Data 값을 씁니다. **RDSR이 수신되지 않으면 FAIL이 아니라 MANUAL**
입니다 — 개정본 Precondition이 "RDSR 생성 조건을 충족"을 요구하는데 이 환경은
Demo(F8) 가상 촬영이라 그 조건 성립이 확인되지 않았습니다. 전제 미충족을 제품
결함처럼 보고하지 않습니다.

`WorkFlow_15`(Pre-send Preview) — Preview 창의 영상 패널 개수·Overlay 판독,
같은 검사를 View 로 열어 항목 관찰 대조(Step 4), Send 후 Queue `State=Done` 과
수신 객체 식별 Tag 대조까지 자동입니다. 남은 MANUAL 은 **Dose SR 뿐**이고 이유는
`WorkFlow_06` 과 같습니다(Demo 촬영 전제 미충족).

### 수동 (10건)

실물 장비(Detector/Gantry/ACR Phantom), 신규 OS 설치, 파괴적 작업, 또는
**체크리스트 자체가 허용 기준을 확정하지 않은 것**이 이유입니다.
**임의로 자동 PASS를 만들지 않는 것이 이 프로젝트의 원칙입니다.**

| TC | 막힌 지점 | 해제 조건 |
|---|---|---|
| `Install_03/04/05` | Windows 10 / 11 / 11 IoT LTSC **신규 설치 환경** | 별도 시험 PC |
| `Install_06` | Detector/Gantry 실제 연결, VIVIX-M Setup·Bellalun System Setup 실행 | 실물 장비가 연결된 시험 PC |
| `QC_01/02` | 실물 **ACR Phantom** 2D/3D 촬영 | 팬텀 + 실제 X-ray |
| `Performance_01/02/03` | X-ray 스위치 입력 시점 측정 + **체크리스트 Test Data 가 "허용 기준: 추가 사양 확인 필요"** 라고 명시 | 팬텀 + 실제 X-ray + 시험계획서의 허용 기준 |
| `WorkFlow_16` | **사용자가 전체 수동으로 지정**(2026-08-21). 제품 동작은 자동화하지 않고 회귀에는 MANUAL 판정 행만 기록합니다 | 없음 — 자동화 재시도 대상이 아닙니다 |

Performance 3건은 장비만 있으면 되는 것이 아닙니다. **판정 기준 자체가 문서에
없습니다** — 기준 없이 측정값만 찍어 PASS 라고 쓰지 않습니다.

`WorkFlow_16`(Kiosk 및 System Launcher)은 2026-08-21 에 **사용자 지시로 전체 수동**이
됐습니다. 개정본 Step 자체가 자동화와 맞지 않습니다 — Step 3 은 시스템 재시작,
Step 12 는 PC 종료여서 자동화 세션이 함께 죽고, Step 4~9 의 System Launcher 는
재시작 후 Kiosk 조건에서만 나타나며, Step 5/6 의 VIVIX-M Setup / Bellalun System
Setup 은 엔지니어 전용 프로그램이라 이 PC 에 설치되어 있지 않습니다.
게다가 Kiosk 를 켠 채 재부팅되면 Windows 바탕화면이 뜨지 않아 복구가 어렵습니다.

사용자 지시인 "자동화 코드도 만들지 말고 수행하지 마라"를 그대로 반영해,
`tests/workflow16.py` 에는 제품을 조작하는 Kiosk UI 자동화 코드를 두지 않습니다.
`run.py` 의 단독 실행과 전체 회귀 모두 MANUAL 판정 한 건만 기록합니다.

### 자동화 보조 (4건 — 그중 2건은 회귀에서 제외)

개정본 TC가 아니지만 자동화가 수행하는 항목입니다. 체크리스트 결과 xlsx에는
'자동화 추가 항목'으로 덧붙습니다.

- `AUTOMATION_ENVIRONMENT_RESET` — DB 기준 스냅샷 복원, 제품 서비스 재기동,
  XIPL 시험 파라미터 재생성 **(회귀에 포함)**
- `DICOM_Server_Setup` — MWL/Storage/Print 등록과 C-ECHO 연결 **(회귀에 포함)**
- `AUTOMATION_3D_ACQUISITION_3DN` / `_3DW` — 3D-N/3D-W Preset 등록과 Demo 촬영,
  `INSTANCE_GROUP.ExposureMode` 판정. **2026-08-21 부터 회귀에서 제외**했습니다
  (사용자 지시) — 개정본 TC 가 아니고 종합 판정이 장비 MANUAL 로 끝나 상세 결과에
  실을 내용이 없습니다. 3D 픽스처는 `WorkFlow_02` 가 이미 만듭니다. 필요할 때
  `python run.py run-sys3d` 로 단독 실행합니다.

---

## 10. 참고 문서

| 문서 | 용도 |
|---|---|
| `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` | **시험 대상 TC의 유일한 기준** (시트 `개정 TC`) |
| `AGENTS.md` | 기준 문서, 코드 수정·검증·커밋 규칙 (0절부터 읽는다) |
| `NEXT_TASK.md` | 다음 우선순위, 미결정 사항, 환경 준비 상태 |
| `PORTABILITY_AUDIT.md` | 이식성 점검 결과 |
| `automation_scope.json` | 개정본 36개 TC + 보조 4개의 자동화 수준과 사유 |
| `..\지식\[자동화 운영 지침] ...md` | 영구 적용 규칙 (0절: 어떤 문서를 근거로 삼는가) |

### 판정 근거로 쓰는 원본 문서

자동화 코드를 새로 쓸 때도, 고도화할 때도 이 문서들이 기준입니다(§3.2 ②).
**TC가 "무엇을 하는지"는 개정본에서, "왜 그것이 정상인지"는 매뉴얼·사양서에서**
확인합니다.

| 문서 | 무엇을 여기서 확인하나 |
|---|---|
| `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` | **TC의 Step / Expected Result 원문.** 시트 `개정 TC`. TC ID로 내용을 추측하지 않는다 |
| `..\지식\Bellalun Viewer Operation Manual ...` | 사용자 절차, 기대 동작, 기능의 선행조건 |
| `..\지식\Bellalun Viewer Service Manual ...` | Setting 각 항목의 의미·선택지·반영 조건 |
| `..\지식\...DICOM Conformance Statement ...` | SOP Class, Transfer Syntax, SCU/SCP 동작 |
| `..\지식\(사양서) ....pdf` | 제품 사양·허용 범위 |

`.docx` / `.xlsx` / `.pdf`는 grep이 되지 않으므로 같은 폴더의 추출된 `.txt`
사본을 검색에 사용합니다.

**한 번 크게 틀린 적이 있습니다.** `지식` 폴더에 있는 다른 체크리스트
(`(TC) R-23-2346_...xlsx`)를 기준으로 착각해, 정상 구현된 `WorkFlow_02`를 "체크리스트
원문과 범위가 다르다"며 등급을 내렸습니다. 두 문서는 **같은 형태의 TC ID를 쓰지만
번호 매핑이 다릅니다.** 사용자가 바로잡아 준 뒤 전 TC를 개정본으로 재정렬했고,
`AGENTS.md` 0절에 기준 문서를 못박아 같은 혼동이 반복되지 않게 했습니다.

---|---|
| `(TC) ..._기본기능_Checklist.xlsx` | TC의 Step / Expected Result **원문** — TC ID로 내용을 추측하지 않는다 |
| `Bellalun Viewer Operation Manual ...` | 사용자 절차, 기대 동작, 기능의 선행조건 |
| `Bellalun Viewer Service Manual ...` | Setting 각 항목의 의미·선택지·반영 조건 |
| `DICOM Conformance Statement` | SOP Class, Transfer Syntax, SCU/SCP 동작 |
| `(사양서) ....pdf` | 제품 사양·허용 범위 |

`.docx` / `.xlsx` / `.pdf`는 grep이 되지 않으므로 같은 폴더의 추출된 `.txt`
사본을 검색에 사용합니다.

---

## 부록: 실행 중 유의사항

**마우스/키보드를 점유합니다.** 커스텀 렌더링 컨트롤이 표준 메시지에 반응하지 않아
실제 물리 입력(`SetCursorPos`+`mouse_event`, `SendInput`)을 사용합니다. 실행 중
같은 세션에서 다른 작업을 하려면 Switch User로 별도 Windows 세션에서 돌리십시오.

**실패 후 프로세스가 남았을 때** (안전하게 정리 가능)

```bash
powershell -NoProfile -Command "Get-Process VIEWER,XIPL.STUDIO -ErrorAction SilentlyContinue | Stop-Process -Force"
```

**실촬영 안전 게이트**: 2D/3D 촬영은 `config.json > viewer.demo_mode = true`일 때만
동작합니다. Demo 모드가 아니면 자동화가 촬영을 시도하지 않고 FAIL로 기록합니다.
실제 X-ray 노출은 자동으로 실행하지 않습니다.
