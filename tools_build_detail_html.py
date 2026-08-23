# -*- coding: utf-8 -*-
r"""프로젝트 루트의 `프로젝트 상세.html`(운영 상세 문서)을 만든다.

    python tools_build_detail_html.py

## 왜 생성기인가

이 문서에는 자동화 범위 전수표, `run.py` 명령 전수표, 사양↔TC 추적성 표, 코드 규모,
최신 회귀 수치가 들어간다. 손으로 옮겨 적으면 **문서만 낡는다.** 그래서 표와 수치는
저장소의 실제 파일에서 생성한다.

  - 자동화 범위·커버리지  <- `automation_scope.json`
  - 명령 전수             <- `run.py` 의 `sub.add_parser(...)` 소스
  - 추적성                <- `traceability.json`
  - 코드 규모             <- `core/` `tests/` `tools_*.py` `run.py` 실측
  - 최신 회귀 수치        <- `REG_REPORT` 이 가리키는 리포트 JSON

**설명 문장은 이 스크립트 안의 상수에 둔다.** 문장을 고칠 때는 여기를 고치고 다시
생성한다. HTML 을 직접 편집하면 다음 생성에서 사라진다.

회귀를 새로 돌렸으면 `REG_REPORT` 를 그 리포트로 바꾼 뒤 다시 생성한다.
"""
import html
import io
import json
import os
import re
import subprocess
import sys

# 경로를 하드코딩하지 않는다 — 이 파일 위치 기준으로 찾는다(`core/specs.py`,
# `core/checklist.py` 와 같은 방식). PC 마다 사용자 폴더가 다르다.
AUTO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(AUTO)
OUT = os.path.join(ROOT, "프로젝트 상세.html")
sys.path.insert(0, AUTO)
os.chdir(AUTO)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def e(text):
    return html.escape(str(text if text is not None else ""))


def load(path):
    with io.open(path, encoding="utf-8") as stream:
        return json.load(stream)


scope = load("automation_scope.json")
trace = load("traceability.json")

# run.py 서브명령 + help 문구 (실제 등록된 것만)
with io.open("run.py", encoding="utf-8") as f:
    run_src = f.read()
commands = re.findall(
    r'sub\.add_parser\(\s*"([^"]+)"\s*,?\s*(?:help=\s*((?:"[^"]*"\s*)+))?\)',
    run_src)
cmd_rows = []
for name, help_text in commands:
    text = " ".join(re.findall(r'"([^"]*)"', help_text or "")).strip()
    cmd_rows.append((name, text))

# 코드 규모 실측
def count(paths):
    lines = 0
    files = 0
    for path in paths:
        with io.open(path, encoding="utf-8", errors="replace") as stream:
            lines += sum(1 for _ in stream)
        files += 1
    return lines, files


core_files = sorted(os.path.join("core", n) for n in os.listdir("core")
                    if n.endswith(".py"))
test_files = sorted(os.path.join("tests", n) for n in os.listdir("tests")
                    if n.endswith(".py"))
tool_files = sorted(n for n in os.listdir(".") if n.startswith("tools_")
                    and n.endswith(".py"))
core_lines, core_n = count(core_files)
test_lines, test_n = count(test_files)
tool_lines, tool_n = count(tool_files)
run_lines, _ = count(["run.py"])
total_lines = core_lines + test_lines + tool_lines + run_lines
total_files = core_n + test_n + tool_n + 1

levels = {}
for item in scope:
    levels[item["level"]] = levels.get(item["level"], 0) + 1
checklist_tc = [x for x in scope if x["level"] != "SUPPORT"]

# 최신 전체 회귀(실측): 리포트 JSON 에서 직접 센다
REG_REPORT = "Reports/Result_20260821_164016.json"
reg = load(REG_REPORT)["results"]
reg_tc = {}
reg_check = {}
for r in reg:
    reg_tc[r["verdict"]] = reg_tc.get(r["verdict"], 0) + 1
    for c in r.get("checks", []):
        reg_check[c["status"]] = reg_check.get(c["status"], 0) + 1
reg_minutes = sum(float(r.get("duration_seconds") or 0) for r in reg) / 60
reg_fails = [(r["tc_id"], c.get("step"), c.get("title"))
             for r in reg for c in r.get("checks", []) if c["status"] == "FAIL"]

STYLE = """
:root{
  --bg:#ffffff; --fg:#1b1b1b; --mut:#5d6470; --line:#dcdfe4;
  --card:#f7f8fa; --head:#eef1f5; --accent:#1558b0; --ok:#0a7f3f;
  --bad:#c62828; --warn:#a06000; --code:#f3f4f6;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#16181d; --fg:#e6e8ec; --mut:#a2a9b5; --line:#333842;
    --card:#1d2027; --head:#232830; --accent:#7fb0ff; --ok:#5fd39a;
    --bad:#ff8b8b; --warn:#f0c169; --code:#1f232a;
  }
}
:root[data-theme="dark"]{
  --bg:#16181d; --fg:#e6e8ec; --mut:#a2a9b5; --line:#333842;
  --card:#1d2027; --head:#232830; --accent:#7fb0ff; --ok:#5fd39a;
  --bad:#ff8b8b; --warn:#f0c169; --code:#1f232a;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font-family:'Malgun Gothic','Segoe UI',system-ui,sans-serif;line-height:1.65;
  font-size:15px}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:27px;margin:0 0 6px;letter-spacing:-.4px}
h2{font-size:20px;margin:44px 0 10px;padding-top:14px;
  border-top:2px solid var(--line)}
h3{font-size:16px;margin:26px 0 6px}
h4{font-size:14px;margin:18px 0 4px;color:var(--mut)}
p,li{margin:6px 0}
a{color:var(--accent)}
code,pre{font-family:Consolas,'Cascadia Mono',monospace}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:13px}
pre{background:var(--code);border:1px solid var(--line);border-radius:8px;
  padding:12px 14px;overflow-x:auto;font-size:13px;line-height:1.55}
pre code{background:none;padding:0}
.sub{color:var(--mut);font-size:14px;margin:0 0 18px}
.tablewrap{overflow-x:auto;margin:10px 0 4px}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:520px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;
  vertical-align:top}
th{background:var(--head);font-weight:600;white-space:nowrap}
td.n{text-align:center;white-space:nowrap}
.tiles{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0 6px}
.tile{flex:1 1 165px;border:1px solid var(--line);border-radius:10px;
  padding:13px 15px;background:var(--card)}
.tile .n{font-size:25px;font-weight:700;line-height:1.15}
.tile .k{font-size:12px;color:var(--mut);margin-top:2px}
.note{background:var(--card);border-left:4px solid var(--accent);
  border-radius:0 8px 8px 0;padding:10px 14px;margin:14px 0}
.warn{border-left-color:var(--warn)}
.bad{border-left-color:var(--bad)}
.FULL{color:var(--ok);font-weight:600}
.PARTIAL{color:var(--warn);font-weight:600}
.MANUAL{color:var(--mut);font-weight:600}
.SUPPORT{color:var(--accent);font-weight:600}
nav.toc{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:14px 18px;margin:18px 0 6px}
nav.toc ol{margin:4px 0 0;padding-left:22px;columns:2;column-gap:28px}
nav.toc li{break-inside:avoid}
hr{border:0;border-top:1px solid var(--line);margin:32px 0}
.small{font-size:12.5px;color:var(--mut)}
"""


def table(headers, rows, classes=""):
    out = [f"<div class='tablewrap'><table class='{classes}'><tr>"]
    out += [f"<th>{e(h)}</th>" for h in headers]
    out.append("</tr>")
    for row in rows:
        out.append("<tr>" + "".join(
            (c if isinstance(c, _Raw) else f"<td>{e(c)}</td>") for c in row)
            + "</tr>")
    out.append("</table></div>")
    return "\n".join(out)


class _Raw(str):
    pass


def raw(text):
    return _Raw(text)


P = []
A = P.append

A(f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
  f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
  f"<title>Bellalun Viewer QA 자동화 — 프로젝트 상세</title>"
  f"<style>{STYLE}</style></head><body><div class='wrap'>")

A("<h1>Bellalun Viewer 기본기능 QA 자동화 — 프로젝트 상세</h1>")
A("<p class='sub'>운영 문서입니다. 저장소 개요와 포트폴리오 요약은 "
  "<code>auto/README.md</code>를 보십시오. 이 문서의 표와 수치는 "
  "<code>automation_scope.json</code> · <code>traceability.json</code> · "
  "<code>run.py</code> · 리포트 JSON에서 생성했습니다 "
  "(기준 시점 2026-08-24).</p>")

A("""<nav class='toc'><b>목차</b><ol>
<li><a href='#quick'>Quick Start</a></li>
<li><a href='#basis'>기준 문서와 판정 근거</a></li>
<li><a href='#arch'>아키텍처</a></li>
<li><a href='#rules'>설계 원칙</a></li>
<li><a href='#tech'>기술 선택</a></li>
<li><a href='#cmd'>실행 명령 전수</a></li>
<li><a href='#out'>결과물과 리포트 구성</a></li>
<li><a href='#addtc'>TC를 새로 추가하는 절차</a></li>
<li><a href='#trace'>추적성 (사양↔TC)</a></li>
<li><a href='#scope'>자동화 범위 전수</a></li>
<li><a href='#reg'>회귀 실적</a></li>
<li><a href='#trouble'>문제 해결</a></li>
<li><a href='#limit'>제한사항</a></li>
<li><a href='#lesson'>실제로 잡아낸 결함과 교훈</a></li>
<li><a href='#docs'>참고 문서</a></li>
</ol></nav>""")

A("<div class='tiles'>")
for value, label in [
        (f"{total_lines:,}", f"Python 줄 ({total_files}개 모듈)"),
        (len(checklist_tc), "개정본 TC 전수 등록"),
        (levels.get("FULL", 0), "완전 자동 (FULL)"),
        (f"{reg_minutes:.0f}분", "최신 전체 회귀 소요"),
        (sum(reg_check.values()), "회귀 1회 검증 항목")]:
    A(f"<div class='tile'><div class='n'>{e(value)}</div>"
      f"<div class='k'>{e(label)}</div></div>")
A("</div>")

# ---------------------------------------------------------------- Quick Start
A("<h2 id='quick'>1. Quick Start</h2>")
A("<h3>1.1 준비 — 실제 명령</h3>")
A("""<pre><code>cd "C:\\Users\\&lt;사용자&gt;\\...\\Bellalun Viewer\\auto"

python -m pip install -r requirements.txt
copy config.example.json config.json        :: 계정·경로·서버 주소를 채운다
python run.py portability-check              :: 해상도·DPI·권한·필수 경로 점검</code></pre>""")
A("<p><code>portability-check</code>가 하나라도 FAIL이면 UI 자동화를 시작하지 "
  "않습니다. 조용히 오작동하는 대신 시작 시점에 막는 것이 설계 의도입니다.</p>")

A("<h3>1.2 실행 환경 요구조건</h3>")
A(table(["항목", "요구값", "확인 방법", "충족하지 않으면"], [
    ("관리자 권한", "High Integrity (Python 프로세스 자체)",
     raw("<td><code>python -c \"import sys;sys.path.insert(0,'.');"
         "from core import sysinfo;print(sysinfo.is_elevated())\"</code></td>"),
     "VIEWER.exe가 requireAdministrator라 Windows UIPI가 입력 주입을 차단합니다. "
     "화면 캡처는 되고 클릭만 조용히 실패해 엉뚱한 증상으로 보입니다"),
    ("Primary display", "1920×1080",
     raw("<td><code>python run.py portability-check</code></td>"),
     "좌표 기반 조작이 어긋납니다. 시작 시점에 FAIL"),
    ("배율/DPI", "100% (96 DPI)",
     raw("<td>같음</td>"), "같음"),
    ("Tesseract-OCR", "설치 + config의 tesseract_exe 경로",
     raw("<td>같음</td>"), "커스텀 렌더링 값을 읽을 수 없습니다"),
    ("SQL Server 인스턴스", "예: .\\BELLALUN (Integrated Security)",
     raw("<td><code>python -c \"import sys;sys.path.insert(0,'.');"
         "from core.db import BellalunDb;print(BellalunDb(r'.\\BELLALUN')"
         ".ping('DATA'))\"</code></td>"),
     "DB 교차 검증이 전부 불가"),
    ("XIPL Studio", "config의 studio_exe 경로",
     raw("<td><code>python run.py portability-check</code></td>"),
     "XIPL 연동 TC 불가"),
]))

A("<h3>1.3 설정 — <code>config.json</code></h3>")
A("<p><code>config.json</code>은 <b>Git에 올리지 않습니다</b>(계정·서버 주소·PC별 "
  "경로). 저장소에는 <code>config.example.json</code> 템플릿만 있습니다. 주요 절:</p>")
A(table(["절", "무엇을 정하는가", "메모"], [
    ("viewer.exe / viewer.login", "Viewer 실행 파일과 자동 로그인 계정",
     "계정은 사용자 승인 하에만 넣습니다"),
    ("sql_server / data_dir", "DB 인스턴스와 제품 데이터 폴더",
     "data_dir은 드라이브 문자가 달라도 run.py가 모든 드라이브를 탐색해 찾습니다"),
    ("dicom.*", "MWL / Storage / Print 서버 주소·AE Title·포트",
     "setup-dicom이 이 값으로 등록하고 C-ECHO까지 확인합니다"),
    ("xipl.parameter_dir", "XIPL 파라미터 폴더 (예: C:\\XIPL\\PARAMETER)",
     "시험 파라미터 TEST_*는 여기에 만들어집니다"),
    ("xipl.*_timeout / *_wait", "조건 기반 대기의 상한(초)",
     "그 시간을 무조건 기다리는 것이 아니라 완료 신호가 오면 즉시 넘어갑니다"),
    ("demo.settle_seconds", "Demo(F8) 촬영 후 잔여 정착 시간",
     "TC_XIPL_compatibility_07은 이 고정 대기를 쓰지 않고 DB 도착을 기다립니다"),
    ("display.enforce", "해상도를 강제로 1920×1080으로 바꿀지",
     "false면 맞지 않을 때 FAIL만 하고 바꾸지 않습니다"),
]))

A("<h3>1.4 시험 데이터</h3>")
A(table(["종류", "무엇", "누가 만드는가"], [
    ("기준 DB 스냅샷", "Baseline/*.bak (DATA/ACCOUNT/PROCEDURE/CONFIGURATION)",
     "python run.py snapshot-baseline — 회귀는 시작 시 이것으로 복원합니다"),
    ("검사 픽스처", "DATA_FLOW_MWL_01 (2D + 3D Raw)",
     "WF_01 / WF_02가 만들고 WF_03~15와 XIPL이 재사용합니다"),
    ("XIPL 시험 파라미터",
     "TEST_2D_A_M.pim / TEST_2D_B_M.pim / TEST_2D_FLOW_M.pim / "
     "TEST_XIPL_SAVED_M.pim / TEST_3D_FLOW.xtp / TEST_3D_NARROW.xtp / "
     "TEST_3D_WIDE.xtp / TEST_QC_2D_M.pim / TEST_QC_3D.eap",
     "회귀 시작 시 core/viewer_processing.reset_parameter_copies가 전부 지우고 "
     "제품 기본 파라미터에서 다시 복사합니다"),
    ("TC 전용 검사",
     "DATA_XIPL_PRESET_01 (XIPL_04) / DATA_XIPL_3D_01 (XIPL_07) / "
     "SYS3D_* (보조 3D)",
     "촬영 자체가 판정 조건인 TC만 따로 촬영합니다(개정본 '개정 원칙' 4항)"),
]))

A("<h3>1.5 로그·증거·리포트가 남는 위치</h3>")
A(table(["위치", "무엇", "Git"], [
    ("auto/Reports/Result_&lt;시각&gt;.html", "상세 리포트(사람이 읽는 주 산출물)",
     "제외(런타임 산출물)"),
    ("auto/Reports/Result_&lt;시각&gt;.{json,csv,txt}", "기계 판독·표·터미널 요약",
     "제외"),
    ("auto/Reports/Checklist_Result_&lt;시각&gt;.xlsx",
     "기준 체크리스트 원본 행 옆에 판정 열을 붙인 사본(원본은 수정하지 않음)",
     "제외"),
    ("auto/Evidence/", "단계별 화면 캡처와 크롭(판정 근거 이미지)", "제외"),
    ("auto/Log/, auto/Cache/, auto/Temp/, auto/work/",
     "자동화 실행 로그·중간 산출물", "제외"),
    ("&lt;data_dir&gt;\\Log\\Viewer\\YYYY_MM_DD.log",
     "<b>제품</b> Viewer 로그 — 파라미터 적용·Reconstruction 완료 판정의 근거",
     "제품 데이터(저장소 밖)"),
]))
A("<div class='note'>리포트 상단 '실행 환경' 표의 경로는 <b>클릭하면 열립니다</b> — "
  "제품 로그와 증거 폴더 포함. 실패를 재현할 때 리포트 한 장에서 출발할 수 있게 "
  "하려는 의도입니다.</div>")

A("<h3>1.6 실패를 확인하는 순서</h3>")
A("""<ol>
<li><b>리포트 상단의 '실패 항목 원인' 표</b>부터 봅니다. 회귀는 앞선 TC가 실패하면
뒤가 전제 미충족으로 연쇄 실패하므로 <b>가장 앞선 FAIL</b>이 원인입니다.</li>
<li>판정의 <code>기대값</code>/<code>실제값</code>/<code>판정 근거</code> 세 열을 봅니다.
근거에는 <b>무엇을 대조했는지</b>(DB 쿼리·로그 문구·파일 경로·UI 재진입)와 인용한
문서·쪽·SRS ID가 적혀 있습니다.</li>
<li><code>Evidence/</code>의 해당 캡처를 <b>눈으로</b> 봅니다. OCR이 못 읽었다는 판정은
타이밍 문제보다 전처리 문제인 경우가 많았습니다(과거 2건 모두).</li>
<li>"전제 미충족" 문구가 있으면 <b>제품 판정이 아닙니다</b> — 픽스처 없음, 서버 미등록,
GPU 없음 등 환경 사유입니다.</li>
<li>재현은 회귀 시작 상태에서 합니다:
<code>python run.py reset-environment</code> → 해당 <code>run-*</code> 명령.</li>
</ol>""")
A("<div class='note warn'><b>단독 실행 통과 ≠ 그 분기 검증.</b> "
  "<code>ensure_*</code> 계열 헬퍼는 조건이 이미 충족되면 건너뜁니다. 회귀에서만 "
  "깨지는 결함(모듈 오염, 저장 확인 팝업, Storage 활성 행 중복)은 모두 이 형태였습니다. "
  "고쳤다고 말하기 전에 <code>reset-environment</code>부터 다시 지나가십시오.</div>")

A("<h3>1.7 사전 검사 (긴 실행 전 필수)</h3>")
A("""<pre><code>python -m py_compile &lt;바꾼 파일&gt;
python tools_check_module_attrs.py        :: 모듈 속성 오염·없는 이름 참조
python tools_check_regression_names.py    :: 회귀 블록 이름 결속
python tools_traceability.py              :: 인용·모듈·명령·Step 범위 대조
python -m unittest discover -s tests -p "test_*.py"</code></pre>""")
A("<p><code>py_compile</code>만으로는 부족합니다. 실제로 겪은 세 가지를 각각 다른 "
  "검사가 막습니다 — 누락된 <code>import</code>(실행 시 NameError), 다른 분기의 "
  "import가 만든 <code>UnboundLocalError</code>(회귀 41분 뒤 사망), 자동 치환이 "
  "모듈 함수를 리스트로 덮어쓴 것(다음 TC에서 사망).</p>")

# --------------------------------------------------------------------- basis
A("<h2 id='basis'>2. 기준 문서와 판정 근거</h2>")
A("<p><b>시험 대상 TC의 유일한 기준</b>은 "
  "<code>Bellalun_Viewer_기본기능_Checklist_개정본.xlsx</code>의 "
  "<code>개정 TC</code> 시트입니다. TC ID·Title·Precondition·Step Description·"
  "Expected Result·Test Data를 여기서만 확인합니다.</p>")
A("<div class='note bad'><b>혼동 주의.</b> "
  "<code>지식\\(TC) R-23-2346_BellalunViewer_기본기능_Checklist.xlsx</code>는 "
  "<b>다른 문서</b>입니다. 같은 형태의 TC ID를 쓰지만 번호 매핑이 다릅니다. "
  "이 둘을 혼동해 정상 구현된 TC를 '범위 불일치'로 잘못 강등한 일이 있었습니다.</div>")
A("<p>TC가 <b>무엇을 하는지</b>는 개정본에서, <b>왜 그것이 정상인지</b>는 아래에서 "
  "확인합니다.</p>")
A(table(["문서", "여기서 확인하는 것"], [
    ("(사양서) Bellalun Viewer 사양서1 / 2 (.pdf)",
     "요구사항 본문. SRS ID(예: SRS 03-10-110)와 쪽 번호로 인용합니다. "
     "core/specs.py가 PDF를 검색해 문구·쪽·SRS를 함께 돌려줍니다"),
    ("Operation Manual (.docx / 추출 .txt)", "사용자 조작 절차와 기대 동작"),
    ("Service Manual (.docx / 추출 .txt)",
     "Setting 각 항목의 의미·선택지·반영 조건"),
    ("DICOM Conformance Statement", "SOP Class, Transfer Syntax, SCU/SCP 동작"),
    ("[자동화 운영 지침] …md", "영구 적용 규칙(0절이 문서 근거 규칙)"),
    ("[자동화 구현 현황] …md", "TC별 구현 수준과 연결 상태"),
    ("[QA 작성 규칙] …md", "TC 설계·자체검토 방법론"),
]))
A("<div class='note bad'><b>화면을 보고 합격 기준을 역산하면 결함을 정상으로 "
  "인증합니다.</b> 실제로 두 번 겪었습니다 — Window Level은 매뉴얼이 'W1/W2 값의 "
  "증가·감소'로 정의하는데 '화면 픽셀이 몇 % 바뀌었나'라는 대리 지표를 써서 "
  "<b>정상 동작을 FAIL로 뒤집었고</b>, Q.C 파라미터는 형식을 확인하지 않아 "
  "<b>깨진 파일이 PASS처럼 보였습니다</b>.</div>")

# ---------------------------------------------------------------------- arch
A("<h2 id='arch'>3. 아키텍처</h2>")
A("<h3>3.1 코드 규모 (실측)</h3>")
A(table(["계층", "줄", "파일"], [
    ("core/ (재사용 계층)", f"{core_lines:,}", core_n),
    ("tests/ (TC 시나리오·판정)", f"{test_lines:,}", test_n),
    ("run.py (CLI·환경 게이트·리포트)", f"{run_lines:,}", 1),
    ("tools_*.py (자체 검사 도구)", f"{tool_lines:,}", tool_n),
    (raw("<td><b>합계</b></td>"), raw(f"<td><b>{total_lines:,}</b></td>"),
     raw(f"<td><b>{total_files}</b></td>")),
]))

A("<h3>3.2 파일명 ↔ TC 번호</h3>")
A("<p><code>tests/workflowNN.py</code>의 <code>NN</code>이 체크리스트 TC 번호입니다. "
  "파일명만 보고 어느 TC인지 알 수 있게 1:1로 맞췄습니다. 이 정리 전에는 "
  "<code>tests/workflow03.py</code>가 <code>WF_08</code>(Film Print)을 담고 있었고, "
  "한 파일에 세 TC가 섞여 있었습니다.</p>")
mod_rows = []
for item in trace["tc"]:
    if item.get("module"):
        mod_rows.append((item["tc_id"], item["module"],
                         item.get("command", ""),
                         raw(f"<td class='{item['level']}'>{e(item['level'])}</td>")))
A(table(["TC", "구현 위치", "명령", "등급"], mod_rows))
A("<p class='small'>이 표는 <code>traceability.json</code>에서 생성했고 "
  "<code>python tools_traceability.py</code>가 파일·함수·명령의 실존을 매번 "
  "확인합니다.</p>")

A("<h3>3.3 core 계층</h3>")
CORE_DESC = [
    ("ui.py", "Win32 컨트롤 열거 · 물리 입력 · 화면 캡처"),
    ("uitext.py", "커스텀 렌더 컨트롤의 화면 텍스트 OCR · 문구로 항목 선택"),
    ("flows.py", "화면 전환 시나리오(로그인·Setting·검사) + 컨트롤 맵"),
    ("viewer_processing.py",
     "영상처리 파라미터 UI · OCR 판독 · 시험 파라미터 생성 · 촬영 완료 조건 대기"),
    ("viewer_tools.py", "Tool(W/L·Zoom·Pan·Annotation) 적용 검증"),
    ("image_overlay.py", "영상 위 Image Overlay 크롭·OCR·항목 판정 (WF_03 / WF_15 공용)"),
    ("print_overlay.py", "Print Overlay 설정 + 출력물·Film 창 영역별 대조"),
    ("imginfo.py",
     "제품 .img 파일 꼬리의 &lt;INFORMATION&gt; XML 판독 — 3D Recon 파라미터"
     "(XtpName/EgpName)와 촬영 모드. <b>DB에 없는 정보</b>라 XIPL_07의 주 근거"),
    ("xipl.py", "XIPL Studio 제어 (WPF UI Automation)"),
    ("send_verify.py", "DICOM Send 공용 판정 (Queue · 수신 객체 · 식별 Tag)"),
    ("dicom_settings.py", "DICOM 서버 등록·C-ECHO·Storage 설정 행 판별"),
    ("dicomlite.py", "필요한 태그만 읽는 최소 DICOM 파서"),
    ("export_manager.py", "Export Manager 제어 (별도 프로세스)"),
    ("setting_transfer.py", "Setting Export/Import 구동 (.vms 구성 검사)"),
    ("setting_values.py", "Setting 페이지의 컨트롤 값 판독 · 항목 단위 대조"),
    ("specs.py", "사양서 PDF 검색 (쪽 번호 · SRS ID 인용)"),
    ("snapshot.py", "DB 전 구간 스냅샷 · 섹션 diff"),
    ("db.py", "DB 조회 (<b>조회 전용</b> — §4 ① 참고)"),
    ("dbreset.py", "기준 스냅샷 백업/복원"),
    ("result.py", "판정 누적 · 리포트 4종 생성"),
    ("checklist.py", "체크리스트 xlsx에 결과 기록"),
    ("tc_modules.py", "TC ID → 구현 파일 지도 (리포트가 코드 위치를 보여준다)"),
    ("sysinfo.py", "PC/OS 실측 정보 · 권한 확인"),
    ("display.py", "해상도·DPI 정규화와 검사"),
    ("watchdog.py", "예상치 못한 팝업을 증거로 남기고 닫는다"),
]
A(table(["모듈", "역할"],
        [(name, raw(f"<td>{desc}</td>")) for name, desc in CORE_DESC]))

# --------------------------------------------------------------------- rules
A("<h2 id='rules'>4. 설계 원칙</h2>")
RULES = [
    ("① DB는 조회 전용 — 상태 변경은 반드시 UI로",
     "<code>core/db.py</code>에는 <code>SELECT</code>만 있고 저장소 전체에 "
     "<code>INSERT</code>/<code>UPDATE</code>/<code>DELETE</code>가 한 줄도 "
     "없습니다. DB를 직접 고치면 '제품 UI가 그 동작을 실제로 했다'는 판정 근거가 "
     "무너집니다. 시험 데이터 정리도 UI 버튼으로 합니다."),
    ("② 판정 기준은 화면이 아니라 매뉴얼·사양서에서",
     "TC를 새로 만들 때도 고도화할 때도 먼저 근거 문서를 읽습니다. 판정의 "
     "<code>note</code>에 인용한 문서와 쪽·SRS ID를 남겨 리포트만으로 기준의 출처를 "
     "감사할 수 있게 합니다."),
    ("③ 조작 전·후 모두 상태를 확인한다",
     "클릭만 보내고 결과를 확인하지 않는 코드는 단독 실행에서 통과하고 회귀에서만 "
     "깨집니다. 그런 결함 5건(메뉴 토글, 콤보 스크롤, 저장 팝업, 카드 배치, 툴바 "
     "펼침)이 모두 같은 형태였습니다. 여섯 번째는 거울상 — 조작 <i>전</i>에 화면이 "
     "존재하는지 확인하지 않은 것이었습니다."),
    ("④ 환경 오염을 제품 결함처럼 보고하지 않는다",
     "이전 실행이 남긴 데이터로 수행 불가한 경우는 <code>FAIL</code>이 아니라 무엇을 "
     "정리해야 하는지 알려주는 <code>MANUAL</code>로 분리합니다."),
    ("⑤ 고정 sleep 대신 상태 기반 대기",
     "컨트롤 출현·팝업·로그 기록·DB 행 도착·파일 생성 등 <b>실제 증거</b>가 나타날 "
     "때까지 상한을 두고 polling합니다. 모든 대기에 타임아웃이 있어 무한 대기가 "
     "없습니다. 조건 대기는 <b>부분 도착을 성공으로 보지 않습니다</b> — 3D 촬영은 "
     "Raw/Recon/Synthetic 세 건이 다 들어와야 완료로 봅니다."),
    ("⑥ 클릭 성공을 PASS로 쓰지 않는다",
     "DB / 제품 로그 / 생성 파일 / UI 재진입 / 화면 OCR 중 최소 하나로 교차 "
     "확인합니다. 로그 문구 하나로 성공을 단정하지 않습니다."),
    ("⑦ 컨트롤 ID도 그것만 믿지 않는다",
     "같은 ID가 화면마다 다른 뜻입니다. <code>501</code>/<code>500</code>은 Print "
     "범위 선택에서 <code>Selected</code>/<code>Cancel</code>인데 Film 종료 확인 "
     "대화상자에서는 <code>Yes</code>/<code>No</code>입니다. "
     "<code>uitext.pick_button</code>은 문구를 OCR로 읽어 <b>후보가 하나일 때만</b> "
     "누릅니다."),
    ("⑧ 이식 가능한 선택자만",
     "Win32 컨트롤 ID, 화면 텍스트, OCR, <b>창 기준 상대 좌표</b>를 씁니다. 저장소에 "
     "절대 데스크톱 좌표 클릭은 없습니다."),
]
for title, body in RULES:
    A(f"<h4>{e(title)}</h4><p>{body}</p>")

# ---------------------------------------------------------------------- tech
A("<h2 id='tech'>5. 기술 선택</h2>")
A("<p>외부 의존성을 <b>4개</b>로 억제했습니다 (<code>requirements.txt</code>: "
  "Pillow, pytesseract, openpyxl, pypdf). 새 QA PC에서 "
  "<code>pip install -r requirements.txt</code> 한 번으로 준비가 끝납니다.</p>")
A(table(["필요 기능", "흔한 선택", "이 프로젝트", "이유"], [
    ("Win32 UI 제어", "pywin32", "ctypes 직접 호출", "설치 부담 제거, QA PC 이식성"),
    ("SQL Server 접근", "pyodbc", "PowerShell + .NET SqlClient",
     "Windows 기본 제공, ODBC 드라이버 설치 불필요"),
    ("DICOM 파싱", "pydicom", "자체 core/dicomlite.py", "필요한 태그만 읽으면 충분"),
    ("사양서 PDF 읽기", "PyMuPDF, pdfplumber", "pypdf",
     "MIT 라이선스, 순수 Python이라 빌드 도구 불필요. PyMuPDF는 AGPL/상용 이중 "
     "라이선스라 의료기기 QA 저장소에 넣기 부담스럽습니다"),
    ("제품 .img 파싱", "(없음)", "자체 core/imginfo.py",
     "제품 고유 컨테이너입니다. 꼬리의 UTF-16LE XML만 읽으므로 700MB 파일도 "
     "seek 한 번으로 끝납니다"),
]))
A("<h3>판정에 쓰는 증거 5종</h3>")
A("""<ol>
<li><b>DB 조회</b> — 검사·영상 구조, UID 유일성, 설정 저장값</li>
<li><b>제품 로그</b> — 적용된 파라미터명·수치 (줄마다의 타임스탬프로 시점 필터링)</li>
<li><b>생성 파일</b> — 영상 <code>.img</code>의 &lt;ReconParam&gt;, Export 산출물,
해시·크기</li>
<li><b>UI 재진입</b> — 저장 후 화면을 다시 열어 표시값 재확인</li>
<li><b>화면 캡처 + OCR</b> — 커스텀 렌더링 값 판독, 증거 이미지 보존</li>
</ol>""")

# ----------------------------------------------------------------------- cmd
A("<h2 id='cmd'>6. 실행 명령 전수</h2>")
A("<p><code>run.py</code>에 <b>실제로 등록된</b> 서브명령 전부입니다 "
  "(소스에서 생성했습니다 — 없는 명령을 적지 않기 위해).</p>")
A(table(["명령", "내용"],
        [(raw(f"<td><code>python run.py {e(name)}</code></td>"), text)
         for name, text in cmd_rows]))

# ----------------------------------------------------------------------- out
A("<h2 id='out'>7. 결과물과 리포트 구성</h2>")
A("<h3>HTML 리포트에 들어가는 것</h3>")
A("""<ul>
<li><b>요약 대시보드</b> — TC/검증 항목 집계 타일, PASS/FAIL/MANUAL/SKIP 비율 막대,
실행 구간과 총 소요 시간</li>
<li><b>실행 환경 및 버전</b> — 수행 일시·호스트·실행 계정·PC 제조사/모델·CPU·메모리·
GPU·BIOS·OS Caption/Version/Build/Arch·OS 설치일·최근 부팅·Python·해상도/DPI·
관리자 권한·Viewer 파일 버전·Tesseract 버전·data_dir·SQL Server·기준 체크리스트 경로.
존재하는 경로는 클릭하면 열립니다</li>
<li><b>자동화 커버리지 총괄</b> — 기준 체크리스트 TC 전부를 분류해, 자동화하지 못한
것의 <b>정확한 지점과 해제 조건</b>을 함께 싣습니다. 사유는 리포트가 만들지 않고
<code>automation_scope.json</code>의 <code>coverage</code>에서 읽습니다 — 근거 없는
설명을 생성하지 않기 위해서입니다</li>
<li><b>실패 항목 원인</b> — 앞선 FAIL부터 읽도록 위에 모아 둡니다</li>
<li><b>수동 확인 / 미수행 사유와 해제 조건</b> — MANUAL/SKIP을 TC 단위 한 행으로
묶어 '무엇이 있으면 자동 판정할 수 있는가'를 적습니다</li>
<li>TC별로 <b>기준 문서 원문</b>(Precondition / Step Description / Expected Result /
Test Data), 자동화 범위 사유, <b>자동화 코드 위치</b>, 시작·종료 시각과 소요 시간,
단계별 기대값/실제값/판정 근거, 증거 파일 링크, <b>소요 시간 분해</b></li>
</ul>""")
A("<p>단계별 판정 표는 <code>table-layout:fixed</code> + <code>colgroup</code>으로 "
  "<b>기대값과 실제값을 정확히 같은 폭</b>(각 27%)으로 고정했습니다. 브라우저가 내용 "
  "길이로 폭을 재조정하면 긴 <code>actual</code>이 기대값 열을 잡아먹어 두 값을 "
  "나란히 대조할 수 없기 때문입니다.</p>")
A("<p><code>python tools_report_numbers.py</code>는 문서에 적을 수치(코드 규모, "
  "자동화 등급 건수, 커버리지 분류, TC/검증 판정, 소요 시간, FAIL 목록)를 리포트 "
  "JSON과 저장소에서 <b>다시 계산</b>해 출력합니다. 손으로 옮겨 적은 숫자가 낡는 "
  "것을 막는 도구입니다.</p>")

# --------------------------------------------------------------------- addtc
A("<h2 id='addtc'>8. TC를 새로 추가하는 절차</h2>")
A("""<ol>
<li><b>기준 문서에서 원문을 읽습니다.</b> 개정본 <code>개정 TC</code> 시트에서 그 TC
행의 Precondition / Step Description / Expected Result / Test Data를 그대로
확인합니다. <b>TC ID만 보고 Step을 추측하면 안 됩니다.</b></li>
<li><b>매뉴얼·사양서에서 기대 동작의 근거를 찾습니다.</b>
<code>core/specs.py</code>로 사양서를 검색하면 쪽 번호와 SRS ID가 함께 나옵니다.</li>
<li><b><code>tests/workflowNN.py</code></b>(또는 계열 모듈)를 만듭니다. 최상단
docstring에 체크리스트 원문을 변경 없이 옮기고, 판정 근거와 실측한 컨트롤 ID를 함께
적습니다.</li>
<li><b><code>run(ctx) -&gt; TCResult</code></b>를 구현합니다. Expected 한 줄이 하나의
Check입니다.
<pre><code>r = TCResult("TC_...", "제목")
r.assert_equal(3, "확인 항목", expected, actual,
               note="근거: 사양서1 186쪽 SRS 03-10-110 — \\"...\\"")
r.attach(screenshot_path)          # 증거
r.skip(1, "항목", "이 환경에는 확인 대상이 없다 + 그 근거")
r.manual(5, "항목", "사유 + 해제 조건 + 이 실행으로 말할 수 없는 것")</code></pre></li>
<li><b><code>core/tc_modules.py</code></b>에 TC ID → 파일 목록을 등록합니다.</li>
<li><b><code>automation_scope.json</code></b>에 등급과 사유, 그리고
<code>coverage.gap</code> / <code>coverage.unblock</code>을 적습니다. 등급은
<b>실측으로 확인된 뒤에만</b> 올립니다.</li>
<li><b><code>traceability.json</code></b>에 인용(문서·쪽·SRS·문구·해당 Step)을
추가합니다. 쪽·SRS는 손으로 적지 않고 <code>core/specs.py</code>로 찾은 값을 씁니다.</li>
<li><b><code>run.py</code></b>에 <code>run-*</code> 서브명령을 추가하고, 회귀에 포함할
것이면 <b>회귀 블록 안에서</b> import합니다. 다른 분기의 import는
<code>UnboundLocalError</code>를 만듭니다(실제로 회귀가 41분 뒤 죽었습니다).
UI를 조작하는 명령이면 <code>ui_commands</code> 집합에도 넣어 권한·해상도 게이트를
받게 합니다.</li>
<li><b>사전 검사를 돌립니다</b> (§1.7).</li>
<li><b>회귀 시작 상태에서 검증합니다.</b>
<code>python run.py reset-environment</code> → 그 명령.</li>
<li><b>문서를 갱신합니다</b> — <code>auto/README.md</code>, 이 문서,
<code>auto/NEXT_TASK.md</code>, <code>지식\\[자동화 구현 현황]…md</code>.</li>
</ol>""")

# --------------------------------------------------------------------- trace
A("<h2 id='trace'>9. 추적성 (사양 ↔ TC)</h2>")
A("<p>사양→TC와 TC→사양을 <code>auto/traceability.json</code> 하나에 두고, "
  "<code>python tools_traceability.py --reverse</code>가 <b>매번 원문과 대조</b>한 뒤 "
  "양방향 인덱스를 출력합니다. 표를 문서에 손으로 적으면 사양서가 개정될 때 "
  "문서만 낡아 '근거가 있다'고 거짓말합니다.</p>")
A("<h4>검사하는 것</h4>")
A("""<ol>
<li><code>tc_id</code>가 기준 체크리스트에 실제로 있는가 / 빠진 TC가 없는가</li>
<li><code>level</code>이 <code>automation_scope.json</code>과 일치하는가</li>
<li><code>module</code>의 파일과 함수가 실제로 있는가</li>
<li><code>command</code>가 <code>run.py</code>의 서브명령에 있는가</li>
<li>인용한 문구가 그 문서 원문에 <b>실제로 있는가</b>(공백 무시 비교)</li>
<li>사양서 인용의 쪽 번호·SRS ID가 실측값과 같은가</li>
<li><code>steps</code> 번호가 체크리스트 Step Description 범위 안인가</li>
</ol>""")
A("<p class='small'>위조한 쪽 번호·SRS·없는 인용·범위 밖 Step·없는 함수·없는 명령·"
  "등급 불일치 7건을 주입해 <b>전부 검출되는 것을 확인</b>했습니다(2026-08-24).</p>")
covered = [x for x in trace["tc"] if x.get("requirements")]
A(f"<p>현재 상태: TC {len(trace['tc'])}건 중 <b>{len(covered)}건</b>에 인용이 있고 "
  f"총 <b>{sum(len(x['requirements']) for x in trace['tc'])}건</b>의 요구사항이 "
  f"연결돼 있습니다. 나머지는 <code>pending_reason</code>에 <b>왜 미확정인지</b>를 "
  f"적어 두었습니다 — 없는 근거를 만들지 않기 위해서입니다.</p>")
rev = {}
for item in trace["tc"]:
    for req in item.get("requirements", []):
        key = req["doc"] + ((" " + req["srs"]) if req.get("srs") else "")
        rev.setdefault(key, set()).add(item["tc_id"])
A(table(["사양 / 문서", "검증하는 TC"],
        [(key, ", ".join(sorted(tcs))) for key, tcs in sorted(rev.items())]))

# --------------------------------------------------------------------- scope
A("<h2 id='scope'>10. 자동화 범위 전수</h2>")
A(f"<p>개정본 체크리스트 <b>{len(checklist_tc)}개 TC</b>를 전수 등록했습니다 — "
  f"완전자동 <b>{levels.get('FULL',0)}</b> / 부분자동 "
  f"<b>{levels.get('PARTIAL',0)}</b> / 수동 <b>{levels.get('MANUAL',0)}</b> "
  f"(+ 자동화 보조 {levels.get('SUPPORT',0)}, 그중 3D 촬영 2건은 회귀 제외). "
  f"<code>python run.py list</code>로 확인합니다.</p>")
rows = []
for item in scope:
    cov = item.get("coverage") or {}
    rows.append((
        item["tc_id"],
        item.get("title", ""),
        raw(f"<td class='n {item['level']}'>{e(item['level'])}</td>"),
        cov.get("category", ""),
        cov.get("gap", "") or "—",
        cov.get("unblock", "") or "—",
    ))
A(table(["TC", "Title", "등급", "커버리지 분류", "못 한 지점", "해제 조건"], rows))

# ----------------------------------------------------------------------- reg
A("<h2 id='reg'>11. 회귀 실적</h2>")
A(f"<p><b>최신 전체 회귀 (2026-08-21 16:40, 실측)</b> — "
  f"TC {len(reg)}건: PASS {reg_tc.get('PASS',0)} / FAIL {reg_tc.get('FAIL',0)} / "
  f"MANUAL {reg_tc.get('MANUAL',0)} / SKIP {reg_tc.get('SKIP',0)}, "
  f"그 안의 검증 {sum(reg_check.values())}개: PASS {reg_check.get('PASS',0)} / "
  f"FAIL {reg_check.get('FAIL',0)} / MANUAL {reg_check.get('MANUAL',0)} / "
  f"SKIP {reg_check.get('SKIP',0)}, {reg_minutes:.1f}분. "
  f"근거 파일 <code>{e(REG_REPORT)}</code>.</p>")
A("<p>남은 FAIL: " + ", ".join(
    f"<code>{e(tc)}</code> Step {e(step)} — {e(title)}"
    for tc, step, title in reg_fails) + " (제품 결함. 의도적으로 완화하지 "
  "않습니다).</p>")
A("<div class='note warn'><b>두 층을 구분해 읽습니다.</b> "
  "<code>TC 판정</code>은 TC 하나의 종합 결과이고 <code>검증 판정</code>은 그 안의 "
  "Step 단위 결과입니다. <b>검증 수가 급감한 회차는 그 자체가 연쇄 실패의 "
  "신호입니다</b> — 앞선 TC가 실패하면 뒤 TC가 전제 미충족으로 조기 중단되어 수행되는 "
  "체크 자체가 줄어듭니다(7차 45개, 13·14차 49개).</div>")
A(table(["회차", "일시", "TC", "TC 판정 (P/F/M)", "검증 수",
         "검증 판정 (P/F/M/S)", "비고"], [
    ("6차", "08-18 12:10", 15, "9 / 1 / 5", 129, "121 / 1 / 6 / 1",
     "FAIL 1 = 제품 결함"),
    ("7차", "08-18 16:56", 17, "3 / 10 / 4", 45, "30 / 10 / 5 / 0",
     "연쇄 실패 — 원인 1개"),
    ("8차", "08-18 17:52", 17, "9 / 4 / 4", 135, "121 / 5 / 8 / 1",
     "기동·서비스 수정"),
    ("10차", "08-19 09:55", 17, "8 / 2 / 7", 136, "124 / 2 / 9 / 1",
     "Send·화면 이동 수정"),
    ("11차", "08-19 11:26", 17, "9 / 2 / 6", 136, "124 / 2 / 9 / 1",
     "개정본 기준 TC 번호 전면 재정렬"),
    ("12차", "08-19 13:50", 18, "11 / 1 / 6", 152, "140 / 1 / 10 / 1",
     "저장 확인 팝업 처리, WF_06 신규"),
    ("13·14차", "08-19 14:39·14:59", 20, "3 / 13 / 4", 49, "30 / 14 / 5 / 0",
     "내가 넣은 로그인 가드가 정상 실행을 막음"),
    ("15차", "08-19 16:00", 20, "13 / 1 / 6", 172, "160 / 1 / 10 / 1",
     "가드 재설계, WF_05·WF_09 신규"),
    ("16차", "08-19 20:18", 21, "13 / 2 / 6", 176, "163 / 2 / 10 / 1",
     "파일명↔TC 맵핑, WF_13 신규. FAIL 2 = 제품 결함 1 + 내가 넣은 버그 1"),
    ("17차", "08-20 16:12", 26, "16 / 1 / 9", 233, "215 / 1 / 16 / 1",
     "WF_07/10/11/12/15 신규, 회귀를 개정본 행 순서로 재배열. 80.1분"),
    ("18차", "08-21 13:04", 28, "17 / 4 / 7", 254, "232 / 5 / 16 / 1",
     "WF_14/WF_16 신규. 94.2분. FAIL 4 중 3건은 Storage 활성 행 중복(자동화 결함)"),
    ("19차", "08-21 16:40", 26, "20 / 1 / 5", 251, "241 / 1 / 7 / 2",
     "Storage 설정 행/작업 사본 구분 수정, WF_03 Overlay 자동화, "
     "WF_16 전체 수동 전환. 111.3분"),
]))
A("<div class='note bad'><b>2026-08-24 회차는 실행하지 못했습니다.</b> 이 세션의 "
  "Python 프로세스가 관리자 권한(High Integrity)이 아니어서 "
  "<code>run.py</code>의 환경 게이트가 UI 자동화를 시작 시점에 차단합니다"
  "(<code>python run.py portability-check</code> 실측: 관리자 권한 <b>False</b>, "
  "나머지 해상도·DPI·필수 경로는 PASS). "
  "그래서 이 회차의 변경은 정적 검사·단위 시험·DB/파일 기반 검증까지만 확인했습니다. "
  "권한을 갖춘 세션에서 <code>python run.py run-regression</code>을 돌려야 "
  "합니다.</div>")

# ------------------------------------------------------------------- trouble
A("<h2 id='trouble'>12. 문제 해결</h2>")
A(table(["증상", "먼저 볼 것"], [
    (raw("<td><b>클릭이 조용히 안 먹는다</b>(캡처는 되는데 창이 반응 없음)</td>"),
     raw("<td><b>관리자 권한.</b> <code>sysinfo.is_elevated()</code>가 "
         "<code>False</code>면 Windows UIPI가 입력을 막고 있습니다. 코드보다 권한을 "
         "먼저 확인하십시오</td>")),
    ("좌표가 어긋난다",
     raw("<td><code>python run.py portability-check</code> — 1920×1080 @ 100%"
         "(96 DPI)가 아니면 시작 시점에 FAIL시킵니다</td>")),
    ("OCR이 '못 읽는다'",
     raw("<td><b>캡처 이미지를 먼저 보십시오.</b> 타이밍·경합을 의심하기 전에. "
         "<code>Evidence/</code>에 크롭 원본이 남습니다. 과거 두 번 모두 원인은 "
         "타이밍이 아니라 전처리(psm 선택, 명암 방향)였습니다</td>")),
    ("회귀가 첫 단계에서 무너진다",
     raw("<td>제품 서비스가 내려가 있을 수 있습니다. "
         "<code>AUTOMATION_ENVIRONMENT_RESET</code> 판정의 <code>services</code> "
         "값을 보십시오</td>")),
    ("앞선 TC 실패 뒤 FAIL이 줄줄이",
     raw("<td><b>가장 앞선 FAIL부터</b> 읽으십시오. 리포트가 위에 모아 둡니다. "
         "'전제 미충족' 문구가 보이면 제품 판정이 아닙니다</td>")),
    ("'수신 객체가 정확히 N건'이 틀린다",
     raw("<td>활성 Storage SCP가 둘 이상일 수 있습니다. 리포트의 "
         "<code>[전제] 활성 Storage SCP가 하나</code> 판정을 보고, "
         "<code>reset-environment</code> 후 <code>setup-dicom</code>을 1회만 "
         "실행하십시오</td>")),
    ("시험 Preset·Hospital Code가 남아 반복 실행이 막힌다",
     raw("<td><code>python run.py reset-environment</code>로 DB를 기준 스냅샷으로 "
         "되돌립니다</td>")),
    (raw("<td><code>UnboundLocalError: ... run_xxx</code></td>"),
     raw("<td>같은 이름의 import가 다른 분기에 있습니다. "
         "<code>python tools_check_regression_names.py</code></td>")),
    (raw("<td><code>'list' object is not callable</code></td>"),
     raw("<td>모듈 함수가 같은 이름의 값으로 덮어써졌습니다. "
         "<code>python tools_check_module_attrs.py</code></td>")),
    ("추적성 위반이 보고된다",
     raw("<td><code>python tools_traceability.py</code>의 위반 목록을 보십시오. "
         "쪽·SRS는 손으로 고치지 말고 <code>core/specs.py</code>로 다시 찾은 값을 "
         "넣습니다</td>")),
    ("수동 WF_16 뒤 Kiosk가 켜진 채로 남았다",
     raw("<td>Viewer &gt; Setting &gt; System &gt; Security에서 KIOSK mode를 "
         "Not use로 바꾸고 Update합니다. 자동화는 Kiosk 설정을 조작하지 "
         "않습니다</td>")),
]))

# --------------------------------------------------------------------- limit
A("<h2 id='limit'>13. 제한사항</h2>")
A("""<ul>
<li><b>환경 고정</b> — Primary 1920×1080 @ 100%(96 DPI), 관리자 권한, Windows.
다른 해상도·배율은 시작 시점에 거부합니다(조용히 오작동하지 않기 위해).</li>
<li><b>Demo(F8) 가상 촬영 환경</b> — 실제 X-ray가 아니므로 <b>RDSR(Dose SR)이
생성되지 않습니다</b>. <code>WF_06</code> Step 3~5, <code>WF_07</code> Step 6,
<code>WF_15</code> Step 6은 전제 미충족으로 MANUAL이고 <b>제품 결함으로 보고하지
않습니다</b>.</li>
<li><b>GPU 미탑재</b> — <code>XIPL_03</code> Step 10은 Viewer가 <code>No GPUS</code>를
반환해 SKIP됩니다. GPU와 무관하게 성립해야 하는 판정(Apply 후 파라미터 유지)은
면제하지 않습니다.</li>
<li><b>실물 장비 없음</b> — Detector/Gantry, ACR Phantom, VIVIX-M Setup,
Bellalun System Setup이 없어 <code>Install_03~06</code>, <code>QC_01/02</code>는
수동입니다.</li>
<li><b>판정 기준이 문서에 없는 것</b> — <code>Performance_01~03</code>은 체크리스트
Test Data가 "허용 기준: 추가 사양 확인 필요"라고 명시합니다. 기준 없이 측정값만 찍어
PASS라고 쓰지 않습니다.</li>
<li><b>파괴적 동작 제외</b> — 설치/Upgrade/Uninstall 실행, 시스템 재시작, PC 종료는
자동화하지 않습니다(자동화 세션이 함께 죽고 무인 회귀가 중단됩니다).</li>
<li><b>Overlay 표시 판정은 '값'이 아니라 '항목'</b> — Demo 촬영에서는 선량 값이
<code>-- kVp</code>로 찍힙니다. 개정본 Expected가 요구하는 것도 "설정한 Image Overlay
<b>항목</b>이 표시된다"입니다.</li>
<li><b>3D Preset 목록 컨트롤 미실측</b> — <code>Setting &gt; Procedure &gt; Preset</code>의
3D-N/3D-W 목록·추가·삭제 컨트롤 ID가 아직 실측되지 않았습니다(2D만
<code>2554</code>/<code>2548</code>/<code>2549</code> 확정). 그래서
<code>XIPL_07</code>은 3D Preset 행을 만들거나 편집하지 않고
<code>Procedure &gt; General</code>의 모드별 Default만 조작합니다. 번호가 이어질
것이라 추측하지 않습니다. <code>python run.py probe-preset3d</code>(조회 전용)로
실측하면 해제됩니다.</li>
<li><b><code>core/db.py</code>는 조회 전용</b> — 정리용으로도 DB 쓰기를 열지
않습니다.</li>
<li><b>마우스·키보드를 점유합니다</b> — 실행 중에는 PC를 쓰지 마십시오. 물리 입력을
제어하기 때문에 사람이 끼어들면 판정이 틀립니다.</li>
</ul>""")

# -------------------------------------------------------------------- lesson
A("<h2 id='lesson'>14. 실제로 잡아낸 결함과 교훈</h2>")
A("<h3>제품 결함 (현재도 FAIL로 보고 중)</h3>")
A("<p><code>TC_XIPL_compatibility_03</code> Step 9 — <b>3D Post Reconstruction의 "
  "Apply 후 재진입하면 값이 기본값으로 되돌아갑니다</b>(<code>Not use</code>→"
  "<code>Use</code>, 14→10). GPU 유무와 무관하며, 사양서1 277쪽 SRS 03-50-230이 "
  "\"Apply를 누르게 되면 해당 img 파일에 영상 조정 파라미터 값들이 저장된다\"고 "
  "정하고 있어 <b>의도적으로 완화하지 않습니다</b>.</p>")

A("<h3>기준 문서를 잘못 골라 정상 구현을 결함으로 판정한 일</h3>")
A("<p>파일명이 비슷한 다른 체크리스트(<code>지식\\(TC) R-23-2346…</code>)를 기준으로 "
  "착각해 정상 구현된 <code>WF_02</code>를 '범위 불일치'로 강등했습니다. 같은 형태의 "
  "TC ID에 다른 내용이 붙어 있었습니다. 확인해 보니 어긋난 것은 하나가 아니라 "
  "10개였습니다. <b>그래서 기준 문서를 <code>AGENTS.md</code> 0절에 못박고</b>, "
  "혼동 주의 문구를 함께 적었습니다.</p>")

A("<h3>저장 시점을 가정해 사용자 DB를 오염시킨 일</h3>")
A("<p><code>Setting &gt; Procedure &gt; Hospital Code</code>의 <code>+</code>는 "
  "<b>Update를 누르지 않아도 즉시 DB에 행을 만듭니다.</b> 프로브 주석에는 \"Update를 "
  "누르지 않으므로 DB에는 아무 변화가 없다\"고 적어 두었는데 <b>확인하지 않고 단정한 "
  "것</b>이었습니다. 프로브를 다섯 번 돌려 사용자 DB에 5행을 남겼습니다. Print "
  "Overlay는 Update까지 눌러야 저장되고 이 화면은 즉시 저장됩니다 — <b>화면마다 "
  "다릅니다.</b> 이제 조회 전용이라고 생각한 프로브도 앞뒤로 DB를 찍어 대조합니다"
  "(<code>run.py probe-preset3d</code>가 그 형식입니다).</p>")

A("<h3>미표시를 제품 문제로 의심하다 설정에서 원인을 찾은 일</h3>")
A("<p>Print Overlay Header에 항목을 넣었는데 필름에 나오지 않았습니다. 원인은 같은 "
  "화면 우측 <code>Header Layout</code>의 표시 위치가 <b>None</b>이었고(그래서 Layout "
  "콤보도 회색 비활성), 사양서1 297쪽이 \"None으로 설정한 경우 표시되지 않는다\"고 "
  "이미 적어 둔 동작이었습니다. <b>설정 화면을 캡처해 눈으로 본 것</b>이 원인을 "
  "찾아냈습니다.</p>")

A("<h3>화면 콤보의 순서와 DB 값이 일치한다고 가정한 일</h3>")
A("<p>Header 표시 위치 콤보에서 두 번째 항목을 골랐더니 <code>HeaderPosition</code>이 "
  "Top(1)이 아니라 Bottom(2)이 됐습니다. 이제 순서로 고르지 않고 <b>항목 문구를 "
  "OCR로 읽어</b> 고르고, 저장 후 DB 값으로 확인합니다.</p>")

A("<h3>세 번 만에 잡은 것 — 회귀에서만 실패하던 TC</h3>")
A("<p><code>TC_XIPL_compatibility_04</code>가 회귀 8·10·11차에서 3회 연속 같은 "
  "지점에서 실패했습니다. 원인은 <b>저장 확인 팝업</b>이었습니다 — "
  "<code>There are changes. Do you like to save them?</code>에 아무도 답하지 않아 "
  "모달이 이후 모든 클릭을 삼켰습니다. 회귀에서만 터진 이유는 직전 "
  "<code>XIPL_03</code>이 파라미터를 변경해 '변경사항'이 생기기 때문입니다. "
  "두 번 잘못 짚은 뒤(대기 부족 → 상한 상향, 검사 열림 → 복구 분기 추가) "
  "<b>세 번째 추측 대신 실패 시점의 화면 랜드마크·대화상자 문구를 증거로 남기게 "
  "했고</b> 그것이 팝업을 드러냈습니다.</p>")

A("<h3>자동 치환이 모듈 함수를 리스트로 덮어쓴 일 (회귀 16차)</h3>")
A("""<pre><code>received = _received(ctx) or []        # 원본 — 지역 변수
sv.received = sv.received(ctx) or []   # 치환 결과 — 모듈 함수를 리스트로 덮어씀</code></pre>""")
A("<p><code>WF_05</code>가 먼저 실행되며 <code>send_verify.received</code>를 리스트로 "
  "덮어쓰고, 뒤이은 <code>WF_06</code>이 그 오염된 모듈을 물려받아 죽었습니다. "
  "<code>py_compile</code>과 <code>ast</code> 미정의 이름 검사 모두 통과했습니다 — "
  "둘 다 \"존재하는 이름에 대입하는 것\"은 잡지 못합니다. 그래서 "
  "<code>tools_check_module_attrs.py</code>를 만들었습니다.</p>")
A("<p><b>고친 뒤의 검증도 한 번 잘못했습니다.</b> 두 TC를 따로 돌려 '고쳤다'고 볼 "
  "뻔했는데 <b>별도 프로세스</b>라 모듈 오염 경로를 아예 지나가지 않습니다. 회귀와 "
  "같은 조건은 <b>한 프로세스에서 이어 돌리는 것</b>입니다.</p>")

A("<h3>다른 분기의 import가 회귀를 41분 뒤에 죽인 일</h3>")
A("<p>회귀에 TC를 추가하면서 <code>import</code>가 회귀 블록이 아니라 다른 분기에 "
  "들어갔습니다. 함수 어딘가에 그 이름의 import가 있으면 정적 검사에는 '정의됨'으로 "
  "보이지만 실제로는 그 분기에서 unbound입니다. 회귀가 <b>41분을 돌고 나서</b> "
  "<code>UnboundLocalError</code>로 죽었습니다. 그래서 "
  "<code>tools_check_regression_names.py</code>를 만들어 <b>긴 실행 전에 반드시</b> "
  "돌립니다.</p>")

A("<h3>예외처리를 넣다가 정상 실행을 막은 일 (회귀 2회 붕괴)</h3>")
A("<p>13·14차의 급락(TC 20건 중 FAIL 13)은 제가 넣은 로그인 가드 때문이었습니다. "
  "<b>재현할 수 없는 상황에 '중단' 로직을 넣은 것</b>이 원인이었습니다. 이후 규칙: "
  "방어 코드를 넣으면 <b>그 조건을 직접 만들어 켜고 끈 비교</b>를 하고, 없어도 정상 "
  "동작하면 제거합니다.</p>")

A("<h3>첫 진단이 틀렸고 측정이 그것을 잡아낸 일 (2026-08-21)</h3>")
A("<p>\"Storage 활성 행이 Send 때마다 늘어난다\"를 제품/자동화 결함으로 의심했는데, "
  "실제로는 <b>판정 쿼리의 결함</b>이었습니다. <code>DICOM_STORAGE</code>는 설정 행과 "
  "<b>전송 작업 사본 행</b>을 함께 담고 <code>SCPUseType</code>으로 구분합니다"
  "(<code>0</code>=설정). 사본도 <code>Use=1</code>이라 "
  "<code>WHERE [Use]=1</code>만으로 '활성 SCP가 하나'를 판정하면 Send 한 번마다 "
  "오판정합니다. 쿼리를 <code>SCPUseType=0</code>으로 좁혀 해결했습니다.</p>")

A("<h3>선행 도구의 오탐을 원인 쪽에서 없앤 것 (WF_14)</h3>")
A("<p>사내에 같은 목적의 선행 도구(Setting 화면 캡처-비교)가 있었고, 그 문서의 회고가 "
  "스스로 두 가지 오탐을 적어 두었습니다 — \"텍스트 커서가 캡처되면 같은 값인데 "
  "Fail\", \"Setting 창 로딩이 늦어진 Fail\". 둘 다 <b>픽셀을 값의 대리물로 쓴 데서</b> "
  "나옵니다. 그래서 <code>WF_14</code>는 주 판정을 <b>DB 설정 테이블 전수 대조</b>로 "
  "하고, 화면 값은 <code>core/setting_values.py</code>가 <b>컨트롤 ID 기준으로 값을 "
  "직접 읽어</b> 보조 판정합니다. 커서도 로딩도 판정에 섞이지 않습니다.</p>")

A("<h3>단위 시험이 실패한 채 방치돼 있던 것 (2026-08-24)</h3>")
A("<p>저장소의 유일한 단위 시험이 HTML 리포트에서 <code>소요시간</code>(붙여쓰기)을 "
  "찾고 있었는데 리포트는 그 전부터 <code>소요 시간 분해</code>(띄어쓰기)를 쓰고 "
  "있었습니다. <b>아무도 돌리지 않아 실패 상태로 남아 있었습니다.</b> 문구를 그대로 "
  "박는 대신 HTML이 실제로 내는 제목을 확인하도록 고치고, 사전 검사 목록에 "
  "<code>python -m unittest discover</code>를 넣었습니다.</p>")

A("<h3>죽은 코드가 조건 대기를 되돌릴 수 있던 것 (2026-08-24)</h3>")
A("<p><code>viewer_processing.preview_and_apply</code>는 Preview/Apply 뒤에 "
  "<b>무조건 자는</b> 함수였습니다(2D 20/30초, 3D 35/75초). 호출부는 이미 전부 조건 "
  "기반 대기로 옮겨 갔고 저장소·문서·설정 어디에서도 참조되지 않았습니다. "
  "<b>죽은 코드라서만이 아니라</b>, 남겨 두면 다음 사람이 '이미 있는 헬퍼'로 다시 써서 "
  "조건 대기가 조용히 되돌아가기 때문에 지웠습니다. 같은 이유로 "
  "<code>config.example.json</code>의 <code>preview_3d_wait</code>/"
  "<code>apply_3d_wait</code>도 코드가 실제로 읽는 <code>*_timeout</code> 키로 "
  "고쳤습니다 — 그 두 키는 아무도 읽지 않아 <b>조정해도 아무 일이 없었습니다</b>.</p>")

# ---------------------------------------------------------------------- docs
A("<h2 id='docs'>15. 참고 문서</h2>")
A(table(["문서", "무엇"], [
    ("auto/README.md", "저장소 개요·포트폴리오 요약 (이 문서의 상위)"),
    ("auto/AGENTS.md", "저장소 작업 규칙 (기준 문서, 작업 순서, 검증, Git 규약)"),
    ("auto/NEXT_TASK.md", "누적 인수인계 기록 (실측 컨트롤·제품 동작·판정 기준)"),
    ("auto/NEXT_WORK.md", "현재 상태와 다음 작업 (P0/P1/P2 + 다음 세션용 프롬프트)"),
    ("auto/automation_scope.json", "TC별 자동화 등급·사유·커버리지 분류·해제 조건"),
    ("auto/traceability.json", "사양↔TC 추적성 데이터 (tools_traceability.py가 검사)"),
    ("auto/PORTABILITY_AUDIT.md", "다른 QA PC 이식 점검 기록"),
    ("지식/[자동화 운영 지침] …md", "영구 구현 규칙"),
    ("지식/[자동화 구현 현황] …md", "TC별 구현 수준과 연결 상태"),
    ("지식/[QA 작성 규칙] …md", "TC 설계·자동화·자체검토 가이드"),
]))

A("<hr><p class='small'>이 문서는 "
  "<code>automation_scope.json</code> · <code>traceability.json</code> · "
  "<code>run.py</code> · 리포트 JSON에서 표를 생성해 만들었습니다. "
  "저장소를 바꾸면 다시 생성해 수치가 낡지 않게 하십시오.</p>")
A("</div></body></html>")

with io.open(OUT, "w", encoding="utf-8", newline="\n") as stream:
    stream.write("\n".join(P))
print("wrote %s (%.1f KB)" % (OUT, os.path.getsize(OUT) / 1024))
