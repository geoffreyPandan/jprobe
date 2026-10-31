"""Remove legacy names from source line metadata in prebuilt BPF objects."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


ALLOWED = {".BTF", ".debug_str", ".debug_line_str"}
PATTERN = re.compile(b"frida", re.IGNORECASE)


def sections(data):
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] not in (1, 2):
        raise ValueError("Expected a 64-bit ELF object")
    endian = "<" if data[5] == 1 else ">"
    header = struct.unpack_from(endian + "HHIQQQIHHHHHH", data, 16)
    table_offset, entry_size, count, names_index = header[5], header[10], header[11], header[12]
    entries = [struct.unpack_from(endian + "IIQQQQIIQQ", data, table_offset + i * entry_size)
               for i in range(count)]
    names = data[entries[names_index][4]:entries[names_index][4] + entries[names_index][5]]
    result = []
    for entry in entries:
        name = names[entry[0]:].split(b"\0", 1)[0].decode("ascii")
        start, length = entry[4], entry[5]
        if start + length > len(data):
            raise ValueError("Section extends past end of file")
        result.append((name, start, start + length))
    return endian, result


def sanitize(path):
    before = path.read_bytes()
    endian, entries = sections(before)
    data = bytearray(before)
    count = 0
    for match in PATTERN.finditer(before):
        matched = [(name, start, end) for name, start, end in entries
                   if start <= match.start() and match.end() <= end]
        if len(matched) != 1 or matched[0][0] not in ALLOWED:
            raise ValueError(f"Unexpected identifier at {path}:{match.start()}: {matched}")
        name, start, _ = matched[0]
        if name == ".BTF":
            _, _, _, header_size, _, _, strings_offset, strings_size = struct.unpack_from(
                endian + "HBBIIIII", before, start)
            strings_start = start + header_size + strings_offset
            if not strings_start <= match.start() < match.end() <= strings_start + strings_size:
                raise ValueError(f"Identifier outside BTF strings at {path}:{match.start()}")
        old = match.group()
        new = bytes(ord("P") if ch == ord("F") else ord("p") if ch == ord("f")
                    else ch for ch in old).replace(b"rida", b"robe").replace(b"RIDA", b"ROBE")
        if len(new) != len(old) or PATTERN.search(new):
            raise ValueError(f"Invalid replacement at {path}:{match.start()}")
        data[match.start():match.end()] = new
        count += 1
    if PATTERN.search(data):
        raise ValueError(f"Legacy identifier remains in {path}")
    after = bytes(data)
    if after != before:
        path.write_bytes(after)
    sha = lambda blob: hashlib.sha256(blob).hexdigest()
    return {"path": str(path), "replacements": count,
            "beforeSha256": sha(before), "afterSha256": sha(after)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    files = sorted(args.root.rglob("*.elf"))
    if not files:
        raise ValueError("No BPF objects found")
    report = [sanitize(path) for path in files]
    output = json.dumps(report, indent=2)
    if args.report:
        args.report.write_text(output + "\n")
    print(f"Scanned {len(report)} BPF objects; replaced "
          f"{sum(item['replacements'] for item in report)} source metadata occurrences")
