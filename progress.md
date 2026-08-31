# Progress Checkpoint

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: `NEXT_WORK.md` P0 순서대로 계속한다. 바로 다음 할 일은 이번 세션에서
  고친 `KeyError: 'changed'` 픽스를 `run-wf14` 라이브 재실행으로 검증하는 것이다.

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

- 진행 중 작업: 없음. 코드 수정과 단위시험은 끝났고 **라이브 재검증은 아직**이다.

- 남은 작업(다음 세션 시작점):
  1. `run-wf14`를 다시 돌려 `KeyError` 픽스가 실제로 통하는지 확인한다 — 예외 없이
     Step 7까지 판정이 나와야 한다. 그 뒤 목록 행 수 불일치·설정 테이블 13개 섹션
     불일치가 재현되면, 재현되는 섹션이 DICOM 관련뿐인지(→ 09:48 `setup-dicom` 재실행과
     타이밍이 겹친 환경 오염일 가능성) 아니면 `reset-environment`로 완전히 새로
     시작해도 재현되는지(→ 진짜 Import 복원 결함) 구분해야 한다.
  2. 위가 안정되면 원래 3-C(`my_settings` 진입 실패) 재현율도 계속 지켜본다.
  3. 주 모니터 **밖**에서 `cold_start` 안전 중단 확인(안쪽 정상 로그인은 확인됨).
  4. `WF_04→06`·`WF_13`·`WF_15`·`XIPL_05` 개별 재검증.
  5. 전체 회귀 재실행(위가 모두 끝난 뒤).

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

- 변경 파일: `tests/workflow14.py`(`compare_sweep` 반환 키 수정),
  `tests/test_setting_lists.py`(`CompareSweepTest` 신설), `NEXT_WORK.md`(2-D절 신설,
  3절/4절/6절 갱신), `README.md`(직전 세션이 수정한 것을 그대로 유지 — `setup-dicom`
  선행 조건 정정 + MWL/Storage 증상별 표), `progress.md`.

- 알려진 문제:
  - `run-wf14`의 `KeyError` 픽스는 **정적 검사·단위시험만 통과했고 라이브로는 아직
    확인 못 했다.** 다음 세션 첫 실행 항목이다.
  - Step 7 "설정 테이블 전수 대조" 13개 섹션 불일치와 "목록 전 행 열거 완주" 다수
    페이지 행 수 불일치가 **진짜 제품/자동화 결함인지, `setup-dicom` 재실행 타이밍과
    겹친 환경 오염인지 아직 나누지 못했다.**
  - 이 세션은 Claude Code(CLI)에서 진행됐고 직전은 Claude Desktop이었다 — 세션 간
    대화 인계 수단이 없어 이번처럼 리포트·git 이력 역추적에 의존해야 했다. 앞으로도
    같은 상황이 생기면 이 checkpoint 파일이 얼마나 최신인지가 인계 품질을 좌우한다.
