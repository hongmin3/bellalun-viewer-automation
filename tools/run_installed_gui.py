# -*- coding: utf-8 -*-
"""설치판 GUI에서 기본기능·WU 전체를 실행하고 릴리스 게이트 기록을 남긴다 (REQ-DIST-008).

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

from tools.run_installed_suites import collect_result, sha256, verify_install  # noqa: E402

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


def find_run_record(workspace, command, since):
    """`since` 뒤 GUI가 만든 이 명령의 실행 기록 경로. 없으면 None."""
    runs = Path(workspace) / 'Runs'
    found = []
    for path in runs.glob('*/run.json') if runs.is_dir() else ():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if data.get('action') == command and float(data.get('started_epoch') or 0) >= since - 5:
            found.append((float(data['started_epoch']), path))
    return max(found)[1] if found else None


def latest_log(workspace, since):
    logs = [p for p in (Path(workspace) / 'Log').glob('BellalunAuto-*.log') if p.stat().st_mtime >= since - 5]
    return max(logs, key=lambda p: p.stat().st_mtime) if logs else None


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
    env = {k: v for k, v in os.environ.items() if k != 'QA_AUTOMATION_UNATTENDED'}
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
    deadline = time.time() + 120
    while record_path is None and time.time() < deadline:
        record_path = find_run_record(workspace, command, started)
        time.sleep(2)
    if record_path is None:
        raise RuntimeError('GUI가 시작한 실행 기록(Runs/*/run.json)을 찾지 못했습니다.')
    log(f'{command}: 실행 번호 {record_path.parent.name} 시작')
    end = time.time() + max_hours * 3600
    last = None
    while True:
        data = json.loads(record_path.read_text(encoding='utf-8'))
        progress = data.get('progress') or {}
        line = (data.get('status'), progress.get('completed'), progress.get('total'), progress.get('current_tc'))
        if line != last:
            log(f'{command}: 상태 {line[0]} · {line[1]}/{line[2]} · {line[3]}')
            last = line
        if data.get('status') != 'running':
            break
        if process.poll() is not None:
            raise RuntimeError(f'실행이 끝나기 전에 GUI가 종료됐습니다(종료 코드 {process.returncode}).')
        if time.time() >= end:
            raise RuntimeError(f'{max_hours}시간 안에 끝나지 않았습니다. 실행은 계속될 수 있습니다.')
        time.sleep(poll)
    hwnd, _ = step(['결과'], 900, '결과')
    drive.click(hwnd, HOME_LABEL)
    hwnd, _ = step(['시작'], 120, '처음 화면')
    drive.click(hwnd, CLOSE_LABEL)
    try:
        process.wait(180)
    except subprocess.TimeoutExpired:
        log('GUI가 3분 안에 닫히지 않았습니다. 결과는 그대로 모읍니다.')
    data = json.loads(record_path.read_text(encoding='utf-8'))
    result = {'command': command, 'args': [str(exe)], 'cwd': str(Path(exe).parent),
              'exit_code': data.get('exit_code'), 'started': started_at, 'ended': now(),
              'minutes': round((time.time() - started) / 60, 1)}
    engine_log = latest_log(workspace, started)
    if engine_log:
        result.update(log=str(engine_log), log_sha256=sha256(engine_log))
    collect_result(result, workspace, command, out_dir, started)
    result['gui'] = {'run_id': data.get('run_id'), 'run_record': str(record_path),
                     'run_record_sha256': sha256(record_path), 'consent': data.get('consent'),
                     'status': data.get('status'), 'verdicts': data.get('verdicts'), 'screens': screens}
    return result


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='설치판 GUI 전체 실행과 게이트 기록 (REQ-DIST-008)')
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
                    'launch': {'mode': 'gui', 'operator': 'agent', 'approval': args.approval,
                               'product_window': product},
                    'install': verify_install(exe, info_path), 'runs': []}
    path = out / 'verification.json'
    log_path = out / 'gui-run.log'

    def save():
        path.write_text(json.dumps(verification, ensure_ascii=False, indent=1), encoding='utf-8')

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
        except RuntimeError as error:
            log(f'[FAIL] {command}: {error}')
            verification['runs'].append({'command': command, 'completed': False, 'error': str(error)})
            save()
            return 1
        verification['runs'].append(result)
        save()
        log(f'{command} 종료: 실행 번호 {result["gui"]["run_id"]} · 판정 {result["gui"]["verdicts"]}')
    verification.pop('current', None)
    verification['finished'] = now()
    save()
    return 0 if all(run.get('completed') for run in verification['runs']) else 1


if __name__ == '__main__':
    sys.exit(main())
