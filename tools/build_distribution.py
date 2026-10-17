"""Build local, private BellalunAuto distributions; never discovers private assets.

All subprocess arguments are arrays, including paths containing Korean or spaces.
Importing this module performs no build, product operation, or configuration write.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import re
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = '3.12.10'
INNO_VERSION = '6.7.3'
TK_VERSION = '8.6.15'
PUBLIC_LICENSE_VERSIONS = {'Tcl': TK_VERSION, 'Tk': TK_VERSION,
                           'OpenSSL': '3.0.16', 'zlib': '1.3.1'}
PINNED = {'Nuitka': '4.3', 'Pillow': '12.1.1', 'pytesseract': '0.3.13',
          'openpyxl': '3.1.5', 'pypdf': '6.1.1', 'ordered-set': '4.1.0',
          'zstandard': '0.25.0', 'et_xmlfile': '2.0.0', 'packaging': '26.3',
          'pytest': '9.1.1', 'iniconfig': '2.3.0', 'pluggy': '1.6.0',
          'colorama': '0.4.6', 'Pygments': '2.21.0'}
FORBIDDEN_PARTS = {'.git', '__pycache__', 'reports', 'evidence', 'log', 'cache',
                   'temp', 'work', 'patient', 'patients', 'dicom', 'current-db'}
SOURCE_SUFFIXES = {'.py', '.pyc', '.pyo', '.pdb', '.c', '.cpp', '.h', '.obj', '.o', '.a', '.lib'}
ASSET_SUFFIXES = {'checklist': {'.xlsx'}, 'baseline': {'.bak'},
                  'knowledge': {'.pdf', '.docx'}, 'manual': {'.pdf', '.docx'}}
ASSET_ROLES = {'checklist': {'basic-checklist', 'windows-update-checklist'},
               'knowledge': {'specification1', 'specification2'},
               'manual': {'operation-manual', 'service-manual', 'dicom-conformance'}}
# Nuitka can legitimately copy data owned by these third-party packages.
# Their Python source/bytecode, if present, must remain under their package root.
THIRD_PARTY_ROOTS = {'pil', 'pytesseract', 'openpyxl', 'pypdf', 'et_xmlfile', 'packaging'}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _not_link(path):
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError(f'링크/재분석 경로 금지: {path.name}')


def _safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('목적 경로는 /로 구분한 상대 경로여야 합니다')
    parts = value.split('/')
    if PureWindowsPath(value).drive or PurePosixPath(value).is_absolute():
        raise ValueError('절대 목적 경로 금지')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                *(f'LPT{i}' for i in range(1, 10))}
    for part in parts:
        if (part in {'', '.', '..'} or part.rstrip(' .') != part
                or any(ch in part for ch in ':*?"<>|')
                or any(ord(ch) < 32 for ch in part)
                or part.split('.')[0].upper() in reserved):
            raise ValueError('잘못된 Windows 목적 경로')
    return PurePosixPath(value)


def _sensitive(path, source=False):
    # OS temporary directories can hold approved inputs; runtime output folders
    # remain forbidden inside the resulting distribution.
    forbidden = FORBIDDEN_PARTS - {'temp', 'cache', 'log', 'work'} if source else FORBIDDEN_PARTS
    return (any(part.casefold() in forbidden for part in path.parts)
            or path.name.casefold() in {'config.json', '.config-session.json'}
            or path.name.casefold().startswith(('current-db', 'current_db'))
            or path.suffix.casefold() in {'.dcm', '.mdf', '.ldf'})


def load_assets(manifest_path):
    manifest_path = Path(manifest_path)
    _not_link(manifest_path.absolute())
    data = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if data.get('schema_version') != 1 or not data.get('asset_version'):
        raise ValueError('schema_version=1 및 asset_version 필수')
    compatibility = data.get('compatibility', {})
    for name in ('viewer', 'sql'):
        values = compatibility.get(name)
        if not isinstance(values, list) or not values or not all(isinstance(v, str) and v.strip() for v in values):
            raise ValueError(f'{name} 호환성 허용 목록 필수')
    counts = Counter()
    destinations = set()
    for item in data.get('files', []):
        destination = _safe_relative(item.get('destination'))
        key = str(destination).casefold()
        if key in destinations:
            raise ValueError('중복 목적 경로')
        destinations.add(key)
        kind = item.get('kind')
        if kind not in ASSET_SUFFIXES or not isinstance(item.get('version'), str) or not item['version'].strip():
            raise ValueError('자료 kind/version 필수')
        source = Path(item.get('source', ''))
        if not source.is_absolute():
            raise ValueError('원본은 절대 파일 경로여야 합니다')
        _not_link(source)
        if not source.is_file() or _sensitive(source, source=True) or _sensitive(destination):
            raise ValueError('민감자료/런타임 자료/누락 원본 금지')
        if (source.suffix.casefold() not in ASSET_SUFFIXES[kind]
                or destination.suffix.casefold() not in ASSET_SUFFIXES[kind]):
            raise ValueError('자료 유형과 확장자가 일치하지 않습니다')
        expected_hash = item.get('sha256', '')
        if not re.fullmatch('[0-9a-fA-F]{64}', expected_hash) or sha256(source) != expected_hash.lower():
            raise ValueError('자료 SHA256 불일치')
        counts[kind] += 1
    if counts != Counter({'checklist': 2, 'baseline': 4, 'knowledge': 2, 'manual': 3}):
        raise ValueError('체크리스트2/승인 Baseline4/필수 사양2·매뉴얼3이 필요합니다')
    for kind, expected_roles in ASSET_ROLES.items():
        roles = [item.get('role') for item in data['files'] if item['kind'] == kind]
        if len(set(roles)) != len(roles) or set(roles) != expected_roles:
            raise ValueError(f'{kind} 필수 자료 role 누락/중복')
    baseline = {item['destination'].casefold() for item in data['files'] if item['kind'] == 'baseline'}
    if baseline != {f'baseline/{name}.bak' for name in ('data', 'account', 'configuration', 'procedure')}:
        raise ValueError('승인 Baseline DATA/ACCOUNT/CONFIGURATION/PROCEDURE만 허용합니다')
    return data


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def stage_assets(assets, destination):
    root = Path(destination) / 'resources/assets'
    root.mkdir(parents=True, exist_ok=True)
    _not_link(root.absolute())
    for item in assets['files']:
        source = Path(item['source'])
        _not_link(source)
        target = root.joinpath(*_safe_relative(item['destination']).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        _not_link(target.absolute())
        shutil.copyfile(source, target)
        if sha256(target) != item['sha256'].lower():
            target.unlink()
            raise ValueError('복사 중 자료 변경 감지')


def inventory(directory):
    root = Path(directory)
    return [{'path': path.relative_to(root).as_posix(), 'size': path.stat().st_size,
             'sha256': sha256(path)} for path in sorted(root.rglob('*')) if path.is_file()]


def audit_distribution(directory):
    root = Path(directory)
    for path in root.rglob('*'):
        _not_link(path)
        relative = path.relative_to(root)
        if _sensitive(relative):
            raise ValueError(f'배포 금지 경로: {relative}')
        if not path.is_file():
            continue
        suffix = path.suffix.casefold()
        third_party = relative.parts[0].casefold() in THIRD_PARTY_ROOTS
        if suffix in SOURCE_SUFFIXES and not (third_party and suffix in {'.py', '.pyc', '.pyo'}):
            raise ValueError(f'자체 소스/바이트코드/중간파일 금지: {relative}')
        if relative.parts[0].casefold() == 'tests' and path.stem.startswith('test_'):
            raise ValueError(f'단위시험 배포 금지: {relative}')


def nuitka_command(root, output, version):
    root, output = Path(root), Path(output)
    command = [sys.executable, '-m', 'nuitka', '--mode=standalone', '--mingw64', '--jobs=2',
               '--assume-yes-for-downloads', '--enable-plugin=tk-inter',
               '--windows-console-mode=hide', '--output-filename=BellalunAuto.exe',
               f'--output-dir={output}', f'--report={output / "nuitka-report.xml"}',
               '--include-module=run', '--include-package=core', '--include-package=bellalunauto',
               '--nofollow-import-to=tests.test_*', '--company-name=Bellalun QA',
               '--product-name=BellalunAuto', f'--file-version={version}',
               f'--product-version={version}']
    for path in sorted((root / 'tests').glob('*.py')):
        if path.name != '__init__.py' and not path.stem.startswith('test_'):
            command.append(f'--include-module=tests.{path.stem}')
    return command + [str(root / 'BellalunAuto.py')]


def validate_console_subsystem(executable):
    """Reject PE GUI binaries: PowerShell direct invocation does not wait for them.

    Nuitka hide uses console subsystem while hiding a newly spawned console.
    This checks the actual artifact, independently of the compiler option list.
    """
    with Path(executable).open('rb') as stream:
        dos_header = stream.read(64)
        if len(dos_header) != 64 or dos_header[:2] != b'MZ':
            raise ValueError('Windows PE 실행 파일이 아닙니다')
        pe_offset = struct.unpack_from('<I', dos_header, 0x3c)[0]
        stream.seek(pe_offset)
        header = stream.read(94)
    if (len(header) != 94 or header[:4] != b'PE\0\0'
            or struct.unpack_from('<H', header, 4)[0] != 0x8664
            or struct.unpack_from('<H', header, 24)[0] != 0x20b):
        raise ValueError('x64 PE32+ 실행 파일이 아닙니다')
    subsystem = struct.unpack_from('<H', header, 92)[0]
    if subsystem != 3:
        raise ValueError('PowerShell 출력·대기를 위해 PE console subsystem 3이 필요합니다')
    return subsystem


def run_checked(command, cwd=ROOT, log_path=None):
    environment = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    if log_path:
        with Path(log_path).open('w', encoding='utf-8') as log:
            subprocess.run(command, cwd=cwd, check=True, stdout=log, stderr=subprocess.STDOUT, env=environment)
    else:
        subprocess.run(command, cwd=cwd, check=True, env=environment)


def preflight_commands(root, skip_tests=False):
    # Source-reading checks run here, never in the installed selfcheck.
    commands = []
    for script in ('check_module_attrs.py', 'check_self_attrs.py', 'check_cleanup_stop.py',
                   'check_regression_names.py'):
        commands.append([sys.executable, str(root / 'tools' / script)])
    if not skip_tests:
        commands.append([sys.executable, '-m', 'pytest', 'tests', '-q'])
    return commands


def preflight(root, skip_tests=False):
    for command in preflight_commands(root, skip_tests):
        run_checked(command, cwd=root)


def inno_version(iscc):
    # /? exposes only the major version; Ver is the official encoded compiler
    # version. The probe aborts during preprocessing, before creating output.
    marker = f'BELLALUNAUTO_INNO_VERSION_OK_{INNO_VERSION}'
    major, minor, revision = map(int, INNO_VERSION.split('.'))
    expected = (major << 24) | (minor << 16) | (revision << 8)
    probe = (f'#if (Ver & 0xFFFFFF00) != {expected}\n'
             '#error BELLALUNAUTO_INNO_WRONG_VERSION\n#else\n'
             f'#error {marker}\n#endif\n')
    result = subprocess.run([str(iscc), '/Q', '-'], input=probe, capture_output=True,
                            text=True, errors='replace')
    if marker not in result.stdout + result.stderr:
        raise ValueError(f'Inno Setup {INNO_VERSION} 필요')
    return INNO_VERSION


def tool_versions(iscc):
    if platform.python_version() != PYTHON_VERSION or platform.architecture()[0] != '64bit' or os.name != 'nt':
        raise ValueError(f'Windows x64 CPython {PYTHON_VERSION} 빌드 환경이 필요합니다')
    versions = {'python': platform.python_version()}
    for package, expected in PINNED.items():
        actual = metadata.version(package)
        if actual != expected:
            raise ValueError(f'{package}=={expected} 필요 (현재 {actual})')
        versions[package] = actual
    versions['inno_setup'] = inno_version(iscc)
    # Capture transitive versions too: reproducibility uses requirements-build.txt.
    versions['installed_distributions'] = dict(sorted((dist.metadata['Name'], dist.version)
                                                     for dist in metadata.distributions()))
    return versions


def compiler_provenance(report_path, scons_report_path):
    """Read the compiler Nuitka actually selected, rather than guessing PATH.

    SCons CC may contain a ccache wrapper followed by the absolute gcc.exe.
    Only the selected MinGW compiler is queried; no shell evaluates CC text.
    """
    report_path, scons_report_path = Path(report_path).absolute(), Path(scons_report_path).absolute()
    for path in (report_path, scons_report_path):
        _not_link(path)
        if not path.is_file():
            raise ValueError('Nuitka/SCons 원본 컴파일 보고서가 필요합니다')
    try:
        # Nuitka declares encoding='utf8'; expat treats that alias as a single-byte
        # codec and rejects non-ASCII build paths. Decode as UTF-8 ourselves.
        report = ET.fromstring(report_path.read_bytes().decode('utf-8'))
    except (ET.ParseError, UnicodeDecodeError) as error:
        raise ValueError('Nuitka 컴파일 보고서 XML 오류') from error
    if (report.tag != 'nuitka-compilation-report' or report.get('completion') != 'yes'
            or report.get('nuitka_version') != PINNED['Nuitka'] or report.get('mode') != 'standalone'):
        raise ValueError('고정 Nuitka 버전의 성공한 standalone 컴파일 보고서가 필요합니다')
    values = dict(line.split('=', 1) for line in scons_report_path.read_text(encoding='utf-8-sig').splitlines()
                  if '=' in line)
    arguments = [quoted or plain for quoted, plain in re.findall(r'"([^"]+)"|(\S+)', values.get('CC', ''))]
    drivers = [Path(argument) for argument in arguments if Path(argument).name.casefold() == 'gcc.exe']
    if len(drivers) != 1 or not drivers[0].is_absolute() or not drivers[0].is_file():
        raise ValueError('SCons 보고서에서 실제 MinGW64 gcc.exe 절대 경로를 찾지 못했습니다')
    driver = drivers[0].resolve()
    _not_link(driver)
    version = subprocess.run([str(driver), '--version'], capture_output=True, text=True,
                             encoding='utf-8', errors='replace', check=True).stdout.strip()
    target = subprocess.run([str(driver), '-dumpmachine'], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', check=True).stdout.strip()
    if not version or target != 'x86_64-w64-mingw32':
        raise ValueError('실제 컴파일러의 버전/x64 MinGW target을 확인하지 못했습니다')
    return {'compiler': {'path': str(driver), 'sha256': sha256(driver),
                         'version': version, 'target': target},
            'nuitka_report': {'path': str(report_path), 'sha256': sha256(report_path),
                              'nuitka_version': report.get('nuitka_version'),
                              'mode': report.get('mode'), 'completion': report.get('completion')},
            'scons_report': {'path': str(scons_report_path), 'sha256': sha256(scons_report_path)}}


def tk_provenance(distribution):
    """Verify bundled GUI runtime files without initializing Tk or a display."""
    distribution = Path(distribution)
    names = ['tcl/init.tcl', 'tk/tk.tcl', 'tcl86t.dll', 'tk86t.dll', '_tkinter.pyd']
    files, versions = [], {}
    for name in names:
        path = distribution / name
        _not_link(path.absolute())
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'Tcl/Tk 런타임 누락: {name}')
        files.append({'path': name, 'sha256': sha256(path), 'size': path.stat().st_size})
    for component, name in (('Tcl', 'tcl/init.tcl'), ('Tk', 'tk/tk.tcl')):
        match = re.search(r'package\s+require\s+-exact\s+' + component + r'\s+([0-9.]+)',
                          (distribution / name).read_text(encoding='utf-8'))
        if not match or match.group(1) != TK_VERSION:
            raise ValueError(f'{component} 런타임과 고정 라이선스 버전 {TK_VERSION} 불일치')
        versions[component.casefold() + '_version'] = match.group(1)
    return dict(versions, files=files, license_provenance='third-party-licenses/public-runtime-provenance.json')


def stage_resources(root, distribution, assets):
    sys.path.insert(0, str(root))
    from bellalunauto.runtime import default_config
    resources = distribution / 'resources'
    resources.mkdir(exist_ok=True)
    _write_json(resources / 'config.example.json', default_config(resource_dir=root))
    for name in ('automation_scope.json', 'traceability.json'):
        shutil.copyfile(root / name, resources / name)
    stage_assets(assets, distribution)
    # Do not expose local absolute source paths in installed metadata.
    public_manifest = {key: value for key, value in assets.items() if key != 'files'}
    public_manifest['files'] = [{key: value for key, value in item.items() if key != 'source'}
                                for item in assets['files']]
    _write_json(resources / 'assets-manifest.json', public_manifest)
    shutil.copyfile(root / 'packaging/사용안내.txt', distribution / '사용안내.txt')
    licenses = distribution / 'third-party-licenses'
    licenses.mkdir()
    # ordered-set/zstandard drive the compiler only; they are not imported by
    # the application. Nuitka's runtime and bundled-library licenses are copied.
    for name in ('Nuitka', 'Pillow', 'pytesseract', 'openpyxl', 'pypdf', 'et_xmlfile', 'packaging'):
        dist = metadata.distribution(name)
        copied = 0
        for file in dist.files or []:
            if re.search(r'^(licen[cs]e|copying|notice)(?:[._-]|$)', file.name, re.I):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = licenses / name / Path(*file.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    copied += 1
        if not copied:
            raise ValueError(f'제3자 라이선스 누락: {name}')
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise ValueError('CPython LICENSE.txt 누락')
    shutil.copyfile(python_license, licenses / 'CPython-LICENSE.txt')
    public_licenses = root / 'packaging/licenses'
    license_manifest = json.loads((public_licenses / 'provenance.json').read_text(encoding='utf-8'))
    for item in license_manifest['files']:
        source = public_licenses / item['file']
        if item['version'] != PUBLIC_LICENSE_VERSIONS.get(item['component']) or sha256(source) != item['sha256']:
            raise ValueError('고정 공개 런타임 라이선스 버전/해시 불일치')
        shutil.copyfile(source, licenses / item['file'])
    _write_json(licenses / 'public-runtime-provenance.json', license_manifest)


def build(args):
    root = ROOT
    output = Path(args.output).expanduser().absolute()
    # Require a fresh location: never delete or merge pre-existing private outputs.
    if output.exists() and any(output.iterdir()):
        raise ValueError('비어 있는 전용 output 폴더를 지정하십시오')
    _not_link(output)
    assets = load_assets(args.assets)
    versions = tool_versions(Path(args.iscc).absolute())
    output.mkdir(parents=True, exist_ok=True)
    preflight(root, args.skip_tests)
    sys.path.insert(0, str(root))
    from bellalunauto import __version__
    git = shutil.which('git')
    if not git:
        raise ValueError('빌드 메타데이터에 필요한 Git을 찾지 못했습니다')
    commit = subprocess.check_output([git, 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output([git, 'status', '--porcelain'], cwd=root, text=True).strip())
    compile_dir = output / 'compile'
    if args.skip_compile:
        if not args.compiled_dir:
            raise ValueError('--skip-compile 사용 시 --compiled-dir 필수')
        compiled = Path(args.compiled_dir).absolute()
        if not args.compilation_report or not args.scons_report:
            raise ValueError('--skip-compile 사용 시 --compilation-report 및 --scons-report 필수')
        provenance = compiler_provenance(args.compilation_report, args.scons_report)
    else:
        compile_dir.mkdir()
        run_checked(nuitka_command(root, compile_dir, __version__), log_path=output / 'compile.log')
        compiled = compile_dir / 'BellalunAuto.dist'
        provenance = compiler_provenance(compile_dir / 'nuitka-report.xml',
                                         compile_dir / 'BellalunAuto.build/scons-report.txt')
    if not (compiled / 'BellalunAuto.exe').is_file():
        raise ValueError('컴파일된 BellalunAuto.exe 누락')
    pe_subsystem = validate_console_subsystem(compiled / 'BellalunAuto.exe')
    audit_distribution(compiled)
    distribution = output / f'BellalunAuto-{__version__}'
    shutil.copytree(compiled, distribution)
    stage_resources(root, distribution, assets)
    audit_distribution(distribution)
    versions['c_compiler'] = provenance['compiler']
    versions['tcl_tk'] = tk_provenance(distribution)
    info = {'schema_version': 1, 'version': __version__, 'source_commit': commit,
            'source_dirty': dirty, 'built_at_utc': datetime.now(timezone.utc).isoformat(),
            'target_os': ['Windows 10 x64', 'Windows 11 x64'],
            'build_host_os': {'platform': platform.platform(), 'version': platform.version()},
            'validation': {'installation': 'not verified by build', 'product_tests': 'not verified by build'},
            'tools': versions, 'asset_version': assets['asset_version'],
            'compilation': provenance,
            'application': {'path': 'BellalunAuto.exe', 'sha256': sha256(distribution / 'BellalunAuto.exe'),
                            'pe_subsystem': pe_subsystem, 'windows_console_mode': 'hide'},
            'compatibility': assets['compatibility'],
            'skipped': {'compile': args.skip_compile, 'tests': args.skip_tests},
            'third_party_source_allowed_roots': sorted(THIRD_PARTY_ROOTS),
            'files': inventory(distribution)}
    _write_json(distribution / 'build-info.json', info)
    _write_json(output / 'build-info.json', info)
    archive = output / f'BellalunAuto-{__version__}-portable.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as stream:
        for file in sorted(distribution.rglob('*')):
            if file.is_file():
                stream.write(file, Path(distribution.name) / file.relative_to(distribution))
    run_checked([str(Path(args.iscc).absolute()), f'/DAppVersion={__version__}',
                 f'/DSourceDir={distribution}', f'/DOutputDir={output}',
                 str(root / 'packaging/BellalunAuto.iss')], log_path=output / 'installer.log')
    installer = output / f'BellalunAuto-{__version__}-setup.exe'
    if not installer.is_file():
        raise ValueError('설치 파일 누락')
    artifacts = [archive, installer, output / 'build-info.json']
    (output / 'SHA256SUMS.txt').write_text(''.join(f'{sha256(file)}  {file.name}\n' for file in artifacts), encoding='utf-8')
    print(f'빌드 완료: {output}')
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='BellalunAuto 내부 배포 빌드')
    parser.add_argument('--assets', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--iscc', required=True, type=Path)
    parser.add_argument('--skip-tests', action='store_true', help='개발용: 생략 내역을 build-info에 기록')
    parser.add_argument('--skip-compile', action='store_true', help='개발용: 기존 standalone 재사용, build-info 기록')
    parser.add_argument('--compiled-dir', type=Path)
    parser.add_argument('--compilation-report', type=Path, help='--skip-compile 원본 Nuitka XML 보고서')
    parser.add_argument('--scons-report', type=Path, help='--skip-compile 원본 SCons 보고서')
    args = parser.parse_args(argv)
    try:
        return build(args)
    except (ValueError, OSError, subprocess.CalledProcessError, metadata.PackageNotFoundError) as error:
        print(f'빌드 중단: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
