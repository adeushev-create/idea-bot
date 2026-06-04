import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

# Use PostgreSQL if DATABASE_URL is set, otherwise SQLite
if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    USE_PG = True
else:
    import sqlite3
    USE_PG = False
    DB_PATH = "ideas.db"


class Database:
    def _conn(self):
        if USE_PG:
            return psycopg2.connect(DATABASE_URL)
        return sqlite3.connect(DB_PATH)

    def init(self):
        with self._conn() as conn:
            cur = conn.cursor()
            if USE_PG:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        xp INTEGER DEFAULT 0,
                        total_ideas INTEGER DEFAULT 0,
                        done_count INTEGER DEFAULT 0,
                        links_count INTEGER DEFAULT 0,
                        streak INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW()
                    )""")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ideas (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        content TEXT NOT NULL,
                        raw_text TEXT,
                        topic TEXT DEFAULT 'Разное',
                        url TEXT,
                        estimated_hours REAL,
                        xp_reward INTEGER DEFAULT 10,
                        done INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW()
                    )""")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS usernames (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT
                    )""")
            else:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        xp INTEGER DEFAULT 0,
                        total_ideas INTEGER DEFAULT 0,
                        done_count INTEGER DEFAULT 0,
                        links_count INTEGER DEFAULT 0,
                        streak INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )""")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ideas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        raw_text TEXT,
                        topic TEXT DEFAULT 'Разное',
                        url TEXT,
                        estimated_hours REAL,
                        xp_reward INTEGER DEFAULT 10,
                        done INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )""")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS usernames (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT
                    )""")
            conn.commit()
        logger.info(f"Database initialized ({'PostgreSQL' if USE_PG else 'SQLite'})")

    def _row_to_dict(self, cursor, row):
        if USE_PG:
            cols = [d[0] for d in cursor.description]
            return dict(zip(cols, row))
        return dict(row)

    def save_user(self, user_id: int):
        with self._conn() as conn:
            cur = conn.cursor()
            if USE_PG:
                cur.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
            else:
                cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            conn.commit()

    def save_username(self, user_id: int, username: str, first_name: str):
        with self._conn() as conn:
            cur = conn.cursor()
            if USE_PG:
                cur.execute("""
                    INSERT INTO usernames (user_id, username, first_name) VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username, first_name=EXCLUDED.first_name
                """, (user_id, username, first_name))
            else:
                cur.execute("""
                    INSERT OR REPLACE INTO usernames (user_id, username, first_name) VALUES (?, ?, ?)
                """, (user_id, username, first_name))
            conn.commit()

    def save_idea(self, user_id: int, content: str, raw_text: str,
                  topic: str, url: Optional[str], estimated_hours: Optional[float],
                  xp_reward: int) -> int:
        self.save_user(user_id)
        with self._conn() as conn:
            cur = conn.cursor()
            if USE_PG:
                cur.execute("""
                    INSERT INTO ideas (user_id, content, raw_text, topic, url, estimated_hours, xp_reward)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                """, (user_id, content, raw_text, topic, url, estimated_hours, xp_reward))
                idea_id = cur.fetchone()[0]
                cur.execute("UPDATE users SET total_ideas = total_ideas + 1 WHERE user_id = %s", (user_id,))
                if url:
                    cur.execute("UPDATE users SET links_count = links_count + 1 WHERE user_id = %s", (user_id,))
            else:
                cur.execute("""
                    INSERT INTO ideas (user_id, content, raw_text, topic, url, estimated_hours, xp_reward)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, content, raw_text, topic, url, estimated_hours, xp_reward))
                idea_id = cur.lastrowid
                cur.execute("UPDATE users SET total_ideas = total_ideas + 1 WHERE user_id = ?", (user_id,))
                if url:
                    cur.execute("UPDATE users SET links_count = links_count + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
        return idea_id

    def get_week_ideas(self, user_id: int) -> List[Dict]:
        week_ago = datetime.now() - timedelta(days=7)
        with self._conn() as conn:
            cur = conn.cursor()
            if USE_PG:
                cur.execute("""
                    SELECT * FROM ideas WHERE user_id = %s AND created_at >= %s ORDER BY created_at DESC
                """, (user_id, week_ago))
            else:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("""
                    SELECT * FROM ideas WHERE user_id = ? AND created_at >= ? ORDER BY created_at DESC
                """, (user_id, week_ago.isoformat()))
            rows = cur.fetchall()
            if USE_PG:
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, r)) for r in rows]
            return [dict(r) for r in rows]

    def get_all_active_users(self) -> List[int]:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users")
            return [r[0] for r in cur.fetchall()]

    def mark_done(self, idea_id: int, user_id: int) -> int:
        with self._conn() as conn:
            cur = conn.cursor()
            if USE_PG:
                cur.execute("SELECT xp_reward FROM ideas WHERE id = %s AND user_id = %s", (idea_id, user_id))
            else:
                cur.execute("SELECT xp_reward FROM ideas WHERE id = ? AND user_id = ?", (idea_id, user_id))
            row = cur.fetchone()
            if not row:
                return 0
            xp_reward = row[0]
            if USE_PG:
                cur.execute("UPDATE ideas SET done = 1 WHERE id = %s AND user_id = %s", (idea_id, user_id))
                cur.execute("UPDATE users SET xp = xp + %s, done_count = done_count + 1 WHERE user_id = %s", (xp_reward, user_id))
            else:
                cur.execute("UPDATE ideas SET done = 1 WHERE id = ? AND user_id = ?", (idea_id, user_id))
                cur.execute("UPDATE users SET xp = xp + ?, done_count = done_count + 1 WHERE user_id = ?", (xp_reward, user_id))
            conn.commit()
        return xp_reward

    def get_user_xp(self, user_id: int) -> int:
        with self._conn() as conn:
            cur = conn.cursor()
            if USE_PG:
                cur.execute("SELECT xp FROM users WHERE user_id = %s", (user_id,))
            else:
                cur.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            return row[0] if row else 0

    def get_user_stats(self, user_id: int) -> Dict:
        with self._conn() as conn:
            cur = conn.cursor()
            if USE_PG:
                cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                if row:
                    cols = [d[0] for d in cur.description]
                    return dict(zip(cols, row))
            else:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                row = cur.fetchone()
                if row:
                    return dict(row)
        return {"xp": 0, "total_ideas": 0, "done_count": 0, "links_count": 0, "streak": 0}

    def get_leaderboard(self, limit: int = 20) -> List[Dict]:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, xp, total_ideas, done_count FROM users ORDER BY xp DESC LIMIT %s" if USE_PG else
                       "SELECT user_id, xp, total_ideas, done_count FROM users ORDER BY xp DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            if USE_PG:
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, r)) for r in rows]
            return [{"user_id": r[0], "xp": r[1], "total_ideas": r[2], "done_count": r[3]} for r in rows]

    def get_usernames(self, user_ids: List[int]) -> Dict:
        if not user_ids:
            return {}
        with self._conn() as conn:
            cur = conn.cursor()
            try:
                placeholders = ','.join(['%s' if USE_PG else '?' for _ in user_ids])
                cur.execute(f"SELECT user_id, first_name FROM usernames WHERE user_id IN ({placeholders})", user_ids)
                return {r[0]: r[1] for r in cur.fetchall()}
            except:
                return {}
