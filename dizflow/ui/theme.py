from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QLinearGradient, QPen

ACCENT = "#6D5EF5"
ACCENT_2 = "#22C3A6"
INK = "#15151C"
BG = "#F6F6FA"
CARD = "#FFFFFF"
MUTED = "#6B6B7B"
LINE = "#E6E6EE"
RECORD = "#FF5A5F"

QSS = f"""
* {{ font-family: 'Segoe UI Variable Text', 'Segoe UI'; font-size: 10pt; color: {INK}; }}
QMainWindow, #content {{ background: {BG}; }}
#sidebar {{ background: {INK}; }}
#sidebar QPushButton {{
    color: #B9B9C8; background: transparent; border: none; text-align: left;
    padding: 10px 16px; border-radius: 10px; font-size: 10.5pt; }}
#sidebar QPushButton:hover {{ background: #24243000; color: white; background: #23232E; }}
#sidebar QPushButton:checked {{ background: #2D2A4A; color: white; font-weight: 600; }}
#brand {{ color: white; font-size: 16pt; font-weight: 700; }}
#brandSub {{ color: #8C8CA0; font-size: 8.5pt; }}
#sideStatus {{ color: #8C8CA0; font-size: 8.5pt; }}
QLabel#h1 {{ font-size: 20pt; font-weight: 700; }}
QLabel#h2 {{ font-size: 12pt; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#statValue {{ font-size: 20pt; font-weight: 700; }}
QLabel#statLabel {{ color: {MUTED}; font-size: 9pt; }}
QFrame#card {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; }}
QFrame#heroCard {{ border-radius: 16px; background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 {ACCENT}, stop:1 #8B5CF6); }}
QFrame#heroCard QLabel {{ color: white; }}
QLabel#kbd {{ background: rgba(255,255,255,0.18); color: white; border-radius: 6px; padding: 3px 8px;
    font-weight: 600; }}
QLabel#kbdDark {{ background: #EEEDFE; color: {ACCENT}; border-radius: 6px; padding: 3px 8px; font-weight: 600; }}
QPushButton {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 9px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton#primary {{ background: {ACCENT}; color: white; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: #5B4CE0; }}
QPushButton#danger {{ color: #C9302C; }}
QPushButton#seg {{ border-radius: 8px; padding: 6px 12px; }}
QPushButton#seg:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{
    background: {CARD}; border: 1px solid {LINE}; border-radius: 9px; padding: 7px 10px;
    selection-background-color: {ACCENT}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid {LINE}; selection-background-color: #EEEDFE;
    selection-color: {INK}; }}
QListWidget {{ background: transparent; border: none; }}
QListWidget::item {{ border: none; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: #D0D0DC; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 36px; height: 20px; border-radius: 10px; background: #D5D5E0; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; }}
QToolTip {{ background: {INK}; color: white; border: none; padding: 6px; }}
"""


def app_icon(size=256) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(ACCENT))
    g.setColorAt(1, QColor("#8B5CF6"))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)
    pen = QPen(QColor("white"), size * 0.075, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    heights = [0.22, 0.42, 0.6, 0.42, 0.22]
    for i, h in enumerate(heights):
        x = size * (0.26 + i * 0.12)
        p.drawLine(QPointF(x, size * (0.5 - h / 2)), QPointF(x, size * (0.5 + h / 2)))
    p.end()
    return QIcon(pm)
