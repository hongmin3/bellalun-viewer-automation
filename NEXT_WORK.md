# 다음 작업 (2026-08-24 기준)

> 이 문서는 **현재 상태와 다음에 할 일**만 담는다. 누적 기록(실측 컨트롤 ID, 확정한
> 제품 동작, 과거 판정 기준)은 `NEXT_TASK.md`에, 영구 규칙은 `AGENTS.md`와
> `..\지식\` 지침에 있다.

---

## 1. 현재 상태

| 항목 | 값 | 근거 |
|---|---|---|
| 기준 문서 | `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC` — **TC 37건** | 2026-08-24 `TC_XIPL_compatibility_07` 추가 |
| 자동화 범위 | 완전자동 **21** / 부분자동 6 / 수동 10 (+ 보조 4) | `python run.py list` |
| 코드 규모 | Python 21,388줄 / 모듈 62개 (core 32 · tests 25 · `run.py` · 도구 4) | 2026-08-24 실측 |
| 추적성 | TC 37건 중 18건에 사양 인용 43건 연결, 위반 0 | `python tools_traceability.py` |
| 단위 시험 | 14건 전부 통과 | `python -m unittest discover -s tests -p "test_*.py"` |
| 정적 검사 | 모듈 속성 57개 대상 이상 없음 / 회귀 블록 이름 결속 이상 없음 | `tools_check_module_attrs.py`, `tools_check_regression_names.py` |
| **최신 전체 회귀** | **2026-08-21 16:40 (19차)** — TC 26건: PASS 20 / FAIL 1 / MANUAL 5, 검증 251개: PASS 241 / FAIL 1 / MANUAL 7 / SKIP 2, 111.3분 | `Reports/Result_20260821_164016.json` |
| 남은 제품 FAIL | `TC_XIPL_compatibility_03` Step 9 (Apply 후 3D 파라미터 기본값 복귀) | 완화하지 않는다 |

### 2026-08-24 회차는 전체 회귀를 실행하지 못했다

이 세션의 Python 프로세스가 **관리자 권한(High Integrity)이 아니다.** `VIEWER.exe`가
`requireAdministrator`라 Medium 프로세스에서는 Windows UIPI가 입력 주입을 막고,
`run.py`의 환경 게이트가 UI 자동화를 시작 시점에 차단한다.

```
python run.py portability-check      (2026-08-24 08:25 실측)
  [PASS] Primary display 1920x1080
  [PASS] Windows UI DPI 100%
  [FAIL] 관리자 권한: False          ← 이것 때문에 UI 자동화 전부 차단
  [PASS] 필수 경로 [Viewer] / [XIPL Studio] / [XIPL Parameter] / [Tesseract OCR]
```

그래서 이번 변경은 **정적 검사·단위 시험·DB/파일 기반 검증까지만** 확인했다.
`TC_XIPL_compatibility_07`의 UI 조작 경로는 **한 번도 실행되지 않았다** —
"구현 완료"이지 "검증 완료"가 아니다. 아래 P0가 그것이다.

---

## 2. 이번 변경 (2026-08-24)

### 2.1 신규 TC — `TC_XIPL_compatibility_07`

**개정본 `개정 TC` 시트 33행에 추가했다** (`TC_XIPL_compatibility_06` 바로 뒤).
백업: `..\Baseline\Checklist_개정본_20260824_XIPL07추가전.xlsx`.

- Title: **촬영 모드별 3D Default Recon Parameter 적용**, Func_01 `3D Default Parameter변경`
- 9단계. 열 구조·문체·서식(Carlito 11 / wrap / vertical=top)·행 높이 모두 형제 행과
  동일하게 맞췄고, 저장 후 **다른 셀이 하나도 바뀌지 않았음을 전수 대조로 확인**했다
  (수식 0건, 병합 0건, 열 폭·헤더 동일).

**왜 `_04`와 중복이 아닌가.** `_04`는 **Preset별**로 2D 파라미터가 갈리는지 보고,
`_07`은 **촬영 모드별**(Narrow/Wide)로 3D Recon 파라미터가 갈리는지 본다. 사양이
3D에만 요구하는 축이 모드이고(사양서1 186쪽 SRS 03-10-110 — *"3D Viewposition은 촬영
모드 (Narrow / Wide)에 따라 각각 Reconstruction Parameter를 설정한다.(.xtp)"*),
2D에는 이 축이 아예 없다.

**사양 근거** (전부 `traceability.json`에 등록하고 원문 대조로 검증)

| 문서 | 확인한 것 |
|---|---|
| 사양서1 186쪽 SRS 03-10-110 | 모드별 각각 Recon Parameter 설정 / 기본 파라미터는 `Setting > Procedure > General` / Preset 등록 여부에 따른 우선순위 / 2D License면 항목 미표시 |
| 사양서1 196쪽 SRS 03-30-20 | 설정 가능한 3D Viewposition 11종(`CC, MLO, LM, SIO, ML, LMO, ISO, XCCL, XCCM, AT, TAN`), *"FB 및 CV는 촬영 불가"* |
| 사양서1 277·278쪽 SRS 03-50-230 | *"영상을 획득 시 설정한 xtp 파일을 Combo 박스에 자동으로 선택된다"*, *"Apply를 누르게 되면 해당 img 파일에 영상 조정 파라미터 값들이 저장된다"*, Post Reconstruction↔XTP 매핑표 |
| Service Manual `Procedure 그룹 > General` | `Reconstruction parameter for 3D-N/3D-W`의 정의, Default 적용 조건, **Tomo 미지원·2D License면 항목 미표시** |
| Service Manual `Preset 메뉴` | 목록 열 `Name / Alias / XIPL Param(2D) / Recon Param(3D)`, `2D / 3D-N / 3D-W 각각 40개` |

**실측으로 확정한 것** (사양 대조에 쓴 근거)

- `PROCEDURE.PROCEDURE_COMMON`에 `DefaultImgProcess`(2D) / `DefaultReconNarrow`(3D-N) /
  `DefaultReconWide`(3D-W) 세 열이 있다. 모드별로 나뉜다는 사양이 스키마에 그대로 있다.
- `VIEW_POSITION_PRESET.Type` `0`=2D / `1`=3D-N / `2`=3D-W. **Type 1·2의 Positioning이
  각각 정확히 11종이고 사양서1 196쪽의 11종과 일치**하며 `FB`(10)·`CV`(12)는 없다.
  이것이 Step 3의 판정 근거다(화면 OCR보다 강하다).
- **적용된 3D Recon 파라미터 이름은 `DATA` 데이터베이스에 없다** —
  `INFORMATION_SCHEMA.COLUMNS` 전수 조회로 확인. 그래서 `.img` 파일을 읽는다.
- 제품 `.img`는 꼬리에 **UTF-16LE `<INFORMATION>` XML**을 담는다. 실측 예:
  `<ReconParam EgpName="narrow_standard.egp" EapName="common_standard.eap"
  XtpName="TEST_3D_FLOW.xtp" PostContrast="14" .../>`.
  2D 영상은 같은 요소를 갖지만 이름 3개가 **모두 빈 문자열**이라 3D 전용 근거다.

**자동화** — `tests/xipl_flows.py::compatibility_07`, 명령 `python run.py run-xipl-07`
(`run_xipl`에 포함되어 회귀에도 자동으로 들어간다). 판정 구조:

| Step | 판정 근거 |
|---|---|
| 1·2 | 콤보 `2543`/`2544`로 모드별 Default 변경 → `PROCEDURE_COMMON` 두 열 대조. **한쪽을 바꿔도 다른 쪽이 유지되는지**까지 본다(모드 독립) |
| 3 | Preset 페이지 캡처 OCR로 `3D-N`/`3D-W` 표시 확인 + `VIEW_POSITION_PRESET × VIEW_POSITION_POSITIONING` 전수 대조(사양 11종 일치, FB/CV 부재) |
| 4 | `DATA_XIPL_3D_01` 검사 생성 → `STUDY` 조회 |
| 5·6 | 모드별 View Position 등록 + Demo(F8) → `INSTANCE_GROUP.Type=1` / `ExposureMode` 1↔2, `InstanceType 1/2/3` 각 1건, UID 유일. **두 모드의 ExposureMode가 서로 다른지**까지 본다 |
| 7 | Post Reconstruction 콤보 표시값(사양서1 277쪽 — 획득 시 xtp 자동 선택) |
| 8 | `.img`의 `<ReconParam>` — `XtpName`이 **그 모드의 Preset 설정값 또는 그 모드의 General Default 중 하나**인지(사양이 정한 두 정상 경로), `EgpName`이 모드별로 서로 다른지, **화면 표시와 파일 기록이 일치**하는지 |
| 9 | 시험 전 값으로 UI 원복 → DB 재확인. 예외로 끝나도 `finally`에서 한 번 더 시도하고 **결과를 반드시 판정으로 남긴다** |

**SKIP 기준** — `Setting > Procedure > General`에 Recon Parameter 콤보가 **둘 다
없으면** Tomo 미지원 또는 2D 전용 License다(Service Manual). 그때만 TC 전체를 SKIP하고
근거 문구를 함께 남긴다. **하나만 없으면 FAIL** — 미지원이면 두 항목이 함께 사라지므로
"3D 미지원"으로 설명되지 않는다. 판단은 **실제로 화면을 열어 확인한 그 단계에서** 한다
(`AGENTS.md` 7절). GPU 미탑재는 이 TC의 SKIP 사유가 **아니다** — Reconstruction을 다시
돌리지 않고 촬영 결과만 읽으므로, 촬영이 성립하지 않으면 정직하게 FAIL해야 한다.

### 2.2 신규 모듈·도구

| 파일 | 용도 | 검증 |
|---|---|---|
| `core/imginfo.py` | 제품 `.img` 꼬리의 `<INFORMATION>` XML 판독. `read_information` / `sections` / `recon_param` / `study_image_dirs` / `instance_image_path` | 실제 제품 파일 4개(2D 1 + 3D 3)로 확인 + 단위 시험 7건 |
| `tools_traceability.py` | `traceability.json`을 원문·저장소와 대조하고 사양↔TC 양방향 인덱스 출력 | 위조 7건 주입 → 전부 검출 확인 |
| `traceability.json` | 사양↔TC 추적성 데이터 (쪽·SRS는 문서 검색으로 실측한 값) | 위반 0 |
| `tests/test_imginfo_and_waits.py` | `imginfo`와 조건 대기 단위 시험 12건 | 통과 |
| `tools_build_detail_html.py` | `..\프로젝트 상세.html` 생성기. 표·수치를 `automation_scope.json`/`traceability.json`/`run.py`/리포트 JSON 에서 만든다 | 생성·렌더 확인 |
| `run.py probe-preset3d` | `Setting > Procedure > Preset`의 3D 목록 컨트롤을 **조회 전용**으로 실측(TC 아님). 전후 DB 스냅샷 대조 포함 | **미실행** (권한 없음) |

### 2.3 성능·독립성·증거 개선

- **조건 기반 촬영 대기** — `core/viewer_processing.wait_new_group()`. F8 뒤에
  `settle`초를 무조건 자는 대신, 새 `INSTANCE_GROUP`과 그 안의 `InstanceType`이
  **다 들어올 때까지** DB를 polling한다. `_07`은 `settle=0` + 이 대기를 쓴다.
  **부분 도착을 성공으로 보지 않는다**(Raw만 들어오고 Recon/Syn이 없으면 타임아웃으로
  기록) — 단위 시험으로 고정했다.
- **죽은 blind-sleep 함수 삭제** — `viewer_processing.preview_and_apply`는
  Preview/Apply 뒤에 무조건 자는 함수였고(2D 20/30초, 3D 35/75초) 저장소·문서·설정
  어디에서도 참조되지 않았다. 지운 이유는 죽은 코드라서만이 아니다 — 남겨 두면 다음
  사람이 "이미 있는 헬퍼"로 다시 써서 조건 대기가 조용히 되돌아간다.
- **죽은 설정 키 수정** — `config.example.json`의 `preview_3d_wait`/`apply_3d_wait`는
  **아무도 읽지 않았다**(조정해도 아무 일이 없었다). 코드가 실제로 읽는
  `post_recon_timeout` / `preview_3d_timeout` / `apply_3d_timeout` /
  `acquire_3d_timeout`으로 고치고, "이 값들은 조건 대기의 **상한**"이라는 주석을 넣었다.
- **상태 원복 강화** — `_07`은 시험 전 `PROCEDURE_COMMON` 값을 먼저 기록하고 Step 9에서
  UI로 되돌린 뒤 DB로 확인한다. 예외로 끝나도 `finally`가 한 번 더 시도하고 그 결과를
  판정으로 남긴다.
- **실패 증거** — `_07`의 예외 경로가 `flows._screen_context(ui)`로 실패 시점 화면
  랜드마크·대화상자 문구를 `note`에 싣는다. 단계마다 캡처를 `Evidence`에 붙인다.

### 2.4 발견해 고친 결함

1. **저장소의 유일한 단위 시험이 실패 상태로 방치돼 있었다.** HTML 리포트에서
   `소요시간`(붙여쓰기)을 찾는데 리포트는 그 전부터 `소요 시간 분해`(띄어쓰기)를 쓰고
   있었다. 아무도 돌리지 않았다. 문구를 그대로 박는 대신 HTML이 실제로 내는 제목을
   확인하도록 고치고, 사전 검사 목록에 `python -m unittest discover`를 넣었다.
2. **죽은 설정 키**(위 2.3) — 사용자가 3D 대기를 조정하려 해도 반영되지 않는 상태였다.

### 2.5 용어 통일 — `증적` → `증거`

`auto/`(생성물 제외)와 `지식/`의 코드·주석·문서·리포트 출력에서 **54회 치환**
(파일 25개). 영문 식별자(`Evidence/` 폴더, `evidence_root` 변수)는 호환성 때문에
그대로 뒀다 — 치환 대상이 한국어 단어 하나뿐이라 자동으로 보존됐다.

사용자에게 보이는 문구도 바뀌었다: 리포트 HTML `<h3>증거 (스크린샷·파일)</h3>`,
TXT `[증거]`, 체크리스트 결과 xlsx 열 헤더 `증거`, 리포트 환경 표 `증거 폴더`.
기준 체크리스트 xlsx의 Test Data 열 20셀(`증적: Evidence\...` → `증거: Evidence\...`)도
함께 통일했다. **실제 리포트를 생성해 `증적` 0건 / `증거` 표시를 확인했다.**

**치환이 만든 조사 오류를 diff 눈으로 보고 잡았다.** `증적`은 자음으로 끝나고
`증거`는 모음으로 끝나므로 조사가 달라진다 — `증적을/은/으로/이/과` →
`증거를/는/로/가/와`. 일괄 치환 직후에는 `증거을`·`증거으로`가 30여 곳 생겼고,
`git diff -U0` 을 눈으로 훑다가 발견해 파일 16개에서 고쳤다. `AGENTS.md` 8절
"자동 치환으로 코드를 옮기면 diff 를 눈으로 본다"의 또 다른 사례다. `증거` 뒤 한 글자
분포를 전수 집계해 잘못된 조사 0건을 확인했다(로 22 / 를 9 / 가 5 / 는 4 / 와 4 / 에 1).

**재검색 결과**: `auto/` · `지식/`의 소스·문서에 `증적` 잔존 **0건**. 남은 것은
`auto/work/reg_wf01.stdout.log` 1건뿐이고 이것은 **과거 실행이 남긴 런타임 로그**다
(`.gitignore` 대상, 소스 아님). 프로젝트 루트의 `인수인계_2026-08-*.md`는 **날짜가
박힌 과거 세션 기록**이라 소급 수정하지 않았다(Git 추적 대상도 아니다).

### 2.6 문서

| 문서 | 변경 |
|---|---|
| `README.md` | **1,286줄 → 257줄**로 축약. 포트폴리오 요약(무엇을 어떻게 검증하는가)만 남기고 운영 상세는 아래 HTML로 옮겼다. 최신 회귀 **1건만** 기록 |
| `..\프로젝트 상세.html` | **신규.** Quick Start(실제 명령·환경 요구조건·설정 절·시험 데이터·로그/증거/리포트 위치·실패 확인 순서·사전 검사) + 아키텍처 + 설계 원칙 + 기술 선택 + **명령 전수**(`run.py` 소스에서 생성) + 리포트 구성 + TC 추가 절차 + 추적성 + **자동화 범위 전수표**(`automation_scope.json`에서 생성) + 회귀 실적 + 문제 해결 + 제한사항 + 결함·교훈 전체 + 참고 문서 |
| `automation_scope.json` | `TC_XIPL_compatibility_07` 추가(FULL) + `coverage.gap`/`unblock` |
| `traceability.json` | 신규 |
| `NEXT_TASK.md` | 이번 회차 절 추가 |
| `..\지식\[자동화 구현 현황]` | TC 37건 기준으로 갱신 |
| `AGENTS.md` | 사전 검사에 `tools_traceability.py`·단위 시험 추가, 용어 통일 |

**`AUTOMATION_GUIDELINES.md`는 만들지 않았다.** `..\지식\[자동화 운영 지침] Bellalun
Viewer auto 저장소 구현 규칙.md`가 이미 같은 역할이고, 두 곳에 규칙을 두면 갈라진다.
그 문서를 갱신했다.

---

## 3. 남은 문제

| # | 문제 | 상태 |
|---|---|---|
| 1 | **`TC_XIPL_compatibility_07`의 UI 경로가 한 번도 실행되지 않았다** | P0 — 권한 있는 세션에서 확인 필요 |
| 2 | `Setting > Procedure > Preset`의 **3D-N/3D-W 목록·추가·삭제 컨트롤 ID 미실측** (2D만 `2554`/`2548`/`2549` 확정). 그래서 `_07`은 3D Preset 행을 만들거나 편집하지 않는다 | P1 — `run.py probe-preset3d`로 실측하면 해제 |
| 3 | Service Manual의 *"Preset에 **새로 추가하는** View Position은 Default로 설정한 파라미터를 적용한다"* 경로를 `_07`이 판정하지 않는다 | P1 — #2가 해제되면 가능 |
| 4 | `TC_XIPL_compatibility_04`가 `PROCEDURE_COMMON.DefaultImgProcess`를 `TEST_2D_A_M.pim`으로 **남긴 채 끝난다**(현재 DB 실측값이 그렇다). 회귀는 시작 시 스냅샷 복원으로 지워지지만 단독 실행은 오염이 남는다 | P1 — `_07`처럼 원복을 넣어야 하지만 **검증 없이 정상 동작 TC를 건드리지 않았다** |
| 5 | `flows.demo_acquire_step(settle=14)`의 고정 대기가 `WF_01`/`WF_02`/`run-sys3d`에 그대로 남아 있다 | P1 — `_07`에 쓴 `wait_new_group` 레시피로 바꿀 수 있으나 회귀 검증이 필요 |
| 6 | `flows.close_examine`의 no-dialog 경로에 `time.sleep(wait)`가 남아 있다 | P2 — 상태 신호 후보 확인 필요 |
| 7 | 추적성 인용이 없는 TC 19건(`pending_reason`에 사유 기록) | P2 |
| 8 | Dose SR(RDSR) 전송 검증 — Demo(F8)에서는 RDSR이 생성되지 않는다(전제 미충족, 제품 결함 아님) | P2 — `NEXT_TASK.md` 고도화 대기 1번 |
| 9 | `tests/settings.py`의 과거 pre/post 판정부가 실행 경로에 없다. `core/tc_modules.py`가 `Install_07`에서 참조하므로 지우지 않았다 | P2 — 참조 확실히 정리한 뒤에만 |

---

## 4. 우선순위

### P0 — 권한 있는 세션에서 즉시

1. **`TC_XIPL_compatibility_07` 단독 실행 검증**
   ```bash
   python run.py portability-check          # 관리자 권한 True 확인이 먼저다
   python run.py reset-environment          # 회귀 시작 상태
   python run.py run-xipl-07
   ```
   확인할 것:
   - Step 1·2에서 콤보 `2543`/`2544`가 **보이는지**(안 보이면 SKIP이 맞다)
   - `TEST_3D_NARROW.xtp` / `TEST_3D_WIDE.xtp`를 **OCR이 서로 구분해 골랐는지**
     (DB 값이 반대면 오독이다 — 판정이 잡아낸다)
   - Step 5·6에서 F8이 **의도한 3D Step을 촬영했는지**(`ExposureMode` 1↔2로 확정)
   - Step 8의 `EgpName`이 3D-W에서 **무엇으로 나오는지** — `wide_standard.egp`로
     추정되지만 **실측하지 않았다.** 확인되면 `core/imginfo.py` 주석과
     `NEXT_TASK.md`에 실측값으로 적을 것
   - Step 9 원복 후 `DefaultReconNarrow`/`DefaultReconWide`가 `DBT_Standard_Default.xtp`
     로 돌아왔는지
2. **전체 회귀 1회**
   ```bash
   python tools_check_module_attrs.py && python tools_check_regression_names.py
   python tools_traceability.py
   python -m unittest discover -s tests -p "test_*.py"
   python run.py run-regression
   ```
   기록할 것: TC/PASS/FAIL/SKIP/MANUAL, 소요 시간, 특이사항, Report/Log/증거 경로,
   Cleanup 결과. **실행하지 않은 것을 성공으로 적지 않는다.**

### P1

3. `python run.py probe-preset3d` — 3D-N/3D-W Preset 목록 컨트롤 실측. 결과를
   `core/flows.py`에 `PRESET_3DN_*`/`PRESET_3DW_*`로 넣고 `NEXT_TASK.md`에 기록.
4. #3 해제 후 `_07`에 **"새 3D Preset이 그 시점 Default를 물려받는가"** 판정 추가
   (`_04`의 `_add_preset_2d_pair`/`_alias_preset_row`와 같은 방식, 정리도 UI 삭제로).
5. `TC_XIPL_compatibility_04`에 `DefaultImgProcess` 원복 추가 — 반드시
   `reset-environment` → `run-xipl-04` → DB 확인까지 지나간 뒤에만 커밋.
6. `flows.demo_acquire_step`의 고정 대기를 `wait_new_group` 기반으로 전환. 호출부가
   `WF_01`/`WF_02`/`run-sys3d`이므로 **그 세 개를 회귀 순서로 실제 지나가야** 한다.

### P2

7. `flows.close_examine`의 no-dialog 경로 상태 신호화.
8. 추적성 미확정 19건 중 **구현된 TC**부터 인용 확보 —
   `WF_01`(DICOM Conformance Statement), `WF_04`(2D Send), `WF_07`(Auto Send),
   `WF_12`(Study Reject), `WF_15`(Pre-send Preview).
9. Dose SR 생성 조건 조사(`NEXT_TASK.md` 고도화 대기 1번의 절차대로).
10. `Install_01`/`Install_02` MANUAL 해제 — 검증 대상 Release Note와 지원 OS Build
    목록·DICOM 어댑터 별칭을 사용자에게 받으면 자동 판정 가능
    (`config.json > release_note`, `> prerequisites`).

---

## 5. 다음 세션용 프롬프트

아래를 그대로 붙여 쓸 수 있다.

```text
Bellalun Viewer QA 자동화를 아래 경로에서 이어서 진행해줘.

프로젝트 루트: C:\Users\ksj74\OneDrive\Desktop\자동화\Bellalun Viewer
Git 저장소: 같은 경로의 auto

먼저 auto/AGENTS.md, auto/NEXT_WORK.md, auto/NEXT_TASK.md, ..\프로젝트 상세.html,
그리고 지식 폴더의 영구 지침 3종을 읽어 현재 상태와 규칙을 파악해라.
TC 원문은 Bellalun_Viewer_기본기능_Checklist_개정본.xlsx의 `개정 TC` 시트만 기준으로
삼는다(지식 폴더의 다른 체크리스트는 번호 매핑이 다르다).

가장 먼저 관리자 권한을 확인해라 — `python run.py portability-check`의 "관리자 권한"이
False면 UI 자동화가 전부 차단된다. False면 그 사실을 먼저 보고하고, UI가 필요 없는
작업(정적 검사, 문서, 추적성)만 진행해라.

P0 (권한이 있을 때)
1. TC_XIPL_compatibility_07을 회귀 시작 상태에서 단독 실행해 검증한다.
   python run.py reset-environment → python run.py run-xipl-07
   NEXT_WORK.md 4절 P0-1의 확인 목록을 그대로 따라가고, 3D-W의 EgpName 실측값을
   기록해라. 실패하면 추측으로 완화하지 말고 실패 증거(화면 컨텍스트·캡처·로그)를
   먼저 확인해라.
2. 전체 회귀 1회를 돌리고 TC/PASS/FAIL/SKIP/MANUAL·소요 시간·특이사항·Report/Log/증거
   경로·Cleanup 결과를 실제 결과만 기록한다.

P1
3. python run.py probe-preset3d 로 Setting > Procedure > Preset의 3D-N/3D-W 목록·추가·
   삭제 컨트롤을 실측하고 core/flows.py 상수와 NEXT_TASK.md에 기록한다. 번호가 이어질
   것이라 추측하지 마라.
4. 그 위에 "새 3D Preset이 그 시점 Default Recon Parameter를 물려받는가"(Service
   Manual 근거)를 TC_XIPL_compatibility_07에 추가한다. 정리는 UI 삭제로 하고 삭제 전후
   DB를 대조해 대상 외 삭제를 막아라.
5. TC_XIPL_compatibility_04에 DefaultImgProcess 원복을 추가한다. reset-environment →
   run-xipl-04 → DB 확인까지 실제로 지나간 뒤에만 커밋해라.
6. flows.demo_acquire_step의 고정 대기(settle=14)를 wait_new_group 기반 조건 대기로
   바꾼다. 호출부가 WF_01/WF_02/run-sys3d이므로 그 세 개를 회귀 순서로 실제 지나가라.

검증·Git
- 변경 모듈 py_compile, tools_check_module_attrs.py, tools_check_regression_names.py,
  tools_traceability.py, python -m unittest discover -s tests -p "test_*.py" 를
  긴 실행 전에 모두 돌려라.
- 문서를 갱신해라: README.md(간결·최신 회귀 1건), ..\프로젝트 상세.html,
  NEXT_WORK.md, NEXT_TASK.md, automation_scope.json, traceability.json,
  지식/[자동화 구현 현황].
- git status/diff/remote 를 검토하고 관련 파일만 commit 한 뒤 git push origin main 을
  시도해라. Force Push와 history 재작성은 금지다. config.json, Reports/, Evidence/,
  Log/, Cache/, Temp/, work/ 는 커밋하지 마라.
- 테스트하지 않은 것을 성공했다고 기록하지 마라. 사용자 판단이 필요한 항목은
  SKIP/TODO로 남기고 나머지는 계속 진행해라.
```
