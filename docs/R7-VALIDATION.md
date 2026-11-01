# R7 / macOS candidate verification

Recorded on 2026-11-01. jprobe 17.25.0, tools 14.11.0+jprobe.

- macOS ARM64 client: installed wheel matched the audited extension; dependency
  check, process enumeration, TypeScript compilation, QuickJS/V8 RPC, CModule
  and date semantics passed on macOS 26.2 / Python 3.13.
- Android ARM64: the installed Mac client passed the same functional checks
  plus CLI Java bridge invocation against the R7 server.
- The Mac extension retains one full ordinary word `Friday` from a libc++
  date locale table. That exception was accepted for this candidate. Other
  ASCII matches and all UTF-16LE matches were zero; seven injected JS files
  had zero matches. The strict build/packaging gate remains unchanged and
  stops at this exception. This is not a strict raw-zero artifact.
- Fatdog was tested without replacing its detector results. Six of seven
  screens passed initially. Veil first detected private executable dirty
  pages plus anonymous executable memory (2/7), then only anonymous executable
  memory (1/7, below threshold) after a cold restart. Thread checks passed in
  both. Stable complete nondetection is not established.
- One local suspended-process initialization timed out. Immediate attach and
  the installed-wheel runtime retests passed; the cause was not established.
- ARM32 runtime, Gadget injection, macOS Intel and arm64e were not verified.
- The Environment Inspector example deliberately replaces result objects;
  its zero-signal UI is not evidence that Root or injection is hidden from
  other software.

Machine-specific paths are replaced by placeholders in the retained
`evidence/r7/` audit and verification records. Raw screenshots and device
configuration backups are not part of this publication.
