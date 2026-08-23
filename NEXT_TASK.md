# 다음 작업 인수인계

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

**아직 실측하지 않은 것**: `EgpName` 의 3D-W 값. `C:\XIPL\PARAMETER` 에
`narrow_standard.egp` / `wide_standard.egp` 두 개만 설치돼 있어 `wide_standard.egp` 로
추정되지만 **확인하지 않았다.** 그래서 `compatibility_07` 은 특정 파일명을 기대하지 않고
"두 모드의 `EgpName` 이 서로 다르다"까지만 판정한다. 실행 검증 때 확인해 여기에 적을 것.

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
`python tools_report_numbers.py` 로 확인한다.

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
| `tools_report_numbers.py` | 문서에 적을 수치를 리포트 JSON·저장소에서 실측 |

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

### 9. 미구현 TC의 진입점 실측 (2026-08-19) — 다음에 이어서 하면 된다

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

### 12. WF_13 완전 자동화 + WF_15 구현 (2026-08-20)

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

### 13. WF_11 / WF_12 — Reject 진입점을 아직 못 찾았다 (물어볼 것)

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

### 15. WF_10 진행 상황 (2026-08-20) — Code 셀 편집만 남았다

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

### 14. WF_10 — MWL 커스텀 태그 등록 방법 (해소됨, 2026-08-20)

아래 항목은 **해소됐다.** `core/mwl.py` 를 읽어 보니 처방 등록이 가능하다.
자세한 것은 15항 참고.

`Setting > DICOM > MWL` 의 `Hospital Code Mapping` 콤보(**2453**)와 순서는 확정했다
(등록된 Hospital Code 가 없으면 콤보가 아예 열리지 않는다).

**남은 것**: "MWL 서버에 임의의 코드로 커스텀 태그를 만들고 값을 넣는" 부분.
현재 `core/mwl.py` 가 처방을 만들 수 있는지, 아니면 별도 도구(Bunny 설정 화면 등)를
쓰는지 알려 주시면 붙이겠습니다.

### 11. 자매 프로젝트(VXvue) 개선안 검토 결과 (2026-08-20)

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

### 10. 사용자 답변 반영 (2026-08-20)

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

### 아직 못 찾은 것 — Pre-send Preview 버튼 (물어볼 것)

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

### 사용자에게 물어볼 것 (2026-08-19)

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

자동화 쪽 조치: `core/send_verify.py:ensure_transfer_syntax`가 전송 전에
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
| Examined 창 컨트롤 즉시 판정 | `flows.wait_controls()`로 상한 대기 (`viewer_processing`, `tests/workflow03.py`) | — |
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

실제 `config.json`과 생성된 증거/리포트는 의도적으로 로컬 파일이며 Git에서
제외된다. 보존하고, 저장소 템플릿은 `config.example.json`만 사용한다.

## 마무리 규칙

작업이 끝나면 이 파일을 다음 TC 기준으로 갱신하거나 제거하고, `AGENTS.md`에 따라
검증·커밋·푸시한다. 로컬 설정과 런타임 증거는 커밋하지 않는다. 계속 적용해야 하는
규칙은 이 파일이 아니라 `..\지식\`의 운영 지침/구현 현황 문서에 반영한다.
