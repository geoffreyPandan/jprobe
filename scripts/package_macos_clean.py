#!/usr/bin/env python3
"""Stage, sanitize, package and audit both wheels without overwriting a release."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
import zipfile


def run(argv, **kwargs):
    subprocess.run(argv, check=True, **kwargs)


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: package_macos_clean.py UPSTREAM WORKSPACE')
    source, workspace = [Path(p).resolve(strict=True) for p in sys.argv[1:]]
    build = workspace / 'build-macos-clean'
    dist = workspace / 'dist/macos-clean'
    if dist.is_symlink() or (dist.exists() and any(dist.iterdir())):
        raise SystemExit('Refusing to overwrite existing dist/macos-clean artifacts')
    staging_root = workspace / '.macos-package-staging'
    staging_root.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='package-', dir=staging_root))
    print('Packaging stage:', stage, flush=True)
    package = build / 'subprojects/frida-python/jprobe'
    extensions = list(package.glob('_jprobe*.so'))
    if len(extensions) != 1:
        raise RuntimeError('Expected one compiled Python extension')
    candidate = stage / 'native-package'
    candidate.mkdir()
    for name in ['__init__.py', 'aio.py', '_jprobe.pyi']:
        shutil.copy2(package / name, candidate / name)
    clean_extension = candidate / extensions[0].name
    report = stage / 'native-audit.json'
    run([sys.executable, str(Path(__file__).resolve().parent / 'sanitize_macos_extension.py'),
         str(extensions[0]), str(clean_extension), '--report', str(report), '--require-zero'])
    wheels = stage / 'wheels'
    wheels.mkdir()
    env = os.environ.copy()
    env.update(JPROBE_VERSION='17.25.0', JPROBE_TOOLS_VERSION='14.11.0+jprobe',
               JPROBE_EXTENSION=str(clean_extension))
    run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
         '-w', str(wheels), str(source / 'subprojects/frida-python')], env=env)

    tools = source / 'subprojects/frida-tools'
    link = tools / 'build'
    target = build / 'subprojects/frida-tools'
    if not target.is_dir():
        raise RuntimeError('Built tools directory is missing')
    allowed = {(workspace / name / 'subprojects/frida-tools').resolve()
               for name in ['build-macos-client', 'build-macos-clean']}
    lock_path = tools / '.jprobe-tools-build-link.lock'
    lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(lock)
    previous = None
    changed = False
    previous_handler = signal.getsignal(signal.SIGTERM)
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminate)
    try:
        if link.is_symlink():
            if link.resolve() not in allowed:
                raise RuntimeError('Refusing tools build link outside known workspace builds')
            previous = os.readlink(link)
        elif link.exists():
            raise RuntimeError('Refusing to replace a real tools build directory')
        (stage / 'tools-link-state.json').write_text(json.dumps({'link': str(link),
            'previousTarget': previous, 'temporaryTarget': str(target)}, indent=2))
        temporary = tools / ('.jprobe-build-' + uuid.uuid4().hex)
        temporary.symlink_to(target, target_is_directory=True)
        os.replace(temporary, link)
        changed = True
        run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
             '-w', str(wheels), str(tools)], env=env)
    finally:
        try:
            if changed:
                if not link.is_symlink() or link.resolve() != target.resolve():
                    raise RuntimeError('Tools build link changed concurrently; refusing to overwrite it during restore')
                if previous is None:
                    link.unlink()
                else:
                    restore = tools / ('.jprobe-build-restore-' + uuid.uuid4().hex)
                    restore.symlink_to(previous, target_is_directory=True)
                    os.replace(restore, link)
        finally:
            signal.signal(signal.SIGTERM, previous_handler)
            lock_path.unlink()

    entries = sorted(wheels.glob('*.whl'))
    if len(entries) != 2 or not any(p.name.startswith('jprobe-17.25.0-') for p in entries) or not any(p.name.startswith('jprobe_tools-14.11.0+jprobe-') for p in entries):
        raise RuntimeError('Unexpected wheel set')
    scanned, violations = [], []
    clean_digest = hashlib.sha256(clean_extension.read_bytes()).digest()
    for wheel in entries:
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if Path(name).suffix not in {'.so', '.js'}:
                    continue
                data = archive.read(name)
                row = {'wheel': wheel.name, 'member': name,
                       'asciiHits': len(re.findall(b'frida', data, re.I)),
                       'utf16LEHits': len(re.findall(b'f\0r\0i\0d\0a\0', data, re.I))}
                scanned.append(row)
                if row['asciiHits'] or row['utf16LEHits']:
                    violations.append(row)
                if name.endswith('.so') and hashlib.sha256(data).digest() != clean_digest:
                    raise RuntimeError('Wheel extension differs from audited staged extension')
    if not any(r['member'].endswith('.so') for r in scanned) or not any(r['member'].endswith('.js') for r in scanned):
        raise RuntimeError('Expected native extension and injected JS assets are missing')
    (stage / 'wheel-audit.json').write_text(json.dumps({'scope': '.so and .js wheel members',
        'passed': not violations, 'files': scanned}, indent=2))
    if violations:
        raise RuntimeError('Wheel keyword audit failed; retained stage: ' + str(stage))
    shutil.copy2(report, wheels / 'native-audit.json')
    shutil.copy2(stage / 'wheel-audit.json', wheels / 'wheel-audit.json')
    shutil.copy2(source / 'deps/sdk-macos-arm64/JPROBE-SDK-AUDIT.json', wheels / 'SDK-AUDIT.json')
    (wheels / 'SHA256SUMS.txt').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in entries))
    dist.parent.mkdir(parents=True, exist_ok=True)
    # Directory rename atomically refuses to replace a nonempty destination.
    os.rename(wheels, dist)
    print('Published audited wheels:', dist)


if __name__ == '__main__':
    main()
