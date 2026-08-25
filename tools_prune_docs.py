# -*- coding: utf-8 -*-
r"""문서의 **수명**을 관리한다 — 낡은 기록을 아카이브로 내려 읽는 비용을 줄인다.

## 왜 있는가

이 저장소는 "실패를 규칙으로 승격한다"는 방침 때문에 문서가 계속 자란다. 그 자체는
옳지만, 새 세션이 상태를 파악하려고 `AGENTS.md` + `README.md` + `NEXT_WORK.md` +
`NEXT_TASK.md` + 지식 지침 2종을 읽으면 **읽기만으로 큰 비용**이 든다. 그런데 그중
상당 부분은 **이미 끝난 일**이다 — 2026-08-25 실측으로 `NEXT_TASK.md` 1,310줄 가운데
428줄(33%)이 `[완료]` / `(해소됨)` 표시가 붙은 절이었다.

**끝난 일은 지우는 게 아니라 내린다.** 이 도구는 해결 표시가 붙었거나 보존 기간이
지난 절을 `Archive/` 로 **옮기고**, 원래 자리에는 어디로 갔는지 한 줄을 남긴다.
검색하면 그대로 나오고 Git 이력에도 남으므로 **정보는 하나도 사라지지 않는다.**
사라지는 것은 "매 세션 읽어야 하는 분량"뿐이다.

예외는 `HANDOFF.md` 하나다. 운영 지침 15절이 이 파일을 **일회성 인수인계**로 정의했고
영구 규칙은 거기 두지 않기로 이미 정해져 있으므로, 보존 기간(기본 7일)이 지나면
아카이브하지 않고 **지운다**. 다만 커밋되지 않은 상태에서는 지우지 않는다 — Git
이력에도 없는 것을 지우면 그때는 정말 사라지기 때문이다.

## 정책 (`POLICIES` / `BUDGETS` 가 유일한 정의다)

| 문서 | 정책 |
|---|---|
| `HANDOFF.md` | 보존 7일. 지나면 **삭제**(커밋된 경우에만). 영구 규칙은 여기 두지 않는다 |
| `NEXT_TASK.md` | 해결 표시 절 + 보존 기간(기본 60일) 지난 날짜 절 → `Archive/` 로 이동 |
| `[자동화 구현 현황] ...md` | 같은 규칙. 뒤 회차가 대체한 갱신 요약을 `Archive/` 로 이동 |
| `NEXT_WORK.md` | 이동하지 않는다(현재 상태 문서). 줄 수 예산만 점검 |
| `AGENTS.md` / `README.md` / `[자동화 운영 지침]` | **대상 아님.** 영구 규칙·포트폴리오 요약이라 줄 수 예산만 점검 |

**해결 표시**: 절 제목에 `[완료]` `(완료)` `(해소됨)` `(해결됨)` 또는 취소선(`~~`).
**즉시 이관**: 절 안에 `<!-- archive -->` — 규칙으로는 못 잡지만 사람이 "이제 안 읽어도
된다"고 판단한 것(뒤 회차가 대체한 갱신 요약 등). **판단은 사람이, 옮기기는 도구가.**
**보존 예외**: 절 본문 어디든 `<!-- keep -->` 이 있으면 절대 옮기지 않는다.

## 사용법

```
python tools_prune_docs.py              # 점검만 한다(기본). 무엇이 얼마나 줄어드는지 출력
python tools_prune_docs.py --apply      # 실제로 옮기고/지운다
python tools_prune_docs.py --handoff-days 14 --task-days 90
```

`--apply` 뒤에는 **반드시 `git diff` 를 눈으로 본다**(`AGENTS.md` 8절 — 자동 치환으로
코드를 옮기면 diff 를 눈으로 본다. 문서도 같다).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DIR = os.path.join(ROOT, "Archive")

# 절 제목에 이것이 있으면 "끝난 일"로 본다.
RESOLVED_MARKERS = ("[완료]", "(완료)", "(해소됨", "(해결됨", "~~")

# 절 안에 이 표시가 있으면 보존 기간·해결 표시와 무관하게 남긴다.
KEEP_MARKER = "<!-- keep -->"

# 절 안에 이 표시가 있으면 즉시 내린다. 규칙으로는 못 잡지만 사람이 "이제 안 읽어도
# 된다"고 판단한 것 — 회차 갱신 요약처럼 뒤 회차가 대체해 버린 절이 여기 해당한다.
# **판단은 사람이 하고 도구는 옮기기만 한다**(운영 지침 16절).
ARCHIVE_MARKER = "<!-- archive -->"

DATE_RE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")


class Policy:
    """문서 하나의 수명 정책."""

    def __init__(self, path, mode, archive=None, days=None, budget=None, note=""):
        self.path = path          # ROOT 기준 상대 경로
        self.mode = mode          # "delete" | "archive" | "budget"
        self.archive = archive    # archive 모드일 때 옮겨 담을 파일
        self.days = days          # 보존 기간(일)
        self.budget = budget      # 줄 수 예산
        self.note = note


# ---------------------------------------------------------------- 정책 정의
def policies(handoff_days, task_days):
    return [
        Policy("HANDOFF.md", "delete", days=handoff_days,
               note="일회성 인수인계. 영구 규칙은 지식 지침에 둔다(운영 지침 15절)"),
        Policy("NEXT_TASK.md", "archive",
               archive=os.path.join("Archive", "NEXT_TASK_완료기록.md"),
               days=task_days, budget=900,
               note="누적 인수인계. 끝난 일은 내리고 실측 지식만 남긴다"),
        Policy("NEXT_WORK.md", "budget", budget=400,
               note="현재 상태 문서. 회차가 끝나면 누적 기록은 NEXT_TASK.md 로 옮긴다"),
        Policy("AGENTS.md", "budget", budget=350, note="영구 규칙"),
        Policy("README.md", "budget", budget=320, note="포트폴리오 요약(간결 유지)"),
        Policy(os.path.join("..", "지식",
                            "[자동화 운영 지침] Bellalun Viewer auto 저장소 구현 규칙.md"),
               "budget", budget=1300, note="영구 구현 규칙과 사고 이력"),
        # 구현 현황은 **영구 규칙이 아니라 상태 문서**다. 회차 갱신 요약이 쌓이고
        # 뒤 회차가 앞 회차를 대체하므로 이관 대상으로 둔다.
        Policy(os.path.join("..", "지식",
                            "[자동화 구현 현황] Bellalun Viewer auto 구현 상태.md"),
               "archive",
               archive=os.path.join("Archive", "구현현황_지난회차.md"),
               days=task_days, budget=500,
               note="상태 문서. 뒤 회차가 대체한 갱신 요약은 내린다"),
    ]


# ---------------------------------------------------------------- 공통 유틸
def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def est_tokens(chars):
    """한국어가 섞인 문서의 대략적인 토큰 수. 정확한 값이 아니라 **규모 감각**용이다."""
    return int(chars / 1.8)


def git_tracked_and_clean(rel):
    """그 파일이 Git 에 커밋돼 있고, 커밋 이후 수정되지 않았는가."""
    try:
        ls = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                            cwd=ROOT, capture_output=True, text=True)
        if ls.returncode != 0:
            return False, "Git 에 없다(커밋되지 않았다)"
        st = subprocess.run(["git", "status", "--porcelain", "--", rel],
                            cwd=ROOT, capture_output=True, text=True)
        if st.stdout.strip():
            return False, "커밋 이후 수정됐다"
        return True, ""
    except FileNotFoundError:
        return False, "git 을 찾을 수 없다"


def newest_date_in(text):
    """문서 안에서 가장 늦은 YYYY-MM-DD. 없으면 None."""
    best = None
    for y, m, d in DATE_RE.findall(text):
        try:
            got = _dt.date(int(y), int(m), int(d))
        except ValueError:
            continue
        if best is None or got > best:
            best = got
    return best


# ---------------------------------------------------------------- 절 나누기
class Section:
    def __init__(self, level, title, start, lines):
        self.level = level
        self.title = title
        self.start = start
        self.lines = lines      # 제목 줄을 포함한 본문

    @property
    def text(self):
        return "\n".join(self.lines)

    @property
    def resolved(self):
        return any(m in self.title for m in RESOLVED_MARKERS)

    @property
    def keep(self):
        return KEEP_MARKER in self.text

    @property
    def marked_archive(self):
        return ARCHIVE_MARKER in self.text

    @property
    def date(self):
        """제목의 날짜를 우선하고, 없으면 본문 처음 5줄에서 찾는다."""
        for src in (self.title, "\n".join(self.lines[1:6])):
            hits = DATE_RE.findall(src)
            if hits:
                y, m, d = hits[0]
                try:
                    return _dt.date(int(y), int(m), int(d))
                except ValueError:
                    pass
        return None


def split_sections(text, levels=(2, 3)):
    """`## `/`### ` 로 문서를 절로 나눈다. 첫 제목 앞의 머리말은 preamble 로 돌려준다."""
    lines = text.split("\n")
    heads = []
    fence = False
    for i, line in enumerate(lines):
        if line.startswith("```"):
            fence = not fence
        if fence:
            continue                      # 코드 블록 안의 `#` 는 제목이 아니다
        m = re.match(r"^(#{2,6}) (.*)$", line)
        if m and len(m.group(1)) in levels:
            heads.append((i, len(m.group(1)), m.group(2)))
    if not heads:
        return text, []
    preamble = "\n".join(lines[: heads[0][0]])
    secs = []
    for n, (i, lv, title) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        secs.append(Section(lv, title, i, lines[i:end]))
    return preamble, secs


# ---------------------------------------------------------------- 각 정책 처리
def do_delete(pol, today, apply_):
    path = os.path.join(ROOT, pol.path)
    if not os.path.exists(path):
        return {"state": "없음", "msg": f"{pol.path} 없음 — 정책만 유지({pol.days}일)"}
    text = read(path)
    mtime = _dt.date.fromtimestamp(os.path.getmtime(path))
    inner = newest_date_in(text)
    # 파일 수정 시각과 문서가 스스로 적은 날짜 중 **늦은 쪽**을 기준으로 삼는다.
    ref = max([d for d in (mtime, inner) if d], default=mtime)
    age = (today - ref).days
    chars = len(text)
    if age <= pol.days:
        return {"state": "유지", "msg":
                f"{pol.path} — 기준일 {ref} (경과 {age}일 ≤ 보존 {pol.days}일)"}
    ok, why = git_tracked_and_clean(pol.path)
    if not ok:
        return {"state": "보류", "msg":
                f"{pol.path} — 보존 기간({pol.days}일)을 넘겼지만 지우지 않는다: {why}. "
                f"먼저 커밋하면 다음 실행에서 삭제된다"}
    if apply_:
        os.remove(path)
    return {"state": "삭제", "chars": chars, "msg":
            f"{pol.path} — 기준일 {ref} (경과 {age}일 > 보존 {pol.days}일) "
            f"{'삭제함' if apply_ else '삭제 대상'}. Git 이력에 남는다"}


def do_archive(pol, today, apply_):
    path = os.path.join(ROOT, pol.path)
    if not os.path.exists(path):
        return {"state": "없음", "msg": f"{pol.path} 없음"}
    text = read(path)
    preamble, secs = split_sections(text)
    if not secs:
        return {"state": "유지", "msg": f"{pol.path} — 절을 찾지 못했다"}

    move, keep, review = [], [], []
    for s in secs:
        if s.keep:
            keep.append(s)
            continue
        if s.marked_archive:
            move.append((s, "이관 표시(사람이 판단)"))
            continue
        if s.resolved:
            move.append((s, "해결 표시"))
            continue
        if s.date and (today - s.date).days > pol.days:
            move.append((s, f"{s.date} — 보존 {pol.days}일 경과"))
            continue
        # 옮기지는 않지만 사람이 한 번 볼 만한 것
        if s.date and (today - s.date).days > pol.days // 2:
            review.append((s, f"{s.date}"))
        keep.append(s)

    if not move:
        return {"state": "유지",
                "msg": f"{pol.path} — 옮길 절 없음 (절 {len(secs)}개)",
                "review": review}

    # 상위 절이 옮겨지면 그 안의 하위 절도 함께 간다(줄 범위가 이미 분리돼 있으므로
    # 여기서는 제목 수준만 확인해 사람이 읽을 로그에 표시한다).
    moved_chars = sum(len(s.text) + 1 for s, _ in move)

    if apply_:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        apath = os.path.join(ROOT, pol.archive)
        head = (
            f"# {os.path.basename(pol.path)} — 아카이브 (끝난 기록)\n\n"
            "> `tools_prune_docs.py` 가 옮겨 담는다. **읽는 비용을 줄이려고 내린 것이지\n"
            "> 지운 것이 아니다** — 원문 그대로이고 Git 이력에도 남아 있다.\n"
            "> 새 세션은 이 파일을 읽지 않아도 된다. 과거 경위를 되짚을 때만 검색한다.\n"
        )
        prev = read(apath) if os.path.exists(apath) else head
        if not prev.startswith("#"):
            prev = head + prev
        chunks = [prev.rstrip("\n"), "",
                  f"<!-- {today} 이관 — {os.path.basename(pol.path)} -->", ""]
        for s, why in move:
            chunks.append(f"<!-- 이관 사유: {why} -->")
            chunks.append(s.text.rstrip("\n"))
            chunks.append("")
        write(apath, "\n".join(chunks) + "\n")

        # 링크는 **그 문서가 있는 폴더 기준**이어야 한다. `지식\` 의 문서는
        # `auto\Archive\` 가 상위 폴더 건너편에 있으므로 `../auto/Archive/...` 가 된다.
        rel = os.path.relpath(os.path.join(ROOT, pol.archive),
                              os.path.dirname(path)).replace("\\", "/")
        out = [preamble.rstrip("\n"), ""]
        stubbed = False
        for s in secs:
            if any(s is m for m, _ in move):
                if not stubbed:
                    out.append(
                        f"> **끝난 기록은 [`{rel}`]({rel}) 로 내렸다** "
                        f"({today} 기준 {len(move)}개 절 / {moved_chars:,}자). "
                        "지운 것이 아니라 옮긴 것이라 검색하면 그대로 나온다 — "
                        "`tools_prune_docs.py` 참고.")
                    out.append("")
                    stubbed = True
                continue
            out.append(s.text.rstrip("\n"))
            out.append("")
        write(path, "\n".join(out).rstrip("\n") + "\n")

    return {"state": "이관", "chars": moved_chars, "review": review,
            "msg": f"{pol.path} — 절 {len(move)}개 / {moved_chars:,}자 "
                   f"{'이관함' if apply_ else '이관 대상'} → {pol.archive}",
            "detail": [(s.title, why) for s, why in move]}


def do_budget(pol):
    path = os.path.join(ROOT, pol.path)
    if not os.path.exists(path):
        return {"state": "없음", "msg": f"{pol.path} 없음"}
    text = read(path)
    n = text.count("\n") + 1
    over = n > pol.budget
    return {"state": "초과" if over else "이내",
            "msg": f"{n:>5}줄 / 예산 {pol.budget}줄  "
                   f"(약 {est_tokens(len(text)):,} 토큰)  {pol.path}"}


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="낡은 문서 기록을 아카이브로 내려 읽는 비용을 줄인다")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 옮기고/지운다 (기본은 점검만)")
    ap.add_argument("--handoff-days", type=int, default=7,
                    help="HANDOFF.md 보존 기간(일). 기본 7")
    ap.add_argument("--task-days", type=int, default=60,
                    help="NEXT_TASK.md 날짜 절 보존 기간(일). 기본 60")
    ap.add_argument("--today", default="",
                    help="기준일 YYYY-MM-DD (시험용). 기본은 오늘")
    args = ap.parse_args(argv)

    today = (_dt.date.fromisoformat(args.today) if args.today
             else _dt.date.today())
    pols = policies(args.handoff_days, args.task_days)

    print("=" * 78)
    print(f" 문서 수명 점검 — 기준일 {today}"
          f"{'   [--apply: 실제로 반영한다]' if args.apply else '   [점검만]'}")
    print(f" 보존 기간: HANDOFF {args.handoff_days}일 / NEXT_TASK 날짜 절 "
          f"{args.task_days}일")
    print("=" * 78)

    saved = 0
    reviews = []
    print("\n[정리]")
    for pol in pols:
        if pol.mode == "delete":
            r = do_delete(pol, today, args.apply)
        elif pol.mode == "archive":
            r = do_archive(pol, today, args.apply)
        else:
            continue
        print(f"  [{r['state']}] {r['msg']}")
        for title, why in r.get("detail", []) or []:
            print(f"           · {title[:64]}   ({why})")
        saved += r.get("chars", 0)
        reviews.extend(r.get("review", []) or [])

    if reviews:
        print("\n[검토 권장] 아직 옮기지 않았지만 낡아 가는 절 — 사람이 판단한다")
        for s, when in reviews:
            print(f"  · {when}  {s.title[:64]}")

    print("\n[줄 수 예산]")
    over = []
    for pol in pols:
        r = do_budget(pol)
        if r["state"] == "없음":
            continue
        mark = "!!" if r["state"] == "초과" else "  "
        print(f"  {mark} {r['msg']}")
        if r["state"] == "초과":
            over.append(pol.path)

    print("\n" + "-" * 78)
    if saved:
        print(f" 절감: {saved:,}자 (약 {est_tokens(saved):,} 토큰) "
              f"{'반영됨' if args.apply else '— 반영하려면 --apply'}")
    else:
        print(" 절감: 없음 — 정리할 것이 없다")
    if over:
        print(f" 예산 초과 {len(over)}건: {', '.join(over)}")
        print(" 예산은 상한이 아니라 **신호**다. 넘으면 무엇을 내릴지 사람이 정한다.")
    if args.apply:
        print(" `git diff` 를 눈으로 확인한 뒤 커밋한다.")
    print("-" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
