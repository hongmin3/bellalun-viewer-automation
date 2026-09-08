# Progress Checkpoint

## 2026-09-07 Windows Update 체크리스트 자동화 — 완료(라이브 전체 체인 PASS 9/FAIL 0/MANUAL 4)

**목표**: `../Windows Update 호환성 검증 Checklist_Bellalun Viewer_R-25-782.xlsx`
(시트 `Checklist`, TC_WindowsUpdate_01~13)를 신규 TC 없이 기존 기본기능/XIPL
자동화 재사용 + 얇은 매핑 계층으로 자동화. 상세 요구사항은 이 작업을 지시한
프롬프트(세션 로그) 참고 — 결정사항 1~7 전부 사용자 확정.

### 완료

- **매핑/리포트 인프라**: `tests/winupdate.py`(공유 매핑 표 `build_wu_results()`,
  `run()`/`--from-regression` 양쪽이 공유), `core/winupdate_report.py`(K열
  삽입 + `Result\n<MM/DD>` + Pass/Fail/Manual 리터럴 + 1~4행 실측 + Issues
  탭), `run.py`에 `run-winupdate`(+`--from-regression <path>`) CLI 추가.
  `python run.py run-winupdate --from-regression Reports/Result_20260903_224518.json`
  로 라이브 검증 완료 — `Reports/WindowsUpdate_Checklist_Result_20260907_191627.xlsx`
  생성 확인(K열 정상 삽입, 기존 L~S 밀림, 1~4행 실측값, Issues 탭 3건).
- **WU_01/12/13 MANUAL** — `TC_Basic_WorkFlow_16` 패턴으로 기록. WU_01은
  Install_01/02 판정 + `sysinfo.pc_info()`/`os_update_info()` 실측을 참고
  근거로 첨부.
- **WU_02** — `tests/workflow01.py`에 **Age** 대조 추가(생년월일·Scheduled
  Date 기준 독립 계산, 라이브 검증 PASS "46"). **Scheduled Date/Time은
  SKIP으로 보류** — Patient List MWL 카드(OCR+스크린샷 실측)와 Edit
  Information 어디에도 표시 위치를 못 찾았다(`np_study_datetime`은 Scheduled
  이 아니라 실제 Study 일시임을 실측 확인). **사용자에게 화면 표시 위치를
  물어야 한다** — 5절 참고.
- **WU_03** — Rotation 컨트롤 ID 실측(CW=1120, CCW=1121 — Expand 패널 안,
  스크린샷으로 라벨 확인). `core/viewer_tools.py::apply_tool_sequence`에
  Select(1111, 기존 실측)+Rotate CW/CCW 추가, Select는 화면 변화 대신
  `screen.radio_selected` 활성 표시로 판정. 라이브 검증 전부 PASS(2D pane).
  WF_02도 함께 고도화(Step 6/7에 반영, 사용자 승인).
- **WU_04/06/07/08/05/11**: 재사용 매핑 구현 + 결함 예외 처리(`_copy_checks`의
  `abort_keyword` — 알려진 결함이 유일한 FAIL 원인일 때만 cascading abort
  기록도 함께 제외, 다른 FAIL이 있으면 안전하게 남김). `--from-regression`
  라이브 테스트에서 WU_11이 UPS 결함 2건 모두 정상 제외되고 PASS로 전환됨을
  확인. WU_05는 이번 회귀 스냅샷의 실제 다른 원인(Step 1 조기 중단)이 그대로
  FAIL로 남는 것도 확인(설계대로 — 알려진 결함이 아닌 FAIL은 안 가린다).
- **WU_09**: `core/usb_media.py` 신규 — `find_usb_drive()`(이동식 드라이브
  자동 탐지, 없으면 SKIP), USB Export는 `core/export_manager.py` 그대로
  재사용(경로만 USB로). **USB Import 되읽기는 미해결** — Import Study
  대화상자(2184, 컨트롤 ID 전부 실측: 2062 드라이브/2065 경로 Edit/2063
  폴더찾아보기/2066 결과 목록/2064 Import/1102 Close)까지는 열었지만, 목록에
  실제로 행이 채워지는 트리거를 이 세션에서 못 찾았다(경로 Edit
  set_text+Enter 시도, 네이티브 폴더 다이얼로그 경로 주입 시도 모두 실패 —
  드라이브 드롭다운 C:\\/D:\\/E:\\ 선택이 진짜 트리거일 가능성이 높으나
  항목 컨트롤 ID 미확정). 현재 코드는 목록이 비어 있으면 **추측으로 Import를
  누르지 않고 MANUAL로 남긴다**(안전한 실패). 상세 실측 기록은
  `core/usb_media.py` 모듈 docstring.
- **WU_10**: 신규 구현(`tests/winupdate.run_setting_display`) —
  `setting_values.read_all` 전수 순회 그대로 재사용 + "탭 빠른 클릭"
  서브체크 신규(인접 그룹 A→B→A, 0.15초 간격, 활성표시+콘텐츠렌더 확인).

### 라이브 전체 체인 실행 결과 (완료 — 2026-09-07 19:17~20:57, 99.8분)

`python run.py run-winupdate` 를 Start-Process로 완전히 분리된 백그라운드
프로세스로 띄워 끝까지 완주했다(세션 종료와 무관하게 계속 동작 — 로그
`Reports/winupdate_live_20260907.out.log`, 산출물
`Reports/WindowsUpdate_Checklist_Result_20260907_205703.xlsx`).

**TC 13건: PASS 9 / FAIL 0 / MANUAL 4 / SKIP 0. 검증 215개: PASS 209 / FAIL 0 /
MANUAL 4 / SKIP 2. 자동화·제품 결함 전부 0건(FAIL 없음).**

| WU TC | 판정 | 비고 |
|---|---|---|
| 01 | MANUAL | 설계대로(참고 근거 첨부) |
| 02 | PASS | Age 대조 포함(46 일치) |
| 03 | PASS | Select+Rotate CW/CCW 신규 추가분 라이브 확인 |
| 04 | PASS | |
| 05 | PASS | XIPL_03 Step 9 알려진 결함, 이번 실행에선 재현 안 됨(아래 참고) |
| 06 | PASS | |
| 07 | PASS | |
| 08 | PASS | |
| 09 | MANUAL | **USB 드라이브 실제 인식(D:\\), Export 완전 자동 PASS.** Import 되읽기만 안전하게 MANUAL(추측 클릭 안 함) |
| 10 | **PASS** | 신규 구현 첫 라이브 실행 — Setting 56페이지 전수 순회 PASS, "탭 빠른 클릭" 24/24 전부 PASS |
| 11 | PASS | |
| 12 | MANUAL | 설계대로 |
| 13 | MANUAL | 설계대로 |

**Issues 탭 정확도 개선(라이브 실행 후 발견)**: `_attach_known_issues`가
title 매칭만으로 이슈를 실었는데, 이번 실행처럼 알려진 결함(UPS/3D 파라미터)
이 실제로는 재현되지 않은 회차에도 "기존 알려진 제품 결함"으로 실려 오해를
줄 수 있었다. **실제 그 check가 FAIL일 때만** Issues 탭에 싣도록
`tests/winupdate.py::_attach_known_issues`를 고쳤다(status=="FAIL" 조건
추가). `--from-regression`으로 결함이 실제 FAIL이었던 과거 스냅샷 재검증 —
issues 3건 그대로 유지됨을 확인(회귀 없음).

### 남은 작업 / 사용자 판단 필요

1. **WU_02 Scheduled Date/Time 표시 위치** — Patient List MWL 카드와 Edit
   Information 어디에도 없었다(실측 확인). 화면 어디에 있는지 알려주시면
   대조를 추가할 수 있다(현재 SKIP, 판정에 영향 없음).
2. **WU_09 USB Import 되읽기 트리거 미해결** — Import Study 대화상자 컨트롤
   ID는 전부 실측했지만(`core/usb_media.py` docstring 참고) 목록이 채워지는
   트리거를 못 찾았다. 드라이브 드롭다운(C:\\/D:\\/E:\\) 선택이 유력한
   후보다. 다음 세션에서 계속 조사하거나 사용자가 실제 UI로 확인해 주면
   빠르게 마무리 가능.

### 변경/신규 파일

`tests/winupdate.py`(신규 — 매핑 표), `core/winupdate_report.py`(신규 — WU
xlsx writer), `core/usb_media.py`(신규 — USB 탐지+Import 시도), `run.py`
(`run-winupdate`/`--from-regression` CLI), `core/sysinfo.py`
(`os_update_info` 추가), `core/viewer_tools.py`(Select/Rotate CW/CCW),
`tests/workflow01.py`(Age/Scheduled 대조 추가 — WF_01 자체도 고도화됨).

---

## 2026-09-07 저장소 경로 이전 (기능 변경 없음)

- OneDrive 동기화를 해지하고 알려진 폴더 리디렉션(`Desktop`/`Personal`/`My Pictures`
  → `%USERPROFILE%\OneDrive\...`)을 해제하면서 프로젝트 루트를
  `C:\Users\ksj74\OneDrive\Desktop\자동화\Bellalun Viewer` → **`C:\자동화\Bellalun Viewer`**
  로 옮겼다. 저장소 안의 산출물·기준 문서 경로는 모두 `ctx.root`/`__file__` 상대라
  **기능 코드 변경은 없다.**
- 갱신한 것: `config.json > checklist_xlsx`(다른 PC 경로가 박혀 있어 `""`로 비움 —
  `core/checklist.source_path`가 상위 탐색으로 스스로 찾는다), `core/dbreset.py`
  docstring 근거, `NEXT_WORK.md` 1절, `..\프로젝트_상세.md`(+`.html` 재생성),
  원격 자동화의 `C:\AI-Worker\config\worker.json`(`bellalun` 경로).
- 부수 효과 2건(둘 다 개선):
  - 프로필 밖으로 나가 SQL Server `NT AUTHORITY\LOCALSERVICE`가 `Baseline\`을 직접
    읽을 수 있게 됐다. `core/dbreset.py`의 복사-후-RESTORE는 PC 독립성 때문에 유지.
  - `tests/install_package_flow.py`의 `~\Desktop` 후보가 리디렉션 때문에 **실존하지
    않는 경로**를 보고 있었다(`C:\Users\ksj74\Desktop`가 없었음). 이제 정상화.
- `tests/install_package.install_log_dir()`는 `SHGetFolderPathW(CSIDL_PERSONAL)`로
  Documents를 셸에 물으므로 코드 변경이 필요 없었다. 실체 데이터(`Bellalun\InstallLog`)
  를 `OneDrive\문서` → `C:\Users\ksj74\Documents`로 함께 옮겨 기존 로그 3건 유지 확인.

## 2026-09-03 현재 상태

- **29차 전체 회귀 완료(2026-09-03 20:45~22:45, `Reports/Result_20260903_224518.json`,
  119.9분): PASS 23 / FAIL 2 / MANUAL 2. 자동화 결함 0건.** 남은 FAIL 2건(`WF_14`
  UPS 설정 미복원, `XIPL_03` 3D 파라미터 기본값 복귀)은 전부 이미 알려진 **제품
  결함**이라 완화하지 않는다. 28차와 TC 판정 완전히 동일 — 이번 회차에 추가한
  변경(아래)이 전체 회귀 경로에서 회귀를 만들지 않음을 확인했다.
- 이번 회차에 한 일:
  - `TC_XIPL_compatibility_07`에 "새 3D Preset이 그 시점 General Default를
    물려받는가" 보강 체크 추가(`probe-preset3d`로 3D-N/3D-W Preset 컨트롤
    ID 실측 → `core/flows.py` 상수화 → `tests/xipl_flows.py`에 헬퍼 신설).
    `automation_scope.json`의 gap 해소로 정정.
  - `run-sys3d`/`run-ui`에 남은 고정 대기를 상태 기반(`wait_new_group`/DB 행
    수 대기)으로 전환.
  - `TC_Basic_WorkFlow_13`(계정 권한별 Setting 노출)은 이미 2026-08-20에
    완전 자동화돼 있었음을 발견 — docstring/`--help`만 stale이라 문서만 정정.
  - stale 브랜치 `agent/add-next-task-handoff`는 이미 존재하지 않음 확인.
  - 회귀 진행률을 `work/regression_state.json`에 남기는 Hub/Worker 연동
    착수(커밋 `65d44d5`). `AI-Remote-Control`은 `hongmin3/AI-Remote-Control`
    (GitHub, private)로 위치 확인 — 이 세션 자체가 그 Issue(#24)로 디스패치된
    것이었다. `background_watch.py`의 실제 소비 로직은 아직 안 봤다.
  - 전체 회귀는 `tools/run_regression.py`를 완전히 분리된 백그라운드
    프로세스로 띄워 수행했다(세션 종료와 무관하게 계속 동작).
- 문서 동기화: `../프로젝트_상세.md`(B.34~B.36, 5.1/5.2절·기준 시점을 29차로)
  → `render_docs.py` → `README.md` → `NEXT_WORK.md` → 이 문서 순으로 갱신했다.

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 진행 중 작업: 없음. 이번 회차 요청 사항(WF_13/P1/P2/전체 회귀) 전부 완료.
- 남은 작업(사용자 자료 대기):
  - `Install_01`/`Install_02`는 사용자가 자료(Release Note, OS Build 목록)를
    줄 때까지 건드리지 않음(MANUAL/SKIP 유지).
  - Hub/Worker 연동 후속 — `AI-Remote-Control` 저장소의 `background_watch.py`
    실제 소비 로직 확인, 다음 필요 항목 설계.
- 알려진 문제: `NEXT_WORK.md` 3절 참고(제품 결함 3-A/XIPL_03, 간헐 증상
  3-B/3-C — 전부 자동화 결함 아님, 29차에서도 회귀 없음).
