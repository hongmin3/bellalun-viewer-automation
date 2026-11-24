"""공용 화면 조작기가 창 제목으로 단계를 읽는 규칙 (frame/FRAME.md 2.7).

Validates: REQ-DIST-009
창을 띄우거나 제품을 조작하지 않는다.
"""
from core import frame_drive as drive
from core.frame_ui import STEPS


def test_screen_is_read_from_product_title():
    for step in STEPS:
        assert drive.screen_of(f'BellalunAuto 1.0.0.009 · {step}', 'BellalunAuto 1.0.0.009') == step


def test_other_product_version_or_unknown_step_is_ignored():
    assert drive.screen_of('BellalunAuto 1.0.0.008 · 시작', 'BellalunAuto 1.0.0.009') is None
    assert drive.screen_of('VXvueAuto 2.0 · 시작', 'BellalunAuto 1.0.0.009') is None
    assert drive.screen_of('BellalunAuto 1.0.0.009 · 설정', 'BellalunAuto 1.0.0.009') is None
    assert drive.screen_of('', 'BellalunAuto 1.0.0.009') is None


def test_driver_does_not_change_shared_ctypes_windll():
    """공용 ctypes.windll.user32의 함수 형식을 바꾸지 않는다(tools/wu_selfcheck.py c항)."""
    source = open(drive.__file__, encoding='utf-8').read()
    assert 'windll.user32' not in source
