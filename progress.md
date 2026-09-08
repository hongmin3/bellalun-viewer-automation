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
  Date 기준 독립 계산, 라이브 검증 PASS "46"). **Scheduled Date/Time도
  2026-09-08 완료** — 사용자 힌트(`Setting > Patient > Patient List >
  List Show Item`에 "Scheduled Study DateTime" 추가) 그대로 확인됨(기본
  꺼짐). `core/flows.py::ensure_scheduled_datetime_column()`(멱등 — 이미
  켜져 있으면 안 바꿈)와 `scroll_study_list_right()`(카드 열 전체 폭이
  화면보다 넓어 오른쪽으로 스크롤 필요, owner-draw라 고정 클릭 수 대신
  "기대 날짜 보일 때까지 조금씩 스크롤 반복" 방식)를 추가하고
  `tests/workflow01.py` Step 1에서 Patient List 카드를 OCR로 읽어 대조한다
  (Edit Information의 `study_datetime`은 Scheduled가 아니라 실제 Study
  일시라 여전히 안 씀). **라이브 검증: `TC_Basic_WorkFlow_01` 전체 PASS**
  (`Scheduled Date` 항목 포함, `Reports/Result_20260908_120515.json`).
  이 대조는 `r.add(..., stop=False)`로 넣어 owner-draw OCR 특유의 간헐
  실패가 TC 전체를 중단시키지 않게 방어해 뒀다.
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

1. ~~WU_02 Scheduled Date/Time 표시 위치~~ — **2026-09-08 완료**(위 참고).
2. **WU_09 USB Import 되읽기 — 핵심 원인 확정, 가설 (a)(b) 기각(2026-09-08
   이어서 조사)**. Import Study는 **DICOMDIR 포맷이 있어야만 인식한다** —
   일반 "DICOM" 포맷 Export(기존 WF_09/USB Export가 쓰는 것)는 DICOMDIR을
   안 만든다. `core/export_manager.py`에 `FORMAT_DICOMDIR`/`select_format()`/
   `set_portable_viewer()` 헬퍼를 정식으로 추가했고(`FORMAT_DICOM`도
   1008로 정정 — 기존 1009는 실제로 DICOMDIR 버튼이었다), `tests/
   winupdate.py::run_usb_export_import`가 Export 전에 이 둘을 선택하도록
   반영했다. 라이브로 DICOMDIR+Portable Viewer Export(Autorun.inf+
   PortView\ 전부 생성 확인, MG 데이터 정상)한 뒤, Import 경로를 정확한
   리프 폴더로 설정하고 **90초 폴링**, **드라이브 드롭다운(2062)을 경로
   설정보다 먼저 선택**하는 조합, **드라이브 우선 선택 + 키보드 트리 탐색**
   조합까지 전부 시도했지만 Import 목록(2066)은 항상 0행이었다 — **스캔
   대기 부족(가설 a)과 Autorun.inf/PortView 부재(가설 b)는 원인이 아니라고
   결론**. 남은 후보 (c) USB가 Import 기능이 요구하는 미디어 종류로 인식
   안 될 가능성, (d) DICOMDIR 스캔이 Windows AutoPlay/미디어 삽입 이벤트에
   매여 있어 이미 꽂힌 드라이브를 UI로 사후 탐색해선 트리거가 안 될 가능성
   — 상세는 `NEXT_WORK.md` 5절 ⑨ 참고.
   - **환경 버그 발견·수정(WU_09와 별개, 전체 라이브 자동화에 영향)**: 이
     조사 중 Windows **작업표시줄 자동 숨김이 꺼져 있어** Viewer 메인 메뉴
     버튼(화면 좌하단)을 작업표시줄이 덮어 클릭이 새는 문제를 발견했다
     (`blocking_window()`는 셸 창을 의도적으로 "가림 아님"으로 봐서 못
     잡는 케이스). `core/ui.py::taskbar_autohidden()`(SHAppBarMessage로
     임시 자동 숨김, 종료 시 원상복구 — `foreground_unlocked`와 같은
     패턴)을 추가하고 `run.py`의 `__main__`에서 함께 걸었다.
   - **2026-09-08 추가 조사(사용자 요청 — IMG 옵션, USB 드라이브 재확인)**:
     USB는 이번에도 **D:\ (VXvue1, REMOVABLE)** 로 동일하게 인식됨을 재확인
     (참고로 E:\ 는 빈 CD-ROM 드라이브). Export Manager의 File Format
     버튼은 **라디오 그룹이 아니라 독립 체크박스**임을 실측으로 정정했다
     (DICOMDIR+IMG를 동시에 체크한 채 Export하면 DICOMDIR 패키지에 IMG
     원본 덤프가 추가로 섞여 들어간다 — 이전 docstring이 "라디오 방식
     그룹"이라 잘못 적어 뒀던 것을 고쳤다). **IMG 단독**(DICOMDIR/Portable
     Viewer 전부 해제, `.img`+`.txt` 원본 픽셀 덤프만 생성 확인)으로도
     Import 목록은 여전히 0행 — **사용자의 IMG 가설도 기각.** 또한 Import
     목록이 0행인 채로 "Import" 버튼(2064)을 눌러 보면 "No study to
     import." 안내만 뜨고 숨은 스캔 트리거는 아니었다. 지금까지 DICOMDIR
     단독/DICOMDIR+Portable Viewer/DICOMDIR+IMG/IMG 단독 네 조합 모두
     실패 — **Export 포맷 조합이 원인일 가능성은 사실상 소진됐다**, 남은
     유력 후보는 NEXT_WORK.md ⑨의 (c)/(d)(USB 미디어 인식/AutoPlay 트리거)
     뿐이다.
3. ~~WU_09 xlsx 자동 기록 정책 재검토~~ — **2026-09-08 사용자 확정, 구현
   완료**. 기존 K열(Result) 삽입 방식은 유지하고, **K열 바로 옆에 L열
   (Comment)을 추가로 삽입**해 Fail/Manual TC에만 그 판정을 끌어낸 check의
   note(짧게, 최대 3개) 를 적도록 `core/winupdate_report.py`를 고쳤다
   (`_reason_for()` 신규 — Pass/Skip은 비워 둔다). 기존에 이미 있던 공용
   "Comment" 열(여러 회차가 공유하는 수기 메모)은 그대로 두고 자동화가
   덮어쓰지 않는다 — 이 새 L열과는 별개다. `--from-regression Reports/
   Result_20260903_224518.json`로 재생성해 FAIL 1건(WU_05)·MANUAL 3건
   (WU_01/12/13)에 Comment가 채워지고 PASS/SKIP 행은 비는 것을 확인했다.
   상단 1~4행 OS/OS Version/OS Build/Viewer Version 실측 기록은 이미
   2026-09-07에 구현돼 있었다(`_winupdate_env()`) — 그대로 유지.

### 변경/신규 파일

`tests/winupdate.py`(신규 — 매핑 표, 2026-09-08 이어서 DICOMDIR 포맷/
Portable Viewer 선택 추가), `core/winupdate_report.py`(신규 — WU
xlsx writer), `core/usb_media.py`(신규 — USB 탐지+Import 시도), `run.py`
(`run-winupdate`/`--from-regression` CLI, 2026-09-08 이어서 `__main__`에
`taskbar_autohidden()` 추가), `core/sysinfo.py`(`os_update_info` 추가),
`core/viewer_tools.py`(Select/Rotate CW/CCW), `tests/workflow01.py`
(Age/Scheduled 대조 추가 — WF_01 자체도 고도화됨), `core/export_manager.py`
(2026-09-08 이어서 — `FORMAT_DICOM` 1008로 정정, `FORMAT_DICOMDIR` 등 File
Format 상수 전부 추가, `select_format()`/`set_portable_viewer()` 신규,
File Format이 체크박스임을 반영해 docstring 정정), `core/ui.py`(2026-09-08
이어서 — `taskbar_autohidden()` 신규, 환경 버그 수정), `core/winupdate_report.py`
(2026-09-08 이어서 — L열 Comment 신규, `_reason_for()` 신규).

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
