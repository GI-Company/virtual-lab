"""
virtual_lab.gui.shell.system_monitor
──────────────────────────────────────
Compact always-visible hardware monitor for the main window header.

Shows in real-time (1 Hz poll):
  ▸ Metal GPU — active MLX memory / total unified memory (Apple M-series)
  ▸ RAM        — used / total
  ▸ Disk       — free on the VirtualLab data volume

Uses only mlx.core and psutil — no subprocesses, no blocking calls.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel


def _fmt_bytes(n: int, decimals: int = 1) -> str:
    """Format bytes into human-readable GiB / MiB string."""
    gib = n / (1024 ** 3)
    if gib >= 1.0:
        return f"{gib:.{decimals}f} GiB"
    mib = n / (1024 ** 2)
    return f"{mib:.0f} MiB"


class SystemMonitorWidget(QWidget):
    """
    Small horizontal pill that lives in the main window header.
    Polls every second; updates labels without blocking the UI thread.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()  # immediate first read

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(14)

        style_label = "color: #64748b; font-size: 10px; font-weight: bold; letter-spacing: 0.05em;"
        style_value = "color: #94a3b8; font-size: 10px; font-family: monospace;"
        style_warn  = "color: #f59e0b; font-size: 10px; font-family: monospace; font-weight: bold;"
        style_crit  = "color: #ef4444; font-size: 10px; font-family: monospace; font-weight: bold;"
        self._style_value = style_value
        self._style_warn  = style_warn
        self._style_crit  = style_crit

        # Metal / GPU
        lbl_gpu = QLabel("METAL")
        lbl_gpu.setStyleSheet(style_label)
        self._val_gpu = QLabel("—")
        self._val_gpu.setStyleSheet(style_value)
        layout.addWidget(lbl_gpu)
        layout.addWidget(self._val_gpu)

        # RAM
        lbl_ram = QLabel("RAM")
        lbl_ram.setStyleSheet(style_label)
        self._val_ram = QLabel("—")
        self._val_ram.setStyleSheet(style_value)
        layout.addWidget(lbl_ram)
        layout.addWidget(self._val_ram)

        # Disk
        lbl_disk = QLabel("DISK")
        lbl_disk.setStyleSheet(style_label)
        self._val_disk = QLabel("—")
        self._val_disk.setStyleSheet(style_value)
        layout.addWidget(lbl_disk)
        layout.addWidget(self._val_disk)

    # ── Polling ───────────────────────────────────────────────────────────────

    def _refresh(self):
        self._update_metal()
        self._update_ram()
        self._update_disk()

    def _update_metal(self):
        """Read MLX Metal active + cache memory and total unified memory."""
        try:
            import mlx.core as mx
            active  = mx.get_active_memory()
            cache   = mx.get_cache_memory()
            used    = active + cache
            total   = mx.device_info().get("memory_size", 0)

            if total > 0:
                pct = used / total * 100
                text = f"{_fmt_bytes(used)} / {_fmt_bytes(total)}  ({pct:.0f}%)"
                if pct > 85:
                    self._val_gpu.setStyleSheet(self._style_crit)
                elif pct > 65:
                    self._val_gpu.setStyleSheet(self._style_warn)
                else:
                    self._val_gpu.setStyleSheet(self._style_value)
            else:
                text = _fmt_bytes(used)
                self._val_gpu.setStyleSheet(self._style_value)
            self._val_gpu.setText(text)
        except Exception:
            self._val_gpu.setText("unavailable")

    def _update_ram(self):
        try:
            import psutil
            vm = psutil.virtual_memory()
            pct = vm.percent
            text = f"{_fmt_bytes(vm.used)} / {_fmt_bytes(vm.total)}  ({pct:.0f}%)"
            if pct > 90:
                self._val_ram.setStyleSheet(self._style_crit)
            elif pct > 75:
                self._val_ram.setStyleSheet(self._style_warn)
            else:
                self._val_ram.setStyleSheet(self._style_value)
            self._val_ram.setText(text)
        except Exception:
            self._val_ram.setText("unavailable")

    def _update_disk(self):
        try:
            import psutil, os
            # Use the VirtualLab data dir if set, else home
            path = os.environ.get("VIRTUALLAB_DATA_DIR", str(__import__("pathlib").Path.home()))
            usage = psutil.disk_usage(path)
            free_pct = usage.free / usage.total * 100
            text = f"{_fmt_bytes(usage.free)} free / {_fmt_bytes(usage.total)}"
            if free_pct < 5:
                self._val_disk.setStyleSheet(self._style_crit)
            elif free_pct < 15:
                self._val_disk.setStyleSheet(self._style_warn)
            else:
                self._val_disk.setStyleSheet(self._style_value)
            self._val_disk.setText(text)
        except Exception:
            self._val_disk.setText("unavailable")
