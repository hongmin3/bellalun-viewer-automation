"""automation_scope.json의 등급·제약을 문서로 만든다. 실적을 추정하지 않는다."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
LEVELS = ('FULL', 'PARTIAL', 'MANUAL', 'SKIP', 'SUPPORT')


def _cell(value):
    return str(value or '—').replace('|', '&#124;').replace('\r', '').replace('\n', '<br>')


def render_scope(rows):
    if not isinstance(rows, list):
        raise ValueError('범위 원본은 TC 목록이어야 합니다.')
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or not row.get('tc_id') or row['tc_id'] in seen
                or row.get('level') not in LEVELS
                or row.get('checklist', 'basic') not in {'basic', 'windows_update'}):
            raise ValueError('TC 번호·중복·등급·체크리스트 구분을 확인하세요.')
        seen.add(row['tc_id'])
    digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
                                      separators=(',', ':')).encode('utf-8')).hexdigest()
    lines = ['# 자동화 범위 현황', '',
             '이 문서는 `automation_scope.json`에서 자동 생성합니다. 등급은 구현 범위이며 실행 PASS 수치가 아닙니다. '
             '준비 항목(SUPPORT)은 체크리스트 TC 수에서 제외합니다.', '',
             f'원본 내용 SHA-256: `{digest}`', '',
             '갱신: `python tools/scope_summary.py`', '',
             '동기화 확인: `python tools/scope_summary.py --check`', '',
             '| 체크리스트 | TC 수 | FULL | PARTIAL | MANUAL | SKIP | 준비(SUPPORT) |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for kind, label in (('basic', '기본기능'), ('windows_update', 'Windows Update')):
        group = [row for row in rows if row.get('checklist', 'basic') == kind]
        counts = Counter(row['level'] for row in group)
        values = [len(group) - counts['SUPPORT'], *(counts[level] for level in LEVELS)]
        lines.append('| ' + label + ' | ' + ' | '.join(map(str, values)) + ' |')
    lines.extend(['', '## TC별 구현 범위와 남은 조건', '',
                  '기본기능과 WU는 각각 셉니다. 재사용하는 기본기능 TC의 결과를 WU 신규 실적으로 합산하지 않습니다. '
                  '제약과 해제 조건은 범위 원본에 기록된 내용을 그대로 표시합니다.', '',
                  '| TC | 제목 | 구분 / 등급 | 범위 분류 | 제약 | 해제 조건 |',
                  '|---|---|---|---|---|---|'])
    for row in rows:
        coverage = row.get('coverage') or {}
        kind = 'WU' if row.get('checklist') == 'windows_update' else '준비' if row['level'] == 'SUPPORT' else '기본기능'
        cells = (row['tc_id'], row.get('title'), kind + ' / ' + row['level'],
                 coverage.get('category'), coverage.get('gap') or row.get('reason'), coverage.get('unblock'))
        lines.append('| ' + ' | '.join(_cell(value) for value in cells) + ' |')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description='범위 원본에서 현재 구현 범위 문서를 생성합니다.')
    parser.add_argument('--source', type=Path, default=ROOT / 'automation_scope.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs' / 'followup-scope.md')
    parser.add_argument('--check', action='store_true', help='문서를 쓰지 않고 원본과 비교합니다.')
    args = parser.parse_args(argv)
    try:
        rendered = render_scope(json.loads(args.source.read_text(encoding='utf-8-sig')))
        if args.check:
            if not args.output.is_file() or args.output.read_text(encoding='utf-8') != rendered:
                print('범위 문서가 원본과 다릅니다. python tools/scope_summary.py로 갱신하세요.')
                return 1
            print('범위 문서가 현재 원본과 일치합니다.')
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding='utf-8', newline='\n')
            print('범위 문서를 현재 원본에서 생성했습니다.')
        return 0
    except (OSError, ValueError) as error:
        print(f'범위 문서를 만들지 못했습니다: {type(error).__name__}')
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
