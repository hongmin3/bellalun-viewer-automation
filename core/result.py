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


class TCResult:
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

    # --- 등록 헬퍼 -----------------------------------------------------
    def add(self, step, title, status, expected="", actual="", note=""):
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
        return self.checks[-1]

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

    def manual(self, step, title, note, expected="", actual=""):
        return self.add(step, title, MANUAL, expected, actual, note)

    def skip(self, step, title, note):
        return self.add(step, title, SKIP, note=note)

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
        c = self.counts
        if c[FAIL]:
            return FAIL
        if c[PASS] == 0:
            return SKIP if c[SKIP] else MANUAL
        return MANUAL if c[MANUAL] else PASS

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
body{font-family:'Malgun Gothic',sans-serif;margin:24px;color:#1a1a1a;background:#fff}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:22px 0 6px}
.meta{color:#666;font-size:12px;margin-bottom:18px}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin-bottom:8px}
th,td{border:1px solid #d8d8d8;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f3f4f6;font-weight:600}
td.s{font-weight:700;text-align:center;width:74px}
.PASS{color:#0a7f3f}.FAIL{color:#c62828}.MANUAL{color:#a06000}.SKIP{color:#777}
.sum td.s{font-size:13px}
tr.hdr td{background:#fafafa}
code{font-family:Consolas,monospace;font-size:12px;word-break:break-all}
"""


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
    L.append(f" TC 건수   : {len(results)}")
    L.append(f" 판정 합계 : PASS {total[PASS]} / FAIL {total[FAIL]} / "
             f"MANUAL {total[MANUAL]} / SKIP {total[SKIP]}")
    if env:
        L.append("")
        L.append(" [ 시험 환경 ]")
        for k, v in env.items():
            L.append(f"   - {k}: {v}")
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
            L.append(f"  [{chk.status:^6}] Step {chk.step:<3} {chk.title}")
            if chk.status in (FAIL, MANUAL) or chk.expected or chk.actual:
                if str(chk.expected):
                    L.append(f"            기대 : {chk.expected}")
                if str(chk.actual):
                    L.append(f"            실제 : {chk.actual}")
            if chk.note:
                L.append(f"            비고 : {chk.note}")
        if r.evidence:
            L.append("  [증적]")
            for e in r.evidence:
                L.append(f"    - {e}")
        if r.timings:
            L.append("  [소요시간]")
            for timing in r.timings:
                L.append(f"    - {timing['kind']} {timing['name']}: "
                         f"{timing['duration_seconds']:.3f}s / "
                         f"{timing['outcome']} / {timing['detail']}")
        L.append("")

    fails = [(r, c) for r in results for c in r.checks if c.status == FAIL]
    L.append("=" * 78)
    if fails:
        L.append(f" 실패 항목 {len(fails)}건")
        L.append("=" * 78)
        for r, c in fails:
            L.append(f"  {r.tc_id} / Step {c.step} / {c.title}")
            L.append(f"     기대={c.expected}")
            L.append(f"     실제={c.actual}")
    else:
        L.append(" 실패 항목 없음")
    L.append("=" * 78)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


def write_reports(results, out_dir, run_name=None):
    """CSV / JSON / HTML 리포트를 out_dir에 생성하고 경로를 반환한다."""
    os.makedirs(out_dir, exist_ok=True)
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
    e = html.escape
    total = {PASS: 0, FAIL: 0, MANUAL: 0, SKIP: 0}
    for r in results:
        for k, v in r.counts.items():
            total[k] += v

    parts = [f"<style>{_STYLE}</style>",
             "<h1>Bellalun Viewer 기본기능 자동화 결과</h1>",
             f"<div class='meta'>생성 {datetime.now():%Y-%m-%d %H:%M:%S} &nbsp;|&nbsp; "
             f"TC {len(results)}건 &nbsp;|&nbsp; "
             f"<span class='PASS'>PASS {total[PASS]}</span> / "
             f"<span class='FAIL'>FAIL {total[FAIL]}</span> / "
             f"<span class='MANUAL'>MANUAL {total[MANUAL]}</span> / "
             f"<span class='SKIP'>SKIP {total[SKIP]}</span></div>",
             "<h2>요약</h2><table class='sum'><tr><th>TC ID</th><th>Title</th><th>판정</th>"
             "<th>P</th><th>F</th><th>M</th><th>S</th><th>소요시간</th></tr>"]
    for r in results:
        c = r.counts
        parts.append(f"<tr><td>{e(r.tc_id)}</td><td>{e(r.title)}</td>"
                     f"<td class='s {r.verdict}'>{r.verdict}</td>"
                     f"<td>{c[PASS]}</td><td>{c[FAIL]}</td><td>{c[MANUAL]}</td><td>{c[SKIP]}</td>"
                     f"<td>{r.duration_seconds:.1f}s</td></tr>")
    parts.append("</table>")

    for r in results:
        parts.append(f"<h2>{e(r.tc_id)} — {e(r.title)} "
                     f"<span class='{r.verdict}'>[{r.verdict}]</span></h2>")
        parts.append("<table><tr><th style='width:46px'>Step</th><th>확인 항목</th>"
                     "<th style='width:74px'>판정</th><th>기대값</th><th>실제값</th><th>비고</th></tr>")
        for c in r.checks:
            parts.append(f"<tr><td>{e(str(c.step))}</td><td>{e(c.title)}</td>"
                         f"<td class='s {c.status}'>{c.status}</td>"
                         f"<td><code>{e(str(c.expected))}</code></td>"
                         f"<td><code>{e(str(c.actual))}</code></td>"
                         f"<td>{e(c.note)}</td></tr>")
        parts.append("</table>")
        if r.timings:
            parts.append("<table><tr><th>종류</th><th>단계/대기</th><th>소요시간</th>"
                         "<th>종료 원인</th><th>상세</th></tr>")
            for timing in r.timings:
                parts.append(
                    f"<tr><td>{e(timing['kind'])}</td><td>{e(timing['name'])}</td>"
                    f"<td>{timing['duration_seconds']:.3f}s</td>"
                    f"<td>{e(timing['outcome'])}</td>"
                    f"<td>{e(timing['detail'])}</td></tr>")
            parts.append("</table>")
        if r.evidence:
            parts.append("<div class='meta'>증적: " +
                         ", ".join(f"<code>{e(p)}</code>" for p in r.evidence) + "</div>")

    html_path = base + ".html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    txt_path = write_txt(results, base + ".txt")

    return {"csv": csv_path, "json": json_path, "html": html_path, "txt": txt_path}
