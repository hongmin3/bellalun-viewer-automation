# Bellalun Viewer 기본기능 QA 자동화

의료영상 진단 소프트웨어(디지털 유방촬영 Viewer)의 **QA 체크리스트를 실제 UI로
자동 수행하고 Pass/Fail을 스스로 판정하는** 테스트 자동화 프레임워크입니다.

사람이 손으로 하루씩 돌리던 회귀 시험을, **명령 한 줄로 수행하고 판정 근거까지
남기는** 자동화로 만들었습니다. 최신 전수 회귀는 94.1분이 걸렸습니다.

```bash
python run.py run-regression
```

---

## 0. 온보딩 요약 — 5분 안에 전체 그림

| 무엇 | 한 줄 |
|---|---|
| **목적** | 의료영상 진단 SW의 QA 체크리스트를 **실제 UI로 자동 수행하고 Pass/Fail을 스스로 판정**한다. 사람이 하루씩 돌리던 회귀를 명령 한 줄로 돌리고 판정 근거까지 남긴다 |
| **기준 문서** | `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`. **여기에 없는 TC는 이 저장소의 시험 대상이 아니다** — 지식 폴더의 다른 체크리스트는 번호 매핑이 다르다 |
| **자동화 범위** | 개정본 **37 TC** = 완전자동 **20** / 부분자동 7 / 수동 10 (+ 자동화 보조 4건, 그중 2건은 회귀 제외). 회귀 1회가 수행하는 것은 **27 TC**. 등급·사유·해제 조건의 원본은 `automation_scope.json` 하나뿐이다 |
| **실행 1줄** | `python run.py run-regression` — 그 전에 `python run.py portability-check`로 **`관리자 권한`이 True**인지 먼저 본다(False면 UI 자동화가 전부 막힌다) |
| **필수 조건** | 관리자 권한(High Integrity) · 1920×1080 @100%(96 DPI) · Tesseract-OCR · SQL Server 인스턴스 · XIPL Studio |

**문서 읽는 순서** — 신규 세션·신규 인원 공통.

1. **이 README** (5분) — 무엇을 왜 어떻게 검증하는가.
2. **`AGENTS.md`** — 저장소 작업 규칙. 기준 문서·작업 순서·긴 실행 전 사전 검사·Git 규약.
3. **`NEXT_WORK.md`** — **지금 상태와 다음에 할 일.** 최신 회귀 결과, 남은 FAIL,
   P0/P1/P2, 사용자 판단이 필요한 항목.
4. **`..\지식\[자동화 운영 지침] ...md`** — 영구 구현 규칙과 사고 이력. 상단의
   **"증상 → 원인 → 조치" 빠른 색인**부터 본다.
5. **`NEXT_TASK.md`** — 누적 인수인계(실측 컨트롤 ID, 확정한 제품 동작). 통독하지 말고
   **필요할 때 검색**한다.

> 1~3만 읽으면 "무엇을 하는 저장소이고 지금 무엇이 문제인가"까지 파악됩니다.
> 4~5는 코드를 실제로 고칠 때 엽니다.

---

## 1. 프로젝트 구조

프로젝트 루트는 `...\Bellalun Viewer`이고, **Git 저장소는 그 아래 `auto/` 하나뿐**입니다.
루트의 나머지는 저장소 밖 자산(기준 문서·근거 문서·DB 스냅샷)입니다.

```
Bellalun Viewer\
├─ (운영 상세 문서)          ← 사내 정보가 섞여 저장소 밖에 둔다. tools/render_docs.py 가 관리
├─ Bellalun_Viewer_기본기능_Checklist_개정본.xlsx   ← 시험 대상의 유일한 기준
├─ Baseline\                 회귀 기준 DB 스냅샷 4종(.bak)
├─ 지식\                     판정 근거 원본 — 사양서1/2, Operation·Service Manual,
│                            DICOM Conformance Statement, 영구 지침 3종
├─ ORG\                      사내 선행 자산(참고용. 자동화가 참조하지 않는다)
└─ auto\                     ★ Git 저장소
   ├─ run.py                 CLI · 환경 게이트 · 회귀 사슬 · 리포트 호출
   ├─ core\                  재사용 계층 34개 모듈 (UI·OCR·DB·DICOM·리포트)
   ├─ tests\                 TC 시나리오·판정 29개 모듈 (workflowNN.py = TC 번호)
   ├─ tools\                 자체 검사·운영 도구 11개 + _paths.py
   ├─ automation_scope.json  TC별 등급·사유·커버리지·해제 조건 (원본)
   ├─ traceability.json      사양↔TC 추적성 데이터
   ├─ config.example.json    설정 템플릿 (config.json 은 커밋하지 않는다)
   ├─ AGENTS.md              저장소 작업 규칙
   ├─ NEXT_WORK.md           현재 상태와 다음 할 일
   ├─ NEXT_TASK.md           누적 인수인계 (실측 컨트롤 ID·확정한 제품 동작)
   ├─ Archive\               끝난 기록 (tools/prune_docs.py 가 내려 둔 원문)
   ├─ Reports\               리포트 4종 + 체크리스트 결과 xlsx   ┐
   ├─ Evidence\              단계별 캡처·크롭 (판정 근거 이미지)  │ 전부
   └─ work\ Temp\ Log\ Cache\  런타임 산출물                      ┘ 커밋 제외
```

**왜 프로젝트 루트와 저장소를 나누는가** — 기준 체크리스트·사양서·매뉴얼·DB 스냅샷과
운영 상세 문서에는 제품 내부 구조와 사내 정보가 들어 있고, `auto/`는 GitHub 공개
원격에 push하기 때문입니다. 문서 렌더러(`tools/render_docs.py`)처럼 사내 정보가 없는
스크립트만 저장소 안에서 관리합니다 — 작업 규칙·사전 검사와 함께 리뷰되어야 하기
때문입니다.

### `tools/` — 자체 검사와 운영 도구

`auto/` 바닥에 흩어져 있던 `tools_*.py` 10개를 2026-08-26에 한 폴더로 모으고 접두사를
뗐습니다. `tools/_paths.py`가 `sys.path`와 작업 디렉터리를 저장소 루트로 맞추므로,
어디서 실행하든 결과가 같습니다.

| 도구 | 무엇을 막는가 |
|---|---|
| `tools/check_module_attrs.py` | 모듈 속성 오염·없는 이름 참조 (`'list' object is not callable`) |
| `tools/check_self_attrs.py` | 구간 교체 편집이 지운 `self.` 메서드 (`AttributeError`) |
| `tools/check_cleanup_stop.py` | `finally` 안의 FAIL이 TC 밖으로 새어 리포트를 삼키는 것 |
| `tools/check_regression_names.py` | 다른 분기의 `import`가 만든 `UnboundLocalError` |
| `tools/traceability.py` | 인용·쪽·SRS·모듈·명령·Step 범위를 원문과 대조 |
| `tools/check_docs_sync.py` | 운영 문서 갱신 누락 · HTML 재생성 누락 |
| `tools/report_numbers.py` | 문서에 적을 수치를 리포트·저장소에서 재계산 |
| `tools/prune_docs.py` | 끝난 기록을 `Archive/`로 이관, 문서 읽기 비용 점검 |
| `tools/run_regression.py` | 회귀 Python 바깥에서 비정상 종료 감시 (권장 진입점) |
| `tools/automation_status.py` | 마지막 완료 전체 회귀 경과일 |
| `tools/render_docs.py` | 프로젝트 루트의 운영 상세 문서를 md → html 로 재생성 |

---

## 2. 한눈에 보기

| 항목 | 내용 |
|---|---|
| 대상 | Bellalun Viewer 1.0.12 (Windows 데스크톱 의료영상 SW) |
| 기준 문서 | `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` (시트 `개정 TC`) |
| 규모 | Python **25,508줄** / 모듈 75개 — core 13,074(34) · tests 9,974(29) · `run.py` 990 · `tools/` 1,470(11). 2026-08-26 재실측 |
| 시험 범위 | 개정본 **37개 TC 전수 등록** — 완전자동 **20** / 부분자동 7 / 수동 10 (+ 자동화 보조 4, 그중 2건은 회귀 제외) |
| 최신 전체 회귀 | 2026-08-25 20:44~22:19 — TC 27건 : PASS 20 / FAIL 2 / MANUAL 3 / BLOCKED 2 / SKIP 0 (94.1분)<br>그 안의 검증 271개 : PASS 255 / FAIL 7 / MANUAL 4 / BLOCKED 4 / SKIP 1 |
| 남은 FAIL | `TC_Basic_WorkFlow_14` Step 7 — **제품 결함**(UPS 설정이 Export/Import로 복원되지 않음) / `TC_XIPL_compatibility_03` Step 9 — **제품 결함**(Apply 후 3D 파라미터 기본값 복귀). 둘 다 완화하지 않고 계속 보고합니다 |
| 외부 의존성 | Pillow, pytesseract, openpyxl, pypdf **4개뿐** |
| 추적성 | `traceability.json` + `tools/traceability.py` — 인용한 사양 문구·쪽·SRS ID를 **원문과 매번 대조**하고 사양↔TC 양방향 인덱스를 만듭니다. TC 37건 중 **24건**에 사양 인용 68건, 위반 0 |
| 자체 검사 | `tools/` 도구 11개 + 단위 시험 **71건** |

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
  → XIPL 연동 7종(2D/3D 영상처리 파라미터 왕복 검증)
  → 리포트 4종(HTML·CSV·JSON·TXT) + 체크리스트 xlsx 결과 기록
```

---

## 3. 왜 만들었나 — 해결한 문제

이 제품의 QA에는 자동화를 어렵게 만드는 조건이 겹쳐 있었습니다.

| 문제 | 이 프로젝트의 해결 |
|---|---|
| 버튼 대부분이 **커스텀 렌더링**(`AfxWnd140u`)이라 표준 UI 자동화 도구가 인식 못 함 | `ctypes`로 Win32를 직접 다루고 물리 마우스·키보드를 제어 |
| 화면 값이 **텍스트가 아니라 그림**으로 그려져 읽을 수 없음 | 창 기준 상대 좌표로 크롭 → Tesseract OCR, 다중 psm 다수결로 오독 방지 |
| 같은 컨트롤 ID가 화면마다 **다른 뜻** (`501`이 `Selected`이기도 `Yes`이기도 함) | 누르기 전에 **버튼 문구를 OCR로 읽고**, 후보가 하나일 때만 누름 |
| "버튼 눌렀다"만으로는 기능 동작을 증명할 수 없음 | DB · 제품 로그 · 생성 파일 · UI 재진입 · 화면 OCR을 **교차 검증** |
| 시험마다 데이터가 쌓여 결과가 달라짐 | DB 기준 스냅샷 복원 + 시험 픽스처 자동 정리로 **반복 가능**하게 |
| 실제 X-ray 노출은 자동으로 쏠 수 없음 | Demo 모드(F8 가상 촬영)로 대체하고 **안전 게이트**로 실촬영을 차단 |

---

## 4. 어떻게 판정하는가

### 판정 기준은 화면이 아니라 문서에서 가져온다

TC가 **무엇을 하는지**는 기준 체크리스트에서, **왜 그것이 정상인지**는 제품 사양서·
Operation Manual·Service Manual·DICOM Conformance Statement에서 확인합니다. 판정의
`note`에 인용한 문서와 **쪽 번호·SRS ID**를 남겨, 리포트만 보고도 기준의 출처를
감사할 수 있게 했습니다.

사양서가 `.pdf`라 grep이 되지 않아 근거를 대기 어려웠습니다. `core/specs.py`가
`pypdf`로 문구를 찾아 **쪽 번호와 SRS ID까지** 돌려줍니다.

```python
specs.cite(ctx, r"3D Viewposition은 촬영 모드")
# 근거: 사양서1 186쪽 SRS 03-10-110 — "3D Viewposition은 촬영 모드
#  (Narrow / Wide)에 대해 각각 Parameter를 설정한 다. ○ 2D License의 경우
#  3D-N / 3D-W Preset 설"      ← 추출 텍스트 그대로. 손으로 다듬지 않는다
```

**화면을 보고 합격 기준을 역산하면 결함을 정상으로 인증합니다.** 실제로 두 번
겪었습니다 — Window Level은 매뉴얼이 *"W1/W2 값의 증가·감소"* 로 정의하는데 초기
구현은 "화면 픽셀이 몇 % 바뀌었나"라는 대리 지표를 써서 **정상 동작을 FAIL로
뒤집었고**, Q.C 파라미터는 형식을 확인하지 않아 **깨진 파일이 PASS처럼 보였습니다.**

### 추적성을 데이터로 고정한다

추적성 표를 문서에 손으로 적으면 사양서가 개정될 때 **문서만 낡아 "근거가 있다"고
거짓말합니다.** 그래서 데이터는 `traceability.json` 한 곳에만 두고, 도구가 매번
원문과 대조합니다.

```bash
python tools/traceability.py --reverse
# TC 37건 / 인용 있는 TC 24건 / 인용 68건
# === 사양 → TC ===
#   사양서1 SRS 03-10-110   TC_Basic_WorkFlow_02(Step 1),
#                           TC_XIPL_compatibility_04(Step 1,6,7,8),
#                           TC_XIPL_compatibility_07(Step 1,2,5,6,7,8)
# 이상 없음 — 모든 인용이 원문과 일치하고 모듈·명령·Step 범위도 맞다.
```

검사하는 것: TC ID가 기준 체크리스트에 실존하는가 / 빠진 TC가 없는가 / 등급이
`automation_scope.json`과 일치하는가 / 구현 파일과 함수가 있는가 / `run.py`에 그
명령이 있는가 / **인용 문구가 문서 원문에 실제로 있는가**(공백 무시) / 쪽·SRS가
실측값과 같은가 / Step 번호가 체크리스트 범위 안인가.

위조한 쪽 번호·SRS·없는 인용·범위 밖 Step·없는 함수·없는 명령·등급 불일치 7건을
주입해 **전부 검출되는 것을 확인**했습니다.

### 증거 5종 — 하나에만 의존하지 않는다

1. **DB 조회** — 검사·영상 구조, UID 유일성, 설정 저장값
2. **제품 로그** — 적용된 파라미터명·수치 (줄마다의 타임스탬프로 시점 필터링)
3. **생성 파일** — 영상 `.img`의 `<ReconParam>`, Export 산출물, 해시·크기
4. **UI 재진입** — 저장 후 화면을 다시 열어 표시값 재확인
5. **화면 캡처 + OCR** — 커스텀 렌더링 값 판독, 증거 이미지 보존

DB에 없는 것도 있습니다. **적용된 3D Recon 파라미터 이름은 `DATA` 데이터베이스 어느
컬럼에도 없습니다**(컬럼 전수 조회로 확인). 사양서1 277쪽 SRS 03-50-230이 저장 위치를
`img` 파일로 명시하고 있어, `core/imginfo.py`가 `.img` 꼬리의 UTF-16LE XML을 읽어
`XtpName`/`EgpName`을 화면 표시와 교차 확인합니다. 3D Raw가 700MB를 넘으므로 꼬리만
읽습니다.

---

## 5. 설계 원칙

대부분 실패를 겪고 나서 규칙으로 승격시킨 것입니다. 여섯 개만 옮깁니다.

**① DB는 조회 전용 — 상태 변경은 반드시 UI로.** `core/db.py`에는 `SELECT`만 있고
저장소 전체에 `INSERT`/`UPDATE`/`DELETE`가 한 줄도 없습니다. DB를 직접 고치면
"제품 UI가 그 동작을 실제로 했다"는 판정 근거가 무너집니다.

**② 클릭 성공을 PASS로 쓰지 않는다.** DB / 로그 / 생성 파일 / UI 재진입 / 화면 OCR
중 최소 하나로 교차 확인합니다.

**③ 조작 전·후 모두 상태를 확인한다.** 클릭만 보내고 결과를 확인하지 않는 코드는
단독 실행에서 통과하고 **회귀에서만** 깨집니다. 그런 결함 5건(메뉴 토글, 콤보 스크롤,
저장 팝업, 카드 배치, 툴바 펼침)이 모두 같은 형태였습니다. 여섯 번째는 거울상 —
조작 *전*에 그 화면이 존재하는지 확인하지 않은 것이었습니다.

**④ 환경 오염을 제품 결함처럼 보고하지 않는다.** 이전 실행이 남긴 데이터로 수행
불가한 경우는 `FAIL`이 아니라 무엇을 정리해야 하는지 알려주는 `MANUAL`로 분리합니다.

**⑤ 고정 sleep 대신 상태 기반 대기.** 컨트롤 출현·팝업·로그 기록·DB 행 도착·파일
생성 등 **실제 증거**가 나타날 때까지 상한을 두고 polling합니다. 조건 대기는
**부분 도착을 성공으로 보지 않습니다** — 3D 촬영은 Raw/Recon/Synthetic 세 건이 다
들어와야 완료입니다(단위 시험으로 고정).

**⑥ 이식 가능한 선택자만.** Win32 컨트롤 ID, 화면 텍스트, OCR, **창 기준 상대 좌표**를
씁니다. 저장소에 절대 데스크톱 좌표 클릭은 없습니다.

---

## 6. 기술 선택

외부 의존성을 **4개**로 억제했습니다. 새 QA PC에서 `pip install -r requirements.txt`
한 번으로 준비가 끝납니다.

| 필요 기능 | 흔한 선택 | 이 프로젝트 | 이유 |
|---|---|---|---|
| Win32 UI 제어 | pywin32 | **`ctypes`** 직접 호출 | 설치 부담 제거, QA PC 이식성 |
| SQL Server 접근 | pyodbc | **PowerShell + .NET `SqlClient`** | Windows 기본 제공, 드라이버 설치 불필요 |
| DICOM 파싱 | pydicom | **자체 `dicomlite.py`** | 필요한 태그만 읽으면 충분 |
| 사양서 PDF 읽기 | PyMuPDF, pdfplumber | **`pypdf`** | MIT, 순수 Python. PyMuPDF는 AGPL/상용 이중 라이선스라 의료기기 QA 저장소에 넣기 부담 |
| 제품 `.img` 파싱 | (없음) | **자체 `imginfo.py`** | 제품 고유 컨테이너. 꼬리 XML만 읽어 700MB도 seek 한 번 |
| md → html 문서 | markdown, mkdocs | **자체 `tools/render_docs.py`** | QA PC에 변환기를 새로 깔지 않는다 |

---

## 7. 실제로 잡아낸 것

대표 네 건입니다.

**제품 결함 — `TC_XIPL_compatibility_03` Step 9.** 3D Post Reconstruction의 Apply 후
재진입하면 값이 기본값으로 되돌아갑니다(`Not use`→`Use`, 14→10). 사양서1 277쪽
SRS 03-50-230이 *"Apply를 누르게 되면 해당 img 파일에 영상 조정 파라미터 값들이
저장된다"* 고 정하고 있어 **완화하지 않고 계속 FAIL로 보고**합니다.

**기준 문서를 잘못 골라 정상 구현을 결함으로 판정한 일.** 파일명이 비슷한 다른
체크리스트를 기준으로 착각해 정상 구현된 `WF_02`를 "범위 불일치"로 강등했습니다.
같은 형태의 TC ID에 다른 내용이 붙어 있었고, 어긋난 것은 하나가 아니라 10개였습니다.
그래서 기준 문서를 `AGENTS.md` 0절에 못박고 혼동 주의를 함께 적었습니다.

**세 번 만에 잡은 것 — 회귀에서만 실패하던 TC.** `XIPL_04`가 3회 연속 같은 지점에서
실패했습니다. 원인은 **저장 확인 팝업**이었고(직전 TC가 파라미터를 바꿔 "변경사항"이
생김), 아무도 답하지 않아 모달이 이후 모든 클릭을 삼켰습니다. 두 번 잘못 짚은 뒤
**세 번째 추측 대신 실패 시점의 화면 랜드마크와 대화상자 문구를 증거로 남기게 했고**
그것이 팝업을 드러냈습니다.

**자동 치환이 모듈 함수를 리스트로 덮어쓴 일.** `py_compile`과 `ast` 미정의 이름 검사
모두 통과했지만 회귀에서만 죽었습니다 — 둘 다 "존재하는 이름에 대입하는 것"은 잡지
못합니다. 그래서 `tools/check_module_attrs.py`를 만들었습니다. **고친 뒤의 검증도 한
번 잘못했습니다** — 두 TC를 따로 돌리면 별도 프로세스라 오염 경로를 지나가지 않습니다.

---

## 8. AI(Claude Code)를 활용한 개발 방식

이 저장소는 AI 세션을 여러 번 이어 만들었습니다. 매 세션 같은 품질로 일하게 만드는
장치를 코드와 문서에 심었습니다.

- **`AGENTS.md`가 영구 규칙을 담습니다** — 기준 문서가 무엇인지, 작업 순서,
  검증 기준, Git 규약. 세션이 바뀌어도 처음 읽는 문서가 같습니다.
- **실패를 규칙으로 승격시킵니다.** 같은 실수를 두 번 하지 않도록, 겪은 사고를
  주석과 문서에 **경위까지** 적습니다(위 §7).
- **AI 결과물을 그대로 믿지 않습니다.** `tools/`의 정적 검사 5종과 단위 시험 71건이
  긴 실행 전에 돌아갑니다. `py_compile`이 못 잡는 다섯 가지(누락 import, 다른 분기의
  import, 모듈 속성 오염, 구간 교체가 지운 메서드, `finally` 안의 FAIL 누출)를
  각각 다른 검사가 막습니다.
- **사람이 판단해야 하는 지점은 묻고 설계합니다.** 파괴적 동작, 판정 기준이 문서에
  없는 항목, 실물 장비가 필요한 항목은 추측으로 자동화하지 않고 `MANUAL`/`SKIP`으로
  남기고 **해제 조건**을 적습니다.
- **수치는 실측합니다.** `tools/report_numbers.py`가 문서에 적을 코드 규모·등급
  건수·회귀 판정을 리포트와 저장소에서 다시 계산합니다.
- **문서에도 읽는 비용이 있습니다.** 끝난 기록은 지우지 않고 `tools/prune_docs.py`가
  `Archive/`로 내립니다 — 검색하면 그대로 나오고, 줄어드는 것은 매 세션 읽어야 하는
  분량뿐입니다.

---

## 9. 실행

```bash
python -m pip install -r requirements.txt
copy config.example.json config.json     # 계정·경로·서버 주소 입력
python run.py portability-check          # 해상도·DPI·권한·필수 경로 사전 점검

python run.py list                       # 개정본 37개 TC + 보조 4개의 자동화 수준
python run.py run-regression             # 전체 회귀 (기준 복원부터 리포트까지)
python run.py run-xipl-07                # 개별 TC (전수는 python run.py --help)
python tools/run_regression.py           # 외부 감시가 붙은 전체 회귀(권장, run_all.cmd가 사용)
check_automation_status.cmd 7            # 마지막 완료 전체 회귀가 7일 넘었는지 알림
```

`tools/run_regression.py`는 회귀 Python 바깥에서 기다리므로 Python 자체가 죽어
리포트를 못 남긴 경우도 감지합니다. TC 수행 중 Viewer가 사라지면 WER 덤프를 확인해
실제 크래시와 원인 불명 종료를 구분하고, 다음 TC를 위해 재기동합니다. 완료·비정상
종료는 Windows 알림 영역에도 표시됩니다.

**긴 실행 전 사전 검사**

```bash
python -m py_compile <바꾼 파일>
python tools/check_module_attrs.py
python tools/check_self_attrs.py
python tools/check_cleanup_stop.py
python tools/check_regression_names.py
python tools/traceability.py
python tools/check_docs_sync.py
python -m unittest discover -s tests -p "test_*.py"
```

**필수 조건** — 충족하지 않으면 자동화가 시작 시점에 명확히 FAIL시킵니다.

- **관리자 권한**(High Integrity). `VIEWER.exe`가 `requireAdministrator`라 자동화가
  일반 권한이면 Windows UIPI가 입력 주입을 막는데, 이때 **화면 캡처는 되고 클릭만
  조용히 실패**해 엉뚱한 증상으로 보입니다.
- **1920×1080 @ 100%(96 DPI)**
- Tesseract-OCR, SQL Server 인스턴스, XIPL Studio (경로는 `config.json`)

실행 중에는 **마우스·키보드를 점유합니다.** 사람이 끼어들면 판정이 틀립니다.

---

## 10. 문서

| 문서 | 무엇 |
|---|---|
| `AGENTS.md` | 저장소 작업 규칙 (기준 문서 · 작업 순서 · 검증 · Git 규약) |
| `NEXT_WORK.md` | 현재 상태, 이번 변경, 남은 문제, P0/P1/P2, 다음 세션용 프롬프트 |
| `NEXT_TASK.md` | 누적 인수인계 기록 (실측 컨트롤 ID · 확정한 제품 동작 · 판정 기준) |
| `automation_scope.json` | TC별 자동화 등급·사유·커버리지 분류·**못 한 지점과 해제 조건** |
| `traceability.json` | 사양↔TC 추적성 데이터 (`tools/traceability.py`가 검사) |
| `Archive/` | **끝난 기록.** `tools/prune_docs.py`가 내려 둔 원문 — 새 세션은 읽지 않아도 되고, 과거 경위를 되짚을 때만 검색합니다 |
| `PORTABILITY_AUDIT.md` | 다른 QA PC 이식 점검 기록 |
| `..\지식\` | 판정 근거 원본 — 사양서1/2, Operation/Service Manual, DICOM Conformance Statement, 영구 지침 3종 |
