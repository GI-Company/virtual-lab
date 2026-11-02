from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import service_process as lifecycle


def test_windows_launch_and_graceful_break(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    popen = Mock(return_value=process)
    monkeypatch.setattr(lifecycle, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(lifecycle, 'signal', SimpleNamespace(CTRL_BREAK_EVENT=123))
    monkeypatch.setattr(lifecycle, 'subprocess', SimpleNamespace(Popen=popen,
        CREATE_NEW_PROCESS_GROUP=456, TimeoutExpired=TimeoutError))
    stream = object()
    assert lifecycle.launch_service(['python', 'server'], stream) is process
    popen.assert_called_once_with(['python', 'server'], stdout=stream, stderr=stream, creationflags=456)
    lifecycle.stop_service(process)
    process.send_signal.assert_called_once_with(123)
    process.terminate.assert_not_called()
    process.wait.assert_called_once_with(timeout=10)


def test_posix_terminate_and_already_finished_noop(monkeypatch):
    monkeypatch.setattr(lifecycle, 'os', SimpleNamespace(name='posix'))
    process = Mock()
    process.poll.return_value = None
    lifecycle.stop_service(process)
    process.terminate.assert_called_once_with()
    process.send_signal.assert_not_called()
    process.reset_mock()
    process.poll.return_value = 0
    lifecycle.stop_service(process)
    process.terminate.assert_not_called()


def test_forced_cleanup_does_not_claim_graceful_shutdown(monkeypatch):
    monkeypatch.setattr(lifecycle, 'os', SimpleNamespace(name='posix'))
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = [lifecycle.subprocess.TimeoutExpired('server', 10), 0]
    with pytest.raises(RuntimeError, match='did not shut down gracefully'):
        lifecycle.stop_service(process)
    process.kill.assert_called_once_with()
    assert process.wait.call_count == 2
