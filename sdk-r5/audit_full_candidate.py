"""Audit raw binary identifiers and executable client assets, retaining evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile

BASE = Path('/home/jim/jprobe')
parser = argparse.ArgumentParser()
parser.add_argument('--release', default='full-r4')
args = parser.parse_args()
if Path(args.release).name != args.release or args.release in {'.', '..'}:
    raise ValueError('Invalid release name')
release = BASE / 'candidates' / args.release
artifacts = BASE / 'full-source/build/subprojects/frida-core'
paths = [artifacts / name for name in ['server/jprobe-server', 'lib/agent/jprobe-agent.so',
                                      'lib/gadget/jprobe-gadget.so', 'inject/jprobe-inject']]
extensions = list((release / 'client-env/lib').glob('python*/site-packages/jprobe/_jprobe*.so'))
if len(extensions) != 1:
    raise ValueError('Missing unique candidate Python native extension')
paths += extensions
packages = list((release / 'client-env/lib').glob('python*/site-packages/jprobe_tools'))
if len(packages) != 1:
    raise ValueError('Missing candidate tools package')
paths += [packages[0] / name for name in ['fs_agent.js', 'tracer_agent.js', 'itracer_agent.js',
                                         'repl_agent.js', 'bridges/java.js', 'bridges/objc.js', 'bridges/swift.js']]
report = {'scope': 'Android binaries, Python native extension, injected JS, and standalone Java bridge executable modules',
          'zeroRawMatchesRequired': args.release != 'full-r4',
          'artifacts': [], 'passed': True}
for path in paths:
    data = path.read_bytes()
    matches = []
    for encoding, needle, unit in [('ascii', b'frida', 1), ('utf16le', b'f\0r\0i\0d\0a\0', 2)]:
        for match in re.finditer(needle, data, re.I):
            suffix = data[match.start():match.start() + 6 * unit]
            friday = 'Friday'.encode('ascii' if unit == 1 else 'utf-16le')
            # Locale day names are ordinary data, not a tool identifier.
            before = data[max(0, match.start() - unit):match.start()]
            after = data[match.start() + 6 * unit:match.start() + 7 * unit]
            word_byte = lambda raw: bool(raw) and (65 <= raw[0] <= 90 or 97 <= raw[0] <= 122 or 48 <= raw[0] <= 57 or raw[0] == 95)
            allowed = (not report['zeroRawMatchesRequired'] and suffix == friday
                       and not word_byte(before) and not word_byte(after))
            item = {'offset': match.start(), 'encoding': encoding,
                    'classification': 'ordinary-locale-day' if allowed else 'unresolved-identifier',
                    'context': data[max(0, match.start() - 60):match.end() + 90].decode('ascii', errors='backslashreplace')}
            matches.append(item)
            if not allowed:
                report['passed'] = False
    report['artifacts'].append({'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
                                'size': len(data), 'matches': matches})
    print(path.name, 'raw matches:', len(matches), 'unresolved:', sum(m['classification'] == 'unresolved-identifier' for m in matches))
archives = list((release / 'client').glob('jprobe-java-bridge-*.tgz'))
if len(archives) != 1:
    raise ValueError('Missing standalone Java bridge archive')
archive_path = archives[0]
matches = []
with tarfile.open(archive_path) as archive:
    for member in archive.getmembers():
        if member.isfile() and member.name.endswith('.js'):
            data = archive.extractfile(member).read()
            for match in re.finditer(b'frida', data, re.I):
                matches.append({'member': member.name, 'offset': match.start(),
                                'classification': 'unresolved-identifier'})
if matches:
    report['passed'] = False
report['artifacts'].append({'path': str(archive_path), 'sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                            'size': archive_path.stat().st_size, 'matches': matches})
print(archive_path.name, 'executable matches:', len(matches))
(release / 'keyword-audit.json').write_text(json.dumps(report, indent=2))
if not report['passed']:
    raise SystemExit('Unresolved identifiers remain; see keyword-audit.json')
