"""배포 자료 경계만 검증한다. Viewer/DB/UI를 실행하지 않는다."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class DistributionBuildTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'tools/build_distribution.py').is_file(),
                        '배포 빌드 구현이 필요합니다')
        spec = importlib.util.spec_from_file_location('distribution_builder', ROOT / 'tools/build_distribution.py')
        self.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.builder)
        self.temp = tempfile.TemporaryDirectory(prefix='배포 시험 ')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.manifest = {'schema_version': 1, 'asset_version': 'approved-v1',
                         'compatibility': {'viewer': ['1.0'], 'sql': ['SQL Server 2022']}, 'files': []}
        for kind, names in {'checklist': ['basic.xlsx', 'wu.xlsx'],
                            'baseline': ['DATA.bak', 'ACCOUNT.bak', 'CONFIGURATION.bak', 'PROCEDURE.bak'],
                            'knowledge': ['spec1.pdf', 'spec2.pdf'],
                            'manual': ['operation.docx', 'service.docx', 'dicom.docx']}.items():
            for name in names:
                source = self.home / name
                source.write_bytes(b'approved-fixture')
                self.manifest['files'].append({'source': str(source),
                    'destination': f'{kind}/{name}', 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                    'kind': kind, 'version': 'approved-v1'})
                roles = {'basic.xlsx': 'basic-checklist', 'wu.xlsx': 'windows-update-checklist',
                         'spec1.pdf': 'specification1', 'spec2.pdf': 'specification2',
                         'operation.docx': 'operation-manual', 'service.docx': 'service-manual',
                         'dicom.docx': 'dicom-conformance'}
                if name in roles:
                    self.manifest['files'][-1]['role'] = roles[name]

    def validate(self, manifest=None):
        path = self.home / 'approved-assets.json'
        path.write_text(json.dumps(manifest or self.manifest), encoding='utf-8')
        return self.builder.load_assets(path)

    def test_approved_manifest_is_staged_and_hashes_are_recorded(self):
        assets = self.validate()
        destination = self.home / '설치 폴더'
        self.builder.stage_assets(assets, destination)
        self.assertEqual((destination / 'resources/assets/checklist/basic.xlsx').read_bytes(), b'approved-fixture')
        inventory = self.builder.inventory(destination)
        self.assertEqual(len(inventory), 11)
        self.assertEqual(inventory[0]['sha256'], hashlib.sha256(b'approved-fixture').hexdigest())

    def test_destination_escape_absolute_ads_and_windows_alias_are_rejected(self):
        for target in ['../escape.xlsx', '/absolute.xlsx', 'C:/escape.xlsx', 'a:stream.xlsx',
                       'checklist/../basic.xlsx', 'checklist/CON.xlsx', 'checklist/basic.xlsx.']:
            with self.subTest(target=target):
                data = copy.deepcopy(self.manifest)
                data['files'][0]['destination'] = target
                with self.assertRaises(ValueError):
                    self.validate(data)

    def test_duplicate_case_insensitive_destination_is_rejected(self):
        self.manifest['files'][1]['destination'] = 'CHECKLIST/BASIC.XLSX'
        with self.assertRaises(ValueError):
            self.validate()

    def test_hash_mismatch_and_missing_version_are_rejected(self):
        for key, value in [('sha256', '0' * 64), ('version', '')]:
            with self.subTest(key=key):
                data = copy.deepcopy(self.manifest)
                data['files'][0][key] = value
                with self.assertRaises(ValueError):
                    self.validate(data)

    def test_source_code_private_config_and_runtime_paths_are_rejected(self):
        for name in ['source.py', 'source.pyc', 'symbols.pdb', 'config.json',
                     'Reports/test.pdf', 'Evidence/test.pdf', 'patient/test.pdf', 'dicom/test.dcm',
                     '.git/secrets.pdf', 'current-db.bak']:
            with self.subTest(name=name):
                source = self.home / name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(b'approved-fixture')
                data = copy.deepcopy(self.manifest)
                data['files'][0]['source'] = str(source)
                with self.assertRaises(ValueError):
                    self.validate(data)

    def test_relative_and_symlink_sources_are_rejected(self):
        self.manifest['files'][0]['source'] = 'basic.xlsx'
        with self.assertRaises(ValueError):
            self.validate()
        source = self.home / 'linked.xlsx'
        try:
            source.symlink_to(self.home / 'basic.xlsx')
        except OSError:
            self.skipTest('symlink 권한 없음')
        self.manifest['files'][0]['source'] = str(source)
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_required_assets_and_compatibility_are_rejected(self):
        for field in ['files', 'compatibility']:
            data = copy.deepcopy(self.manifest)
            data[field] = [] if field == 'files' else {'viewer': [], 'sql': []}
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate(data)

    def test_only_four_named_approved_baseline_destinations_are_allowed(self):
        data = copy.deepcopy(self.manifest)
        for item in data['files']:
            if item['kind'] == 'baseline':
                item['destination'] = 'baseline/current.bak'
                break
        with self.assertRaises(ValueError):
            self.validate(data)

    def test_both_specs_and_all_three_manuals_are_required(self):
        for kind in ('knowledge', 'manual'):
            data = copy.deepcopy(self.manifest)
            data['files'].remove(next(item for item in data['files'] if item['kind'] == kind))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.validate(data)

    def test_required_document_roles_cannot_be_omitted_or_duplicated(self):
        for kind in ('checklist', 'knowledge', 'manual'):
            for duplicate in (True, False):
                data = copy.deepcopy(self.manifest)
                items = [item for item in data['files'] if item['kind'] == kind]
                if duplicate:
                    items[1]['role'] = items[0]['role']
                else:
                    del items[0]['role']
                with self.subTest(kind=kind, duplicate=duplicate), self.assertRaises(ValueError):
                    self.validate(data)

    def test_build_preflight_includes_pytest_function_tests(self):
        commands = self.builder.preflight_commands(ROOT)
        self.assertIn([sys.executable, '-m', 'pytest', 'tests', '-q'], commands)
        self.assertNotIn([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'], commands)

    @unittest.skipUnless(os.name == 'nt', 'Windows Inno version probe')
    def test_iscc_preprocessor_version_probe_works_without_building_an_installer(self):
        iscc = ROOT / 'work/InnoSetup6/ISCC.exe'
        if not iscc.is_file():
            self.skipTest('optional local Inno compiler not installed')
        self.assertEqual(self.builder.inno_version(iscc), '6.7.3')

    def test_changed_source_between_validation_and_copy_is_rejected(self):
        assets = self.validate()
        (self.home / 'basic.xlsx').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.builder.stage_assets(assets, self.home / 'dist')

    def test_distribution_audit_rejects_own_source_and_sensitive_data(self):
        for name in ['core/run.py', 'run.pyc', 'tests/test_dummy.pyd', 'config.json',
                     '.git/config', 'Reports/old.html', 'file.pdb', 'module.c', 'module.o', 'library.a']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'bad')
                with self.assertRaises(ValueError):
                    self.builder.audit_distribution(Path(directory))

    def test_nuitka_compiles_scenarios_and_excludes_only_unit_tests(self):
        command = self.builder.nuitka_command(ROOT, self.home, '1.2.3')
        self.assertIn('--include-module=tests.winupdate', command)
        self.assertIn('--include-module=tests.workflow01', command)
        self.assertIn('--nofollow-import-to=tests.test_*', command)
        self.assertNotIn('--nofollow-import-to=tests', command)
        self.assertIn('--windows-console-mode=hide', command)
        self.assertIn('--mingw64', command)
        self.assertIn('--jobs=2', command)
        self.assertEqual(command[-1], str(ROOT / 'BellalunAuto.py'))

    def test_cli_help_survives_non_korean_windows_stdout(self):
        environment = dict(os.environ, PYTHONIOENCODING='cp1252')
        result = subprocess.run([sys.executable, str(ROOT / 'tools/build_distribution.py'), '--help'],
                                env=environment, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('ascii', errors='replace'))
        self.assertIn('--assets', result.stdout.decode('utf-8'))

    def test_gui_subsystem_binary_is_rejected_because_powershell_does_not_wait(self):
        for subsystem in (2, 3):
            content = bytearray(512)
            content[:2] = b'MZ'
            struct.pack_into('<I', content, 0x3c, 0x80)
            content[0x80:0x84] = b'PE\0\0'
            struct.pack_into('<H', content, 0x84, 0x8664)
            struct.pack_into('<H', content, 0x98, 0x20b)
            struct.pack_into('<H', content, 0x98 + 68, subsystem)
            executable = self.home / f'synthetic-{subsystem}.exe'
            executable.write_bytes(content)
            with self.subTest(subsystem=subsystem):
                if subsystem == 2:
                    with self.assertRaises(ValueError):
                        self.builder.validate_console_subsystem(executable)
                else:
                    self.assertEqual(self.builder.validate_console_subsystem(executable), 3)

    def test_runtime_resources_require_runtime_licenses_and_omit_build_only_packages(self):
        # Installed distribution metadata is a build-host dependency. A metadata
        # fixture avoids requiring Nuitka on the normal source test host.
        license_file = self.home / 'LICENSE.txt'
        license_file.write_text('fixture license', encoding='utf-8')
        class Installed:
            files = [Path('LICENSE.txt'), Path('reports/LicenseReport.rst.j2')]
            def locate_file(self, file):
                return license_file
        def installed(name):
            if name in {'ordered-set', 'zstandard'}:
                raise self.builder.metadata.PackageNotFoundError(name)
            return Installed()
        output = self.home / 'runtime distribution'
        output.mkdir()
        with patch.object(self.builder.metadata, 'distribution', installed):
            self.builder.stage_resources(ROOT, output, self.validate())
        self.assertTrue((output / 'third-party-licenses/Pillow/LICENSE.txt').is_file())
        self.assertTrue((output / 'third-party-licenses/Tcl-8.6.15-license.terms').is_file())
        self.assertTrue((output / 'third-party-licenses/Tk-8.6.15-license.terms').is_file())
        self.assertTrue((output / 'third-party-licenses/OpenSSL-3.0.16-LICENSE.txt').is_file())
        self.assertTrue((output / 'third-party-licenses/OpenSSL-3.0.16-COPYRIGHT.txt').is_file())
        self.assertTrue((output / 'third-party-licenses/zlib-1.3.1-LICENSE.txt').is_file())
        self.assertFalse((output / 'third-party-licenses/Pillow/reports').exists())
        self.assertFalse((output / 'third-party-licenses/ordered-set').exists())
        defaults = json.loads((output / 'resources/config.example.json').read_text(encoding='utf-8'))
        self.assertEqual(defaults['viewer']['login']['password'], '')
        self.assertNotIn('10.13.0.222', json.dumps(defaults))
        public_assets = json.loads((output / 'resources/assets-manifest.json').read_text(encoding='utf-8'))
        self.assertNotIn('source', public_assets['files'][0])

    def compiler_reports(self):
        compiler = self.home / 'toolchain with spaces/gcc.exe'
        compiler.parent.mkdir()
        compiler.write_bytes(b'synthetic compiler executable')
        report = self.home / 'nuitka-report.xml'
        report.write_text('<nuitka-compilation-report nuitka_version="4.3" mode="standalone" completion="yes">'
                          '<scons_environment c_compiler="MinGW64" the_cc_name="gcc"/>'
                          '</nuitka-compilation-report>', encoding='utf-8')
        scons = self.home / 'scons-report.txt'
        scons.write_text(f'CC="C:/synthetic/ccache.exe" "{compiler}"\nthe_cc_name=gcc\n', encoding='utf-8')
        return compiler, report, scons

    def test_compiler_provenance_records_actual_binary_versions_and_report_hashes(self):
        compiler, report, scons = self.compiler_reports()
        def execute(command, **kwargs):
            output = 'gcc (synthetic mingw64) 15.2.0\n' if command[-1] == '--version' else 'x86_64-w64-mingw32\n'
            return subprocess.CompletedProcess(command, 0, stdout=output, stderr='')
        with patch.object(self.builder.subprocess, 'run', execute):
            actual = self.builder.compiler_provenance(report, scons)
        self.assertEqual(actual['compiler']['sha256'], hashlib.sha256(b'synthetic compiler executable').hexdigest())
        self.assertEqual(actual['compiler']['version'], 'gcc (synthetic mingw64) 15.2.0')
        self.assertEqual(actual['compiler']['target'], 'x86_64-w64-mingw32')
        self.assertEqual(actual['nuitka_report']['sha256'], hashlib.sha256(report.read_bytes()).hexdigest())
        self.assertEqual(actual['scons_report']['sha256'], hashlib.sha256(scons.read_bytes()).hexdigest())

    def test_compiler_provenance_rejects_incomplete_report_or_missing_compiler(self):
        compiler, report, scons = self.compiler_reports()
        report.write_text('<nuitka-compilation-report nuitka_version="4.3" completion="interrupted"/>', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.builder.compiler_provenance(report, scons)
        report.write_text('<nuitka-compilation-report nuitka_version="4.3" mode="standalone" completion="yes"/>', encoding='utf-8')
        compiler.unlink()
        with self.assertRaises(ValueError):
            self.builder.compiler_provenance(report, scons)

    def test_tcl_tk_runtime_provenance_requires_libraries_and_records_patchlevels(self):
        dist = self.home / 'gui dist'
        for relative, content in {'tcl/init.tcl': b'package require -exact Tcl 8.6.15',
                                  'tk/tk.tcl': b'package require -exact Tk 8.6.15',
                                  'tcl86t.dll': b'tcl fixture', 'tk86t.dll': b'tk fixture',
                                  '_tkinter.pyd': b'tkinter fixture'}.items():
            target = dist / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        provenance = self.builder.tk_provenance(dist)
        self.assertEqual(provenance['tcl_version'], '8.6.15')
        self.assertEqual(provenance['tk_version'], '8.6.15')
        self.assertEqual(len(provenance['files']), 5)
        (dist / 'tk86t.dll').unlink()
        with self.assertRaises(ValueError):
            self.builder.tk_provenance(dist)


if __name__ == '__main__':
    unittest.main()
