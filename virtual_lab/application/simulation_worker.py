"""Isolated numerical job. No database, credential, HTTP or instrument access."""
import json
import socket
import sys


def denied(*args, **kwargs):
    raise RuntimeError('Numerical worker has no network access')


def main():
    socket.socket.connect = denied
    socket.socket.bind = denied
    from virtual_lab.application.simulation_runner import run_simulation
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError('Numerical request exceeds limit')
    result = run_simulation(json.loads(raw))
    sys.stdout.buffer.write(json.dumps(result, sort_keys=True, allow_nan=False).encode())


if __name__ == '__main__':
    main()
