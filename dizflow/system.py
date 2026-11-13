"""Windows integration: global hotkeys, the focused app, clipboard paste, start-with-Windows."""
import ctypes
import sys
import threading
import time
import winreg
from pathlib import Path

import keyboard
import pyperclip

from .paths import BUNDLE_DIR, FROZEN

MODIFIERS = {"ctrl", "alt", "shift", "windows"}

# Left/right virtual-key codes for each modifier.
_MOD_VKS = {"ctrl": (0xA2, 0xA3), "alt": (0xA4, 0xA5), "shift": (0xA0, 0xA1), "windows": (0x5B, 0x5C)}


def _physically_down(name: str):
    """Ask Windows whether a key is really held right now. None = can't tell (non-modifier key).

    The listener's own record of pressed keys can go stale: Windows doesn't always deliver a key-up
    (Win+L, an elevated window in focus, the Start menu swallowing it), which used to leave Win "stuck"
    so that Ctrl alone looked like Ctrl+Win.
    """
    vks = _MOD_VKS.get(name)
    if vks is None:
        return None
    return any(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000 for vk in vks)


def norm_key(name: str) -> str:
    name = (name or "").lower().replace("left ", "").replace("right ", "")
    return {"control": "ctrl", "win": "windows", "cmd": "windows", "option": "alt", "escape": "esc",
            "alt gr": "alt"}.get(name, name)


def parse_combo(s: str) -> frozenset:
    return frozenset(norm_key(k.strip()) for k in s.split("+") if k.strip())


def format_combo(keys) -> str:
    order = ["ctrl", "alt", "shift", "windows"]
    ks = sorted(keys, key=lambda k: (order.index(k) if k in order else 9, k))
    return "+".join(ks)


def pretty_combo(s: str) -> str:
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "windows": "Win", "space": "Space"}
    return " + ".join(names.get(k, k.title()) for k in s.split("+"))


class HotkeyListener:
    """Watches the keyboard and turns hotkey presses into start/stop/cancel callbacks.

    on_event(kind, action): kind is "dictate" or "command"; action is "start", "stop", "cancel" or "switch".
    """

    def __init__(self, settings, on_event):
        self.s = settings
        self.on_event = on_event
        self.pressed: set[str] = set()
        self.active = None          # kind currently recording
        self.latched = False        # toggle mode: combo is held down right now
        self.paused = False
        self._capture = None
        self.reload()
        keyboard.hook(self._hook)

    def reload(self):
        self.combos = {"dictate": parse_combo(self.s["dictate_hotkey"]),
                       "command": parse_combo(self.s["command_hotkey"])}

    def set_active(self, kind):
        self.active = kind

    def capture(self, callback):
        """Record the next key combination the user presses (for the hotkey picker)."""
        self._capture = {"max": set(), "cb": callback}

    def modifiers_down(self) -> bool:
        self._prune()
        return bool(self.pressed & MODIFIERS)

    def _prune(self, current: str = ""):
        """Drop modifiers Windows says are no longer held (lost key-up events)."""
        for k in list(self.pressed):
            if k != current and _physically_down(k) is False:
                self.pressed.discard(k)

    def combo_held(self, kind) -> bool:
        """True while every modifier of the hotkey is physically down."""
        combo = self.combos.get(kind, frozenset())
        return all(_physically_down(k) is not False for k in combo)

    def _hook(self, e):
        name = norm_key(e.name)
        down = e.event_type == "down"
        if down:
            self.pressed.add(name)
        else:
            self.pressed.discard(name)
        # The key in this event is trusted as reported; every other key is checked against Windows.
        self._prune(current=name)

        if self._capture is not None:
            cap = self._capture
            if down:
                cap["max"] = cap["max"] | self.pressed
            elif not self.pressed:
                self._capture = None
                if cap["max"] and cap["max"] != {"esc"}:
                    cap["cb"](format_combo(cap["max"]))
            return
        if self.paused:
            return

        if down:
            if name == "esc" and self.active:
                self.on_event(self.active, "cancel")
                return
            satisfied = [k for k, c in self.combos.items() if c and c <= self.pressed]
            if not satisfied:
                return
            kind = max(satisfied, key=lambda k: len(self.combos[k]))  # most specific combo wins
            if self.s["mode"] == "toggle":
                if not self.latched:
                    self.latched = True
                    self.on_event(self.active or kind, "stop" if self.active else "start")
            elif self.active is None:
                self.on_event(kind, "start")
            elif self.active != kind and self.combos[kind] > self.combos[self.active]:
                self.on_event(kind, "switch")
        else:
            if self.active and name in self.combos[self.active]:
                if self.s["mode"] == "hold":
                    self.on_event(self.active, "stop")
            if not any(c <= self.pressed for c in self.combos.values()):
                self.latched = False


# ---------------------------------------------------------------- focused app
def foreground_app() -> str:
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    title = buf.value
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if h:
        size = ctypes.c_ulong(512)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            exe = Path(buf.value).name
        kernel32.CloseHandle(h)
    return f"{exe} - {title[:120]}" if (exe or title) else "unknown"


# ---------------------------------------------------------------- clipboard
def wait_modifiers_released(listener: HotkeyListener, timeout=2.0):
    end = time.time() + timeout
    while listener.modifiers_down() and time.time() < end:
        time.sleep(0.02)


def _safe_paste():
    try:
        return pyperclip.paste()
    except Exception:
        return None


def paste_text(text: str, restore: bool):
    old = _safe_paste() if restore else None
    pyperclip.copy(text)
    time.sleep(0.05)
    keyboard.send("ctrl+v")
    if old is not None:
        time.sleep(0.4)
        pyperclip.copy(old)


def copy_selection() -> str:
    """Return the text currently selected in the focused app ('' if none). Leaves the clipboard as it was."""
    old = _safe_paste()
    sentinel = f"__dizflow_{time.time()}__"
    pyperclip.copy(sentinel)
    keyboard.send("ctrl+c")
    selected = ""
    for _ in range(15):
        time.sleep(0.03)
        now = _safe_paste()
        if now and now != sentinel:
            selected = now
            break
    pyperclip.copy(old if old is not None else "")
    return selected


# ---------------------------------------------------------------- autostart
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    if FROZEN:
        return f'"{sys.executable}" --minimized'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else sys.executable}" "{BUNDLE_DIR / "main.py"}" --minimized'


def set_autostart(enabled: bool):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, "Dizflow", 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(k, "Dizflow")
            except FileNotFoundError:
                pass
