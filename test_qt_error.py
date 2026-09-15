from PySide6.QtCore import QObject, Signal
import sys

class Emitter(QObject):
    sig = Signal(str)
    
    def emit_sig(self):
        try:
            self.sig.emit("hello")
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")

e = Emitter()
# Delete the C++ object?
import shiboken6
shiboken6.delete(e)
e.emit_sig()
