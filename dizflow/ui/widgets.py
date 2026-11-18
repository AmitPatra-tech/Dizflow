"""Small reusable widgets."""
from PySide6.QtCore import Qt, QRectF, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
                               QButtonGroup, QSizePolicy)

from .theme import ACCENT, ACCENT_SOFT, LINE, MUTED
from ..system import pretty_combo


def card(object_name="card") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName(object_name)
    lay = QVBoxLayout(f)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(10)
    return f, lay


def label(text, name=None, wrap=False) -> QLabel:
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


def kbd_row(combo: str, dark=False) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    for i, part in enumerate(pretty_combo(combo).split(" + ")):
        if i:
            lay.addWidget(label("+", "muted" if dark else None))
        lay.addWidget(label(part, "kbdDark" if dark else "kbd"))
    w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return w


class StatCard(QFrame):
    def __init__(self, title, icon=""):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(2)
        self.value = label("0", "statValue")
        lay.addWidget(label(f"{icon}  {title}" if icon else title, "statLabel"))
        lay.addWidget(self.value)

    def set(self, v):
        self.value.setText(str(v))


class WeekChart(QWidget):
    def __init__(self):
        super().__init__()
        self.data = []
        self.setMinimumHeight(150)

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, _):
        if not self.data:
            return
        from datetime import date
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        top, bottom = 22, h - 24
        mx = max(1, max(v for _, v in self.data))
        n = len(self.data)
        slot = w / n
        bw = min(34, slot * 0.6)
        many = n > 10
        p.setFont(QFont("Segoe UI", 8))
        for i, (d, v) in enumerate(self.data):
            x = i * slot + (slot - bw) / 2
            bh = max(4, (bottom - top) * v / mx) if v else 4
            today = i == n - 1
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ACCENT) if today else QColor(ACCENT_SOFT) if v else QColor(LINE))
            p.drawRoundedRect(QRectF(x, bottom - bh, bw, bh), min(6, bw / 2), min(6, bw / 2))
            p.setPen(QColor(MUTED))
            day = date.fromisoformat(d)
            if not many or today or i % 5 == 0:
                text = "Today" if today and not many else day.strftime("%d %b" if many else "%a")
                p.drawText(QRectF(i * slot - 20, bottom + 4, slot + 40, 18), Qt.AlignCenter, text)
            if v and not many:
                p.drawText(QRectF(i * slot, bottom - bh - 18, slot, 16), Qt.AlignCenter, f"{v:,}")
        p.end()


class AppBar(QWidget):
    """One row of the 'apps you use most' list: name, bar, numbers."""

    def __init__(self, name, ratio, detail):
        super().__init__()
        self.name, self.ratio, self.detail = name, ratio, detail
        self.setFixedHeight(34)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        name_w, detail_w = 150, 230
        p.setPen(QColor("#15151C"))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(QRectF(0, 0, name_w - 10, h), Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(self.name, Qt.ElideRight, name_w - 10))
        bar_w = max(0, w - name_w - detail_w - 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(LINE))
        p.drawRoundedRect(QRectF(name_w, h / 2 - 6, bar_w, 12), 6, 6)
        p.setBrush(QColor(ACCENT))
        p.drawRoundedRect(QRectF(name_w, h / 2 - 6, max(12, bar_w * self.ratio), 12), 6, 6)
        p.setPen(QColor(MUTED))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRectF(w - detail_w, 0, detail_w, h), Qt.AlignVCenter | Qt.AlignRight, self.detail)
        p.end()


class Segmented(QWidget):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], current: str):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.group = QButtonGroup(self)
        for value, text in options:
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(value == current)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, v=value: self.changed.emit(v))
            self.group.addButton(b)
            lay.addWidget(b)
        lay.addStretch()


class LevelMeter(QWidget):
    """Live microphone level bar (used in setup and settings)."""

    def __init__(self, level_fn):
        super().__init__()
        self.level_fn = level_fn
        self.v = 0.0
        self.setFixedHeight(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.t = QTimer(self, interval=40, timeout=self._tick)

    def start(self):
        self.t.start()

    def stop(self):
        self.t.stop()
        self.v = 0
        self.update()

    def _tick(self):
        self.v = max(min(1.0, self.level_fn() * 14), self.v * 0.85)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(LINE))
        p.drawRoundedRect(QRectF(0, 0, self.width(), 10), 5, 5)
        p.setBrush(QColor("#22C3A6"))
        p.drawRoundedRect(QRectF(0, 0, max(10, self.width() * self.v), 10), 5, 5)
        p.end()
