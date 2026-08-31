# Progress Checkpoint

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: P0 개별 검증을 순서대로 끝내는 중이다. **`cold_start` 주 모니터 가드
  검증(P0)을 완료했고, 그 과정에서 가드가 절반만 걸려 있던 결함을 찾아 고쳤다(아래).**
  다음은 (a) "목록 전 행 열거 완주" 수정 방향에 대한 사용자 합의(`NEXT_WORK.md` 5절 ⑦),
  (b) `WF_04→06`/`WF_13`/`WF_15`/`XIPL_05` 개별 재검증, (c) 전체 회귀다.

- 이번 세션의 특수 사정: Claude Desktop에서 진행 중이던 세션이 세션 한도로 끊겼다.
  **끊긴 세션의 대화 내용 자체는 이 세션에서 접근할 수 없어서**, git 커밋 이력·
  커밋되지 않은 `README.md` diff·`Reports/`의 파일 타임스탬프만으로 어디까지
  했는지를 역추적해 재구성했다. 재구성 결과가 실제 작업 의도와 다르면 정정이
  필요할 수 있다.

- 재구성으로 확인한, 마지막 커밋(`1b44250`, 09:27) 이후 있었던 일(전부
  `Reports/Result_20260831_*.json`의 `meta.command`/`verdict`로 재확인함):
  1. `run-wf07` 3회 연속 PASS(09:15~09:23) — 직전 커밋의 `close_examine_confirmed`
     확인 실행으로 보인다(이미 커밋에 반영됨, 재확인만 된 상태).
  2. `setup-storage` → `run-wf10` FAIL(09:33~09:36) — Step 3 Hospital Code Mapping
     콤보(2453)가 비활성이라 열리지 않음. MWL이 없어서였다.
  3. `setup-dicom` → `run-wf10` **PASS 11/11**(09:39~09:43) — `HC`가
     `Mammography (Rt)`에 매핑되고 MWL 처방 등록·조회·`STUDY.ProcedureKey` 반영·
     Examine Step 등록까지 전부 확인됨. **P0 #3(`run-wf10` 매핑 검증) 완료.**
  4. `setup-dicom` 재실행(09:48) 후 `run-wf14` 연속 3회(10:09/10:40/11:13) —
     원래 찾던 "`my_settings`(193) 진입 실패"(3-C)는 재현되지 않았다. 대신:
     - 1차: Step 7 "설정 테이블 전수 대조" 13개 섹션 불일치로 조기 중단.
     - 2·3차: Step 7 "목록 전 행 열거 완주"에서 다수 페이지 행 수 불일치 발생 후
       `KeyError: 'changed'`로 TC 자체가 중단됨.
  5. `README.md`가 위 2·3번 결과를 반영해 수정됐지만(`setup-storage`→`setup-dicom`
     정정, 증상별 표 추가) **커밋되지 않은 채로 남아 있었다** — 이번 세션에서 diff를
     확인해 그대로 유지·커밋 대상에 포함시켰다.

- 이번 세션에 새로 한 작업:
  - **`KeyError: 'changed'` 원인 규명 및 수정.** `tests/workflow14.py:547~559`가
    `core/setting_lists.compare_sweep()`의 반환값에서 존재하지 않는 `"changed"` 키를
    참조했다 — 실제로는 집계용 `"changed_total"`(정수)과 페이지별
    `"pages"[페이지]["changed"]`(목록)뿐이다. `compare()`(단일 페이지, 행→상세값)에는
    `"changed"` 키가 있어서 두 함수를 혼동한 것으로 보인다. Step 7(a)("설정 테이블
    전수 대조")가 먼저 FAIL 해 TC가 조기 중단되는 경로(1차 실행)에서는 이 줄에
    도달하지 않아 지금까지 드러나지 않았다. `lc["changed"]` → `lc["changed_total"]`로,
    `lc["changed"][:20]` → 페이지별 `changed`를 펼친 목록(`lc_changed`)으로 고쳤다.
  - 회귀 방지 단위시험 2건 신설(`tests/test_setting_lists.py::CompareSweepTest`) —
    `compare_sweep()` 반환에 `"changed"` 키가 없음을 명시적으로 확인하고, 픽스와 같은
    방식(페이지 순회로 펼치기)으로 값이 올바르게 나오는지 검증한다.
  - 정적 검사 전부 통과(`check_module_attrs`의 `tests/install_package_flow.py:310`
    경고는 기존 것 — `NEXT_WORK.md` 6절에 이미 무시 대상으로 기록돼 있다),
    단위시험 94 → **96건 OK**.
  - `NEXT_WORK.md`를 2-D절 신설로 갱신(위 1~4번 재구성 내용 + 결함 원인·수정 내용),
    3절 #9/#10, 4절 P0 목록, 6절 프롬프트를 현재 상태로 정정.

- **이번 세션(사용량 한도 재설정 후 이어받음)에 새로 한 작업 — 주 모니터 가드 P0 검증과
  결함 수정.**
  - 이 PC 는 모니터가 1개(`EnumDisplayMonitors` 1개, 가상 화면 = 주 모니터 1920x1080)라
    "주 모니터 밖"을 만들 수 없어 보였지만, 가드 조건이 **좌표 기반**
    (`0 <= left < max_w and 0 <= top < max_h`)이라 창을 `(-600, 100)` 으로 옮기면 같은
    분기를 그대로 탄다. `SetWindowPos` 로 옮겼다가 `finally` 로 원위치시키는 일회성
    진단으로 검증했다(스크립트는 저장소에 두지 않았다).
  - **발견: 재사용 경로가 가드를 아예 평가하지 않았다.** 가드가 `cold_start` 의
    기동/로그인 경로에만 있었고 **재사용 분기가 그보다 먼저 `return`** 한다.
    `config.json` 의 `viewer.force_restart` 가 `None`(=재사용)이라
    `WF_01`/`WF_05`/`run-ui` 등은 창이 어긋나 있어도 그대로 진행했다는 뜻이다.
    창을 옮긴 뒤 `cold_start(force_restart=False)` 가 **중단 없이 정상 반환**하는 것으로
    확인했다.
  - 가드를 `core/flows.require_primary_monitor(ui)` 로 뽑아 두 경로가 같은 검사를 쓰게
    고쳤다. 재사용 경로에서는 팝업 정리(`DialogGuard.sweep`, 클릭이 일어난다)보다
    **먼저** 확인한다.
  - 재검증(라이브): 밖 `(-600,100)` → **중단 + 창 위치 그대로**(자동화가 옮기지 않음) /
    안 `(0,0)` → 정상 재사용·로그인 / 기동 경로(`force_restart=True`) → 정상 재기동·로그인.
  - 단위시험 7건 신설(`tests/test_primary_monitor_guard.py`) — 안/밖/우측 이탈/창 미발견에
    더해 **재사용 경로가 검사를 거친다는 것**과 **클릭보다 먼저 막는다는 것**을 고정.
    정적 검사 전부 통과, 단위시험 96 → **103건 OK**.
  - 문서: `../프로젝트_상세.md` 0.1절 갱신 → `render_docs.py` 재생성(`check_docs_sync` OK)
    → `NEXT_WORK.md`(2-E절 신설, 2절 표, 3절 #11, 4절 P0 #2·#4, 5절 ⑦ 신설, 6절 프롬프트).

- 진행 중 작업: 없음.

- **`KeyError` 픽스 라이브 검증 완료(같은 세션).** `run-wf14`를 다시 돌렸다
  (`Reports/Result_20260831_115710.json`, 1819초). Step 7(c) "Setting 목록 행 상세값
  복원"이 예외 없이 **PASS**(123행/1820항목, 달라진 항목 0)로 판정됐다 — 픽스가
  라이브로 확인됐다. TC 전체는 FAIL로 끝났지만 원인은 `device.ups` UPS 설정이 복원
  안 되는, **이미 알려져 완화하지 않기로 한 제품 결함**(3-A/B.22)이었다 — 새로 생긴
  문제가 아니다. 원래 3-C 증상(`my_settings` 진입 실패)은 이번에도 재현 안 됨(연속
  4회 모두 미재현).

  **대신 새로 드러난 문제 — "목록 전 행 열거 완주" 서브체크의 근본 원인을 라이브로
  확인했다(사용자 요청으로 이어서 조사).** 로그인된 Viewer에 직접 붙어
  `system.account`/`patient.physician`의 행을 자식 컨트롤 텍스트와 화면 OCR로 각각
  읽어 비교했다(일회성 진단 스크립트, 결과만 남기고 삭제). 원인은 두 가지다:
  - **행이 owner-draw라 자식 창이 없다.** `system.account`의 두 행은
    `children(row.hwnd, 3)`로는 0개지만, 그 rect를 OCR 하면 `service`/`admin` 계정이
    실제로 그려져 있다 — `row_signature()`가 전제하는 "자식 컨트롤 WM_GETTEXT"로는
    원천적으로 못 읽는 구조다.
  - **`patient.physician`은 애초에 엉뚱한 목록을 보고 있다.** `visible_rows()`가 잡은
    "3행"을 OCR 하면 실제 의사 명단이 아니라 `'1. Scheduled Performing Physician
    (MWL)'` 등 MWL 역할 매핑 콤보다 — `PHYSICIAN` 테이블(0행)과 애초에 무관한 화면
    요소를 비교하고 있었다.

  두 원인 모두 `stop=False` 서브체크 안에 갇혀 다른 판정(Step 7(c) 실제 값 대조,
  PASS)을 오염시키지 않아 2026-08-27 도입 이후 계속 이 상태였는데도 드러나지 않았다.
  **제품 결함이 아니라 자동화의 읽기 방식이 이 컨트롤 구조에 안 맞는 것이다.** 개선
  방향(OCR 기반 `row_signature()` 재설계 + `LIST_PAGES` 페이지 매핑 전수 재확인)은
  `NEXT_WORK.md` 2-D절에 남겼다 — **구현은 아직 하지 않았다.** 범위가 `core/setting_lists.py`
  전반의 재설계라 세션 하나에 다 넣기보다 사용자와 방향을 합의한 뒤 별도로 진행하는
  편이 낫다고 판단했다.

- 남은 작업(다음 세션 시작점):
  1. **"목록 전 행 열거 완주" 수정 방향을 사용자와 합의한 뒤 구현**
     (`NEXT_WORK.md` 5절 ⑦에 선택지 3개로 정리해 뒀다). 원인은 이미 확정됐다 —
     (a) `row_signature()`를 OCR 기반으로 재설계, (b) `patient.physician`을 포함해
     `LIST_PAGES`의 각 페이지가 올바른 화면 요소를 보는지 전수 재확인.
     `core/setting_lists.py` 전반의 재설계라 Plan First로 접근한다.
  2. `WF_04→06`·`WF_13`·`WF_15`·`XIPL_05` 개별 재검증. **합의 없이 바로 할 수 있는
     다음 실행 항목이다.**
  3. 전체 회귀 재실행(위가 모두 끝난 뒤).

- 중요한 설계 결정:
  - **원래 목표 증상(3-C)을 재현하려는 시도가 다른 결함을 드러냈을 때, 원래 목표를
    억지로 재현하려 하지 않고 드러난 결함부터 원인을 규명한다.** `KeyError`는 TC
    자체를 중단시켜 그 뒤의 어떤 판정도 신뢰할 수 없게 만들므로, 이걸 먼저 고치지
    않으면 3-C 재현율 측정 자체가 의미가 없다.
  - **DB 등록 상태(`setup-storage` vs `setup-dicom`)가 TC마다 다른 전제를 요구할 수
    있다.** `run-wf07`은 Storage만 있으면 충분했지만 `run-wf10`은 MWL이 반드시
    필요했다 — "DICOM 서버 등록이 필요하다"를 한 종류로 뭉뚱그리지 않고 TC별로
    실측했다.
  - 세션이 끊겼을 때 **대화 내용을 추측으로 재구성하지 않고**, git 커밋·미커밋 diff·
    산출물 타임스탬프처럼 검증 가능한 근거만으로 재구성한 뒤 그 사실을 문서에 명시했다
    (재구성이 틀렸을 가능성을 사용자가 확인할 수 있도록).

- 변경 파일(이번 세션): `core/flows.py`(`require_primary_monitor` 신설, 기동·재사용
  두 경로가 공용 사용), `tests/test_primary_monitor_guard.py`(신설),
  `../프로젝트_상세.md`(+렌더링 `.html`), `NEXT_WORK.md`, `progress.md`.
- 변경 파일(직전 세션): `tests/workflow14.py`(`compare_sweep` 반환 키 수정),
  `tests/test_setting_lists.py`(`CompareSweepTest` 신설), `NEXT_WORK.md`(2-D절 신설,
  3절/4절/6절 갱신), `README.md`(직전 세션이 수정한 것을 그대로 유지 — `setup-dicom`
  선행 조건 정정 + MWL/Storage 증상별 표), `progress.md`.

- 알려진 문제:
  - "목록 전 행 열거 완주" 서브체크가 왜 대부분의 목록 페이지에서 실패하는지 원인
    미확인(위 참고). Step 7 "설정 테이블 전수 대조" 13개 섹션 불일치(1차 실행에서만
    관측, 이번 재실행에서는 재현 안 됨)는 09:48 `setup-dicom` 재실행과 시간이 겹친
    환경 오염이었을 가능성이 높아졌다 — 이번 실행은 "설정 테이블 전수 대조"가 PASS 했다.
  - 이 세션은 Claude Code(CLI)에서 진행됐고 직전은 Claude Desktop이었다 — 세션 간
    대화 인계 수단이 없어 이번처럼 리포트·git 이력 역추적에 의존해야 했다. 앞으로도
    같은 상황이 생기면 이 checkpoint 파일이 얼마나 최신인지가 인계 품질을 좌우한다.
