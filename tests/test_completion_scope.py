"""단독 결과를 전체 회귀 완료로 오인하지 않도록 표시 범위를 검사한다."""
import run


def test_single_completion_uses_its_own_scope(capsys,monkeypatch):
    monkeypatch.setenv('BELLALUN_EXTERNAL_GUARD','1')
    run.announce_done([],0,{},label='단독 시험')
    output=capsys.readouterr().out
    assert '단독 시험 완료' in output
    assert '전체 회귀 완료' not in output
