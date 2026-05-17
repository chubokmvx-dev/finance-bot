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
                title       TEXT,
                views       INTEGER DEFAULT 0,
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

            CREATE TABLE IF NOT EXISTS digest_state (
                id      INTEGER PRIMARY KEY CHECK (id = 1),
                last_digest_date TEXT DEFAULT ''
            );
        """)
        self.conn.commit()

    # ─── Новини ──────────────────────────────────────────────────────────────
    def is_published(self, url: str) -> bool:
        r = self.conn.execute("SELECT 1 FROM published_news WHERE url=?", (url,)).fetchone()
        return r is not None

    def is_similar_title(self, title: str) -> bool:
        """Перевіряє чи є схожий заголовок серед останніх 50 публікацій."""
        if not title or len(title) < 10:
            return False
        # Беремо ключові слова з заголовку (слова довші за 4 символи)
        words = [w.lower() for w in title.split() if len(w) > 4]
        if not words:
            return False
        recent = self.conn.execute(
            "SELECT title FROM published_news WHERE title IS NOT NULL ORDER BY id DESC LIMIT 50"
        ).fetchall()
        for (existing_title,) in recent:
            if not existing_title:
                continue
            existing_words = [w.lower() for w in existing_title.split() if len(w) > 4]
            # Якщо більше 60% ключових слів співпадає — дублікат
            if not existing_words:
                continue
            matches = sum(1 for w in words if w in existing_words)
            similarity = matches / max(len(words), len(existing_words))
            if similarity > 0.6:
                return True
        return False

    def mark_published(self, url: str, message_id: int, category: str = None, title: str = None):
        try:
            self.conn.execute(
                "INSERT INTO published_news (url, message_id, category, title) VALUES (?,?,?,?)",
                (url, message_id, category, title)
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass

    def get_today_posts(self) -> list[dict]:
        """Повертає всі пости за сьогодні для дайджесту."""
        today = date.today().isoformat()
        rows = self.conn.execute("""
            SELECT title, category, message_id, published_at
            FROM published_news
            WHERE published_at LIKE ? AND title IS NOT NULL
            AND category NOT IN ('urgent')
            ORDER BY id DESC LIMIT 20
        """, (f"{today}%",)).fetchall()
        return [{"title": r[0], "category": r[1], "message_id": r[2], "published_at": r[3]} for r in rows]

    def get_week_top_posts(self) -> list[dict]:
        """Повертає топ постів за тиждень для статистики."""
        rows = self.conn.execute("""
            SELECT title, category, message_id, views, published_at
            FROM published_news
            WHERE published_at >= datetime('now', '-7 days')
            AND title IS NOT NULL
            ORDER BY views DESC, id DESC LIMIT 5
        """).fetchall()
        return [{"title": r[0], "category": r[1], "message_id": r[2], "views": r[3], "published_at": r[4]} for r in rows]

    def update_views(self, message_id: int, views: int):
        self.conn.execute(
            "UPDATE published_news SET views=? WHERE message_id=?",
            (views, message_id)
        )
        self.conn.commit()

    def digest_sent_today(self) -> bool:
        today = date.today().isoformat()
        r = self.conn.execute("SELECT last_digest_date FROM digest_state WHERE id=1").fetchone()
        return r is not None and r[0] == today

    def mark_digest_sent(self):
        today = date.today().isoformat()
        self.conn.execute("""
            INSERT INTO digest_state (id, last_digest_date) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET last_digest_date=excluded.last_digest_date
        """, (today,))
        self.conn.commit()

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

