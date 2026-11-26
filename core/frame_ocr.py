# -*- coding: utf-8 -*-
"""OCR 판독 합의와 재판독 — 제품 정보 없이 쓰는 공용 규칙.

제품 이름·컨트롤 ID·판정 근거는 담지 않는다. 무엇을 어떻게 읽을지는 호출하는 쪽이
`read_round(round_index)` 함수로 넘긴다. 이 모듈은 받은 판독으로 값을 확정할지,
기대값과 다르다고 확정할지, 다시 읽어야 할지만 정한다.

규칙(사용자 지시 2026-11-26):

1. 표는 `(방식, 회차)`마다 하나다. 같은 회차에서 같은 방식을 밝기 기준만 바꿔 여러 번 읽은 것은 한 표이고,
   그 안에서 과반 값이 표가 된다. 회차가 바뀌면 화면을 새로 캡처하고 확대 배율도 바꿔 읽으므로 다른 표다.
   이유: 같은 영상을 같은 방식으로 읽으면 같은 글꼴 착시를 반복한다(실측 2026-11-26: Classic 글꼴 `V`를
   문자 제한 판독이 세 밝기 모두 `Y`로 읽어 틀린 값이 합의를 통과했다). 배율을 바꾸면 오독 양상이 달라진다.
2. 값은 1등 표 수가 2등보다 많고, 그 값을 낸 **서로 다른 방식**이 두 개 이상일 때만 쓴다.
   이유: 한 방식이 회차마다 같은 착시를 반복해도 그 방식 혼자서는 값을 확정하지 못하게 한다.
3. 기대값과 다른 값은 어느 판독도 기대값을 읽지 못했을 때만 불일치로 확정한다.
   한 판독이라도 기대값을 읽었으면 불일치를 확정하지 않고 다시 읽는다.
4. 합의가 안 되거나 불일치를 확정하지 못하면 화면을 다시 캡처해 다시 읽는다(최대 `max_rounds`회).
   모든 회차의 판독을 함께 센다. 기대값과 같아질 때까지 골라 쓰지 않는다.
5. 끝까지 정하지 못하면 판독 불가(`unsure`)로 돌려주고, 판독 원문과 방식별 표를 남긴다.

PASS 기준은 낮추지 않는다. 기대값은 일치 여부를 확인할 때만 쓰고, 판독값을 기대값으로 바꾸거나 고르지 않는다.
"""

from collections import Counter

MATCH = "match"          # 합의한 값이 기대값과 같다
MISMATCH = "mismatch"    # 합의한 값이 기대값과 다르고, 어느 판독도 기대값을 읽지 못했다
UNSURE = "unsure"        # 합의하지 못했거나 불일치를 확정하지 못했다


def default_normalize(value):
    """비교용 값: 글자·숫자만 남기고 소문자로 바꾼다. 빈 값은 None."""
    text = "".join(c.lower() for c in str(value or "") if c.isalnum())
    return text or None


class Ballot:
    """한 칸(필드)의 판독 표. `add(방식, 값)`으로 모으고 `settle()`로 확정한다."""

    def __init__(self, normalize=default_normalize):
        self.normalize = normalize
        self.reads = []          # [(방식, 원문 값, 비교용 값, 회차)]

    def add(self, method, value, round_index=0):
        norm = self.normalize(value)
        if norm:
            self.reads.append((str(method), str(value).strip(), norm, int(round_index)))

    def method_votes(self):
        """표: {(방식, 회차): 비교용 값}. 한 표 안에서 과반(1등이 2등보다 많음)이 없으면 그 표는 없다."""
        by_method = {}
        for method, _raw, norm, round_index in self.reads:
            by_method.setdefault((method, round_index), Counter())[norm] += 1
        votes = {}
        for method, counts in by_method.items():
            ranked = counts.most_common(2)
            if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
                votes[method] = ranked[0][0]
        return votes

    def settle(self, min_methods=2):
        """확정한 원문 값 또는 None."""
        votes = self.method_votes()
        ranked = Counter(votes.values()).most_common(2)
        if not ranked:
            return None
        top_norm, top = ranked[0]
        runner = ranked[1][1] if len(ranked) > 1 else 0
        methods = {method for (method, _r), norm in votes.items() if norm == top_norm}
        if len(methods) < min_methods or top <= runner:
            return None
        return next(raw for _m, raw, norm, _r in self.reads if norm == top_norm)

    def saw(self, expected):
        """어느 판독이든 기대값과 같은 값을 읽은 적이 있는가."""
        want = self.normalize(expected)
        return bool(want) and any(norm == want for _m, _raw, norm, _r in self.reads)

    def describe(self, limit=12):
        """사람이 읽는 표 요약: `방식@회차=값(같은 값 수/읽은 수) …`. 회차는 1부터 센다."""
        votes = self.method_votes()
        keys = sorted({(m, r) for m, _raw, _n, r in self.reads}, key=lambda k: (k[1], k[0]))
        parts = []
        for method, round_index in keys:
            raws = [(raw, n) for m, raw, n, r in self.reads if (m, r) == (method, round_index)]
            label = "%s@%d" % (method, round_index + 1)
            if (method, round_index) in votes:
                want = votes[(method, round_index)]
                raw = next(r for r, n in raws if n == want)
                parts.append("%s=%s(%d/%d)" % (label, raw, sum(1 for _r, n in raws if n == want), len(raws)))
            else:
                parts.append("%s=표 없음(%s)" % (label, ", ".join(r for r, _n in raws[:3])))
        return " ".join(parts[:limit]) or "판독 없음"


def judge(ballot, expected=None, min_methods=2):
    """(MATCH|MISMATCH|UNSURE, 확정 값). 기대값이 없으면 확정 여부만 본다(확정이면 MATCH)."""
    value = ballot.settle(min_methods)
    if value is None:
        return UNSURE, None
    if expected is None:
        return MATCH, value
    if ballot.normalize(value) == ballot.normalize(expected):
        return MATCH, value
    if ballot.saw(expected):
        return UNSURE, value     # 기대값을 읽은 판독이 있다 — 불일치를 확정하지 않고 다시 읽는다
    return MISMATCH, value


def reread(read_round, expected=None, max_rounds=3, min_methods=2, normalize=default_normalize):
    """여러 칸을 함께 읽고, 정해지지 않은 칸이 있으면 다시 읽는다.

    read_round(round_index) -> {칸: [(방식, 값), ...]} 또는 None(이번 회차 판독 실패).
    expected: {칸: 기대값} 또는 None. 기대값이 있는 칸만 판정 대상이다. 없으면 받은 칸 모두를 확정하려 한다.

    반환: {"fields": {칸: 확정 값}, "verdicts": {칸: MATCH|MISMATCH|UNSURE},
           "ballots": {칸: Ballot}, "rounds": 실제 회차 수, "notes": [회차별 사유]}
    """
    ballots, notes, rounds = {}, [], 0
    verdicts, fields = {}, {}
    for index in range(max(1, int(max_rounds))):
        rounds = index + 1
        got = read_round(index)
        if got is None:
            notes.append("%d회차: 판독 실패" % rounds)
        else:
            for field, reads in got.items():
                ballot = ballots.setdefault(field, Ballot(normalize))
                for method, value in reads:
                    ballot.add(method, value, index)
        targets = list(expected) if expected else list(ballots)
        verdicts, fields = {}, {}
        for field in targets:
            verdict, value = judge(ballots.get(field, Ballot(normalize)),
                                   (expected or {}).get(field), min_methods)
            verdicts[field] = verdict
            if value is not None and verdict != UNSURE:
                fields[field] = value
        open_fields = [f for f, v in verdicts.items() if v == UNSURE]
        if not open_fields and targets:
            break
        notes.append("%d회차: 다시 읽을 칸 %s" % (rounds, ", ".join(open_fields) or "(판독 없음)"))
    return {"fields": fields, "verdicts": verdicts, "ballots": ballots, "rounds": rounds, "notes": notes}
