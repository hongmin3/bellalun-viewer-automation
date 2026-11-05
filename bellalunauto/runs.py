"""실행 계획·진행·결과·사람 검토. 엔진 판정은 수정하지 않는다."""
from __future__ import annotations

from datetime import datetime
import getpass
import json
import os
from pathlib import Path
import tempfile
import time
import uuid


def _now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _read(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RunRecord:
    def __init__(self, workspace, path, data):
        self.workspace, self.path, self.data = Path(workspace), Path(path), data

    @classmethod
    def create(cls, workspace, action, plan, *, consent=False):
        stamp = time.time()
        run_id = datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
        path = Path(workspace) / 'Runs' / run_id / 'run.json'
        existing = {str(p): [p.stat().st_mtime_ns, p.stat().st_size]
                    for p in (Path(workspace) / 'Reports').glob('*') if p.is_file()}
        record = cls(workspace, path, {
            'schema': 1, 'run_id': run_id, 'action': action, 'started': _now(),
            'started_epoch': stamp, 'plan': plan,
            'consent': {'source': 'GUI' if consent else '화면 동의 없음(CLI)',
                        'at': _now() if consent else None, 'user': getpass.getuser()},
            'status': 'running', 'stop_requested': False, 'progress': {},
            'reports': [], 'existing_reports': existing, 'review_status': '실행 중',
        })
        record.save()
        return record

    def save(self):
        _write(self.path, self.data)

    def request_stop(self):
        self.data['stop_requested'] = True
        self.save()

    def refresh_progress(self):
        elapsed = max(0, int(time.time() - self.data['started_epoch']))
        progress = dict(self.data.get('progress', {}), elapsed_seconds=elapsed)
        name = 'winupdate_checkpoint.json' if self.data['action'] == 'run-winupdate' else 'regression_state.json'
        path = self.workspace / 'work' / name
        if path.is_file() and path.stat().st_mtime >= self.data['started_epoch']:
            state = _read(path)
            if name.startswith('winupdate'):
                payload = state.get('payload', {})
                stages = payload.get('order', [])
                progress.update(completed=len(stages), total=None,
                                current_tc='최근 완료: ' + (str(stages[-1]) if stages else '준비 중'))
            else:
                progress.update(current_tc=state.get('current_tc', '준비 중'),
                                completed=max(0, int(state.get('index', 1)) - 1), total=state.get('total'))
        live = _read(self.workspace / 'work' / 'qa_progress.json')
        if live.get('run_id') == self.data['run_id']:
            progress.update(current_tc=live.get('current_tc'), total=live.get('total'))
            if self.data['action'] != 'run-winupdate':
                progress['completed'] = max(0, live.get('index', 1) - 1)
        self.data['progress'] = progress
        self.save()
        return progress

    def finish(self, code):
        self.refresh_progress()
        reports = []
        for path in sorted((self.workspace / 'Reports').glob('*')):
            if not path.is_file() or path.suffix.lower() not in {'.json', '.html', '.txt', '.csv', '.xlsx'}:
                continue
            stat = path.stat()
            if stat.st_mtime < self.data['started_epoch']:
                continue
            if self.data['existing_reports'].get(str(path)) == [stat.st_mtime_ns, stat.st_size]:
                continue
            is_wu = 'WindowsUpdate' in path.name
            if is_wu != (self.data['action'] == 'run-winupdate'):
                continue
            reports.append(str(path))
        from .app import completed_report
        # 엔진은 전체 시험을 마쳐도 FAIL TC가 있으면 1을 반환한다.
        primary = completed_report(self.workspace / 'Reports', self.data['action'], int(self.data['started_epoch']))
        complete = bool(primary and str(Path(primary['path'])) in reports)
        status = ('uac_cancelled' if code == 1223 else 'stopped' if self.data['stop_requested'] or code == 130
                  else 'completed' if code in (0, 1) and complete else 'abnormal')
        self.data.update(status=status, exit_code=code, ended=_now(), reports=reports,
                         review_status='자동 실행 완료(검토 전)' if status == 'completed' else '미완료')
        rows = self.result_rows()
        counts = {}
        for row in rows:
            verdict = row.get('verdict', 'UNKNOWN')
            counts[verdict] = counts.get(verdict, 0) + 1
        self.data['verdicts'] = counts
        try:
            from core.result import outcome_summary
            from core.wu_chain import result_from_dict
            self.data['summary'] = outcome_summary([result_from_dict(row) for row in rows])['headline']
        except (KeyError, TypeError, ValueError):
            self.data['summary'] = '보고서의 TC별 판정과 근거를 확인하세요.'
        self.data['next_action'] = ('준비 점검 후 재실행' if status != 'completed' or counts.get('BLOCKED')
                                    else 'TC 상세와 증거를 열어 수동 검토' if self.review_targets()
                                    else '보고서와 증거를 확인하고 검토자 이름으로 검수 완료를 기록하세요.')
        self.save()

    def result_rows(self):
        rows = {}
        for report in self.data['reports']:
            if Path(report).suffix == '.json':
                for row in _read(report).get('results', []):
                    if isinstance(row, dict) and row.get('tc_id'):
                        rows[row['tc_id']] = row
        return list(rows.values())

    def review_targets(self):
        return [row['tc_id'] for row in self.result_rows() if row.get('verdict') != 'PASS']

    def save_review(self, reviewer, entries, *, complete=False):
        allowed = {'확인 완료', '결함 등록', '재시험 필요'}
        if any(not isinstance(entry, dict) or entry.get('result') not in allowed for entry in entries.values()):
            raise ValueError('검토 결과를 선택하세요.')
        if complete and (self.data['status'] != 'completed' or not self.result_rows()
                         or not reviewer.strip() or any(tc not in entries for tc in self.review_targets())):
            raise ValueError('자동 실행 완료·검토자 이름·모든 PASS 아닌 TC의 검토 결과가 필요합니다.')
        status = '검수 완료' if complete else '검토 중'
        _write(self.path.with_name('review.json'), {
            'run_id': self.data['run_id'], 'reviewer': reviewer.strip(), 'updated': _now(),
            'status': status, 'targets': self.review_targets(), 'entries': entries,
        })
        self.data['review_status'] = status
        self.save()


def latest_run(workspace):
    candidates = sorted((Path(workspace) / 'Runs').glob('*/run.json'), reverse=True)
    if not candidates:
        return None
    path = candidates[0]
    data = _read(path)
    return RunRecord(workspace, path, data) if data.get('run_id') == path.parent.name else None


def engine_progress(workspace, run_id, tc_id, index, total):
    if run_id:
        _write(Path(workspace) / 'work' / 'qa_progress.json', {
            'run_id': run_id, 'current_tc': tc_id, 'index': index, 'total': total, 'updated': _now(),
        })
