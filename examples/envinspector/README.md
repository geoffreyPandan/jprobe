# Environment Inspector result override

Tested with `dev.jim.envinspector` 1.0.1 (versionCode 2). This example changes
the application's reported results; it does not remove Root or make the
instrumentation undetectable. No APK or device hiding settings are changed.

Open the application, then run from the repository root with jprobe installed:

```sh
jprobe -H 127.0.0.1:35000 -N dev.jim.envinspector \
  -l examples/envinspector/envinspector-clear.js \
  -q -t inf --exit-on-error --no-auto-reload
```

The endpoint assumes an existing connection/forward to your device's server.
After `Installed` appears, tap **开始检测** and wait for completion. Existing
results are not changed until a new scan runs. Keep the command running;
restart the application without attaching to restore its original behavior.
After detaching, rescan to replace any cached results.

The hook intercepts the six-argument `Finding` constructor and converts only
`SIGNAL` to `CLEAR`, replacing the corresponding evidence text. It preserves
`LIMITED`, `ERROR`, `INFO`, timestamps and limitations.

Device observation: baseline 7 signals; two scans while attached reported 0
signals, with 40 checks and 7 limited/unavailable results retained. The signal
filter was empty. Eight signal types, including the instrumentation thread,
were intercepted. This is an intentional result override, separate from the
unmodified Fatdog detector tests. See `../../evidence/r7/envinspector-example.json`.

Attach mode was verified. A spawn (`-f`) attempt timed out in this session.
Hardware attestation, location permissions and screen-capture events were not
separately exercised.
