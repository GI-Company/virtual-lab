"""Keep cyclic collection of Qt wrappers on the application's GUI thread.

The installed pyqtgraph collector exists for this Qt/Python threading hazard.
One timer belongs to the QApplication, rather than to individual windows.
Numerical subprocesses do not import this module or change their GC policy.
"""

import gc
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication
from pyqtgraph.util.garbage_collector import GarbageCollector


def ensure_gui_gc():
    app = QApplication.instance()
    if app is None:
        return None
    if QThread.currentThread() != app.thread():
        raise RuntimeError("Initialize Qt garbage collection on the GUI thread")
    guard = getattr(app, "_virtual_lab_gui_gc", None)
    if guard is None:
        previously_enabled = gc.isenabled()
        guard = GarbageCollector(interval=1.0)
        guard.timer.setParent(app)
        app._virtual_lab_gui_gc = guard

        def restore_policy():
            guard.timer.stop()
            if previously_enabled:
                gc.enable()

        app.destroyed.connect(restore_policy)
    return guard
