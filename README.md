# jprobe r6d publication kit

This repository contains the source changes for `jprobe` 17.25.0 and the
records for the Android ARM64 / Linux x86_64 build tested on a Pixel 6. It is
a patch kit against pinned upstream Git commits, not a copy of the 6.4 GB
checkout or its build cache.

## Contents

- `patches/`: changes to tracked files in the root project and five subprojects.
- `new-source/`: new source files needed in the matching project directories.
- `sdk-r5/`: source patches and build scripts retained from the base r5 build.
- `upstream-commits.json`: exact upstream Git commit for each patched project.
- `evidence/`: release hashes, keyword audit, validation run, installation
  record, and installed Fatdog detector results.
- `release-assets.json`: SHA-256 and size for the separately packaged binaries.
- `licenses/`: upstream license texts. Preserve notices in redistributed files.
- `docs/MACOS-BUILD.md`: native macOS client build and verification steps.

## Apply the source changes

On Linux, clone the upstream project at the root commit in
`upstream-commits.json` and initialize its submodules. Then run:

```sh
bash apply-source.sh /path/to/frida-checkout
```

The script checks all six commit IDs before applying patches and copying new
files. It refuses to overwrite a different existing file. Build toolchains and
SDK archives are not included in this Git repository. The `sdk-r5` files and
the source references in `evidence/release.json` document the base build.

## Release assets

Upload the ten files listed in `release-assets.json` to a GitHub Release named
`shared-code-sync-r6d`. They are staged on the build VM at
`/home/jim/jprobe/publication/shared-code-sync-r6d/release-assets/`.

The Python wheel `jprobe-17.25.0-cp37-abi3-linux_x86_64.whl` runs on Linux
x86_64. It does not install natively on macOS. A Mac can create this GitHub
repository and use the existing Ubuntu VM over SSH; a native macOS client
requires a separate build. The Android ARM64 binaries target the Pixel 6 lab
device. Start the server with `JPROBE_AGENT_FILE_MODE=1` and port `35000`.

## Validation and limit

The exact candidate passed 108/108 functional cases and the listed raw keyword
audit. After installation, seven client checks passed; Fatdog `fox`, `owl`,
`sun`, `ice`, `dusk`, `veil`, and two runs of its own `snow` screen returned not
detected. `dusk`, `veil`, and `snow` still observed one anonymous executable
mapping, below their detection threshold. These results do not guarantee that
other applications will not detect the agent.
