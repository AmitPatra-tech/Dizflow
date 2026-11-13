from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMenu, QPlainTextEdit, QPushButton, QStackedWidget,
                               QSystemTrayIcon, QVBoxLayout, QWidget, QComboBox)

from .. import __version__, audio, system
from .overlay import Overlay
from .pages import (HomePage, HistoryPage, DictionaryPage, SnippetsPage, StylePage, SettingsPage, _combo)
from .theme import app_icon
from .widgets import LevelMeter, label, kbd_row

NAV = [("🏠", "Home"), ("🕘", "History"), ("📖", "Dictionary"), ("✂", "Snippets"), ("🎨", "Style"), ("⚙", "Settings")]


class UpdateBanner(QFrame):
    """Strip across the top of the window: 'Version X is available - Update now / Later'."""

    def __init__(self, updater):
        super().__init__()
        self.u = updater
        self.setObjectName("updateBanner")
        self.setStyleSheet("#updateBanner { background: #EEEDFE; border-bottom: 1px solid #DCD8FD; }"
                           "#updateBanner QLabel { color: #3B2FC9; }")
        h = QHBoxLayout(self)
        h.setContentsMargins(36, 10, 36, 10)
        self.text = label("")
        h.addWidget(self.text, 1)
        self.later = QPushButton("Later")
        self.later.clicked.connect(self._later)
        self.go = QPushButton("Update now")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self._go)
        h.addWidget(self.later)
        h.addWidget(self.go)
        self.hide()
        updater.available.connect(self.offer)
        updater.progress.connect(lambda p: self.text.setText(f"Downloading update… {p}%"))
        updater.failed.connect(self._failed)

    def offer(self, info):
        self.text.setText(f"✨  Dizflow {info['version']} is available. Your settings and history are kept.")
        self.go.setEnabled(True)
        self.later.show()
        self.show()

    def _go(self):
        self.go.setEnabled(False)
        self.later.hide()
        self.text.setText("Starting download…")
        self.u.install()

    def _later(self):
        self.u.skip()
        self.hide()

    def _failed(self, msg):
        self.text.setText(msg)
        self.go.setEnabled(True)
        self.go.setText("Try again")
        self.later.show()


class MainWindow(QMainWindow):
    def __init__(self, engine, settings, updater=None):
        super().__init__()
        self.e, self.s = engine, settings
        self.updater = updater
        self.setWindowTitle("Dizflow")
        self.setWindowIcon(app_icon())
        self.resize(1080, 740)
        self.setMinimumSize(880, 600)

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 22, 14, 18)
        sl.setSpacing(4)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(34, 34))
        brand.addWidget(logo)
        bcol = QVBoxLayout()
        bcol.setSpacing(0)
        bcol.addWidget(label("Dizflow", "brand"))
        bcol.addWidget(label("Voice to text, everywhere", "brandSub"))
        brand.addLayout(bcol)
        brand.addStretch()
        sl.addLayout(brand)
        sl.addSpacing(18)

        self.stack = QStackedWidget()
        self.pages = [HomePage(engine, settings), HistoryPage(engine), DictionaryPage(engine),
                      SnippetsPage(engine), StylePage(settings), SettingsPage(engine, settings, updater)]
        self.pages[5].hotkeys_changed.connect(lambda: self.pages[0].refresh())
        group = QButtonGroup(self)
        for i, ((icon, name), page) in enumerate(zip(NAV, self.pages)):
            b = QPushButton(f"{icon}   {name}")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self.go(i))
            group.addButton(b)
            sl.addWidget(b)
            self.stack.addWidget(page)
            if i == 0:
                b.setChecked(True)
        self.nav = group.buttons()
        sl.addStretch()
        self.side_status = label(engine.status_text, "sideStatus", wrap=True)
        engine.status.connect(self.side_status.setText)
        sl.addWidget(self.side_status)
        sl.addWidget(label(f"v{__version__}", "sideStatus"))

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        if updater is not None:
            self.banner = UpdateBanner(updater)
            rl.addWidget(self.banner)
        rl.addWidget(self.stack, 1)
        h.addWidget(side)
        h.addWidget(right, 1)
        self.setCentralWidget(root)

        engine.finished.connect(self._refresh_current)
        self.overlay = Overlay(engine)
        self._make_tray()
        if updater is not None:
            updater.available.connect(self._update_available)
            updater.installing.connect(self.quit)
        self.go(0)

    def _update_available(self, info):
        if not self.isVisible():
            self.tray.showMessage("Dizflow update available",
                                  f"Version {info['version']} is ready. Open Dizflow to install it.", app_icon(), 6000)

    def go(self, i):
        self.stack.setCurrentIndex(i)
        self.nav[i].setChecked(True)
        self.pages[i].refresh()

    def _refresh_current(self):
        self.pages[self.stack.currentIndex()].refresh()

    # ------------------------------------------------------------ tray
    def _make_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(f"Dizflow - hold {system.pretty_combo(self.s['dictate_hotkey'])} to dictate")
        menu = QMenu()
        menu.addAction("Open Dizflow", self.show_window)
        if self.updater is not None:
            menu.addAction("Check for updates", lambda: (self.show_window(), self.updater.check(manual=True)))
        self.pause_action = QAction("Pause shortcuts", menu, checkable=True)
        self.pause_action.toggled.connect(self._pause)
        menu.addAction(self.pause_action)
        menu.addSeparator()
        menu.addAction("Quit Dizflow", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show_window() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()
        self._tray_tip_shown = False

    def _pause(self, paused):
        self.e.hotkeys.paused = paused
        self.tray.setToolTip("Dizflow - paused" if paused else "Dizflow")

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._refresh_current()

    def closeEvent(self, ev):
        ev.ignore()
        self.hide()
        if not self._tray_tip_shown:
            self._tray_tip_shown = True
            self.tray.showMessage("Dizflow is still running",
                                  f"Hold {system.pretty_combo(self.s['dictate_hotkey'])} in any app to dictate. "
                                  "Right-click the tray icon to quit.", app_icon(), 4000)

    def quit(self):
        self.tray.hide()
        QApplication.quit()


# ================================================================ first-run setup
class Onboarding(QDialog):
    def __init__(self, engine, settings, parent=None):
        super().__init__(parent)
        self.e, self.s = engine, settings
        self.setWindowTitle("Welcome to Dizflow")
        self.setWindowIcon(app_icon())
        self.setFixedSize(620, 460)
        self.setObjectName("content")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 30, 36, 24)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        nav = QHBoxLayout()
        self.dots = label("", "muted")
        nav.addWidget(self.dots)
        nav.addStretch()
        self.back = QPushButton("Back")
        self.back.clicked.connect(lambda: self._step(-1))
        self.next = QPushButton("Next")
        self.next.setObjectName("primary")
        self.next.clicked.connect(lambda: self._step(1))
        nav.addWidget(self.back)
        nav.addWidget(self.next)
        lay.addLayout(nav)

        # 1 welcome
        p, pl = self._page()
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(72, 72))
        pl.addWidget(icon)
        pl.addWidget(label("Talk instead of type.", "h1"))
        pl.addWidget(label("Dizflow turns your voice into clean, ready-to-send text in any app: email, chat, "
                           "docs, your code editor. Speech is recognised privately on this PC.", "muted", wrap=True))
        pl.addStretch()

        # 2 microphone
        p, pl = self._page()
        pl.addWidget(label("Check your microphone", "h1"))
        pl.addWidget(label("Pick a microphone and say something. The bar should move.", "muted", wrap=True))
        mics = [("", "System default")] + [(m, m) for m in audio.input_devices()]
        self.mic = _combo(mics, self.s["microphone"])
        self.mic.currentIndexChanged.connect(self._mic_changed)
        pl.addWidget(self.mic)
        self.tester = audio.Recorder()
        self.meter = LevelMeter(lambda: self.tester.level)
        pl.addWidget(self.meter)
        pl.addStretch()

        # 3 AI
        p, pl = self._page()
        pl.addWidget(label("AI writing", "h1"))
        pl.addWidget(label("Dizflow can polish what you say: drop the “um”s, apply “no wait, I meant…”, add "
                           "punctuation and match the app's tone. Paste a Google Gemini API key (free at "
                           "aistudio.google.com), or skip to type exactly what you say.", "muted", wrap=True))
        self.key = QLineEdit(self.s["gemini_api_key"])
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("Gemini API key (optional)")
        pl.addWidget(self.key)
        pl.addStretch()

        # 4 try it
        p, pl = self._page()
        pl.addWidget(label("Try it", "h1"))
        row = QHBoxLayout()
        row.addWidget(label("Click the box, hold"))
        row.addWidget(kbd_row(self.s["dictate_hotkey"], dark=True))
        row.addWidget(label("and speak. Let go to finish."))
        row.addStretch()
        pl.addLayout(row)
        box = QPlainTextEdit()
        box.setPlaceholderText("Your words will appear here…")
        pl.addWidget(box)
        self.model_note = label(engine.status_text, "muted", wrap=True)
        engine.status.connect(self.model_note.setText)
        pl.addWidget(self.model_note)

        self.i = 0
        self._show()

    def _page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setSpacing(14)
        self.stack.addWidget(w)
        return w, l

    def _mic_changed(self):
        self.s.set("microphone", self.mic.currentData())
        self.tester.stop()
        self._start_meter()

    def _start_meter(self):
        try:
            self.tester.start(self.s["microphone"])
            self.meter.start()
        except Exception:
            pass

    def _show(self):
        self.stack.setCurrentIndex(self.i)
        n = self.stack.count()
        self.dots.setText("  ".join("●" if k == self.i else "○" for k in range(n)))
        self.back.setVisible(self.i > 0)
        self.next.setText("Start using Dizflow" if self.i == n - 1 else "Next")
        if self.i == 1:
            self._start_meter()
        else:
            self.tester.stop()
            self.meter.stop()

    def _step(self, d):
        if self.i == 2 and d > 0:
            key = self.key.text().strip()
            self.s.set("gemini_api_key", key)
            self.s.set("ai_provider", "gemini" if key else self.s["ai_provider"] if self.s["ai_provider"] == "claude" else "off")
        if self.i == self.stack.count() - 1 and d > 0:
            self.s.set("onboarded", True)
            self.accept()
            return
        self.i = max(0, self.i + d)
        self._show()

    def done(self, r):
        self.tester.stop()
        self.meter.stop()
        super().done(r)
