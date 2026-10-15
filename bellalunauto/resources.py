"""설치된 읽기 전용 시험 자료를 PC 설정과 연결한다."""

from copy import deepcopy
from pathlib import Path


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
