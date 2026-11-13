"""The dictation pipeline, wired to Qt signals so the UI can follow along."""
import logging
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal

from . import audio, system
from .llm import LLM, protect_snippets, restore_snippets
from .store import Store

log = logging.getLogger("dizflow")


class Engine(QObject):
    state = Signal(str)            # idle | recording | command | processing | error
    status = Signal(str)           # model / readiness text for the UI
    finished = Signal()            # a dictation was saved to history
    notice = Signal(str)           # short message for the user (warnings, errors)
    _hotkey = Signal(str, str)

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self.store = Store()
        self.llm = LLM(settings)
        self.recorder = audio.Recorder()
        self.status_text = "Starting…"
        self.transcriber = audio.Transcriber(settings, on_status=self._set_status)
        self.kind = None
        self.busy = False
        self.target = "unknown"
        self._hotkey.connect(self._on_hotkey)
        self.hotkeys = system.HotkeyListener(settings, lambda k, a: self._hotkey.emit(k, a))
        # Hold mode safety net: stop as soon as the hotkey isn't physically held any more,
        # even if Windows never told us it was released.
        self._released_ticks = 0
        self._watchdog = QTimer(self, interval=50, timeout=self._check_still_held)

    def _check_still_held(self):
        if not self.kind or self.s["mode"] != "hold":
            self._watchdog.stop()
            return
        if self.hotkeys.combo_held(self.kind):
            self._released_ticks = 0
            return
        self._released_ticks += 1
        if self._released_ticks >= 2:  # ~100 ms, ignores a single glitchy reading
            self._finish_recording()

    def _set_status(self, text):
        self.status_text = text
        self.status.emit(text)

    @property
    def level(self):
        return self.recorder.level

    def _sound(self, name):
        if self.s["sounds"]:
            try:
                audio.play(name)
            except Exception:
                pass

    # ------------------------------------------------------------ hotkeys (main thread)
    def _on_hotkey(self, kind, action):
        if action == "start" and self.kind is None and not self.busy:
            self.target = system.foreground_app()
            try:
                self.recorder.start(self.s["microphone"])
            except Exception as e:
                self.notice.emit(f"Microphone error: {e}")
                self.state.emit("error")
                return
            self.kind = kind
            self.hotkeys.set_active(kind)
            self.started = time.time()
            self._released_ticks = 0
            self._watchdog.start()
            self._sound("start")
            self.state.emit("recording" if kind == "dictate" else "command")
        elif action == "switch" and self.kind:
            self.kind = kind
            self.hotkeys.set_active(kind)
            self.state.emit("command" if kind == "command" else "recording")
        elif action == "stop" and self.kind:
            self._finish_recording()
        elif action == "cancel" and self.kind:
            self._watchdog.stop()
            self.recorder.stop()
            self.kind = None
            self.hotkeys.set_active(None)
            self.state.emit("idle")

    def _finish_recording(self):
        self._watchdog.stop()
        if not self.kind:
            return
        kind, self.kind = self.kind, None
        self.hotkeys.set_active(None)
        clip = self.recorder.stop()
        self._sound("stop")
        if len(clip) < audio.RATE * 0.3:
            self.state.emit("idle")
            return
        self.busy = True
        self.state.emit("processing")
        threading.Thread(target=self._process, args=(kind, clip, self.target), daemon=True).start()

    # ------------------------------------------------------------ pipeline (worker thread)
    def _process(self, kind, clip, target):
        seconds = len(clip) / audio.RATE
        terms = self.store.terms()
        ok = True
        try:
            t0 = time.time()
            raw = self.transcriber.transcribe(clip, terms)
            t1 = time.time()
            if not raw:
                self.notice.emit("Didn't catch that - nothing was typed")
                ok = False
                return
            if kind == "command":
                text = self._run_command(raw, terms)
            else:
                text = self._run_dictation(raw, target, terms)
            if not text:
                ok = False
                return
            system.wait_modifiers_released(self.hotkeys)
            if self.s["add_trailing_space"] and kind == "dictate" and not text.endswith(("\n", " ")):
                text += " "
            system.paste_text(text, self.s["restore_clipboard"])
            log.info("%s %.1fs -> %s | whisper %.2fs | total %.2fs", kind, seconds, target, t1 - t0, time.time() - t0)
            self.store.add_history(kind, target, raw, text.rstrip(" "), seconds)
            self.finished.emit()
        except Exception as e:
            log.exception("processing failed")
            self.notice.emit(f"Something went wrong: {e}")
            ok = False
        finally:
            self.busy = False
            if not ok:
                self._sound("error")
            self.state.emit("idle" if ok else "error")

    def _run_dictation(self, raw, target, terms):
        protected, mapping = protect_snippets(raw, self.store.snippets())
        text = protected
        if self.llm.enabled:
            try:
                text = self.llm.cleanup(protected, target, terms)
                # The model must keep every placeholder; if it lost one, fall back to the raw text.
                if any(tok not in text for tok in mapping):
                    text = protected
            except Exception as e:
                log.warning("cleanup failed: %s", e)
                self.notice.emit("AI cleanup unavailable - typed the raw transcript")
        return restore_snippets(text, mapping)

    def _run_command(self, instruction, terms):
        if not self.llm.enabled:
            self.notice.emit("Command mode needs an AI provider - add a key in Settings")
            return ""
        system.wait_modifiers_released(self.hotkeys)
        selected = system.copy_selection()
        try:
            return self.llm.command(instruction, selected, terms)
        except Exception as e:
            self.notice.emit(f"Command failed: {e}")
            return ""

    # ------------------------------------------------------------ settings hooks
    def reload_hotkeys(self):
        self.hotkeys.reload()

    def reload_model(self):
        self.transcriber.load()
