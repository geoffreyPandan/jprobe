"""Adapt the pinned filesystem dependency to optional pointer-read offsets."""
from pathlib import Path

OLD = 'const value = read.call(this.buffer.add(offset), path);'
NEW = '''const value = (typeof type === "string")
        ? read.call(this.buffer.add(offset))
        : read.call(this.buffer.add(offset), path);'''
UPSTREAM_FIXED = '''const address = this.buffer.add(offset);
    const value = (typeof type === "string")
        ? NativePointer.prototype["read" + type].call(address)
        : type.call(address, path);'''

def patch_dependencies(private_dir):
    path = Path(private_dir) / 'node_modules/frida-fs/dist/index.js'
    if not path.exists():
        return
    source = path.read_text()
    if OLD in source:
        if source.count(OLD) != 1:
            raise ValueError('Ambiguous filesystem reader implementation')
        path.write_text(source.replace(OLD, NEW))
    elif NEW not in source and UPSTREAM_FIXED not in source:
        raise ValueError('Unexpected pinned filesystem reader implementation')
