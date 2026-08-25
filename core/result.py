# -*- coding: utf-8 -*-
"""판정 결과 모델과 리포트 산출물.

각 TC는 여러 개의 Check(=Expected Result 한 줄)를 갖는다.
판정은 PASS / FAIL / MANUAL / SKIP 네 가지만 쓴다.

  PASS   : 자동 판정으로 기대 결과 충족
  FAIL   : 자동 판정으로 기대 결과 불충족
  MANUAL : 자동화 대상이 아니거나 문서상 기대값이 확정되지 않아 수동 확인 필요
  SKIP   : 사전 조건 미충족으로 수행하지 않음
"""

import csv
import html
import json
import os
import time
from datetime import datetime

PASS, FAIL, MANUAL, SKIP = "PASS", "FAIL", "MANUAL", "SKIP"


def step_label(step):
    """리포트에 표시할 Step 표기.

    `step = 0` 은 **기준 체크리스트의 Step 이 아닌 보조 판정**이라는 뜻이다
    (시험 파라미터 준비, 시험 전 값 기록, TC 중단 기록, 정리·원복 등).
    숫자 `0` 을 그대로 찍으면 "Step 번호가 잘못 나온 것" 처럼 보여서
    사용자가 실제로 그렇게 읽었다(2026-08-24). 그래서 문구로 바꾼다.
    """
    try:
        number = int(step)
    except (TypeError, ValueError):
        return str(step)
    return "보조" if number == 0 else str(number)


class Check:
    def __init__(self, step, title, status, expected="", actual="", note=""):
        self.step = step
        self.title = title
        self.status = status
        self.expected = expected
        self.actual = actual
        self.note = note

    def as_dict(self):
        return {
            "step": self.step, "title": self.title, "status": self.status,
            "expected": str(self.expected), "actual": str(self.actual), "note": self.note,
        }


class StepFailed(RuntimeError):
    """어떤 Step 이 FAIL 한 시점에서 **그 TC 를 중단**시키는 신호.

    2026-08-24 사용자 지시: "어떤 스텝에서 fail 이 났다면 이후 step 을 수행하지
    말고 넘어가. 어차피 그 TC 는 자동화 완료 후 내가 직접 봐야 하는 거니까 전체
    자동화 수행할 때 시간이 길어지는 걸 방지할 수 있을 것 같아."

    구현 방식: `TCResult.add()` 가 FAIL 을 기록한 직후 이 예외를 던진다. 각 TC 는
    이미 본문을 `try/except` 로 감싸고 있으므로(`abort()` 를 부른다) **TC 코드를
    하나도 고치지 않고** 중단이 걸린다. 그리고 `run.py::pad_aborted_steps` 가
    남은 Step 을 미수행(FAIL)으로 채운다.

    맞바꾼 것: 첫 FAIL 뒤의 판정 정보는 더 이상 수집되지 않는다. 예를 들어
    `TC_XIPL_compatibility_03` 은 Step 9(제품 결함)에서 멈추므로 Step 10 의
    'GPU 없음 SKIP' 기록이 사라지고 미수행으로 남는다. 시간을 아끼는 대신
    **그 TC 는 사람이 직접 본다**는 전제다.
    """


class TCResult:
    #: FAIL 이 나면 그 TC 를 즉시 중단할지. `config.json > regression.stop_tc_on_fail`
    #: 로 끌 수 있다(`run.py` 가 세운다). 끄면 예전처럼 남은 Step 도 계속 수행한다.
    stop_on_fail = True

    def __init__(self, tc_id, title):
        self.tc_id = tc_id
        self.title = title
        self.checks = []
        self.started = datetime.now()
        self.completed = None
        self.timings = []
        self._step_cursor_wall = self.started
        self._step_cursor = time.perf_counter()
        self.evidence = []
        #: 이 TC 안에서 이미 FAIL 로 중단시켰는가(중복 예외 방지).
        self._stopped = False
        #: TC 가 **중간에 중단**됐는가. `abort()` 가 True 로 세운다.
        #: 이 값이 True 인 TC 는 `run.py` 가 리포트를 쓰기 전에 **남은 Step 을
        #: FAIL(미수행)로 채운다.** 단순히 "FAIL 이 있다"로 판단하면 안 된다 —
        #: 정상 수행하면서도 Step 을 통합해 기록하는 TC 가 있어(예: XIPL_03 은
        #: Step 3·5 를 별도 판정으로 내지 않는다) 멀쩡한 리포트에 없는 FAIL 이
        #: 생긴다.
        self.aborted = False

    # --- 등록 헬퍼 -----------------------------------------------------
    def add(self, step, title, status, expected="", actual="", note="",
            stop=True):
        """판정 하나를 기록한다.

        `stop=False` 는 **중단 신호를 내지 않는다.** `abort()` 와 `run.py` 의
        미수행 Step 채우기가 쓴다 — 그 둘은 이미 중단된 뒤에 부르는 것이라
        다시 예외를 던지면 안 된다.
        """
        now_wall = datetime.now()
        now = time.perf_counter()
        self.timings.append({
            "kind": "step", "name": f"Step {step}: {title}",
            "started": self._step_cursor_wall.isoformat(timespec="milliseconds"),
            "ended": now_wall.isoformat(timespec="milliseconds"),
            "duration_seconds": round(now - self._step_cursor, 3),
            "outcome": status, "detail": "check recorded",
        })
        self._step_cursor_wall, self._step_cursor = now_wall, now
        self.checks.append(Check(step, title, status, expected, actual, note))
        check = self.checks[-1]
        if (status == FAIL and stop and self.stop_on_fail
                and not self._stopped):
            self._stopped = True
            raise StepFailed(f"Step {step} FAIL — 이후 Step 을 수행하지 않고 "
                             f"이 TC 를 중단합니다: {title}")
        return check

    def record_timing(self, name, started_wall, started_perf, outcome, detail="",
                      kind="wait"):
        """Append timing metadata without changing any PASS/FAIL assertion."""
        ended = datetime.now()
        self.timings.append({
            "kind": kind, "name": name,
            "started": started_wall.isoformat(timespec="milliseconds"),
            "ended": ended.isoformat(timespec="milliseconds"),
            "duration_seconds": round(time.perf_counter() - started_perf, 3),
            "outcome": outcome, "detail": str(detail),
        })

    def finalize(self, completed=None):
        """종료 시각을 확정한다.

        호출자(`run.py::finish`)는 보통 **다음 TC의 시작 시각**을 넘긴다. 그런데
        TCResult가 실행 순서와 다른 순서로 만들어지는 경로가 있다(예: XIPL
        `_prepare` 실패 시 01/02/03과 06의 결과 객체를 먼저 만들고 04/05를
        나중에 실행). 그때 "다음 것"의 시작이 자기 시작보다 이르면 소요시간이
        음수로 찍힌다(2026-08-18 회귀 리포트에 -301.6s). 판정에는 영향이
        없지만 리포트를 못 믿게 만든다.

        그래서 넘어온 값이 자기 시작 이전이면 신뢰하지 않고, 마지막으로 기록된
        체크 시각(`_step_cursor_wall`)을 종료로 쓴다. 체크가 없으면 시작 시각을
        그대로 써서 0초로 만든다(음수보다 정직하다).
        """
        if self.completed is not None:
            return self
        if completed is None:
            self.completed = datetime.now()
        elif completed >= self.started:
            self.completed = completed
        else:
            self.completed = max(self.started, self._step_cursor_wall)
        return self

    @property
    def duration_seconds(self):
        end = self.completed or datetime.now()
        return round((end - self.started).total_seconds(), 3)

    def assert_equal(self, step, title, expected, actual, note=""):
        ok = str(expected).strip().lower() == str(actual).strip().lower()
        return self.add(step, title, PASS if ok else FAIL, expected, actual, note)

    def assert_true(self, step, title, cond, expected="True", actual=None, note=""):
        return self.add(step, title, PASS if cond else FAIL,
                        expected, actual if actual is not None else cond, note)

    def abort(self, step, title, exc, note=""):
        """TC 가 **중간에 중단**됐음을 기록한다(예외 처리 자리).

        `add(..., FAIL, actual=str(exc))` 와 같은 FAIL 을 남기면서 `aborted` 를
        세운다. 그러면 `run.py` 가 리포트를 쓰기 전에 **체크리스트의 남은 Step 을
        FAIL(미수행)로 채운다** — "이 TC 의 어느 단계까지 갔는가"가 리포트에
        드러나야 하기 때문이다(2026-08-24 사용자 요청).

        예외 타입을 함께 남긴다. `str(exc)` 만으로는 `KeyError: 'x'` 처럼
        메시지가 비거나 모호한 경우 원인을 못 짚는다.
        """
        self.aborted = True
        detail = exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
        return self.add(step, title, FAIL, actual=detail, stop=False,
                        note=note or
                        "이 단계에서 예외가 발생해 TC 가 중단됐다. 회귀는 멈추지 "
                        "않고 다음 TC 로 넘어간다. 남은 Step 은 '미수행(FAIL)'로 "
                        "채워진다 — 제품 결함 판정이 아니라 수행하지 못한 것이다.")

    def cleanup(self, step, title, status, expected="", actual="", note=""):
        """**정리(원복) 결과**를 기록한다. 절대 중단 신호를 내지 않는다.

        `finally` 안에서 `add(..., FAIL)` 을 부르면 `stop_on_fail` 때문에
        **정리 블록 자체가 StepFailed 를 던져 TC 밖으로 샌다.** 단독 실행은
        통째로 죽고, 회귀에서는 `guarded()` 가 받아 "TC 가 죽었다" 로 기록해
        실제로 일어난 일("본 시험은 통과했고 정리만 실패했다")을 가린다.

        2026-08-25 WF_14 에서 실측했다 — Step 1~7 을 다 통과한 실행이 정리
        단계의 `ensure_patient_screen` 예외 때문에 리포트조차 남기지 못했다.
        같은 형태가 7개 TC 파일 17곳에 있었다.

        정리가 실패한 사실은 **FAIL 로 남긴다**(조용히 넘기지 않는다). 다만 그
        FAIL 이 흐름을 끊지는 않는다 — 이미 끝난 TC 를 중단할 것이 없다.
        """
        return self.add(step, title, status, expected, actual, note,
                        stop=False)

    def manual(self, step, title, note, expected="", actual=""):
        return self.add(step, title, MANUAL, expected, actual, note)

    def skip(self, step, title, note, expected="", actual=""):
        """수행하지 않은 확인 항목.

        **SKIP 은 TC 판정을 MANUAL 로 끌어내리지 않는다**(`verdict` 참고).
        "확인해야 하는데 사람이 해야 한다"(MANUAL)와 "이 환경에서는 확인 대상이
        아니다"(SKIP)는 다르기 때문이다. 그래서 SKIP 을 쓸 때는 `note` 에
        **왜 대상이 아닌지**를 반드시 남긴다.
        """
        return self.add(step, title, SKIP, expected, actual, note)

    def attach(self, path):
        self.evidence.append(path)

    # --- 집계 ----------------------------------------------------------
    @property
    def counts(self):
        c = {PASS: 0, FAIL: 0, MANUAL: 0, SKIP: 0}
        for chk in self.checks:
            c[chk.status] = c.get(chk.status, 0) + 1
        return c

    @property
    def verdict(self):
        """TC 단위 판정.

        정책 (2026-08-21 사용자 확정)
          FAIL 이 하나라도 있으면 FAIL.
          MANUAL 이 남아 있으면 MANUAL — 사람이 아직 확인할 것이 있다는 뜻이다.
          **SKIP 은 판정을 끌어내리지 않는다.** SKIP 은 "이 환경에서 확인 대상이
          아니다"(예: 검증 환경서가 DICOM 전용 어댑터를 지정하지 않는 PC)이고,
          MANUAL 은 "확인해야 하는데 자동으로 못 한다"이다. 둘을 같이 취급하면
          대상이 아닌 항목 때문에 TC 가 영구히 MANUAL 로 남는다.
        """
        c = self.counts
        if c[FAIL]:
            return FAIL
        if c[MANUAL]:
            return MANUAL
        if c[PASS]:
            return PASS
        return SKIP

    def as_dict(self):
        return {
            "tc_id": self.tc_id, "title": self.title, "verdict": self.verdict,
            "started": self.started.isoformat(timespec="seconds"),
            "completed": (self.completed or datetime.now()).isoformat(timespec="seconds"),
            "duration_seconds": self.duration_seconds,
            "counts": self.counts, "evidence": self.evidence,
            "timings": self.timings,
            "checks": [c.as_dict() for c in self.checks],
        }


# ---------------------------------------------------------------------
_STYLE = """
:root{--fg:#1a1a1a;--mut:#666;--line:#d8d8d8;--head:#f3f4f6;--card:#fafafa}
body{font-family:'Malgun Gothic',sans-serif;margin:0;color:var(--fg);background:#fff}
.wrap{max-width:1500px;margin:0 auto;padding:24px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:26px 0 8px;padding-top:10px;border-top:2px solid #eee}
h3{font-size:13px;margin:14px 0 4px;color:#444}
.meta{color:var(--mut);font-size:12px;margin-bottom:18px}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin-bottom:8px}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:var(--head);font-weight:600}
td.s{font-weight:700;text-align:center}
/* 단계별 판정 표 — 기대값/실제값을 **같은 폭**으로 고정하고 판정 열을 줄인다
   (2026-08-21 사용자 요청). `table-layout:fixed` + colgroup 이라야 브라우저가
   내용 길이로 폭을 재조정하지 않아 두 열이 실제로 같은 크기로 보인다. */
table.steps{table-layout:fixed}
table.steps td,table.steps th{overflow-wrap:anywhere;word-break:break-word}
table.steps col.c-step{width:38px}
table.steps col.c-title{width:15%}
table.steps col.c-verdict{width:46px}
table.steps col.c-exp{width:27%}
table.steps col.c-act{width:27%}
table.steps col.c-note{width:auto}
table.steps td.s{padding:6px 2px;font-size:10.5px;letter-spacing:-.4px}
table.steps code{font-size:11.5px}
/* 실패 항목 표도 같은 균형을 쓴다(TC/Step 열만 다르다). */
table.fails{table-layout:fixed}
table.fails td,table.fails th{overflow-wrap:anywhere;word-break:break-word}
table.fails col.c-tc{width:190px}
table.fails col.c-step{width:38px}
table.fails col.c-title{width:15%}
table.fails col.c-exp{width:27%}
table.fails col.c-act{width:27%}
table.fails col.c-note{width:auto}
.PASS{color:#0a7f3f}.FAIL{color:#c62828}.MANUAL{color:#a06000}.SKIP{color:#777}
.sum td.s{font-size:13px}
tr.hdr td{background:var(--card)}
code{font-family:Consolas,monospace;font-size:12px;word-break:break-all}
/* 대시보드 */
.dash{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0 6px}
.tile{flex:1 1 150px;border:1px solid var(--line);border-radius:8px;padding:12px 14px;background:var(--card)}
.tile .n{font-size:26px;font-weight:700;line-height:1.1}
.tile .k{font-size:11.5px;color:var(--mut);margin-top:2px}
.bar{display:flex;height:14px;border-radius:7px;overflow:hidden;border:1px solid var(--line);margin:8px 0 2px}
.bar span{display:block}
.bPASS{background:#2e9e63}.bFAIL{background:#d34a4a}.bMANUAL{background:#e0a740}.bSKIP{background:#b8b8b8}
.legend{font-size:11.5px;color:var(--mut)}
.k{font-size:11px;color:var(--mut)}
table.cov{table-layout:fixed}
table.cov td,table.cov th{overflow-wrap:anywhere}
tr.gh td{background:#eef1f5;font-weight:700;font-size:12.5px}
table.holds{table-layout:fixed}
table.holds td,table.holds th{overflow-wrap:anywhere}
/* TC 카드 */
.spec{display:flex;flex-wrap:wrap;gap:10px;margin:6px 0 12px}
.spec>div{flex:1 1 260px;border:1px solid var(--line);border-radius:6px;padding:8px 10px;background:var(--card)}
.spec h4{margin:0 0 4px;font-size:11.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px}
.spec pre{margin:0;font-family:'Malgun Gothic',sans-serif;font-size:12px;white-space:pre-wrap;line-height:1.5}
.files code{display:block}
.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;border:1px solid var(--line);margin-left:6px;vertical-align:2px;color:var(--mut);background:#fff}
a{color:#1558b0}
.note{white-space:pre-wrap}
"""


#: 자동화 커버리지 총괄 섹션의 분류 표시 순서 (2026-08-21 사용자 요청).
#  "무엇을 자동화했고, 못 한 것은 왜 못 했는가"를 리포트 앞에서 한 번에 보여 준다.
#  분류 문구와 사유는 `automation_scope.json` 의 각 TC `coverage` 항목에서 온다 —
#  리포트가 사유를 스스로 만들지 않는다(근거 없는 설명을 만들지 않기 위해서다).
COVERAGE_ORDER = (
    "자동 판정(구현 완료)",
    "부분 자동 — 남은 항목 있음",
    "미구현 — 구현 가능(다음 작업 후보)",
    "실물 장비·촬영 환경 필요",
    "OS 신규 설치 환경 필요",
    "파괴적 작업(설치·재부팅·종료)",
    "판정 기준·문서 정보 미확정",
    "사용자 지정 수동",
)

def _coverage_groups(coverage):
    """커버리지 항목을 분류별로 묶어 표시 순서대로 돌려준다."""
    buckets = {}
    for item in coverage:
        buckets.setdefault(str(item.get("category") or "(분류 미기재)"),
                           []).append(item)
    ordered = [(name, buckets.pop(name)) for name in COVERAGE_ORDER
               if name in buckets]
    ordered.extend(sorted(buckets.items()))
    return ordered


def _pct(part, whole):
    return 0 if not whole else round(part * 100.0 / whole, 1)


def _file_url(path):
    """로컬 파일을 브라우저에서 열 수 있는 링크로 만든다."""
    from urllib.parse import quote
    p = str(path or "").replace("\\", "/")
    if not p:
        return ""
    return "file:///" + quote(p, safe="/:")


def _one_line(value, limit=200):
    """리포트 상단 요약에 넣기 위해 한 줄로 줄인다.

    `actual`이 dict면 진단에 핵심인 오류 문구를 앞세운다. 그냥 dict를 문자열로
    바꾸면 기동 로그 같은 부수 정보가 글자 수를 다 먹어 정작 원인이 잘린다.
    """
    if isinstance(value, dict):
        for key in ("error", "detail", "message"):
            if value.get(key):
                value = value[key]
                break
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def write_txt(results, path, env=None):
    """사람이 바로 읽는 Pass/Fail 요약 텍스트."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    total = {PASS: 0, FAIL: 0, MANUAL: 0, SKIP: 0}
    for r in results:
        for k, v in r.counts.items():
            total[k] += v

    L = []
    L.append("=" * 78)
    L.append(" Bellalun Viewer 기본기능 자동화 결과")
    L.append("=" * 78)
    L.append(f" 수행 일시 : {datetime.now():%Y-%m-%d %H:%M:%S}")
    # **두 층을 구분해 적는다.** 아래 "판정 합계"는 Step(체크) 단위 합계라서 TC
    # 개수보다 훨씬 크다. 예: TC 20개인데 체크 172개 -> PASS 160.
    # 구분하지 않으면 "TC가 20개인데 왜 PASS가 160개냐"는 오해가 생긴다
    # (2026-08-19 사용자 지적).
    tc_total = {PASS: 0, FAIL: 0, MANUAL: 0, SKIP: 0}
    for r in results:
        if r.verdict in tc_total:
            tc_total[r.verdict] += 1
    L.append(f" TC 건수   : {len(results)}")
    L.append(f" TC 판정   : PASS {tc_total[PASS]} / FAIL {tc_total[FAIL]} / "
             f"MANUAL {tc_total[MANUAL]} / SKIP {tc_total[SKIP]}   (TC 단위)")
    checks = sum(total.values())
    L.append(f" 검증 판정 : PASS {total[PASS]} / FAIL {total[FAIL]} / "
             f"MANUAL {total[MANUAL]} / SKIP {total[SKIP]}   "
             f"(Step 단위, 총 {checks}개 체크)")
    if env:
        L.append("")
        L.append(" [ 시험 환경 ]")
        for k, v in env.items():
            L.append(f"   - {k}: {v}")

    # 회귀는 선행 단계(DB 복원 -> DICOM 등록 -> WF01 -> 촬영)가 뒤 TC의 전제다.
    # 앞에서 한 번 무너지면 뒤가 줄줄이 FAIL로 찍혀 "제품이 10군데 깨졌다"처럼
    # 보인다(2026-08-18 실측: FAIL 10건이 전부 첫 FAIL 하나의 결과였다).
    # 그래서 **가장 앞선 FAIL을 맨 위에 표시**해 읽는 순서를 강제한다.
    first = next((r for r in results if r.verdict == FAIL), None)
    if first is not None and total[FAIL] > 1 and len(results) > 1:
        L.append("")
        L.append(" [ 먼저 볼 것 ] 가장 앞선 FAIL")
        L.append(f"   - {first.tc_id}: {first.title}")
        for chk in first.checks:
            if chk.status == FAIL:
                L.append(f"     -> Step {step_label(chk.step)}: {chk.title}")
                L.append(f"        실제: {_one_line(chk.actual)}")
                break
        L.append(f"   - 이후 FAIL {total[FAIL] - 1}건 중 일부는 이 실패의 결과일 "
                 f"수 있다. 전제 미충족(fixture 없음 / 서버 미등록) 메시지가 "
                 f"보이면 제품 판정이 아니다.")
    L.append("")

    L.append("-" * 78)
    L.append(" TC 별 판정")
    L.append("-" * 78)
    for r in results:
        c = r.counts
        L.append(f" [{r.verdict:^6}] {r.tc_id:<28} {r.title} ({r.duration_seconds:.1f}s)")
        L.append(f"          P{c[PASS]} F{c[FAIL]} M{c[MANUAL]} S{c[SKIP]}")
    L.append("")

    for r in results:
        L.append("=" * 78)
        L.append(f" {r.tc_id} — {r.title}   →  {r.verdict}")
        L.append("=" * 78)
        for chk in r.checks:
            L.append(f"  [{chk.status:^6}] "
                     f"Step {step_label(chk.step):<4} {chk.title}")
            if chk.status in (FAIL, MANUAL) or chk.expected or chk.actual:
                if str(chk.expected):
                    L.append(f"            기대 : {chk.expected}")
                if str(chk.actual):
                    L.append(f"            실제 : {chk.actual}")
            if chk.note:
                L.append(f"            비고 : {chk.note}")
        if r.evidence:
            L.append("  [증거]")
            for e in r.evidence:
                L.append(f"    - {e}")
        if r.timings:
            L.append("  [소요시간]")
            for timing in r.timings:
                L.append(f"    - {timing['kind']} {timing['name']}: "
                         f"{timing['duration_seconds']:.3f}s / "
                         f"{timing['outcome']} / {timing['detail']}")
            # 스텝 시각화 밖에서 쓴 시간(전제 준비, 실패 전 재시도 등)을 숨기지
            # 않는다. 2026-08-18 실측: TC_XIPL_06이 523.9초 걸렸는데 스텝 합계는
            # 0.000초로 찍혀 "그 8분은 어디서 썼나"를 리포트만으로 알 수 없었다.
            accounted = sum(t["duration_seconds"] for t in r.timings)
            unaccounted = r.duration_seconds - accounted
            if unaccounted > 5:
                L.append(f"    - (스텝 외) 전제 준비·재시도 등: "
                         f"{unaccounted:.1f}s / 스텝 합계 {accounted:.1f}s / "
                         f"TC 전체 {r.duration_seconds:.1f}s")
        L.append("")

    fails = [(r, c) for r in results for c in r.checks if c.status == FAIL]
    L.append("=" * 78)
    if fails:
        L.append(f" 실패 항목 {len(fails)}건")
        L.append("=" * 78)
        for r, c in fails:
            L.append(f"  {r.tc_id} / Step {step_label(c.step)} / {c.title}")
            L.append(f"     기대={c.expected}")
            L.append(f"     실제={c.actual}")
    else:
        L.append(" 실패 항목 없음")
    L.append("=" * 78)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


def write_reports(results, out_dir, run_name=None, meta=None):
    """CSV / JSON / HTML / TXT 리포트를 out_dir에 생성하고 경로를 반환한다.

    `meta` (있으면 HTML 에 함께 실린다):
      {"env":      {"항목": "값"},             # 실행 환경·버전
       "checklist":{tc_id: {precondition, steps, expected, test_data, ...}},
       "modules":  {tc_id: ["tests/workflow14.py", ...]},
       "scope":    {tc_id: {"level":.., "reason":..}},
       "command":  "python run.py run-regression"}
    """
    os.makedirs(out_dir, exist_ok=True)
    meta = meta or {}
    stamp = run_name or datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(out_dir, f"Result_{stamp}")

    # CSV
    csv_path = base + ".csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["TC ID", "Title", "TC 판정", "Step", "확인 항목", "판정", "기대값", "실제값", "비고"])
        for r in results:
            for c in r.checks:
                w.writerow([r.tc_id, r.title, r.verdict, c.step, c.title,
                            c.status, c.expected, c.actual, c.note])

    # JSON
    json_path = base + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.now().isoformat(timespec="seconds"),
                   "results": [r.as_dict() for r in results]}, f, ensure_ascii=False, indent=2)

    # HTML
    txt_path = write_txt(results, base + ".txt", env=meta.get("env"))
    html_path = base + ".html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(_render_html(results, meta,
                             siblings={"csv": csv_path, "json": json_path,
                                       "txt": txt_path}))

    return {"csv": csv_path, "json": json_path, "html": html_path, "txt": txt_path}


def _render_html(results, meta, siblings=None):
    """상세 HTML 리포트를 만든다.

    포함해야 하는 것(사용자 요구): 요약 대시보드 / TC별 사양과 검증 목적 /
    사전 조건 / 단계별 수행 내용과 기대 결과 / 실제 결과와 판정 근거 /
    시작·종료 시각과 소요 시간 / 로그·스크린샷 링크 / 실패 원인 /
    BLOCKED·SKIPPED 사유 / 자동화 코드 위치 / 실행 환경과 버전.
    """
    e = html.escape
    total = {PASS: 0, FAIL: 0, MANUAL: 0, SKIP: 0}
    for r in results:
        for k, v in r.counts.items():
            total[k] += v
    checks = sum(total.values())
    tc_total = {PASS: 0, FAIL: 0, MANUAL: 0, SKIP: 0}
    for r in results:
        if r.verdict in tc_total:
            tc_total[r.verdict] += 1
    wall = sum(r.duration_seconds for r in results)
    first_start = min((r.started for r in results), default=None)
    last_end = max(((r.completed or datetime.now()) for r in results),
                   default=None)

    cl = meta.get("checklist") or {}
    mods = meta.get("modules") or {}
    scope = meta.get("scope") or {}

    P = [f"<style>{_STYLE}</style>", "<div class='wrap'>",
         "<h1>Bellalun Viewer 기본기능 자동화 상세 리포트</h1>",
         "<div class='meta'>기준 문서 "
         "<code>Bellalun_Viewer_기본기능_Checklist_개정본.xlsx</code> "
         "(시트 <code>개정 TC</code>) &nbsp;|&nbsp; 생성 "
         f"{datetime.now():%Y-%m-%d %H:%M:%S}"
         + (f" &nbsp;|&nbsp; 실행 명령 <code>{e(meta['command'])}</code>"
            if meta.get("command") else "") + "</div>"]

    # --- 대시보드 -----------------------------------------------------
    P.append("<h2 style='border:0;padding:0;margin-top:6px'>요약 대시보드</h2>")
    P.append("<div class='dash'>")
    P.append(f"<div class='tile'><div class='n'>{len(results)}</div>"
             "<div class='k'>수행 TC</div></div>")
    for k in (PASS, FAIL, MANUAL, SKIP):
        P.append(f"<div class='tile'><div class='n {k}'>{tc_total[k]}</div>"
                 f"<div class='k'>TC {k}</div></div>")
    P.append(f"<div class='tile'><div class='n'>{checks}</div>"
             "<div class='k'>검증 항목(Step 단위)</div></div>")
    P.append(f"<div class='tile'><div class='n'>{wall / 60:.1f}<span "
             "style='font-size:14px'> 분</span></div>"
             "<div class='k'>총 소요 시간</div></div>")
    P.append("</div>")

    P.append("<div class='bar'>")
    for k in (PASS, FAIL, MANUAL, SKIP):
        if total[k]:
            P.append(f"<span class='b{k}' style='width:"
                     f"{_pct(total[k], checks)}%' title='{k} {total[k]}'></span>")
    P.append("</div>")
    P.append("<div class='legend'>검증 항목 "
             + " / ".join(f"<b class='{k}'>{k} {total[k]}</b> "
                          f"({_pct(total[k], checks)}%)"
                          for k in (PASS, FAIL, MANUAL, SKIP)) + "</div>")
    if first_start and last_end:
        P.append(f"<div class='meta'>실행 구간 {first_start:%Y-%m-%d %H:%M:%S} "
                 f"~ {last_end:%Y-%m-%d %H:%M:%S}</div>")

    # --- 실행 환경 ----------------------------------------------------
    if meta.get("env"):
        P.append("<h2>실행 환경 및 버전</h2><table>")
        for k, v in meta["env"].items():
            text = str(v)
            # 실제로 존재하는 경로는 눌러서 열 수 있게 링크로 만든다
            # (Viewer 로그·증거 폴더를 리포트에서 바로 열기 위해서다).
            cell = (f"<a href='{_file_url(text)}'><code>{e(text)}</code></a>"
                    if os.path.exists(text) else f"<code>{e(text)}</code>")
            P.append(f"<tr><th style='width:230px'>{e(str(k))}</th>"
                     f"<td>{cell}</td></tr>")
        P.append("</table>")

    # --- 자동화 커버리지 총괄 (기준 체크리스트 전체) --------------------
    # 2026-08-21 사용자 요청: "실제 자동화 TC 를 못 만들어서 MANUAL 로 남겨 놓은
    # TC" 를 리포트 초반에 한 섹션으로 모은다. 이번 실행에서 수행한 TC 뿐 아니라
    # **기준 체크리스트 전체 행**을 대상으로 하며, 사유는 자동으로 추측하지 않고
    # `automation_scope.json` 의 `coverage` 항목에서 읽는다.
    coverage = meta.get("coverage") or []
    if coverage:
        groups = _coverage_groups(coverage)
        # 타일은 **자동화 등급**(`automation_scope.json` 의 `level`) 으로 센다.
        # 아래 표의 묶음은 **미자동화 사유 분류**라 기준이 다르다 — 예를 들어
        # `Install_01` 은 코드가 완성된 FULL 이지만 승인 Release Note 가 없어
        # '판정 기준 미확정' 으로 묶인다. 두 기준을 한 숫자로 섞으면 "FULL 20인데
        # 자동 판정 19"처럼 읽혀 오해가 생긴다(2026-08-21에 실제로 그랬다).
        levels = {}
        for x in coverage:
            levels[str(x.get("level"))] = levels.get(str(x.get("level")), 0) + 1
        P.append(f"<h2>자동화 커버리지 총괄 — 기준 체크리스트 {len(coverage)} TC</h2>")
        P.append("<div class='meta'>이번 실행 결과와 별개로, <b>기준 체크리스트의 "
                 "모든 TC</b>가 자동화됐는지와 못 한 것의 사유를 모아 둔 표다. "
                 "사유는 <code>automation_scope.json</code> 의 각 TC "
                 "<code>coverage</code> 항목에서 그대로 읽는다 — 리포트가 사유를 "
                 "만들어 내지 않는다. <b>타일은 자동화 등급</b>(FULL/PARTIAL/"
                 "MANUAL)이고, <b>아래 표의 묶음은 미자동화 사유 분류</b>라 기준이 "
                 "다르다.</div>")
        P.append("<div class='dash'>")
        P.append(f"<div class='tile'><div class='n'>{len(coverage)}</div>"
                 "<div class='k'>기준 TC 총계</div></div>")
        P.append(f"<div class='tile'><div class='n PASS'>"
                 f"{levels.get('FULL', 0)}</div>"
                 "<div class='k'>FULL — 전 단계 자동 판정</div></div>")
        P.append(f"<div class='tile'><div class='n MANUAL'>"
                 f"{levels.get('PARTIAL', 0)}</div>"
                 "<div class='k'>PARTIAL — 일부 수동</div></div>")
        P.append(f"<div class='tile'><div class='n SKIP'>"
                 f"{levels.get('MANUAL', 0)}</div>"
                 "<div class='k'>MANUAL — 수동 전용</div></div>")
        P.append("</div>")
        P.append("<table class='cov'><colgroup><col style='width:200px'>"
                 "<col style='width:20%'><col style='width:66px'>"
                 "<col style='width:28%'><col></colgroup>"
                 "<tr><th>TC ID</th><th>Title</th><th>범위</th>"
                 "<th>자동화하지 못한 지점</th><th>해제 조건</th></tr>")
        for name, items in groups:
            P.append(f"<tr class='gh'><td colspan='5'>{e(name)} — "
                     f"{len(items)}건</td></tr>")
            for x in items:
                tc_id = str(x.get("tc_id") or "")
                link = (f"<a href='#{e(tc_id)}'>{e(tc_id)}</a>"
                        if tc_id in {r.tc_id for r in results} else e(tc_id))
                P.append(f"<tr><td>{link}</td><td>{e(str(x.get('title') or ''))}</td>"
                         f"<td class='s'>{e(str(x.get('level') or '-'))}</td>"
                         f"<td class='note'>{e(str(x.get('gap') or '-'))}</td>"
                         f"<td class='note'>{e(str(x.get('unblock') or '-'))}</td>"
                         "</tr>")
        P.append("</table>")

    # --- 먼저 볼 것: FAIL 원인 ----------------------------------------
    fails = [(r, c) for r in results for c in r.checks if c.status == FAIL]
    if fails:
        P.append(f"<h2>실패 항목 {len(fails)}건 — 원인</h2>")
        P.append("<div class='meta'>회귀는 앞 단계가 뒤 TC 의 전제다. "
                 "<b>가장 위의 FAIL 부터</b> 읽는다 — 아래 FAIL 중 일부는 그 "
                 "실패의 결과일 수 있다.</div>")
        P.append("<table class='fails'><colgroup>"
                 "<col class='c-tc'><col class='c-step'><col class='c-title'>"
                 "<col class='c-exp'><col class='c-act'><col class='c-note'>"
                 "</colgroup>"
                 "<tr><th>TC</th>"
                 "<th>Step</th><th>확인 항목</th>"
                 "<th>기대값</th><th>실제값</th><th>판정 근거 / 비고</th></tr>")
        for r, c in fails:
            P.append(f"<tr><td><a href='#{e(r.tc_id)}'>{e(r.tc_id)}</a></td>"
                     f"<td>{e(step_label(c.step))}</td>"
                     f"<td>{e(c.title)}</td>"
                     f"<td><code>{e(str(c.expected))}</code></td>"
                     f"<td><code>{e(str(c.actual))}</code></td>"
                     f"<td class='note'>{e(c.note)}</td></tr>")
        P.append("</table>")

    # --- MANUAL / SKIP 사유 (TC 별로 한 행) ----------------------------
    # 2026-08-21 사용자 요청: MANUAL Step 을 전부 행으로 펼치지 않고 **TC 별로
    # 한 행**에 모은다. 이전에는 17행이 나와 "어느 TC 가 왜 막혔는가"가 묻혔다.
    holds = []
    for r in results:
        items = [c for c in r.checks if c.status in (MANUAL, SKIP)]
        if items:
            holds.append((r, items))
    if holds:
        total_items = sum(len(x) for _, x in holds)
        P.append(f"<h2>수동 확인 / 미수행 — TC {len(holds)}건 "
                 f"(확인 항목 {total_items}개) — 사유와 해제 조건</h2>")
        P.append("<div class='meta'>TC 하나에 여러 항목이 걸려 있어도 "
                 "<b>한 행</b>으로 묶어 적는다. 항목별 원문 사유는 각 TC 상세의 "
                 "단계별 판정 표에 그대로 남아 있다.</div>")
        P.append("<table class='holds'><colgroup><col style='width:190px'>"
                 "<col style='width:52px'><col style='width:30%'>"
                 "<col></colgroup>"
                 "<tr><th>TC</th><th>건수</th><th>확인 항목</th>"
                 "<th>사유 / 해제 조건</th></tr>")
        for r, items in holds:
            labels = "<br>".join(
                f"<span class='s {c.status}'>[{c.status}]</span> "
                f"Step {e(step_label(c.step))} {e(c.title)}"
                for c in items)
            # 같은 사유가 여러 Step 에 반복되는 경우가 많다(예: RDSR 전제 미충족).
            # 중복을 접어 **서로 다른 사유만** 남긴다.
            reasons, seen = [], set()
            for c in items:
                text = " ".join(str(c.note or "").split())
                if text and text not in seen:
                    seen.add(text)
                    reasons.append(text)
            body = "<br><br>".join(e(x) for x in reasons) or "(사유 미기재)"
            P.append(f"<tr><td><a href='#{e(r.tc_id)}'>{e(r.tc_id)}</a><br>"
                     f"<span class='k'>{e(r.title)}</span></td>"
                     f"<td style='text-align:center'>{len(items)}</td>"
                     f"<td>{labels}</td>"
                     f"<td class='note'>{body}</td></tr>")
        P.append("</table>")

    # --- TC 요약 표 + 목차 ---------------------------------------------
    P.append("<h2>TC 별 판정</h2>")
    P.append("<table class='sum'><tr><th>TC ID</th><th>Title</th>"
             "<th>자동화 범위</th><th>판정</th><th>P</th><th>F</th><th>M</th>"
             "<th>S</th><th>시작</th><th>종료</th><th>소요</th></tr>")
    for r in results:
        c = r.counts
        lvl = (scope.get(r.tc_id) or {}).get("level", "-")
        end = r.completed or datetime.now()
        P.append(f"<tr><td><a href='#{e(r.tc_id)}'>{e(r.tc_id)}</a></td>"
                 f"<td>{e(r.title)}</td><td>{e(str(lvl))}</td>"
                 f"<td class='s {r.verdict}'>{r.verdict}</td>"
                 f"<td>{c[PASS]}</td><td>{c[FAIL]}</td><td>{c[MANUAL]}</td>"
                 f"<td>{c[SKIP]}</td>"
                 f"<td>{r.started:%H:%M:%S}</td><td>{end:%H:%M:%S}</td>"
                 f"<td>{r.duration_seconds:.1f}s</td></tr>")
    P.append("</table>")

    # --- TC 상세 -------------------------------------------------------
    for r in results:
        spec = cl.get(r.tc_id) or {}
        sc = scope.get(r.tc_id) or {}
        end = r.completed or datetime.now()
        P.append(f"<h2 id='{e(r.tc_id)}'>{e(r.tc_id)} — {e(r.title)} "
                 f"<span class='{r.verdict}'>[{r.verdict}]</span>"
                 + (f"<span class='badge'>{e(str(sc.get('level')))}</span>"
                    if sc.get("level") else "") + "</h2>")
        P.append(f"<div class='meta'>시작 {r.started:%Y-%m-%d %H:%M:%S}"
                 f" &nbsp;→&nbsp; 종료 {end:%Y-%m-%d %H:%M:%S}"
                 f" &nbsp;|&nbsp; 소요 {r.duration_seconds:.1f}s</div>")

        # 사양·검증 목적 (기준 문서 원문)
        cells = []
        if spec.get("precondition"):
            cells.append(("사전 조건 (Precondition)", spec["precondition"]))
        if spec.get("steps"):
            cells.append(("수행 단계 (Step Description)", spec["steps"]))
        if spec.get("expected"):
            cells.append(("기대 결과 (Expected Result)", spec["expected"]))
        if spec.get("test_data"):
            cells.append(("테스트 데이터 (Test Data)", spec["test_data"]))
        if sc.get("reason"):
            cells.append(("자동화 범위와 사유", sc["reason"]))
        if cells:
            P.append("<h3>기준 문서 원문 — 이 TC 가 무엇을 검증하는가</h3>")
            P.append("<div class='spec'>")
            for head, body in cells:
                P.append(f"<div><h4>{e(head)}</h4><pre>{e(body)}</pre></div>")
            P.append("</div>")

        # 자동화 코드 위치
        files = mods.get(r.tc_id) or []
        if files:
            P.append("<h3>자동화 코드 위치</h3>"
                     "<div class='meta files'>"
                     + "".join(f"<code>{e(p)}</code>" for p in files)
                     + "</div>")

        # 단계별 판정
        P.append("<h3>단계별 판정 — 기대값 / 실제값 / 근거</h3>")
        # 기대값/실제값을 **같은 폭**으로 고정하고 판정 열을 좁힌다
        # (2026-08-21 사용자 요청: 표를 봤을 때 두 값이 바로 대조되어야 한다).
        P.append("<table class='steps'><colgroup>"
                 "<col class='c-step'><col class='c-title'>"
                 "<col class='c-verdict'><col class='c-exp'><col class='c-act'>"
                 "<col class='c-note'></colgroup>"
                 "<tr><th>Step</th><th>확인 항목</th>"
                 "<th>판정</th><th>기대값</th><th>실제값</th>"
                 "<th>판정 근거 / 비고</th></tr>")
        for c in r.checks:
            P.append(f"<tr><td>{e(step_label(c.step))}</td>"
                     f"<td>{e(c.title)}</td>"
                     f"<td class='s {c.status}'>{c.status}</td>"
                     f"<td><code>{e(str(c.expected))}</code></td>"
                     f"<td><code>{e(str(c.actual))}</code></td>"
                     f"<td class='note'>{e(c.note)}</td></tr>")
        P.append("</table>")

        # 증거 (클릭 가능한 링크)
        if r.evidence:
            P.append("<h3>증거 (스크린샷·파일)</h3><table>"
                     "<tr><th style='width:46px'>#</th><th>경로</th></tr>")
            for i, p in enumerate(r.evidence, 1):
                P.append(f"<tr><td>{i}</td><td>"
                         f"<a href='{_file_url(p)}'>{e(str(p))}</a></td></tr>")
            P.append("</table>")

        # 소요시간 분해
        if r.timings:
            accounted = sum(t["duration_seconds"] for t in r.timings)
            unaccounted = r.duration_seconds - accounted
            P.append("<h3>소요 시간 분해</h3>")
            P.append("<table><tr><th style='width:60px'>종류</th>"
                     "<th>단계 / 대기</th><th style='width:90px'>소요</th>"
                     "<th style='width:80px'>결과</th><th>상세</th></tr>")
            for t in r.timings:
                P.append(f"<tr><td>{e(t['kind'])}</td><td>{e(t['name'])}</td>"
                         f"<td>{t['duration_seconds']:.3f}s</td>"
                         f"<td class='{t['outcome']}'>{e(t['outcome'])}</td>"
                         f"<td>{e(t['detail'])}</td></tr>")
            if unaccounted > 5:
                P.append("<tr class='hdr'><td>-</td><td>(스텝 외) 전제 준비·"
                         "재시도 등</td>"
                         f"<td>{unaccounted:.1f}s</td><td>-</td>"
                         f"<td>스텝 합계 {accounted:.1f}s / TC 전체 "
                         f"{r.duration_seconds:.1f}s</td></tr>")
            P.append("</table>")

    if siblings:
        P.append("<h2>같은 실행의 다른 산출물</h2><table>")
        for k, p in siblings.items():
            P.append(f"<tr><th style='width:80px'>{e(k)}</th>"
                     f"<td><a href='{_file_url(p)}'>{e(str(p))}</a></td></tr>")
        P.append("</table>")
    P.append("</div>")
    return "\n".join(P)
