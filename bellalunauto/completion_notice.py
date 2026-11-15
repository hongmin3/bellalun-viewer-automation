"""무인 실행 결과 창이 자동으로 닫힐 때 Windows 알림 센터에 결과를 남긴다 (REQ-FOLLOWUP-003).

알림은 실행이 끝나고 창을 숨긴 뒤에만 띄운다. 제품을 조작하는 동안 띄우면 Viewer를 가린다.
알림이 실패해도 예외를 밖으로 내보내지 않는다. 결과·리포트 저장과 창 닫기를 막지 않고,
실패 사실은 호출한 쪽이 실행 기록에 남긴다.
"""
from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape

from core.sysinfo import ps_literal

# 등록된 앱 ID가 없는 프로그램도 알림 센터에 남는 알림을 띄울 수 있게 Windows PowerShell의 ID를 쓴다.
POWERSHELL_AUMID = r'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
VERDICT_KEYS = ('PASS', 'FAIL', 'MANUAL', 'SKIP', 'BLOCKED')
TIMEOUT_SECONDS = 20


def verdict_totals(verdicts):
    verdicts = verdicts or {}
    parts = [f'{key} {verdicts.get(key, 0)}' for key in VERDICT_KEYS]
    parts += [f'{key} {value}' for key, value in verdicts.items() if key not in VERDICT_KEYS]
    return ' / '.join(parts)


def primary_report(reports):
    """사람이 여는 HTML 리포트를 우선한다. 없으면 첫 리포트."""
    reports = [str(path) for path in reports or []]
    return next((path for path in reports if Path(path).suffix.lower() == '.html'), reports[0] if reports else None)


def toast_xml(record):
    lines = ('BellalunAuto 체크리스트 실행 완료 · 결과 창 자동 닫힘',
             f"실행 번호 {record.get('run_id', '?')} · {verdict_totals(record.get('verdicts'))}",
             f"리포트: {primary_report(record.get('reports')) or '없음'}")
    texts = ''.join(f'<text>{escape(line)}</text>' for line in lines)
    return f'<toast><visual><binding template="ToastGeneric">{texts}</binding></visual></toast>'


def toast_command(record):
    script = '\n'.join([
        "$ErrorActionPreference='Stop'",
        '[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null',
        '[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null',
        '$xml = New-Object Windows.Data.Xml.Dom.XmlDocument',
        f'$xml.LoadXml({ps_literal(toast_xml(record))})',
        '$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)',
        f"$toast.Tag = {ps_literal(str(record.get('run_id', ''))[:64])}",
        "$toast.Group = 'BellalunAuto'",
        f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier({ps_literal(POWERSHELL_AUMID)}).Show($toast)',
    ])
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    return ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded]


def show(record, *, runner=subprocess.run, timeout=TIMEOUT_SECONDS):
    """알림 결과 `{'status': 'shown'|'failed', 'reason'?, 'at'}`. 예외를 내보내지 않는다."""
    at = datetime.now().astimezone().isoformat(timespec='seconds')
    try:
        result = runner(toast_command(record), stdin=subprocess.DEVNULL, capture_output=True, text=True,
                        encoding='utf-8', errors='replace', timeout=timeout,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        return {'status': 'failed', 'reason': 'timeout', 'at': at}
    except Exception as error:  # noqa: BLE001 - 알림 실패가 결과 저장·창 닫기를 막으면 안 된다.
        return {'status': 'failed', 'reason': type(error).__name__, 'at': at}
    if result.returncode != 0:
        return {'status': 'failed', 'reason': f'exit-{result.returncode}', 'at': at}
    return {'status': 'shown', 'at': at}
