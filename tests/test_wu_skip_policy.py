# -*- coding: utf-8 -*-
"""SKIP 과 최종 판정의 관계 (REQ-WU-003, TEST-WU-003).

WU_09 는 CD 단계를 늘 SKIP 하고, USB 는 연결 여부에 따라 수행하거나 SKIP 한다.
USB 있음/없음/오류 × CD SKIP 조합의 최종 판정을 표시 정책별로 고정한다.
`--from-regression` 변환도 같은 함수를 지나므로 같은 규칙이 적용되는지 함께 본다.
"""
import unittest
from unittest.mock import patch

from core.result import TCResult, PASS, FAIL, MANUAL, SKIP
from tests import winupdate

WF09 = {"tc_id": "TC_Basic_WorkFlow_09", "verdict": "PASS",
        "checks": [{"step": 1, "title": "Export", "status": "PASS",
                    "expected": "", "actual": "", "note": ""}]}

USB_PASS = {
    "drive": "E:\\", "export": {"files": ["E:\\BellalunWU09\\a.img"], "inventory": []},
    "import": {"rows": 1, "imported_clicked": True, "closed": True,
               "evidence": {"before": {}, "after": {}, "completion": {}, "examined": {}}},
}
USB_ABSENT = {"drive": None}
USB_ERROR = {"drive": "E:\\", "error": "synthetic export error"}


def _no_sysinfo():
    return patch.multiple("core.sysinfo", pc_info=lambda: {}, os_update_info=lambda: {})


def wu09(outcome, policy):
    with patch("core.usb_verification.verify_import_evidence",
               return_value={"ok": True, "reason": "합성 근거 일치"}), _no_sysinfo():
        results = winupdate.build_wu_results({"TC_Basic_WorkFlow_09": WF09},
                                             live_extra={"usb": outcome}, usb_policy=policy)
    return next(r for r in results if r.tc_id == "TC_WindowsUpdate_09")


class SkipVerdictMatrixTests(unittest.TestCase):
    EXPECTED = {
        # (USB 결과, 정책): (판정, L열 표시)
        ("pass", "current"): (PASS, None),
        ("pass", "flag"): (PASS, None),
        ("pass", "manual"): (PASS, None),
        ("absent", "current"): (PASS, None),
        ("absent", "flag"): (PASS, winupdate.USB_UNVERIFIED_LABEL),
        ("absent", "manual"): (MANUAL, None),
        ("error", "current"): (FAIL, None),
        ("error", "flag"): (FAIL, None),
        ("error", "manual"): (FAIL, None),
        ("regression", "current"): (PASS, None),
        ("regression", "flag"): (PASS, winupdate.USB_UNVERIFIED_LABEL),
        ("regression", "manual"): (MANUAL, None),
    }
    OUTCOMES = {"pass": USB_PASS, "absent": USB_ABSENT, "error": USB_ERROR, "regression": None}

    def test_matrix(self):
        for (kind, policy), (verdict, flag) in self.EXPECTED.items():
            with self.subTest(usb=kind, policy=policy):
                r = wu09(self.OUTCOMES[kind], policy)
                self.assertEqual(r.verdict, verdict)
                self.assertEqual((getattr(r, "wu_flags", None) or [None])[0], flag)
                cd = next(c for c in r.checks if c.title == "CD Export/Import")
                self.assertEqual(cd.status, SKIP)
                self.assertIs(cd.blocks_verdict, False)  # CD SKIP 은 판정을 막지 않는다(의도)

    def test_every_wu_skip_declares_blocks_verdict(self):
        with _no_sysinfo():
            results = winupdate.build_wu_results({}, live_extra={"usb": USB_ABSENT})
        skips = [(r.tc_id, c.title) for r in results for c in r.checks
                 if c.status == SKIP and c.blocks_verdict is None
                 and not c.title.startswith("[")]   # 재사용 원본 TC 의 SKIP 은 원본 규칙을 따른다
        # WU_10 의 변환 경로 SKIP 은 TC 전체가 SKIP 이라 PASS 가 될 수 없다.
        self.assertEqual(skips, [("TC_WindowsUpdate_10", "Setting 화면 표시")])

    def test_default_policy_is_manual_by_user_decision(self):
        # 2026-11-04 사용자 결정(SPEC REQ-WU-003): USB 왕복 미확인은 PASS 로 두지 않는다.
        self.assertEqual(winupdate.USB_UNVERIFIED_POLICY, "manual")


class BlocksVerdictResultTests(unittest.TestCase):
    def test_blocking_skip_turns_pass_into_manual_but_not_fail(self):
        r = TCResult("T", "t")
        r.add(1, "a", PASS)
        r.skip(2, "b", "사유", blocks_verdict=True)
        self.assertEqual(r.verdict, MANUAL)
        r.add(3, "c", FAIL, stop=False)
        self.assertEqual(r.verdict, FAIL)

    def test_legacy_skip_keeps_old_rule(self):
        r = TCResult("T", "t")
        r.add(1, "a", PASS)
        r.skip(2, "b", "사유")
        self.assertEqual(r.verdict, PASS)
        self.assertNotIn("blocks_verdict", r.as_dict()["checks"][1])

    def test_copied_checks_keep_flag(self):
        source = {"tc_id": "TC_X", "verdict": "PASS", "checks": [
            {"step": 1, "title": "a", "status": "SKIP", "blocks_verdict": True}]}
        r = TCResult("W", "w")
        winupdate._copy_checks(r, source, "TC_X")
        self.assertEqual(r.verdict, MANUAL)


class RegressionConversionParityTests(unittest.TestCase):
    """변환 경로의 '미수행' 채움 행이 알려진 결함 제외를 깨지 않는다(실시간 경로와 같은 판정)."""

    XIPL03_LIVE = [
        {"step": 1, "title": "3D Post Reconstruction 자동 수행", "status": "FAIL",
         "actual": "StepFailed: Step 9 FAIL — 이후 Step 을 수행하지 않고 이 TC 를 중단합니다: "
                   "Apply 후 TEST_3D 이름과 Recon/Syn 10개 값 유지"},
        {"step": 9, "title": "Apply 후 TEST_3D 이름과 Recon/Syn 10개 값 유지", "status": "FAIL"},
    ]
    PADDED = [{"step": n, "title": f"Step {n} 미수행", "status": "FAIL",
               "actual": "수행하지 않음(앞선 단계에서 TC 가 중단됨)"} for n in (3, 5)]
    XIPL07 = {"tc_id": "TC_XIPL_compatibility_07", "verdict": "PASS",
              "checks": [{"step": 1, "title": "적용", "status": "PASS"}]}

    def wu05(self, checks):
        lookup = {"TC_XIPL_compatibility_03": {"tc_id": "TC_XIPL_compatibility_03",
                                               "verdict": "FAIL", "checks": checks},
                  "TC_XIPL_compatibility_07": self.XIPL07}
        with _no_sysinfo():
            return next(r for r in winupdate.build_wu_results(lookup)
                        if r.tc_id == "TC_WindowsUpdate_05")

    def test_live_and_converted_results_get_same_verdict(self):
        live = self.wu05(self.XIPL03_LIVE)
        converted = self.wu05(self.XIPL03_LIVE + self.PADDED)
        self.assertEqual(live.verdict, PASS)
        self.assertEqual(converted.verdict, live.verdict)
        self.assertTrue(converted.wu_known_issues)

    def test_padding_after_a_real_failure_still_fails(self):
        other = {"step": 2, "title": "다른 결함", "status": "FAIL", "actual": "x"}
        self.assertEqual(self.wu05(self.XIPL03_LIVE + self.PADDED + [other]).verdict, FAIL)


if __name__ == "__main__":
    unittest.main()
