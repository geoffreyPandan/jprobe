# MobiKwik Custom ROM experiment

`startup.js` is the combined startup candidate for the same app build and the
R8 Android server. Start it before application initialization:

```sh
jprobe -H 127.0.0.1:35001 -f com.mobikwik_new -l examples/mobikwik/startup.js
```

The endpoint must already reach the R8 server. The script checks ARM64, the
process package, native function prefixes, and Java version 23.75.1 / 2290.
Android temporarily retains its launcher process name during spawn, so the
package check runs when the app's native module loads. Attaching after startup
can be too late to prevent a native termination that has already been scheduled.

The combined candidate applies these deliberate per-process overrides:

| Startup path | Change |
| --- | --- |
| BTL method-hook classification | Replaces the tag in the scanner's method records. |
| Contradictory boot properties | Only the verified native caller's `green` read becomes `orange` when its parsed record is exactly version 300, unlocked, and boot state 2. |
| Unverified-boot Custom ROM branch | Enables that detector's existing allowance flag; the attestation record itself is unchanged. |
| Zygisk response | Clears only its native termination bit and overrides its Java popup response. |
| Application RootChecker | Calls the startup listener's unrooted continuation, avoiding the separate countdown dialog. |

Frida and Custom ROM popup suppression are absent from the Java response hook.
R8 changes the GLib worker names in source. The script does not change the APK,
global properties or Magisk settings, keystore methods, or certificate bytes.
Its Root result override is intentional and does not establish that the device
is unrooted. Native policy bytes and BTL record pointers are restored on script
unload; normal jprobe teardown removes its hooks.

Validation covers the logged-out onboarding screen and process liveness.
Login, payment, server-side integrity checks and other app versions are outside
that result. See `evidence/r8/` for completed runtime records.

## Standalone BTL diagnostic

`custom-rom.js` is restricted to `com.mobikwik_new` and the verified ARM64
`libloader.so` callback prefix from version 23.75.1 / 2290. Other versions
require a fresh analysis; the offset and prefix checks are not an APK hash check.

The native scanner classified existing keystore method hooks as `BTL`, then
reported Custom ROM. This script replaces only that classification tag in the
method records. It does not repair the device environment or alter keystore
methods, certificates or attestation. It intentionally changes this app's
detector result and is not proof that instrumentation is generally invisible.

Two R7 comparison runs inspected 24 method records without reporting the
previous Custom ROM event. Java-level Custom ROM popup suppression was disabled.
The same runs still reported Frida worker threads and eventually terminated.
R8 corrects those worker names in GLib; see [R8 limits](../../docs/ANDROID-R8.md).

Load the script into an already running supported process with the matching
jprobe client. The native module must already be loaded. The script exports
`customRomStatus` and `customRomRestore`; restoration stops polling and restores
the original record pointers. This example alone does not resolve Root,
other integrity detections, or startup termination.
