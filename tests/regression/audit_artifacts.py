#!/usr/bin/env python3
"""Audit delivered binaries only. Source/license attribution is intentionally excluded."""
import argparse,hashlib,json,re
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();rows=[]
 for path in sorted(a.directory.iterdir()):
  if not path.is_file() or not path.name.startswith('jprobe-'):continue
  data=path.read_bytes();hits={k:[m.start() for m in re.finditer(pattern,data,re.I)] for k,pattern in [('ascii',b'frida'),('utf16le',b'f\x00r\x00i\x00d\x00a\x00')]}
  names={name:len(re.findall(b'\x00'+name.encode()+b'\x00',data)) for name in ['gmain','gdbus','gum-js-loop']}
  rows.append({'file':path.name,'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),'keywordOffsets':hits,'oldThreadStrings':names})
 assert rows,'No candidate artifacts found';a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(rows,indent=2));print(json.dumps([{**{k:v for k,v in row.items() if k not in ['keywordOffsets','sha256','size']},'keywordMatches':sum(map(len,row['keywordOffsets'].values()))} for row in rows],indent=2))
 return 1 if any(any(row['keywordOffsets'].values()) for row in rows) else 0
if __name__=='__main__':raise SystemExit(main())
