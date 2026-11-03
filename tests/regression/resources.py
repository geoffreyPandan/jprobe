"""Verify socket ownership without relying on optional ss process annotations."""
import re
import shlex
import time


def verify_heartbeat_time(heartbeat_ms, device_seconds, max_age=15):
    """Compare clocks on the same device; date +%s has one-second precision."""
    age = float(device_seconds) - float(heartbeat_ms) / 1000
    if not -1 < age < max_age:
        raise AssertionError(f'stale or future device heartbeat: age={age:.3f}s')
    return age


def listening_inodes(tables, port):
    result = set()
    for line in tables.splitlines():
        fields = line.split()
        if len(fields) < 10 or fields[3] != '0A':
            continue
        try:
            if int(fields[1].rsplit(':', 1)[1], 16) == port:
                result.add(fields[9])
        except (ValueError, IndexError):
            continue
    return result


def owns_listener(tables, fd_links, port):
    return bool(listening_inodes(tables, port) & set(re.findall(r'socket:\[(\d+)\]', fd_links)))


def wait_listener(shell, pid, path, port, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        actual = shell(f'readlink /proc/{pid}/exe', check=False)
        if actual.removesuffix(' (deleted)') == path:
            tables = shell('cat /proc/net/tcp /proc/net/tcp6')
            links = shell(f'ls -l /proc/{pid}/fd', check=False)
            if owns_listener(tables, links, port):
                return
        time.sleep(.1)
    raise RuntimeError(f'Could not verify owned listener PID={pid} port={port}')


def stop_owned(shell, pid, path, timeout=3):
    """Only signal the exact per-run executable; recheck before escalation."""
    pid = int(pid)
    def matches():
        return shell(f'readlink /proc/{pid}/exe', check=False).removesuffix(' (deleted)') == path
    if not matches():
        return
    # Recheck in the same device command as the signal to minimize PID reuse risk.
    def kill(sig):
        guard = f'e=$(readlink /proc/{pid}/exe); if [ "$e" = {shlex.quote(path)} ] || [ "$e" = {shlex.quote(path + " (deleted)")} ]; then kill -{sig} {pid}; fi'
        shell(guard, check=False)
    for sig in ('TERM', 'KILL'):
        kill(sig)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not matches():
                return
            time.sleep(.1)
    raise RuntimeError(f'Owned process did not exit: {pid} {path}')
