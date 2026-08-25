# -*- coding: utf-8 -*-
"""`프로젝트_상세.md` → `프로젝트_상세.html` 렌더러.

## 왜 이렇게 하나

사용자 지시(2026-08-26): *"vxvue 처럼 이 프로젝트의 전체의 내용을 한 문서로 볼 수
있는 문서가 있으면 좋겠는데 ... vxvue 구조대로"*, *"리드미에는 그냥 포폴용으로
간단히 하고 이 문서에는 이 프로젝트에 대한 모든 내용이 아주 자세하게 들어가길
원하고"*, *"이 생성 규칙도 벨라룬 기준 md 파일에 있었으면 좋겠고"*.

그래서 **편집은 마크다운에 하고 읽기는 HTML로** 한다. 마크다운이 원본이므로 다음
세션이 이어서 쓰기 쉽고, HTML은 사람이 브라우저로 바로 볼 수 있다. 외부 의존성
없이 표준 라이브러리만 쓴다(이 PC에 마크다운 변환기를 새로 깔지 않는다).

**이 파일은 2026-08-24 의 "HTML 을 직접 갱신한다" 방침을 2026-08-26 사용자 지시로
대체한 것이다.** 그때 렌더러를 두지 않은 이유는 "이미 손으로 유지 중인 HTML 을
자동 변환물이 덮어쓸 수 있다"는 것이었는데, 이제 **원본이 `.md` 하나뿐**이라 그
위험이 없다. HTML 을 직접 고치지 말고 `.md` 를 고친 뒤 이 스크립트를 돌린다.

지원하는 문법은 이 문서가 실제로 쓰는 것만이다 — 제목(`#`~`####`), 표, 코드펜스,
인용(`>`), 목록(`-`), 수평선, `**굵게**`, `` `코드` ``, 링크. 그 밖의 문법은
그대로 평문으로 나온다(모르는 것을 임의로 해석하지 않는다).

`1.` 로 시작하는 번호 목록은 **지원하지 않는다** — 그대로 단락이 된다. 순서가 있는
목록은 `- **1)** ...` 처럼 쓴다.

## 파일 배치

이 스크립트는 **저장소(`auto/`) 안**에 있고, 원본·출력은 **프로젝트 루트**에 있다
(2026-08-26 사용자 지시 — *"render_docs.py는 auto 폴더 내에서 관리될 수 있도록
구조화해주고"*). 스크립트에는 사내 정보가 없어 저장소에서 관리·리뷰하고, 문서
본문에는 컨트롤 ID·DB 스키마 같은 제품 내부 구조가 있어 저장소 밖에 남긴다.

    auto/render_docs.py   ← 이 파일 (Git 포함)
    ../프로젝트_상세.md   ← 원본     (Git 제외)
    ../프로젝트_상세.html ← 생성물   (Git 제외)

## 문서 위계

**`프로젝트_상세.md` 가 기본이고 `auto/README.md` 는 그 포트폴리오 축약형이다**
(2026-08-26 사용자 확정). 새 사실은 상세에 먼저 쓰고, README 는 거기서 골라
줄인다. 상세 갱신 → 이 스크립트 실행 → README 정렬 순서를 지킨다.

실행: `cd auto` 후 `python render_docs.py`
"""


import _paths  # noqa: F401 — 저장소 루트를 sys.path 와 cwd 에 맞춘다
import html
import io
import os
import re
import sys

# 이 스크립트는 저장소(`auto/`) 안에 있고, 문서 본문은 **한 단계 위 프로젝트
# 루트**에 있다. 본문에는 사내 정보와 제품 내부 구조가 들어 있어 공개 원격에
# push 하는 저장소 안에 두지 않는다(부록 D.2).
PROJECT = _paths.PROJECT
SRC = os.path.join(PROJECT, "프로젝트_상세.md")
OUT = os.path.join(PROJECT, "프로젝트_상세.html")

# 레이아웃은 VXvue 의 `프로젝트_상세.html` 과 같다(왼쪽 고정 목차 + 본문).
# 색만 테마 대응을 추가했다 — 뷰어의 라이트/다크 설정을 따라간다.
CSS = """
:root{--fg:#1c1c1e;--muted:#6b6b70;--line:#e3e3e6;--bg:#ffffff;
      --code-bg:#f5f5f7;--accent:#0b5cad;--warn:#a35200;
      --ok:#0a7f3f;--bad:#c62828}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --fg:#e6e8ec;--muted:#a2a9b5;--line:#333842;--bg:#16181d;
    --code-bg:#1f232a;--accent:#7fb0ff;--warn:#f0c169;
    --ok:#5fd39a;--bad:#ff8b8b}
}
:root[data-theme="dark"]{
  --fg:#e6e8ec;--muted:#a2a9b5;--line:#333842;--bg:#16181d;
  --code-bg:#1f232a;--accent:#7fb0ff;--warn:#f0c169;
  --ok:#5fd39a;--bad:#ff8b8b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font-family:'Malgun Gothic','Segoe UI',sans-serif;line-height:1.72;
     font-size:15px}
.wrap{display:flex;align-items:flex-start;max-width:1500px;margin:0 auto}
nav{position:sticky;top:0;width:290px;flex:0 0 290px;max-height:100vh;
    overflow:auto;padding:28px 18px;border-right:1px solid var(--line);
    font-size:13px}
nav h2{font-size:12px;letter-spacing:.08em;color:var(--muted);
       text-transform:uppercase;margin:0 0 10px}
nav a{display:block;color:var(--fg);text-decoration:none;padding:3px 6px;
      border-radius:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
nav a:hover{background:var(--code-bg);color:var(--accent)}
nav a.lv3{padding-left:20px;color:var(--muted)}
main{flex:1;min-width:0;padding:28px 40px 100px}
h1{font-size:27px;margin:0 0 6px;padding-bottom:12px;
   border-bottom:2px solid var(--fg)}
h2{font-size:21px;margin:38px 0 12px;padding-bottom:6px;
   border-bottom:1px solid var(--line)}
h3{font-size:17px;margin:26px 0 8px}
h4{font-size:15px;margin:20px 0 6px;color:var(--muted)}
p{margin:10px 0}
blockquote{margin:14px 0;padding:10px 16px;background:var(--code-bg);
           border-left:3px solid var(--accent)}
blockquote p{margin:5px 0}
code{background:var(--code-bg);padding:1px 5px;border-radius:4px;
     font-family:Consolas,'D2Coding',monospace;font-size:12.8px}
pre{background:var(--code-bg);padding:12px 14px;border-radius:7px;
    overflow-x:auto;border:1px solid var(--line)}
pre code{background:none;padding:0;font-size:12.5px;line-height:1.55}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:13.5px;
      display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:7px 10px;vertical-align:top;
      text-align:left}
th{background:var(--code-bg);font-weight:700;white-space:nowrap}
ul{margin:10px 0;padding-left:22px}
li{margin:4px 0}
hr{border:0;border-top:1px solid var(--line);margin:32px 0}
a{color:var(--accent)}
.meta{color:var(--muted);font-size:12.5px;margin-bottom:20px}
@media print{nav{display:none}main{padding:0}}
"""

CODE_SPAN = re.compile(r"`([^`]+)`")
INLINE = (
    (re.compile(r"\*\*([^*]+)\*\*"), lambda m: "<strong>%s</strong>" % m.group(1)),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"),
     lambda m: '<a href="%s">%s</a>' % (m.group(2), m.group(1))),
)


def inline(text):
    """인라인 문법을 적용한다. **코드 스팬 안은 건드리지 않는다.**

    VXvue 원본은 코드 스팬을 다른 규칙과 같은 목록에서 처리했는데, 그러면 두
    가지가 깨진다(이 문서의 부록 D.4 문법표가 실측으로 드러냈다).

    - **이중 이스케이프** — 맨 위에서 `html.escape` 로 한 번 바꾼 뒤 코드 스팬
      람다가 또 escape 해서 `<hr>` 이 `&amp;lt;hr&amp;gt;` 로 나왔다.
    - **코드 안에서 굵게가 먹었다** — ``**굵게**`` 를 코드로 보여 주려 했는데
      `<code><strong>굵게</strong></code>` 가 됐다.

    그래서 코드 스팬을 먼저 자리표시자로 빼 두고, 굵게·링크를 적용한 뒤 되돌린다.
    자리표시자는 원본에 나올 수 없는 NUL 문자를 쓴다.
    """
    out = html.escape(text)
    spans = []

    def _stash(m):
        spans.append(m.group(1))          # 이미 escape 된 상태다 — 다시 하지 않는다
        return "\x00%d\x00" % (len(spans) - 1)

    out = CODE_SPAN.sub(_stash, out)
    for rx, fn in INLINE:
        out = rx.sub(fn, out)
    for i, code in enumerate(spans):
        out = out.replace("\x00%d\x00" % i, "<code>%s</code>" % code)
    return out


def slug(text, seen):
    base = re.sub(r"[^0-9A-Za-z가-힣]+", "-", text).strip("-").lower() or "s"
    name, n = base, 2
    while name in seen:
        name, n = "%s-%d" % (base, n), n + 1
    seen.add(name)
    return name


def render(md):
    lines = md.replace("\r\n", "\n").split("\n")
    body, toc, seen = [], [], set()
    i = 0
    while i < len(lines):
        ln = lines[i]

        if ln.startswith("```"):                       # 코드펜스
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            body.append("<pre><code>%s</code></pre>"
                        % html.escape("\n".join(buf)))
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if m:
            lvl, text = len(m.group(1)), m.group(2).strip()
            sid = slug(text, seen)
            body.append('<h%d id="%s">%s</h%d>' % (lvl, sid, inline(text), lvl))
            if lvl in (2, 3):
                toc.append('<a class="lv%d" href="#%s">%s</a>'
                           % (lvl, sid, inline(text)))
            i += 1
            continue

        if ln.strip() in ("---", "***", "___"):
            body.append("<hr>")
            i += 1
            continue

        if ln.startswith("|"):                          # 표
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            cells = [[c.strip() for c in r.strip().strip("|").split("|")]
                     for r in rows]
            sep = 1 if len(cells) > 1 and re.match(
                r"^[\s:|-]+$", rows[1].strip().strip("|")) else None
            out = ["<table>"]
            if sep:
                out.append("<thead><tr>%s</tr></thead>"
                           % "".join("<th>%s</th>" % inline(c) for c in cells[0]))
                data = cells[2:]
            else:
                data = cells
            out.append("<tbody>")
            for row in data:
                out.append("<tr>%s</tr>"
                           % "".join("<td>%s</td>" % inline(c) for c in row))
            out.append("</tbody></table>")
            body.append("".join(out))
            continue

        if ln.startswith(">"):                          # 인용
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip())
                i += 1
            paras = " ".join(buf).split("  ")
            body.append("<blockquote>%s</blockquote>"
                        % "".join("<p>%s</p>" % inline(p) for p in paras if p))
            continue

        if re.match(r"^\s*[-*]\s+", ln):                 # 목록
            items, cur = [], None
            while i < len(lines) and (re.match(r"^\s*[-*]\s+", lines[i])
                                      or (lines[i].startswith("  ")
                                          and lines[i].strip() and cur is not None)):
                mm = re.match(r"^\s*[-*]\s+(.*)$", lines[i])
                if mm:
                    if cur is not None:
                        items.append(cur)
                    cur = mm.group(1)
                else:
                    cur += " " + lines[i].strip()
                i += 1
            if cur is not None:
                items.append(cur)
            body.append("<ul>%s</ul>"
                        % "".join("<li>%s</li>" % inline(x) for x in items))
            continue

        if not ln.strip():
            i += 1
            continue

        buf = []                                        # 단락
        # `#`로 시작해도 제목이 아닐 수 있다(예: 결함 번호 `#22985`) — 제목
        # 정규식으로 판별해야 한다. 단순히 startswith("#")로 막으면 그런 줄에서
        # i가 전진하지 않아 **무한 루프**가 난다(VXvue 렌더러 실측 2026-08-21).
        def _breaks(t):
            return (t.startswith(("|", ">", "```"))
                    or re.match(r"^#{1,4}\s+", t) is not None
                    or re.match(r"^\s*[-*]\s+", t) is not None
                    or t.strip() in ("---", "***", "___"))

        while i < len(lines) and lines[i].strip() and not _breaks(lines[i]):
            buf.append(lines[i].strip())
            i += 1
        if not buf:                    # 어떤 경우에도 반드시 전진한다
            buf.append(lines[i].strip())
            i += 1
        body.append("<p>%s</p>" % inline(" ".join(buf)))

    return "\n".join(body), "\n".join(toc)


def main():
    if not os.path.exists(SRC):
        sys.exit("원본이 없다: %s" % SRC)
    md = io.open(SRC, encoding="utf-8").read()
    body, toc = render(md)
    stamp = os.path.getmtime(SRC)
    import datetime
    when = datetime.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M")
    page = ("""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bellalun Viewer QA 자동화 — 프로젝트 상세</title><style>%s</style></head>
<body><div class="wrap">
<nav><h2>목차</h2>%s</nav>
<main><p class="meta">원본 %s 기준 · <code>python render_docs.py</code>로 재생성</p>
%s
</main></div></body></html>
""" % (CSS, toc, when, body))
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(page)
    print("생성: %s (%d자)" % (OUT, len(page)))


if __name__ == "__main__":
    main()
