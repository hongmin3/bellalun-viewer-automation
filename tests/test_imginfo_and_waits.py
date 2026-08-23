# -*- coding: utf-8 -*-
r"""`core/imginfo.py` 와 조건 기반 촬영 대기의 단위 시험.

UI 도, 제품도, 관리자 권한도 필요 없다. `TC_XIPL_compatibility_07` 의 판정은
이 두 조각에 기대고 있어서, 회귀를 돌리지 못하는 환경에서도 **여기까지는**
실제로 검증할 수 있어야 한다.

실행: `python -m unittest discover -s tests -p "test_*.py"`

`.img` 표본은 실제 제품 파일에서 확인한 구조를 그대로 재현한다
(2026-08-24 실측: `C:\BellalunData\Image\Study48_.../Image81.img`).
"""

import os
import tempfile
import unittest

from core import imginfo
from core import viewer_processing as vp

#: 실제 제품 파일에서 그대로 옮긴 `<INFORMATION>` 골격(3D-Narrow).
SAMPLE_XML = (
    '<?xml version="1.0"?>\n'
    "<INFORMATION>"
    '<PATIENT_INFO Version="0"><Patient Key="48" ID="DATA_FLOW_MWL_01" '
    'Name="AUTO^MWL^^^" BirthDate="19800101" Sex="F" Comments=""/>'
    "</PATIENT_INFO>"
    '<STUDY_INFO Version="0"><Study Key="48" Type="0" Date="20260821"/>'
    "</STUDY_INFO>"
    '<SERIES_INFO Version="0"><Series Key="54" Number="2"/></SERIES_INFO>'
    '<INSTANCE_GROUP_INFO Version="0">'
    '<InstanceGroup Key="54" ExposureType="1" ExposureMode="1" StereoType="0"/>'
    '<ViewPosition Name="CC" Type="1" Alias="" Code="R-10242" Laterality="1"/>'
    '<ReconParam EgpName="narrow_standard.egp" EapName="common_standard.eap" '
    'XtpName="TEST_3D_NARROW.xtp" PostBackgroundMasking="0" PostContrast="14" '
    'PostDetailEnhancement="16" PostBrightness="14" PostToneType="15" '
    'S2DBackgroundMasking="0" S2DContrast="6" S2DDetailEnhancement="14" '
    'S2DBrightness="6" S2DTonetype="15"/>'
    "</INSTANCE_GROUP_INFO>"
    '<INSTANCE_INFO Version="0"><Instance Key="81" InstanceType="2"/>'
    "</INSTANCE_INFO>"
    "</INFORMATION>"
)


def write_sample(path, xml=SAMPLE_XML, payload=b"", trailer=b""):
    """제품과 같은 배치로 표본을 만든다 — 이진 앞부분 + UTF-16LE XML 꼬리."""
    with open(path, "wb") as stream:
        stream.write(b"\x00\x00BELLALUN\x00IMG\x00")
        stream.write(payload)
        stream.write(xml.encode("utf-16-le"))
        stream.write(trailer)


class ImgInfoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_reads_recon_param_from_tail(self):
        path = os.path.join(self.tmp.name, "Image81.img")
        write_sample(path, payload=os.urandom(200000))
        recon = imginfo.recon_param(path)
        self.assertEqual("TEST_3D_NARROW.xtp", recon["XtpName"])
        self.assertEqual("narrow_standard.egp", recon["EgpName"])
        self.assertEqual("14", recon["PostContrast"])

    def test_sections_expose_mode_and_view_position(self):
        path = os.path.join(self.tmp.name, "Image81.img")
        write_sample(path)
        sections = imginfo.sections(path)
        self.assertEqual("1", sections["instance_group"]["ExposureMode"])
        self.assertEqual("CC", sections["view_position"]["Name"])
        self.assertEqual("1", sections["view_position"]["Type"])
        self.assertEqual("DATA_FLOW_MWL_01", sections["patient"]["ID"])

    def test_only_the_tail_is_read(self):
        """`tail_bytes` 밖에 있는 XML 은 읽지 않는다.

        3D Raw 는 700MB 를 넘으므로 전체를 읽으면 회귀가 그것만으로 수십 초를
        쓴다. 꼬리만 읽는다는 것이 성능 전제라서 시험으로 고정한다.
        """
        path = os.path.join(self.tmp.name, "Image80.img")
        write_sample(path, payload=b"\x00" * 5000)
        with self.assertRaises(imginfo.ImgInfoError):
            imginfo.read_information(path, tail_bytes=64)
        # 넉넉히 주면 읽힌다.
        self.assertIn("ReconParam", imginfo.read_information(path))

    def test_missing_and_malformed_raise(self):
        with self.assertRaises(imginfo.ImgInfoError):
            imginfo.read_information(os.path.join(self.tmp.name, "없다.img"))
        broken = os.path.join(self.tmp.name, "broken.img")
        with open(broken, "wb") as stream:
            stream.write(b"not a bellalun image at all")
        with self.assertRaises(imginfo.ImgInfoError):
            imginfo.read_information(broken)

    def test_truncated_xml_raises_instead_of_returning_partial(self):
        path = os.path.join(self.tmp.name, "cut.img")
        write_sample(path, xml=SAMPLE_XML.replace("</INFORMATION>", ""))
        with self.assertRaises(imginfo.ImgInfoError):
            imginfo.sections(path)

    def test_study_dirs_prefer_newest_and_match_exact_key(self):
        root = os.path.join(self.tmp.name, "Image")
        for name in ("Study48_20260819_090000", "Study48_20260821_145346",
                     "Study480_20260821_150000", "Study4_20260821_150000"):
            os.makedirs(os.path.join(root, name))
        dirs = imginfo.study_image_dirs(self.tmp.name, 48)
        self.assertEqual(2, len(dirs), dirs)
        self.assertTrue(dirs[0].endswith("Study48_20260821_145346"))
        # `Study480_` 이 `Study48` 로 잘못 잡히면 다른 검사의 영상을 읽는다.
        self.assertFalse(any("Study480_" in d for d in dirs))

    def test_instance_path_found_in_newest_folder(self):
        root = os.path.join(self.tmp.name, "Image")
        old = os.path.join(root, "Study48_20260819_090000")
        new = os.path.join(root, "Study48_20260821_145346")
        os.makedirs(old)
        os.makedirs(new)
        write_sample(os.path.join(new, "Image81.img"))
        found = imginfo.instance_image_path(self.tmp.name, 48, 81)
        self.assertTrue(found.startswith(new), found)
        self.assertIsNone(imginfo.instance_image_path(self.tmp.name, 48, 999))
        self.assertEqual([], imginfo.study_image_dirs(self.tmp.name, 77))


class _FakeDb:
    """`wait_new_group` 이 쓰는 조회 두 개만 흉내낸다.

    `steps` 는 호출 회차별로 돌려줄 (그룹 목록, 인스턴스 목록) 이다. 마지막
    항목은 그 뒤로 계속 유지된다(타임아웃 경로 시험용).
    """

    def __init__(self, steps):
        self.steps = steps
        self.calls = 0

    def _state(self):
        index = min(self.calls, len(self.steps) - 1)
        return self.steps[index]

    def query(self, database, sql, params=None):
        if "INSTANCE_GROUP" in sql:
            groups, _ = self._state()
            self.calls += 1
            return groups
        _, instances = self._state()
        return instances


class WaitNewGroupTests(unittest.TestCase):
    GROUP_2D = {"Key": 53, "Type": 0, "ExposureMode": 0}
    GROUP_3D = {"Key": 54, "Type": 1, "ExposureMode": 1}
    FULL_3D = [{"Key": 80, "InstanceType": 1}, {"Key": 81, "InstanceType": 2},
               {"Key": 82, "InstanceType": 3}]

    def test_returns_as_soon_as_all_types_arrive(self):
        db = _FakeDb([
            ([self.GROUP_2D], []),                              # 아직 없음
            ([self.GROUP_2D, self.GROUP_3D], self.FULL_3D[:1]),  # Raw 만
            ([self.GROUP_2D, self.GROUP_3D], self.FULL_3D),      # 전부
        ])
        out = vp.wait_new_group(db, 48, known_keys=[53], timeout=10, poll=0)
        self.assertFalse(out["timed_out"])
        self.assertEqual(54, int(out["group"]["Key"]))
        self.assertEqual(3, len(out["instances"]))

    def test_partial_arrival_times_out_and_reports_what_it_saw(self):
        """Raw 만 들어오고 Recon/Syn 이 없으면 **성공으로 보지 않는다.**

        고정 대기를 조건 대기로 바꿀 때 가장 위험한 실수는 "새 그룹이 생겼다"
        만으로 통과시키는 것이다. 그러면 Reconstruction 실패가 PASS 가 된다.
        """
        db = _FakeDb([([self.GROUP_2D, self.GROUP_3D], self.FULL_3D[:1])])
        out = vp.wait_new_group(db, 48, known_keys=[53], timeout=0, poll=0)
        self.assertTrue(out["timed_out"])
        self.assertEqual(54, int(out["group"]["Key"]))
        self.assertEqual([1], [int(x["InstanceType"]) for x in out["instances"]])

    def test_existing_groups_are_never_mistaken_for_new_ones(self):
        db = _FakeDb([([self.GROUP_2D, self.GROUP_3D], self.FULL_3D)])
        out = vp.wait_new_group(db, 48, known_keys=[53, 54], timeout=0, poll=0)
        self.assertTrue(out["timed_out"])
        self.assertIsNone(out["group"])

    def test_2d_acquisition_only_needs_type_zero(self):
        db = _FakeDb([([self.GROUP_2D], [{"Key": 79, "InstanceType": 0}])])
        out = vp.wait_new_group(db, 48, known_keys=[],
                               required_types=vp.INSTANCE_TYPES_2D,
                               timeout=10, poll=0)
        self.assertFalse(out["timed_out"])
        self.assertEqual(53, int(out["group"]["Key"]))


class TestParameterNamingTests(unittest.TestCase):
    def test_3d_test_parameters_are_registered_and_distinguishable(self):
        self.assertIn(vp.PARAM_3D_NARROW, vp.TEST_PARAMETER_FILES)
        self.assertIn(vp.PARAM_3D_WIDE, vp.TEST_PARAMETER_FILES)
        self.assertNotEqual(vp.PARAM_3D_NARROW, vp.PARAM_3D_WIDE)
        # 콤보 항목은 OCR 로 고른다. 한 글자만 다르면 반대쪽을 고를 수 있다.
        narrow = set(vp.PARAM_3D_NARROW.replace(".xtp", ""))
        wide = set(vp.PARAM_3D_WIDE.replace(".xtp", ""))
        self.assertGreaterEqual(len(narrow ^ wide), 3,
                                "두 이름이 너무 비슷해 OCR 오독 위험이 있다")
        for name in (vp.PARAM_3D_NARROW, vp.PARAM_3D_WIDE):
            self.assertTrue(name.startswith("TEST_"),
                            "reset_parameter_copies 가 지우는 접두사여야 한다")
            self.assertTrue(name.endswith(".xtp"))


if __name__ == "__main__":
    unittest.main()
