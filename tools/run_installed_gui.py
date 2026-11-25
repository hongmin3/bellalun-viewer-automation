# -*- coding: utf-8 -*-
"""설치판 GUI에서 기본기능·WU 전체를 실행하고 릴리스 게이트 기록을 남긴다 (REQ-DIST-009).

최종 전체 검증은 빌드한 후보를 설치한 뒤, 사람이 쓰는 것과 같은 설치판 실행 화면에서 시작한다.
에이전트가 화면을 조작할 때는 사용자가 이 후보·범위의 실행을 승인한 문구를 `--approval`로 받아
기록에 남긴다. 승인 문구가 없으면 화면을 열지 않는다.

하는 일:
1. 설치 폴더 파일이 build-info와 같은지 대조한다(`run_installed_suites.verify_install`).
2. 바탕화면 바로가기와 같이 인수 없이 설치된 EXE를 연다.
3. 시작 → 준비 점검 → 체크리스트 선택 → 확인 항목·동의 체크 → "동의하고 시작"을 누른다.
4. 실행 기록(`Runs/<실행 번호>/run.json`)이 끝날 때까지 기다리고 결과 화면을 닫는다.
5. 리포트·증거를 모아 `verification.json`을 쓴다. 판정은 `release_gate.py --installed-verification`이 한다.

사용 예:
    python tools/run_installed_gui.py --exe C:/BellalunAuto/BellalunAuto.exe \
        --build-info C:/BellalunAuto/build-info.json --workspace C:/BellalunAuto \
        --out work/gui-1.0.0.009 --suites run-winupdate,run-regression \
        --approval "사용자 승인 원문"
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bellalunauto.runs import GUI_VERIFICATION_RUN_ID, engine_log_path, new_run_id  # noqa: E402
from core.frame_evidence import file_matches, sha256, write_json  # noqa: E402
from tools.run_installed_suites import attach_report, snapshot_files, verify_install  # noqa: E402

#: 공용 화면의 체크리스트 버튼 문구(bellalunauto/frame_launch.TARGETS와 같다).
TARGET_BUTTONS = {'run-regression': '기본기능 체크리스트', 'run-winupdate': 'Windows Update 체크리스트'}
START_LABEL, INSPECT_LABEL, CONSENT_LABEL = '준비 점검 시작', '준비 점검', '동의하고 시작'
HOME_LABEL, CLOSE_LABEL = '처음으로', '닫기'


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def validate_commands(suites):
    commands = [c.strip() for c in suites.split(',') if c.strip()]
    if not commands or len(commands) != len(set(commands)) or not set(commands) <= set(TARGET_BUTTONS):
        raise ValueError('--suites에는 run-regression·run-winupdate만 쉼표로 지정합니다(단독 TC는 run_installed_suites.py)')
    return commands


def read_run_record(path, command, run_id, gui_pid):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if (not isinstance(data, dict)
            or (data.get('run_id'), data.get('action'), data.get('supervisor_pid')) != (run_id, command, gui_pid)):
        raise RuntimeError('GUI 프로세스·명령·회차 번호가 실행 기록과 다릅니다.')
    return data


def find_run_record(workspace, command, run_id, gui_pid):
    engine_log_path(workspace, run_id)  # validate the generated run identifier
    runs = (Path(workspace) / 'Runs').resolve()
    path = runs / run_id / 'run.json'
    if path.resolve().parent.parent != runs:
        raise RuntimeError('GUI 실행 기록은 이 작업 폴더의 Runs 안에 있어야 합니다.')
    return path if read_run_record(path, command, run_id, gui_pid) is not None else None


def collect_gui_result(result, workspace, command, out_dir, record_path):
    """Collect only the artifacts attributed to this completed run by the engine."""
    workspace = Path(workspace)
    data = json.loads(record_path.read_text(encoding='utf-8'))
    run_id = data['run_id']
    result['gui'] = {'run_id': run_id, 'run_record': str(record_path),
                     'run_record_sha256': sha256(record_path), 'consent': data.get('consent'),
                     'status': data.get('status'), 'verdicts': data.get('verdicts'),
                     'supervisor_pid': data.get('supervisor_pid')}
    paths = [record_path]
    events = record_path.with_name('events.jsonl')
    if events.is_file():
        paths.append(events)
    log = engine_log_path(workspace, run_id)
    if log.is_file():
        result.update(log=str(log), log_sha256=sha256(log))
        paths.append(log)
    reports_root = workspace / 'Reports'
    owned_reports = [Path(item) for item in data.get('reports', [])
                     if Path(item).parent == reports_root and Path(item).is_file()]
    paths.extend(owned_reports)
    primary = data.get('primary_report') or {}
    path = Path(primary.get('path', ''))
    report = None
    attach_report(result, command, None)
    if data.get('status') == 'completed' and path in owned_reports and file_matches(path, primary):
        source = json.loads(path.read_text(encoding='utf-8'))
        meta = source.get('meta') or {}
        if meta.get('run_id') == run_id:
            report = {'path': str(path), 'verdicts': data.get('verdicts'),
                      'tc_count': len(source.get('results') or [])}
            attach_report(result, command, report, payload=source)
            result['meta'].update({key: meta[key] for key in (
                'run_id', 'preflight', 'restoration', 'execution_fingerprint',
                'resumed', 'resume_count', 'reused_stages', 'stage_trips', 'checkpoint')
                if key in meta})
            evidence_root = (workspace / 'Evidence').resolve()
            for row in source.get('results', []):
                for item in row.get('evidence') or []:
                    evidence = (workspace / item).resolve()
                    if evidence.is_relative_to(evidence_root) and evidence.is_file():
                        paths.append(evidence)
    result['snapshot'] = snapshot_files(workspace, paths, Path(out_dir) / 'snapshots' / command)
    result['completed'] = bool(report and result.get('log') and result['snapshot']['verified'])
    return result


def drive_one(exe, product, workspace, command, out_dir, *, drive, max_hours, poll, log):
    """GUI 한 회차. 화면 조작 기록과 수집 결과를 돌려준다. 시작하지 못하면 RuntimeError."""
    screens = []

    def step(names, timeout, label):
        found = drive.wait_screen(product, names, timeout)
        if not found:
            raise RuntimeError(f'{label}: 화면 {names}이(가) {timeout}초 안에 뜨지 않았습니다.')
        hwnd, name = found
        screens.append({'time': now(), 'screen': name, 'texts': drive.texts(hwnd)[:40]})
        return hwnd, name

    if drive.frame_windows(product):
        raise RuntimeError(f'{product} 화면이 이미 열려 있습니다. 닫은 뒤 다시 실행하세요.')
    started, started_at = time.time(), now()
    run_id = new_run_id()
    env = {k: v for k, v in os.environ.items() if k not in ('QA_AUTOMATION_UNATTENDED', 'BELLALUN_QA_RUN')}
    env[GUI_VERIFICATION_RUN_ID] = run_id
    process = subprocess.Popen([str(exe)], cwd=str(Path(exe).parent), env=env,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log(f'{command}: GUI 실행(PID {process.pid})')
    hwnd, _ = step(['시작'], 180, '첫 화면')
    drive.click(hwnd, START_LABEL)
    hwnd, _ = step([INSPECT_LABEL], 900, '준비 점검')
    drive.click(hwnd, TARGET_BUTTONS[command], timeout=60)
    hwnd, name = step(['실행 동의', '결과'], 600, '실행 동의')
    if name == '결과':
        raise RuntimeError(f'실행 계획을 만들지 못했습니다: {screens[-1]["texts"]}')
    screens[-1]['checked'] = drive.check_all(hwnd)
    drive.click(hwnd, CONSENT_LABEL)
    hwnd, name = step(['진행', '결과'], 600, '시작')
    if name == '결과':
        raise RuntimeError(f'시험을 시작하지 못했습니다: {screens[-1]["texts"]}')
    record_path = None
    deadline = time.monotonic() + 120
    while record_path is None and time.monotonic() < deadline:
        record_path = find_run_record(workspace, command, run_id, process.pid)
        if record_path is None:
            if process.poll() is not None:
                raise RuntimeError(f'실행 기록을 쓰기 전에 GUI가 종료됐습니다(종료 코드 {process.returncode}).')
            time.sleep(2)
    if record_path is None:
        raise RuntimeError(f'GUI 실행 기록(Runs/{run_id}/run.json)을 찾지 못했습니다.')
    log(f'{command}: 실행 번호 {record_path.parent.name} 시작')
    end = time.monotonic() + max_hours * 3600
    last = None
    while True:
        data = read_run_record(record_path, command, run_id, process.pid)
        if data is not None:
            progress = data.get('progress') or {}
            line = (data.get('status'), progress.get('completed'), progress.get('total'), progress.get('current_tc'))
            if line != last:
                log(f'{command}: 상태 {line[0]} · {line[1]}/{line[2]} · {line[3]}')
                last = line
            if data.get('status') != 'running':
                break
        if process.poll() is not None:
            raise RuntimeError(f'실행이 끝나기 전에 GUI가 종료됐습니다(종료 코드 {process.returncode}).')
        if time.monotonic() >= end:
            raise RuntimeError(f'{max_hours}시간 안에 끝나지 않았습니다. 실행은 계속될 수 있습니다.')
        time.sleep(poll)
    hwnd, _ = step(['결과'], 900, '결과')
    drive.click(hwnd, HOME_LABEL)
    hwnd, _ = step(['시작'], 120, '처음 화면')
    drive.click(hwnd, CLOSE_LABEL)
    closed = True
    try:
        process.wait(180)
    except subprocess.TimeoutExpired:
        closed = False
        log('GUI가 3분 안에 닫히지 않았습니다. 이번 회차의 자료를 모으고 검증을 중단합니다.')
    data = json.loads(record_path.read_text(encoding='utf-8'))
    result = {'command': command, 'args': [str(exe)], 'cwd': str(Path(exe).parent),
              'exit_code': data.get('exit_code'), 'started': started_at, 'ended': now(),
              'minutes': round((time.time() - started) / 60, 1)}
    collect_gui_result(result, workspace, command, out_dir, record_path)
    result['gui'].update(screens=screens, closed=closed)
    result['completed'] = result['completed'] and closed
    return result


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='설치판 GUI 전체 실행과 게이트 기록 (REQ-DIST-009)')
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--build-info', required=True, type=Path)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path, help='비어 있거나 없는 실행 기록 폴더')
    parser.add_argument('--suites', required=True, help='run-regression·run-winupdate를 실행 순서대로 쉼표로')
    parser.add_argument('--approval', required=True, help='이 후보·범위의 실행을 승인한 사용자 문구 원문')
    parser.add_argument('--max-hours', type=float, default=10)
    parser.add_argument('--poll', type=float, default=30)
    args = parser.parse_args(argv)
    try:
        commands = validate_commands(args.suites)
    except ValueError as error:
        parser.error(str(error))
    if not args.approval.strip():
        parser.error('--approval에 사용자 승인 문구를 넣어야 화면을 조작합니다')
    exe, info_path, workspace = args.exe.resolve(), args.build_info.resolve(), args.workspace.resolve()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error(f'실행 기록 폴더가 비어 있지 않습니다: {out}')
    out.mkdir(parents=True, exist_ok=True)
    info = json.loads(info_path.read_text(encoding='utf-8'))
    product = f"BellalunAuto {info.get('version')}"
    verification = {'tool': 'tools/run_installed_gui.py', 'created': now(),
                    'exe': str(exe), 'workspace': str(workspace), 'build_info': str(info_path),
                    'build_info_sha256': sha256(info_path), 'selected_commands': commands,
                    'expected_tcs': [], 'restore_after': True, 'prepared': True,
                    'not_executed': [command for command in TARGET_BUTTONS if command not in commands],
                    'launch': {'mode': 'gui', 'operator': 'agent', 'approval': args.approval,
                               'product_window': product, 'binding': 'run-id'},
                    'install': verify_install(exe, info_path), 'runs': []}
    path = out / 'verification.json'
    log_path = out / 'gui-run.log'

    def save():
        write_json(path, verification)

    def log(message):
        line = f'[{datetime.now():%H:%M:%S}] {message}'
        print(line, flush=True)
        with log_path.open('a', encoding='utf-8') as stream:
            stream.write(line + '\n')

    save()
    if not verification['install']['ok']:
        log('[FAIL] 설치 파일이 build-info와 다릅니다. 화면을 열지 않습니다.')
        return 2
    from core import frame_drive as drive
    for command in commands:
        verification['current'] = command
        save()
        try:
            result = drive_one(exe, product, workspace, command, out, drive=drive,
                               max_hours=args.max_hours, poll=args.poll, log=log)
        except (OSError, RuntimeError, ValueError) as error:
            log(f'[FAIL] {command}: {error}')
            verification['runs'].append({'command': command, 'completed': False, 'error': str(error)})
            save()
            return 1
        verification['runs'].append(result)
        save()
        log(f'{command} 종료: 실행 번호 {result["gui"]["run_id"]} · 판정 {result["gui"]["verdicts"]}')
        if not result['completed']:
            return 1
    verification.pop('current', None)
    verification['finished'] = now()
    save()
    return 0 if all(run.get('completed') for run in verification['runs']) else 1


if __name__ == '__main__':
    sys.exit(main())
