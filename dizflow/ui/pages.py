"""The pages shown in the main window."""
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget, QCheckBox, QInputDialog)

from .. import audio, system
from .widgets import StatCard, WeekChart, Segmented, LevelMeter, card, label, kbd_row


def scroll_page(title, subtitle=""):
    """A scrollable page with a header; returns (outer widget, content layout)."""
    outer = QScrollArea()
    outer.setWidgetResizable(True)
    inner = QWidget()
    inner.setObjectName("content")
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(36, 30, 36, 30)
    lay.setSpacing(16)
    lay.addWidget(label(title, "h1"))
    if subtitle:
        lay.addWidget(label(subtitle, "muted", wrap=True))
    outer.setWidget(inner)
    return outer, lay


def _ago(ts: str) -> str:
    d = datetime.now() - datetime.fromisoformat(ts)
    s = int(d.total_seconds())
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return datetime.fromisoformat(ts).strftime("%d %b, %H:%M")


def _app_name(target: str) -> str:
    exe = (target or "").split(" - ")[0]
    return exe.replace(".exe", "").replace(".EXE", "") or "Unknown app"


class HistoryRow(QFrame):
    def __init__(self, row, on_delete=None):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)
        head = QHBoxLayout()
        tag = "⌘ Command" if row["kind"] == "command" else "🎙 Dictation"
        head.addWidget(label(f"{tag}  ·  {_app_name(row['app'])}  ·  {_ago(row['ts'])}  ·  {row['words']} words", "muted"))
        head.addStretch()
        copy = QPushButton("Copy")
        copy.setCursor(Qt.PointingHandCursor)
        copy.clicked.connect(lambda: (QGuiApplication.clipboard().setText(row["text"]), copy.setText("Copied")))
        head.addWidget(copy)
        if on_delete:
            rm = QPushButton("Delete")
            rm.setObjectName("danger")
            rm.clicked.connect(lambda: on_delete(row["id"]))
            head.addWidget(rm)
        lay.addLayout(head)
        body = label(row["text"], wrap=True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(body)
        if row["raw"] and row["raw"] != row["text"]:
            raw = label(f"Heard: “{row['raw']}”", "muted", wrap=True)
            raw.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(raw)


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


# ============================================================ Home
class HomePage(QScrollArea):
    def __init__(self, engine, settings):
        super().__init__()
        self.e, self.s = engine, settings
        self.setWidgetResizable(True)
        inner = QWidget()
        inner.setObjectName("content")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(36, 30, 36, 30)
        self.lay.setSpacing(18)
        self.setWidget(inner)

        self.greet = label("", "h1")
        self.lay.addWidget(self.greet)

        hero, hl = card("heroCard")
        hl.setContentsMargins(24, 22, 24, 22)
        hl.addWidget(label("Talk instead of type, in any app.", "h2"))
        self.hero_rows = QVBoxLayout()
        hl.addLayout(self.hero_rows)
        self.lay.addWidget(hero)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.c_words = StatCard("Words dictated", "✍")
        self.c_wpm = StatCard("Speaking speed (WPM)", "⚡")
        self.c_saved = StatCard("Time saved", "⏱")
        self.c_streak = StatCard("Day streak", "🔥")
        for i, c in enumerate((self.c_words, self.c_wpm, self.c_saved, self.c_streak)):
            grid.addWidget(c, 0, i)
        self.lay.addLayout(grid)

        chart_card, cl = card()
        cl.addWidget(label("Words this week", "h2"))
        self.chart = WeekChart()
        cl.addWidget(self.chart)
        self.lay.addWidget(chart_card)

        try_card, tl = card()
        tl.addWidget(label("Try it here", "h2"))
        self.try_hint = label("", "muted", wrap=True)
        tl.addWidget(self.try_hint)
        box = QPlainTextEdit()
        box.setPlaceholderText("Click here, then hold the hotkey and speak…")
        box.setFixedHeight(90)
        tl.addWidget(box)
        self.lay.addWidget(try_card)

        self.lay.addWidget(label("Recent", "h2"))
        self.recent = QVBoxLayout()
        self.recent.setSpacing(10)
        self.lay.addLayout(self.recent)
        self.lay.addStretch()

    def refresh(self):
        h = datetime.now().hour
        part = "morning" if h < 12 else "afternoon" if h < 18 else "evening"
        self.greet.setText(f"Good {part} 👋")
        _clear(self.hero_rows)
        for combo, text in ((self.s["dictate_hotkey"], "to dictate"),
                            (self.s["command_hotkey"], "on selected text to rewrite it by voice (Command mode)")):
            row = QHBoxLayout()
            verb = "Hold" if self.s["mode"] == "hold" else "Press"
            row.addWidget(label(verb))
            row.addWidget(kbd_row(combo))
            row.addWidget(label(text))
            row.addStretch()
            w = QWidget()
            w.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            self.hero_rows.addWidget(w)
        st = self.e.store.stats()
        self.c_words.set(f"{st['words']:,}")
        self.c_wpm.set(st["wpm"] or "–")
        m = st["saved_min"]
        self.c_saved.set(f"{m / 60:.1f} h" if m >= 60 else f"{m:.0f} min")
        self.c_streak.set(st["streak"])
        self.chart.set_data(st["week"])
        self.try_hint.setText(f"{'Hold' if self.s['mode'] == 'hold' else 'Press'} "
                              f"{system.pretty_combo(self.s['dictate_hotkey'])}, speak, then let go. "
                              "Try: “um, send it at three, no wait, at four, new line, thanks”.")
        _clear(self.recent)
        rows = self.e.store.history(limit=4)
        if not rows:
            self.recent.addWidget(label("Nothing yet - your dictations will show up here.", "muted"))
        for r in rows:
            self.recent.addWidget(HistoryRow(r))


# ============================================================ History
class HistoryPage(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.e = engine
        self.setObjectName("content")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 30, 36, 20)
        lay.setSpacing(14)
        top = QHBoxLayout()
        top.addWidget(label("History", "h1"))
        top.addStretch()
        clear = QPushButton("Clear all")
        clear.setObjectName("danger")
        clear.clicked.connect(self._clear_all)
        top.addWidget(clear)
        lay.addLayout(top)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search what you've said…")
        self.search.textChanged.connect(lambda: self.refresh())
        lay.addWidget(self.search)
        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        inner.setObjectName("content")
        self.list = QVBoxLayout(inner)
        self.list.setSpacing(10)
        area.setWidget(inner)
        lay.addWidget(area)

    def refresh(self):
        _clear(self.list)
        rows = self.e.store.history(self.search.text().strip(), limit=300)
        if not rows:
            self.list.addWidget(label("No dictations found.", "muted"))
        for r in rows:
            self.list.addWidget(HistoryRow(r, on_delete=self._delete))
        self.list.addStretch()

    def _delete(self, hid):
        self.e.store.delete_history(hid)
        self.refresh()

    def _clear_all(self):
        if QMessageBox.question(self, "Clear history", "Delete all saved dictations? This can't be undone.") \
                == QMessageBox.Yes:
            self.e.store.clear_history()
            self.refresh()


# ============================================================ Dictionary
class DictionaryPage(QScrollArea):
    def __init__(self, engine):
        super().__init__()
        self.e = engine
        page, lay = scroll_page("Dictionary", "Names, brands and jargon Dizflow should always spell your way. "
                                "They also help the speech model recognise them.")
        self.setWidgetResizable(True)
        self.setWidget(page.takeWidget())
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Add a word, e.g. Kubernetes, Priyanka, Dizflow")
        self.input.returnPressed.connect(self._add)
        add = QPushButton("Add")
        add.setObjectName("primary")
        add.clicked.connect(self._add)
        row.addWidget(self.input)
        row.addWidget(add)
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.setMinimumHeight(360)
        self.list.setSpacing(3)
        lay.addWidget(self.list)
        lay.addStretch()

    def _add(self):
        for t in self.input.text().split(","):
            if t.strip():
                self.e.store.add_term(t)
        self.input.clear()
        self.refresh()

    def refresh(self):
        self.list.clear()
        for term in self.e.store.terms():
            item = QListWidgetItem()
            w = QFrame()
            w.setObjectName("card")
            h = QHBoxLayout(w)
            h.setContentsMargins(14, 6, 8, 6)
            h.addWidget(label(term))
            h.addStretch()
            rm = QPushButton("Remove")
            rm.setObjectName("danger")
            rm.clicked.connect(lambda _=False, t=term: (self.e.store.delete_term(t), self.refresh()))
            h.addWidget(rm)
            item.setSizeHint(w.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, w)


# ============================================================ Snippets
class SnippetsPage(QScrollArea):
    def __init__(self, engine):
        super().__init__()
        self.e = engine
        page, lay = scroll_page("Snippets", "Say a short phrase, get a longer text. For example say “my calendar link” "
                                "and Dizflow types the full URL.")
        self.setWidgetResizable(True)
        self.setWidget(page.takeWidget())
        form, fl = card()
        self.trigger = QLineEdit()
        self.trigger.setPlaceholderText("When I say…   e.g. my email")
        self.expansion = QPlainTextEdit()
        self.expansion.setPlaceholderText("Type this instead…")
        self.expansion.setFixedHeight(80)
        save = QPushButton("Save snippet")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        fl.addWidget(self.trigger)
        fl.addWidget(self.expansion)
        fl.addWidget(save, alignment=Qt.AlignRight)
        lay.addWidget(form)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(10)
        lay.addLayout(self.rows)
        lay.addStretch()

    def _save(self):
        t, x = self.trigger.text().strip(), self.expansion.toPlainText()
        if t and x:
            self.e.store.set_snippet(t, x)
            self.trigger.clear()
            self.expansion.clear()
            self.refresh()

    def refresh(self):
        _clear(self.rows)
        snippets = self.e.store.snippets()
        if not snippets:
            self.rows.addWidget(label("No snippets yet.", "muted"))
        for trig, exp in snippets:
            c, cl = card()
            top = QHBoxLayout()
            top.addWidget(label(f"“{trig}”", "h2"))
            top.addStretch()
            edit = QPushButton("Edit")
            edit.clicked.connect(lambda _=False, t=trig, x=exp: (self.trigger.setText(t), self.expansion.setPlainText(x)))
            rm = QPushButton("Delete")
            rm.setObjectName("danger")
            rm.clicked.connect(lambda _=False, t=trig: (self.e.store.delete_snippet(t), self.refresh()))
            top.addWidget(edit)
            top.addWidget(rm)
            cl.addLayout(top)
            body = label(exp, "muted", wrap=True)
            cl.addWidget(body)
            self.rows.addWidget(c)


# ============================================================ Style
STYLE_CATEGORIES = [
    ("chat", "💬 Messaging", "Slack, Discord, WhatsApp, Teams, Telegram"),
    ("email", "✉ Email", "Outlook, Gmail, Thunderbird"),
    ("docs", "📄 Documents", "Word, Google Docs, Notion, Obsidian"),
    ("code", "⌨ Code & terminal", "VS Code, Cursor, JetBrains, Terminal"),
    ("other", "✦ Everything else", "Any other app"),
]
STYLE_OPTIONS = [("casual", "Casual"), ("neutral", "Neutral"), ("formal", "Formal")]
STYLE_EXAMPLES = {
    "casual": "hey, running 5 min late, start without me",
    "neutral": "Hey, I'm running five minutes late. Start without me.",
    "formal": "Hi all, I'm running about five minutes late. Please go ahead and start without me.",
}


class StylePage(QScrollArea):
    def __init__(self, settings):
        super().__init__()
        self.s = settings
        page, lay = scroll_page("Style", "Dizflow sees which app you're dictating into and writes in the tone you pick "
                                "for it.")
        self.setWidgetResizable(True)
        self.setWidget(page.takeWidget())
        for key, title, apps in STYLE_CATEGORIES:
            c, cl = card()
            top = QHBoxLayout()
            col = QVBoxLayout()
            col.addWidget(label(title, "h2"))
            col.addWidget(label(apps, "muted"))
            top.addLayout(col)
            top.addStretch()
            seg = Segmented(STYLE_OPTIONS, self.s["styles"].get(key, "neutral"))
            example = label("", "muted", wrap=True)
            example.setText(f"Example: {STYLE_EXAMPLES[self.s['styles'].get(key, 'neutral')]}")
            seg.changed.connect(lambda v, k=key, ex=example: self._set(k, v, ex))
            top.addWidget(seg)
            cl.addLayout(top)
            cl.addWidget(example)
            lay.addWidget(c)
        lay.addStretch()

    def _set(self, key, value, example):
        styles = dict(self.s["styles"])
        styles[key] = value
        self.s.set("styles", styles)
        example.setText(f"Example: {STYLE_EXAMPLES[value]}")

    def refresh(self):
        pass


# ============================================================ Settings
class _Bridge(QObject):
    captured = Signal(str)


class HotkeyButton(QPushButton):
    """Click, then press a key combination."""
    changed = Signal(str)

    def __init__(self, engine, value):
        super().__init__()
        self.e = engine
        self.value = value
        self.bridge = _Bridge()
        self.bridge.captured.connect(self._done)
        self.setMinimumWidth(200)
        self.setText(system.pretty_combo(value))
        self.clicked.connect(self._start)

    def _start(self):
        self.setText("Press keys… (Esc to cancel)")
        self.e.hotkeys.capture(self.bridge.captured.emit)

    def _done(self, combo):
        self.value = combo
        self.setText(system.pretty_combo(combo))
        self.changed.emit(combo)


WHISPER_MODELS = [("large-v3-turbo", "Turbo - best accuracy, fast on GPU (recommended)"),
                  ("large-v3", "Large v3 - most accurate, slower"),
                  ("medium", "Medium - balanced"),
                  ("small", "Small - lightweight, for CPU"),
                  ("base", "Base - fastest, least accurate")]
LANGUAGES = [("en", "English"), ("", "Auto-detect (any language)"), ("hi", "Hindi"), ("es", "Spanish"),
             ("fr", "French"), ("de", "German"), ("pt", "Portuguese"), ("it", "Italian"), ("ja", "Japanese"),
             ("zh", "Chinese"), ("ar", "Arabic"), ("ru", "Russian"), ("ko", "Korean")]


def _combo(options, current):
    cb = QComboBox()
    for value, text in options:
        cb.addItem(text, value)
    idx = max(0, cb.findData(current))
    cb.setCurrentIndex(idx)
    return cb


def _row(title, desc, widget):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 4, 0, 4)
    col = QVBoxLayout()
    col.setSpacing(1)
    col.addWidget(label(title))
    if desc:
        col.addWidget(label(desc, "muted", wrap=True))
    h.addLayout(col, 1)
    h.addWidget(widget)
    return w


class SettingsPage(QScrollArea):
    hotkeys_changed = Signal()

    def __init__(self, engine, settings, updater=None):
        super().__init__()
        self.e, self.s = engine, settings
        page, lay = scroll_page("Settings")
        self.setWidgetResizable(True)
        self.setWidget(page.takeWidget())

        # --- shortcuts
        c, cl = card()
        cl.addWidget(label("Shortcuts", "h2"))
        dk = HotkeyButton(engine, self.s["dictate_hotkey"])
        dk.changed.connect(lambda v: self._hotkey("dictate_hotkey", v))
        ck = HotkeyButton(engine, self.s["command_hotkey"])
        ck.changed.connect(lambda v: self._hotkey("command_hotkey", v))
        mode = Segmented([("hold", "Hold to talk"), ("toggle", "Press to start / stop")], self.s["mode"])
        mode.changed.connect(lambda v: (self.s.set("mode", v), self.hotkeys_changed.emit()))
        cl.addWidget(_row("Dictation", "Speak and Dizflow types it where your cursor is.", dk))
        cl.addWidget(_row("Command mode", "Select text, then say what to do: “make this friendlier”, "
                          "“translate to Spanish”. With nothing selected it writes from scratch.", ck))
        cl.addWidget(_row("Activation", "Esc always cancels a recording.", mode))
        lay.addWidget(c)

        # --- microphone & speech
        c, cl = card()
        cl.addWidget(label("Microphone & speech", "h2"))
        mics = [("", "System default")] + [(m, m) for m in audio.input_devices()]
        self.mic = _combo(mics, self.s["microphone"])
        self.mic.currentIndexChanged.connect(lambda: self.s.set("microphone", self.mic.currentData()))
        cl.addWidget(_row("Microphone", "", self.mic))
        test = QHBoxLayout()
        self.test_btn = QPushButton("Test microphone")
        self.test_btn.clicked.connect(self._toggle_test)
        self.tester = audio.Recorder()
        self.meter = LevelMeter(lambda: self.tester.level)
        test.addWidget(self.test_btn)
        test.addWidget(self.meter, 1)
        cl.addLayout(test)
        self.lang = _combo(LANGUAGES, self.s["language"])
        self.lang.currentIndexChanged.connect(lambda: self.s.set("language", self.lang.currentData()))
        cl.addWidget(_row("Language", "Pick yours for best accuracy.", self.lang))
        self.model = _combo(WHISPER_MODELS, self.s["whisper_model"])
        self.model.currentIndexChanged.connect(self._model_changed)
        cl.addWidget(_row("Speech model", "Runs privately on this PC. New models download once.", self.model))
        self.device = _combo([("auto", "Automatic"), ("cuda", "GPU (NVIDIA)"), ("cpu", "CPU")], self.s["device"])
        self.device.currentIndexChanged.connect(self._device_changed)
        cl.addWidget(_row("Run on", "", self.device))
        self.model_status = label(engine.status_text, "muted")
        engine.status.connect(self.model_status.setText)
        cl.addWidget(self.model_status)
        lay.addWidget(c)

        # --- AI
        c, cl = card()
        cl.addWidget(label("AI writing", "h2"))
        cl.addWidget(label("Removes filler words, applies your corrections, fixes punctuation and matches the "
                           "app's style. Only the transcript text is sent; your audio stays on this PC.",
                           "muted", wrap=True))
        self.provider = _combo([("gemini", "Google Gemini"), ("claude", "Anthropic Claude"),
                                ("off", "Off - type exactly what I say")], self.s["ai_provider"])
        self.provider.currentIndexChanged.connect(self._provider_changed)
        cl.addWidget(_row("Provider", "", self.provider))
        self.gem_key = QLineEdit(self.s["gemini_api_key"])
        self.gem_key.setEchoMode(QLineEdit.Password)
        self.gem_key.setPlaceholderText("Gemini API key")
        self.gem_key.editingFinished.connect(lambda: self.s.set("gemini_api_key", self.gem_key.text().strip()))
        self.gem_row = _row("Gemini API key", "From aistudio.google.com", self.gem_key)
        cl.addWidget(self.gem_row)
        self.cl_key = QLineEdit(self.s["anthropic_api_key"])
        self.cl_key.setEchoMode(QLineEdit.Password)
        self.cl_key.setPlaceholderText("Anthropic API key")
        self.cl_key.editingFinished.connect(lambda: self.s.set("anthropic_api_key", self.cl_key.text().strip()))
        self.cl_row = _row("Anthropic API key", "From console.anthropic.com", self.cl_key)
        cl.addWidget(self.cl_row)
        for w in (self.gem_key, self.cl_key):
            w.setMinimumWidth(280)
        self._provider_rows()
        lay.addWidget(c)

        # --- general
        c, cl = card()
        cl.addWidget(label("General", "h2"))
        for key, title, desc in [
            ("sounds", "Sound effects", "A soft chime when recording starts and stops."),
            ("restore_clipboard", "Keep my clipboard", "Put back what you had copied after Dizflow pastes."),
            ("add_trailing_space", "Add a space after dictation", "So the next sentence starts cleanly."),
            ("start_with_windows", "Start with Windows", "Dizflow waits in the tray, ready for your hotkey."),
            ("start_minimized", "Start minimized", "Open to the tray instead of this window."),
        ]:
            cb = QCheckBox()
            cb.setChecked(bool(self.s[key]))
            cb.toggled.connect(lambda v, k=key: self._toggle(k, v))
            cl.addWidget(_row(title, desc, cb))
        lay.addWidget(c)

        # --- updates
        if updater is not None:
            from .. import __version__
            c, cl = card()
            cl.addWidget(label("Updates", "h2"))
            auto = QCheckBox()
            auto.setChecked(bool(self.s.get("auto_update", True)))
            auto.toggled.connect(updater.set_auto)
            cl.addWidget(_row("Check for updates automatically", "Dizflow asks before installing anything.", auto))
            row = QHBoxLayout()
            self.update_status = label(f"Version {__version__}", "muted")
            updater.status.connect(self.update_status.setText)
            check = QPushButton("Check now")
            check.clicked.connect(lambda: updater.check(manual=True))
            row.addWidget(self.update_status, 1)
            row.addWidget(check)
            cl.addLayout(row)
            lay.addWidget(c)
        lay.addStretch()

    def _hotkey(self, key, value):
        other = "command_hotkey" if key == "dictate_hotkey" else "dictate_hotkey"
        if value == self.s[other]:
            QMessageBox.warning(self, "Shortcut in use", "That shortcut is already used. Pick a different one.")
            return
        self.s.set(key, value)
        self.e.reload_hotkeys()
        self.hotkeys_changed.emit()

    def _toggle(self, key, value):
        self.s.set(key, value)
        if key == "start_with_windows":
            try:
                system.set_autostart(value)
            except OSError as e:
                QMessageBox.warning(self, "Start with Windows", f"Couldn't change startup setting: {e}")

    def _toggle_test(self):
        if self.meter.t.isActive():
            self.tester.stop()
            self.meter.stop()
            self.test_btn.setText("Test microphone")
        else:
            try:
                self.tester.start(self.s["microphone"])
            except Exception as e:
                QMessageBox.warning(self, "Microphone", f"Couldn't open the microphone: {e}")
                return
            self.meter.start()
            self.test_btn.setText("Stop test")

    def _model_changed(self):
        self.s.set("whisper_model", self.model.currentData())
        self.e.reload_model()

    def _device_changed(self):
        self.s.set("device", self.device.currentData())
        self.e.reload_model()

    def _provider_changed(self):
        self.s.set("ai_provider", self.provider.currentData())
        self._provider_rows()

    def _provider_rows(self):
        p = self.s["ai_provider"]
        self.gem_row.setVisible(p == "gemini")
        self.cl_row.setVisible(p == "claude")

    def hideEvent(self, e):
        if self.meter.t.isActive():
            self._toggle_test()
        super().hideEvent(e)

    def refresh(self):
        pass
