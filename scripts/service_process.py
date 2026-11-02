"""Graceful lifecycle for isolated HTTP qualification children on each OS."""
import os
import signal
import subprocess


def launch_service(command, stream):
    # Windows terminate() uses TerminateProcess: it cannot run ASGI lifespan
    # cleanup or close/checkpoint SQLite. Give the child its own console group
    # so Uvicorn's SIGBREAK handler can finish that cleanup instead.
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {}
    return subprocess.Popen(command, stdout=stream, stderr=stream, **options)


def stop_service(process):
    if process.poll() is not None:
        return
    try:
        if os.name == 'nt':
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        process.kill()
        process.wait(timeout=5)
        raise RuntimeError('Qualification service did not shut down gracefully') from exc
