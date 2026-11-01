#!/usr/bin/env bash
# Build an isolated R7 candidate from an existing, prepared r6d workspace.
set -euo pipefail
if [[ $# != 2 ]]; then
  echo 'Usage: build_android_vm.sh BASE_WORKSPACE NEW_CANDIDATE_DIRECTORY' >&2
  exit 2
fi
base=$(cd -- "$1" && pwd)
candidate=$2
kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
test ! -e "$candidate" || { echo 'Candidate directory already exists' >&2; exit 1; }
test -f "$base/full-source/subprojects/frida-gum/bindings/gumjs/gumscriptscheduler.c"
test -f "$base/go-rename/tsc/go.mod"
export ANDROID_NDK_ROOT=${ANDROID_NDK_ROOT:-"$base/toolchains/android-ndk-r29"}
test -d "$ANDROID_NDK_ROOT"
export PATH="$base/toolchains/go/bin:$PATH"
export GOTOOLCHAIN=local
export FRIDA_VERSION=17.25.0 JPROBE_VERSION=17.25.0
command -v node >/dev/null
for name in sdk-android-arm sdk-android-arm64 sdk-linux-x86 sdk-linux-x86_64 toolchain-linux-x86_64; do
  test -d "$base/full-source/deps/$name"
done
mkdir -p "$candidate/source"
candidate=$(cd -- "$candidate" && pwd)
rsync -a --exclude=.git --exclude=/build --exclude='/deps*' \
  "$base/full-source/" "$candidate/source/"
mkdir "$candidate/source/deps"
for name in sdk-android-arm sdk-android-arm64 sdk-linux-x86 sdk-linux-x86_64 toolchain-linux-x86_64; do
  ln -s "$base/full-source/deps/$name" "$candidate/source/deps/$name"
done
cd "$candidate/source"
git apply --check "$kit/patches/android-thread-name-r7.patch"
git apply "$kit/patches/android-thread-name-r7.patch"
./configure --host=android-arm64 --enable-server --enable-gadget --enable-inject \
  --disable-jprobe-tools --disable-jprobe-python > "$candidate/configure.log" 2>&1
make -j8 > "$candidate/build.log" 2>&1
echo "Built candidate in $candidate"
