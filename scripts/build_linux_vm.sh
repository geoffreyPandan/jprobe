#!/usr/bin/env bash
# Linux client build entry point from the prepared VM workspace.
set -euo pipefail
if [[ $# != 1 ]]; then
  echo 'Usage: build_linux_vm.sh PREPARED_BASE_WORKSPACE' >&2
  exit 2
fi
base=$(cd -- "$1" && pwd)
test -f "$base/full-source/configure"
test -f "$base/go-rename/tsc/go.mod"
export PATH="$base/toolchains/go/bin:$PATH"
export GOTOOLCHAIN=local
export JPROBE_VERSION=17.25.0 FRIDA_VERSION=17.25.0
command -v node >/dev/null
mkdir -p "$base/full-client-build"
cd "$base/full-client-build"
if [[ ! -f build.ninja ]]; then
  "$base/full-source/configure" --enable-jprobe-python --enable-jprobe-tools \
    --disable-server --disable-gadget --disable-inject > "$base/full-client-configure.log" 2>&1
fi
export PATH="$base/full-source/deps/toolchain-linux-x86_64/bin:$PATH"
python3 "$base/full-source/releng/meson/meson.py" compile -j8 > "$base/full-client-build.log" 2>&1
