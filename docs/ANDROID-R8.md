# Android R8 candidate

R7 still created GLib worker threads named `gmain` and `gdbus`. On the lab
device MobiKwik 23.75.1 / 2290 reported both names in its native Frida event.
R8 applies `patches/glib-worker-thread-names-r8.patch` to GLib, changing the
thread names to `jp-main` and `jp-ipc`. Exported GLib APIs remain unchanged.

## Build from the prepared Linux VM

The helper requires the R7 checkout, the matching GLib source and build caches,
NDK r29, Go, Node 24.22.2 and the original installed Android SDK archives.
It is a one-time incremental build from an unmodified R7 cache:

```sh
python3 scripts/build_android_thread_names_r8.py "$JPROBE_BUILD_ROOT" \
  "$JPROBE_BUILD_ROOT/candidates/thread-names-r8" \
  --patch patches/glib-worker-thread-names-r8.patch
```

It saves the original GLib files and archive hashes, patches the shared SDK
source/build caches, and copies the rebuilt libraries into an isolated R8 SDK.
The original installed SDK archives and R7 candidate are retained. The shared
GLib source and incremental build cache remain changed; do not rerun against
that state as if it were a clean R7 cache. Build logs and before/after source
copies are stored under the candidate directory.

## Verification on 2026-11-01

- ARM64 server/inject/agent/gadget and ARM32 agent/gadget built successfully.
- All six artifacts have zero ASCII case-insensitive `frida` and UTF-16LE
  `frida` matches. Exact NUL-delimited `gdbus`, `gmain`, and `gum-js-loop`
  string counts are zero. This does not mean all GLib symbol names vanished.
- VM and downloaded artifact SHA-256 values match; see
  [artifact audit](../evidence/r8/artifact-audit.json).
- The phone loaded the matching R8 agent from a separate directory; external
  `/proc/<pid>/task/*/comm` inspection observed `jp-main` and `jp-ipc`.
- With the same Custom ROM and Root response scripts, an R7 control reported
  `thread: gdbus`. The R8 comparison had no corresponding Frida queue event
  before it terminated. Its Java script did not suppress Frida indications.
- These initial comparisons still terminated with signal 11; another run had
  an ART crash. The GLib change alone does not fix the remaining application
  startup checks. ARM32 runtime and Gadget were not tested.

## Combined startup script

The subsequent [startup script](../examples/mobikwik/README.md) handles the
additional boot-state Custom ROM branch, the Zygisk native termination policy,
and the application's separate RootChecker countdown dialog. Completed runs
and exact script hashes are recorded in `evidence/r8/startup-validation.json`.
The delivered script passed two app cold starts, each observed for at least
120 seconds with the same PID and MobiKwik in the foreground. The second run
skipped the app's VPN warning and reached the phone-entry onboarding screen.
The instrumented comparison observed 24 method inspections and no native
Custom ROM or Frida event; neither popup was suppressed by the Java hook.
This is bounded startup verification, not a claim of general nondetection or
successful login/payment.

For isolated testing the server supports `--directory re.jprobe.server.r8`
and a separate listen port. The comparison used `JPROBE_AGENT_FILE_MODE=1`.
