#!/usr/bin/env python3
"""Copy the pinned local Go toolchain and patch its weekday source, without building.

Only the copy's src/time/format.go gains owner-write permission. The source
download cache and any globally installed Go toolchain remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat

TOOLCHAIN = "golang.org/toolchain@v0.0.1-go1.26.0.darwin-arm64"
ANCHOR = "var longDayNames = []string{\n"
OLD = '\t"Friday",\n'
NEW = "\tweekdayFiveName(),\n"
HELPER = """var weekdayFiveSuffix = [3]byte{'d', 'a', 'y'}

func weekdayFiveName() string {
\treturn "Fri" + string(weekdayFiveSuffix[:])
}

"""


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_patched(text):
    suffix = re.search(r"var weekdayFiveSuffix = \[3\]byte\{'d', 'a', 'y'\}", text)
    function = re.search(r'func weekdayFiveName\(\) string \{\s*return "Fri" \+ string\(weekdayFiveSuffix\[:\]\)\s*\}', text)
    return (suffix is not None and function is not None and text.count(NEW) == 1
            and OLD not in text and text.count(ANCHOR) == 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    source = workspace / "go-download-cache" / TOOLCHAIN
    target = workspace / "toolchains/go1.26-jprobe"
    if source.resolve() == target.resolve():
        raise ValueError("Source cache and output toolchain must be distinct")
    version = (source / "VERSION").read_text().splitlines()[0]
    if version != "go1.26.0":
        raise ValueError("Expected pinned Go 1.26.0, got " + version)
    original = source / "src/time/format.go"
    original_sha = sha(original)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, symlinks=True)
    elif target.is_symlink() or (target / "VERSION").read_bytes() != (source / "VERSION").read_bytes():
        raise ValueError("Existing toolchain is not the expected independent pinned copy")
    if sha(target / "bin/go") != sha(source / "bin/go"):
        raise ValueError("Existing copied Go executable differs from the pinned source")
    path = target / "src/time/format.go"
    text = path.read_text()
    if verify_patched(text):
        print("Weekday source already patched:", path)
    else:
        if sha(path) != original_sha or text.count(OLD) != 1 or text.count(ANCHOR) != 1:
            raise ValueError("Unexpected existing weekday source; refusing to overwrite")
        text = text.replace(OLD, NEW).replace(ANCHOR, HELPER + ANCHOR)
        if not verify_patched(text):
            raise ValueError("Weekday patch validation failed")
        path.chmod(path.stat().st_mode | stat.S_IWUSR)
        path.write_text(text)
        print("Patched copied weekday source:", path)
    if sha(original) != original_sha:
        raise ValueError("Source download cache changed unexpectedly")
    print(json.dumps({"toolchain": str(target), "version": version,
                      "originalWeekdaySha256": original_sha, "patchedWeekdaySha256": sha(path),
                      "sourceCacheUnchanged": True, "compiled": False}, indent=2))


if __name__ == "__main__":
    main()
