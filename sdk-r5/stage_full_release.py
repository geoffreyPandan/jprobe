"""Collect exact artifacts and validation records for the matched fork."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile
import subprocess
import argparse
import sys
from release_checks import SUITES, inputs, verify_run, digest

BASE = Path('/home/jim/jprobe')
ROOT = BASE / 'full-source'
parser = argparse.ArgumentParser()
parser.add_argument('--release', default='full-r4')
args = parser.parse_args()
if Path(args.release).name != args.release or args.release in {'.', '..'}:
    raise ValueError('Invalid release name')
OUT = BASE / 'candidates' / args.release
if (OUT / 'release.json').exists():
    raise ValueError('A staged release is immutable; use a new release directory')
run = json.loads((OUT / 'validation-run.json').read_text())
environment = OUT / 'client-env'
verify_run(run, inputs(BASE, environment))
subprocess.run([sys.executable, str(BASE / 'audit_full_candidate.py'), '--release', args.release], check=True)
audit = json.loads((OUT / 'keyword-audit.json').read_text())
if audit.get('passed') is not True:
    raise ValueError('Keyword audit did not pass')
DIST = OUT / 'android-arm64'
DIST.mkdir(parents=True, exist_ok=True)
report = {'version': '17.25.0', 'protocol': 'jprobe', 'jsGlobal': 'Jprobe', 'tests': [], 'artifacts': [],
          'clientEnvironment': str(environment), 'validationRun': str(OUT / 'validation-run.json'),
          'keywordAudit': audit}
for suffix, count in SUITES.items():
    filename = suffix + '.json'
    record = Path(run['suites'][suffix]['record'])
    data = json.loads(record.read_text())
    cases = data['tests'] if isinstance(data, dict) else data
    assert len(cases) == count and all(case['passed'] for case in cases), record
    shutil.copy2(record, OUT / filename)
    report['tests'].append({'suite': suffix, 'count': count, 'record': str(record)})

for relative in ['server/jprobe-server', 'lib/agent/jprobe-agent.so',
                 'lib/gadget/jprobe-gadget.so', 'inject/jprobe-inject']:
    source = ROOT / 'build/subprojects/frida-core' / relative
    target = DIST / source.name
    shutil.copy2(source, target)
    if digest(target) != run['inputsAfter']['android/' + relative]:
        raise ValueError('Artifact changed while staging: ' + str(target))
    data = target.read_bytes()
    strings = sorted(set(match.group().decode('ascii') for match in re.finditer(rb'[ -~]{5,}', data)
                         if b'frida' in match.group().lower()))
    (DIST / (target.name + '.retained-keywords.txt')).write_text('\n'.join(strings) + '\n')
    report['artifacts'].append({'name': target.name, 'sha256': hashlib.sha256(data).hexdigest(),
                                'size': len(data), 'distinctPrintableKeywordMatches': len(strings),
                                'rawAsciiMatchesIgnoringCase': len(re.findall(b'frida', data, re.I)),
                                'rawUtf16LEMatchesIgnoringCase': len(re.findall(b'f\0r\0i\0d\0a\0', data, re.I))})
for path in (OUT / 'client').iterdir():
    if path.suffix not in {'.whl', '.tgz'}:
        continue
    report['artifacts'].append({'name': path.name, 'size': path.stat().st_size,
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
report['limitations'] = [
    'Raw ASCII and UTF-16LE scans cover the listed binaries and injected scripts; upstream attribution is retained separately.',
    'Intermittent ARM32 helper crashes occurred in earlier official and custom tests; long-term stability is unproven.',
    'Warm Java tests explicitly deoptimize the fixture before hooking.',
    'No claim of universal nondetection or third-party application compatibility.',
]
for component in ['root', 'frida-core', 'frida-gum', 'frida-python', 'frida-tools', 'idun']:
    directory = ROOT if component == 'root' else ROOT / 'subprojects' / component
    with (OUT / (component + '.patch')).open('wb') as output:
        subprocess.run(['git', 'diff', '--binary'], cwd=directory, stdout=output, check=True)
    # Renamed source files are untracked until staged; preserve their contents too.
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=directory, text=True)
    for name in untracked.splitlines():
        source = directory / name
        if source.is_file() and source.stat().st_size < 2_000_000:
            target = OUT / 'untracked-source' / component / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
go_source = BASE / 'go-rename/tsc'
if go_source.is_dir():
    dependency_archive = OUT / 'deps/tsc.tar.gz'
    dependency_archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dependency_archive, 'w:gz') as archive:
        archive.add(go_source, arcname='tsc')
        archive.add(go_source.parent / 'UPSTREAM.txt', arcname='UPSTREAM.txt')
    report['artifacts'].append({'name': 'deps/tsc.tar.gz', 'size': dependency_archive.stat().st_size,
                                'sha256': digest(dependency_archive)})
if args.release == 'full-r5':
    sdk_dir = OUT / 'deps/sdk-source'
    sdk_dir.mkdir(parents=True, exist_ok=True)
    sdk_sources = {
        'glib': BASE / 'sdk-rebuild/src/glib',
        'tinycc': BASE / 'sdk-rebuild/src/tinycc',
        'v8-abseil': BASE / 'sdk-rebuild/src/v8/third_party/abseil-cpp/src',
    }
    for name, directory in sdk_sources.items():
        patch = sdk_dir / (name + '.patch')
        with patch.open('wb') as output:
            subprocess.run(['git', 'diff', '--binary'], cwd=directory, stdout=output, check=True)
        if patch.stat().st_size == 0:
            raise ValueError('Missing SDK source patch: ' + name)
        report['artifacts'].append({'name': str(patch.relative_to(OUT)),
                                    'size': patch.stat().st_size, 'sha256': digest(patch)})
    for name in ['rebuild_named_sdk.py', 'install_named_sdk.py',
                 'patch_weekday_literal.py', 'patch_v8_weekday_literal.py',
                 'sanitize_client_extension.py', 'audit_full_candidate.py',
                 'stage_full_release.py', 'sanitize_bpf_lineinfo.py',
                 'patch_final_literals_r5.py', 'patch_go_weekday_r5.py',
                 'patch_libstdcxx_weekday_r5.py', 'use_patched_libstdcxx_r5.py']:
        source = BASE / name
        target = sdk_dir / name
        shutil.copy2(source, target)
        report['artifacts'].append({'name': str(target.relative_to(OUT)),
                                    'size': target.stat().st_size, 'sha256': digest(target)})
    for name in ['glib', 'tinycc', 'v8']:
        source = BASE / 'sdk-rebuild' / (name + '-source.json')
        target = sdk_dir / source.name
        shutil.copy2(source, target)
        report['artifacts'].append({'name': str(target.relative_to(OUT)),
                                    'size': target.stat().st_size, 'sha256': digest(target)})
    extra_sources = {
        'go-time-format.go': BASE / 'toolchains/go/src/time/format.go',
        'go-time-format.go.before': BASE / 'toolchains/go/src/time/format.go.before-jprobe-r5',
        'gcc-time-members.cc': BASE / 'gcc-time-r5/time_members.cc',
        'gcc-c++locale_internal.h': BASE / 'gcc-time-r5/c++locale_internal.h',
        'gcc-UPSTREAM.txt': BASE / 'gcc-time-r5/UPSTREAM.txt',
        'bpf-sanitize.json': BASE / 'bpf-r5-sanitize.json',
        'libstdc++-x86.a': BASE / 'gcc-time-r5/x86/libstdc++.a',
        'libstdc++-x86_64.a': BASE / 'gcc-time-r5/x86_64/libstdc++.a',
    }
    for name, source in extra_sources.items():
        target = sdk_dir / name
        shutil.copy2(source, target)
        report['artifacts'].append({'name': str(target.relative_to(OUT)),
                                    'size': target.stat().st_size, 'sha256': digest(target)})
    report['sdkArchives'] = []
    for host in ['linux-x86_64', 'linux-x86', 'android-arm64', 'android-arm']:
        archive = BASE / 'sdk-rebuild' / ('sdk-' + host + '.tar.xz')
        report['sdkArchives'].append({'host': host, 'path': str(archive),
                                      'size': archive.stat().st_size, 'sha256': digest(archive)})
verify_run(run, inputs(BASE, environment))
(OUT / 'release.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
