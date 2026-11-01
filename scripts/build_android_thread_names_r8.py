#!/usr/bin/env python3
"""Build an isolated Android R8 candidate using a prepared VM's R7 and SDK caches."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('base', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--patch', type=Path, required=True)
    args = parser.parse_args()
    base = args.base.resolve(strict=True)
    candidate = args.candidate.resolve()
    patch = args.patch.resolve(strict=True)
    old_source = base / 'candidates/thread-name-r7/source'
    sdk_source = base / 'sdk-rebuild/src/glib'
    deps = base / 'full-source/deps'
    ninja = deps / 'toolchain-linux-x86_64/bin/ninja'
    hosts = ('android-arm64', 'android-arm')
    libraries = ('glib/libglib-2.0.a', 'gio/libgio-2.0.a')
    baseline = {}
    for host in hosts:
        for name in libraries:
            installed = deps / ('sdk-' + host) / 'lib' / Path(name).name
            built = base / 'sdk-rebuild/src' / ('_sdk-' + host + '.tmp') / host / 'glib' / name
            baseline[str(installed)] = sha(installed)
            if sha(built) != baseline[str(installed)]:
                raise RuntimeError('SDK cache differs from installed baseline: ' + str(built))
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=sdk_source, check=True)
    candidate.mkdir(parents=True, exist_ok=False)
    (candidate / 'baseline-sdk-sha256.json').write_text(json.dumps(baseline, indent=2) + '\n')
    shutil.copy2(patch, candidate / patch.name)
    for name in ('gio/gdbusprivate.c', 'glib/gmain.c'):
        dest = candidate / 'sdk-source-before' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sdk_source / name, dest)
    source = candidate / 'source'
    source.mkdir()
    subprocess.run(['rsync', '-a', '--exclude=.git', '--exclude=/build', '--exclude=/deps',
                    str(old_source) + '/', str(source) + '/'], check=True)
    new_deps = source / 'deps'
    new_deps.mkdir()
    for entry in (old_source / 'deps').iterdir():
        if entry.name in {'sdk-' + host for host in hosts}:
            shutil.copytree(entry.resolve(), new_deps / entry.name, symlinks=True)
        else:
            (new_deps / entry.name).symlink_to(entry.resolve(), target_is_directory=entry.is_dir())
    subprocess.run(['git', 'apply', str(patch)], cwd=sdk_source, check=True)
    env = os.environ.copy()
    node_bin = Path.home() / '.local/share/nodejs/node-v24.22.2-linux-x64/bin'
    env['PATH'] = ':'.join(map(str, (base / 'toolchains/go/bin', node_bin, ninja.parent))) + ':' + env['PATH']
    env.update(ANDROID_NDK_ROOT=str(base / 'toolchains/android-ndk-r29'), GOTOOLCHAIN='local',
               FRIDA_VERSION='17.25.0', JPROBE_VERSION='17.25.0', GIT_CONFIG_COUNT='1',
               GIT_CONFIG_KEY_0='http.https://github.com.proxy', GIT_CONFIG_VALUE_0='')
    changed = {}
    for host in hosts:
        build = base / 'sdk-rebuild/src' / ('_sdk-' + host + '.tmp') / host / 'glib'
        print('Rebuilding GLib:', host, flush=True)
        with (candidate / ('glib-' + host + '.log')).open('w') as log:
            subprocess.run([str(ninja), '-C', str(build), '-j8', *libraries],
                           env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        changed[host] = {}
        for name in libraries:
            target = new_deps / ('sdk-' + host) / 'lib' / Path(name).name
            shutil.copy2(build / name, target)
            changed[host][target.name] = sha(target)
    for name in ('gio/gdbusprivate.c', 'glib/gmain.c'):
        dest = candidate / 'sdk-source-after' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sdk_source / name, dest)
    for name, expected in baseline.items():
        if sha(Path(name)) != expected:
            raise RuntimeError('Baseline SDK changed unexpectedly: ' + name)
    (candidate / 'changed-sdk-sha256.json').write_text(json.dumps(changed, indent=2) + '\n')
    print('Configuring isolated R8 source', flush=True)
    with (candidate / 'configure.log').open('w') as log:
        subprocess.run(['./configure', '--host=android-arm64', '--enable-server', '--enable-gadget',
                        '--enable-inject', '--disable-jprobe-tools', '--disable-jprobe-python'],
                       cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    print('Building isolated R8 candidate', flush=True)
    with (candidate / 'build.log').open('w') as log:
        subprocess.run(['make', '-j8'], cwd=source, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    (candidate / 'build-complete.json').write_text(json.dumps({'source':str(source),'built':True}) + '\n')
    print('Build complete:', candidate, flush=True)


if __name__ == '__main__':
    main()
