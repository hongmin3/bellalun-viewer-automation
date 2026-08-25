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
from unittest import mock

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


class StopOnFailTests(unittest.TestCase):
    """FAIL 이 나면 그 TC 를 즉시 중단하는 정책 (2026-08-24 사용자 지시).

    "어떤 스텝에서 fail 이 났다면 이후 step 을 수행하지 말고 넘어가. 어차피 그
    TC 는 자동화 완료 후 내가 직접 봐야 하는 거니까 전체 자동화 수행할 때 시간이
    길어지는 걸 방지할 수 있을 것 같아."
    """

    def _policy(self, enabled):
        """정책을 이 시험 동안만 바꾼다(끝나면 자동 복원).

        `TCResult.stop_on_fail = ...` 을 직접 쓰지 않는다 —
        `tools_check_module_attrs.py` 가 클래스 속성 대입을 결함 신호로 본다.
        """
        from core.result import TCResult
        patcher = mock.patch.object(TCResult, "stop_on_fail", enabled)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fail_raises_and_later_steps_do_not_run(self):
        from core.result import FAIL, PASS, StepFailed, TCResult
        self._policy(True)
        r = TCResult("TC_TEST", "stop on fail")
        ran = []
        try:
            r.assert_true(1, "첫 단계", True)
            ran.append(1)
            r.assert_true(2, "두 번째 단계", False)   # 여기서 중단
            ran.append(2)
            r.assert_true(3, "세 번째 단계", True)
            ran.append(3)
        except StepFailed as exc:
            self.assertIn("Step 2", str(exc))
        self.assertEqual([1], ran, "FAIL 이후 코드가 계속 실행됐다")
        self.assertEqual([PASS, FAIL], [c.status for c in r.checks])

    def test_disabled_policy_keeps_running(self):
        from core.result import TCResult
        self._policy(False)
        r = TCResult("TC_TEST", "legacy")
        r.assert_true(1, "a", True)
        r.assert_true(2, "b", False)
        r.assert_true(3, "c", True)      # 예전 동작: 계속 수행
        self.assertEqual(3, len(r.checks))

    def test_abort_records_fail_without_raising(self):
        """`abort()` 는 이미 중단된 뒤에 부르므로 다시 예외를 던지면 안 된다."""
        from core.result import FAIL, TCResult
        self._policy(True)
        r = TCResult("TC_TEST", "abort")
        r.abort(0, "TC 진입", RuntimeError("boom"))     # 예외를 던지지 않아야 한다
        self.assertTrue(r.aborted)
        self.assertEqual(FAIL, r.checks[-1].status)
        self.assertIn("RuntimeError: boom", str(r.checks[-1].actual))

    def test_only_first_fail_raises(self):
        """중단 신호는 한 번만. `finally` 안에서 FAIL 을 더 기록해도 죽지 않는다."""
        from core.result import StepFailed, TCResult
        self._policy(True)
        r = TCResult("TC_TEST", "once")
        with self.assertRaises(StepFailed):
            r.assert_true(1, "a", False)
        r.assert_true(2, "정리 중 기록", False)          # 두 번째는 조용히 기록만
        self.assertEqual(2, len(r.checks))

    def test_padding_does_not_raise(self):
        """`run.py::pad_aborted_steps` 가 쓰는 `stop=False` 경로."""
        from core.result import FAIL, TCResult
        self._policy(True)
        r = TCResult("TC_TEST", "padding")
        for step in (3, 4, 5):
            r.add(step, f"Step {step} 미수행", FAIL, stop=False,
                  actual="수행하지 않음")
        self.assertEqual(3, len(r.checks))


class ExcludeRectsTests(unittest.TestCase):
    """`click_viewer_text(exclude_rects=)` 후보 제외 로직.

    20차 회귀에서 `min_y`(콤보 아래만 본다)가 **과교정**으로 드러났다 — 세 번째
    콤보의 드롭다운 항목이 콤보보다 위에 그려져 후보가 0개가 됐다. 그래서 y 로
    자르지 않고 형제 콤보 rect 만 제외한다. 그 판정식을 여기서 고정한다.
    """

    @staticmethod
    def _filter(boxes, exclude):
        def outside(box):
            cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
            return not any(l <= cx <= r and t <= cy <= b
                           for l, t, r, b in exclude)
        return [b for b in boxes if outside(b)]

    def test_sibling_combo_value_is_excluded_but_item_above_survives(self):
        combo_3dn = (900, 200, 1200, 240)      # 이미 같은 값을 표시 중인 형제 콤보
        item_above = (900, 150, 300, 20, 90.0)  # 콤보보다 **위**에 열린 드롭다운 항목
        inside = (1000, 210, 120, 18, 95.0)     # 형제 콤보 안의 표시값
        kept = self._filter([item_above, inside], [combo_3dn])
        self.assertEqual([item_above], kept)

    def test_min_y_would_have_dropped_the_real_item(self):
        """과교정 재현 — y 하한을 쓰면 실제 항목이 사라진다."""
        item_above = (900, 150, 300, 20, 90.0)
        min_y = 240                                   # 콤보 하단
        self.assertEqual([], [b for b in [item_above] if b[1] >= min_y])


class PreconditionGateTests(unittest.TestCase):
    """전제(환경 복원·DICOM 등록)가 실패하면 회귀를 즉시 중단한다.

    2026-08-25 사용자 지시: "전제 준비부터 뻑나면 그냥 바로 전체 회귀를 종료해주라.
    서버들이 정상적으로 등록이 안되면 테스트의 의미가 없어."

    21차 회귀가 그 낭비를 실측으로 보여 줬다 — `DICOM_Server_Setup` 실패 뒤에도
    80분을 더 돌며 19개 TC 를 연쇄 FAIL 로 채웠다.
    """

    PRECONDITIONS = {"AUTOMATION_ENVIRONMENT_RESET", "DICOM_Server_Setup"}

    @staticmethod
    def _result(tc_id, status):
        from core.result import PASS, TCResult
        r = TCResult(tc_id, tc_id)
        r.stop_on_fail = False          # 전제는 첫 실패에서 멈추지 않는다
        r.add(1, "확인", status)
        return r

    def _chain_stops_at(self, statuses):
        """`run.py` 회귀 사슬의 게이트 판정과 같은 로직."""
        ran = []
        for tc_id, status in statuses:
            ran.append(tc_id)
            r = self._result(tc_id, status)
            if tc_id in self.PRECONDITIONS and r.verdict == "FAIL":
                return ran, r
        return ran, None

    def test_setup_failure_stops_the_chain_immediately(self):
        from core.result import FAIL, PASS
        ran, broken = self._chain_stops_at([
            ("AUTOMATION_ENVIRONMENT_RESET", PASS),
            ("DICOM_Server_Setup", FAIL),
            ("TC_Basic_WorkFlow_01", PASS),
        ])
        self.assertIsNotNone(broken)
        self.assertEqual("DICOM_Server_Setup", broken.tc_id)
        self.assertNotIn("TC_Basic_WorkFlow_01", ran,
                         "전제가 깨졌는데 본 시험이 계속 수행됐다")

    def test_normal_tc_failure_does_not_stop_the_chain(self):
        from core.result import FAIL, PASS
        ran, broken = self._chain_stops_at([
            ("AUTOMATION_ENVIRONMENT_RESET", PASS),
            ("DICOM_Server_Setup", PASS),
            ("TC_Basic_WorkFlow_01", FAIL),
            ("TC_Basic_WorkFlow_02", PASS),
        ])
        self.assertIsNone(broken)
        self.assertIn("TC_Basic_WorkFlow_02", ran,
                      "일반 TC 실패는 회귀를 멈추면 안 된다")

    def test_setup_records_every_kind_before_the_gate(self):
        """`setup_all` 은 첫 실패에서 멈추지 않고 세 종류를 다 보고해야 한다."""
        from core.result import FAIL, PASS, TCResult
        r = TCResult("DICOM_Server_Setup", "setup")
        r.stop_on_fail = False
        for kind, status in (("MWL", FAIL), ("Storage", PASS), ("Print", PASS)):
            r.add(1, f"{kind} 설정 화면 준비", status)
        self.assertEqual(3, len(r.checks),
                         "전제 준비가 첫 실패에서 끊기면 어느 서버가 문제인지 "
                         "알 수 없다")
        self.assertEqual("FAIL", r.verdict)


class PasswordFillTests(unittest.TestCase):
    """비밀번호 입력은 **읽을 수 있을 때만** 확인하고 재시도한다.

    2026-08-25 사용자 관찰: "로그인할때 비밀번호를 3번씩 입력하는데 이유가 뭐야?"
    원인은 확인 로직이었다 — 로그인 PW 필드는 password 스타일 `Edit` 이라 다른
    프로세스의 `WM_GETTEXT` 에 **빈 문자열**을 돌려주는데, 그것을 "유실"로 보고
    상한(3회)까지 다시 쳤다. **확인할 수 없는 것을 실패로 단정하면 안 된다.**
    """

    class _FakeUi:
        """`fill_password` 가 쓰는 것만 흉내낸다."""

        PW_TYPE_ATTEMPTS = 3

        def __init__(self, reads):
            self.reads = list(reads)
            self.typed = 0
            self.front_calls = 0

        def require_front(self, what="키 입력"):
            self.front_calls += 1

        def type_text(self, control, text, clear=True, settle=0.3):
            self.typed += 1

        def get_text(self, control):
            return self.reads[min(self.typed - 1, len(self.reads) - 1)]

    def _fill(self, reads, password="1234567"):
        from core.ui import ViewerUi
        fake = self._FakeUi(reads)
        out = ViewerUi.fill_password(fake, object(), password)
        return fake.typed, out

    def test_unreadable_field_types_once_and_does_not_retry(self):
        typed, out = self._fill([""])
        self.assertEqual(1, typed, "읽을 수 없다고 다시 치면 안 된다")
        self.assertIsNone(out["verified"], "확인 불가는 실패가 아니다")

    def test_readable_and_correct_types_once(self):
        typed, out = self._fill(["1234567"])
        self.assertEqual(1, typed)
        self.assertTrue(out["verified"])

    def test_genuine_loss_is_retyped(self):
        """읽히는데 길이가 다르면 **실제 유실**이다 — 그때만 다시 친다."""
        typed, out = self._fill(["12", "1234567"])
        self.assertEqual(2, typed)
        self.assertTrue(out["verified"])

    def test_persistent_loss_reports_failure(self):
        typed, out = self._fill(["12"])
        self.assertEqual(3, typed)
        self.assertFalse(out["verified"])
        self.assertEqual(7, out["expected"])

    def test_requires_viewer_to_be_in_front_before_typing(self):
        """비밀번호를 치기 전에 **최전면인지 확인**해야 한다.

        `keybd_event` 는 창을 지정할 수 없어 그 순간 최전면인 창으로 들어간다.
        2026-08-25 실측: Viewer 가 가려진 상태에서 로그인이 진행돼 계정 ID 가
        **다른 프로그램의 입력란**에 타이핑됐다.
        """
        from core.ui import ViewerUi
        fake = self._FakeUi(["1234567"])
        ViewerUi.fill_password(fake, object(), "1234567")
        self.assertGreaterEqual(fake.front_calls, 1)
