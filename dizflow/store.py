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
        self._migrate()
        self.db.commit()

    def _migrate(self):
        """1.2 adds words spoken and words corrected per dictation; fill them in for older history."""
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(history)")}
        if "spoken_words" in cols:
            return
        from .llm import count_corrections
        self.db.execute("ALTER TABLE history ADD COLUMN spoken_words INTEGER DEFAULT 0")
        self.db.execute("ALTER TABLE history ADD COLUMN corrections INTEGER DEFAULT 0")
        for r in self.db.execute("SELECT id, kind, raw, text FROM history").fetchall():
            spoken = len((r["raw"] or "").split())
            fixed = 0 if r["kind"] == "command" else count_corrections(r["raw"] or "", r["text"] or "")
            self.db.execute("UPDATE history SET spoken_words=?, corrections=? WHERE id=?", (spoken, fixed, r["id"]))

    def _q(self, sql, args=()):
        with self._lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.fetchall()

    # history
    def add_history(self, kind, app, raw, text, seconds, corrections=0):
        self._q("INSERT INTO history (ts, kind, app, raw, text, seconds, words, spoken_words, corrections) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), kind, app, raw, text, seconds,
                 len(text.split()), len(raw.split()), corrections))

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

    # insights
    @staticmethod
    def app_name(target: str) -> str:
        exe = (target or "").split(" - ")[0].strip()
        for suffix in (".exe", ".EXE", ".Exe"):
            exe = exe.removesuffix(suffix)
        return exe or "Unknown"

    def daily(self, days=30):
        """One row per day for the last `days` days (newest first), including days with no dictation."""
        since = (datetime.now().date() - timedelta(days=days - 1)).isoformat()
        rows = self._q("""SELECT substr(ts,1,10) d, COUNT(*) n, SUM(spoken_words) spoken, SUM(words) typed,
                                 SUM(corrections) fixed, SUM(seconds) secs
                          FROM history WHERE substr(ts,1,10) >= ? GROUP BY d""", (since,))
        by_day = {r["d"]: dict(r) for r in rows}
        apps = self._q("""SELECT substr(ts,1,10) d, app, SUM(spoken_words) w FROM history
                          WHERE substr(ts,1,10) >= ? GROUP BY d, app""", (since,))
        top: dict[str, dict] = {}
        for r in apps:
            per = top.setdefault(r["d"], {})
            name = self.app_name(r["app"])
            per[name] = per.get(name, 0) + (r["w"] or 0)
        out = []
        for i in range(days):
            d = (datetime.now().date() - timedelta(days=i)).isoformat()
            r = by_day.get(d, {"n": 0, "spoken": 0, "typed": 0, "fixed": 0, "secs": 0})
            per = top.get(d, {})
            out.append({"date": d, "dictations": r["n"] or 0, "spoken": r["spoken"] or 0, "typed": r["typed"] or 0,
                        "corrected": r["fixed"] or 0, "seconds": r["secs"] or 0.0,
                        "top_app": max(per, key=per.get) if per else ""})
        return out

    def top_apps(self, days=30, limit=8):
        """Apps ranked by words spoken into them over the last `days` days."""
        since = (datetime.now().date() - timedelta(days=days - 1)).isoformat()
        rows = self._q("""SELECT app, COUNT(*) n, SUM(spoken_words) w, SUM(seconds) s FROM history
                          WHERE substr(ts,1,10) >= ? GROUP BY app""", (since,))
        merged: dict[str, dict] = {}
        for r in rows:
            m = merged.setdefault(self.app_name(r["app"]), {"dictations": 0, "words": 0, "seconds": 0.0})
            m["dictations"] += r["n"] or 0
            m["words"] += r["w"] or 0
            m["seconds"] += r["s"] or 0.0
        ranked = sorted(merged.items(), key=lambda kv: (-kv[1]["words"], -kv[1]["dictations"]))
        return [{"app": k, **v} for k, v in ranked[:limit]]

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
