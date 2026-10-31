"""Preserve V8's English weekday output without a contiguous literal."""
from pathlib import Path

path = Path('/home/jim/jprobe/sdk-rebuild/src/v8/third_party/abseil-cpp/src/absl/time/internal/cctz/src/civil_time_detail.cc')
text = path.read_text()
old = '      return os << "Friday";'
new = '      return os << "Fri" << "day";'
if old in text:
    assert text.count(old) == 1
    text = text.replace(old, new)
else:
    assert new in text
path.write_text(text)
print('Patched V8 weekday literal:', path)
