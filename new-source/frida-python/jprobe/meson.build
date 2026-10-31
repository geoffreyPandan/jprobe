if jprobe_core_dep.type_name() == 'internal'
  jprobe_core_subprj = subproject('frida-core')
  jprobe_gir = jprobe_core_subprj.get_variable('core_public_gir')
  glib_gir = jprobe_core_subprj.get_variable('glib_gir')
  gobject_gir = jprobe_core_subprj.get_variable('gobject_gir')
  gio_gir = jprobe_core_subprj.get_variable('gio_gir')
else
  girdir = jprobe_core_dep.get_variable('jprobe_girdir')
  jprobe_gir = girdir / 'Jprobe-1.0.gir'
  glib_gir = girdir / 'GLib-2.0.gir'
  gobject_gir = girdir / 'GObject-2.0.gir'
  gio_gir = girdir / 'Gio-2.0.gir'
endif

env = environment()
env.set('PYTHONPATH', [meson.current_source_dir(), meson.project_source_root() / 'frida-bindgen'])

code = custom_target('binding-code',
  output: [
    '__init__.py',
    '_jprobe.pyi',
    'extension.c',
    'aio.py',
  ],
  input: [
    jprobe_gir,
    glib_gir,
    gobject_gir,
    gio_gir,
    files(
      'jprobe_bindgen' / '__init__.py',
      'jprobe_bindgen' / '__main__.py',
      'jprobe_bindgen' / 'cli.py',
      'jprobe_bindgen' / 'codegen.py',
      'jprobe_bindgen' / 'customization.py',
      'jprobe_bindgen' / 'loader.py',
      'jprobe_bindgen' / 'model.py',
      'jprobe_bindgen' / 'assets' / 'codegen_gobject_globals.c',
      'jprobe_bindgen' / 'assets' / 'codegen_gobject_methods.c',
      'jprobe_bindgen' / 'assets' / 'codegen_gobject_prototypes.h',
      'jprobe_bindgen' / 'assets' / 'codegen_macros.h',
      'jprobe_bindgen' / 'assets' / 'codegen_structs.h',
      'jprobe_bindgen' / 'assets' / 'codegen_typedefs.h',
      'jprobe_bindgen' / 'assets' / 'facade_toplevel.py',
      'jprobe_bindgen' / 'assets' / 'facade_toplevel_aio.py',
      'jprobe_bindgen' / 'assets' / 'facade_cancellable.py',
      'jprobe_bindgen' / 'assets' / 'facade_cancellable_aio.py',
      'jprobe_bindgen' / 'assets' / 'facade_cancellable_helpers.py',
      'jprobe_bindgen' / 'assets' / 'facade_cancellable_helpers_aio.py',
      'jprobe_bindgen' / 'assets' / 'facade_device_members.py',
      'jprobe_bindgen' / 'assets' / 'facade_device_members_aio.py',
      'jprobe_bindgen' / 'assets' / 'facade_device_manager_members.py',
      'jprobe_bindgen' / 'assets' / 'facade_device_manager_members_aio.py',
      'jprobe_bindgen' / 'assets' / 'facade_bus.py',
      'jprobe_bindgen' / 'assets' / 'facade_bus_aio.py',
      'jprobe_bindgen' / 'assets' / 'facade_portal.py',
      'jprobe_bindgen' / 'assets' / 'facade_portal_aio.py',
      'jprobe_bindgen' / 'assets' / 'facade_rpc_helpers.py',
      'jprobe_bindgen' / 'assets' / 'facade_rpc_helpers_aio.py',
      'jprobe_bindgen' / 'assets' / 'facade_rpc_members.py',
      'jprobe_bindgen' / 'assets' / 'facade_rpc_members_aio.py',
      'jprobe_bindgen' / 'assets' / 'facade_iostream.py',
      'jprobe_bindgen' / 'assets' / 'facade_iostream_aio.py',
      'jprobe_bindgen' / 'assets' / 'facade_interface.py',
      'jprobe_bindgen' / 'assets' / 'facade_interface_aio.py',
      'jprobe_bindgen' / 'assets' / 'codegen_endpoint_parameters.c',
    ),
    files(
      meson.project_source_root() / 'frida-bindgen' / 'jprobe_bindgen_core' / '__init__.py',
      meson.project_source_root() / 'frida-bindgen' / 'jprobe_bindgen_core' / 'loader.py',
      meson.project_source_root() / 'frida-bindgen' / 'jprobe_bindgen_core' / 'model.py',
      meson.project_source_root() / 'frida-bindgen' / 'jprobe_bindgen_core' / 'naming.py',
    ),
  ],
  command: [
    python, '-m', 'jprobe_bindgen',
    '--jprobe-gir=@INPUT0@',
    '--glib-gir=@INPUT1@',
    '--gobject-gir=@INPUT2@',
    '--gio-gir=@INPUT3@',
    '--output-py=@OUTPUT0@',
    '--output-pyi=@OUTPUT1@',
    '--output-c=@OUTPUT2@',
    '--output-aio=@OUTPUT3@',
  ],
  env: env,
  install: true,
  install_dir: [
    python.get_install_dir() / 'jprobe',
    python.get_install_dir() / 'jprobe',
    false,
    python.get_install_dir() / 'jprobe',
  ]
)

py_sources = [
  'py.typed',
]
python.install_sources(py_sources, subdir: 'jprobe', pure: false)

extra_link_args = []
if host_os_family == 'darwin'
  extra_link_args += '-Wl,-exported_symbol,_PyInit__jprobe'
elif host_os_family != 'windows'
  extra_link_args += '-Wl,--version-script,' + meson.current_source_dir() / 'extension.version'
endif

extension = python.extension_module('_jprobe', code[2],
  limited_api: '3.7',
  c_args: jprobe_component_cflags,
  link_args: extra_link_args,
  dependencies: [python_dep, jprobe_core_dep, os_deps],
  install: true,
  subdir: 'jprobe',
)
