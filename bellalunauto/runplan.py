"""조회 전용 실행 계획. 이 모듈은 DB·서비스·화면·USB를 변경하지 않는다."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from bellalunauto.resources import bundled_config
from core.dbreset import APP_PROCESSES, APP_SERVICES, DATABASES, source_dir
from core.usb_paths import EXPORT_FOLDER
from core.source_identity import source_identity, execution_fingerprint


def _digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), default=str).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _redacted_config(value):
    """비밀 값은 해시 입력에도 넣지 않는다. 그 밖의 실행 설정은 모두 비교한다."""
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            name = str(key).lower().replace('-', '_')
            if any(secret in name for secret in ('password', 'passwd', 'secret', 'token',
                                                  'credential', 'api_key', 'authorization',
                                                  'cookie', 'private_key', 'connection_string')) or name == 'pwd':
                continue
            redacted[key] = _redacted_config(item)
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redacted_config(item) for item in value]
    return value


def _source_content_identity(root):
    """같은 dirty 상태 안에서 달라진 실행 소스도 구별한다. 원문은 노출하지 않는다."""
    root = Path(root)
    candidates = [root / 'run.py', root / 'build-info.json', root.parent / 'build-info.json']
    for folder in ('core', 'bellalunauto', 'tests'):
        candidates.extend((root / folder).rglob('*.py'))
    rows = []
    for path in sorted(set(candidates)):
        if not path.is_file():
            continue
        try:
            with path.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            rows.append((str(path.relative_to(root)) if path.is_relative_to(root) else '../build-info.json', digest))
        except OSError:
            rows.append((path.name, 'unreadable'))
    return _digest(rows) if rows else None


def _backup_identity(path, database):
    row = {'database': database, 'path': str(path), 'status': 'missing',
           'modified_at': None, 'sha256': None}
    try:
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
            details = path.stat()
        row.update(status='available', sha256=digest,
                   modified_at=datetime.fromtimestamp(details.st_mtime, timezone.utc).isoformat())
    except FileNotFoundError:
        pass
    except OSError:
        row['status'] = 'unreadable'
    return row


def build_plan(layout, config, action):
    """실제 선택 경로의 자료와 설정을 읽어 JSON으로 저장 가능한 계획을 만든다.

    파일 날짜는 UTC, sha256은 실제 파일 전체의 해시다. 누락/조회 실패는
    확인 불가로 남긴다. 실행 허용 여부는 기존 환경 gate가 판단한다.
    """
    labels = {'run-regression': '기본기능 체크리스트 자동화 수행',
              'run-wu09': 'USB Export/Import 단독 수행',
              'run-winupdate': 'Windows Update 체크리스트 자동화 수행'}
    if action not in labels:
        raise ValueError('실행 계획은 기본기능 전체 또는 Windows Update 전체에만 제공됩니다.')
    cfg = bundled_config(config, layout.resource_dir)
    baseline = Path(source_dir(SimpleNamespace(cfg=cfg, root=str(layout.workspace))))
    asset_version = None
    try:
        manifest = json.loads((Path(layout.resource_dir) / 'assets-manifest.json').read_text(encoding='utf-8-sig'))
        if isinstance(manifest, dict):
            asset_version = manifest.get('asset_version')
    except (OSError, ValueError):
        pass
    viewer = (cfg.get('viewer') or {}).get('exe', '')
    version = None
    if viewer:
        from core.sysinfo import file_version
        try:
            version = file_version(viewer)
        except (OSError, ValueError):
            pass
    display = cfg.get('display') or {}
    plan = {
        'action': action, 'label': labels[action],
        'viewer': {'path': viewer, 'version': version},
        'sql': {'instance': cfg.get('sql_server', '.\\BELLALUN'),
                'service': cfg.get('sql_service_name', 'MSSQL$BELLALUN')},
        'databases': list(DATABASES),
        'baseline': {'path': str(baseline), 'asset_version': asset_version,
                     'files': [_backup_identity(baseline / (db + '.bak'), db) for db in DATABASES]},
        'changes': {
            'database': 'DB 4개를 Baseline으로 복원합니다. 기존 DB 내용이 덮어써집니다.',
            'sql_service': 'SQL 서비스가 수동/사용 안 함이면 AUTO_START로 바꾸고 중지 상태면 시작합니다.',
            'app_services': list(APP_SERVICES), 'processes': list(APP_PROCESSES),
            'display': {'width': int(display.get('width', 1920)),
                        'height': int(display.get('height', 1080)),
                        'enforce': bool(display.get('enforce', True))},
            'xipl': {'path': (cfg.get('xipl') or {}).get('parameter_dir', r'C:\XIPL\PARAMETER'),
                     'policy': ('TEST_* 시험 파라미터를 삭제 후 재생성합니다.'
                                if action == 'run-regression' else
                                'XIPL TC에서 필요한 TEST_* 시험 파라미터 사본을 준비합니다.')},
            'dicom': 'MWL/Storage/Print DICOM 서버를 Viewer에 등록하고 연결합니다.',
            'usb': {'enabled': action in {'run-winupdate', 'run-wu09'}, 'folder': EXPORT_FOLDER,
                    'policy': f'선택 USB의 {EXPORT_FOLDER} 폴더에 있는 기존 파일을 삭제한 뒤 내보내기/가져오기에 사용합니다.'},
        },
        'recovery_policy': [
            'TC가 바꾼 Viewer 설정은 TC 끝에 되돌리고 복구 결과를 기록합니다.',
            '원상복원을 선택하지 않으면 DB는 실행 전 상태로 되돌리지 않고 다음 실행 시작 때 Baseline으로 다시 복원합니다. 선택하면 검증된 사전 DB 사본으로 복원합니다.',
            'DICOM 서버 등록·해상도는 되돌리지 않습니다.',
            'Bellalun Service는 DB 복원 후 다시 시작합니다. SQL 서비스 시작 유형·시작 상태는 되돌리지 않습니다.',
            f'원상복원을 선택하지 않으면 USB {EXPORT_FOLDER}에서 삭제한 기존 파일은 복구하지 않습니다. 선택하면 검증된 사전 사본으로 복원합니다.',
        ],
    }
    viewer_file = _backup_identity(Path(viewer), 'Viewer') if viewer else {
        'status': 'missing', 'sha256': None}
    plan['viewer'].update(status=viewer_file['status'], sha256=viewer_file['sha256'])
    plan['config_fingerprint'] = _digest(_redacted_config(cfg))
    plan['source_identity'] = source_identity(layout.resource_dir)
    plan['source_fingerprint'] = _source_content_identity(layout.resource_dir)
    plan['plan_id'] = _digest({
        'action': action, 'config_fingerprint': plan['config_fingerprint'],
        'viewer': plan['viewer'], 'source_identity': plan['source_identity'],
        'source_fingerprint': plan['source_fingerprint'],
        'baseline': {'path': plan['baseline']['path'], 'asset_version': asset_version,
                     'files': [{key: row[key] for key in ('database', 'path', 'status', 'sha256')}
                               for row in plan['baseline']['files']]},
    })
    plan['execution_fingerprint'] = execution_fingerprint(plan['plan_id'])
    return plan


def format_plan(plan):
    """동의 화면과 실행 기록에 같은 대상·변경·복구 정책을 표시한다."""
    baseline, changes = plan['baseline'], plan['changes']
    lines = [f"실행 전 확인: {plan['label']}",
             f"Viewer: {plan['viewer']['path'] or '확인 불가'} · 버전: {plan['viewer']['version'] or '확인 불가'}",
             f"SQL 인스턴스: {plan['sql']['instance']} · 서비스: {plan['sql']['service']}",
             '복원 DB: ' + ', '.join(plan['databases']),
             f"Baseline: {baseline['path']}",
             f"배포 자료 판(asset_version): {baseline['asset_version'] or '확인 불가'}"]
    for row in baseline['files']:
        status = {'missing': '파일 없음', 'unreadable': '읽기 실패'}.get(row['status'], '')
        lines.append(f"  {row['database']}.bak: 날짜(UTC) {row['modified_at'] or '확인 불가'} · "
                     f"SHA-256 {(row['sha256'] or '')[:12] or '확인 불가'} {status}".rstrip())
    screen = changes['display']
    lines.extend(['', '바뀌는 것:', changes['database'], changes['sql_service'],
                  '제품 서비스 중지·시작: ' + ', '.join(changes['app_services']),
                  '관련 프로세스 종료: ' + ', '.join(changes['processes']),
                  f"해상도: {screen['width']}x{screen['height']} · " + ('강제 설정' if screen['enforce'] else '조회만(강제 설정 꺼짐)'),
                  f"XIPL: {changes['xipl']['path']} · {changes['xipl']['policy']}", changes['dicom'],
                  'WU USB: ' + (changes['usb']['policy'] if changes['usb']['enabled'] else '이번 실행에서는 사용하지 않습니다.'),
                  '', '복구 정책:', *plan['recovery_policy'], '',
                  '이번 실행에서 원상복원을 선택하면 검증된 사전 사본으로 DB·파일을 복원하고 대조합니다.',
                  '복원을 선택하지 않으면 사전 사본만 보관하고 시험 후 상태를 유지합니다.',
                  'UAC 승인은 위 변경 동의를 대신하지 않습니다.'])
    return '\n'.join(lines)
