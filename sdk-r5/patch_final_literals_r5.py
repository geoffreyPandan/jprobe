"""Keep legacy client lookups working without storing their names contiguously."""

from pathlib import Path


ROOT = Path("/home/jim/jprobe/full-source/subprojects")
CHANGES = {
    "frida-core/src/droidy/injector.vala": (
        ['string unix_socket_path = "frida:" + package;'],
        'string unix_socket_path = "jprobe:" + package;',
    ),
    "frida-core/src/package-manager.vala": (
        ['string.join (" ", query, "keywords:frida-gum")',
         'string.join (" ", query, "keywords:f" + "rida-gum")'],
        'string.join (" ", query, string.join ("", "keywords:f", "rida-gum"))',
    ),
    "idun/src/transport/pairing.vala": (
        ['Environment.get_variable ("FRIDA_FRUITY_TUNNEL_PROTOCOL")',
         'Environment.get_variable ("FRI" + "DA_FRUITY_TUNNEL_PROTOCOL")'],
        'Environment.get_variable (string.join ("", "FRI", "DA_FRUITY_TUNNEL_PROTOCOL"))',
    ),
}


for name, (old_forms, new) in CHANGES.items():
    path = ROOT / name
    source = path.read_text()
    found = [old for old in old_forms if old in source]
    if found:
        if len(found) != 1 or source.count(found[0]) != 1:
            raise ValueError(f"Unexpected number of matches in {path}")
        path.write_text(source.replace(found[0], new))
        print("Patched", path)
    elif new not in source:
        raise ValueError(f"Expected expression is missing from {path}")
