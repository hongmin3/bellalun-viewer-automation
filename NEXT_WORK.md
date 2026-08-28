# 다음 작업 (2026-08-28 기준)

> **문서 지도 — 이 문서의 역할과 다른 3개 문서와의 관계**
> 이 문서는 **현재 상태와 다음에 할 일**만 담는다 — 최신 회귀 결과, 이번 회차에 바꾼 것, 남은 문제, P0/P1/P2, **사용자 판단이 필요한 항목(5절)**, 다음 세션용 프롬프트(6절).
> **영구 규칙**은 `AGENTS.md`, **영구 구현 규칙과 사고 이력**은 `..\지식\[자동화 운영 지침] ...md` 에 있다. 과거에 실측으로 확정한 컨트롤 ID·제품 동작은 **코드 상수·docstring** 과 `automation_scope.json` / `traceability.json` 에 있고, 그 경위는 `git log` 로 찾는다(2026-08-28 부로 `NEXT_TASK.md` 는 폐지).
> **읽는 순서 — `README.md` 최상단 "온보딩 요약" → `AGENTS.md` → 이 문서 → `[자동화 운영 지침]`(상단 "증상 → 원인 → 조치" 색인부터).**

---

## 1. 현재 상태

| 항목 | 값 | 근거 |
|---|---|---|
| 기준 문서 | `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC` — TC 37건 | `WF_14` Step 3 문구는 2026-08-28 사용자 승인으로 수정(원본은 `..\Baseline\Checklist_개정본_20260828_WF14Step3수정전.xlsx`) |
| 자동화 범위 | 완전자동 20 / 부분자동 7 / 수동 10 (+ 보조 4) | `python run.py list` |
| **최신 전체 회귀** | 26차, 2026-08-26 18:52~20:28 — TC 27건: PASS 22 / FAIL 2 / MANUAL 2 / BLOCKED 1, 검증 275개: PASS 261 / FAIL 7 / MANUAL 3 / SKIP 1 / BLOCKED 3, 96.3분. 남은 FAIL 2건은 둘 다 제품 결함 | `Reports/Result_20260826_202818.json` |
| 문서 구조 | `AGENTS.md`/`README.md`/`NEXT_WORK.md`/`..\프로젝트_상세.md` 4개로 유지. `NEXT_TASK.md`·`PORTABILITY_AUDIT.md`·`tools/prune_docs.py` 는 2026-08-28 폐지(아래 2절) | `AGENTS.md` "문서 수명 정책" |
| **오늘(08-28) 이후 회귀 미실행** | 아래 2절의 수정 사항은 개별 TC 단위로만 검증했다. 전체 회귀 재실행이 필요하다 | — |

---

## 2. 2026-08-28 회차 — 버그 수정 및 문서 구조 정리

### 코드 수정 (검증 상태 포함)

| 수정 | 내용 | 검증 |
|---|---|---|
| `WF_04` 종료 시 View 닫기 | `flows.close_view_study` 추가. `WF_04`가 View 로 연 검사를 닫지 않고 끝나 뒤따른 `WF_06`이 Examined 검색 컨트롤(2177/2178/2179)을 못 찾던 문제 | 코드 반영. `run-wf04`→`run-wf06` 연쇄 재검증 대기 |
| 로그인 ID 콤보 견고화 | `flows.select_login_id` — OCR 선택 실패 시 항목을 하나씩 눌러 `current_login_id()`로 확인하며 재시도(`_click_general_param_combo`와 같은 방식) | 코드 반영. `run-wf13` 재검증 대기 |
| `XIPL_04` 2D Default Parameter 원복 | Step 1 이 바꾼 `PROCEDURE_COMMON.DefaultImgProcess` 를 `finally`에서 UI로 원복(`_restore_default_2d_param`) | **`run-xipl-04` 전 Step PASS, 원복도 `Standard_Default_M.pim`으로 확인(2026-08-28)** |
| `XIPL_05` Q.C 채점을 좌표 대신 임계값으로 | 화면 절대좌표 대신 `CONFIGURATION.QC_COMMON`의 합격 기준을 DB로 읽어 OCR로 경계값을 고르고, 합격/불합격 경계 양쪽을 검증(5절 ① 판단 반영 — Result는 별도 항목으로 분리) | **PASS(MANUAL 1) 확인(2026-08-28 재검증).** Step 3~5 전부 PASS. Fiber 콤보에 기준(4.0) 미만 항목 자체가 없어 불합격 경계 하나만 MANUAL — 자동화 결함이 아니라 콤보 항목 구성의 한계(3절 #1) |
| `WF_15` Dose Overlay 전제 자체 보장 | 단독 실행 시 `WF_03`을 거치지 않으면 선량 Overlay(115/118)가 없어 Step 3 이 전제 미충족으로 FAIL 하던 것을, `vp.add_image_overlay_items`로 멱등하게 준비 | 코드 반영. `run-wf15` 단독 실행 재검증 대기 |
| `core/ui.py` 포그라운드 잠금 타임아웃 | `force_foreground`가 `SPI_FOREGROUNDLOCKTIMEOUT`을 0으로 낮췄다가 복원 — 잠금이 남아 있으면 `AttachThreadInput`을 붙여도 전환이 거부됨 | 코드 반영 |
| `core/ui.py` 클릭 가드 — 다중 모니터 겹침 인식 | `require_front_for_pointer`가 "다른 창이 최전면"이라는 사실만으로 막던 것을, **그 창이 클릭 좌표를 실제로 화면에서 덮고 있는지**까지 확인하도록 바꿈(`_rect_contains_point`). 다른 모니터의 창은 Viewer를 가리지 않으므로 막지 않는다(2026-08-28 사용자 지시) | `run-xipl-05` 재검증으로 확인 |
| `core/ui.py` `bring_to_front`가 항상 메인 프레임만 올리던 문제 | Q.C 테스트 창처럼 메인 프레임과 다른 최상위 창을 조작 중일 때, 최전면 복구가 메인 프레임을 올려 오히려 그 창을 가리는 문제를 고침 — 클릭 좌표를 실제로 담고 있는 창(`_window_at_point`)을 우선 올린다 | `run-xipl-05` 재검증으로 확인 |
| `tests/xipl_flows.py` `_qc_recover` 1회 클릭 → 재시도 루프 | Q.C 콤보 팝업이 마우스를 잡고 있을 때 첫 클릭이 Cancel이 아니라 팝업만 닫아, 창이 안 닫힌 채 남던 문제. Cancel이 안 보일 때까지(최대 3회) 반복 | `run-xipl-05` 재검증으로 확인 — 이제 Step 4·5까지 정상 진행 |
| `WF_10` 비기본 Procedure 매핑 | Hospital Code `HC`를 기본값 `Routine Mammography` 대신 `Mammography (Rt)`에 매핑한다. 기본값 사용 시 매핑 실패가 제품 기본값으로 가려질 수 있어 거짓 PASS를 막기 위한 변경 | 코드 반영. `run-wf10`으로 MappingKey, Study ProcedureKey, Step 수와 Examine 준비 상태 재검증 대기 |
| `cold_start` 주 모니터 이탈 중단 | Viewer 창이 주 모니터 좌표 범위 밖이면 강제 이동하지 않고 오류로 중단한다. 다중 모니터/DPI 가상화에서 자동 이동이 잘못된 모니터로 창을 옮긴 사례를 방지 | 코드 반영. 주 모니터 밖에서는 안전 중단, 안에서는 정상 로그인하는지 실제 UI 검증 대기 |
| 로그인 전용 스모크 도구 | `_login_check.py`가 TC 수행 없이 `cold_start()`를 1회 호출해 Viewer 실행·로그인만 확인 | 코드 반영. 위 창 위치 보호 로직의 좁은 스모크 검증에 사용 가능 |

### 중단된 전체 회귀

- 2026-08-28 15:16경 `python tools/run_regression.py`로 전체 회귀를 시작했으나 세션 만료 후
  사용자 요청으로 감시 프로세스와 `run.py run-regression` 자식 프로세스를 종료했다.
- 종료 직전 생성물 메타데이터는 `Evidence/Flow/14_Setting` 갱신을 보이지만 완료 리포트가
  아니므로 `WF_14` 완료/PASS나 새 전체 회귀 결과로 기록하지 않는다.
- 아래 미검증 변경을 개별 검증한 뒤 전체 회귀를 처음부터 다시 실행해야 한다.

### 문서 구조 정리 (2026-08-28)

- **`NEXT_TASK.md`(542줄) 삭제.** 절별로 코드 대조해 실측 지식(컨트롤 ID·DB 구조·`.img` 구조 등)이 이미 `core/flows.py`, `core/imginfo.py`, `core/export_manager.py`, `tests/xipl_flows.py`, `automation_scope.json`에 옮겨져 있음을 확인한 뒤 지웠다. Dose SR MANUAL 사유 등 일부 내용은 이미 아래 3절/1-F(git 이력)로 대체돼 있었다.
- **`PORTABILITY_AUDIT.md` 삭제.** 아무 문서·코드도 참조하지 않는 고아 파일이었고, 내용은 `README.md` "다른 PC로 옮길 때" 절에 이미 반영돼 있었다.
- **`tools/prune_docs.py` 삭제.** "끝난 기록을 `Archive/`로 내린다"는 옛 정책 도구인데, 새 정책("문서는 4개로 유지, 완료 기록은 git 이력에 맡긴다")으로 대체됐다. 이미 내려간 `Archive/*.md` 2개는 과거 기록으로 그대로 둔다.
- `tests/workflow13.py`의 `NEXT_TASK.md` 참조를 이 문서 5절로 옮겼다.

---

## 3. 남은 문제

| # | 문제 | 우선순위 |
|---|---|---|
| 1 | `TC_XIPL_compatibility_05` Fiber 콤보에 합격 기준(4.0) 미만 항목이 없어 불합격 경계 검증이 MANUAL로 남는다(TC 전체는 정상적으로 MANUAL 판정까지 끝난다 — 크래시 아님, 2026-08-28 재검증) | P2 |
| 2 | `TC_XIPL_compatibility_03` Step 9 — 제품 결함. 완화하지 않는다 | 제품 수정 대기 |
| 3 | 3D Preset 목록·추가·삭제 컨트롤 ID 미실측 → "새 Preset 이 Default 를 물려받는가" 미판정 | P1 |
| 4 | `flows.demo_acquire_step(settle=14)` 고정 대기 — 2026-08-28 실측(26차 회귀 로그 분석)으로 위치를 정정함: 회귀에 포함된 곳은 `tests/workflow07.py:230`(WF_07)과 `tests/xipl_flows.py:1181/1185/1187`(XIPL_04)뿐이다. `run-sys3d`(`tests/system_compat.py:207`, 명시적 settle=20)와 `run-ui`/`run-auto`(`tests/ui_flows.py:206`)는 회귀에 포함되지 않는 별도 명령이다. **`WF_02`는 이미 `settle=0` + DB 폴링(`_wait_types`)으로 상태 기반 대기로 전환돼 있다 — 옛 서술은 구식.** `workflow07.py:230`은 이미 자체 DB 폴링(최대 60초)으로 재확인하므로 그 앞 고정 sleep은 그 호출부에서는 중복이지만, `xipl_flows.py`의 호출부는 후속 폴링 없이 고정 sleep에만 의존해 공용 함수 기본값을 그대로 바꾸면 안전망이 없다 — 콜사이트별로 나눠 처리해야 한다 | P1 |
| 5 | 중단 정책 때문에 `XIPL_03` Step 10 의 "GPU 없음 SKIP" 기록이 사라진다 | P2(맞바꾼 것) |
| 6 | 추적성 미연결 13건 — `Install_01` 외 12건은 전부 미구현 | P2 |
| 7 | **UPS 설정이 Setting Export/Import 범위 밖이다** — 아래 3-A | 제품 수정 대기 |
| 8 | **Setting 페이지 순회 중 Viewer 가 종료되는 경우가 있다**(간헐) — 아래 3-B | 조사 계속 |
| 9 | **`WF_14` 진입이 간헐적으로 실패한다**(`my_settings` ID 193 미발견) — 아래 3-C | P0 |
| 10 | **`WF_10`의 `HC` → `Mammography (Rt)` 비기본 Procedure 매핑 변경이 미검증** — DB MappingKey/ProcedureKey, Step 수, Examine Ready를 함께 확인해야 한다 | P0 |
| 11 | **`cold_start` 주 모니터 이탈 중단 로직이 미검증** — 밖에서는 안전 중단하고 안에서는 정상 로그인이 계속돼야 한다 | P0 |

### 3-A. UPS 설정이 Export/Import 로 복원되지 않는다 (제품 결함, 사용자 확인 완료)

`Setting > Device > UPS` 값은 저장은 되지만 `.vms` 20개 항목·DB 3종·`ExternalInput.xml`·
레지스트리 어디에도 실리지 않는다(전수 확인). 사양서1 60절은 Export 대상을 "Study 정보를
제외한 모든 설정 정보"로 정의하므로 `WF_14` Step 7 판정에 넣었고 완화하지 않는다.

### 3-B. Setting 전 페이지 순회 중 Viewer 가 종료된다 (간헐, 원인 미특정)

51개 페이지를 읽은 뒤 Q.C. 그룹에서 4회 재현됐으나, 그룹 순서를 뒤집으면 56페이지
모두 정상이었다(GDI/USER 핸들이 더 높은데도). 최소 재현(3페이지)으로는 재현되지 않는다
— 간헐적이다. `read_all`이 소멸을 감지하면 순회를 멈추고 `viewer_died`를 남기며, `WF_14`는
재기동해 본 시험을 끝까지 수행한다. 페이지당 GDI 약 50·USER 약 82 증가가 함께 관측된다.

### 3-C. `WF_14` 진입 실패 — `my_settings`(193) 미발견 (간헐)

같은 코드로 19분 전 실행은 PASS(18/18)했는데 다음 실행이 진입에서
`System 설정 'my_settings'(ID 193)을 찾지 못했습니다`로 실패했다(정리/원복은 정상 수행).
3-B와 같은 계열(Setting 진입 직후 화면 불안정)일 수 있으나 진입과 순회-중은 다르므로
단정하지 않는다. **다음에 할 것**: `reset-environment` 후 `run-wf14` 연속 3회로 재현율을
잰다.

---

## 4. 우선순위

### P0

1. `WF_14` 간헐적 진입 실패 재현율 확인(3-C).
2. `run-wf10`으로 `HC`가 비기본 Procedure `Mammography (Rt)`에 실제 매핑되고 해당
   Procedure Step이 등록되는지 검증한다. 기본 Procedure로 조용히 대체된 결과를 PASS로
   인정하지 않는다.
3. 주 모니터 밖/안 조건에서 `cold_start` 안전 중단과 정상 로그인을 각각 확인한다.
4. 남은 미검증 항목(`run-wf04`→`run-wf06` 연쇄, `run-wf13`, `run-wf15` 단독 실행)을
   재검증한 뒤 전체 회귀 1회 실행. `run-xipl-04`/`run-xipl-05`는 2026-08-28 확인 완료.

### P1

5. **자동화 리팩터링과 속도 개선을 다음 개발의 중심으로 둔다.** 먼저 개별 TC/공용 흐름의
   구간별 시간을 측정해 병목을 기록하고, 고정 `sleep`·중복 화면 전환·중복 로그인/검색을
   우선 줄인다. 판정 기준·Workflow 순서·제품 상태 변경 방식은 유지하고, 변경 전후 실행
   시간과 동일 판정 결과를 함께 검증한다.
6. `python run.py probe-preset3d` 로 3D-N/3D-W Preset 목록 컨트롤 실측 → `core/flows.py`
   상수로 기록.
7. 그 위에 "새 3D Preset 이 그 시점 Default 를 물려받는가"(Service Manual 근거)를
   `XIPL_07` 에 추가.
8. 속도 개선의 첫 구체 항목으로 `demo_acquire_step`의 고정 대기를 상태 기반 대기로
   전환하고 `run-wf07`/`run-xipl-04` 시간을 비교한다(실제 위치는 3절 #4 참고 —
   `WF_01`/`WF_02`/`run-sys3d`가 아니다). 공용 함수라 콜사이트별 안전망 차이를 먼저
   확인해야 한다.

### P2

9. `flows.close_examine` 의 no-dialog 경로 상태 신호화.
10. 추적성 미확정 중 `Install_01` — 검증 대상 Release Note 를 받으면 확보 가능.
11. `XIPL_05` Fiber 콤보 항목 구성 재검토(3절 #1) — 급하지 않다.

---

## 5. 사용자 판단이 필요한 항목

### ① `Install_01` — 검증 대상 Release Note

`config.json > release_note` 가 2026-08-10 캡처 baseline 이고 `_source` 에 "교체
필요" 로 표시돼 있다. 실제 검증 대상 Release Note 를 주시면 `Install_01` 을
MANUAL → 자동 판정으로 올리고 추적성도 연결할 수 있다.

### ② `Install_02` — 지원 OS Build 목록과 DICOM 어댑터 별칭

`config.json > prerequisites.dicom_nic_alias` 와 지원 OS Build 기준을 주시면
현재 SKIP 인 항목을 자동 판정으로 바꿀 수 있다.

### ③ 중단 정책이 맞바꾼 것

FAIL 이 나면 그 TC 를 중단하므로 첫 FAIL 뒤의 판정 정보는 수집되지 않는다(3절 #5).
원하시면 `config.json > regression.stop_tc_on_fail` 을 `false` 로 두면 예전처럼 끝까지
수행한다.

### ④ `TC_Basic_WorkFlow_13` Step 4~6 — 로그인 계정 전환을 자동화할지

로그오프 후 시험 계정으로 로그인하면 회귀의 나머지 TC 가 권한이 제한된 계정으로
실행된다. 중간에 실패하면 로그인 상태를 복구하지 못해 뒤따르는 TC 가 연쇄로 무너진
전례가 있다(회귀 7·13·14차). 복구 절차를 합의한 뒤에만 붙인다.

### ⑤ 스테일 브랜치 `agent/add-next-task-handoff` 삭제

2026-08-11 에 판 작업용 브랜치이고 `main`의 조상(고유 커밋 0개, `git diff` 비어 있음
— 2026-08-25 실측)이라 지워도 내용은 잃지 않는다. 로컬·`origin` 양쪽에 남아 있다.
승인하시면:

```bash
git branch -d agent/add-next-task-handoff
git push origin --delete agent/add-next-task-handoff
```

---

## 6. 다음 세션용 프롬프트

```text
Bellalun Viewer QA 자동화를 이어서 진행해줘.

이번 세션의 개발 초점은 **자동화 리팩터링과 실행 속도 개선**이다. 단순히 전체 회귀를
다시 돌리는 데 그치지 말고, 현재 TC 판정 기준과 Workflow 순서를 보존하면서 실제 병목을
측정하고 공용 흐름의 중복과 고정 대기를 줄여라. 추측으로 sleep 값을 낮추지 말고 상태 기반
대기로 바꾸며, 변경 전후 실행 시간과 판정 결과가 동일한지 증거를 남겨라.

먼저 auto/AGENTS.md, auto/README.md, auto/NEXT_WORK.md, ..\프로젝트_상세.md,
그리고 지식 폴더의 영구 지침 3종([QA 작성 규칙]/[자동화 구현 현황]/[자동화 운영 지침])을 읽어 현재
상태와 규칙을 파악해라. TC 원문은 Bellalun_Viewer_기본기능_Checklist_개정본.xlsx의
`개정 TC` 시트만 기준으로 삼는다.

가장 먼저 python run.py portability-check 의 "관리자 권한"이 True 인지 확인해라.
False 면 UI 자동화가 전부 차단되므로 그 사실을 먼저 보고하고 UI 가 필요 없는
작업만 진행해라.

P0
1. NEXT_WORK.md 2절에 적은 2026-08-28 미검증 수정을 하나씩 재검증해라 —
   run-wf10에서 Hospital Code `HC`가 기본값 `Routine Mammography`가 아니라
   `Mammography (Rt)`에 실제 매핑되는지 DB MappingKey/ProcedureKey, Procedure Step 수,
   Examine Ready를 함께 확인해라. 기본 Procedure 대체로 생긴 거짓 PASS를 허용하지 마라.
2. Viewer가 주 모니터 밖일 때 cold_start가 창을 강제 이동하지 않고 안전 중단하는지,
   주 모니터 안에서는 정상 로그인하는지 확인해라. `_login_check.py`를 좁은 스모크 점검에
   사용할 수 있다.
3. 나머지 수정도 재검증해라 —
   run-wf04 → run-wf06 (close_view_study), run-wf13 (로그인 콤보), run-xipl-05
   (Q.C 채점 + _qc_recover), run-wf15 (Dose Overlay 전제). 이미 PASS 확인된
   run-xipl-04 는 재검증 생략 가능.
4. XIPL_05 불합격 경계 검증(3절 #1) — Fiber 콤보 항목 구성을 다시 확인해라.
5. 전부 통과하면 중단됐던 실행을 이어받지 말고 전체 회귀를 처음부터 1회 돌려 실제
   완료 결과만 기록해라.

리팩터링·속도 개선
- 우선 개별 TC와 `cold_start`, 화면 전환, 검색, 영상 준비 구간의 소요 시간을 측정해
  가장 큰 병목부터 고쳐라.
- `demo_acquire_step(settle=14)` 등 고정 대기를 실제 상태 신호(`wait_new_group` 등)로
  전환하는 작업을 우선 검토해라.
- 반복되는 로그인·화면 진입·환자 검색·정리 흐름은 공용 helper로 합칠 수 있는지 보되,
  관련 없는 TC의 판정이나 회귀 순서를 바꾸지 마라.
- 리팩터링은 작은 단위로 나누고 각 단위마다 정적 검사, 관련 개별 TC, 변경 전후 실행
  시간 비교를 수행해라. 전체 회귀는 이 좁은 검증이 끝난 뒤 마지막 확인으로 실행해라.

검증·Git
- 긴 실행 전에 반드시: py_compile, tools/check_module_attrs.py,
  tools/check_regression_names.py, tools/traceability.py,
  python -m unittest discover -s tests -p "test_*.py"
- 문서를 갱신해라. 순서: ..\프로젝트_상세.md(기본 문서 — 먼저 갱신) →
  python tools/render_docs.py → README.md(포트폴리오 축약형) → NEXT_WORK.md,
  automation_scope.json, traceability.json, 지식/[자동화 구현 현황].
- git status/diff/remote 검토 후 관련 파일만 commit 하고 같은 작업에서 별도 재승인 없이
  일반 push까지 수행해라. push한 브랜치와 commit SHA를 보고해라.
  Force Push·history 재작성 금지. config.json, Reports/, Evidence/, Log/, Cache/,
  Temp/, work/ 는 커밋하지 마라.
- 테스트하지 않은 것을 성공했다고 기록하지 마라.
```
