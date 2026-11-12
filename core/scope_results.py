"""자동화하지 않는 사용자 지정 TC도 회귀 보고서에 명시한다."""
from core.result import TCResult


def regression_skips(scope, results):
    existing = {r.tc_id for r in results}
    skipped = []
    for row in scope:
        if (row.get('level') != 'SKIP' or row.get('checklist') == 'windows_update'
                or row['tc_id'] in existing):
            continue
        result = TCResult(row['tc_id'], row.get('title', row['tc_id']))
        result.skip(0, '사람 전용 TC — 자동화 수행 제외', row['reason'])
        skipped.append(result)
        existing.add(row['tc_id'])
    return skipped
