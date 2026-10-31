"""Rebuild brand-bearing SDK dependencies from the pinned upstream sources."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import subprocess
import sys

BASE = Path('/home/jim/jprobe')
SOURCE = BASE / 'full-source'
sys.path.insert(0, str(SOURCE))
from releng import deps
from releng.machine_spec import MachineSpec

parser = argparse.ArgumentParser()
parser.add_argument('host', choices=['android-arm64', 'android-arm', 'linux-x86_64', 'linux-x86'])
args = parser.parse_args()
os.environ['ANDROID_NDK_ROOT'] = str(BASE / 'toolchains/android-ndk-r29')
os.environ['GIT_CONFIG_COUNT'] = '1'
os.environ['GIT_CONFIG_KEY_0'] = 'http.https://github.com.proxy'
os.environ['GIT_CONFIG_VALUE_0'] = ''
deps.compute_job_count = lambda memory: min(8, os.cpu_count() or 1)

class NamedBuilder(deps.Builder):
    def _get_builddir_container(self):
        return self._workdir / ('_sdk-' + self._host_machine.identifier + '.tmp')

    def _get_outdir(self):
        return self._workdir / ('_sdk-' + self._host_machine.identifier + '.out')

    def _resolve_package(self, pkg):
        pkg = super()._resolve_package(pkg)
        if pkg.identifier == 'v8':
            pkg = dataclasses.replace(pkg, options=[dataclasses.replace(option,
                value=option.value.replace('-Dembedder_string=-frida', '-Dembedder_string=-jprobe'))
                for option in pkg.options])
        return pkg

    def _clone_repo_if_needed(self, pkg):
        super()._clone_repo_if_needed(pkg)
        root = self._get_sourcedir(pkg)
        if pkg.identifier == 'tinycc':
            for path in [root / 'VERSION', root / 'meson.build']:
                if path.exists():
                    before = path.read_text()
                    after = before.replace('0.9.28rc-frida', '0.9.28rc-jprobe')
                    if after != before:
                        path.write_text(after)
        record = {'package': pkg.identifier, 'pinnedCommit': pkg.version,
                  'actualCommit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()}
        (self._cachedir / (pkg.identifier + '-source.json')).write_text(json.dumps(record, indent=2))

    def _call_meson(self, argv, *args, **kwargs):
        if argv[0] == 'install':
            super()._call_meson(['compile', '-j8'], *args, **kwargs)
            argv = ['install', '--no-rebuild', *argv[1:]]
        return super()._call_meson(argv, *args, **kwargs)

build_machine = MachineSpec.parse('linux-x86') if args.host == 'android-arm' else MachineSpec.make_from_local_system()
if args.host == 'android-arm':
    os.environ['CC_FOR_BUILD'] = 'gcc -m32 -fcf-protection=none'
    os.environ['CXX_FOR_BUILD'] = 'g++ -m32 -fcf-protection=none'
builder = NamedBuilder(deps.Bundle.SDK, build_machine, MachineSpec.parse(args.host), True)
builder._cachedir = BASE / 'sdk-rebuild'
builder._workdir = builder._cachedir / 'src'
artifact = builder.build(None, set(), {'glib', 'tinycc', 'v8'}, '20261030')
print('SDK artifact:', artifact, flush=True)
