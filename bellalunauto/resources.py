"""설치된 읽기 전용 시험 자료를 PC 설정과 연결한다."""

from copy import deepcopy
from pathlib import Path


#: 사내 배포본에만 넣는 팀 공통 설정(시험 서버·시험 계정). 공개 저장소에는 두지 않는다.
TEAM_SETTINGS = 'team-settings.json'
_DROP_KEYS = {'password', 'token', 'api_key', 'secret', 'accounts', 'login'}
_PLACEHOLDERS = {'', 'REPLACE_ME', None}


def _clean(value):
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()
                if not str(k).startswith('_') and str(k).lower() not in _DROP_KEYS}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _has_value(value):
    if isinstance(value, dict):
        return any(_has_value(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_value(v) for v in value)
    return value not in _PLACEHOLDERS


def team_settings_payload(config):
    """설정에서 팀 공통 값만 뽑는다: `dicom` 서버 값과 Viewer 시험 계정(사용자 결정 2026-11-05).

    그 밖의 비밀 값(token 등)·주석·PC별 경로는 넣지 않는다. 서버 값이 없으면 거부한다.
    """
    dicom = _clean((config or {}).get('dicom') or {})
    if not isinstance(dicom, dict) or not _has_value(dicom):
        raise ValueError('팀 공통 설정에 넣을 DICOM 서버 값이 없습니다.')
    payload = {'dicom': dicom}
    login = ((config or {}).get('viewer') or {}).get('login') or {}
    if isinstance(login, dict) and login.get('id'):
        payload['viewer'] = {'login': {'id': str(login['id']), 'password': str(login.get('password') or '')}}
    return payload


def load_team_settings(resource_dir):
    """배포본의 팀 공통 설정. 없거나 읽을 수 없으면 None. 읽을 때도 같은 규칙으로 다시 거른다."""
    path = Path(resource_dir) / TEAM_SETTINGS
    try:
        if not path.is_file():
            return None
        import json
        return team_settings_payload(json.loads(path.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError):
        return None


def bundled_config(config, resource_dir):
    result = deepcopy(config)
    assets = Path(resource_dir) / 'assets'
    if not assets.is_dir():
        return result
    candidates = {
        'checklist_xlsx': assets/'checklists/Bellalun_Viewer_기본기능_Checklist_개정본.xlsx',
        'winupdate_checklist_xlsx': assets/'checklists/Windows Update 호환성 검증 Checklist_Bellalun Viewer_R-25-782.xlsx',
        'baseline_dir': assets/'Baseline',
        'knowledge_dir': assets/'지식',
    }
    example_paths = {'checklist_xlsx': r'C:\QA\Bellalun_Viewer_Checklist.xlsx'}
    for key, path in candidates.items():
        configured = result.get(key)
        # Explicit operator settings take precedence; examples are not a selection.
        if (not configured or configured == 'REPLACE_ME'
                or configured == example_paths.get(key)):
            result[key] = str(path)
    return result
