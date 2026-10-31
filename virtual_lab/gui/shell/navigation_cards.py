"""Native vector artwork and accessible cards for research navigation.

These widgets present the domain registry; they do not activate any tool.
"""

from math import cos, pi, sin

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)


def discipline_icon(domain_id, color="#7dcfff", size=48):
    """Draw a small resolution-independent discipline glyph using Qt only."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / 48, size / 48)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#1b3044"))
    painter.drawRoundedRect(QRectF(0, 0, 48, 48), 12, 12)
    pen = QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    def line(x1, y1, x2, y2):
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def node(x, y, radius=2.4):
        painter.setBrush(QColor("#1b3044"))
        painter.drawEllipse(QPointF(x, y), radius, radius)
        painter.setBrush(Qt.NoBrush)

    if domain_id == "mass_spectrometry":
        line(8, 36, 40, 36)
        for x, peak in ((13, 26), (20, 12), (27, 20), (34, 28)):
            line(x, 35, x, peak)
        line(8, 36, 8, 12)
    elif domain_id == "molecular_biology":
        points = [
            QPointF(24 + 12 * cos(pi / 3 * n), 24 + 12 * sin(pi / 3 * n))
            for n in range(6)
        ]
        for n, point in enumerate(points):
            painter.drawLine(point, points[(n + 1) % 6])
        line(36, 24, 41, 19)
        for point in points:
            node(point.x(), point.y())
    elif domain_id == "computational_biology":
        points = ((10, 16), (10, 33), (24, 10), (24, 25), (38, 17), (38, 34))
        for a, b in ((0, 2), (0, 3), (1, 3), (2, 4), (3, 4), (3, 5)):
            line(*points[a], *points[b])
        for point in points:
            node(*point)
    elif domain_id == "physics_simulation":
        painter.save()
        painter.translate(24, 24)
        for angle in (0, 60, 120):
            painter.save()
            painter.rotate(angle)
            painter.drawEllipse(QRectF(-17, -6, 34, 12))
            painter.restore()
        painter.restore()
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(24, 24), 2.5, 2.5)
    elif domain_id == "instruments_sensors":
        path = QPainterPath(QPointF(6, 26))
        for point in ((13, 26), (17, 14), (22, 35), (28, 10), (33, 26), (41, 26)):
            path.lineTo(QPointF(*point))
        painter.drawPath(path)
        line(7, 38, 40, 38)
    elif domain_id == "data_analysis":
        line(8, 37, 40, 37)
        for x, top in ((12, 27), (22, 19), (32, 11)):
            painter.drawRoundedRect(QRectF(x, top, 5, 36 - top), 1, 1)
    else:
        path = QPainterPath(QPointF(7, 14))
        for point in ((18, 14), (22, 18), (40, 18), (40, 36), (7, 36), (7, 14)):
            path.lineTo(QPointF(*point))
        painter.drawPath(path)
        line(12, 25, 34, 25)
        line(12, 30, 27, 30)
    painter.end()
    return QIcon(pixmap)


def _label(text, *, color="#edf4fc", bold=False, size=12):
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    label.setAttribute(Qt.WA_TransparentForMouseEvents)
    label.setFocusPolicy(Qt.NoFocus)
    label.setStyleSheet(
        f"background: transparent; border: none; color: {color}; "
        f"font-size: {size}px; font-weight: {'600' if bold else '400'};"
    )
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    return label


class _DisciplineIcon(QLabel):
    """Preserve the deliberate status palette when the parent tile is disabled."""

    def paintEvent(self, event):
        pixmap = self.pixmap()
        if pixmap is not None and not pixmap.isNull():
            painter = QPainter(self)
            painter.drawPixmap(self.rect(), pixmap)
            painter.end()


class DisciplineCard(QPushButton):
    """One keyboard-focusable target for a domain's icon, description and status."""

    def __init__(self, domain, availability, installed_count, total_count, parent=None):
        super().__init__(parent)
        status = getattr(availability, "value", availability)
        palette = {
            "enabled": ("Available", "#88e6ca", "#173c38"),
            "experimental": ("Experimental", "#f4cf8b", "#403522"),
            "unavailable": ("Unavailable", "#c0ccda", "#2a3442"),
        }
        if status not in palette:
            raise ValueError("Unknown discipline availability")
        status_text, accent, badge_background = palette[status]
        available = status != "unavailable"
        self.setObjectName("disciplineCard")
        self.setAccessibleName(domain.title)
        tool_count = (
            f"{installed_count} of {total_count} tools installed"
            if available
            else "No discipline-specific tools installed"
        )
        self.setAccessibleDescription(
            f"{domain.description}. {status_text}. {tool_count}."
        )
        self.setToolTip(tool_count)
        self.setEnabled(available)
        self.setMinimumHeight(142)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setCursor(Qt.PointingHandCursor if available else Qt.ArrowCursor)
        self.setStyleSheet(
            """
            QPushButton#disciplineCard {
                background: #162332; border: 2px solid #2a3a50;
                border-radius: 12px; text-align: left; padding: 0;
            }
            QPushButton#disciplineCard:hover:enabled { background: #1b2d40; border-color: #508bb8; }
            QPushButton#disciplineCard:focus:enabled { border-color: #84d3ff; }
            QPushButton#disciplineCard:pressed:enabled { background: #20384d; }
            QPushButton#disciplineCard:disabled { background: #121c28; border-color: #253245; }
        """
        )
        layout = QGridLayout(self)
        layout.setContentsMargins(16, 15, 16, 14)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(7)
        icon_label = _DisciplineIcon()
        icon_label.setPixmap(
            discipline_icon(domain.id, accent).pixmap(QSize(48, 48), QIcon.Normal)
        )
        icon_label.setFixedSize(48, 48)
        icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        icon_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon_label, 0, 0, 2, 1, Qt.AlignTop)
        self.title_label = _label(
            domain.title,
            bold=True,
            size=14,
            color="#edf4fc" if available else "#bcc8d8",
        )
        layout.addWidget(self.title_label, 0, 1)
        self.status_label = _label(status_text, color=accent, bold=True, size=10)
        self.status_label.setWordWrap(False)
        self.status_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.status_label.setStyleSheet(
            f"background: {badge_background}; color: {accent}; border: none; "
            "border-radius: 9px; padding: 4px 7px; font-size: 10px; font-weight: 600;"
        )
        layout.addWidget(self.status_label, 0, 2, Qt.AlignRight | Qt.AlignTop)
        self.description_label = _label(
            domain.description, color="#b1c0d2" if available else "#95a5bb", size=11
        )
        layout.addWidget(self.description_label, 1, 1, 1, 2)
        self.count_label = _label(tool_count, color="#90a7bf", size=10)
        layout.addWidget(self.count_label, 2, 1, 1, 2)
        layout.setColumnStretch(1, 1)

    def sizeHint(self):
        return QSize(360, max(150, self.layout().sizeHint().height()))

    def minimumSizeHint(self):
        return QSize(270, max(142, self.layout().minimumSize().height()))


class RecentProjectCard(QFrame):
    """Display-only list row; the owning QListWidget retains selection and focus."""

    def __init__(self, name, subtitle, parent=None):
        super().__init__(parent)
        self.setObjectName("recentProjectCard")
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAccessibleName(name)
        self.setAccessibleDescription(subtitle)
        self.setMinimumHeight(64)
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("selected", False)
        self.setStyleSheet(
            """
            QFrame#recentProjectCard {
                background: #162332; border: 1px solid #2a3a50; border-radius: 8px;
            }
            QFrame#recentProjectCard[selected="true"] {
                background: #213d56; border: 1px solid #7dcfff;
            }
        """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(4)
        self.name_label = _label(name, bold=True, size=13)
        self.subtitle_label = _label(subtitle, color="#a8bbcf", size=11)
        layout.addWidget(self.name_label)
        layout.addWidget(self.subtitle_label)
        self.setAutoFillBackground(True)

    def set_selected(self, selected):
        """Reflect the owning list's selection without taking keyboard focus."""
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)
        self.setAutoFillBackground(True)
        self.update()
