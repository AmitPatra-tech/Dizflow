import json
import threading

from .paths import SETTINGS_PATH, BUNDLE_DIR

DEFAULTS = {
    "onboarded": False,
    # hotkeys
    "dictate_hotkey": "ctrl+windows",
    "command_hotkey": "alt+windows",
    "mode": "hold",                      # hold | toggle
    # audio + speech
    "microphone": "",                    # "" = system default, else device name
    "language": "en",                    # "" = auto-detect
    "whisper_model": "large-v3-turbo",
    "device": "auto",                    # auto | cuda | cpu
    # AI
    "ai_provider": "gemini",             # gemini | claude | off
    "gemini_api_key": "",
    "gemini_models": ["gemini-3.5-flash", "gemini-3.5-flash-lite"],
    "anthropic_api_key": "",
    "claude_model": "claude-opus-5-5",
    "styles": {"chat": "casual", "email": "formal", "code": "neutral", "docs": "formal", "other": "neutral"},
    # behaviour
    "sounds": True,
    "restore_clipboard": True,
    "add_trailing_space": True,
    "start_with_windows": True,
    "start_minimized": False,
    "auto_update": True,
    "skipped_version": "",
}


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self.data = json.loads(json.dumps(DEFAULTS))
        if SETTINGS_PATH.exists():
            try:
                stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                self.data.update(stored)
                self.data["styles"] = {**DEFAULTS["styles"], **stored.get("styles", {})}
            except json.JSONDecodeError:
                pass
        else:
            self._migrate_legacy()
        self.save()

    def _migrate_legacy(self):
        """Carry the API key over from the first prototype's config.json."""
        legacy = BUNDLE_DIR / "config.json"
        if legacy.exists():
            try:
                old = json.loads(legacy.read_text(encoding="utf-8"))
                for k in ("gemini_api_key", "anthropic_api_key", "gemini_models", "whisper_model", "language"):
                    if old.get(k):
                        self.data[k] = old[k]
                if old.get("hotkey"):
                    self.data["dictate_hotkey"] = old["hotkey"]
            except json.JSONDecodeError:
                pass

    def __getitem__(self, k):
        return self.data[k]

    def get(self, k, default=None):
        return self.data.get(k, default)

    def set(self, k, v):
        with self._lock:
            self.data[k] = v
        self.save()

    def save(self):
        with self._lock:
            SETTINGS_PATH.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
