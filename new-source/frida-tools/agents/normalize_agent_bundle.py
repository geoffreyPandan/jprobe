"""Normalize injected JS module IDs while maintaining bundle byte lengths."""
import json
from pathlib import Path
import re
import subprocess
import shutil

MAGIC = '\U0001f4e6\n'
SEPARATOR = '\n\u2704\n'

def renamed(text):
    text = text.replace('@frida/', '@jprobe/').replace('frida-', 'jprobe-')
    text = text.replace('/frida/', '/jprobe/').replace('frida:', 'jprobe:')
    text = text.replace('frida_', 'jprobe_').replace('FRIDA_', 'JPROBE_')
    text = re.sub(r'Frida(?=[A-Z]|\b)', 'Jprobe', text)
    text = re.sub(r'frida(?=[A-Z])', 'jprobe', text)
    return text.replace("'frida'", "'jprobe'").replace('"frida"', '"jprobe"')

def unpack(bundle):
    if not bundle.startswith(MAGIC):
        return [{'name': None, 'aliases': [], 'code': bundle}]
    header, separator, body = bundle.partition(SEPARATOR)
    if not separator:
        raise ValueError('Missing bundle header separator')
    modules = []
    for line in header[len(MAGIC):].splitlines():
        size, space, name = line.partition(' ')
        if not space:
            raise ValueError('Invalid bundle header line')
        if size == '\u21bb':
            if not modules:
                raise ValueError('Alias before first module')
            modules[-1]['aliases'].append(name)
        else:
            modules.append({'size': int(size), 'name': name, 'aliases': []})
    remaining = body.encode()
    for index, module in enumerate(modules):
        size = module.pop('size')
        if size > len(remaining) or size < 0:
            raise ValueError('Invalid module byte length')
        module['code'] = remaining[:size].decode()
        remaining = remaining[size:]
        if index + 1 < len(modules):
            if not remaining.startswith(SEPARATOR.encode()):
                raise ValueError('Invalid module separator')
            remaining = remaining[len(SEPARATOR.encode()):]
    if remaining:
        raise ValueError('Trailing bytes after bundle modules')
    return modules

def pack(modules):
    if len(modules) == 1 and modules[0]['name'] is None:
        return modules[0]['code']
    lines = []
    for module in modules:
        lines.append(str(len(module['code'].encode())) + ' ' + module['name'])
        lines.extend('\u21bb ' + alias for alias in module['aliases'])
    return MAGIC + '\n'.join(lines) + SEPARATOR + SEPARATOR.join(module['code'] for module in modules)

NODE = r'''
const fs = require('fs');
const {pathToFileURL} = require('url');
(async () => {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const {minify} = await import(pathToFileURL(input.parser).href);
  const codes = [], notices = new Set();
  for (const source of input.codes) {
    const result = await minify(source, {
      module: input.module, compress: false, mangle: false,
      format: {comments: (node, comment) => {
        notices.add(comment.value);
        return false;
      }}
    });
    codes.push(result.code);
  }
  process.stdout.write(JSON.stringify({codes, notices: Array.from(notices)}));
})().catch(error => { console.error(error); process.exit(1); });
'''

def normalize(path, private_dir, npm):
    path, private_dir = Path(path), Path(private_dir)
    modules = unpack(path.read_text())
    parsers = [private_dir / 'node_modules' / name / 'main.js' for name in ['terser', '@frida/terser']]
    parser = next((path for path in parsers if path.exists()), None)
    if parser is None:
        raise ValueError('The build requires its pinned Terser parser')
    node = shutil.which('node')
    if node is None:
        raise ValueError('Node.js is required to normalize injected scripts')
    parsed = subprocess.run([node, '-e', NODE], input=json.dumps({
        'parser': str(parser), 'codes': [module['code'] for module in modules],
        'module': modules[0]['name'] is not None}), capture_output=True, text=True, check=True)
    result = json.loads(parsed.stdout)
    for module, code in zip(modules, result['codes'], strict=True):
        module['code'] = renamed(code)
        if module['name'] is not None:
            module['name'] = renamed(module['name'])
        module['aliases'] = [renamed(alias) for alias in module['aliases']]
    output = pack(modules)
    if re.search('frida', output, re.I):
        raise ValueError('Unclassified identifier remains in ' + str(path))
    # Preserve extracted comments separately, including upstream copyright notices.
    notices = path.with_suffix(path.suffix + '.notices.txt')
    notices.write_text('\n\n'.join(result['notices']) + '\n')
    path.write_text(output)
