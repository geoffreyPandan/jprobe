# Android R7 and VM source provenance

R7 was built on a Linux VM from the existing r6d `full-source` working tree,
with its custom SDKs and renamed TypeScript dependency. It was not built from
an unmodified upstream checkout plus stock SDKs.

The only R7 source change is the scheduler thread name `gum-js-loop` to
`jp-js-loop`; see `../patches/android-thread-name-r7.patch`. Mapping strategy,
allocation behavior and file-backed agent mode remain as in r6d.

## Existing prepared VM workspace

Expected layout under a user-selected `BASE_WORKSPACE`:

```text
full-source/             prepared r6d source, including deps/
go-rename/tsc/           pinned renamed TypeScript source
toolchains/go/           existing customized Go toolchain
toolchains/android-ndk-r29/
```

Put the matching Node.js on `PATH`, then run:

```sh
bash scripts/build_android_vm.sh /path/to/base /path/to/new-r7-candidate
```

The wrapper copies source into a new directory, links the existing SDKs,
checks/applies the R7 patch, configures and builds. It refuses an existing
candidate directory. It does not deploy to a phone. The wrapper is a portable
form of the recorded build commands; its full build was not rerun for this
publication commit.

`scripts/build_linux_vm.sh` retains the Linux client build entry point from
the VM, with the workspace supplied as an argument and Node resolved from
`PATH`. It operates on the already prepared base, including its custom SDKs;
no new Linux client build was performed for this source publication.

Recorded tools: Go 1.27.3 (customized), NDK 29.0.14206865 / Clang 21.0.0,
Node 24.22.2, Python 3.12.3, Ninja 1.13.2, dependency bundle 20261030.
Both Android ARM64 and ARM32 custom SDKs are required; compatibility was enabled.
`sdk-r5/` retains the VM SDK changes and build provenance. The current VM base
patches were compared with this repository: all six match after CRLF
normalization. New-source differences were the Mac Objective-C fixes and a
Windows export-file line ending; the only additional non-backup untracked
file was a generated tracer UI archive. The renamed bindgen files are included.

For a fresh base, use the pinned commits and r6d source kit first, with the
custom dependencies described in the historical documentation. Do not treat
this incremental wrapper as an installer for all those prerequisites.

## Artifacts and verification

`release-assets-r7.json` records the six Android artifacts and Mac/SDK assets.
Server and inject are ARM64; separate agent/gadget files cover ARM64 and ARM32.
All six Android files passed raw case-insensitive ASCII/UTF-16LE keyword checks
and have no old scheduler-thread-name matches. VM-to-Mac hashes matched.

Android ARM64 server/agent were deployed and exercised. ARM32 and Gadget were
built and statically audited, not runtime-validated. Fatdog results remain
variable: first full run passed 6/7 screens; veil reported 2/7 hits, then 1/7
and no detection after a cold restart. Neither result proves universal
nondetection. See `R7-VALIDATION.md`.
