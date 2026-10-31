"""Regress the observed Qt-wrapper traversal from a simulation worker thread."""

import gc
import threading
from PySide6.QtCore import QTimer
from virtual_lab.gui.shell.gui_gc import ensure_gui_gc


def test_collection_is_app_owned_and_runs_on_gui_thread(qtbot, qapp):
    guard = ensure_gui_gc()
    assert ensure_gui_gc() is guard and guard.timer.parent() is qapp
    assert not gc.isenabled()
    main = threading.get_ident()
    collected = []
    finished = threading.Event()

    def callback(phase, info):
        if phase == "start":
            collected.append(threading.get_ident())

    def allocate_cycles():
        for _ in range(5000):
            item = []
            item.append(item)
        finished.set()

    original = guard.threshold
    guard.threshold = (0, 0, 0)
    gc.callbacks.append(callback)
    thread = threading.Thread(target=allocate_cycles)
    try:
        thread.start()
        QTimer.singleShot(0, guard.check)
        qtbot.waitUntil(lambda: finished.is_set() and bool(collected), timeout=3000)
        assert set(collected) == {main}
    finally:
        thread.join(timeout=3)
        guard.threshold = original
        gc.callbacks.remove(callback)
