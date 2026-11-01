#!/usr/bin/env python3
"""Apply the pinned kit and macOS fixes to a clean checkout; does not build.

Usage: python3 prepare_macos_source.py UPSTREAM KIT [--workspace WORKSPACE]
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess

PINNED = {
    "root": "f74818ada177756bd95c26235cdd26ebe4f07e76",
    "frida-core": "f91556129517937e82831458d10f6b8f4ca06dbb",
    "frida-gum": "5ebe3aeccab8dcd4b727378dab67fb15fa8a3cca",
    "frida-python": "c6862934002a1835c51cd6a7ca4d7b949c968971",
    "frida-tools": "a8c12cef7f728812bc8c70197505e8f40e1c26e4",
    "idun": "eaf98270beab0ecf174e611d99036db6843a1865",
}
TSC = "github.com/frida/TypeScript/tsc@v0.0.0-20260906185614-e00a6a37c16e"
TSC_SUM = "h1:78BFgtMGOTP1A1/N1aoGpRO6C2kfjiPO2dk+G+ZPcI4="


def renamed(data):
    return data.replace(b"frida", b"jprobe").replace(b"Frida", b"Jprobe").replace(b"FRIDA", b"JPROBE")


def output(argv, **kwargs):
    return subprocess.check_output(argv, text=True, **kwargs).strip()


def project_dir(upstream, name):
    return upstream if name == "root" else upstream / "subprojects" / name


def prepare_tsc(workspace):
    env = os.environ.copy()
    env.update(GOMODCACHE=str(workspace / "go-download-cache"),
               GOCACHE=str(workspace / "go-build-cache"),
               GOPROXY=env.get("GOPROXY", "https://proxy.golang.org"),
               GOTOOLCHAIN=env.get("GOTOOLCHAIN", "auto"))
    module = json.loads(output(["go", "mod", "download", "-json", TSC], cwd=workspace, env=env))
    if module.get("Error") or module.get("Sum") != TSC_SUM:
        raise RuntimeError("Pinned TypeScript module download/hash verification failed: " + str(module))
    source = Path(module["Dir"])
    target = workspace / "go-rename" / "tsc"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copytree(source, target)
        for path in [target, *target.rglob("*")]:
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
            if path.is_file():
                data = path.read_bytes()
                if b"\0" not in data:
                    path.write_bytes(renamed(data))
    # Refuse to reuse an unrelated or locally changed tree.
    for path in source.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            expected = data if b"\0" in data else renamed(data)
            installed = target / path.relative_to(source)
            if not installed.is_file() or installed.read_bytes() != expected:
                raise RuntimeError("Existing TypeScript copy differs: " + str(installed))
    (workspace / "go-rename" / "tsc-source.json").write_text(json.dumps(module, indent=2) + "\n")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("kit", type=Path)
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args()
    upstream = args.upstream.resolve(strict=True)
    kit = args.kit.resolve(strict=True)
    workspace = (args.workspace or upstream.parent).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if json.loads((kit / "upstream-commits.json").read_text()) != PINNED:
        raise RuntimeError("Kit commit manifest does not match the pinned release")
    # Validate all six commits and clean worktrees before changing source files.
    for name, expected in PINNED.items():
        target = project_dir(upstream, name)
        actual = output(["git", "-C", str(target), "rev-parse", "HEAD"])
        if actual != expected:
            raise RuntimeError(f"{name}: expected {expected}, got {actual}")
        if output(["git", "-C", str(target), "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none"]):
            raise RuntimeError(f"{name}: checkout must be clean before preparation")
        print(f"Verified {name}: {actual}", flush=True)
    tsc = prepare_tsc(workspace)
    for name in PINNED:
        target = project_dir(upstream, name)
        patch = kit / "patches" / (name + ".patch")
        for line in patch.read_text().splitlines():
            if not line.startswith("--- "):
                continue
            old = shlex.split(line[4:])[0]
            if old == "/dev/null":
                continue
            if not old.startswith("a/"):
                raise RuntimeError("Unexpected patch path: " + old)
            relative = Path(old[2:])
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError("Unsafe patch path: " + old)
            path = target / relative
            if not path.is_file():  # Gitlinks/submodules are directories.
                continue
            if path.is_symlink():
                raise RuntimeError("Refusing to normalize a symlink: " + str(path))
            data = path.read_bytes()
            if b"\r\n" in data:
                path.write_bytes(data.replace(b"\r\n", b"\n"))
                print("Normalized CRLF:", path, flush=True)
    subprocess.run(["bash", str(kit / "apply-source.sh"), str(upstream)], check=True)
    bindgen = upstream / "subprojects/frida-python/frida-bindgen"
    for source in (bindgen / "frida_bindgen_core").rglob("*"):
        if not source.is_file() or "__pycache__" in source.parts:
            continue
        target = bindgen / "jprobe_bindgen_core" / source.relative_to(bindgen / "frida_bindgen_core")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = renamed(source.read_bytes())
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError("Kit bindgen file differs from renamed pinned source: " + str(target))
        target.write_bytes(data)
    core = upstream / "subprojects/frida-core"
    for folder in ("src", "lib", "server", "tests"):
        for path in (core / folder).rglob("*.m"):
            data = renamed(path.read_bytes())
            # These generated/platform header filenames retain their original name.
            data = data.replace(b'#include "jprobe-tvos.h"', b'#include "frida-tvos.h"')
            data = data.replace(b'#include "jprobe-core.h"', b'#include "frida-core.h"')
            path.write_bytes(data)
    go_mod = core / "src/compiler/go.mod"
    lines = go_mod.read_text().splitlines()
    prefix = "replace github.com/jprobe/TypeScript/tsc =>"
    replacement = prefix + " " + json.dumps(str(tsc))
    if sum(line.startswith(prefix) for line in lines) != 1:
        raise RuntimeError("Expected one TypeScript replacement in compiler/go.mod")
    go_mod.write_text("\n".join(replacement if line.startswith(prefix) else line for line in lines) + "\n")
    print("Prepared macOS source:", upstream)
    print("Local TypeScript dependency:", tsc)


if __name__ == "__main__":
    main()
