"""Link Linux agents against the isolated weekday-correct libstdc++ copy."""

from pathlib import Path


path = Path("/home/jim/jprobe/full-source/subprojects/frida-core/lib/agent/meson.build")
source = path.read_text()
anchor = "  extra_link_args += prospero_crt_link_args\n"
addition = '''  if host_os == 'linux' and host_arch in ['x86', 'x86_64']
    libstdcxx_dir = '/home/jim/jprobe/gcc-time-r5' / host_arch
    extra_link_args += '-L' + libstdcxx_dir
    extra_link_depends += libstdcxx_dir / 'libstdc++.a'
  endif

'''
if addition in source:
    print("Isolated libstdc++ link already configured")
else:
    if source.count(anchor) != 1:
        raise ValueError("Unexpected Linux agent build layout")
    path.write_text(source.replace(anchor, addition + anchor))
    print("Patched", path)
