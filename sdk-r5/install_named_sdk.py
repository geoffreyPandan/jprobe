"""Install complete rebuilt SDKs without touching the original fork's cache."""
import hashlib
import argparse
import json
from pathlib import Path
import tarfile
import time

BASE = Path('/home/jim/jprobe')
target = BASE / 'full-source/deps'
original = BASE / 'frida/deps'
parser = argparse.ArgumentParser()
parser.add_argument('--hosts', nargs='+', default=['android-arm64', 'android-arm'],
                    choices=['android-arm64', 'android-arm', 'linux-x86_64', 'linux-x86'])
hosts = parser.parse_args().hosts
stamp = time.strftime('%Y%m%d-%H%M%S')

def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

records = {}
staged = {}
for host in hosts:
    archive = BASE / 'sdk-rebuild' / ('sdk-' + host + '.tar.xz')
    stage = BASE / 'sdk-rebuild' / ('install-' + host + '-' + stamp)
    stage.mkdir()
    with tarfile.open(archive, 'r:xz') as source:
        source.extractall(stage, filter='data')
    required = ['lib/libglib-2.0.a', 'lib/libgio-2.0.a', 'lib/libgobject-2.0.a', 'lib/libtcc.a']
    # V8's major version is pinned by releng; discover its archive filename.
    v8 = list((stage / 'lib').glob('libv8-*.a'))
    if len(v8) != 1:
        raise ValueError('Cannot identify V8 archive for ' + host)
    required.append(str(v8[0].relative_to(stage)))
    version = (stage / 'VERSION.txt').read_text().strip()
    if version != '20261030':
        raise ValueError('Unexpected SDK version: ' + version)
    original_sdk = original / ('sdk-' + host)
    original_libraries = {name: sha(original_sdk / name) for name in required
                          if (original_sdk / name).is_file()}
    records[host] = {'archive': str(archive), 'archiveSha256': sha(archive),
                     'libraries': {name: sha(stage / name) for name in required},
                     'originalLibraries': original_libraries}
    for template in stage.rglob('*.frida.in'):
        output = template.with_name(template.name[:-len('.frida.in')])
        output.write_text(template.read_text().replace('@FRIDA_TOOLROOT@', str(target / ('sdk-' + host))))
        template.unlink()
    staged[host] = stage

if target.is_symlink():
    if target.resolve() != original.resolve():
        raise ValueError('Unexpected shared dependency location')
    target.rename(target.with_name('deps-shared-' + stamp))
    target.mkdir()
    for entry in original.iterdir():
        if entry.name not in {'sdk-' + host for host in hosts}:
            (target / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
elif not target.is_dir():
    raise ValueError('Missing dependency directory')

for host, stage in staged.items():
    destination = target / ('sdk-' + host)
    if destination.exists() or destination.is_symlink():
        destination.rename(destination.with_name(destination.name + '-before-' + stamp))
    stage.rename(destination)
    for name, expected in records[host]['originalLibraries'].items():
        if sha(original / ('sdk-' + host) / name) != expected:
            raise ValueError('Shared original SDK unexpectedly changed')

report = BASE / ('sdk-install-' + stamp + '.json')
report.write_text(json.dumps(records, indent=2))
print('Installed isolated SDKs:', report)
