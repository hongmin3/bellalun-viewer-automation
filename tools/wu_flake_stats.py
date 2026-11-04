# -*- coding: utf-8 -*-
r"""여러 회차의 리포트 JSON을 모아 **판정이 갈린 단계**를 찾는다(읽기 전용).

NEXT_WORK.md 3-B·3-C처럼 간헐 증상은 한 회차 리포트만 봐서는 "늘 실패"인지
"가끔 실패"인지 구분되지 않는다. 이 도구는 같은 (TC, Step, 제목) 판정을 회차별로
세어, 회차에 따라 상태가 달라진 항목과 TC 판정이 달라진 TC를 보여 준다.

```
python tools/wu_flake_stats.py                                  # Reports/Result_*.json 전부
python tools/wu_flake_stats.py "Reports/Result_WindowsUpdate_*.json"
python tools/wu_flake_stats.py Reports --tc TC_WindowsUpdate_10 --json
```

주의

* 리포트만 읽는다. 리포트·증거 파일을 고치거나 지우지 않는다.
* 회차 사이에 **자동화 코드가 바뀌었을 수 있다.** 판정이 갈렸다는 사실은 간헐
  결함 후보일 뿐이며, 수정 전후 회차가 섞여도 같은 모양으로 보인다. 회차 범위는
  ``--since``·파일 목록으로 좁힌다.
* 옛 스키마(``meta``·``checks`` 일부 키 없음)는 있는 키만 쓴다. 읽을 수 없는
  파일은 건너뛰고 끝에 사유를 남긴다.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter, OrderedDict

STATUSES = ("PASS", "FAIL", "MANUAL", "SKIP", "BLOCKED")
DEFAULT_PATTERN = os.path.join("Reports", "Result_*.json")


# --------------------------------------------------------------------------
# 입력
# --------------------------------------------------------------------------
def expand_inputs(items, root=None):
    """경로·디렉터리·glob 목록을 실제 JSON 파일 목록(중복 제거, 이름순)으로."""
    root = root or os.getcwd()
    found = []
    for item in items or [os.path.join(root, DEFAULT_PATTERN)]:
        path = item if os.path.isabs(item) else os.path.join(root, item)
        if os.path.isdir(path):
            found.extend(glob.glob(os.path.join(path, "Result_*.json")))
        elif any(ch in item for ch in "*?["):
            found.extend(glob.glob(path))
        else:
            found.append(path)
    seen, out = set(), []
    for path in found:
        key = os.path.normcase(os.path.abspath(path))
        if key not in seen:
            seen.add(key)
            out.append(path)
    return sorted(out, key=lambda p: os.path.basename(p))


def load_runs(paths):
    """(runs, unreadable). run = {"path", "name", "generated", "results"}."""
    runs, unreadable = [], []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            unreadable.append({"path": path, "reason": "%s: %s" % (type(exc).__name__, exc)})
            continue
        if isinstance(data, list):                    # 아주 옛 형식: 결과 목록만
            data = {"results": data}
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            unreadable.append({"path": path, "reason": "results 목록 없음"})
            continue
        runs.append({"path": path, "name": os.path.basename(path),
                     "generated": data.get("generated"),
                     "results": [r for r in data["results"] if isinstance(r, dict)]})
    return runs, unreadable


# --------------------------------------------------------------------------
# 집계
# --------------------------------------------------------------------------
def _status(value):
    text = str(value or "").strip().upper()
    return text or "UNKNOWN"


def analyze(runs, tc_filter=None):
    """Step·TC 단위 상태 분포와 갈린 항목을 계산한다."""
    steps, tcs = OrderedDict(), OrderedDict()
    for run in runs:
        for row in run["results"]:
            tc_id = row.get("tc_id") or "UNKNOWN"
            if tc_filter and not any(tc_id.startswith(f) for f in tc_filter):
                continue
            tc = tcs.setdefault(tc_id, {"tc_id": tc_id, "title": row.get("title") or "",
                                        "verdicts": Counter(), "runs": []})
            verdict = _status(row.get("verdict"))
            tc["verdicts"][verdict] += 1
            tc["runs"].append({"run": run["name"], "verdict": verdict})
            # 같은 회차 안에서 같은 키가 여러 번 나오면(정리 단계 반복 등)
            # 회차당 한 번만 센다 — 가장 나쁜 상태를 그 회차 값으로 본다.
            per_run = {}
            for check in row.get("checks") or []:
                if not isinstance(check, dict):
                    continue
                key = (tc_id, check.get("step"), str(check.get("title") or ""))
                status = _status(check.get("status"))
                prev = per_run.get(key)
                per_run[key] = status if prev is None else _worse(prev, status)
            for key, status in per_run.items():
                item = steps.setdefault(key, {"tc_id": key[0], "step": key[1],
                                              "title": key[2], "statuses": Counter(),
                                              "runs": []})
                item["statuses"][status] += 1
                item["runs"].append({"run": run["name"], "status": status})
    step_rows = list(steps.values())
    tc_rows = list(tcs.values())
    return {
        "runs": len(runs),
        "steps": step_rows,
        "tcs": tc_rows,
        "divergent_steps": [s for s in step_rows if len(s["statuses"]) > 1],
        "divergent_tcs": [t for t in tc_rows if len(t["verdicts"]) > 1],
    }


_RANK = {"FAIL": 5, "BLOCKED": 4, "UNKNOWN": 3, "MANUAL": 2, "SKIP": 1, "PASS": 0}


def _worse(a, b):
    return a if _RANK.get(a, 3) >= _RANK.get(b, 3) else b


def _fail_rate(counter):
    total = sum(counter.values())
    return (counter.get("FAIL", 0) + counter.get("BLOCKED", 0)) / total if total else 0.0


# --------------------------------------------------------------------------
# 출력
# --------------------------------------------------------------------------
def _dist(counter):
    order = list(STATUSES) + sorted(k for k in counter if k not in STATUSES)
    return " ".join("%s %d" % (k, counter[k]) for k in order if counter.get(k))


def _cut(text, width):
    text = str(text).replace("\n", " ")
    return text if len(text) <= width else text[:width - 1] + "…"


def render_text(report, unreadable=(), top=30):
    lines = ["회차 %d개 · Step 키 %d개 · TC %d개" % (
        report["runs"], len(report["steps"]), len(report["tcs"]))]
    lines.append("※ 판정이 갈렸다는 것은 간헐 결함 '후보'다. 회차 사이 코드 변경도 같은 "
                 "모양으로 보인다.")
    lines.append("")
    tcs = sorted(report["divergent_tcs"], key=lambda t: -_fail_rate(t["verdicts"]))
    lines.append("[TC 판정이 갈린 TC] %d개" % len(tcs))
    if tcs:
        lines.append("  %-34s %-5s %s" % ("TC", "회차", "판정 분포"))
        for t in tcs[:top]:
            lines.append("  %-34s %-5d %s" % (_cut(t["tc_id"], 34),
                                             sum(t["verdicts"].values()),
                                             _dist(t["verdicts"])))
        if len(tcs) > top:
            lines.append("  ... 외 %d개" % (len(tcs) - top))
    lines.append("")
    steps = sorted(report["divergent_steps"],
                   key=lambda s: (-_fail_rate(s["statuses"]), s["tc_id"], str(s["step"])))
    lines.append("[판정이 갈린 단계] %d개" % len(steps))
    if steps:
        lines.append("  %-30s %-5s %-36s %-5s %s" % ("TC", "Step", "제목", "회차", "상태 분포"))
        for s in steps[:top]:
            lines.append("  %-30s %-5s %-36s %-5d %s" % (
                _cut(s["tc_id"], 30), s["step"], _cut(s["title"], 36),
                sum(s["statuses"].values()), _dist(s["statuses"])))
        if len(steps) > top:
            lines.append("  ... 외 %d개 (--top 으로 늘린다)" % (len(steps) - top))
    if unreadable:
        lines.append("")
        lines.append("[건너뛴 파일] %d개" % len(unreadable))
        for item in unreadable[:top]:
            lines.append("  %s — %s" % (os.path.basename(item["path"]), item["reason"]))
    return "\n".join(lines)


def to_json(report, unreadable=()):
    def step(s):
        return {"tc_id": s["tc_id"], "step": s["step"], "title": s["title"],
                "statuses": dict(s["statuses"]), "runs": s["runs"]}

    def tc(t):
        return {"tc_id": t["tc_id"], "title": t["title"],
                "verdicts": dict(t["verdicts"]), "runs": t["runs"]}

    return {"runs": report["runs"],
            "step_keys": len(report["steps"]), "tc_count": len(report["tcs"]),
            "divergent_tcs": [tc(t) for t in report["divergent_tcs"]],
            "divergent_steps": [step(s) for s in report["divergent_steps"]],
            "unreadable": list(unreadable)}


def _filter_since(runs, since):
    if not since:
        return runs
    out = []
    for run in runs:
        stamp = str(run.get("generated") or "")
        if not stamp:
            # generated 없는 옛 리포트는 파일명 날짜(Result_YYYYMMDD_...)로 본다.
            digits = "".join(ch for ch in run["name"] if ch.isdigit())[:8]
            stamp = "%s-%s-%s" % (digits[:4], digits[4:6], digits[6:8]) if len(digits) == 8 else ""
        if stamp and stamp[:10] >= since:
            out.append(run)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="여러 회차 리포트 JSON에서 판정이 갈린 단계와 TC를 센다(읽기 전용).")
    parser.add_argument("inputs", nargs="*",
                        help="리포트 JSON 경로·디렉터리·glob (기본 Reports/Result_*.json)")
    parser.add_argument("--tc", action="append", default=[],
                        help="TC ID 접두어로 거른다(여러 번 지정 가능)")
    parser.add_argument("--since", help="YYYY-MM-DD 이후 리포트만")
    parser.add_argument("--top", type=int, default=30, help="표에 보일 최대 행 수")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args(argv)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = expand_inputs(args.inputs, root=root if not args.inputs else os.getcwd())
    runs, unreadable = load_runs(paths)
    runs = _filter_since(runs, args.since)
    report = analyze(runs, tc_filter=args.tc or None)
    if args.json:
        text = json.dumps(to_json(report, unreadable), ensure_ascii=False, indent=2)
    else:
        text = render_text(report, unreadable, top=args.top)
    stream = sys.stdout
    try:
        stream.write(text + "\n")
    except UnicodeEncodeError:
        stream.buffer.write((text + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
