#!/usr/bin/env python3
"""Rebuild the pinned macOS SDK components in an isolated output directory.

Does not install into the active upstream SDK. Run using venv-macos/bin/python.
"""
import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "upstream"
KIT = Path(__file__).resolve().parents[1] / "sdk-r5"
WORK = ROOT / "mac-sdk-rebuild"
BASE_SDK = SOURCE / "deps/sdk-macos-arm64"
sys.path.insert(0, str(SOURCE))
from releng import deps
from releng.machine_spec import MachineSpec


def replace_once(path, old, new):
    text = path.read_text()
    if old in text:
        if text.count(old) != 1:
            raise RuntimeError(f"Unexpected occurrence count in {path}")
        path.write_text(text.replace(old, new))
    elif new not in text:
        raise RuntimeError(f"Expected source was not found in {path}")


def audit_prefix(prefix):
    """Strip debug metadata, then audit the rebuilt runtime libraries only."""
    libraries = [prefix / "lib" / name for name in (
        "libglib-2.0.a", "libgobject-2.0.a", "libgio-2.0.a",
        "libgmodule-2.0.a", "libgthread-2.0.a", "libtcc.a")]
    v8_libraries = sorted((prefix / "lib").glob("libv8-*.a"))
    if not v8_libraries:
        raise RuntimeError("No rebuilt V8 archive to audit")
    libraries += v8_libraries
    hashes = {}
    for library in libraries:
        subprocess.run(["strip", "-S", str(library)], check=True,
                       capture_output=True)
        data = library.read_bytes()
        lowered = data.lower()
        count = lowered.count(b"frida") + lowered.count("frida".encode("utf-16le"))
        if count:
            raise RuntimeError(f"SDK audit failed: {library.name}: {count} raw occurrences")
        hashes[library.relative_to(prefix).as_posix()] = hashlib.sha256(data).hexdigest()
    marker = {"schemaVersion": 1, "host": "macos-arm64", "auditPassed": True,
              "libraries": hashes, "scope": "rebuilt archives after strip -S; raw case-insensitive ASCII and UTF-16LE frida scan"}
    (prefix / "JPROBE-SDK-AUDIT.json").write_text(json.dumps(marker, indent=2) + "\n")
    (WORK / "audit" / "sdk-final.json").write_text(json.dumps(marker, indent=2) + "\n")


class NamedBuilder(deps.Builder):
    v8_jobs = 2

    def _prepare(self):
        original = deps.ensure_toolchain
        deps.ensure_toolchain = lambda *a, **kw: (SOURCE / "deps/toolchain-macos-arm64", deps.SourceState.PRISTINE)
        try:
            super()._prepare()
        finally:
            deps.ensure_toolchain = original

    def _deploy_base(self, packages_to_build):
        prefix = self._get_prefix(self._host_machine)
        if not prefix.exists():
            shutil.copytree(BASE_SDK, prefix)
            for file in prefix.rglob("*.pc"):
                text = file.read_text().replace("${frida_sdk_prefix}", str(prefix))
                file.write_text(text)
            for identifier in packages_to_build:
                manifest = prefix / "manifest" / (identifier + ".pkg")
                if manifest.exists():
                    for entry in manifest.read_text().splitlines():
                        target = prefix / entry
                        if target.is_file() or target.is_symlink():
                            target.unlink()
                    manifest.unlink()

    def _resolve_package(self, pkg):
        pkg = super()._resolve_package(pkg)
        options = list(pkg.options)
        if pkg.identifier == "v8":
            options = [dataclasses.replace(o, value=o.value.replace("-Dembedder_string=-frida", "-Dembedder_string=-jprobe")) for o in options]
        return dataclasses.replace(pkg, options=options)

    def _clone_repo_if_needed(self, pkg):
        super()._clone_repo_if_needed(pkg)
        root = self._get_sourcedir(pkg)
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        if actual != pkg.version:
            raise RuntimeError(f"{pkg.identifier}: unexpected source commit {actual}")
        if pkg.identifier == "glib":
            patch = KIT / "glib.patch"
            if "get_weekday_five_name_translated" not in (root / "glib/gdatetime.c").read_text():
                subprocess.run(["git", "apply", str(patch)], cwd=root, check=True)
            replace_once(root / "meson.build", "glib_conf.set_quoted('GLIB_LOCALE_DIR', glib_localedir)",
                         "glib_conf.set_quoted('GLIB_LOCALE_DIR', '/usr/local/share/locale')")
            replace_once(root / "meson.build", "glib_conf.set_quoted('GLIB_LOCALSTATEDIR', glib_localstatedir)",
                         "glib_conf.set_quoted('GLIB_LOCALSTATEDIR', '/var')")
            replace_once(root / "meson.build", "glib_conf.set_quoted('GLIB_RUNSTATEDIR', glib_runstatedir)",
                         "glib_conf.set_quoted('GLIB_RUNSTATEDIR', '/var/run')")
            for variable, value in [("glib_prefix / multiarch_libexecdir / 'gio-launch-desktop'", "'/usr/local/libexec/gio-launch-desktop'"),
                                    ("glib_giomodulesdir", "'/usr/local/lib/gio/modules'"),
                                    ("glib_localstatedir", "'/var'")]:
                replace_once(root / "gio/meson.build", '.format(' + variable + ')', '.format(' + value + ')')
        elif pkg.identifier == "tinycc":
            for name in ("VERSION", "meson.build"):
                p = root / name
                if p.exists():
                    p.write_text(p.read_text().replace("0.9.28rc-frida", "0.9.28rc-jprobe"))
            replace_once(root / "meson.build", "cdata.set_quoted('CONFIG_TCCDIR', tccdir)",
                         "cdata.set_quoted('CONFIG_TCCDIR', '/usr/local/lib/jprobe/tcc')")
        elif pkg.identifier == "v8":
            path = root / "third_party/abseil-cpp/src/absl/time/internal/cctz/src/civil_time_detail.cc"
            # Keep one stream insertion: splitting insertions would change setw.
            patched = '{ std::string name("Fri"); name.append("day"); return os << name; }'
            if 'return os << "Fri" << "day";' in path.read_text():
                replace_once(path, 'return os << "Fri" << "day";', patched)
            else:
                replace_once(path, 'return os << "Friday";', patched)
        record = {"package": pkg.identifier, "sourceUrl": pkg.url, "pinnedCommit": pkg.version,
                  "actualCommit": actual}
        (WORK / (pkg.identifier + "-source.json")).write_text(json.dumps(record, indent=2))

    def _call_meson(self, argv, *args, **kwargs):
        if argv[0] == "install":
            jobs = self.v8_jobs if Path(kwargs["cwd"]).name == "v8" else 8
            super()._call_meson(["compile", f"-j{jobs}"], *args, **kwargs)
            argv = ["install", "--no-rebuild", *argv[1:]]
        return super()._call_meson(argv, *args, **kwargs)

    def _build_package_for_machine(self, pkg, machine):
        builddir = self._get_builddir(pkg, machine)
        if pkg.identifier != "v8" or not (builddir / "build.ninja").exists():
            return super()._build_package_for_machine(pkg, machine)
        # A full V8 rebuild is expensive. Resume only this isolated, configured
        # build; callers changing configuration must remove its build directory.
        menv = self._host_env if machine is self._host_machine else self._build_env
        self._call_meson(["compile", "-j", str(self.v8_jobs)], cwd=builddir,
                         env=menv, check=True)
        self._call_meson(["install"], cwd=builddir, env=menv, check=True)
        installed = json.loads(self._call_meson(["introspect", "--installed"],
                              cwd=builddir, env=menv, capture_output=True,
                              encoding="utf-8", check=True).stdout)
        prefix = self._get_prefix(machine)
        manifest = self._get_manifest_path(pkg, machine)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("\n".join(sorted(Path(p).relative_to(prefix).as_posix()
                                             for p in installed.values())) + "\n")

    def _package(self):
        audit_prefix(self._get_prefix(self._host_machine))
        return super()._package()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages", default="glib,tinycc,v8")
    parser.add_argument("--v8-jobs", type=int, default=2)
    args = parser.parse_args()
    packages = set(args.packages.split(","))
    if not packages <= {"glib", "tinycc", "v8"}:
        raise RuntimeError("Only pinned GLib, TinyCC, and V8 components are supported")
    WORK.mkdir(exist_ok=True)
    flags = f"-ffile-prefix-map={ROOT}=/src/jprobe -fdebug-prefix-map={ROOT}=/src/jprobe"
    for name in ("CFLAGS", "CXXFLAGS", "OBJCFLAGS"):
        os.environ[name] = " ".join(filter(None, [os.environ.get(name), flags]))
    os.environ["npm_config_registry"] = "https://registry.npmjs.org/"
    if args.v8_jobs < 1:
        parser.error("--v8-jobs must be positive")
    deps.compute_job_count = lambda memory: args.v8_jobs
    machine = MachineSpec.parse("macos-arm64")
    builder = NamedBuilder(deps.Bundle.SDK, machine, machine, True)
    builder.v8_jobs = args.v8_jobs
    builder._cachedir = WORK
    builder._workdir = WORK / "src"
    artifact = builder.build(["glib", "tinycc", "v8"], set(), packages, "20261030")
    print("Isolated SDK:", artifact)


if __name__ == "__main__":
    main()
