"""Bellalun·VXvue 공통 오프라인 보고서 표시 계약 v1. 제품 판정은 호출자가 제공한다."""
from html import escape
from collections.abc import Mapping

LAYOUT_VERSION = 1
STYLE = r"""
:root{--fg:#182638;--mut:#66778a;--line:#dce4ec;--head:#f3f6fa;--card:#f8fafc}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:80px}
body{font-family:'Malgun Gothic','Segoe UI',sans-serif;margin:0;color:var(--fg);background:#f1f5f9;line-height:1.6}
.wrap{max-width:1280px;margin:auto;padding:36px 32px 70px}
h1{font-size:29px;line-height:1.35;margin:6px 0 16px;letter-spacing:-.8px}
h2{font-size:21px;margin:0 0 18px;letter-spacing:-.4px}h3{font-size:15px;margin:24px 0 10px}
p{margin:8px 0}.eyebrow{font-size:11px;letter-spacing:2px;color:#527087;font-weight:700}
.meta,.k{font-size:12px;color:var(--mut);overflow-wrap:anywhere}.note{white-space:pre-wrap;overflow-wrap:anywhere}
a{color:#186b96;text-decoration:none}a:hover{text-decoration:underline}code{font:12px Consolas,monospace;overflow-wrap:anywhere}
header{padding-bottom:20px}.hero{display:flex;align-items:center;gap:24px;justify-content:space-between}
.hero-status{border-left:4px solid #c83d43;padding:12px 20px;background:#fff;min-width:170px;border-radius:0 10px 10px 0}
.hero-status.PASS{border-color:#208661}.hero-status.MANUAL{border-color:#a7771d}.hero-status.BLOCKED{border-color:#7952a2}.hero-status.SKIP{border-color:#7c8794}
.hero-status strong{font-size:22px}.hero-status span{display:block;font-size:12px;color:var(--mut)}
nav{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 22px}nav a{background:#fff;border:1px solid var(--line);padding:6px 14px;border-radius:20px;font-size:12px}
section,.tc-detail,.appendix{background:#fff;border:1px solid var(--line);border-radius:14px;padding:24px;margin-bottom:20px}
.metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.metric{padding:15px;border-right:1px solid var(--line)}.metric:last-child{border:0}
.metric .n{font-size:29px;font-weight:700;line-height:1.2}.metric .label{font-size:11px;color:var(--mut);margin-top:5px}
.PASS{color:#167451}.FAIL{color:#a41926}.MANUAL{color:#976a15}.SKIP{color:#334e68}.BLOCKED{color:#71419b}
.bar{display:flex;height:8px;overflow:hidden;border-radius:8px;background:#edf1f5;margin:18px 0 12px}.bar span{display:block}
.bPASS{background:#249576}.bFAIL{background:#a41926}.bMANUAL{background:#d1a446}.bSKIP{background:#334e68}.bBLOCKED{background:#8f67b3}
.run-facts{margin-top:8px;display:flex;flex-wrap:wrap;gap:10px 24px;font-size:12px;color:var(--mut)}
.failure-panel{border:3px solid #a41926;background:#fff4f5;box-shadow:0 3px 15px #bd303c0c}
.manual-panel{border:3px solid #976a15;background:#fffaf0}.manual-panel h2{color:#7a5410;font-size:22px}.manual-panel .failure-card{border-top-color:#ecdcb8}.manual-panel .comparison .actual{border-left-color:#d1a446}
#skipped{border-left:5px solid #334e68}#skipped h2{color:#334e68}.sum .SKIP-row{background:#f0f5fa}
.failure-panel h2{color:#aa2433;font-size:24px}.failure-card{padding:18px 0;border-top:1px solid #edcbd1}.failure-card:first-of-type{border:0;padding-top:0}
.failure-heading{font-size:16px;font-weight:700;margin:0 0 12px}.comparison{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.comparison>div{background:#fff;border:1px solid #ecd7dc;border-radius:10px;padding:14px}.comparison h3{font-size:11px;color:var(--mut);margin:0 0 8px}
.comparison .actual{border-left:4px solid #d6505b}.cause{margin-top:12px;font-size:13px}.cause b{margin-right:8px}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:12.5px;line-height:1.55}th,td{padding:11px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
.step-card{margin:6px 0}.step-card h4{margin:6px 0 4px}.step-card p{margin:2px 0}.step-card.FAIL-row{background:#fff5f6}.pass-steps>summary,details.more>summary{cursor:pointer;font-weight:700;color:#4a6278;margin:8px 0}.detail-group{margin-top:28px}
.source-actual table{min-width:640px;table-layout:fixed}.source-actual pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.source-actual article{border-bottom:1px solid var(--line);padding-bottom:10px}
th{background:var(--head);font-size:11px;color:#52677c;font-weight:700}.sum{min-width:780px}.sum td:nth-child(1){width:170px}.sum td:nth-child(2){width:32%}
#skipped td:first-child,#skipped th:first-child{width:80px;white-space:nowrap}.sum .FAIL-row{background:#fff3f4}.sum tr:hover{background:#f3f8fc}.sum td.s{font-weight:700;white-space:nowrap}.step-counts{font-size:11px;color:var(--mut);white-space:nowrap}
.tools{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:0 0 14px;font-size:12px}.tools label{display:flex;gap:8px;align-items:center}
input,select,button{font:inherit;border:1px solid #cdd8e3;border-radius:7px;padding:8px 10px;background:#fff;color:var(--fg)}input{width:240px}button{cursor:pointer}button:hover{background:#f2f6fa}
:focus-visible{outline:3px solid #79bde1;outline-offset:2px}[hidden]{display:none!important}
.tc-detail{padding:0;scroll-margin-top:20px;overflow:hidden}.tc-detail>summary{display:flex;align-items:center;gap:12px;padding:18px 22px;cursor:pointer;font-size:14px;font-weight:700;list-style:none}
.tc-detail>summary:before{content:'+';font-size:19px;color:var(--mut)}.tc-detail[open]>summary:before{content:'−'}.tc-detail>summary .tc-title{flex:1}.tc-detail .detail-body{padding:0 22px 24px}
.badge{display:inline-block;background:#f2f5f8;border-radius:6px;padding:3px 9px;font-size:11px;white-space:nowrap}
.badge.FAIL{background:#a41926;color:white}.badge.SKIP{background:#334e68;color:white}.badge{print-color-adjust:exact}
.tc-detail.FAIL{border-left:4px solid #d6505b}.tc-detail{color:var(--fg)}.purpose{font-size:13px;color:var(--mut);margin:4px 0 18px}
.spec{display:grid;grid-template-columns:1fr 1fr;gap:12px}.spec>div{border:1px solid var(--line);border-radius:8px;padding:12px;background:var(--card)}.spec h4{font-size:11px;color:var(--mut);margin:0 0 6px}.spec pre{font:12px/1.7 'Malgun Gothic',sans-serif;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}
.subdetail{border-top:1px solid var(--line);padding:12px 0;margin-top:14px;font-size:12px}.subdetail>summary,.appendix>summary{cursor:pointer;font-weight:700;color:#4a6278}.subdetail[open]>summary{margin-bottom:12px}
.gh td{background:var(--head);font-weight:700}.caveats{font-size:12px;color:var(--mut);margin-top:10px}.caveats ul{margin:0;padding-left:18px}
.glossary{font-size:12px}.glossary dl{display:grid;grid-template-columns:max-content 1fr;gap:8px 20px}.glossary dt{font-weight:700}.glossary dd{margin:0}
.appendix{font-size:12px}.appendix[open]>summary{margin-bottom:18px}.appendix h2{font-size:16px}.artifacts{font-size:12px;margin-top:14px}.empty{text-align:center;padding:36px;color:var(--mut)}
@media(max-width:760px){.wrap{padding:18px 12px 40px}h1{font-size:23px}.hero{display:block}.hero-status{margin-top:12px;min-width:0}.metrics{grid-template-columns:repeat(3,1fr)}.metric{border:0;padding:8px}.metric .n{font-size:25px}section{padding:18px}.comparison,.spec{grid-template-columns:1fr}.tc-detail>summary{padding:14px 12px;flex-wrap:wrap}.tc-detail .detail-body{padding:0 12px 18px}input{max-width:100%;width:180px}}
@media print{details::details-content{content-visibility:visible!important}details:not([open])>*:not(summary){display:block}#filter-empty{display:none!important}body{background:white;font-size:10pt}.wrap{max-width:none;padding:0}nav,.tools{display:none}.table-wrap{overflow:visible}.sum,table.steps{min-width:0;font-size:8pt}section,.tc-detail,.appendix{border-radius:0;margin-bottom:12px;box-shadow:none}.failure-card{break-inside:avoid}.tc-detail>summary{font-size:12pt}.comparison{grid-template-columns:1fr 1fr}a{color:inherit}.metrics{grid-template-columns:repeat(6,1fr)}th{print-color-adjust:exact}.failure-panel,.manual-panel{print-color-adjust:exact}.hero-status{print-color-adjust:exact}}

.dash{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin:12px 0}.tile{background:#f4f7fb;border:1px solid #dbe3ef;border-radius:10px;padding:16px}.tile .n{font-size:26px;font-weight:700}.k{color:#526174;font-size:12px}.s{font-weight:700}.s.PASS{color:#16734a}.s.FAIL{color:#ad2532}.s.BLOCKED{color:#805600}.s.MANUAL{color:#7843a5}.s.SKIP{color:#526174}.steps{table-layout:fixed}.steps th,.steps td{overflow-wrap:anywhere;word-break:break-word}.steps code,.note,pre{white-space:pre-wrap;overflow-wrap:anywhere}.value-detail>summary,.more>summary{cursor:pointer}.value-detail table{table-layout:fixed}.value-detail pre{max-height:30em;overflow:auto}.annotation{font-size:12px;margin-left:6px}.step-pass>summary{padding:12px;cursor:pointer}.fold{margin:12px 0}section[id],h2[id],details[id]{scroll-margin-top:60px}@media(max-width:700px){.comparison,.spec{display:block}.steps{min-width:650px}.table-wrap{overflow:auto}.hero{display:block}.tile{padding:10px}}@media print{.step-pass{break-inside:auto}.value-detail pre{max-height:none;overflow:visible}}
"""
SCRIPT = r"""
(() => {
  const search = document.getElementById('report-search');
  const status = document.getElementById('report-status');
  const rows = [...document.querySelectorAll('.sum tbody tr[data-tc]')];
  const cards = [...document.querySelectorAll('details.tc-detail')];
  const apply = () => {
    const q = search.value.trim().toLocaleLowerCase();
    let count = 0;
    rows.forEach(row => {
      const match = (!status.value || row.dataset.status === status.value) &&
        (!q || (row.dataset.tc + ' ' + row.textContent).toLocaleLowerCase().includes(q));
      row.hidden = !match;
      cards.filter(card => card.dataset.idx === row.dataset.idx).forEach(card => {card.hidden = !match;});
      if (match) count++;
    });
    document.getElementById('filter-count').textContent = count + ' / ' + rows.length + ' TC';
    document.getElementById('filter-empty').hidden = count !== 0;
  };
  if (!search || !status) return;
  document.getElementById('report-tools').hidden = false;
  search.addEventListener('input', apply); status.addEventListener('change', apply); apply();
  document.getElementById('expand-all').addEventListener('click', () => cards.forEach(x => {if (!x.hidden) x.open = true;}));
  document.getElementById('collapse-all').addEventListener('click', () => cards.forEach(x => x.open = false));
  const openTarget = target => {
    if (!target || target.tagName !== 'DETAILS') return;
    if (target.hidden) {search.value = ''; status.value = ''; apply();}
    target.hidden = false; target.open = true;
  };
  const openHash = () => {
    let id; try {id = decodeURIComponent(location.hash.slice(1));} catch (_) {return;}
    const target = document.getElementById(id);
    openTarget(target);
  };
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href^="#"]');
    if (!link) return;
    const target = document.getElementById(link.getAttribute('href').slice(1));
    openTarget(target);
  });
  window.addEventListener('hashchange', openHash); openHash();
  let printState = null;
  window.addEventListener('beforeprint', () => {
    if (printState) return;
    printState = [...document.querySelectorAll('details,[data-tc],#filter-empty')].map(el => [el, el.hidden, el.open]);
    printState.forEach(([el]) => {el.hidden = el.id === 'filter-empty'; if (el.tagName === 'DETAILS') el.open = true;});
  });
  window.addEventListener('afterprint', () => {
    if (!printState) return;
    printState.forEach(([el, hidden, open]) => {el.hidden = hidden; if (el.tagName === 'DETAILS') el.open = open;});
    printState = null;
  });
})();
"""


def render_badge(status, annotation=''):
    status = str(status)
    css = status if status in {'PASS', 'FAIL', 'MANUAL', 'SKIP', 'BLOCKED'} else 'UNKNOWN'
    return '<span class="badge ' + css + '">' + escape(status) + '</span>' + (
        '<span class="annotation">' + escape(str(annotation)) + '</span>' if annotation else '')


def render_value(value, _depth=0):
    if isinstance(value, (Mapping, list, tuple)) and _depth < 4:
        entries = value.items() if isinstance(value, Mapping) else enumerate(value, 1)
        rows = ''.join('<tr><th>' + escape(str(key)) + '</th><td>' + render_value(item, _depth + 1)
                       + '</td></tr>' for key, item in entries)
        return ('<details class="value-detail"><summary>구조화 값 ' + str(len(value))
                + '개 · 펼쳐 보기</summary><table>' + rows + '</table></details>')
    text = str(value)
    if len(text) > 350:
        return '<details class="value-detail"><summary>' + escape(text[:160]) + '…</summary><pre>' + escape(text) + '</pre></details>'
    return '<code>' + escape(text) + '</code>'


def render_note(note, limit=180):
    text = str(note or '')
    if len(text) <= limit:
        return '<span class="note">' + escape(text) + '</span>'
    return ('<span class="note">' + escape(text[:limit]) + '…</span><details class="more">'
            '<summary>비고 전체</summary><div class="note">' + escape(text) + '</div></details>')


def render_step(*, order, step, title, status, expected, actual, note='', source_description='',
                source_expected='', unblock_condition='', not_verified=''):
    context = ('<div class="k">수행 절차: ' + escape(str(source_description)) + '</div>') if source_description else ''
    source = ('<div class="k">기준 기대 결과: ' + escape(str(source_expected)) + '</div>') if source_expected else ''
    extra = ''.join('<p><b>' + label + '</b> ' + escape(str(value)) + '</p>' for label, value in
                    [('해제 조건', unblock_condition), ('이번 실행 미검증', not_verified)] if value)
    return ('<tr data-step-order="' + str(int(order)) + '"><td>' + escape(str(step)) + '</td><td>'
            + escape(str(title)) + context + '</td><td>' + render_badge(status) + '</td><td>'
            + source + render_value(expected) + '</td><td>' + render_value(actual) + '</td><td>'
            + render_note(note) + extra + '</td></tr>')


def render_tc_detail(*, key, tc_id, title, status, body_html):
    opened = '' if status == 'PASS' else ' open'
    return ('<details class="tc-detail" id="' + escape(str(key), quote=True) + '" data-idx="'
            + escape(str(key), quote=True) + '" data-tc="' + escape(str(tc_id), quote=True)
            + '" data-status="' + escape(str(status), quote=True) + '"' + opened + '><summary><span>'
            + escape(str(tc_id)) + '</span><span class="tc-title">' + escape(str(title)) + '</span>'
            + render_badge(status) + '</summary><div class="detail-body">' + body_html + '</div></details>')


def render_tools(statuses=('PASS', 'FAIL', 'BLOCKED', 'MANUAL', 'SKIP')):
    return ('<div class="tools" id="report-tools" hidden><label for="report-search">검색'
            '<input id="report-search" type="search" placeholder="TC 번호 또는 시험 이름"></label>'
            '<label for="report-status">판정<select id="report-status"><option value="">전체</option>'
            + ''.join('<option value="' + escape(s) + '">' + escape(s) + '</option>' for s in statuses)
            + '</select></label><button type="button" id="expand-all">상세 모두 펼치기</button>'
            '<button type="button" id="collapse-all">상세 모두 접기</button>'
            '<span id="filter-count" aria-live="polite"></span></div>')


def render_shell(*, title, product, subtitle, nav, body_html, overall=None):
    overall_class = str(overall) if overall in {'PASS', 'FAIL', 'MANUAL', 'SKIP', 'BLOCKED'} else ''
    header = ('<header><div class="eyebrow">' + escape(str(product)) + ' / QA RESULT</div>'
              '<div class="hero"><div><h1>' + escape(str(title)) + '</h1><div class="meta">'
              + escape(str(subtitle)) + '</div></div>'
              + ('<div class="hero-status ' + overall_class + '"><strong>종합 ' + escape(str(overall))
                 + '</strong><span>TC 최종 판정 기준</span></div>' if overall else '')
              + '</div></header>')
    navigation = '<nav aria-label="리포트 목차">' + ''.join('<a href="#' + escape(key, quote=True) + '">' + escape(label) + '</a>' for key, label in nav) + '</nav>'
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="report-layout-version" content="' + str(LAYOUT_VERSION) + '">'
            '<title>' + escape(str(title)) + '</title><style>' + STYLE + '</style></head><body>'
            '<main class="wrap">' + header + navigation + body_html + '</main><script>' + SCRIPT + '</script></body></html>')
