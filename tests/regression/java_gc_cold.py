#!/usr/bin/env python3
"""Cold-boot Java Hook regression for an explicitly selected emulator clone."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def command(args, timeout=120, check=True):
    result = subprocess.run([str(x) for x in args], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout)
    if check and result.returncode != 0:
        raise RuntimeError(f'{args[0]} exit={result.returncode}: '
                           f'{result.stderr[-2000:]} {result.stdout[-2000:]}')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial', required=True)
    parser.add_argument('--server', required=True, type=Path)
    parser.add_argument('--fixture', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repetitions', type=int, default=3)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error('--repetitions must be positive')

    root = Path(__file__).resolve().parents[3]
    runner = Path(__file__).with_name('run.py')
    args.output.mkdir(parents=True, exist_ok=False)
    state = {'state': 'RUNNING', 'serial': args.serial, 'jobs': []}

    def save():
        temporary = args.output / 'campaign.tmp'
        temporary.write_text(json.dumps(state, indent=2) + '\n')
        temporary.replace(args.output / 'campaign.json')

    try:
        for repetition in range(args.repetitions):
            before = command(['adb', '-s', args.serial, 'shell',
                              'cat /proc/sys/kernel/random/boot_id']).stdout.strip()
            command(['adb', '-s', args.serial, 'reboot'])
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                probe = command(['adb', '-s', args.serial, 'shell',
                                 'getprop sys.boot_completed'], timeout=8,
                                check=False)
                if probe.returncode == 0 and probe.stdout.strip() == '1':
                    break
                time.sleep(2)
            else:
                raise RuntimeError('selected device did not finish booting')

            after = command(['adb', '-s', args.serial, 'shell',
                             'cat /proc/sys/kernel/random/boot_id']).stdout.strip()
            if not after or after == before:
                raise RuntimeError('boot ID did not change')

            for runtime in ('qjs', 'v8'):
                name = f'{repetition:02d}-{runtime}'
                output = args.output / name
                job = {'name': name, 'runtime': runtime, 'bootId': after,
                       'state': 'RUNNING', 'started': time.time()}
                state['jobs'].append(job)
                state['current'] = name
                save()
                invocation = [sys.executable, str(runner), '--serial', args.serial,
                              '--variant', 'r9', '--runtime', runtime,
                              '--suite', 'smoke', '--server', args.server,
                              '--fixture', args.fixture, '--output', output]
                with (args.output / f'{name}.log').open('w') as log:
                    result = subprocess.run(invocation, stdout=log,
                                            stderr=subprocess.STDOUT)
                job.update(state='PASSED' if result.returncode == 0 else 'FAILED',
                           exitCode=result.returncode, finished=time.time())
                results = output / 'results.json'
                if results.exists():
                    job['counts'] = json.loads(results.read_text())['counts']
                save()
        state['state'] = ('PASSED' if all(j['state'] == 'PASSED'
                                          for j in state['jobs'])
                          else 'FINISHED_WITH_FAILURES')
    except Exception as error:
        state.update(state='ERROR', error=str(error))
        raise
    finally:
        state['finished'] = time.time()
        save()

    return 0 if state['state'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
