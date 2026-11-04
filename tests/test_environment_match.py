# -*- coding: utf-8 -*-
"""검증된 환경 대조 — 지문 생성과 등록 항목 비교 (가짜 probe)."""
import json
import tempfile
import unittest
from pathlib import Path

from core import environment_match as em

ENTRIES = [
    {"id": "pro", "os_edition": "Windows 11 Pro", "build_ubr": "26200",
     "resolution": "1920x1080", "dpi": 96, "viewer_version": None},
    {"id": "ltsc", "os_edition": "Windows 11 IoT Enterprise LTSC", "build_ubr": "26100",
     "resolution": "1920x1080", "dpi": 96, "viewer_version": None},
]


def _probe(**over):
    probe = {"os_edition": "Windows 11 Pro", "build_ubr": "26200.7171",
             "display": {"actual": (1920, 1080), "dpi": 96},
             "viewer_version": "1.0.0.1"}
    probe.update(over)
    return probe


class FingerprintTests(unittest.TestCase):
    def test_fields_from_probe_and_callables(self):
        fp = em.fingerprint(_probe(os_edition=lambda: "Microsoft Windows 11 Pro"))
        self.assertEqual({"os_edition": "Windows 11 Pro", "build_ubr": "26200.7171",
                          "resolution": "1920x1080", "dpi": 96,
                          "viewer_version": "1.0.0.1"}, fp)

    def test_failing_probe_becomes_none(self):
        def boom():
            raise OSError("x")
        fp = em.fingerprint(_probe(build_ubr=boom, display=None))
        self.assertIsNone(fp["build_ubr"])
        self.assertIsNone(fp["resolution"])

    def test_registry_product_name_corrected_for_windows11(self):
        self.assertEqual("Windows 11 Pro", em.edition_from_registry(
            {"ProductName": "Windows 10 Pro", "CurrentBuildNumber": "26200"}))
        self.assertEqual("Windows 10 Pro", em.edition_from_registry(
            {"ProductName": "Windows 10 Pro", "CurrentBuildNumber": "19045"}))
        self.assertEqual("26200.9818", em.build_from_registry(
            {"CurrentBuildNumber": "26200", "UBR": 9818}))


class MatchTests(unittest.TestCase):
    def test_build_prefix_entry_matches_any_ubr(self):
        result = em.match(em.fingerprint(_probe()), ENTRIES)
        self.assertEqual("verified", result["status"])
        self.assertEqual("pro", result["matched"]["id"])

    def test_exact_ubr_entry_requires_same_ubr(self):
        entry = dict(ENTRIES[0], build_ubr="26200.7000")
        result = em.match(em.fingerprint(_probe()), [entry])
        self.assertEqual("unregistered", result["status"])
        self.assertEqual(["build_ubr"], [d["field"] for d in result["differences"]])

    def test_ltsc_year_suffix_matches_but_workstations_does_not(self):
        ltsc = em.fingerprint(_probe(os_edition="Windows 11 IoT Enterprise LTSC 2024",
                                     build_ubr="26100.1"))
        self.assertEqual("ltsc", em.match(ltsc, ENTRIES)["matched"]["id"])
        ws = em.fingerprint(_probe(os_edition="Windows 11 Pro for Workstations"))
        self.assertEqual("unregistered", em.match(ws, ENTRIES)["status"])

    def test_unregistered_reports_closest_differences(self):
        fp = em.fingerprint(_probe(display={"actual": (2560, 1440), "dpi": 144}))
        result = em.match(fp, ENTRIES)
        self.assertEqual("unregistered", result["status"])
        self.assertEqual("pro", result["closest"]["id"])
        self.assertEqual({"resolution", "dpi"}, {d["field"] for d in result["differences"]})
        self.assertIn("미등록 환경", em.describe(result))

    def test_unknown_value_is_a_difference(self):
        fp = em.fingerprint(_probe(build_ubr=None))
        result = em.match(fp, ENTRIES[:1])
        self.assertEqual("unregistered", result["status"])
        self.assertIn("조회 불가", result["differences"][0]["text"])

    def test_empty_entries_is_unregistered(self):
        self.assertEqual("unregistered", em.match(em.fingerprint(_probe()), [])["status"])


class DataFileTests(unittest.TestCase):
    def test_repo_data_file_loads_with_evidence(self):
        entries = em.load_entries(Path(__file__).resolve().parent.parent / em.DATA_FILE)
        self.assertTrue(entries)
        for entry in entries:
            self.assertTrue(set(em.FIELDS) <= set(entry))
            self.assertTrue(entry.get("evidence"))

    def test_missing_or_broken_file_gives_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual([], em.load_entries(Path(tmp) / "none.json"))
            bad = Path(tmp) / "bad.json"
            bad.write_text("{", encoding="utf-8")
            self.assertEqual([], em.load_entries(bad))
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps({"entries": ENTRIES}), encoding="utf-8")
            self.assertEqual(2, len(em.load_entries(good)))


if __name__ == "__main__":
    unittest.main()
