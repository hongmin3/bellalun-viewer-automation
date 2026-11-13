"""실행 계획·진행·결과·사람 검토. 엔진 판정은 수정하지 않는다."""
from __future__ import annotations

from datetime import datetime
import getpass
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

from core.atomic_metadata import replace_metadata


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
        replace_metadata(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _fingerprint(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


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
        initial_states = {name: _fingerprint(Path(workspace) / 'work' / name)
                          for name in ('regression_state.json',)}
        record = cls(workspace, path, {
            'schema': 1, 'run_id': run_id, 'action': action, 'started': _now(),
            'started_epoch': stamp, 'plan': plan,
            'consent': {'source': 'GUI' if consent else '화면 동의 없음(CLI)',
                        'at': _now() if consent else None, 'user': getpass.getuser()},
            'status': 'running', 'stop_requested': False, 'progress': {},
            'reports': [], 'existing_reports': existing, 'initial_states': initial_states, 'review_status': '실행 중',
        })
        record.save()
        return record

    def save(self):
        _write(self.path, self.data)

    def request_stop(self):
        self.reload()
        if self.data['status'] != 'running':
            return
        self.data['stop_requested'] = True
        self.save()

    def reload(self):
        """감독 프로세스가 쓴 최종 상태를 오래된 GUI 사본보다 우선한다."""
        current = _read(self.path)
        if current.get('run_id') != self.data['run_id']:
            raise ValueError('실행 기록을 다시 읽지 못했습니다. 원본 run.json을 확인하세요.')
        self.data = current
        return self.data

    def refresh_progress(self):
        self.reload()
        if self.data['status'] != 'running':
            return self.data.get('progress', {})
        elapsed = max(0, int(time.time() - self.data['started_epoch']))
        progress = dict(self.data.get('progress', {}), elapsed_seconds=elapsed)
        name = 'regression_state.json'
        path = self.workspace / 'work' / name
        live = _read(self.workspace / 'work' / 'qa_progress.json')
        if live.get('run_id') == self.data['run_id']:
            if type(live.get('index')) is not int:
                raise ValueError('진행 기록의 순번을 읽지 못했습니다.')
            progress.update(current_tc=live.get('current_tc'), total=live.get('total'),
                            completed=max(0, live.get('index', 1) - 1))
        # 구형 기본기능 엔진만 작은 상태 파일로 보완한다. WU 저장점은 읽지 않는다.
        # NTFS의 파일 시각과 time.time()의 세부 정밀도가 달라도 새 기록을 놓치지 않는다.
        # 같은 초에 남은 이전 실행은 시작 전 내용 해시로 배제한다.
        elif (self.data['action'] == 'run-regression' and path.is_file()
                and path.stat().st_mtime >= int(self.data['started_epoch'])
                and _fingerprint(path) != self.data.get('initial_states', {}).get(name)):
            state = _read(path)
            progress.update(current_tc=state.get('current_tc', '준비 중'),
                            completed=max(0, int(state.get('index', 1)) - 1), total=state.get('total'))
        self.data['progress'] = progress
        return progress

    def finish(self, code):
        self.reload()
        if self.data['status'] != 'running':
            return
        self.refresh_progress()
        reports = []
        report_stamps = {}
        for path in sorted((self.workspace / 'Reports').glob('*')):
            if not path.is_file() or path.suffix.lower() not in {'.json', '.html', '.txt', '.csv', '.xlsx'}:
                continue
            stat = path.stat()
            if stat.st_mtime < int(self.data['started_epoch']):
                continue
            if self.data['existing_reports'].get(str(path)) == [stat.st_mtime_ns, stat.st_size]:
                continue
            is_wu = 'WindowsUpdate' in path.name
            if is_wu != (self.data['action'] == 'run-winupdate'):
                continue
            reports.append(str(path))
            report_stamps[str(path)] = stat.st_mtime_ns
        from .app import completed_report
        # 엔진은 전체 시험을 마쳐도 FAIL TC가 있으면 1을 반환한다.
        primary = completed_report(self.workspace / 'Reports', self.data['action'], int(self.data['started_epoch']))
        complete = bool(primary and str(Path(primary['path'])) in reports)
        if primary:
            report_meta = (_read(primary['path']).get('meta') or {})
            if report_meta.get('run_id') not in (None, self.data['run_id']):
                complete = False
        # 정리 실패로 chain_completed=False가 된 보고서도 복원 사유는 보존한다.
        # 이 경로는 완료 판정을 바꾸지 않고 현재 실행의 메타데이터만 읽는다.
        for report in sorted(reports, key=lambda path: report_stamps[path], reverse=True):
            if Path(report).suffix.lower() != '.json':
                continue
            report_meta = (_read(report).get('meta') or {})
            if not isinstance(report_meta, dict) or report_meta.get('run_id') != self.data['run_id']:
                continue
            if 'restoration' in report_meta:
                self.data['restoration'] = report_meta['restoration']
                self.data['restoration_report'] = report
            if 'execution_fingerprint' in report_meta:
                self.data['execution_fingerprint'] = report_meta['execution_fingerprint']
            break
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
        self.reload()
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
