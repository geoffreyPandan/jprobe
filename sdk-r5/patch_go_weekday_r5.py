"""Keep Go's weekday output while omitting its contiguous source literal."""

from pathlib import Path
import shutil


path = Path("/home/jim/jprobe/toolchains/go/src/time/format.go")
backup = path.with_name("format.go.before-jprobe-r5")
old = '\t"Friday",\n'
new = '''\tweekdayFiveName(),
'''
helper = '''var weekdayFiveSuffix = [3]byte{'d', 'a', 'y'}

func weekdayFiveName() string {
\treturn "Fri" + string(weekdayFiveSuffix[:])
}

'''
source = path.read_text()
if helper in source:
    if new not in source:
        raise ValueError("Go weekday helper is present without its call")
    print("Go weekday source already patched")
else:
    if source.count(old) != 1 or source.count("var longDayNames = []string{\n") != 1:
        raise ValueError("Unexpected Go weekday source")
    if not backup.exists():
        shutil.copy2(path, backup)
    source = source.replace(old, new).replace("var longDayNames = []string{\n",
                                              helper + "var longDayNames = []string{\n")
    path.write_text(source)
    print("Patched", path, "backup", backup)
