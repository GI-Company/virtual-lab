"""Isolated worker: one JSON request on stdin, one JSON completion on stdout."""
import contextlib
import json
import sys
from pydantic import ValidationError

from .adapters import InstrumentError, adapter_for
from .artifacts import execute
from .requests import parse_request


def main():
    try:
        raw = sys.stdin.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Request is too large.")
        request = parse_request(json.loads(raw))
        with contextlib.redirect_stdout(sys.stderr):
            result = execute(request, adapter_for(request))
        print(json.dumps({"ok": True, "manifest_path": result.manifest_path, "sha256": result.sha256}))
        return 0
    except InstrumentError as exc:
        message = str(exc)
    except ValidationError as exc:
        message = "; ".join(e["msg"] for e in exc.errors(include_input=False))
    except (ValueError, KeyError, TypeError):
        message = "Invalid request or unexpected provider response. No completed run was recorded."
    except Exception:
        message = "The computational run failed. Check storage, dependencies, and network access."
    print(json.dumps({"ok": False, "error": message}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
