"""Preserve GLib's translated weekday while avoiding a contiguous identifier."""
from pathlib import Path

path = Path('/home/jim/jprobe/sdk-rebuild/src/glib/glib/gdatetime.c')
text = path.read_text()
old_helper = '''static const gchar *
get_weekday_five_name (void)
{
  static gchar name[7];
  static gsize initialized = 0;

  if (g_once_init_enter (&initialized))
    {
      const gchar first[] = { 'F', 'r', 'i' };
      const gchar last[] = { 'd', 'a', 'y', '\\0' };
      memcpy (name, first, sizeof first);
      memcpy (name + sizeof first, last, sizeof last);
      g_once_init_leave (&initialized, 1);
    }

  return name;
}

'''
translation_helper = '''static const gchar *
get_weekday_five_name_translated (void)
{
#ifdef ENABLE_NLS
  static gchar key[sizeof ("full weekday name") + 7];
  static gsize initialized = 0;

  if (g_once_init_enter (&initialized))
    {
      memcpy (key, "full weekday name\\004", sizeof ("full weekday name"));
      memcpy (key + sizeof ("full weekday name"), get_weekday_five_name (), 7);
      g_once_init_leave (&initialized, 1);
    }

  return glib_pgettext (key, sizeof ("full weekday name"));
#else
  return get_weekday_five_name ();
#endif
}

'''
anchor = '''static const gchar *
get_weekday_name (gint day)
{'''
if old_helper not in text:
    if translation_helper not in text:
        assert text.count(anchor) == 1
        text = text.replace(anchor, old_helper + translation_helper + anchor)
elif translation_helper not in text:
    text = text.replace(old_helper, old_helper + translation_helper)

for old in [
    '      return C_("full weekday name", "Friday");',
    '      return C_("full weekday name", get_weekday_five_name ());',
]:
    text = text.replace(old, '      return get_weekday_five_name_translated ();')
assert text.count('      return get_weekday_five_name_translated ();') == 1
path.write_text(text)
print('Patched GLib weekday translation:', path)
