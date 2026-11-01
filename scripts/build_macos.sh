#!/usr/bin/env bash
# Usage: build_macos.sh [--reuse-build] [UPSTREAM] [WORKSPACE]
# See MACOS-REBUILD.md. This script does not rebuild the SDK or operate a device.
set -euo pipefail
reuse_build=0
if [[ ${1:-} == --reuse-build ]]; then reuse_build=1; shift; fi
if [[ $# -gt 2 ]]; then echo 'Usage: build_macos.sh [--reuse-build] [UPSTREAM] [WORKSPACE]' >&2; exit 2; fi
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
workspace=${2:-"$script_dir/../.."}
workspace=$(cd -- "$workspace" && pwd)
source_dir=${1:-"$workspace/upstream"}
source_dir=$(cd -- "$source_dir" && pwd)
venv_dir="$workspace/venv-macos-clean"
build_dir="$workspace/build-macos-clean"
dist_dir="$workspace/dist/macos-clean"
sdk_dir="$source_dir/deps/sdk-macos-arm64"
test "$(uname -s)" = Darwin && test "$(uname -m)" = arm64 || {
  echo 'This recipe requires native Apple Silicon macOS.' >&2; exit 1;
}
command -v python3.13 >/dev/null
test -f "$source_dir/subprojects/frida-python/jprobe/meson.build" || {
  echo 'Prepare pinned upstream with prepare_macos_source.py first.' >&2; exit 1;
}
test -f "$workspace/go-rename/tsc/go.mod" || {
  echo 'Missing pinned renamed TypeScript dependency.' >&2; exit 1;
}
python3.13 - "$source_dir" "$workspace" "$build_dir" "$dist_dir" "$reuse_build" <<'PY'
from pathlib import Path
import json, sys
source, workspace, build, dist = map(Path, sys.argv[1:5])
reuse = sys.argv[5] == '1'
if source.parent != workspace:
    raise SystemExit('UPSTREAM must be directly inside WORKSPACE for the local TypeScript layout')
if build.is_symlink() or dist.is_symlink():
    raise SystemExit('Refusing symlinked build/output directories')
if dist.exists() and any(dist.iterdir()):
    raise SystemExit('dist/macos-clean is not empty; archive it explicitly before producing another release')
if (build / 'build.ninja').is_file():
    if not reuse:
        raise SystemExit('Existing configured build: pass --reuse-build to reconfigure explicitly')
    files = json.loads((build / 'meson-info/intro-buildsystem_files.json').read_text())
    if str(source / 'meson.build') not in files:
        raise SystemExit('Existing build belongs to a different source checkout')
elif build.exists() and any(build.iterdir()):
    raise SystemExit('Incomplete nonempty build directory: inspect and preserve or relocate it explicitly')
PY
sdk_digest=$(python3.13 "$script_dir/verify_macos_sdk.py" "$sdk_dir")
python3.13 "$script_dir/apply_runtime_identity_fixes.py" "$source_dir"
python3.13 "$script_dir/prepare_go_toolchain.py" --workspace "$workspace"
if [[ ! -e "$venv_dir" ]]; then python3.13 -m venv "$venv_dir"; fi
test -x "$venv_dir/bin/python" || { echo 'Invalid venv-macos-clean' >&2; exit 1; }
"$venv_dir/bin/python" -c 'import sys; assert sys.version_info[:2] == (3, 13)'
source "$venv_dir/bin/activate"
python -m pip install 'pip==26.2.2' 'setuptools==84.2.1' 'wheel==0.48.0' 'packaging==26.3'

# Meson captures this environment in go-config.json during configuration.
export JPROBE_VERSION=17.25.0 JPROBE_TOOLS_VERSION=14.11.0+jprobe
export MACOS_CERTID="${MACOS_CERTID:--}"
export npm_config_registry=https://registry.npmjs.org/
export GOROOT="$workspace/toolchains/go1.26-jprobe"
export GOTOOLCHAIN=local
export GOMODCACHE="$workspace/go-download-cache"
export GOCACHE="$workspace/go-build-cache-clean"
export GOPROXY="${GOPROXY:-https://proxy.golang.org}"
export PATH="$GOROOT/bin:$PATH"
test "$(go env GOVERSION)" = go1.26.0 || { echo 'Unexpected Go toolchain' >&2; exit 1; }
mkdir -p "$build_dir" "$GOCACHE" "$workspace/logs"
log_dir=$(mktemp -d "$workspace/logs/macos-clean.XXXXXX")
exec > >(tee "$log_dir/build.log") 2>&1
printf 'Build log: %s\n' "$log_dir/build.log"
python - "$source_dir" "$build_dir" "$reuse_build" <<'PY'
from pathlib import Path
import os, sys
source, build = map(Path, sys.argv[1:3])
sys.path.insert(0, str(source))
from releng.meson_configure import configure
options = ['-Djprobe_python=enabled', '-Djprobe_tools=enabled',
           '-Dserver=disabled', '-Dgadget=disabled', '-Dinject=disabled',
           '-Dfrida-core:compat=disabled']
if sys.argv[3] == '1' and (build / 'build.ninja').is_file():
    options += ['--reconfigure', '--clearcache']
configure(source, build, environ=dict(os.environ), extra_meson_options=options)
PY
test "$(python "$script_dir/verify_macos_sdk.py" "$sdk_dir")" = "$sdk_digest" || {
  echo 'SDK marker changed during configuration' >&2; exit 1;
}
python - "$build_dir" "$workspace" <<'PY'
from pathlib import Path
import json, re, sys
build, workspace = map(Path, sys.argv[1:])
config = json.loads((build / 'subprojects/frida-core/go-config.json').read_text())
expected = {'GOROOT': str(workspace / 'toolchains/go1.26-jprobe'), 'GOTOOLCHAIN': 'local',
            'GOCACHE': str(workspace / 'go-build-cache-clean'),
            'GOMODCACHE': str(workspace / 'go-download-cache'),
            'npm_config_registry': 'https://registry.npmjs.org/'}
for key, value in expected.items():
    if config['env'].get(key) != value:
        raise SystemExit('Configured compiler environment mismatch: ' + key)
options = {o['name']: o['value'] for o in json.loads((build / 'meson-info/intro-buildoptions.json').read_text())}
for name, expected_value in [('jprobe_python', 'enabled'), ('jprobe_tools', 'enabled'),
                             ('server', 'disabled'), ('gadget', 'disabled'), ('inject', 'disabled'),
                             ('frida-core:compat', ['disabled'])]:
    if options.get(name) != expected_value:
        raise SystemExit('Configured option mismatch: ' + name)
npmrc = build / 'subprojects/frida-core/src/compiler/jprobe-compiler-backend.a.p/.npmrc'
if npmrc.is_symlink():
    raise SystemExit('Refusing to write through npmrc symlink')
npmrc.parent.mkdir(parents=True, exist_ok=True)
lines = npmrc.read_text().splitlines() if npmrc.exists() else []
lines = [line for line in lines if not re.match(r'\s*registry\s*=', line)]
npmrc.write_text('\n'.join(lines + ['registry=https://registry.npmjs.org/']) + '\n')
PY
python "$source_dir/releng/meson/meson.py" compile -C "$build_dir" -j4
python "$script_dir/package_macos_clean.py" "$source_dir" "$workspace"
printf 'Audited wheels: %s\n' "$dist_dir"
