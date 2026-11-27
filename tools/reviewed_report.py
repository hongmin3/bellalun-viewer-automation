"""사람 확인 기록을 결과 JSON에 반영해 `Reports/reviewed/`에 검토본을 만든다(REQ-REPORT-003).

    python tools/reviewed_report.py --result Reports/Result_<시각>.json --review <내려받은 _reviewed.html 또는 JSON>

원본 결과 HTML·JSON·체크리스트 xlsx는 바꾸지 않는다. 다른 회차·판정이 바뀐 결과 파일의 기록,
사유 없는 FAIL·BLOCKED 변경은 반영하지 않고 종료 코드 2로 알린다. 만든 검토본은 자동 회귀 판정이나
릴리스 게이트의 입력이 아니다.
"""
import argparse
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.manual_review import ReviewError, build


def main(argv=None):
    parser = argparse.ArgumentParser(description='사람 확인 기록을 반영한 검토본 만들기')
    parser.add_argument('--result', required=True, help='원본 자동 결과 JSON(Reports/Result_*.json)')
    parser.add_argument('--review', required=True, help='브라우저에서 내려받은 _reviewed.html 또는 기록 JSON')
    parser.add_argument('--out-dir', help='검토본 폴더(기본: 결과 JSON 옆 reviewed)')
    args = parser.parse_args(argv)
    try:
        out = build(args.result, args.review, args.out_dir)
    except (OSError, ValueError) as error:
        print(f'[FAIL] {error}')
        return 2
    print(f"[OK] 반영 {out['applied']}건 · 남은 확인 대상 {out['remaining']}건")
    print(f"  HTML: {out['html']}")
    print(f"  JSON: {out['json']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
