# Build a native macOS jprobe client

This guide builds the Python client and command-line tools from the pinned
source kit. It works as a starting procedure for Apple Silicon (`arm64`) and
Intel (`x86_64`) Macs. The published Linux wheel cannot be installed on macOS.
This macOS build has not yet been run on a Mac, so keep the verification steps.

## 1. Prepare macOS

Install Xcode Command Line Tools and Homebrew. In Terminal:

```sh
xcode-select --install
brew install git python@3.12 node go ninja pkg-config
uname -m
```

`uname -m` should print `arm64` on Apple Silicon or `x86_64` on Intel. Use a
native Terminal and native Homebrew for that architecture. Make at least 30 GB
of free disk space available; the upstream source and build dependencies are
much larger than this patch kit.

## 2. Fetch the exact source

```sh
workdir="$HOME/jprobe-build"
mkdir -p "$workdir"
cd "$workdir"
git clone https://github.com/geoffreyPandan/jprobe.git kit
git clone https://github.com/frida/frida.git upstream
git -C upstream checkout f74818ada177756bd95c26235cdd26ebe4f07e76
git -C upstream submodule update --init --recursive
bash "$workdir/kit/apply-source.sh" "$workdir/upstream"
```

The apply script checks the exact commits of the root and five changed
subprojects. If one differs, stop and inspect the checkout instead of forcing
the patch.

## 3. Build the client

```sh
python3.12 -m venv "$workdir/venv"
source "$workdir/venv/bin/activate"
python -m pip install --upgrade pip setuptools wheel

source_dir="$workdir/upstream"
build_dir="$workdir/build-macos-client"
mkdir -p "$build_dir" "$workdir/dist"
cd "$build_dir"
export JPROBE_VERSION=17.25.0
"$source_dir/configure" \
  --enable-jprobe-python --enable-jprobe-tools \
  --disable-server --disable-gadget --disable-inject
python "$source_dir/releng/meson/meson.py" compile \
  -C "$build_dir" -j "$(sysctl -n hw.ncpu)"
```

If the build requests an Apple signing identity, inspect available identities
with `security find-identity -v -p codesigning` and set `MACOS_CERTID` to the
identity hash before rerunning the build. A certificate is not needed merely
to SSH into the Ubuntu VM or download the release files.

## 4. Package and install macOS wheels

```sh
client_package="$build_dir/subprojects/frida-python/jprobe"
extension=$(find "$client_package" -maxdepth 1 -name '_jprobe*.so' -print -quit)
test -n "$extension" || { echo 'Native client extension was not built' >&2; exit 1; }
test -f "$client_package/__init__.py" || { echo 'Generated Python package is missing' >&2; exit 1; }
export JPROBE_EXTENSION="$extension"
python -m pip wheel --no-deps --no-build-isolation \
  -w "$workdir/dist" "$source_dir/subprojects/frida-python"

tools_source="$source_dir/subprojects/frida-tools"
test ! -e "$tools_source/build" || { echo 'Tools build path already exists' >&2; exit 1; }
ln -s "$build_dir/subprojects/frida-tools" "$tools_source/build"
export JPROBE_TOOLS_VERSION=14.11.0+jprobe
python -m pip wheel --no-deps --no-build-isolation \
  -w "$workdir/dist" "$tools_source"

python -m pip install "$workdir"/dist/jprobe-17.25.0-*.whl \
  "$workdir"/dist/jprobe_tools-*.whl
python -m pip check
python -c 'import jprobe; print(jprobe.__version__)'
jprobe-ps --help
```

The wheel in `dist/` should have a `macosx` platform tag for the Mac's
architecture. The Java bridge package in the Linux release is a separate
component; these commands build the Python client and CLI.

## 5. Check the keyword and connect to the Pixel 6

Run this local binary and injected-script scan. Treat any hit as a build that
needs investigation; do not publish it as a verified macOS release.

```sh
python - <<'PY'
from pathlib import Path
import jprobe
import jprobe_tools

roots = [Path(jprobe.__file__).parent, Path(jprobe_tools.__file__).parent]
targets = [p for root in roots for p in root.rglob('*')
           if p.is_file() and (p.suffix == '.so' or p.suffix == '.js')]
hits = [str(p) for p in targets if b'frida' in p.read_bytes().lower()]
print('Scanned files:', len(targets))
print('Raw keyword hits:', hits)
if hits:
    raise SystemExit(1)
PY
```

The Pixel 6 server currently runs through the Ubuntu VM. From a second Mac
Terminal, forward the VM's existing ADB port:

```sh
ssh -N -L 35000:127.0.0.1:35000 jim@192.168.191.130
```

Keep that SSH session open. In the first Terminal, with the virtual environment
active:

```sh
jprobe-ps -H 127.0.0.1:35000
```

Replace the VM address if it has changed. The VM must still have the phone
attached, its `jprobe-server` running, and ADB forwarding port `35000`.
Successful import and process listing verify basic operation; the Linux
release's 108 functional cases and keyword audit do not prove that this new
macOS build has the same results. Save the build log, wheel names, keyword
scan, and connection output for review.
