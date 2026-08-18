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

## 새로 드러난 이슈 (TC_04 Step 6)

시험 Preset UI 자동 삭제가 동작하면서 **삭제→재등록 경로가 처음 도달 가능**해졌고,
그 지점에서 새 실패가 나왔다: `Step 등록 실패: 0->4`
(`_add_view_position_by_alias`는 +1을 기대하는데 한 번에 4개가 등록됨).

- 실측: 삭제 `{'deleted': [1001,1002,1003,1004], 'clicked_rows': ['RCCRL','RCCRM']}`
  → Step 1~5 PASS → Step 6에서 위 오류.
- 유력 가설: `vp.click_viewer_text(ui, alias)`가 View Position 다이얼로그에서
  의도한 타일이 아닌 것을 클릭했거나, Preset 타일 하나가 R/L 쌍을 함께 등록한다.
  (`PRESET_FLOW_A`/`B`가 둘 다 `PRESET_FL...`로 잘려 여러 박스를 반환하던 결함은
  2026-08-18에 "정확히 1개일 때만 허용"으로 조였다. 재확인 필요.)
- 확인 방법: `python run.py run-xipl-04` 실행 후 실패 순간의
  `%TEMP% 폴더의 bellalun_click_text_probe.png`를 **눈으로 볼 것**(운영 지침 7절 교훈).

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
