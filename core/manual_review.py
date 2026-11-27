# -*- coding: utf-8 -*-
"""사람 확인 반영 리포트(REQ-REPORT-003, `frame/FRAME.md` 4절 8).

1. 결과 리포트(HTML)의 실패 원인·수동 확인 카드에서 MANUAL·SKIP·FAIL·BLOCKED 항목마다
   PASS/FAIL 선택과 메모 칸을 둔다. FAIL·BLOCKED를 확인하려면 사유(메모)가 있어야 한다.
2. "사람 확인 반영 리포트 만들기"를 누르면 브라우저 안에서 같은 리포트의 사본을 고쳐
   `<원본 이름>_reviewed.html`로 내려받는다. 프로그램 실행이나 인터넷이 필요 없다.
   - 맨 위에 사람 확인 결과표(자동 판정 → 사람 판정, 확인자·일시·메모)를 넣는다.
   - 확인한 Step의 판정을 바꾸고 TC 판정·결과 요약 수·종합 판정을 Bellalun 판정 규칙
     (FAIL > BLOCKED > MANUAL > PASS > SKIP, 판정을 막는 SKIP은 MANUAL)으로 다시 계산한다.
   - 확인 기록은 HTML 안 `<script type="application/json" id="human-review">`에 함께 남긴다.
3. 원본 HTML·JSON·체크리스트 xlsx·실행 증거는 바꾸지 않는다. 검토본은 자동 회귀 판정이나 릴리스
   게이트의 입력이 아니다(`report_role: human_reviewed`, `core/automation_health.completed_report_data`).
4. `build()`는 같은 결정을 결과 JSON에 반영해 `Reports/reviewed/`에 HTML·JSON을 만드는 보조 경로다.
   검토 기록은 내려받은 `_reviewed.html` 안의 기록이나 같은 형식의 JSON 파일을 쓴다.
   실행 화면의 수동 검토 창(REQ-QA-003, `review.json`)의 검수 상태 기록과는 따로 남는다.
"""
import hashlib
import html
import json
import os
import re
from datetime import datetime

FORMAT = 'bellalun-manual-review/1'
DECISIONS = ('PASS', 'FAIL')
REVIEWABLE = ('MANUAL', 'SKIP', 'FAIL', 'BLOCKED')
#: 자동 판정을 사람이 바꿀 때 사유(메모)가 꼭 있어야 하는 판정.
REASON_REQUIRED = ('FAIL', 'BLOCKED')
#: 검토본 JSON의 리포트 역할. 완료 리포트 판정(`completed_report_data`)이 받지 않는다.
REVIEW_ROLE = 'human_reviewed'
#: Python 경로 검토본을 두는 하위 폴더. `Reports/Result_*.json`을 찾는 도구에 잡히지 않는다.
REVIEW_DIR = 'reviewed'
STATUSES = ('PASS', 'FAIL', 'MANUAL', 'SKIP', 'BLOCKED')


class ReviewError(ValueError):
    pass


def title_key(title):
    """Step 제목을 기록에 원문으로 싣지 않고 항목을 맞추는 짧은 해시."""
    return hashlib.sha256(str(title).encode('utf-8')).hexdigest()[:12]


def fingerprint(results, run_id=None):
    """리포트와 검토 기록이 같은 실행·같은 자동 판정인지 확인하는 지문.

    실행 번호, TC ID·시작 시각, Step 번호·제목·판정으로 만든다. 다른 회차나 판정이 바뀐 결과 파일에서
    만든 검토 기록은 지문이 달라 반영하지 않는다.
    """
    parts = ['run:%s' % (run_id or '')]
    for r in results:
        started = getattr(r, 'started', None)
        stamp = started.isoformat(timespec='seconds') if hasattr(started, 'isoformat') else str(started or '')
        parts.append('%s|%s|%s' % (r.tc_id, stamp, '/'.join(
            '%s:%s:%s' % (c.step, title_key(c.title), c.status) for c in r.checks)))
    return hashlib.sha256('\n'.join(parts).encode('utf-8')).hexdigest()[:16]


def reviewable(check):
    """사람 확인 대상: MANUAL·SKIP·FAIL·BLOCKED Step. 판정을 막지 않는다고 정한 SKIP은 뺀다."""
    if check.status not in REVIEWABLE:
        return False
    return not (check.status == 'SKIP' and getattr(check, 'blocks_verdict', None) is False)


def verdict_of(checks):
    """`core.result.TCResult.verdict`와 같은 규칙. `checks`는 `(판정, blocks_verdict)` 목록이다."""
    statuses = [status for status, _ in checks]
    for status in ('FAIL', 'BLOCKED', 'MANUAL'):
        if status in statuses:
            return status
    if any(status == 'SKIP' and blocks for status, blocks in checks):
        return 'MANUAL'
    return 'PASS' if 'PASS' in statuses else 'SKIP'


def overall_of(verdicts):
    """종합 판정: TC 판정 중 FAIL > BLOCKED > MANUAL > PASS > SKIP 순으로 처음 있는 것."""
    return next((status for status in ('FAIL', 'BLOCKED', 'MANUAL', 'PASS', 'SKIP') if status in verdicts), None)


def review_data(results, keys, run_id=None):
    """브라우저 스크립트가 TC 판정을 다시 계산할 자료(`<script id="review-data">`)."""
    return {'format': FORMAT, 'fingerprint': fingerprint(results, run_id), 'run_id': run_id or '',
            'statuses': list(STATUSES),
            'tcs': [{'key': key, 'tc_id': r.tc_id, 'verdict': r.verdict,
                     'checks': [[order, c.status, bool(c.blocks_verdict)] for order, c in enumerate(r.checks, 1)]}
                    for r, key in zip(results, keys)]}


def box_html(key, tc_id, check, seq):
    """사람 확인 입력란: PASS/FAIL 선택 버튼과 메모. `seq`는 TC 안 Step 순서(1부터)다."""
    e = lambda value: html.escape(str(value), quote=True)
    name = 'rv-%s-%s' % (key, seq)
    label = '체크리스트 직접 수행' if check.status == 'SKIP' else check.title
    hint = ('직접 수행한 결과와 근거를 적어 주세요(선택). 예: 체크리스트 Step 1~3 직접 수행, 정상'
            if check.status == 'SKIP' else
            '사유 필수 — 직접 확인한 결과와 판단 사유를 적어 주세요. 예: 자동화 판독 오류, 화면에서 정상 확인'
            if check.status in REASON_REQUIRED else
            '확인한 내용을 적어 주세요(선택). 예: 캡처와 기준 문구가 같음')
    warn = ("<div class='rv-warn' hidden>FAIL·BLOCKED 항목은 사유를 꼭 적어야 합니다.</div>"
            if check.status in REASON_REQUIRED else '')
    return ("<div class='review-box' data-idx='%s' data-tc='%s' data-step='%s' data-seq='%s' data-title='%s' "
            "data-auto='%s' data-label='%s'><div class='rv-head'><b>사람 확인 결과</b>"
            "<span class='rv-state'>미확인</span></div><div class='rv-choices'>"
            "<label class='rv-choice pass'><input type='radio' name='%s' value='PASS'><span>PASS</span></label>"
            "<label class='rv-choice fail'><input type='radio' name='%s' value='FAIL'><span>FAIL</span></label>"
            "</div><textarea class='review-memo' rows='2' placeholder='%s'></textarea>%s</div>"
            % (e(key), e(tc_id), e(check.step), e(seq), e(title_key(check.title)), e(check.status), e(label),
               e(name), e(name), e(hint), warn))


def panel_html(results, keys, run_id=None):
    """첫 확인 절 맨 위의 반영 패널, 판정 재계산 자료와 동작 스크립트."""
    data = json.dumps(review_data(results, keys, run_id), ensure_ascii=False).replace('<', '\\u003c')
    # 모양은 공용 `core/report_layout.STYLE`의 사람 확인 반영 규칙을 쓴다(VXvue와 같은 모양).
    return ("<div class='review-panel' id='review-panel'>"
            "<p><b>확인한 결과를 리포트에 반영하기</b> — 아래 실패·수동 확인 항목에서 PASS/FAIL을 고르고 메모를 "
            "적은 뒤 <b>사람 확인 반영 리포트 만들기</b>를 누르세요. 확인 결과가 반영된 새 리포트 파일"
            "(<code>…_reviewed.html</code>)이 내려받아집니다. 이 원본 리포트와 결과 JSON·체크리스트 xlsx는 "
            "바뀌지 않습니다. 검수 완료 기록은 실행 화면의 수동 검토 창에 따로 남깁니다.</p>"
            "<div class='rv-panel-row'><label class='rv-reviewer'>확인자 <input type='text' id='review-reviewer' "
            "placeholder='이름을 입력하세요'></label><button type='button' id='review-save' class='rv-save'>"
            "사람 확인 반영 리포트 만들기</button><span id='review-count' class='rv-count'></span></div></div>"
            "<script type='application/json' id='review-data'>" + data + "</script>" + SCRIPT)


SCRIPT = r"""<script id='review-script'>
(function(){
  var save=document.getElementById('review-save'); if(!save) return;
  var data=JSON.parse(document.getElementById('review-data').textContent);
  function boxes(root){return Array.prototype.slice.call((root||document).querySelectorAll('.review-box'));}
  function esc(t){return String(t).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function badge(s){return '<span class="badge '+s+'">'+s+'</span>';}
  function sel(v){return String(v).replace(/["\\]/g,'\\$&');}
  function count(){var all=boxes(), done=all.filter(function(b){return b.querySelector('input[type=radio]:checked');});
    document.getElementById('review-count').textContent='확인 '+done.length+' / '+all.length+'건';}
  function needsReason(box){var w=box.querySelector('.rv-warn'); if(!w) return false;
    var picked=box.querySelector('input[type=radio]:checked'), empty=!box.querySelector('.review-memo').value.trim();
    var bad=!!picked && empty; w.hidden=!bad; box.classList.toggle('need-reason', bad); return bad;}
  document.addEventListener('change', function(ev){
    var box=ev.target.closest && ev.target.closest('.review-box'); if(!box) return;
    var c=box.querySelector('input[type=radio]:checked'), st=box.querySelector('.rv-state');
    if(c){st.textContent=c.value; st.className='rv-state '+c.value; box.classList.add('done');}
    needsReason(box); count();});
  document.addEventListener('input', function(ev){
    var box=ev.target.closest && ev.target.closest('.review-box'); if(box) needsReason(box);});
  count();
  function verdictOf(checks){var s=checks.map(function(c){return c[1];});
    var first=['FAIL','BLOCKED','MANUAL'].filter(function(v){return s.indexOf(v)>=0;})[0]; if(first) return first;
    if(checks.some(function(c){return c[1]==='SKIP'&&c[2];})) return 'MANUAL';
    return s.indexOf('PASS')>=0?'PASS':'SKIP';}
  save.addEventListener('click', function(){
    var reviewer=document.getElementById('review-reviewer').value.trim();
    if(!reviewer){alert('확인자 이름을 입력하세요.'); return;}
    var live=boxes(), items=[];
    live.forEach(function(b,i){var c=b.querySelector('input[type=radio]:checked');
      items.push({index:i, key:b.dataset.idx, tc_id:b.dataset.tc, step:b.dataset.step, seq:b.dataset.seq,
        title:b.dataset.title, label:b.dataset.label, auto_status:b.dataset.auto, decision:c?c.value:null,
        memo:b.querySelector('.review-memo').value.trim()});});
    var decided=items.filter(function(x){return x.decision;});
    if(!decided.length){alert('PASS 또는 FAIL을 고른 항목이 없습니다.'); return;}
    var noReason=decided.filter(function(x){return (x.auto_status==='FAIL'||x.auto_status==='BLOCKED')&&!x.memo;});
    if(noReason.length){noReason.forEach(function(x){needsReason(live[x.index]);});
      live[noReason[0].index].scrollIntoView({block:'center'}); live[noReason[0].index].querySelector('.review-memo').focus();
      alert('FAIL·BLOCKED 항목은 사유를 꼭 적어야 합니다.\n\n사유가 없는 항목: '
        +noReason.map(function(x){return x.tc_id+' Step '+x.step;}).join(', ')+'\n\n메모 칸에 사유를 적은 뒤 다시 눌러 주세요.');
      return;}
    var now=new Date(), pad=function(n){return String(n).padStart(2,'0');};
    var when=now.getFullYear()+'-'+pad(now.getMonth()+1)+'-'+pad(now.getDate())+' '+pad(now.getHours())+':'+pad(now.getMinutes());
    var doc=document.documentElement.cloneNode(true);
    function rec(x){return '<b>사람 확인 '+badge(x.decision)+'</b> '+esc(reviewer)+' · '+when+(x.memo?' — '+esc(x.memo):'')
      +' <span class="k">(자동 판정 '+esc(x.auto_status)+')</span>';}
    function markCards(scope, decision){ if(!scope) return;
      scope.querySelectorAll('.read-card .read-card-head .badge').forEach(function(bd){
        if(bd.classList.contains('PASS')) return; bd.className='badge '+decision; bd.textContent=decision;
        bd.insertAdjacentHTML('afterend',' <span class="k">사람 확인</span>');});}
    // 1) 입력란 → 확정 결과
    boxes(doc).forEach(function(b,i){var it=items[i], div=document.createElement('div');
      if(it.decision) markCards(b.closest('.manual-step')||b.parentNode, it.decision);
      div.className='review-result '+(it.decision||'NONE');
      div.innerHTML=it.decision?rec(it):'<b>사람 확인 안 함</b> <span class="k">(자동 판정 '+esc(it.auto_status)+' 그대로)</span>';
      b.parentNode.replaceChild(div,b);});
    // 2) TC 상세의 Step 판정과 TC 판정
    var tcs={}; data.tcs.forEach(function(t){tcs[t.key]={tc_id:t.tc_id, verdict:t.verdict,
      checks:t.checks.map(function(c){return c.slice();})};});
    decided.forEach(function(x){var t=tcs[x.key]; if(!t) return;
      t.checks.forEach(function(c){if(String(c[0])===String(x.seq)) c[1]=x.decision;});
      doc.querySelectorAll('details.tc-detail[data-idx="'+sel(x.key)+'"] tr[data-step-order="'+sel(x.seq)+'"]').forEach(function(tr){
        var cells=tr.querySelectorAll(':scope > td'); if(cells.length<3) return;
        cells[2].innerHTML=badge(x.decision)+'<div class="k">사람 확인</div>'; markCards(tr, x.decision);
        cells[cells.length-1].insertAdjacentHTML('afterbegin','<div class="review-result '+x.decision+'">'+rec(x)+'</div>');});});
    var after={}, changed={};
    Object.keys(tcs).forEach(function(key){after[key]=verdictOf(tcs[key].checks);
      if(after[key]!==tcs[key].verdict) changed[key]=after[key];});
    Object.keys(changed).forEach(function(key){var v=changed[key];
      doc.querySelectorAll('tr[data-idx="'+sel(key)+'"]').forEach(function(tr){var td=tr.querySelectorAll(':scope > td')[2];
        if(td) td.innerHTML=badge(v)+' <span class="k">사람 확인</span>'; tr.dataset.status=v;});
      doc.querySelectorAll('details.tc-detail[data-idx="'+sel(key)+'"]').forEach(function(d){d.dataset.status=v;
        var sb=d.querySelector('summary .badge'); if(sb){sb.className='badge '+v; sb.textContent=v;}});});
    // 3) 결과 요약 수와 종합 판정(자동 판정 숫자는 기록으로 남긴다)
    function tally(map){var c={}; data.statuses.forEach(function(s){c[s]=0;}); Object.keys(map).forEach(function(k){c[map[k]]++;}); return c;}
    var autoMap={}; Object.keys(tcs).forEach(function(k){autoMap[k]=tcs[k].verdict;});
    var autoC=tally(autoMap), newC=tally(after);
    function line(c){return data.statuses.filter(function(s){return c[s];}).map(function(s){return s+' '+c[s];}).join(' · ');}
    doc.querySelectorAll('.tile .n[data-status]').forEach(function(n){n.textContent=newC[n.dataset.status];});
    var overall=['FAIL','BLOCKED','MANUAL','PASS','SKIP'].filter(function(s){return newC[s];})[0];
    var hero=doc.querySelector('.hero-status');
    if(hero && overall){hero.className='hero-status '+overall; hero.querySelector('strong').textContent='종합 '+overall;
      hero.querySelector('span').textContent='사람 확인 '+decided.length+'건 포함';}
    var head=doc.querySelector('#overview-headline');
    if(head) head.insertAdjacentHTML('beforebegin','<p class="review-stamp"><b>사람 확인 '+decided.length+'건 반영</b> — '
      +esc(reviewer)+' · '+when+'. 사람 판정 기준 종합 '+badge(overall||'-')+' · 자동 판정 기준 결과: '+line(autoC)+'.</p>');
    function stamp(id, label, sts){var h=doc.querySelector(id+' h2'); if(!h) return;
      var xs=items.filter(function(x){return sts.indexOf(x.auto_status)>=0;}); if(!xs.length) return;
      var n=function(d){return xs.filter(function(x){return x.decision===d;}).length;}, left=xs.filter(function(x){return !x.decision;}).length;
      h.insertAdjacentHTML('afterend','<p class="review-stamp"><b>'+label+'</b> — 확인자 '+esc(reviewer)+' · '+when+' · PASS '+n('PASS')
        +(n('FAIL')?' · FAIL '+n('FAIL'):'')+(left?' · 미확인 '+left:'')+'. 항목별 결과와 메모는 각 항목에 남겼다.</p>');}
    stamp('#failures','사람이 직접 확인(사유 기록)',['FAIL']); stamp('#manual','사람 확인 완료',['MANUAL','SKIP','BLOCKED']);
    // 4) 맨 위 사람 확인 결과표와 기록
    var pending=items.length-decided.length;
    var rows=items.map(function(x){return '<tr><td>'+esc(x.tc_id)+'</td><td>Step '+esc(x.step)+' · '+esc(x.label)+'</td><td>'
      +badge(x.auto_status)+'</td><td>'+(x.decision?badge(x.decision):'<span class="k">확인 안 함</span>')+'</td><td>'+esc(x.memo||'')+'</td></tr>';}).join('');
    var tcRows=Object.keys(changed).map(function(k){return '<tr><td>'+esc(tcs[k].tc_id)+'</td><td>'+badge(tcs[k].verdict)+'</td><td>'+badge(changed[k])+'</td></tr>';}).join('');
    var sec=document.createElement('section'); sec.id='human-review-summary'; sec.className='human-review';
    sec.innerHTML='<h2>사람 확인 반영 — '+esc(reviewer)+' · '+when+'</h2><p>자동 판정이 MANUAL·SKIP·FAIL·BLOCKED이던 '+items.length
      +'건 중 '+decided.length+'건을 사람이 확인했다(PASS '+decided.filter(function(x){return x.decision==='PASS';}).length
      +' · FAIL '+decided.filter(function(x){return x.decision==='FAIL';}).length+(pending?' · 미확인 '+pending:'')
      +'). 종합 판정·결과 요약·전체 TC 결과·상세 근거는 사람 판정을 반영했다. 자동 판정 기준 결과: '+line(autoC)
      +'. 이 사본은 사람 확인 기록이며 자동 회귀 판정이나 릴리스 게이트의 입력이 아니다.</p>'
      +'<div class="table-wrap"><table><tr><th>TC</th><th>항목</th><th>자동 판정</th><th>사람 판정</th><th>메모</th></tr>'+rows+'</table></div>'
      +(tcRows?'<h3>판정이 바뀐 TC</h3><div class="table-wrap"><table><tr><th>TC</th><th>자동 판정</th><th>사람 확인 반영</th></tr>'+tcRows+'</table></div>':'');
    var ov=doc.querySelector('#overview'); ov.parentNode.insertBefore(sec, ov);
    var nav=doc.querySelector('nav'); if(nav){var a=document.createElement('a'); a.href='#human-review-summary';
      a.textContent='사람 확인 결과'; nav.insertBefore(a, nav.firstChild);}
    var record=document.createElement('script'); record.type='application/json'; record.id='human-review';
    record.textContent=JSON.stringify({format:data.format, fingerprint:data.fingerprint, run_id:data.run_id, reviewer:reviewer,
      reviewed_at:now.toISOString(), items:decided.map(function(x){return {tc_id:x.tc_id, key:x.key, step:x.step, seq:x.seq,
        title:x.title, auto_status:x.auto_status, decision:x.decision, memo:x.memo};}),
      tc_verdicts:Object.keys(after).map(function(k){return {key:k, tc_id:tcs[k].tc_id, auto:tcs[k].verdict, reviewed:after[k]};}),
      overall:overall||null}).replace(/</g,'\\u003c');
    doc.querySelector('body').appendChild(record);
    ['#review-panel','#review-script','#review-data'].forEach(function(s){var n=doc.querySelector(s); if(n) n.remove();});
    var t=doc.querySelector('title'); if(t) t.textContent=t.textContent+' · 사람 확인 반영';
    var text='<!doctype html>\n'+doc.outerHTML;
    var name=(decodeURIComponent(location.pathname.split('/').pop()||'Result.html')).replace(/\.html?$/i,'')+'_reviewed.html';
    var blob=new Blob([text],{type:'text/html'}), link=document.createElement('a'), makeLink=URL.createObjectURL;
    link.href=makeLink.call(URL, blob); link.download=name; document.body.appendChild(link); link.click(); link.remove();
  });
})();
</script>"""


_RECORD = re.compile(r'<script type="application/json" id="human-review">(.*?)</script>', re.S)


def read_reviewed_html(path):
    """내려받은 `_reviewed.html` 안의 사람 확인 기록을 읽는다. 없으면 ReviewError."""
    with open(path, encoding='utf-8') as source:
        found = _RECORD.search(source.read())
    if not found:
        raise ReviewError('사람 확인 기록이 들어 있는 검토본이 아닙니다.')
    return json.loads(found.group(1))


def load_review(path):
    """검토 기록: `_reviewed.html`이면 안의 기록을, JSON이면 그대로 읽는다."""
    if str(path).lower().endswith(('.html', '.htm')):
        return read_reviewed_html(path)
    with open(path, encoding='utf-8') as source:
        return json.load(source)


def apply(results, review, run_id=None):
    """검토 기록을 결과에 반영한다. `(반영 목록, 확인자, 시각)`. 맞지 않는 항목이 있으면 ReviewError.

    다른 회차·자동 판정이 바뀐 결과(지문 불일치), 결과에 없는 Step, 확인 대상이 아닌 Step,
    PASS/FAIL이 아닌 결정, 사유 없는 FAIL·BLOCKED 변경은 하나라도 있으면 아무것도 반영하지 않는다.
    """
    if not isinstance(review, dict) or review.get('format') != FORMAT:
        raise ReviewError('사람 확인 기록 형식이 아닙니다.')
    if review.get('fingerprint') != fingerprint(results, run_id):
        raise ReviewError('이 결과 리포트에서 만든 사람 확인 기록이 아닙니다(다른 회차이거나 결과 파일이 바뀜).')
    reviewer = str(review.get('reviewer') or '').strip()
    if not reviewer:
        raise ReviewError('확인자 이름이 없습니다.')
    when = str(review.get('reviewed_at') or '')
    by_key = {}
    for r in results:
        for order, c in enumerate(r.checks, 1):
            by_key[(r.tc_id, str(order), title_key(c.title))] = (r, c)
    plan, problems = [], []
    for item in review.get('items') or []:
        key = (str(item.get('tc_id')), str(item.get('seq')), str(item.get('title')))
        found = by_key.get(key)
        label = '%s Step %s' % (key[0], item.get('step'))
        decision = item.get('decision')
        memo = str(item.get('memo') or '').strip()
        if found is None:
            problems.append(label + ': 결과에 없는 항목')
        elif not reviewable(found[1]):
            problems.append('%s: 확인 대상이 아닌 항목(%s)' % (label, found[1].status))
        elif decision not in DECISIONS:
            problems.append(label + ': 판정은 PASS 또는 FAIL이어야 함')
        elif found[1].status in REASON_REQUIRED and not memo:
            problems.append('%s: 자동 판정 %s를 바꾸려면 사유가 필요함' % (label, found[1].status))
        else:
            plan.append((found, decision, memo))
    if problems:
        raise ReviewError('사람 확인 기록을 반영하지 못했습니다: ' + '; '.join(problems))
    applied = []
    for (r, c), decision, memo in plan:
        auto = c.status
        c.status = decision
        c.note = ('사람 확인(%s, %s): %s / 자동 판정 %s. %s'
                  % (reviewer, when, memo or '메모 없음', auto, c.note or '')).strip()
        applied.append({'tc_id': r.tc_id, 'step': c.step, 'title': c.title, 'auto_status': auto,
                        'decision': decision, 'memo': memo})
    return applied, reviewer, when


def summary_html(applied, reviewer, when, auto_counts, remaining):
    """Python 경로 검토본 맨 위의 사람 확인 결과표."""
    e = lambda value: html.escape(str(value), quote=True)
    badge = lambda status: '<span class="badge %s">%s</span>' % (e(status), e(status))
    rows = ''.join('<tr><td>%s</td><td>Step %s · %s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                   % (e(a['tc_id']), e(a['step']), e(a['title']), badge(a['auto_status']), badge(a['decision']),
                      e(a['memo'])) for a in applied)
    line = ' · '.join('%s %d' % (status, auto_counts[status]) for status in STATUSES if auto_counts.get(status))
    return ("<section id='human-review-summary' class='human-review'><h2>사람 확인 반영 — %s · %s</h2>"
            "<p>사람이 확인한 %d건(PASS %d · FAIL %d)%s. 종합 판정·결과 요약·전체 TC 결과·상세 근거는 사람 판정을 "
            "반영했다. 자동 판정 기준 결과: %s. 이 사본은 사람 확인 기록이며 자동 회귀 판정이나 릴리스 게이트의 "
            "입력이 아니다.</p><div class='table-wrap'><table><tr><th>TC</th><th>항목</th><th>자동 판정</th>"
            "<th>사람 판정</th><th>메모</th></tr>%s</table></div></section>"
            % (e(reviewer), e(when), len(applied), sum(a['decision'] == 'PASS' for a in applied),
               sum(a['decision'] == 'FAIL' for a in applied),
               (' · 남은 확인 대상 %d건' % remaining) if remaining else '', e(line), rows))


def build(result_path, review, out_dir=None):
    """`<결과>_reviewed.html/.json`을 `Reports/reviewed/`에 만든다. 원본 결과 파일은 바꾸지 않는다.

    `review`는 기록(dict)이나 그 파일 경로(`_reviewed.html` 또는 JSON)다.
    """
    from . import result as R
    from .wu_chain import result_from_dict
    if not isinstance(review, dict):
        review = load_review(review)
    with open(result_path, 'rb') as source:
        raw = source.read()
    data = json.loads(raw.decode('utf-8'))
    meta = dict(data.get('meta') or {})
    if meta.get('report_role') == REVIEW_ROLE:
        raise ReviewError('이미 사람 확인을 반영한 검토본입니다. 원본 자동 결과 JSON을 고르세요.')
    results = [result_from_dict(row) for row in data.get('results') or []]
    auto_counts = {status: sum(r.verdict == status for r in results) for status in STATUSES}
    targets = sum(reviewable(c) for r in results for c in r.checks)
    applied, reviewer, when = apply(results, review, meta.get('run_id'))
    remaining = targets - len(applied)
    stem = os.path.splitext(os.path.basename(result_path))[0] + '_reviewed'
    folder = out_dir or os.path.join(os.path.dirname(os.path.abspath(result_path)), REVIEW_DIR)
    os.makedirs(folder, exist_ok=True)
    meta.update(report_role=REVIEW_ROLE, chain_completed=False, human_review={
        'reviewer': reviewer, 'reviewed_at': when, 'items': applied, 'remaining': remaining,
        'auto_result': {'file': os.path.basename(result_path), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'tc_verdicts': auto_counts},
        'built_at': datetime.now().isoformat(timespec='seconds')})
    page = R._render_html(results, meta)
    marker = "<section id='overview'>"
    page = page.replace(marker, summary_html(applied, reviewer, when, auto_counts, remaining) + marker, 1)
    html_path = os.path.join(folder, stem + '.html')
    json_path = os.path.join(folder, stem + '.json')
    with open(html_path, 'w', encoding='utf-8') as output:
        output.write(page)
    out = dict(data, meta=meta, results=[r.as_dict() for r in results])
    with open(json_path, 'w', encoding='utf-8') as output:
        json.dump(out, output, ensure_ascii=False, indent=2)
    return {'html': html_path, 'json': json_path, 'applied': len(applied), 'remaining': remaining}
