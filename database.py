import sqlite3
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)

DB_PATH = "bot_data.db"

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS published_news (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT UNIQUE,
                message_id  INTEGER,
                category    TEXT,
                published_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS polls (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT,
                message_id  INTEGER
            );

            CREATE TABLE IF NOT EXISTS football_state (
                id              INTEGER PRIMARY KEY CHECK (id = 1),
                match_id        TEXT,
                announce_msg_id INTEGER,
                last_score      TEXT DEFAULT '0-0',
                status          TEXT DEFAULT 'NS'
            );
        """)
        self.conn.commit()

    # ─── Новини ──────────────────────────────────────────────────────────────
    def is_published(self, url: str) -> bool:
        r = self.conn.execute("SELECT 1 FROM published_news WHERE url=?", (url,)).fetchone()
        return r is not None

    def mark_published(self, url: str, message_id: int, category: str = None):
        try:
            self.conn.execute(
                "INSERT INTO published_news (url, message_id, category) VALUES (?,?,?)",
                (url, message_id, category)
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass

    # ─── Опитування ──────────────────────────────────────────────────────────
    def polls_today(self) -> int:
        today = date.today().isoformat()
        r = self.conn.execute("SELECT COUNT(*) FROM polls WHERE date=?", (today,)).fetchone()
        return r[0]

    def save_poll(self, message_id: int):
        today = date.today().isoformat()
        self.conn.execute("INSERT INTO polls (date, message_id) VALUES (?,?)", (today, message_id))
        self.conn.commit()

    # ─── Футбол ──────────────────────────────────────────────────────────────
    def get_football_state(self) -> dict | None:
        r = self.conn.execute("SELECT * FROM football_state WHERE id=1").fetchone()
        if not r:
            return None
        return {"match_id": r[1], "announce_msg_id": r[2], "last_score": r[3], "status": r[4]}

    def set_football_announce(self, match_id: str, announce_msg_id: int):
        self.conn.execute("""
            INSERT INTO football_state (id, match_id, announce_msg_id, last_score, status)
            VALUES (1, ?, ?, '0-0', 'NS')
            ON CONFLICT(id) DO UPDATE SET
                match_id=excluded.match_id,
                announce_msg_id=excluded.announce_msg_id,
                last_score='0-0',
                status='NS'
        """, (match_id, announce_msg_id))
        self.conn.commit()

    def update_football_score(self, score: str, status: str):
        self.conn.execute(
            "UPDATE football_state SET last_score=?, status=? WHERE id=1",
            (score, status)
        )
        self.conn.commit()

    def clear_football_state(self):
        self.conn.execute("DELETE FROM football_state WHERE id=1")
        self.conn.commit()
