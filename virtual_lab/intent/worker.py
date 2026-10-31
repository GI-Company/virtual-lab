"""Local CPU worker. JSON only; no pickle, model downloads, network or ledger access."""

import json
import socket
import sys


def deny(*_, **__):
    raise RuntimeError("INTENT numerical worker has no network access")


socket.socket.connect = deny
socket.socket.bind = deny
from virtual_lab.intent.model import MiniModel, canonical


def main():
    raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Worker request exceeds limit")
    request = json.loads(raw)
    if set(request) != {"state", "x", "y", "example_id"}:
        raise ValueError("Unsupported worker request")
    model = MiniModel.from_state(request["state"])
    metrics = model.fit_one(request["x"], request["y"], request["example_id"])
    sys.stdout.buffer.write(canonical({"state": model.state(), "metrics": metrics}))


if __name__ == "__main__":
    main()
