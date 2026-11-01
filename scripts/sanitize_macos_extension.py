#!/usr/bin/env python3
"""Strip non-global Mach-O symbols, remove unused build RPATH, and re-sign a copy.

No runtime strings are rewritten. Remaining keyword hits cause an audit failure
only with --require-zero; their offsets are always included in the JSON report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

BUILD_RPATH = "@loader_path/../../frida-core/src/api"
DYLIB_COMMANDS = {0xC, 0x18, 0x80000018, 0x1F, 0x8000001F, 0x20, 0x23, 0x80000023}


def macho_commands(path):
    data = path.read_bytes()
    if data[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError("Expected a thin little-endian 64-bit Mach-O extension")
    _, cpu, subtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack_from("<8I", data)
    if filetype != 8:
        raise ValueError("Expected MH_BUNDLE (Python extension), not an executable/library")
    offset = 32
    commands = []
    for _ in range(ncmds):
        command, size = struct.unpack_from("<II", data, offset)
        if size < 8 or offset + size > 32 + sizeofcmds:
            raise ValueError("Invalid Mach-O load command bounds")
        entry = {"command": command, "size": size, "offset": offset}
        if command in DYLIB_COMMANDS or command == 0x8000001C:
            relative = struct.unpack_from("<I", data, offset + 8)[0]
            if relative >= size:
                raise ValueError("Invalid Mach-O load-command string offset")
            entry["name"] = data[offset + relative:offset + size].split(b"\0", 1)[0].decode()
        commands.append(entry)
        offset += size
    return commands


def scan(path):
    data = path.read_bytes()
    return {"path": str(path), "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "rawAsciiCaseInsensitiveOffsets": [m.start() for m in re.finditer(b"frida", data, re.I)],
            "rawUtf16LECaseInsensitiveOffsets": [m.start() for m in re.finditer(b"f\0r\0i\0d\0a\0", data, re.I)]}


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--require-zero", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    target = args.output.resolve()
    if source == target or target.exists():
        raise ValueError("Output must be a new path, distinct from the source")
    if args.report.exists():
        raise ValueError("Report path already exists")
    commands = macho_commands(source)
    rpaths = [c["name"] for c in commands if c["command"] == 0x8000001C]
    dependencies = [c["name"] for c in commands if c["command"] in DYLIB_COMMANDS]
    if BUILD_RPATH in rpaths and any(name.startswith("@rpath/") for name in dependencies):
        raise ValueError("Cannot prove obsolete build RPATH is unused: @rpath dependency present")
    before = scan(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    run("strip", "-x", str(target))
    removed = []
    if BUILD_RPATH in rpaths:
        run("install_name_tool", "-delete_rpath", BUILD_RPATH, str(target))
        removed.append(BUILD_RPATH)
    run("codesign", "--force", "--sign", "-", str(target))
    run("codesign", "--verify", "--strict", str(target))
    after_commands = macho_commands(target)
    after_dependencies = [c["name"] for c in after_commands if c["command"] in DYLIB_COMMANDS]
    if dependencies != after_dependencies:
        raise ValueError("Runtime dynamic-library dependency list changed")
    exports = run("nm", "-gU", str(target))
    if "_PyInit__jprobe" not in exports:
        raise ValueError("Expected Python extension initialization export is missing")
    after = scan(target)
    zero = not after["rawAsciiCaseInsensitiveOffsets"] and not after["rawUtf16LECaseInsensitiveOffsets"]
    report = {"actions": ["strip -x", "remove unused exact build RPATH", "ad-hoc codesign"],
              "removedRpaths": removed, "dynamicDependenciesUnchanged": True,
              "pythonInitExportRetained": True, "signatureVerified": True,
              "runtimeStringsRewritten": False, "zeroRawKeywordHits": zero,
              "before": before, "after": after}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(target), "asciiHitsBefore": len(before["rawAsciiCaseInsensitiveOffsets"]),
                      "asciiHitsAfter": len(after["rawAsciiCaseInsensitiveOffsets"]),
                      "utf16HitsAfter": len(after["rawUtf16LECaseInsensitiveOffsets"]),
                      "zeroRawKeywordHits": zero, "report": str(args.report)}, indent=2))
    if args.require_zero and not zero:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
