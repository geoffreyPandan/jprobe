#!/usr/bin/env python3
"""Validate the installed SDK audit marker and named dependency archive hashes."""
import hashlib
import json
from pathlib import Path
import re
import sys


def verify(sdk):
    sdk = sdk.resolve(strict=True)
    raw = (sdk / 'JPROBE-SDK-AUDIT.json').read_bytes()
    data = json.loads(raw)
    if data.get('schemaVersion') != 1 or data.get('host') != 'macos-arm64' or data.get('auditPassed') is not True:
        raise ValueError('SDK audit marker is missing the required verified identity')
    libraries = data.get('libraries')
    if not isinstance(libraries, dict):
        raise ValueError('SDK marker libraries must map relative archive paths to SHA-256 strings')
    required = {'lib/libglib-2.0.a', 'lib/libgobject-2.0.a', 'lib/libgio-2.0.a', 'lib/libtcc.a'}
    v8 = {p.relative_to(sdk).as_posix() for p in (sdk / 'lib').glob('libv8-*.a')}
    if not v8 or not required.union(v8).issubset(libraries):
        raise ValueError('SDK marker does not cover all required GLib/tinycc/V8 archives')
    for relative, expected in libraries.items():
        part = Path(relative)
        if part.is_absolute() or '..' in part.parts or not re.fullmatch(r'[0-9a-f]{64}', str(expected)):
            raise ValueError('Invalid SDK marker archive path/hash')
        path = (sdk / part).resolve(strict=True)
        if sdk not in path.parents or not path.is_file():
            raise ValueError('SDK marker points outside the installed SDK')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('SDK archive hash mismatch: ' + relative)
    return hashlib.sha256(raw).hexdigest()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: verify_macos_sdk.py SDK_DIRECTORY')
    print(verify(Path(sys.argv[1])))
