"""자정 이후 Today 0건 팝업이 Patient ID 콤보 조작을 막는 결함 재현."""
from types import SimpleNamespace as C
from unittest.mock import patch
import pytest
from core import flows


class Ui:
    DIALOG_OK_IDS=(500,1,2)
    def __init__(self,text='No Result'):
        self.active=True;self.text=text;self.events=[]
        self.popup=C(rect=(840,440,1080,640),hwnd=9)
    def dialog(self): return self.popup if self.active else None
    def dialog_text(self,dialog): return self.text
    def dialog_buttons(self,dialog): return [C(ctrl_id=500)]
    def dismiss_dialog(self,timeout=1): self.events.append('notice dismissed');self.active=False
    def by_id(self,cid): return [C(ctrl_id=cid,visible=True,hwnd=cid,rect=(0,0,100,30))]
    def click(self,control,settle=0):
        assert not self.active,'modal blocks underlying search controls'
        self.events.append(control.ctrl_id)
    def set_text(self,control,text): self.events.append(text)


def test_today_no_result_is_acknowledged_before_month_search():
    ui=Ui()
    with patch('core.combo_popup.wait_items',return_value=[C(ctrl_id=flows.EXAMINED_SEARCH['patient_id_option'])]), \
         patch.object(flows,'examined_cards',return_value=['matching card']):
        result=flows.examined_search(ui,'SYNTHETIC-ID')
    assert result==['matching card']
    assert ui.events[0]=='notice dismissed'
    assert 'SYNTHETIC-ID' in ui.events


def test_unknown_popup_blocks_without_clicking_or_dismissing():
    ui=Ui('Delete this study?')
    with pytest.raises(flows.FlowError,match='안내창'):
        flows.examined_search(ui,'SYNTHETIC-ID')
    assert ui.active
    assert ui.events==[]
