# jprobe shared-code-sync-r6d

## Installed state

- Device: Pixel 6 (oriole), ADB serial `22081FDF6001HJ`.
- Build host: `jim@192.168.191.130`, project `/home/jim/jprobe`.
- Installed server: `/data/local/tmp/jprobe/jprobe-server`, listening on `127.0.0.1:35000`.
- Server SHA-256: `a73b151b0f9319fd07fafacfd91d3987450b9efaa46843b3c06a7c6b1a0b4734`.
- Startup sets `JPROBE_AGENT_FILE_MODE=1`. The installed client is the independent
  `candidates/shared-code-sync-r6d/client-env` directory.
- Previous installation backup: `releases/20261031-225628-before-shared-code-sync-r6d`.

## Evidence

- `candidates/shared-code-sync-r6d/validation-run.json`: 108/108 functional cases
  passed against the exact release input hashes.
- `candidates/shared-code-sync-r6d/keyword-audit.json`: raw ASCII and UTF-16LE
  keyword audit passed for the listed Android binaries, Python extension,
  injected JavaScript, and Java bridge. The audit scope is in that file.
- `candidates/shared-code-sync-r6d/installed-native/result.json`: on separate
  cold loads, Fatdog `fox`, `owl`, `sun`, `ice`, `dusk`, and `veil` each returned
  `nativeFridaDetect() == 0`, with the app process still alive.
- `candidates/shared-code-sync-r6d/installed-snow/result.json`: two cold starts
  on Fatdog's own `snow` screen while the installed client remained attached.
  Both displayed "not detected"; the process survived and `libsnow.so` loaded.
  Neither `/proc/<pid>/maps` nor thread names contained the raw `frida` string
  during these captures.
- `candidates/shared-code-sync-r6d/installed-verification/*/client.json`: 7/7
  installed-client checks passed, including process enumeration, CLI execution,
  TypeScript compilation and RPC, asynchronous Python access, and empty and
  binary file transfers.

## Limits

The `dusk`, `veil`, and `snow` detectors still mark an anonymous executable code
island. Each sees one hit, below its threshold of two. A detector with a
different threshold or other checks may still detect the agent. The keyword
audit covers its listed artifacts and the sampled process state; it is not a universal claim about
every runtime string or application. The full 108-case suite ran before
installation; the installed service was checked with the seven client tests,
script attachment, and the Fatdog tests above.
