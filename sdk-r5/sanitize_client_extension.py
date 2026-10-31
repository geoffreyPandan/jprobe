"""Remove non-runtime ELF metadata and an obsolete build-tree runpath."""
import argparse
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('path', type=Path)
path = parser.parse_args().path
temp = path.with_name(path.name + '.sanitizing')
shutil.copy2(path, temp)
try:
    subprocess.run(['strip', '--strip-all', str(temp)], check=True)
    data = bytearray(temp.read_bytes())
    old = b'$ORIGIN/../../frida-core/src/api\0'
    new = b'$ORIGIN\0'
    if old in data:
        assert data.count(old) == 1
        data[data.index(old):data.index(old) + len(old)] = new.ljust(len(old), b'\0')
    else:
        assert new in data, 'Unexpected extension runpath'
    temp.write_bytes(data)
    temp.replace(path)
finally:
    if temp.exists():
        temp.unlink()
print('Sanitized native client extension:', path)
