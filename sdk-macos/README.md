# macOS ARM64 custom SDK

Exact GLib, TinyCC, V8 and Abseil patches and pinned source identities from the
completed SDK build are retained here. Existing unmodified SDK dependencies
were copied from the 20261030 bundle. Licenses and upstream notices are retained.

Workspace layout: `workspace/jprobe/` is this repository and
`workspace/upstream/` is the prepared pinned source. From `workspace/`, run:

```sh
python3.13 jprobe/scripts/rebuild_macos_sdk.py --v8-jobs 2
```

This uses `jprobe/sdk-r5/glib.patch` plus the source transformations in the
builder; it does not apply the exact snapshots here a second time. It requires
the base SDK and macOS toolchain already present in `upstream/deps/`.
Output: `mac-sdk-rebuild/sdk-macos-arm64.tar.xz`. The active SDK is not replaced
automatically. Install the audited output into a prepared build workspace
before using `scripts/build_macos.sh`.

GLib/TinyCC/V8 archive scans passed; native GLib date formatting, TinyCC
compilation, Abseil stream-width formatting and V8 execution were verified.
V8 and its snapshot were rebuilt together. The marker in
`../evidence/r7/macos-SDK-AUDIT.json` covers its seven explicitly listed
archives, not every dependency in the SDK. The final Mac extension's accepted
`Friday` occurrence comes from libc++, not these rebuilt archives.
