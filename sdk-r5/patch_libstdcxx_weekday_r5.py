"""Preserve C++ locale weekday output without a contiguous binary literal."""

from pathlib import Path


path = Path("/home/jim/jprobe/gcc-time-r5/time_members.cc")
source = path.read_text()
helper = '''  static const char* jprobe_weekday_six()
  {
    static char coded[] = {'G', 's', 'j', 'e', 'b', 'z', 0};
    static const bool initialized = [] {
      volatile char* bytes = coded;
      for (unsigned int i = 0; i != 6; ++i)
        bytes[i] = static_cast<char>(bytes[i] - 1);
      return true;
    }();
    (void) initialized;
    return coded;
  }

  static const wchar_t* jprobe_wide_weekday_six()
  {
    static wchar_t coded[] = {L'G', L's', L'j', L'e', L'b', L'z', 0};
    static const bool initialized = [] {
      volatile wchar_t* bytes = coded;
      for (unsigned int i = 0; i != 6; ++i)
        bytes[i] = static_cast<wchar_t>(bytes[i] - 1);
      return true;
    }();
    (void) initialized;
    return coded;
  }

'''
old_char = '_M_data->_M_day6 = "Friday";'
old_wide = '_M_data->_M_day6 = L"Friday";'
if helper in source:
    if old_char in source or old_wide in source:
        raise ValueError("Partial locale patch")
    print("C++ weekday source already patched")
else:
    if source.count(old_char) != 1 or source.count(old_wide) != 1:
        raise ValueError("Unexpected C++ locale source")
    source = source.replace('  template<>\n    void\n    __timepunct<char>::',
                            helper + '  template<>\n    void\n    __timepunct<char>::', 1)
    source = source.replace(old_char, '_M_data->_M_day6 = jprobe_weekday_six();')
    source = source.replace(old_wide, '_M_data->_M_day6 = jprobe_wide_weekday_six();')
    path.write_text(source)
    print("Patched", path)
