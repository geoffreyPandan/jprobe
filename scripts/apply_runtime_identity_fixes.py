#!/usr/bin/env python3
"""Apply the reviewed runtime/build identity fixes to an already prepared tree.

This changes source only. It does not build, sign, install, or touch a device.
"""
import argparse
from pathlib import Path

PREFIX_MARKER = "# Cover dependencies and separate compatibility builds as well as this project."
PREFIX_LANGUAGES = """jp_prefix_languages = ['c', 'cpp']
if host_machine.system() == 'darwin'
  add_languages('objc', 'objcpp', native: false)
  jp_prefix_languages += ['objc', 'objcpp']
endif

"""
GO_ANCHOR = '    go_sources = [str(f.relative_to(base_dir)) for f in inputs if f.suffix == ".go"]'
GO_PATCH = '''    # Keep the local checkout path out of Go module build metadata.
    go_mod = priv_dir / "go.mod"
    local_tsc = base_dir.parents[4] / "go-rename" / "tsc"
    if local_tsc.is_dir():
        import re
        relative_tsc = os.path.relpath(local_tsc, priv_dir)
        contents = re.sub(r"(?m)^replace github\\.com/jprobe/TypeScript/tsc => .+$",
                          "replace github.com/jprobe/TypeScript/tsc => " + relative_tsc,
                          go_mod.read_text())
        go_mod.write_text(contents)

'''


def replace_once(text, old, new, label):
    if old in text:
        if text.count(old) != 1 or new in text:
            raise ValueError("Unexpected duplicate/partial patch in " + label)
        return text.replace(old, new)
    if new not in text:
        raise ValueError("Expected source expression is missing in " + label)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()
    root = args.upstream.resolve(strict=True)
    planned = {}
    for relative in ["meson.build", "subprojects/frida-core/meson.build", "subprojects/frida-gum/meson.build"]:
        path = root / relative
        text = path.read_text()
        if PREFIX_LANGUAGES not in text:
            if "jp_prefix_languages" in text or text.count(PREFIX_MARKER) != 1:
                raise ValueError("Unexpected prefix-map source in " + str(path))
            text = text.replace(PREFIX_MARKER, PREFIX_LANGUAGES + PREFIX_MARKER)
        old = "language: ['c', 'cpp'])"
        new = "language: jp_prefix_languages)"
        text = replace_once(text, old, new, str(path))
        planned[path] = text

    core = root / "subprojects/frida-core"
    scheduler = root / "subprojects/frida-gum/bindings/gumjs/gumscriptscheduler.c"
    planned[scheduler] = replace_once(scheduler.read_text(),
        'g_thread_new ("gum-js-loop",', 'g_thread_new ("jp-js-loop",', str(scheduler))

    for relative in ["src/darwin/jprobe-helper.plist", "src/darwin/jprobe-helper.xcent"]:
        path = core / relative
        text = path.read_text()
        if "frida" not in text.lower() and "jprobe" not in text.lower():
            raise ValueError("Expected helper identity is absent in " + str(path))
        planned[path] = text.replace("Frida", "Jprobe").replace("frida", "jprobe")

    for relative, old, new in [
        ("src/barebone/vz-physical-memory.vala", "frida-core needs root", "jprobe-core needs root"),
        ("src/darwin/jprobe-helper-process.vala", "https://github.com/jprobe/frida-core/issues/524",
         "https://github.com/geoffreyPandan/jprobe/issues"),
    ]:
        path = core / relative
        planned[path] = replace_once(path.read_text(), old, new, str(path))

    backend = core / "src/compiler/build-backend.py"
    text = backend.read_text()
    if GO_PATCH not in text:
        if "relative_tsc" in text or text.count(GO_ANCHOR) != 1:
            raise ValueError("Unexpected or partial Go local-path patch in " + str(backend))
        text = text.replace(GO_ANCHOR, GO_PATCH + GO_ANCHOR)
    planned[backend] = text

    # All expected patterns have been checked before writing any file.
    for path, text in planned.items():
        if path.read_text() != text:
            path.write_text(text)
            print("Patched", path)
        else:
            print("Already patched", path)


if __name__ == "__main__":
    main()
