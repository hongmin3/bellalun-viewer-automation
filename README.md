# Bellalun Viewer 기본기능 QA 자동화

의료영상 진단 소프트웨어(디지털 유방촬영 Viewer)의 **QA 체크리스트를 실제 UI로
자동 수행하고 Pass/Fail을 스스로 판정하는** 테스트 자동화 프레임워크입니다.

사람이 손으로 하루씩 돌리던 회귀 시험을, **명령 한 줄로 30~40분에 끝나고 근거까지
남기는** 자동화로 만들었습니다.

```bash
python run.py run-regression
```

---

## 1. 한눈에 보기

| 항목 | 내용 |
|---|---|
| 대상 | Bellalun Viewer 1.0.12 (Windows 데스크톱 의료영상 SW) |
| 기준 문서 | `Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` (시트 `개정 TC`) |
| 규모 | Python 약 **12,800줄**, 모듈 39개(core 24 / tests 13), 커밋 46개 |
| 시험 범위 | 개정본 체크리스트 **36개 TC** 전수 등록 — 완전자동 14 / 부분자동 5 / 수동 17 (+ 자동화 보조 4) |
| 최신 전체 회귀 | **20개 TC 중 PASS 13 / FAIL 1 / MANUAL 6** (2026-08-19 16:00) |
| 그 안의 검증 항목 | **172개 체크 중 PASS 160 / FAIL 1 / MANUAL 10 / SKIP 1** |
| 그 FAIL 1건 | 자동화가 **실제 제품 결함을 잡아낸** 정상 결과 (§6) |
| 외부 의존성 | Pillow, pytesseract, openpyxl, pypdf **4개뿐** (§4 참고) |

### 이 자동화가 실제로 하는 일

명령을 넣으면 사람의 개입 없이 아래를 **순서대로 전부** 수행합니다.

```
DB를 기준 스냅샷으로 복원 → 시험 파라미터 재생성
  → Viewer 실행·로그인 → DICOM 서버 3종 등록 + C-ECHO 연결 확인
  → MWL 처방 조회·검사 생성 → 2D/3D 촬영(Demo) → Tool 적용 검증
  → DICOM Print 실제 출력 + 출력물 웹 프리뷰 OCR 대조
  → XIPL 연동 6종(영상처리 파라미터 왕복 검증)
  → 3D-Narrow / 3D-Wide 촬영 검증
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
| `tests/workflow03.py` | `WF_03` | Image Overlay(Bottom) / Print Overlay(Header·Top·Bottom) 설정 |
| `tests/workflow04.py` | `WF_04` | 2D 수동 DICOM Send |
| `tests/workflow05.py` | `WF_05` | 3D 수동 DICOM Send |
| `tests/workflow06.py` | `WF_06` | All Images 및 Dose SR 전송 |
| `tests/workflow08.py` | `WF_08` | 2D/3D Film Print (영역별 출력물 대조) |
| `tests/workflow09.py` | `WF_09` | Normal 및 Anonymous Export |
| `tests/workflow13.py` | `WF_13` | 계정 추가·수정 (1~3단계) |
| `tests/xipl_flows.py` | `XIPL_01~06` | XIPL 연동 6종 (한 흐름을 공유하므로 묶음) |
| `tests/install.py` | `Install_01/02/07/08/09` | 설치·환경 점검 |
| `tests/system_compat.py` | `System_compatibility_03/04` | 3D-Narrow / 3D-Wide 촬영 |

이 정리 전에는 **`tests/workflow03.py` 가 `WF_08`(Film Print)을 담고 있었습니다.**
이름이 정면으로 오해를 부르는 상태였고, `send_flows.py` 한 파일에 `WF_04`/`05`/`06`
세 TC가 섞여 있었습니다. 옮기면서 TC가 아니라 인프라에 해당하는 부분(Queue·수신
객체·식별 Tag 대조)은 `core/send_verify.py` 로 내렸습니다.

**아직 연결되지 않은 모듈**: `tests/dataflow.py`, `tests/settings.py` 는 pre/post DB
스냅샷을 받아 판정하는 함수 모음인데 **어디에서도 import되지 않습니다.** UI 드라이버가
없어 한 번도 실행된 적이 없습니다(`core/checklist.py` 가 8일간 출력을 못 냈던 것과 같은
종류의 문제 — §6). `WF_11`/`WF_12` 구현 시 이 판정 로직을 재사용할 계획입니다.

```
run.py                     CLI 진입점 · 환경 게이트(해상도/DPI/권한) · 리포트 생성
│
├── tests/                 TC별 시나리오와 Pass/Fail 판정 (위 맵핑표)
│
└── core/                  재사용 계층 (제품 조작 · 증거 수집)
    ├── ui.py              Win32 컨트롤 열거 · 물리 입력 · 화면 캡처
    ├── uitext.py          커스텀 렌더 컨트롤의 화면 텍스트 OCR · 문구로 항목 선택
    ├── flows.py           화면 전환 시나리오 (로그인·Setting·검사) + 컨트롤 맵
    ├── viewer_processing.py  영상처리 파라미터 UI + OCR 판독
    ├── viewer_tools.py    Tool(W/L·Zoom·Pan·Annotation) 적용 검증
    ├── xipl.py            XIPL Studio 제어 (WPF UI Automation)
    ├── print_overlay.py   Print Overlay 설정 + 출력물 영역별 대조
    ├── send_verify.py     DICOM Send 공용 판정 (Queue·수신 객체·식별 Tag)
    ├── export_manager.py  Export Manager 제어 (별도 프로세스)
    ├── specs.py           사양서 PDF 검색 (SRS 번호 인용)
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
| `run.py run-wf13` | WF_13 계정 추가·수정 (1~3단계 자동, 4~6단계 수동) |
| `run.py run-xipl` | XIPL 연동 6종 (`-01`~`-06`로 개별 실행) |
| `run.py run-sys3d` | 보조: 3D-Narrow / 3D-Wide 촬영 검증 |
| `run.py list` | 개정본 36개 TC의 자동화 수준과 사유 |
| `run.py snapshot-baseline` | 현재 DB를 기준 스냅샷으로 저장 |
| `run.py reset-environment` | 기준 스냅샷으로 되돌리기 |

### 5.3 결과물

| 위치 | 내용 |
|---|---|
| `Reports/Result_<시각>.html` | 사람이 읽는 판정 리포트 (색상 구분) |
| `Reports/Result_<시각>.json` | 기계 판독용 전체 판정·근거 |
| `Evidence/` | 단계별 화면 캡처 (실패 시 원인 추적용) |
| 체크리스트 xlsx | 원본 TC 행 옆에 판정 열을 덧붙인 사본 |

리포트에는 판정만이 아니라 **무엇과 무엇을 대조했는지**가 함께 남습니다.

```
[PASS] Step 6 변경된 세부 설정이 대상 영상에 적용
  values: {'Contrast': 15, 'Sharpness': 10, 'Brightness': 10,
           'Tone type': 20, 'Noise reduction': 8}
  applied_log: {'parameter': 'TEST_XIPL_SAVED_M.pim', ...}
  note: Apply 후 Image Processing에 재진입하여 UI 표시값을 다시 읽어 비교
```

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

---

## 9. 현재 상태와 남은 일

### 회귀 실적 추이 (모두 실측)

**두 층을 구분해 읽습니다.** `TC 판정`은 TC 하나의 종합 결과이고, `검증 판정`은 그
안의 Step(체크) 단위 결과입니다. TC 하나가 여러 체크를 담으므로 체크 수가 훨씬
많습니다 — 20개 TC가 172개 체크를 수행합니다. 리포트 머리글도 두 줄로 나눠 적습니다.

| 회차 | 일시 | TC | TC 판정 (P/F/M) | 체크 수 | 검증 판정 (P/F/M/S) | 비고 |
|---|---|---|---|---|---|---|
| 6차 | 08-18 12:10 | 15 | 9 / 1 / 5 | 129 | 121 / 1 / 6 / 1 | FAIL 1 = 제품 결함 |
| 7차 | 08-18 16:56 | 17 | 3 / 10 / 4 | 45 | 30 / 10 / 5 / 0 | **연쇄 실패** — 원인 1개 (§6) |
| 8차 | 08-18 17:52 | 17 | 9 / 4 / 4 | 135 | 121 / 5 / 8 / 1 | 기동·서비스 수정 |
| 10차 | 08-19 09:55 | 17 | 8 / 2 / 7 | 136 | 124 / 2 / 9 / 1 | Send·화면 이동 수정 |
| 11차 | 08-19 11:26 | 17 | 9 / 2 / 6 | 136 | 124 / 2 / 9 / 1 | 개정본 기준 TC 번호 전면 재정렬 |
| 12차 | 08-19 13:50 | 18 | 11 / 1 / 6 | 152 | 140 / 1 / 10 / 1 | 저장 확인 팝업 처리, WF_06 신규 |
| 13·14차 | 08-19 14:39·14:59 | 20 | 3 / 13 / 4 | 49 | 30 / 14 / 5 / 0 | **제가 넣은 로그인 가드가 정상 실행을 막음**(§6) |
| **15차** | 08-19 16:00 | **20** | **13 / 1 / 6** | **172** | **160 / 1 / 10 / 1** | 가드 재설계, WF_05·WF_09 신규 |

체크 수가 회차마다 다른 이유: 앞선 TC가 실패하면 뒤 TC가 전제 미충족으로 조기
중단되어 수행되는 체크 자체가 줄어듭니다(7차 45개, 13·14차 49개). **체크 수가
급감한 회차는 그 자체가 연쇄 실패의 신호입니다.**

> **15차 이후 변경의 검증 범위**: Image Overlay를 Bottom에 배치하는 변경
> (`WorkFlow_03`)은 전체 회귀가 아니라 **영향 범위만** 검증했습니다 —
> `setup-dicom → run-wf01 → run-wf02 → run-wf03` (약 18분). `add_image_overlay_items`
> 호출부가 `WorkFlow_03` 한 곳뿐이어서 나머지 TC는 이 변경과 무관합니다.
> 그래서 위 표의 최신 값은 15차 그대로입니다.

**15차의 FAIL은 1건이며, 실제 제품 결함입니다**(`XIPL_03` Step 9 — Apply 후 파라미터
기본값 복귀). 자동화가 스스로 막혀서 실패한 항목은 남아 있지 않습니다.

13·14차의 급락은 **제 실수**입니다. 숨기지 않고 §6에 경위를 적었습니다 — 재현할 수
없는 상황에 '중단' 로직을 넣은 것이 원인이었습니다.

### 완전 자동 (14건)

| TC | 내용 |
|---|---|
| `Install_01/02` | 설치 버전·패키지 구성, 실행 전 필수 환경 |
| `WorkFlow_01` | MWL 및 Local 검사 생성 |
| `WorkFlow_02` | 공통 2D/3D 검사 촬영 및 Tool 적용 |
| `WorkFlow_03` | Image Overlay(Bottom) 및 Print Overlay(Header/Top/Bottom) 설정 |
| `WorkFlow_05` | 3D 수동 DICOM Send (사양이 정한 Recon 수신 대조) |
| `WorkFlow_08` | 2D/3D Film Print (Header/Top/Bottom **영역별** 출력물 OCR·raster 대조) |
| `WorkFlow_09` | Normal 및 Anonymous Export (익명화 값까지 대조) |
| `XIPL_compatibility_01~06` | XIPL 연동 6종 (영상처리 파라미터 왕복 검증) |

### 부분 자동 (6건)

`Install_07/08/09` — 설정·데이터 유지는 DB로 자동 판정하고, 설치·업그레이드·제거
실행 자체는 파괴적이라 수동입니다.

`WorkFlow_04`(2D 수동 DICOM Send) — 개정본이 요구하는 것을 그대로 판정합니다.
Selected Images로 전송 → Queue `State=Done` 확인 → 수신 객체 **정확히 1건** →
**식별 태그 4개**(Patient ID / Study·Series·SOP Instance UID)를 DB와 대조 →
수신 객체가 Digital Mammography X-Ray Image Storage인지 SOP Class로 확인.
전송 전 Transfer Syntax를 Conformance Statement 선언값으로 맞춥니다(§6).

`WorkFlow_06`(All Images 및 Dose SR 전송) — All Images 전송과 Queue/수신 판정은
자동입니다. Queue의 Image/DSR 구분은 `ClassUID`로 하고, RDSR SOP Class UID는
체크리스트 Test Data 값을 씁니다. **RDSR이 수신되지 않으면 FAIL이 아니라 MANUAL**
입니다 — 개정본 Precondition이 "RDSR 생성 조건을 충족"을 요구하는데 이 환경은
Demo(F8) 가상 촬영이라 그 조건 성립이 확인되지 않았습니다. 전제 미충족을 제품
결함처럼 보고하지 않습니다.

`WorkFlow_13`(계정 추가·수정 및 로그인) — **1~3단계는 자동**입니다. Setting >
System > Account 에서 계정을 추가하고(New Account 모달), 권한 그룹을 고르고, 계정
정보를 수정한 뒤 `ACCOUNT` 테이블로 대조합니다. `ACCOUNT.Group` 매핑
**Service=3 / Admin=2 / User=1** 은 실제로 만들어 DB로 확인한 값입니다.

4~6단계(로그오프 → 시험 계정 로그인 → 권한별 메뉴 접근)는 **의도적으로 수동**입니다.
로그인 계정을 바꾸면 회귀의 뒤따르는 TC가 제한 권한으로 실행되고, 중간에 실패하면
로그인 상태를 복구할 수 없습니다. 이 저장소는 그런 연쇄 실패를 이미 세 번 겪었고
(회귀 7·13·14차) 매번 원인 추적에 오래 걸렸습니다. 권한 코드별 기능 범위 표도
매뉴얼에 없어 6단계의 기대값을 확정할 수 없습니다.

### 수동 (16건)

실물 장비(Detector/Gantry/ACR Phantom), 신규 OS 설치, 사양 미확정, 또는 **UI
드라이버 미구현**이 이유입니다. **임의로 자동 PASS를 만들지 않는 것이 이
프로젝트의 원칙입니다.**

미구현 중 다음은 기존 구조를 재사용할 수 있어 우선순위가 높습니다.

이번에 **미구현 TC의 진입점을 실측**해 뒀습니다(2026-08-19). 아이콘 모양으로
추정하지 않고 캡처의 화면 라벨과 rect를 대조해 확정했습니다 — 이 저장소는 예전에
`2184`를 Send로 추정했다가 실제로는 `Import Study`였던 적이 있습니다.

| TC | 실측한 진입점 | 남은 것 |
|---|---|---|
| `WorkFlow_07` Emergency Auto Send | Patient 화면 Emergency = `1100`(사이렌 아이콘) / Setting > DICOM > General `2444` "Study close option on Examine mode" · `2446` "Send urgent patient automatically" Yes | 촬영은 `WF_02` 재사용, Queue·수신 판정은 `core/send_verify.py` 재사용 가능. Emergency 검사가 매 실행 새로 생겨 데이터가 쌓이는 문제를 어떻게 다룰지 결정 필요 |
| `WorkFlow_11/12` Reject 및 Restore | Setting > Study > Reject/Retake = 페이지 `211`, 옵션 `2421`~`2428`. **전제조건이 이미 충족**돼 있음을 확인(Use reject reason ✓, Always display rejected images ✓, Reason 5건) | **Reject 실행 버튼을 아직 못 찾았습니다.** Examined 툴바 14개에는 없고, 검사를 연 화면에서 찾아야 합니다. 판정은 `tests/dataflow.py`의 DB 델타 로직을 재사용 |
| `WorkFlow_14` Setting Export/Import | Setting > System > My Settings = 페이지 `193`, `2293` Export / `2294` Import | 파일 대화상자 처리와 Viewer 재시작 후 복원 확인 |
| `WorkFlow_10` MWL Hospital Code 매핑 | Setting > Procedure > Hospital Code = 페이지 `215` | RIS/MWL 서버에 Hospital Code가 포함된 처방을 등록하는 방법 확인 필요 |
| `WorkFlow_15` Send Preview 위치 적용 | Setting > DICOM > Storage = 페이지 `219` | 수신 영상의 표시 위치를 Preview와 대조하는 기준 확정 필요 |

### 자동화 보조 (4건)

개정본 TC가 아니지만 자동화가 수행하는 항목입니다. 체크리스트 결과 xlsx에는
'자동화 추가 항목'으로 덧붙습니다.

- `AUTOMATION_ENVIRONMENT_RESET` — DB 기준 스냅샷 복원, 제품 서비스 재기동,
  XIPL 시험 파라미터 재생성
- `DICOM_Server_Setup` — MWL/Storage/Print 등록과 C-ECHO 연결
- `AUTOMATION_3D_ACQUISITION_3DN` / `_3DW` — 3D-N/3D-W Preset 등록과 Demo 촬영,
  `INSTANCE_GROUP.ExposureMode` 판정

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
