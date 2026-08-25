# 다음 작업 인수인계

> **문서 지도 — 이 문서의 역할과 다른 3개 문서와의 관계**
> 이 문서는 **누적 인수인계 기록**이다 — 실측한 컨트롤 ID, 확정한 제품 동작, 지난 회차의 판정 기준과 그 경위. **통독용이 아니라 검색용**이다. 끝난 항목은 제목에 `[완료]` 를 붙이면 `tools/prune_docs.py` 가 `Archive/NEXT_TASK_완료기록.md` 로 내린다(지우는 것이 아니다 — 운영 지침 16절).
> **지금 할 일**은 `NEXT_WORK.md`, **작업 규칙**은 `AGENTS.md`, **영구 구현 규칙**은 `..\지식\[자동화 운영 지침] ...md` 에 있다. 여기 적힌 과거 기록이 그 셋과 어긋나면 **그 셋이 최신**이다 — 이 문서는 지우지 않고 쌓는 자리다.
> **읽는 순서 — `README.md` 최상단 "온보딩 요약" → `AGENTS.md` → `NEXT_WORK.md` → `[자동화 운영 지침]`(상단 "증상 → 원인 → 조치" 색인부터) → 필요할 때 이 문서 검색.**

## 2026-08-25 — 문서 고도화·자동화 구조 보강 Phase 2

<!-- keep -->

- `프로젝트_상세.md` → `.html` 렌더러를 2026-08-26에 도입했다(`auto/tools/render_docs.py`).
  **상세가 기본 문서, README는 포트폴리오 축약형**이다(사용자 확정). HTML은 직접 고치지
  않는다. 같은 날 `tools_*.py` 10개를 `auto/tools/`로 모으고 접두사를 뗐다 —
  `tools/_paths.py`가 sys.path와 cwd를 저장소 루트로 맞춘다.
- 권장 회귀 진입점은 `run_all.cmd` → `tools/run_regression.py` →
  `run.py run-regression`이다. 외부 래퍼가 새 전체 회귀 리포트 유무를 확인하므로
  회귀 Python 자체가 죽는 경우도 감지한다.
- 상태는 `work/regression_state.json`, 실제 제품 크래시는 Windows WER 기본 위치
  `%LOCALAPPDATA%\CrashDumps\VIEWER.exe.<pid>.dmp`의 **이번 TC 시작 이후 파일**로
  확인한다. 덤프가 없으면 크래시로 단정하지 않고 `원인 불명 종료`로 기록한다.
- `check_automation_status.cmd 7`은 마지막 완료 전체 회귀가 7일 넘었는지 확인한다.
  전체 회귀 표식 4개를 TC ID로 대조하므로 개별 TC 리포트와 전제 실패 조기 종료를
  정상 실행으로 오인하지 않는다.

## 고도화 대기 항목 (사용자 지시로 등록 — 2026-08-21)

여기 적힌 것은 **아직 자동화하지 않았고, 다음 회차에 손댈 후보**다. 리포트의 판정
`note` 가 이 절을 참조하므로 항목을 지우지 말고 상태만 갱신한다.

| # | 항목 | 현재 상태 | 무엇을 해야 하는가 | 막힌 지점 |
|---|---|---|---|---|
| 1 | **Dose SR(RDSR) 전송 검증** | `WF_06` Step 3~5 / `WF_07` Step 6 / `WF_15` Step 6 이 MANUAL. Queue 행은 잡지만 `State=3` 에서 멈춘 것만 관측한다 | RDSR 이 실제로 생성·전송·수신되는 경로를 판정한다. 수신 객체의 SOP Class(`1.2.840.10008.5.1.4.1.1.88.67`)와 Patient ID / Study Instance UID 를 원본과 대조하는 코드는 이미 있다(`core/send_verify.py`) — **생성 조건**만 없다 | 이 PC 는 실제 X-ray 대신 Demo(F8) 가상 촬영을 쓰므로 RDSR 이 만들어지지 않는다. 여러 실행에서 `State=3` 을 반복 확인했다. **제품 결함이 아니라 전제 미충족**이다 |

### 1번 항목의 진행 방법 (조사할 것)

1. Demo(F8) 촬영에서 RDSR 생성 조건을 충족시킬 수 있는지 확인한다 — 사양서/Service
   Manual 에서 "RDSR 생성 조건"을 먼저 찾는다. **화면 동작으로 역산하지 않는다.**
2. 조건이 실제 노출값(선량)을 요구하면 자동화 대상이 아니다. 그 결론을
   `automation_scope.json` 의 해당 TC `coverage.gap` 에 근거와 함께 적는다.
3. 조건이 설정(예: Storage `SendDoseSR`, Study close option)만이라면 그 설정을
   맞춘 뒤 Queue 행이 `State=7` 이 되는지 확인하고, 되면 MANUAL 을 자동 판정으로
   올린다.
4. 어느 경우든 **판정을 약화시켜 통과시키지 않는다.** 조건이 성립하지 않으면
   MANUAL 로 남기고 해제 조건을 적는다.

---

## 2026-08-24 회차 — `TC_XIPL_compatibility_07` 추가와 실측 기록

> 다음 작업과 우선순위는 **`NEXT_WORK.md`** 에 있다. 이 절은 이번 회차에 **실측으로
> 확정한 것**을 누적 기록으로 남긴다.

### 실측으로 확정한 DB 구조 (3D 파라미터)

| 대상 | 확정한 것 |
|---|---|
| `PROCEDURE.PROCEDURE_COMMON` | 컬럼 4개 — `DefaultImgProcess`(2D `.pim`) / `DefaultReconNarrow`(3D-N `.xtp`) / `DefaultReconWide`(3D-W `.xtp`) / `TargetExposureIndex`. **모드별로 나뉜다는 사양(SRS 03-10-110)이 스키마에 그대로 있다.** 관측값 `DBT_Standard_Default.xtp` / `DBT_Standard_Default.xtp` |
| `PROCEDURE.VIEW_POSITION_PRESET.Type` | `0`=2D / `1`=3D-N / `2`=3D-W. 행 수 실측 2D 28(+시험 4) / 3D-N 22 / 3D-W 22 |
| 3D Preset 의 Positioning | Type 1·2 모두 `PositioningKey` `{1,2,3,4,5,6,7,8,9,11,13}` = `CC, MLO, LM, LMO, ML, SIO, ISO, XCCL, XCCM, TAN, AT` **11종**. 사양서1 196쪽 SRS 03-30-20 의 11종과 **정확히 일치**하고 `FB`(10)·`CV`(12)·`SPECIMEN`(14)은 없다(*"FB 및 CV는 촬영 불가"*). Step 3 판정의 근거 — 화면 OCR 보다 강하다 |
| `VIEW_POSITION_PRESET.XIPLParamName` | 컬럼 이름은 하나지만 **Type 에 따라 담는 것이 다르다** — 2D 행은 `.pim`, 3D 행은 `.xtp`. Service Manual 의 `XIPL Param`(2D) / `Recon Param`(3D) 열에 대응 |
| **적용된 3D Recon 파라미터 이름** | **`DATA` 데이터베이스 어디에도 없다.** `INFORMATION_SCHEMA.COLUMNS` 로 `%Param%`/`%Xtp%`/`%Pim%`/`%Recon%`/`%Process%` 를 전수 조회해 확인했다(`EXAMINE_STATISTIC.RejectProcessing`/`RetakeProcessing` 두 개만 걸리고 무관하다). `INSTANCE_GROUP` 에도 없다 |

### 실측으로 확정한 제품 파일 구조 — `.img`

제품 `.img` 는 `..BELLALUN.IMG.` 매직으로 시작하는 이진 컨테이너이고, **끝부분에
UTF-16LE 로 인코딩된 `<INFORMATION>` XML 한 덩어리**가 붙는다.
근거 문서: 사양서1 277쪽 SRS 03-50-230 — *"Apply를 누르게 되면 해당 img 파일에 영상 조정
파라미터 값들이 저장된다"*, 그리고 개발 사양의 `ReconParam` 항목 목록
(`EgpName, EapName, XtpName, PostBackgroundMasking, PostContrast, ...`).

루트 자식: `PATIENT_INFO` / `STUDY_INFO` / `SERIES_INFO` / `INSTANCE_GROUP_INFO` /
`DOSE_LIST` / `DEVICE_INFO` / `INSTANCE_INFO` / `FRAME_LIST` / `ANNOTATION_INFO`.

`INSTANCE_GROUP_INFO` 자식 4개 — `InstanceGroup` / `ViewPosition` / `ReconParam` /
`RawInfo`. 실측 예(3D-N, Study48/Image81):

    <InstanceGroup Key="54" ExposureType="1" ExposureMode="1" StereoType="0" .../>
    <ViewPosition Name="CC" Type="1" Alias="" Code="R-10242" Laterality="1" .../>
    <ReconParam EgpName="narrow_standard.egp" EapName="common_standard.eap"
                XtpName="TEST_3D_FLOW.xtp" PostBackgroundMasking="0"
                PostContrast="14" PostDetailEnhancement="16" PostBrightness="14"
                PostToneType="15" S2DBackgroundMasking="0" S2DContrast="6"
                S2DDetailEnhancement="14" S2DBrightness="6" S2DTonetype="15"/>

- **2D 영상(`ViewPosition/@Type=0`)도 같은 `ReconParam` 요소를 갖지만 이름 3개가 모두
  빈 문자열**이다(실측 Image79). 그래서 이 파일 근거는 3D 전용이다. **2D 의 `.pim`
  이름은 img 에 없다** — `INSTANCE_INFO` 에도 없다.
- `ExposureMode` 는 `INSTANCE_GROUP.ExposureMode` 와 같은 값이다(1=Narrow / 2=Wide,
  `tests/system_compat.py` 가 대조 확정한 값).
- 파일 크기 실측: 3D Raw `Image80.img` 710,001,874 바이트 / Recon `Image81.img`
  45,839,692 / Synthetic `Image82.img` 1,543,294 / 2D `Image79.img` 28,465,124.
  XML 길이는 8.5KB~29KB. **그래서 꼬리만 읽는다**(`core/imginfo.py`, 기본 4MB).
- `S2DTonetype` 은 다른 항목과 달리 **`T` 가 소문자**다(제품이 그렇게 쓴다).
  속성 이름을 손으로 짐작하지 말고 읽은 dict 를 그대로 쓴다.

**2026-08-24 실행 검증에서 확정한 것** (관리자 권한 세션, `reset-environment` ->
`run-xipl-07`, Step 1~9 전부 PASS)

| 항목 | 3D-N (`ExposureMode=1`) | 3D-W (`ExposureMode=2`) |
|---|---|---|
| `ReconParam/@EgpName` | `narrow_standard.egp` | **`wide_standard.egp`** |
| `ReconParam/@EapName` | `common_standard.eap` | `common_standard.eap` |
| `ReconParam/@XtpName` | `DBT_Standard_Default.xtp` | `DBT_Standard_Default.xtp` |
| `ViewPosition/@Type` | `1` | **`2`** |
| `INSTANCE_GROUP` Key | 57 | 58 |

- **`EgpName` 이 모드를 따라간다**는 것이 확정됐다. 그래도 판정은 특정 파일명을
  기대값으로 박지 않고 "두 모드가 서로 다르다"까지만 한다 — 제품이 파일명을 바꿔도
  모드 분리라는 사양(`SRS 03-10-110`)은 그대로 검증된다.
- **`ViewPosition/@Type` 도 모드를 구분한다**(3D-N=1 / 3D-W=2). 그전에는 "3D 면 1" 로만
  알고 있었다. `VIEW_POSITION_PRESET.Type` 과 같은 체계다.
- **`XtpName` 은 두 모드 모두 Preset 설정값**(`DBT_Standard_Default.xtp`)이 들어갔다.
  즉 `Setting > Procedure > General` 의 Default 를 바꿔도 **Preset 에 등록된 View
  Position 에는 반영되지 않는다** — 사양서1 185~186쪽 SRS 03-10-110 과 일치한다.
  `automation_scope.json` 에 적어 둔 coverage.gap("새로 추가하는 Preset 경로는 아직
  판정하지 않는다")이 **실측으로 확인됐다.**

### 조건 기반 촬영 대기 실측치 (2026-08-24)

| 촬영 | `wait_new_group` 실측 | 이전 고정 대기 |
|---|---|---|
| 기본 2D 스텝 4개 | 각 **2.8~2.9초** | 14초 (`demo_acquire_step` 기본값) |
| 3D-N (Raw/Recon/Syn) | **29.5초** | 20초 (`system_compat` 호출부) |
| 3D-W (Raw/Recon/Syn) | **39.7초** | 20초 |

**기존 고정 20초는 3D 에 오히려 부족했다.** 조건 대기는 2D 를 빠르게, 3D 를 안전하게
만든다 — 고정 대기가 "느리면서 동시에 불안정하다"는 것이 수치로 확인됐다.

### Preset 페이지 OCR 실측 (2026-08-24)

`find_text_boxes` 는 OCR 의 **단어** 박스를 대조한다. 그래서 다중 단어는 못 찾는다.

| 찾는 문구 | 결과 | 비고 |
|---|---|---|
| `3D-N` / `3D-W` | **0건** | 제목이 괄호까지 한 단어로 읽힌다 |
| `(3D-N)` / `(3D-W)` | 각 1건 | 목록 제목 `Preset (3D-N)` / `Preset (3D-W)` |
| `Recon Param` | **0건** | 다중 단어는 매칭되지 않는다 |
| `Recon` | **2건** | 3D-N / 3D-W 목록의 열 이름 |
| `XIPL` | 1건 | 2D 목록의 열 이름(대조군) |
| `Preset` | 3건 | 목록 3개 |

화면 구성도 확정됐다 — `Preset (2D)` / `Preset (3D-N)` / `Preset (3D-W)` 세 목록이
나란히 있고 열이 `Name | Alias | XIPL Param`(2D) / `Name | Alias | Recon Param`(3D)다.
**Service Manual `Preset 메뉴` 의 표와 일치한다.** 각 목록에 독립된 `+`/🗑 버튼이 있다
(컨트롤 ID 는 여전히 미실측 — `probe-preset3d` 로 확정할 것).

### 실측하지 않아 추측하지 않은 것 — 3D Preset 목록 컨트롤

`Setting > Procedure > Preset` 의 **3D-N / 3D-W 목록·추가·삭제 컨트롤 ID 는 실측되지
않았다.** 2D 만 확정돼 있다(`flows.PRESET_2D_LIST`=2554 / `PRESET_2D_ADD`=2548 /
`PRESET_2D_DELETE`=2549). 번호가 이어질 것이라 **추측하지 않는다**(`AGENTS.md` 3·5절).

그래서 `compatibility_07` 은 3D Preset 행을 만들거나 편집하지 않고
`Setting > Procedure > General` 의 모드별 Default 콤보(`2543`/`2544`, 이미 실측됨)만
조작한다. 그 결과 Service Manual 의 *"Preset 에 **새로 추가하는** View Position 은
Default 로 설정한 파라미터를 적용한다"* 경로는 아직 판정 대상이 아니다
(`automation_scope.json` 의 `coverage.gap`).

해제 방법: `python run.py probe-preset3d` — **조회 전용** 프로브다. 이미 검증된 레일
컨트롤(`open_procedure_setting`)만 누르고 목록·버튼은 읽기만 하며, `PROCEDURE_COMMON` 과
`VIEW_POSITION_PRESET` 행 수를 **전후로 찍어 대조**해 출력한다(2026-08-20 Hospital Code
사고의 재발 방지 — 조회 전용이라고 생각한 프로브가 DB 를 바꿨다).

### 확정한 판정 기준 — `TC_XIPL_compatibility_07`

- Step 1·2: `PROCEDURE_COMMON.DefaultReconNarrow` / `DefaultReconWide` 값 대조.
  **한쪽을 바꿔도 다른 쪽이 유지되는지**까지 본다(모드 독립이 사양의 요구다).
  Service Manual 에 *"3D-N 타입의 AEC Level Value 값을 변경하면 자동으로 3D-W 값이
  조정되어 변경됩니다"* 라는 항목이 있는데 그것은 **AEC 이고 Recon Parameter 가
  아니다.** 두 축을 섞지 않는다.
- Step 3: Preset 페이지 OCR(`3D-N`/`3D-W` 표시) + Preset 구성 전수 대조(위 11종).
- Step 5·6: `INSTANCE_GROUP.Type=1` 과 `ExposureMode` 1↔2, `InstanceType 1/2/3` 각
  1건, Image Instance UID 유일. **두 모드의 `ExposureMode` 가 서로 다른지**까지 본다
  (이것이 없으면 3D-W TC 가 3D-N 촬영으로도 통과한다 — `system_compat` 과 같은 이유).
- Step 7·8: Post Reconstruction 콤보 표시값(사양서1 277쪽 — 획득 시 xtp 자동 선택)과
  `.img` 의 `XtpName` 을 **교차** 확인. `XtpName` 은 **그 모드의 Preset 설정값 또는 그
  모드의 General Default 중 하나**여야 한다(사양서1 185~186쪽 SRS 03-10-110 이 정한 두
  정상 경로). 어느 규칙이 적용됐는지도 판정 `actual` 에 기록한다 — 둘 다 정상이므로
  하나를 기대값으로 고정하면 오판정한다.
- Step 9: 시험 전 값으로 UI 원복 → DB 재확인. 예외로 끝나도 `finally` 가 한 번 더
  시도하고 **결과를 반드시 판정으로 남긴다**(조용히 넘기지 않는다).
- **SKIP 기준**: `2543`/`2544` 가 **둘 다** 안 보이면 Tomo 미지원 또는 2D 전용
  License(Service Manual). 그때만 TC 전체 SKIP. **하나만 없으면 FAIL** — 미지원이면 두
  항목이 함께 사라지므로 "3D 미지원"으로 설명되지 않는다. 판단은 **실제로 화면을 열어
  확인한 그 단계에서** 한다. GPU 미탑재는 이 TC 의 SKIP 사유가 아니다.

### 시험 파라미터 이름 규칙 (추가)

`TEST_3D_NARROW.xtp` / `TEST_3D_WIDE.xtp`. **`TEST_3D_N` / `TEST_3D_W` 로 줄이지
않는다** — 콤보 항목은 OCR 로 골라야 하고(`_click_general_param_combo`), 한 글자만 다른
두 이름은 오독으로 반대쪽을 고를 수 있다. 단위 시험이 "두 이름이 3자 이상 다르다"를
강제한다. `.pim` 의 `_M` 접미 규칙은 `.xtp` 에는 없다(기존 `TEST_3D_FLOW.xtp` 와 동일).

### 이번 회차에 고친 결함

1. **저장소의 유일한 단위 시험이 실패 상태로 방치돼 있었다** — HTML 리포트에서
   `소요시간`(붙여쓰기)을 찾는데 리포트는 그 전부터 `소요 시간 분해`(띄어쓰기)를 쓰고
   있었다. 아무도 돌리지 않았다. `AGENTS.md` 8절 사전 검사에 단위 시험을 넣었다.
2. **아무도 읽지 않는 설정 키** — `config.example.json` 의 `preview_3d_wait` /
   `apply_3d_wait`. 코드는 `post_recon_timeout` / `preview_3d_timeout` /
   `apply_3d_timeout` 을 읽는다. 사용자가 3D 대기를 조정해도 **아무 일이 없었다.**
3. **죽은 blind-sleep 헬퍼** — `viewer_processing.preview_and_apply`. 호출부 0.
   남겨 두면 다음 사람이 다시 써서 조건 대기가 되돌아간다.

## 다음 우선순위

### 최신 (2026-08-21 후반) — WF_03 완결, WF_16 수동 전환, Storage 중복 해소, 리포트 개편

**전체 회귀 실측(19차, 2026-08-21 16:40)**: TC 26건 = PASS 20 / FAIL 1 /
MANUAL 5 / SKIP 0, 검증 251개 = PASS 241 / FAIL 1 / MANUAL 7 / SKIP 2,
111.3분. FAIL은 기존 `TC_XIPL_compatibility_03` Step 9 제품 결함 한 건뿐이다.

**자동화 범위**: 개정본 36건 = **FULL 20 / PARTIAL 6 / MANUAL 10** (+ 보조 4,
그중 3D 촬영 2건은 회귀 제외). `python run.py list` 또는
`python tools/report_numbers.py` 로 확인한다.

| 항목 | 이전 | 이후 |
|---|---|---|
| `WF_03` Step 5·6 | MANUAL | **자동** — 영상 패널 Overlay OCR / Film 창 영역별 Overlay OCR |
| `WF_16` | PARTIAL(Kiosk 일부 자동) | **MANUAL — 사용자 지정 수동**. 제품 조작 없이 MANUAL 판정 행만 기록 |
| `Install_02` Step 4 (DICOM NIC) | MANUAL | **SKIP** (확인 대상 없음). TC 판정은 PASS |
| `Install_02` OS 정보 | MANUAL 확인 항목 | **삭제** → 리포트 상단 '실행 환경' 표로 이동 |
| "Storage 활성 행 중복" | WF04 뒤 Key 복제 → WF05/06/15 전제 FAIL | **해소 — 판정 쿼리 결함이었다.** `DICOM_STORAGE` 는 설정 행과 **전송 작업 사본 행**을 함께 담고 `SCPUseType` 으로 구분한다(`0`=설정). 사본도 `Use=1` 이라 Send 한 번마다 오판정했다. 쿼리를 `SCPUseType=0` 으로 좁혔다 |
| `AUTOMATION_3D_ACQUISITION_3DN/_3DW` | 회귀 포함 | **회귀 제외** (`run-sys3d` 단독) |
| 리포트 | 기대값/실제값 열 폭 가변 | **고정 27%/27% 동일 폭**, 판정 열 74px→46px |
| 리포트 | — | **자동화 커버리지 총괄** 섹션 신규 (36 TC 전수 분류) |
| 리포트 | MANUAL/SKIP Step 단위 나열 | **TC 단위 한 행**으로 묶음 |

새로 추가한 모듈·도구

| 파일 | 용도 |
|---|---|
| `core/image_overlay.py` | 영상 위 Image Overlay 크롭·OCR·항목 판정. `WF_03` Step 5 와 `WF_15` 가 공용 |
| `core/print_overlay.py` (추가 함수) | `film_norm` / `ocr_film_areas` / `film_expectations` / `judge_film_areas` / `film_all_ok` — `WF_03` Step 6 과 `WF_08` 이 공용 |
| `core/dicom_settings.py` (추가 함수) | `STORAGE_SCP_USE_TYPE` / `active_storage_rows` / `storage_job_copies` / `repair_storage_use` — 설정 행과 전송 작업 사본 행을 구분하고, 설정 행이 여럿이면 UI 로 복구 |
| `core/flows.py` (추가) | `FILM` 컨트롤 맵 / `film_window` / `close_film` — Film 창을 **버튼 문구 OCR 로 확인한 뒤** 닫는다 |
| `core/uitext.py` (추가) | `button_reads` / `button_label` / `pick_button` — 버튼 문구를 반전·이진화 × psm 11/8/7/6 으로 읽어 **후보가 하나일 때만** 누른다 |
| `core/sysinfo.pc_info()` | PC/OS 실측 정보 한 번에 수집 (리포트 환경 표) |
| `tools/report_numbers.py` | 문서에 적을 수치를 리포트 JSON·저장소에서 실측 |

이번에 붙인 것

| TC | 이전 | 이후 | 요점 |
|---|---|---|---|
| `WF_14` Setting Export/Import | MANUAL(미구현) | **FULL** | `run-wf14`. `.vms` 를 zip 으로 열어 사양서1 60절 개발 사양 구성 대조 + 설정 테이블 전수 복원 대조 + Setting 56개 페이지 컨트롤 값 항목 단위 대조 |
| `WF_16` Kiosk 및 System Launcher | PARTIAL(Kiosk 일부 자동) | **MANUAL — 사용자 지정 수동** | `run-wf16`은 제품 UI를 조작하지 않고 MANUAL 한 건만 기록. Kiosk 자동화 코드 삭제 |
| `WF_10` Step 5~7 | MANUAL | **자동** | MWL 조회 -> 처방 선택 -> Examine. 판정 기준 확정(아래) |
| `WF_15` Step 4 | MANUAL | **자동** | View 화면과 항목 관찰 대조. Overlay OCR 전처리 강화 |

#### 실측으로 확정한 컨트롤 (2026-08-21)

| 화면 | 확정한 것 |
|---|---|
| **`CONFIGURATION.DICOM_STORAGE.SCPUseType`** | 이 테이블은 **설정 행과 전송 작업 사본 행을 함께 담는다.** `0` = `Setting > DICOM > Storage` 에 보이는 설정 행. 제품이 전송을 큐에 넣을 때 그 시점 설정을 사본으로 복제하고 `DATA.DICOM_STORAGE_QUEUE.StorageKey` 가 사본, `OriginalStorageKey` 가 원본을 가리킨다(실측: `StorageKey=18` / `OriginalStorageKey=17`). **사본도 `Use=1`** 이라 `WHERE [Use]=1` 만으로 "활성 SCP 가 하나"를 판정하면 Send 한 번마다 오판정한다. Storage Group / Storage Commitment / Query·Retrieve / MPPS 목록은 전부 0행이므로 사본은 어느 설정 화면에도 없다. 열거값 전체는 문서로 확인하지 않았다 — `0` 의 의미만 확정했다 |
| **Film 창** (WF_03 Step 6 / WF_08) | 필름 raster 는 `158`(`CWndFilmManager`). Layout `1141` 1x1 / `1142` 1x2 / `1143` 2x2 / `1144` 2x1. **`1149` Print** (OCR `Print`) / **`1105` Close** (OCR `Close`) — Pre-send Preview 창의 Close 와 같은 ID다. Film 창 자식에는 닫기 버튼이 없다(`166`/`167`/`162`/`203`/`201`만) — Close 는 다이얼로그 하단 우측의 별도 `TextButton` 이다 |
| **Film 종료 확인 대화상자** | Close 를 누르면 `#32770` 팝업 `"Are you sure you want to close?"` 이 뜬다. **`Yes`=501 / `No`=500** — Print 범위 선택(`Selected`=501 / `Cancel`=500)과 **같은 ID** 이므로 ID 로 고르면 정반대를 누를 수 있다. 문구를 OCR 로 읽어 고른다 |
| **버튼 문구 OCR 전처리** | 이 제품의 확인 대화상자는 **분홍 배경+흰 글자**(Yes)와 **흰 배경+분홍 글자**(No)를 나란히 쓴다. `autocontrast` 하나로는 Yes 가 `ee`, No 가 `(me)` 로 읽혀 구분되지 않는다. `auto psm7` → `Yes y`, `bin150 psm11` → `No` 로 읽힌다. 그래서 `uitext.button_reads` 가 반전·임계값 이진화 × psm 11/8/7/6 을 모두 시도하고, `uitext.pick_button` 이 **후보가 하나일 때만** 누른다 |
| My Settings > Export(2293) | **Windows 표준 저장 대화상자**(`#32770` "다른 이름으로 저장"). 파일 이름 Edit `1148`(cls=Edit) / 저장 `1` / 취소 `2` / 파일 형식 콤보 `1136`=`vms file (*.vms)`. 저장 완료 후 버튼 하나(`500`) 팝업 |
| My Settings > Import(2294) | **제품 자체 모달**(표준 열기 대화상자가 아니다). `2075` File Path Edit / `2073` `...` 찾아보기 / `2076` System / `2077` Account / `2078` Procedure 체크박스 / `2074` Import / `1102` Close / `-4` 닫기(x). **기본값은 System 만 체크** |
| `.vms` 내부 | zip 18항목: `CONFIGURATION.bak` `ACCOUNT.bak` `PROCEDURE.bak` `Config/ExternalInput.xml` `PARAMETER/*.pim` `PARAMETER_QC/*.pim` `RECON_PARAMETER/*.xtp` `Version.txt`(=`1.0.12.105`). 사양서1 개발 사양과 일치(사양 본문은 `PARAMETER` 로만 적었는데 제품은 용도별로 더 세분화한다) |
| Setting > System > General | Theme 콤보 `2227` / Monitor 콤보 `2228` / Storage Warning 슬라이더 `2230`(자식 `1`=◀ `2`=▶) + Edit `2232` / Critical 슬라이더 `2231` + Edit `2233` / Update `2226` |
| Setting > System > Security | Strong pwd `2234` Use / `2235` Not use / Auto logoff `2236` Use / `2237` Not use + 분 Edit `2240` / **Exit 권한 콤보 `2241`** / **KIOSK `2238` Use / `2239` Not use** / System date/time `2242` |
| Setting 콘텐츠 패널 | 페이지 레일 오른쪽의 `#32770` 중 가장 큰 것(실측 rect `382,85 ~ 1840,905`). 절대좌표를 박지 않고 이걸로 캡처 영역을 잡는다 |

#### 실측으로 확정한 제품 동작

- **Import 는 재시작 때 적용된다.** Import 직후 팝업: `Please restart to apply the
  change. If you don't restart, the setting change may be ignored.` 재시작 전에는 DB
  값이 그대로고, 재시작 후에 Export 시점 값으로 돌아온다(`StorageWarning` 12 -> 13 ->
  재시작 후 12). 사양서1 60절과 일치.
- **Kiosk 는 저장 시점에 레지스트리를 바꾸지 않는다.** `UseKiosk=1` 이 되어도
  `Winlogon\Shell` 은 `explorer.exe` 그대로이고 팝업만 뜬다:
  `You need to restart PC to apply KIOSK setting.` 사양서1 "PC를 재시작해야 적용된다"
  와 일치. **저장 시점의 레지스트리 쓰기 여부는 문서에 없어 기대값을 단정하지 않고
  관측만 기록한다.**
- **`ExitPermission=3` <-> 화면 `Allow only Service`** (실측된 짝 하나뿐). 나머지 코드
  매핑은 값을 바꿔 봐야 확정되므로 추측하지 않는다.
- **커스텀 컨트롤은 `BM_GETCHECK`/`BM_GETSTATE` 에 응답하지 않는다** — 라디오 8개 전부
  `0`. 화면 상태는 픽셀, 저장된 상태는 DB.
- **VIVIX-M Setup / Bellalun System Setup 이 이 PC 에 설치되어 있지 않다.**
  `Program Files` 전수 탐색으로 확인. `Install_06` 과 `WF_16` Step 5/6 이 MANUAL 인
  진짜 이유다.

#### WF_10 Step 5~7 판정 기준 (미결이었던 것을 확정)

- Expected 6 -> `STUDY.HospitalCode` (MWL 태그의 코드가 검사에 기록됐는가) +
  `STUDY.ProcedureKey` (그 코드가 **매핑된 Procedure 로 해석됐는가**). 화면 OCR 보다
  직접적이다.
- Expected 7 -> Examine 의 Step 수를 `PROCEDURE_ITEMS(ProcedureKey=1)` 행 수와 대조
  (Routine Mammography = **4행**) + 상단 Ready 배너로 첫 Step/Preset 선택 확인.
- **자기충족이 아닌 근거**: `WF_01` 이 Procedure 없는 MWL 처방에서 Step 수 **0** 을
  확인하는 대조군이다.

#### 감사에서 고친 것 (자세한 표는 `..\인수인계_2026-08-21.md` 3-5절)

절대좌표 클릭 1건, 하드코딩 경로 죽은 코드 1건, `UnboundLocalError` 를 낸 미사용
import 1건, 활성 Storage SCP 중복 미확인 1건, 식별 컬럼 없는 테이블의 diff 오작동
1건, 진행 카운터가 설정 비교에 섞인 것 1건, 1px 배치 흔들림 오탐 1건, 페이지 판독
성능 1건, `specs.cite` 근거 유실 1건.

#### 다음 후보

1. `Install_02` MANUAL 2건 — 지원 OS Build 목록과 DICOM 어댑터 별칭을 사용자에게
   받으면 자동 판정 가능(`config.json > prerequisites`).
2. `Install_01` — 검증 대상 Release Note 를 받으면 FULL 가능.
3. `WF_16` Step 9 후반 — Exit 권한을 `Allow only Service` 로 둔 상태에서 User 그룹
   계정으로 로그인해 Exit 버튼 부재를 확인하는 것. WF_13 이 만드는 계정을 재사용할 수
   있지만 로그인 계정을 바꾸는 위험을 회귀 안에서 어떻게 다룰지 결정이 필요하다.
4. `flows.close_examine(wait=8)` 의 고정 대기를 상태 신호로 바꾸는 것(현재 유일하게
   남은 상태 신호 없는 고정 대기).

> **끝난 기록은 [`Archive/NEXT_TASK_완료기록.md`](Archive/NEXT_TASK_완료기록.md) 로 내렸다** (2026-08-25 기준 12개 절 / 16,095자). 지운 것이 아니라 옮긴 것이라 검색하면 그대로 나온다 — `tools/prune_docs.py` 참고.

> **끝난 기록은 [`Archive/NEXT_TASK_완료기록.md`](Archive/NEXT_TASK_완료기록.md) 로 내렸다** (2026-08-26 기준 17개 절 / 17,603자). 지운 것이 아니라 옮긴 것이라 검색하면 그대로 나온다 — `tools/prune_docs.py` 참고.

## 이 PC에서 아직 준비되지 않은 것

- (해결됨) DB 기준 스냅샷은 저장소 상위 `Baseline\` 폴더에서 자동으로 찾아
  복원한다. 2026-08-18 회귀에서 `AUTOMATION_ENVIRONMENT_RESET`이 PASS로 확인됐다.

- (해결됨) `TC_XIPL_compatibility_04`의 시험 Preset은 이제 **UI로 자동 삭제**한다
  (`tests/xipl_flows.py::_delete_test_presets`). 행은 `Type=0 AND Roll IN ('RL','RM')`
  으로 식별하고(제품 기본 Preset은 Roll이 비어 있다), 삭제 전후 전체 Key 집합을
  비교해 의도한 Key만 사라졌는지 확인한다. `core/db.py`는 여전히 조회 전용이다.

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

## Git 브랜치 정리 — `agent/add-next-task-handoff` 는 왜 남아 있나 (2026-08-25 확인) [완료]

<!-- keep -->

**한 줄**: 2026-08-11 에 AI 세션이 작업용으로 판 브랜치이고 그 내용은 **이미 `main`
에 전부 들어가 있다**. 지금은 그저 옛 시점을 가리키는 이름표라서 지워도 잃을 것이
없다 — 지우지 않은 이유는 확인을 받지 않았기 때문이다.

**실측(2026-08-25)** — "main 과 20,000줄 이상 차이 나는 스테일 브랜치"로 보이지만
**갈라진 것이 아니다.**

| 확인 | 명령 | 결과 |
|---|---|---|
| 갈라진 커밋 수 | `git rev-list --left-right --count main...agent/add-next-task-handoff` | `76  0` — **브랜치 고유 커밋 0개**, main 이 76개 앞섬 |
| 병합 여부 | `git merge-base --is-ancestor agent/add-next-task-handoff main` | 참 — **main 의 조상**이다 |
| 브랜치에만 있는 변경 | `git diff --stat main...agent/add-next-task-handoff` | **비어 있음** |
| 브랜치 끝 | `git log -1 agent/add-next-task-handoff` | `28a81ee` 2026-08-11 "Automate Workflow 03 DICOM print overlay" |

`git diff main agent/add-next-task-handoff` 가 보여 주는 **20,012줄 삭제**는 브랜치가
가진 내용이 아니라 **그 시점 이후 main 이 쌓은 것**이다(README 축약 1,286→257줄,
NEXT_TASK 누적, 모듈 분리 등 76 커밋). 2-dot diff 를 스테일 판단의 근거로 쓰면
**정상적으로 병합된 조상 브랜치가 전부 "2만 줄 차이"로 보인다** — 갈라짐은
`rev-list --left-right --count` 의 **오른쪽 숫자**로 판단한다.

**결론**: 삭제해도 안전하다(`git branch -d` 가 이의 없이 지운다 = 병합됐다는 뜻).
로컬과 `origin` 양쪽에 있다. **삭제는 사용자 확인 후 진행한다.**

```bash
git branch -d agent/add-next-task-handoff
git push origin --delete agent/add-next-task-handoff
```

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

실제 `config.json`과 생성된 증거/리포트는 의도적으로 로컬 파일이며 Git에서
제외된다. 보존하고, 저장소 템플릿은 `config.example.json`만 사용한다.

## 마무리 규칙

작업이 끝나면 이 파일을 다음 TC 기준으로 갱신하거나 제거하고, `AGENTS.md`에 따라
검증·커밋·푸시한다. 로컬 설정과 런타임 증거는 커밋하지 않는다. 계속 적용해야 하는
규칙은 이 파일이 아니라 `..\지식\`의 운영 지침/구현 현황 문서에 반영한다.
# 2026-08-25 야간 인수인계 — Result/WF14/XIPL Save As

- Result 4종에 원본 체크리스트 수행 절차·기준 기대 결과·자동화 기대값을 Check별로 연결했다.
  BLOCKED를 별도 상태로 집계하고, 미수행 사유·해제 조건·말할 수 없는 범위를 표시한다.
- WF14의 가상 목록 부분 스크롤은 제거했다. 숨은 하단 행 상세값은 차기 개선 MANUAL이며,
  현재 보이는 56페이지 값과 설정 DB 38개 섹션 대조는 유지한다.
- Setting Update 인라인 팝업은 연결된 분홍 버튼 도형을 찾아 연속 팝업까지 닫고, OCR
  소요시간이 전체 timeout을 넘겨도 이미 닫힌 성공을 잃지 않는다.
- XIPL Save As는 helper PID의 `다른 이름으로 저장` 창을 전역 HWND에서 찾는다. 실측
  파일명 Edit ID=1001, 저장 Button ID=1이며, 실제 입력값 재확인 후에만 저장한다.
- 최종 전체 회귀: `Reports/Result_20260825_221901.json`, 94.1분, TC 27건 =
  PASS 20 / FAIL 2 / MANUAL 3 / BLOCKED 2. XIPL_06 전 Step PASS. 남은 FAIL은
  WF14 UPS Import 미복원과 XIPL_03 3D 파라미터 유지 실패의 제품 동작이다.
