"""Validates: REQ-TCUP-003. 줄 분리 전후를 실제 크롭 경로에서 확인."""
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image, ImageDraw
from core import image_overlay


def test_panel_reads_small_text_lines_without_weakening_patient_match(tmp_path):
    panel = Image.new('RGB', (600,600), 'black')
    draw = ImageDraw.Draw(panel)
    draw.text((330,65), 'ID: DATA_FLOW_MWL_01', fill='white')
    draw.text((330,86), 'Birth Date: 1980/01/01', fill='white')
    def ocr(image, tess, **kwargs):
        # OCR 엔진 경계: 전체 크롭에서는 못 읽고 분리된 줄에서만 읽는 경우.
        return {'read': 'ID: DATA_FLOW_MWL_01'} if image.height < 40 else {'read': ''}
    with patch.object(image_overlay.ImageGrab, 'grab', return_value=panel), \
         patch.object(image_overlay.uitext, 'read_overlay_text', side_effect=ocr):
        reads = image_overlay.read_panel(SimpleNamespace(rect=(0,0,600,600)),
                                        str(tmp_path/'panel.png'), None)
    assert image_overlay.hits(reads, {'PatientID':'DATA_FLOW_MWL_01'})['_pid_match'] == 'exact'
    assert (tmp_path/'panel_top.png').exists()
    assert list(tmp_path.glob('panel_top_line*.png'))


def test_blank_panel_does_not_invent_patient_id(tmp_path):
    with patch.object(image_overlay.ImageGrab, 'grab', return_value=Image.new('RGB',(600,600))), \
         patch.object(image_overlay.uitext, 'read_overlay_text', return_value={'read':''}):
        reads = image_overlay.read_panel(SimpleNamespace(rect=(0,0,600,600)),str(tmp_path/'p.png'),None)
    assert image_overlay.hits(reads, {'PatientID':'DATA_FLOW_MWL_01'})['Patient ID'] is False


def test_ocr_error_is_evidence_but_never_displayed_overlay():
    reads = {'error':'<ocr err ID: DATA_FLOW_MWL_01 19800101 28 kVp 32 mAs LCC (3D-N)>'}
    hits = image_overlay.hits(reads, {'PatientID':'DATA_FLOW_MWL_01','PatientBirthDate':'19800101'})
    assert hits['Patient ID'] is False
    assert hits['Birth Date'] is False
    assert image_overlay.dose_state(reads) == {'Dose kVp':'none','Dose mAs':'none'}
    assert image_overlay.panel_kind(reads) != '3D'


def test_bright_image_left_of_overlay_does_not_swallow_text_line():
    panel = Image.new('RGB',(600,180),'black')
    draw = ImageDraw.Draw(panel)
    draw.rectangle((0,0,90,179),fill='white')
    draw.text((330,65),'ID: DATA_FLOW_MWL_01',fill='white')
    lines = image_overlay._text_lines(panel)
    assert len(lines) >= 1
    assert any(line.height < 40 for line in lines)
