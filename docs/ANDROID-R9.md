# Android R9 repair candidate

R9 addresses the failures found by the Android ARM64 emulator campaign. It uses
the existing pinned Frida/Jprobe and V8 versions. Rebuilding the SDK does not
upgrade the JavaScript engine.

## Product changes

On Bionic, `link_image()` notifies the debugger before the load group is marked
linked. Looking up an export from a module observer used to request a handle
through `dlopen(RTLD_NOLOAD)`. Bionic can then reenter the incomplete load and
abort with `Load CHECK 'did_read_' failed`.

The repair checks the live soinfo under the linker mutex. For an unlinked
module, lookup uses its mapped ELF export table. Once linked, the existing
`dlsym` route remains in use. An early missing-symbol lookup does not cache a
failed handle. This early route covers the module's own ordinary function and
data exports; early dependency-scope, TLS and GNU IFUNC resolution are not
certified by this regression.

Android anonymous pages allocated by Gum now have the honest name
`jprobe-page`, including RW pages later used for generated code. NativeCallback
closure pages allocated by libffi are separately named `jprobe-closure`, for
both QuickJS and V8. This changes mapping attribution only, preserves errno,
and falls back to the allocation on kernels that reject `PR_SET_VMA`.
Existing application/system mappings and detector results are not rewritten.

The Android Java bridge also closes a first-hook race on API 23 and newer.
Previously, the first `ArtMethod` clone could be created before the bridge had
installed its moving-GC observers and before the clone was published in the
replacement table. A GC in that window updated the original method's compressed
declaring-class reference but left the clone stale. The generic JNI trampoline
then dereferenced the stale class and crashed at
`artQuickGenericJniTrampoline+88` / address `0x10`. R9 initializes the
observers before cloning, refetches the method metadata after initialization,
and refreshes the clone's class
reference under the same mutex immediately before publication. The API below
23 object-clone path retains its previous ordering.

## Applying the source repair

Fresh checkouts receive the fixes through `patches/frida-gum.patch` and the
existing `apply-source.sh` workflow. The canonical Java bridge source is stored
at `new-source/root/vendor/jprobe-java-bridge/lib/android.js`; the patched
`frida-tools/bridges/build.py` copies that source over the npm package before
Rollup bundles `java.js`, so a rebuild cannot silently lose the compatibility
fix. For a checkout already prepared as R8:

```sh
cd /path/to/prepared-source/subprojects/frida-gum
git apply --check /path/to/jprobe/patches/android-module-observer-r9.patch
git apply /path/to/jprobe/patches/android-module-observer-r9.patch
```

Do not apply the incremental patch after applying the updated canonical patch.
Keep the R8 GLib thread-name patch and matching named SDK dependencies. A plain
upstream V8/TinyCC cache can reintroduce old identifiers even when Gum is fixed.
The full canonical patch also retains the pinned Windows Meson files' CRLF
context correctly, so `git apply --check` succeeds against the pinned index.
Patch files are marked `-text` in `.gitattributes` so Git preserves that context
when the repair kit is committed or checked out.

## Building with the prepared Linux SDK

The R8 Linux checkout already has the matching SDK; no V8 upgrade or rebuild is
required. Build in a new directory with:

```sh
python3 scripts/build_android_r9.py /home/jim/jprobe \
  /home/jim/jprobe/candidates/module-observer-r9 \
  --patch patches/android-module-observer-r9.patch
```

The helper preserves the R8 source, records SDK library hashes, checks the
incremental patch before applying it, and records `status.json` plus configure
and build logs. It reuses the SDK archives without changing them. `BUILT` means
compilation succeeded; runtime acceptance is recorded separately. Re-running
requires a new candidate directory.

## Verification and delivery boundary

The fixture's `lookup` and `hook` edge modes check missing symbols, function
addresses, data exports and hooking before the library constructor's first
call. `functional` with `--variant r9` also checks external `/proc` evidence for
owned RW-to-RX and closure pages. `detection_signals` diagnoses the lab detector
without replacing its results. The usual seven-page UI suite remains the
detection acceptance test.

Evidence is under `verification/jprobe-regression/repair-20261103/` in the
workspace parent. `dist/android-module-observer-r9/` contains intermediate
ARM64 prototypes and is **not a final release**: its first build used an old
SDK and still contained six old identifier matches. Preserve those prototypes
and their hashes for comparison. A final candidate must pass the binary audit
and rerun tests with the final embedded agent and matching injector/Gadget.

ARM32, other kernels/Android versions and the complete upstream Core/Gum suites
are outside the current runtime validation. The prior R8 two-hour soak results
do not certify a rebuilt R9 candidate. Test durations are recorded per run.

## Linux candidate status, November 3

The isolated Linux build completed for ARM64 server/inject/agent/Gadget and
ARM32 agent/Gadget. The server in `dist/android-r9-linux/` matches the remote
SHA-256 and has zero ASCII/UTF-16LE old-identifier matches. Companion downloads
were initially interrupted by SSH handshake timeouts. After reconnecting to
the Linux host, all six artifacts were retrieved and passed hash and static
audits. The agent actually mapped by a test process also matches the delivered
ARM64 agent. Download completion does not imply runtime acceptance.

That server passed both engines' immediate module lookup, pre-constructor hook,
custom checks and ten cycles each of target exit, client reconnect and server
restart. A 60-second V8 four-process comparison passed on both R8 and R9.
Twelve alternating R8/R9 QJS/V8 smoke jobs also passed. These successful retries
did not erase the earlier controlled-reboot failure: the baseline without
injection passed, QJS smoke passed, but V8 Java Hook crashed with
`artQuickGenericJniTrampoline+88` / SIGSEGV at `0x10` on both R8 and R9. The
device `libart.so` instruction sequence and a forced moving-GC reproducer later
confirmed that the crash was a stale declaring-class reference in an
unpublished `ArtMethod` clone, not a V8-version or server-binary problem.

The first Linux campaign was also interrupted by an emulator reboot, and two
detector UI reads were obscured by another app's root prompt. These remain
failed observations, not detector verdicts. See `repair-20261103/controlled-boot/`,
`cold-hook-repeat/`, `server-retest/`, and the delivery status JSON for evidence.
The Java bridge fix passed three distinct emulator cold boots with QJS and V8
(six jobs, 48 checks), plus forced GC both before and after publication on both
engines. After publication, original and replacement class references moved
together and remained equal; the hooked call returned 43, the native control
returned 42, and restoring the hook returned 42. The fixed bundle also passed
the full functional suites (QJS 43/43; V8 42/42 plus the existing Worker skip).
See [Java GC fix evidence](../evidence/r9/java-gc-fix.json). The tested cold-hook
issue is therefore closed for Android 12/API 32 ARM64.

After retrieving the complete Linux output, the final ten-job regression batch
passed with 149 checks passed, one expected V8 Worker skip, and no failures.
It covers both engines' functional suite (including standalone inject), Gadget
listen mode, native Gadget lifecycle, approximately two minutes of four-process
concurrency, and three repeats of seven detector pages. All 42 UI observations
were collected and none reached the detector threshold. These are repeated
checks, not 149 independent platform features or proof of general nondetection.
See [validation summary](../evidence/r9/validation-summary.json) and
[artifact audit](../evidence/r9/artifact-audit.json).

The separate Nterp flag experiment passed both its control and modified probes;
it did not establish a fix and no such flag change was shipped. R9 still has no
new two-hour soak, root-disabled Gadget run, or ARM32 runtime test, so these
remain release-acceptance limits even though the reproduced cold-hook defect is
fixed.
