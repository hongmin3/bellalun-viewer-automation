"""Validates: REQ-QA-004. 제품과 DB를 조작하지 않는 공유 ZIP 시험."""
import hashlib
import json
import tempfile
import unittest
import zipfile
import warnings
from pathlib import Path

from bellalunauto.share import create_package, verify_package


class SharePackageTests(unittest.TestCase):
    def setUp(self):
        Path('work/qa-share').mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir='work/qa-share')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'Reports').mkdir()
        (self.root / 'Evidence').mkdir()
        self.image = self.root / 'Evidence' / '한글 화면.png'
        self.image.write_bytes(b'picture')
        self.dicom = self.root / 'Evidence' / 'patient.dcm'
        self.dicom.write_bytes(b'DICOM')
        self.log = self.root / 'Evidence' / 'Viewer.log'
        self.log.write_text('selected log', encoding='utf-8')
        self.report = self.root / 'Reports' / '결과 보고서.html'
        self.report.write_text('<a href="' + self.image.as_uri() + '">증거</a>', encoding='utf-8')
        self.data = self.root / 'Reports' / 'result.json'
        self.data.write_text(json.dumps({'results': [{'evidence': list(map(str, [self.image, self.dicom, self.log]))}]}), encoding='utf-8')

    def package(self, **kwargs):
        return create_package(self.root / '공유 결과.zip', run_id='run-한글', reports=[self.report, self.data], **kwargs)

    def test_offline_links_and_manifest(self):
        path = self.package(include_evidence=True)
        self.assertEqual(verify_package(path), [])
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            self.assertIn('evidence/한글 화면.png', names)
            self.assertNotIn('evidence/patient.dcm', names)
            self.assertNotIn('logs/Viewer.log', names)
            html = archive.read('reports/결과 보고서.html').decode('utf-8')
            self.assertIn('../evidence/', html)
            self.assertNotIn('file:', html)
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['run_id'], 'run-한글')
            self.assertTrue(manifest['created_at'])
            for name, item in manifest['files'].items():
                value = archive.read(name)
                self.assertEqual(item['size'], len(value))
                self.assertEqual(item['sha256'], hashlib.sha256(value).hexdigest())

    def test_selection_and_excluded_links(self):
        path = self.package()
        self.assertEqual(verify_package(path), [])
        with zipfile.ZipFile(path) as archive:
            self.assertNotIn('href=', archive.read('reports/결과 보고서.html').decode())
        path = self.package(include_dicom=True, include_logs=True)
        with zipfile.ZipFile(path) as archive:
            self.assertIn('dicom/patient.dcm', archive.namelist())
            self.assertIn('logs/Viewer.log', archive.namelist())

    def test_sensitive_report_rejected(self):
        config = self.root / 'config.json'
        config.write_text('{"password":"secret"}')
        with self.assertRaises(ValueError):
            create_package(self.root / 'bad.zip', run_id='a', reports=[config])
        self.data.write_text('{"password":"secret"}')
        with self.assertRaises(ValueError):
            self.package()

    def test_external_evidence_not_collected(self):
        external = self.root / 'private.png'
        external.write_bytes(b'private')
        self.data.write_text(json.dumps({'results': [{'evidence': [str(external)]}]}))
        self.report.write_text('<img src="' + external.as_uri() + '">')
        self.package(include_evidence=True)
        with zipfile.ZipFile(self.root / '공유 결과.zip') as archive:
            self.assertFalse(any('private' in name for name in archive.namelist()))

    def test_integrity_and_unsafe_links(self):
        original = self.package(include_evidence=True)
        with zipfile.ZipFile(original) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        for label, change in [
            ('missing', lambda d: d.pop('evidence/한글 화면.png')),
            ('extra', lambda d: d.update({'extra.txt': b'extra'})),
            ('tampered', lambda d: d.update({'evidence/한글 화면.png': b'changed'})),
            ('escape', lambda d: d.update({'../escape': b'bad'})),
            ('link', lambda d: d.update({'reports/결과 보고서.html': b'<a href="../../secret">out</a>'})),
        ]:
            with self.subTest(label=label):
                data = entries.copy()
                change(data)
                target = self.root / (label + '.zip')
                with zipfile.ZipFile(target, 'w') as archive:
                    for name, value in data.items():
                        archive.writestr(name, value)
                self.assertTrue(verify_package(target))

    def test_duplicate_zip_entries(self):
        path = self.package()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'a') as archive:
                archive.writestr('reports/result.json', '{}')
        self.assertTrue(any('중복' in error for error in verify_package(path)))

    def test_explicit_reports_and_review_without_sibling_collection(self):
        review = self.root / 'Reports' / 'review.json'
        review.write_text('{"reviewer":"검토자"}', encoding='utf-8')
        paths = [self.report, self.data]
        for suffix in ['.txt', '.csv']:
            path = self.root / 'Reports' / ('결과' + suffix)
            path.write_text('결과', encoding='utf-8')
            paths.append(path)
        workbook = self.root / 'Reports' / '결과.xlsx'
        with zipfile.ZipFile(workbook, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types/>')
        paths.append(workbook)
        (self.root / 'Reports' / 'unselected.txt').write_text('private')
        path = create_package(self.root / 'all.zip', run_id='run', reports=paths, review=review)
        self.assertEqual(verify_package(path), [])
        with zipfile.ZipFile(path) as archive:
            self.assertIn('review/review.json', archive.namelist())
            self.assertNotIn('reports/unselected.txt', archive.namelist())

    def test_unquoted_and_css_links_are_offline(self):
        self.report.write_text('<img src=https://example.com/track><style>body{background:url(https://example.com/p)}</style>', encoding='utf-8')
        path = self.package()
        with zipfile.ZipFile(path) as archive:
            value = archive.read('reports/결과 보고서.html').decode()
            self.assertNotIn('https:', value)
        self.assertEqual(verify_package(path), [])

    def test_xlsx_external_relationship_rejected(self):
        workbook = self.root / 'Reports' / 'checklist.xlsx'
        with zipfile.ZipFile(workbook, 'w') as archive:
            archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Target="file:///secret" TargetMode="External"/></Relationships>')
        with self.assertRaises(ValueError):
            create_package(self.root / 'xlsx.zip', run_id='r', reports=[workbook])

    def test_html_password_rejected(self):
        self.report.write_text('<pre>password = secret</pre>')
        with self.assertRaises(ValueError):
            self.package()

    def test_real_failure_json_shares_only_selected_log_window(self):
        folder = self.root / 'Evidence' / 'failure'
        folder.mkdir()
        failure = folder / 'failure_TC_example_20261105.json'
        failure.write_text(json.dumps({
            'tc_id': 'TC_example', 'reason': 'failure', 'event_time': '2026-11-05T12:00:00',
            'handles': {'private': 'not selected'}, 'foreground': {'title': 'private window'},
            'crash': {'path': 'private dump'},
            'log': {'path': 'C:/private/Viewer.log', 'found': True, 'encoding': 'utf-8',
                    'window': ['2026-11-05T11:59:30', '2026-11-05T12:00:30'],
                    'lines': ['12:00:00 selected Viewer log'], 'truncated': False, 'error': None},
        }), encoding='utf-8')
        self.data.write_text(json.dumps({'results': [{'evidence': [str(failure)]}]}), encoding='utf-8')
        path = self.package(include_evidence=True)
        with zipfile.ZipFile(path) as archive:
            self.assertFalse(any(name.startswith('logs/') for name in archive.namelist()))
        path = self.package(include_logs=True)
        self.assertEqual(verify_package(path), [])
        with zipfile.ZipFile(path) as archive:
            name = 'logs/' + failure.name
            self.assertIn(name, archive.namelist())
            value = json.loads(archive.read(name))
            self.assertEqual(value['log']['lines'], ['12:00:00 selected Viewer log'])
            self.assertEqual(value['log']['window'][0], '2026-11-05T11:59:30')
            self.assertNotIn('private', json.dumps(value))
            self.assertNotIn('path', value['log'])
            self.assertNotIn('crash', value)
            self.assertNotIn('foreground', value)


if __name__ == '__main__':
    Path('work/qa-share').mkdir(parents=True, exist_ok=True)
    unittest.main()
