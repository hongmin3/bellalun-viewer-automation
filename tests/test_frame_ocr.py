# -*- coding: utf-8 -*-
"""공용 OCR 합의·재판독 규칙(`core/frame_ocr.py`).

Validates: REQ-FRAME-001
"""
import unittest

from core import frame_ocr as F


class BallotTests(unittest.TestCase):
    def test_same_method_repeated_is_one_vote(self):
        # 2026-11-26 Classic TC02: 문자 제한 판독이 세 밝기 모두 V를 Y로 읽었다. 한 방식의 반복은 한 표다.
        b = F.Ballot()
        for _ in range(3):
            b.add("word", "YXVUE_261126_073525")
        self.assertIsNone(b.settle())

    def test_two_methods_agree(self):
        b = F.Ballot()
        b.add("word", "YXVUE_1")
        b.add("line", "VXVUE_1")
        b.add("gray", "VXVUE_1")
        self.assertEqual("VXVUE_1", b.settle())

    def test_tie_between_methods_is_unsure(self):
        b = F.Ballot()
        for m, v in (("a", "X1"), ("b", "X1"), ("c", "X2"), ("d", "X2")):
            b.add(m, v)
        self.assertIsNone(b.settle())

    def test_method_without_majority_casts_no_vote(self):
        b = F.Ballot()
        b.add("page", "A"); b.add("page", "B")
        b.add("line", "A")
        self.assertEqual({("line", 0): "a"}, b.method_votes())
        self.assertIsNone(b.settle())

    def test_one_method_across_rounds_cannot_settle_alone(self):
        # 배율을 바꿔도 같은 착시를 반복하는 방식(2026-11-26 word=YXVUE 세 회차)은 혼자 값을 확정하지 못한다.
        b = F.Ballot()
        for r in range(3):
            b.add("word", "YXVUE_1", r)
        b.add("line", "VXVUE_1", 0)
        self.assertIsNone(b.settle())

    def test_rounds_break_a_tie_between_methods(self):
        # 2026-11-26 07:40 캡처 재현: 1회차는 방식마다 값이 갈렸고, 배율을 바꾼 회차에서 정답 표가 늘었다.
        b = F.Ballot()
        for r, gray in ((0, "VXVVUE_1"), (1, "VXVVUE_1"), (2, "VXVUE_1")):
            b.add("line", "VXVUE_1", r)
            b.add("gray", gray, r)
            b.add("word", "YXVUE_1", r)
        self.assertEqual("VXVUE_1", b.settle())

    def test_round_votes_still_need_majority_over_runner(self):
        b = F.Ballot()
        for r in range(2):
            b.add("line", "A", r)
            b.add("word", "B", r)
        b.add("page", "A", 0)
        b.add("gray", "B", 0)
        self.assertIsNone(b.settle())

    def test_empty_values_are_ignored(self):
        b = F.Ballot()
        b.add("a", ""); b.add("b", None); b.add("c", " . ")
        self.assertEqual([], b.reads)


class JudgeTests(unittest.TestCase):
    def _ballot(self, *pairs):
        b = F.Ballot()
        for m, v in pairs:
            b.add(m, v)
        return b

    def test_match(self):
        self.assertEqual((F.MATCH, "A_1"), F.judge(self._ballot(("a", "A_1"), ("b", "A 1")), "A_1"))

    def test_mismatch_only_when_nobody_read_expected(self):
        b = self._ballot(("a", "B_1"), ("b", "B_1"))
        self.assertEqual(F.MISMATCH, F.judge(b, "A_1")[0])

    def test_expected_seen_blocks_mismatch(self):
        b = self._ballot(("a", "B_1"), ("b", "B_1"), ("c", "A_1"))
        self.assertEqual(F.UNSURE, F.judge(b, "A_1")[0])

    def test_expected_never_substitutes_reading(self):
        # 기대값을 한 번 읽었다고 PASS가 되지는 않는다. 합의가 있어야 한다.
        b = self._ballot(("a", "A_1"), ("b", "B_1"))
        self.assertEqual(F.UNSURE, F.judge(b, "A_1")[0])


class RereadTests(unittest.TestCase):
    def test_rereads_until_settled_and_counts_all_rounds(self):
        rounds = [{"id": [("word", "Y1")]}, {"id": [("line", "V1")]}, {"id": [("gray", "V1")]}]
        calls = []

        def read(i):
            calls.append(i)
            return rounds[i]

        r = F.reread(read, expected={"id": "V1"}, max_rounds=3)
        self.assertEqual([0, 1, 2], calls)
        self.assertEqual(F.MATCH, r["verdicts"]["id"])
        self.assertEqual("V1", r["fields"]["id"])
        self.assertEqual(3, r["rounds"])

    def test_stops_early_when_decided(self):
        calls = []

        def read(i):
            calls.append(i)
            return {"id": [("a", "V1"), ("b", "V1")]}

        r = F.reread(read, expected={"id": "V1"}, max_rounds=3)
        self.assertEqual([0], calls)
        self.assertEqual(1, r["rounds"])

    def test_confirmed_mismatch_stops_and_reports(self):
        r = F.reread(lambda i: {"id": [("a", "Q9"), ("b", "Q9")]}, expected={"id": "V1"})
        self.assertEqual(F.MISMATCH, r["verdicts"]["id"])
        self.assertEqual("Q9", r["fields"]["id"])

    def test_still_unsure_after_max_rounds(self):
        r = F.reread(lambda i: {"id": [("a", "V1"), ("b", "Y1")]}, expected={"id": "V1"}, max_rounds=2)
        self.assertEqual(F.UNSURE, r["verdicts"]["id"])
        self.assertNotIn("id", r["fields"])
        self.assertEqual(2, r["rounds"])
        self.assertTrue(r["notes"])

    def test_failed_round_is_recorded(self):
        r = F.reread(lambda i: None, expected={"id": "V1"}, max_rounds=2)
        self.assertEqual(F.UNSURE, r["verdicts"]["id"])
        self.assertIn("판독 실패", r["notes"][0])

    def test_without_expected_settles_every_field(self):
        r = F.reread(lambda i: {"a": [("m1", "x"), ("m2", "x")], "b": [("m1", "y")]}, max_rounds=1)
        self.assertEqual({"a": "x"}, r["fields"])
        self.assertEqual(F.UNSURE, r["verdicts"]["b"])


if __name__ == "__main__":
    unittest.main()
