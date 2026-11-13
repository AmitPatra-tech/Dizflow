"""SQLite storage for history, personal dictionary and voice snippets."""
import sqlite3
import threading
from datetime import datetime, timedelta

from .paths import DB_PATH

TYPING_WPM = 40  # average typing speed used for "time saved"


class Store:
    def __init__(self, path=DB_PATH):
        self._lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, app TEXT,
                raw TEXT, text TEXT, seconds REAL, words INTEGER);
            CREATE TABLE IF NOT EXISTS dictionary (term TEXT PRIMARY KEY COLLATE NOCASE);
            CREATE TABLE IF NOT EXISTS snippets (
                trigger TEXT PRIMARY KEY COLLATE NOCASE, expansion TEXT);
        """)
        self.db.commit()

    def _q(self, sql, args=()):
        with self._lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.fetchall()

    # history
    def add_history(self, kind, app, raw, text, seconds):
        self._q("INSERT INTO history (ts, kind, app, raw, text, seconds, words) VALUES (?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), kind, app, raw, text, seconds, len(text.split())))

    def history(self, search="", limit=500):
        if search:
            return self._q("SELECT * FROM history WHERE text LIKE ? OR app LIKE ? ORDER BY id DESC LIMIT ?",
                           (f"%{search}%", f"%{search}%", limit))
        return self._q("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,))

    def delete_history(self, hid):
        self._q("DELETE FROM history WHERE id=?", (hid,))

    def clear_history(self):
        self._q("DELETE FROM history")

    def stats(self):
        row = self._q("SELECT COUNT(*) n, COALESCE(SUM(words),0) w, COALESCE(SUM(seconds),0) s FROM history")[0]
        words, secs = row["w"], row["s"]
        wpm = round(words / (secs / 60)) if secs > 5 else 0
        saved_min = max(0.0, words / TYPING_WPM - secs / 60)
        days = {r["d"] for r in self._q("SELECT DISTINCT substr(ts,1,10) d FROM history")}
        streak, day = 0, datetime.now().date()
        while day.isoformat() in days:
            streak += 1
            day -= timedelta(days=1)
        week = []
        for i in range(6, -1, -1):
            d = (datetime.now().date() - timedelta(days=i)).isoformat()
            w = self._q("SELECT COALESCE(SUM(words),0) w FROM history WHERE substr(ts,1,10)=?", (d,))[0]["w"]
            week.append((d, w))
        return {"sessions": row["n"], "words": words, "wpm": wpm, "saved_min": saved_min,
                "streak": streak, "week": week}

    # dictionary
    def terms(self):
        return [r["term"] for r in self._q("SELECT term FROM dictionary ORDER BY term")]

    def add_term(self, term):
        self._q("INSERT OR IGNORE INTO dictionary VALUES (?)", (term.strip(),))

    def delete_term(self, term):
        self._q("DELETE FROM dictionary WHERE term=?", (term,))

    # snippets
    def snippets(self):
        return [(r["trigger"], r["expansion"]) for r in self._q("SELECT * FROM snippets ORDER BY trigger")]

    def set_snippet(self, trigger, expansion):
        self._q("INSERT OR REPLACE INTO snippets VALUES (?,?)", (trigger.strip(), expansion))

    def delete_snippet(self, trigger):
        self._q("DELETE FROM snippets WHERE trigger=?", (trigger,))
