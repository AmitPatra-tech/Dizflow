"""Automatic updates from GitHub Releases.

A release is a tag like v1.2.0 with the installer attached as Dizflow-Setup-1.2.0.exe.
Dizflow checks on startup and every few hours; when a newer version exists the user is offered
"Update now", which downloads the installer and runs it silently. The installer restarts Dizflow.
"""
import json
import logging
import os
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from . import __version__
from .paths import FROZEN

log = logging.getLogger("dizflow")

REPO = "AmitPatra-tech/Dizflow"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
CHECK_EVERY_MS = 6 * 60 * 60 * 1000
UA = {"User-Agent": f"Dizflow/{__version__}", "Accept": "application/vnd.github+json"}


def parse_version(v: str) -> tuple:
    parts = []
    for p in v.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts + [0] * (3 - len(parts)))


def fetch_latest() -> dict | None:
    """Latest release info, or None if there's no installer attached to it."""
    req = urllib.request.Request(API_LATEST, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    asset = next((a for a in data.get("assets", [])
                  if a["name"].lower().startswith("dizflow-setup") and a["name"].lower().endswith(".exe")), None)
    if not asset:
        return None
    return {"version": data["tag_name"].lstrip("vV"), "notes": data.get("body") or "",
            "url": asset["browser_download_url"], "size": asset["size"], "name": asset["name"],
            "page": data.get("html_url", RELEASES_PAGE)}


class Updater(QObject):
    status = Signal(str)          # text for the Settings page
    available = Signal(dict)      # a newer version exists
    progress = Signal(int)        # download percent
    failed = Signal(str)
    installing = Signal()         # installer started; the app is about to quit

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self.latest = None
        self._busy = False
        self.timer = QTimer(self, interval=CHECK_EVERY_MS, timeout=lambda: self.check(manual=False))
        if self.s.get("auto_update", True):
            QTimer.singleShot(15_000, lambda: self.check(manual=False))
            self.timer.start()

    def set_auto(self, on: bool):
        self.s.set("auto_update", on)
        self.timer.start() if on else self.timer.stop()

    # ---------------------------------------------------------------- check
    def check(self, manual=True):
        if self._busy:
            return
        self.status.emit("Checking for updates…")
        threading.Thread(target=self._check, args=(manual,), daemon=True).start()

    def _check(self, manual):
        try:
            latest = fetch_latest()
        except urllib.error.HTTPError as e:
            self.status.emit("No releases published yet" if e.code == 404 else f"Update check failed ({e.code})")
            return
        except Exception as e:
            log.info("update check failed: %s", e)
            self.status.emit("Couldn't reach GitHub to check for updates")
            return
        if latest and parse_version(latest["version"]) > parse_version(__version__):
            self.latest = latest
            self.status.emit(f"Version {latest['version']} is available")
            if manual or latest["version"] != self.s.get("skipped_version", ""):
                self.available.emit(latest)
        else:
            self.status.emit(f"You're up to date (version {__version__})")

    def skip(self):
        if self.latest:
            self.s.set("skipped_version", self.latest["version"])

    # ---------------------------------------------------------------- install
    def install(self):
        if not self.latest or self._busy:
            return
        if not FROZEN:  # running from source: there is no installed copy to replace
            webbrowser.open(self.latest["page"])
            return
        self._busy = True
        threading.Thread(target=self._download_and_run, daemon=True).start()

    def _download_and_run(self):
        info = self.latest
        dest = Path(tempfile.gettempdir()) / info["name"]
        part = dest.with_suffix(".part")
        try:
            if not (dest.exists() and dest.stat().st_size == info["size"]):
                req = urllib.request.Request(info["url"], headers={"User-Agent": UA["User-Agent"]})
                with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
                    done, last = 0, -1
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                        done += len(chunk)
                        pct = int(done * 100 / max(1, info["size"]))
                        if pct != last:
                            self.progress.emit(pct)
                            last = pct
                if part.stat().st_size != info["size"]:
                    raise IOError("download incomplete")
                os.replace(part, dest)
            self.status.emit("Installing update…")
            # The installer closes Dizflow, replaces the files and starts the new version.
            subprocess.Popen([str(dest), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/UPDATE=1"],
                             creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                             close_fds=True)
            self.installing.emit()
        except Exception as e:
            log.exception("update failed")
            part.unlink(missing_ok=True)
            self.failed.emit(f"Update failed: {e}")
            self.status.emit("Update failed - try again later")
        finally:
            self._busy = False
