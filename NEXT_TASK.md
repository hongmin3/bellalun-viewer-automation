# Next automation handoff

## Next priority

`TC_Basic_WorkFlow_04`를 구현한다. 시작할 때 체크리스트의 **해당 TC 행과 Expected
Result 원문을 먼저 확인**하고, TC ID만으로 Step을 추측하지 않는다. 현재
`automation_scope.json`에는 "Overlay DB 변경 자동 판정; 표시 육안 확인"으로
PARTIAL 등록돼 있다.

그다음 후보:

1. `tests/dataflow.py`에는 `TC_Basic_WorkFlow_05/06/07/10/12/13`의 **판정 로직만**
   구현돼 있고 `run.py`에 연결하는 명령이 없다. 판정 로직 재작성보다 "실제
   Send/Export/Reject UI 흐름을 수행해 pre/post 스냅샷을 만드는 드라이버"가 먼저
   필요하다.
2. `TC_XIPL_compatibility_03`(Post Reconstruction)의 기대 결과에는 영상 타입으로
   **3D-Narrow와 3D-Wide가 함께** 명시돼 있다. 3D-W 등록/촬영은 이미
   `add_view_position(ui, "3d-w")`로 가능하므로, XIPL 픽스처에 3D-W 스텝을 더해
   Post Reconstruction을 3D-W에서도 검증하는 확장을 검토할 수 있다. 단
   `vp.open_test_study()`가 "정확히 2 스텝"을 요구하므로 픽스처 정의
   (`step_2d`/`step_3d`/`initial_steps`)를 함께 바꿔야 한다.

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

- **TC_XIPL_compatibility_04는 아직 반복 실행이 안 된다.** 이 TC가 만든 시험
  Preset(`PRESET_FLOW_A/B`, 실제 Name은 RCCRL/LCCRL/RCCRM/LCCRM)의 정리 절차가
  수동이라, 두 번째 실행에서는 Preset 추가가 "이미 존재"로 실패한다. 2026-08-14에
  남은 Preset을 감지해 **제품 FAIL이 아니라 무엇을 지워야 하는지 알려주는
  MANUAL**로 보고하도록 고쳤다(환경 오염이 제품 결함으로 오독되던 문제). 진짜
  해결은 UI로 시험 Preset을 자동 삭제하는 것이며, 별도 작업으로 분리했다.
  주의: `core/db.py`는 조회 전용이고 저장소 전체에 DB 쓰기가 없다(모든 상태
  변경은 UI로만 한다는 설계) — 정리용으로 DB 쓰기를 새로 열지 말 것.

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
