#!/usr/bin/env python3
"""Build R9 in a new directory using a prepared Linux R8 source and SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('base', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--patch', required=True, type=Path)
    args = parser.parse_args()
    base = args.base.resolve(strict=True)
    old = base / 'candidates/thread-names-r8/source'
    candidate = args.candidate.resolve()
    patch = args.patch.resolve(strict=True)
    candidate.mkdir(parents=True, exist_ok=False)
    status = {'state': 'PREPARING', 'baseline': str(old),
              'patchSha256': hashlib.sha256(patch.read_bytes()).hexdigest()}

    def record(state, **values):
        status.update(state=state, **values)
        temporary = candidate / 'status.tmp'
        temporary.write_text(json.dumps(status, indent=2) + '\n')
        temporary.replace(candidate / 'status.json')
        print(state, flush=True)

    try:
        record('PREPARING')
        source = candidate / 'source'
        source.mkdir()
        subprocess.run(['rsync', '-a', '--exclude=.git', '--exclude=/build',
                        '--exclude=/deps', str(old) + '/', str(source) + '/'], check=True)
        (source / 'deps').mkdir()
        libraries = {}
        for entry in (old / 'deps').iterdir():
            (source / 'deps' / entry.name).symlink_to(entry.resolve(), target_is_directory=True)
            if entry.name in ('sdk-android-arm', 'sdk-android-arm64'):
                for name in ('libv8-15.7.a', 'libtcc.a', 'libglib-2.0.a', 'libgio-2.0.a'):
                    path = entry / 'lib' / name
                    with path.open('rb') as stream:
                        libraries[str(path)] = hashlib.file_digest(stream, 'sha256').hexdigest()
        (candidate / 'sdk-sha256.json').write_text(json.dumps(libraries, indent=2) + '\n')
        gum = source / 'subprojects/frida-gum'
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=gum, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=gum, check=True)
        env = os.environ.copy()
        paths = [base / 'toolchains/go/bin',
                 Path.home() / '.local/share/nodejs/node-v24.22.2-linux-x64/bin',
                 source / 'deps/toolchain-linux-x86_64/bin']
        env['PATH'] = ':'.join(map(str, paths)) + ':' + env['PATH']
        env.update(ANDROID_NDK_ROOT=str(base / 'toolchains/android-ndk-r29'),
                   GOTOOLCHAIN='local', FRIDA_VERSION='17.25.0', JPROBE_VERSION='17.25.0')
        record('CONFIGURING')
        with (candidate / 'configure.log').open('w') as log:
            subprocess.run(['./configure', '--host=android-arm64', '--enable-server',
                            '--enable-gadget', '--enable-inject', '--disable-jprobe-tools',
                            '--disable-jprobe-python'], cwd=source, env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        record('BUILDING')
        with (candidate / 'build.log').open('w') as log:
            subprocess.run(['make', '-j8'], cwd=source, env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        for name, expected in libraries.items():
            with Path(name).open('rb') as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, name
        record('BUILT', source=str(source))
    except Exception as error:
        record('FAILED', error=str(error))
        raise


if __name__ == '__main__':
    main()
