"""Validates: REQ-TCUP-002. 빈 Overlay와 채워진 Overlay가 함께 있는 DB."""
from types import SimpleNamespace
from unittest.mock import patch
from core import setting_lists as lists


class Db:
    def query(self, database, sql, params):
        if params['name'] == 'Empty':
            return [{'OverlayKey':5,'Position':None,'n':0}]
        return [{'OverlayKey':6,'Position':0,'n':2},
                {'OverlayKey':6,'Position':1,'n':2},
                {'OverlayKey':6,'Position':2,'n':2}]


class Ui:
    def __init__(self): self.selected='Empty'
    def by_id(self, cid):
        return [SimpleNamespace(hwnd=cid,ctrl_id=cid,visible=True,text=self.selected,rect=(0,0,100,50))]
    def click(self, row, settle=0): self.selected=row.name


def test_empty_parent_is_complete_using_its_own_db_counts():
    ui=Ui()
    names=[SimpleNamespace(hwnd=i,text='ListItem',visible=True,rect=(0,i*30,100,i*30+30),name=name)
           for i,name in enumerate(('Empty','Filled'))]
    def collect(ui,pane,expected_count=None,**kwargs):
        actual=0 if ui.selected=='Empty' else 2
        return dict(signatures=[f'{pane.ctrl_id}/{n}' for n in range(actual)],
                    details={},steps=0,complete=expected_count==actual,
                    reasons=[] if expected_count==actual else ['wrong expected count'])
    with patch.object(lists,'children',return_value=names), \
         patch.object(lists,'expected_row_count',return_value=6), \
         patch.object(lists,'collect',side_effect=collect):
        result=lists._collect_print_overlay(ui,Db())
    assert result['complete'],result['reasons']
    assert len(result['signatures'])==6


def test_empty_ui_does_not_pass_when_db_has_items():
    ui=Ui();ui.selected='Filled'
    names=[SimpleNamespace(hwnd=1,text='ListItem',visible=True,rect=(0,0,100,30),name='Filled')]
    def collect(ui,pane,expected_count=None,**kwargs):
        return dict(signatures=[],details={},steps=0,complete=expected_count==0,reasons=['missing items'])
    with patch.object(lists,'children',return_value=names), \
         patch.object(lists,'expected_row_count',return_value=6), \
         patch.object(lists,'collect',side_effect=collect):
        result=lists._collect_print_overlay(ui,Db())
    assert not result['complete']
