# Android ARM64 regression harness

This harness tests the delivered server/client/Gadget artifacts. It does not patch
jprobe or detector results. It is intentionally confined to an explicitly selected
ADB device and fixture packages. Use a disposable emulator clone.

## Requirements and side effects

- macOS ARM64, working Python 3.13, Android SDK platform 32/build-tools 35.0.1,
  NDK 29.0.13113456 and JDK 17. Paths are checked by `build.py`.
- `venv-macos-clean` contains jprobe 17.25.0 and its matching tools/bridge.
- Official comparison uses `verification/jprobe-regression/upstream-env-313`
  containing Frida 17.25.0/tools 14.11.0 and the pinned official server.
- The host's default Python 3.14 was observed to have a broken expat linkage;
  use the verified Python 3.13 environment for runners and reports.
- Server suites require root; Gadget suites run as an ordinary app with no server
  and also support a root-disabled emulator.
- The runner installs/updates `dev.jprobe.lab`. Gadget tests reinstall
  `dev.jprobe.lab.gadget` and clear that fixture's data. Detection uses the fixed
  Fatdog APK. It force-stops only the relevant test packages.
- Unique device directories, checked server PID/port ownership, an advisory host
  device lock and dynamically allocated host forwarding ports prevent stale-server
  connections. No global `adb kill-server`, root hiding or system patches are used.

## Build and verify

From the workspace root (the parent of the jprobe repository):

```sh
venv-macos-clean/bin/python -m unittest discover \
  -s jprobe/tests/regression -p test_harness.py
venv-macos-clean/bin/python jprobe/tests/regression/build.py \
  --output verification/jprobe-regression/fixtures/base-v3
```

Build outputs refuse existing directories. Reuse a completed artifact or choose a
new output path; `--fixture` selects it. The generated keystore is a test-only key.
The fixture has Java/JNI arithmetic, overloads, exceptions, object lifecycle,
in-memory DEX and delayed-library targets. Its exported receiver supplies an
independent business result and UID. PID is checked before and after every check
so a crashed/restarted process cannot produce a false pass.

```sh
venv-macos-clean/bin/python jprobe/tests/regression/run.py \
  --serial 127.0.0.1:16480 --variant r8 --runtime qjs --suite functional \
  --server dist/android-thread-names-r8/artifacts/jprobe-server \
  --output verification/jprobe-regression/example-functional
```

Never reuse the example serial without querying MuMu/ADB; restarting a clone can
change its ADB port. `--runtime v8` tests V8. R7 uses
`dist/android-thread-name-r7/artifacts/jprobe-server`. `--file-mode default`
leaves the agent file-mode variable unset. The official variant must run under
the official Python environment.

## Suites

| Suite | Coverage |
|---|---|
| smoke | enumerate, attach, independent Java/JNI baseline, RPC, Java/Native hook and restore, spawn |
| functional | QJS/V8 semantics, memory, 64-bit native values, callbacks/errno, CModule, ARM64 code, Stalker, Java types/objects/classloaders, RPC/binary/messages, compiler/CLI/trace, spawn gating; QJS Worker |
| custom | JS identity, external thread names before Java initialization, maps/smaps/FD snapshots, server keyword audit |
| edge | isolated delayed load (`none`, `record`, `lookup`), pre-constructor hook (`hook`, base-v4 fixture), or native child gating (`child`) via `--edge-case` |
| gadget | four configurations selected through the supplied fixture build |
| detection | seven Fatdog pages, external UI results, each screen freshly started; `--detection-mode baseline/server/empty/java/native`, `--repeats 10` |
| detection_signals | diagnostic only: read dusk integer subchecks after empty script, bridge initialization and Java hook; never replace results |
| lifecycle | Native Gadget normal exit with minimal teardown, and dlclose with full teardown |
| concurrency | Four independent app service processes with external business heartbeats, 1800 seconds |
| recovery | ten target-exit, client reconnect and server-restart cycles |
| performance | five warmups + thirty measurements per instrumentation mode, CSV with RPC overhead explicitly included |
| stress | 100 attach, 50 spawn, 500 script, 50 foreground cycles, 100000 sequenced messages and a 7200-second Java/Native soak |

The `all` shortcut in `run.py` is the shared server subset. The full **scheduled
campaign** is `campaign.py`; Gadget uses separately built APK configurations and
root-disabled validation is an explicit environment phase, not a claim inferred
from running in a normal UID on a rooted emulator.

```sh
venv-macos-clean/bin/python jprobe/tests/regression/build.py \
  --gadget dist/android-thread-names-r8/artifacts/jprobe-gadget-arm64.so \
  --runtime qjs --interaction listen \
  --output verification/jprobe-regression/fixtures/gadget-example
venv-macos-clean/bin/python jprobe/tests/regression/run.py \
  --serial DEVICE --variant r8 --runtime qjs --suite gadget \
  --server dist/android-thread-names-r8/artifacts/jprobe-gadget-arm64.so \
  --fixture verification/jprobe-regression/fixtures/gadget-example \
  --output verification/jprobe-regression/gadget-example
```

The `--server` artifact argument identifies the delivered Gadget in this suite.
Other interaction values are `script`, `script-directory`, and `connect`.
Connect creates a temporary host Portal and a device-specific ADB reverse rule.

## Durable full campaign

```sh
venv-macos-clean/bin/python jprobe/tests/regression/campaign.py \
  --serial DEVICE --output verification/jprobe-regression/full-RUN_ID \
  --restore-instance 0
```

This takes several hours: two two-hour soaks, two thirty-minute concurrency runs, plus repeated
detector screens and recovery tests (approximately seven hours on this emulator). `campaign.json` records current job, heartbeat and exact commands.
`--resume` skips completed and interrupted existing job directories without
silently retrying failures. The optional MuMu restoration is performed at campaign
exit; it may stop the testing clone because this installation ran only one
instance at a time. The original instance's root setting is never changed.

Every completed job updates the generated report under
`/Users/sunjie.sj/software/vault/pj/jprobe功能回归测试/`.
Existing report snapshots are preserved. No credentials or application accounts
are included.

## Evidence and verdicts

Each run stores client/artifact/bridge hashes, copied harness source, JSON,
JUnit, console logs, independent business values and optional raw /proc/UI data.
The parent watchdog records timeout failures and performs owned-resource cleanup.
Completion requires `completion.json`; a partial results file is not a finished
test. Historical attempts are retained. Count unique function IDs separately
from repetitions and retried suites.

Detection PASS means **successful observation**, not nondetection. Read its
`actual.detected` and raw status; threshold-based nondetection may still contain
positive subchecks. A UI-only collector avoids injecting observation code into
the baseline. Performance numbers are observations, not an official 20% SLO.

Known coverage gaps that must remain visible in acceptance reports:

- ARM32, real devices and other Android/SELinux versions are outside this device.
- Official Core/Gum suites and allocator/fsync fault injection need matching test
  builds; the existing Android build tree has no Core/Gum test targets.
- Gadget minimal teardown is tested at normal process exit; native dlclose is
  tested with full teardown. Minimal is not treated as a full-unload contract.
- Runtime fallback fault injection, all exported API boundary cases and complete
  JS API compatibility are not fully covered. Do not call this a full Frida-platform certification.

Confirmed issues observed during implementation are documented in the generated
execution report and retained under `matrix-01`, `matrix-02`, `extended-01`.
Product code is not modified by these tests.

The November 3 repairs use `/proc/net/tcp*` socket inodes and the selected PID's
FD links to verify ownership even when `ss` omits process information. Ownership
is checkpointed before readiness checks; cleanup waits for the owned executable
to exit and rechecks identity before escalation. APK installation explicitly
disables incremental mode because this emulator rejects that transport.
Concurrent service heartbeats are compared with the emulator's own clock;
the host clock is used only for logging, and elapsed test duration is monotonic.
This avoids treating host/emulator clock skew as a stalled application. Stale
heartbeats, wrong business values and changed PIDs still fail the test.

Detector dialogs and ordinary result text are both parsed as observations;
positive dialogs take precedence over stale negative labels. Unknown UI remains
a collection failure. Historical JSON is never rewritten to turn failures into
passes. R9 details and delivery limits are in [ANDROID-R9.md](../../docs/ANDROID-R9.md).
