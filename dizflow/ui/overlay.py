"""Floating pill near the bottom of the screen that shows what Dizflow is doing. Never takes focus."""
import math
import time

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QGuiApplication
from PySide6.QtWidgets import QWidget

from .theme import ACCENT, ACCENT_2, RECORD

BARS = 18


class Overlay(QWidget):
    def __init__(self, engine):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.engine = engine
        self.mode = "idle"
        self.message = ""
        self.levels = [0.0] * BARS
        self.started = 0.0
        self.resize(220, 46)
        self.timer = QTimer(self, interval=33, timeout=self._tick)
        self.hide_timer = QTimer(self, singleShot=True, timeout=self._hide)
        engine.state.connect(self.set_mode)
        engine.notice.connect(self.flash)

    def _place(self):
        screen = QGuiApplication.screenAt(self.cursor().pos()) or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        self.move(g.center().x() - self.width() // 2, g.bottom() - self.height() - 28)

    def set_mode(self, mode):
        if mode in ("recording", "command", "processing"):
            if self.mode not in ("recording", "command"):
                self.levels = [0.0] * BARS
                self.started = time.time()
            self.mode = mode
            self.message = ""
            self.hide_timer.stop()
            self._place()
            self.show()
            self.timer.start()
        elif mode == "error":
            self.mode = "error"
            self.hide_timer.start(2200)
        else:
            if self.message:  # keep a notice visible a little longer
                self.mode = "notice"
                self.hide_timer.start(2200)
            else:
                self._hide()

    def flash(self, text):
        self.message = text
        self.mode = "notice"
        fm_w = self.fontMetrics().horizontalAdvance(text) + 56
        self.resize(max(220, min(fm_w, 640)), 46)
        self._place()
        self.show()
        self.timer.start()
        self.hide_timer.start(2600)

    def _hide(self):
        self.mode = "idle"
        self.message = ""
        self.timer.stop()
        self.resize(220, 46)
        self.hide()

    def _tick(self):
        if self.mode in ("recording", "command"):
            self.levels = self.levels[1:] + [min(1.0, self.engine.level * 16)]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(18, 18, 26, 235))
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        cy = h / 2
        if self.mode in ("recording", "command"):
            color = QColor(RECORD) if self.mode == "recording" else QColor(ACCENT_2)
            pulse = 0.6 + 0.4 * math.sin(time.time() * 6)
            color.setAlphaF(pulse)
            p.setBrush(color)
            p.drawEllipse(QPointF(22, cy), 5, 5)
            pen = QPen(QColor("white"), 3, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            for i, v in enumerate(self.levels):
                x = 40 + i * 7
                bh = 3 + v * (h - 18)
                p.drawLine(QPointF(x, cy - bh / 2), QPointF(x, cy + bh / 2))
            p.setPen(QColor(200, 200, 215))
            p.setFont(QFont("Segoe UI", 8))
            label = f"{int(time.time() - self.started)}s" if self.mode == "recording" else "cmd"
            p.drawText(QRectF(w - 44, 0, 34, h), Qt.AlignVCenter | Qt.AlignRight, label)
        elif self.mode == "processing":
            t = time.time() * 5
            p.setBrush(QColor(ACCENT))
            for i in range(3):
                y = cy + 5 * math.sin(t - i * 0.9)
                p.setBrush(QColor("white") if i == 1 else QColor(ACCENT))
                p.drawEllipse(QPointF(w / 2 - 18 + i * 18, y), 4.5, 4.5)
        elif self.mode in ("notice", "error"):
            p.setPen(QColor("white"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(18, 0, w - 36, h), Qt.AlignCenter, self.message or "Something went wrong")
        p.end()
