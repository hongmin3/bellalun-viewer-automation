# -*- coding: utf-8 -*-
"""TEST-KNOW-001: 지식 폴더 서버 동기화 (REQ-KNOW-001). 네트워크·실제 `지식` 폴더를 쓰지 않는다."""

import hashlib
import os
import tempfile
import unittest

from core import knowledge_sync as ks

LISTING = """
<section id="kind-specification" class="x"><table><tbody>
<tr><td><a href="/knowledge/download/346">(사양서) Bellalun Viewer 사양서(261030).pdf</a></td><td>사양서</td></tr>
</tbody></table></section>
<section id="kind-manual"><table><tbody>
<tr><td>
<a href="/knowledge/download/347">(매뉴얼) Bellalun Viewer QC Manual.V1.0.12W1_KO_완료.docx</a>
</td><td>매뉴얼</td></tr>
</tbody></table></section>
<section id="kind-qa_rules"><table><tbody>
<tr><td>Bellalun Viewer QA 지침.md</td></tr>
</tbody></table></section>
<section id="kind-release_note"><p>없음</p></section>
"""


class FakeFetcher:
    def __init__(self, files, versions=None, sizes=None):
        self.files = files
        self.versions = versions or {}
        self.sizes = sizes or {}
        self.downloads = []

    def meta(self, doc):
        name = doc["name"]
        data = self.files[name]
        return {"version": self.versions.get(name, "v1"), "size": self.sizes.get(name, len(data))}

    def download(self, doc, dest):
        self.downloads.append(doc["name"])
        with open(dest, "wb") as f:
            f.write(self.files[doc["name"]])


def write(folder, name, data):
    with open(os.path.join(folder, name), "wb") as f:
        f.write(data)


def read(folder, name):
    with open(os.path.join(folder, name), "rb") as f:
        return f.read()


def docs(*names):
    return [{"kind": "manual", "name": n, "id": "1", "source": "http"} for n in names]


class ListingTest(unittest.TestCase):
    def test_parse_listing_reads_names_links_and_kinds(self):
        got = ks.parse_listing(LISTING)
        self.assertEqual(
            [(d["kind"], d["name"], d["id"]) for d in got],
            [("specification", "(사양서) Bellalun Viewer 사양서(261030).pdf", "346"),
             ("manual", "(매뉴얼) Bellalun Viewer QC Manual.V1.0.12W1_KO_완료.docx", "347"),
             ("qa_rules", "Bellalun Viewer QA 지침.md", None)])

    def test_empty_listing_is_an_error_not_an_empty_server(self):
        with self.assertRaises(ks.SyncError):
            ks.parse_listing("<html>점검 중</html>")

    def test_sources_use_ssh_only_for_configured_kinds(self):
        got = ks.attach_sources(ks.parse_listing(LISTING), ("qa_rules",), ssh_ready=True)
        self.assertEqual([d["source"] for d in got], ["http", "http", "ssh"])
        got = ks.attach_sources(ks.parse_listing(LISTING), ("qa_rules",), ssh_ready=False)
        self.assertEqual(got[2]["source"], None)


class DocKeyTest(unittest.TestCase):
    def test_versions_dates_and_prefix_are_ignored(self):
        self.assertEqual(ks.doc_key("(사양서) Bellalun Viewer 사양서(261030).pdf"),
                         ks.doc_key("(사양서) Bellalun Viewer 사양서(260710).pdf"))
        self.assertEqual(ks.doc_key("(매뉴얼) VDMS-1100TM Service Manual.V1.1_EN.pdf"),
                         ks.doc_key("(매뉴얼) VDMS-1100TM Service Manual.V1.2_EN.pdf"))

    def test_split_spec_volumes_and_other_formats_are_different_documents(self):
        self.assertNotEqual(ks.doc_key("(사양서) Bellalun Viewer 사양서(261030).pdf"),
                            ks.doc_key("(사양서) Bellalun Viewer 사양서1(260710).pdf"))
        self.assertNotEqual(ks.doc_key("a.V1.0.pdf"), ks.doc_key("a.V1.0.docx"))

    def test_unsafe_names_are_rejected(self):
        for name in ("..\\x.pdf", "a/b.pdf", ".sync-state.json", ks.ARCHIVE_DIR, "", "a:b"):
            self.assertFalse(ks.safe_name(name), name)
        self.assertTrue(ks.safe_name("(TC) R-23-428_Bellalun Viewer_Test Case.xlsx"))


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = self.tmp.name
        self.lines = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_sync(self, docs_, fetcher, **kw):
        return ks.sync(self.folder, docs_, fetcher, today="2026-11-04", log=self.lines.append, **kw)

    def test_new_version_replaces_old_and_archives_it(self):
        write(self.folder, "(사양서) X 사양서(260710).pdf", b"old")
        write(self.folder, "작성 규칙.md", b"local only")
        fetcher = FakeFetcher({"(사양서) X 사양서(261030).pdf": b"new"})
        result = self.run_sync(docs("(사양서) X 사양서(261030).pdf"), fetcher)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(read(self.folder, "(사양서) X 사양서(261030).pdf"), b"new")
        self.assertFalse(os.path.exists(os.path.join(self.folder, "(사양서) X 사양서(260710).pdf")))
        archived = os.path.join(self.folder, ks.ARCHIVE_DIR, "2026-11-04", "(사양서) X 사양서(260710).pdf")
        self.assertEqual(read(os.path.dirname(archived), os.path.basename(archived)), b"old")
        self.assertEqual(read(self.folder, "작성 규칙.md"), b"local only")
        self.assertFalse(os.path.exists(os.path.join(self.folder, ks.STAGING_DIR)))

    def test_unchanged_document_is_not_downloaded_again(self):
        fetcher = FakeFetcher({"a.docx": b"same"})
        self.run_sync(docs("a.docx"), fetcher)
        fetcher.downloads.clear()
        result = self.run_sync(docs("a.docx"), fetcher)
        self.assertEqual(fetcher.downloads, [])
        self.assertEqual(result["unchanged"], ["a.docx"])

    def test_same_content_with_new_server_version_is_left_in_place(self):
        write(self.folder, "a.docx", b"same")
        result = self.run_sync(docs("a.docx"), FakeFetcher({"a.docx": b"same"}))
        self.assertEqual(result["unchanged"], ["a.docx"])
        self.assertFalse(os.path.exists(os.path.join(self.folder, ks.ARCHIVE_DIR)))

    def test_changed_content_with_same_name_archives_the_old_copy(self):
        write(self.folder, "a.docx", b"old")
        result = self.run_sync(docs("a.docx"), FakeFetcher({"a.docx": b"new"}))
        self.assertEqual(result["changed"], ["a.docx"])
        self.assertEqual(read(self.folder, "a.docx"), b"new")
        self.assertEqual(read(os.path.join(self.folder, ks.ARCHIVE_DIR, "2026-11-04"), "a.docx"), b"old")

    def test_size_mismatch_keeps_old_version_and_fails(self):
        write(self.folder, "a.docx", b"old")
        result = self.run_sync(docs("a.docx"), FakeFetcher({"a.docx": b"new"}, sizes={"a.docx": 99}))
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(read(self.folder, "a.docx"), b"old")

    def test_dry_run_does_not_touch_the_folder(self):
        write(self.folder, "a.docx", b"old")
        result = self.run_sync(docs("a.docx"), FakeFetcher({"a.docx": b"new"}), dry_run=True)
        self.assertEqual(result["moves"], ["a.docx"])
        self.assertEqual(read(self.folder, "a.docx"), b"old")
        self.assertFalse(os.path.exists(os.path.join(self.folder, ks.STATE_FILE)))

    def test_unavailable_document_keeps_local_copy(self):
        write(self.folder, "Bellalun Viewer QA 지침.md", b"local")
        d = [{"kind": "qa_rules", "name": "Bellalun Viewer QA 지침.md", "id": None, "source": None}]
        result = self.run_sync(d, FakeFetcher({}))
        self.assertEqual(result["unavailable"], ["Bellalun Viewer QA 지침.md"])
        self.assertEqual(read(self.folder, "Bellalun Viewer QA 지침.md"), b"local")

    def test_failed_archive_move_blocks_the_new_version(self):
        write(self.folder, "a.docx", b"old")

        def move(src, dst):
            if dst.startswith(os.path.join(self.folder, ks.ARCHIVE_DIR)):
                raise PermissionError("열려 있음")
            os.replace(src, dst)

        result = self.run_sync(docs("a.docx"), FakeFetcher({"a.docx": b"new"}), move=move)
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(read(self.folder, "a.docx"), b"old")

    def test_unsafe_server_name_is_refused(self):
        result = self.run_sync(docs("..\\evil.pdf"), FakeFetcher({"..\\evil.pdf": b"x"}))
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(os.listdir(self.folder), [ks.STATE_FILE])

    def test_state_records_content_hash(self):
        self.run_sync(docs("a.docx"), FakeFetcher({"a.docx": b"new"}))
        state = ks.load_state(os.path.join(self.folder, ks.STATE_FILE))
        self.assertEqual(state["a.docx"]["sha256"], hashlib.sha256(b"new").hexdigest())


class HostTest(unittest.TestCase):
    def setUp(self):
        self.s = ks.settings({"knowledge_sync": {"server_url": "http://server/", "hosts": ["admin"]}})

    def test_settings_require_server_url(self):
        with self.assertRaises(ks.SyncError):
            ks.settings({})
        self.assertEqual(self.s["server_url"], "http://server")
        self.assertEqual(self.s["product"], "bellalun-viewer")

    def test_only_listed_receivers_run(self):
        ks.check_host(self.s, "ADMIN")
        with self.assertRaises(ks.SyncError):
            ks.check_host(self.s, "OTHER")
        with self.assertRaises(ks.SyncError):
            ks.check_host(dict(self.s, hosts=()), "ADMIN")

    def test_uploader_pc_never_overwrites_its_own_originals(self):
        with self.assertRaises(ks.SyncError):
            ks.check_host(self.s, "ADMIN", uploader="admin")


class FolderTest(unittest.TestCase):
    def test_finds_knowledge_folder_above_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "proj", "auto")
            os.makedirs(os.path.join(tmp, "proj", ks.KNOWLEDGE_DIR))
            os.makedirs(repo)
            self.assertEqual(ks.knowledge_dir({}, repo), os.path.join(tmp, "proj", ks.KNOWLEDGE_DIR))
            self.assertEqual(ks.knowledge_dir({"knowledge_dir": os.path.join(tmp, "nope")}, repo), "")

    def test_log_sits_next_to_knowledge_folder(self):
        self.assertEqual(ks.log_path(os.path.join("P", "지식"), "2026-11-04"),
                         os.path.join("P", "logs", "knowledge-sync", "2026-11-04.log"))


if __name__ == "__main__":
    unittest.main()
