"""Validates: REQ-SPECSYNC-002, REQ-SPECSYNC-003. 동작 파일이 SPEC 12절 추적표에 나오고 verify 게이트가 시험을 모두 돈다."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
BEHAVIOR_GLOBS = ("run.py", "core/**/*.py", "bellalunauto/**/*.py", "remote/**/*.py", "tests/**/*.py")

# 추적 대상에서 빼는 파일. 동작이 없는 패키지 표시 파일만 둔다.
EXCLUDED = {
    "core/__init__.py": "빈 패키지 표시 파일",
    "tests/__init__.py": "빈 패키지 표시 파일",
    "bellalunauto/__init__.py": "패키지 설명과 버전 문자열만 있다(버전은 REQ-DIST-003 빌드가 읽는다)",
    "remote/__init__.py": "패키지 설명 문자열만 있다",
}

# 2026-11-16 이 검사를 도입할 때 12절에 없던 파일. 근거(REQ 본문·Validates 표기·사양 문서) 없이 REQ에
# 붙이지 않으려고 그대로 남겼다. 이 목록은 줄이기만 한다. 파일을 12절에 넣으면 여기서 지운다.
UNTRACED_BASELINE = {
    "core/dicomlite.py",
    "core/display.py",
    "core/imginfo.py",
    "core/installer_ui.py",
    "core/mwl.py",
    "core/net.py",
    "core/setting_changes.py",
    "core/setting_transfer.py",
    "core/snapshot.py",
    "core/statusbar.py",
    "core/uitext.py",
    "core/viewer_tools.py",
    "core/watchdog.py",
    "tests/dataflow.py",
    "tests/install.py",
    "tests/install_package.py",
    "tests/install_package_flow.py",
    "tests/settings.py",
    "tests/system_compat.py",
    "tests/test_cause_evidence_followup.py",
    "tests/test_close_examine_confirm.py",
    "tests/test_distribution_integration.py",
    "tests/test_export_completion_wait.py",
    "tests/test_imginfo_and_waits.py",
    "tests/test_install_observation_followup.py",
    "tests/test_module_attr_check.py",
    "tests/test_non_ui_improvements.py",
    "tests/test_performance_waits.py",
    "tests/test_qc_wait_diagnostics.py",
    "tests/test_scope_summary.py",
    "tests/test_setting_changes.py",
    "tests/test_setting_dialog.py",
    "tests/test_supervisor_final_record.py",
    "tests/test_ui_children.py",
    "tests/test_winupdate_isolation.py",
    "tests/test_xipl_startup.py",
    "tests/ui_flows.py",
    "tests/workflow06.py",
    "tests/workflow07.py",
}


def _section(text, number):
    start = text.index(f"\n## {number}. ")
    end = text.find("\n## ", start + 1)
    return text[start:end if end > 0 else None]


def _test_bodies(text):
    bodies = {}
    for m in re.finditer(r"^### (TEST-[A-Z0-9]+-\d{3})\b.*$", text, re.M):
        nxt = re.search(r"^##", text[m.end():], re.M)
        bodies[m.group(1)] = text[m.end(): m.end() + nxt.start() if nxt else None]
    return bodies


def traced_paths(spec_text):
    """12절 행의 backtick 경로와, 그 행이 가리키는 TEST-ID 본문의 backtick 경로."""
    bodies = _test_bodies(spec_text)
    tokens = set()
    for line in _section(spec_text, 12).splitlines():
        if not re.match(r"\|\s*(REQ|NFR)-", line):
            continue
        tokens.update(re.findall(r"`([^`]+)`", line))
        for test_id in re.findall(r"\bTEST-[A-Z0-9]+-\d{3}\b", line):
            tokens.update(re.findall(r"`([^`]+)`", bodies.get(test_id, "")))
    return {t.strip().replace("\\", "/") for t in tokens}


def _covered(path, tokens):
    return path in tokens or any(t.endswith("/") and path.startswith(t) for t in tokens)


def behavior_files():
    found = set()
    for pattern in BEHAVIOR_GLOBS:
        for p in ROOT.glob(pattern):
            if p.is_file() and "__pycache__" not in p.parts:
                found.add(p.relative_to(ROOT).as_posix())
    return found


class TraceCoverageTests(unittest.TestCase):
    def test_harness_guide_is_reachable_and_its_local_links_resolve(self):
        guide = ROOT / "docs/harness.md"
        self.assertIn("@AGENTS.md", (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines())
        for entry in ("AGENTS.md", "README.md"):
            self.assertIn("](docs/harness.md)", (ROOT / entry).read_text(encoding="utf-8"), entry)
        links = re.findall(r"\]\(([^)]+)\)", guide.read_text(encoding="utf-8"))
        self.assertIn("examples/conflict-claim.json", links)
        for link in links:
            if "://" not in link:
                self.assertTrue((guide.parent / link.split("#")[0]).exists(), link)

    @classmethod
    def setUpClass(cls):
        cls.spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")
        cls.tokens = traced_paths(cls.spec)
        cls.files = behavior_files()

    def test_every_behavior_file_is_traced(self):
        missing = sorted(f for f in self.files
                         if not _covered(f, self.tokens) and f not in EXCLUDED and f not in UNTRACED_BASELINE)
        self.assertEqual(missing, [], "SPEC.md 12절에 구현 또는 테스트로 넣으세요(관련 REQ 근거를 확인한 뒤)")

    def test_lists_do_not_go_stale(self):
        stale = sorted(f for f in UNTRACED_BASELINE | set(EXCLUDED) if f not in self.files)
        self.assertEqual(stale, [], "없어진 파일을 목록에서 지우세요")
        now_traced = sorted(f for f in UNTRACED_BASELINE if _covered(f, self.tokens))
        self.assertEqual(now_traced, [], "12절에 들어간 파일을 UNTRACED_BASELINE에서 지우세요")
        self.assertFalse(UNTRACED_BASELINE & set(EXCLUDED))


class VerifyGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "botyard.json").read_text(encoding="utf-8"))
        cls.spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")

    def test_verify_runs_required_checks(self):
        joined = "\n".join(self.config["verify"])
        for needle in ("tools/spec_sync_check.py", "project-readiness.js", "tools/traceability.py",
                       "pytest tests"):
            self.assertIn(needle, joined)

    def test_publish_settings_kept(self):
        self.assertIs(self.config.get("autoSync"), False)
        self.assertIs(self.config.get("autoPush"), False)

    def test_verify_tests_match_unit_test_files(self):
        expected = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_*.py"))
        self.assertEqual(sorted(self.config["verifyTests"]), expected,
                         "pytest tests가 실제로 도는 파일과 verifyTests를 맞추세요")

    def test_verified_rows_are_fully_gated(self):
        gated = set(self.config["verifyTests"])
        bodies = _test_bodies(self.spec)
        for line in _section(self.spec, 12).splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4 or not re.match(r"(REQ|NFR)-", cells[0]) or cells[3] != "verified":
                continue
            files = set(re.findall(r"`(tests/test_[^`]+\.py)`", cells[2]))
            for test_id in re.findall(r"\bTEST-[A-Z0-9]+-\d{3}\b", cells[2]):
                files |= set(re.findall(r"`(tests/test_[^`]+\.py)`", bodies.get(test_id, "")))
            self.assertTrue(files, f"{cells[0]}: verified인데 자동 시험 파일이 없습니다")
            self.assertEqual(sorted(files - gated), [], f"{cells[0]}: 게이트가 돌지 않는 시험이 있습니다")


if __name__ == "__main__":
    unittest.main()
