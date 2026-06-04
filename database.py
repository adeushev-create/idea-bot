import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

DB_PATH = "ideas.db"


class Database:
    def init(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    xp INTEGER DEFAULT 0,
                    total_ideas INTEGER DEFAULT 0,
                    done_count INTEGER DEFAULT 0,
                    links_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.commit()
        logger.info("Database initialized")

    def _conn(self):
        return sqlite3.connect(DB_PATH)

    def save_user(self, user_id: int):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                (user_id,)
            )
            conn.commit()

    def save_idea(self, user_id: int, content: str, raw_text: str,
                  topic: str, url: Optional[str], estimated_hours: Optional[float],
                  xp_reward: int) -> int:
        self.save_user(user_id)
        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO ideas 
                   (user_id, content, raw_text, topic, url, estimated_hours, xp_reward)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, content, raw_text, topic, url, estimated_hours, xp_reward)
            )
            idea_id = cursor.lastrowid

            # Обновляем счётчик идей
            conn.execute(
                "UPDATE users SET total_ideas = total_ideas + 1 WHERE user_id = ?",
                (user_id,)
            )
            if url:
                conn.execute(
                    "UPDATE users SET links_count = links_count + 1 WHERE user_id = ?",
                    (user_id,)
                )
            conn.commit()
        return idea_id

    def get_week_ideas(self, user_id: int) -> List[Dict]:
        week_ago = datetime.now() - timedelta(days=7)
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT * FROM ideas 
                   WHERE user_id = ? AND created_at >= ?
                   ORDER BY created_at DESC""",
                (user_id, week_ago.isoformat())
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_active_users(self) -> List[int]:
        with self._conn() as conn:
            cursor = conn.execute("SELECT user_id FROM users")
            return [row[0] for row in cursor.fetchall()]

    def mark_done(self, idea_id: int, user_id: int) -> int:
        with self._conn() as conn:
            # Получаем XP за задачу
            cursor = conn.execute(
                "SELECT xp_reward FROM ideas WHERE id = ? AND user_id = ?",
                (idea_id, user_id)
            )
            row = cursor.fetchone()
            if not row:
                return 0

            xp_reward = row[0]

            conn.execute(
                "UPDATE ideas SET done = 1 WHERE id = ? AND user_id = ?",
                (idea_id, user_id)
            )
            conn.execute(
                """UPDATE users 
                   SET xp = xp + ?, done_count = done_count + 1 
                   WHERE user_id = ?""",
                (xp_reward, user_id)
            )
            conn.commit()
        return xp_reward

    def get_user_xp(self, user_id: int) -> int:
        with self._conn() as conn:
            cursor = conn.execute(
                "SELECT xp FROM users WHERE user_id = ?", (user_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_user_stats(self, user_id: int) -> Dict:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return {"xp": 0, "total_ideas": 0, "done_count": 0, "links_count": 0}
