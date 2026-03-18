import sqlite3
import logging
from datetime import datetime, timedelta
from config import Config

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.db_path = Config.DB_PATH
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id          INTEGER UNIQUE NOT NULL,
                    username         TEXT,
                    full_name        TEXT,
                    is_active        INTEGER DEFAULT 0,
                    subscription_end TEXT,
                    created_at       TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS payments (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    file_id    TEXT NOT NULL,
                    status     TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    user_text  TEXT,
                    bot_reply  TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Suhbat tarixi (volume da saqlanadi)
                CREATE TABLE IF NOT EXISTS chat_history (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Kunlik xabar hisob-kitobi
                CREATE TABLE IF NOT EXISTS daily_usage (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       INTEGER NOT NULL,
                    usage_date    TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    UNIQUE(user_id, usage_date)
                );

                -- Majburiy kanallar (admin panel orqali boshqariladi)
                CREATE TABLE IF NOT EXISTS required_channels (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT UNIQUE NOT NULL,
                    name       TEXT NOT NULL,
                    link       TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Bot sozlamalari (kalit-qiymat)
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
        logger.info("✅ Database tayyor!")

    # ─── FOYDALANUVCHILAR ─────────────────────────────────────────────────────

    def add_user(self, user_id: int, username: str, full_name: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?,?,?)",
                (user_id, username or "", full_name or "")
            )
            conn.execute(
                "UPDATE users SET username=?, full_name=? WHERE user_id=?",
                (username or "", full_name or "", user_id)
            )

    def is_active_subscriber(self, user_id: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT is_active, subscription_end FROM users WHERE user_id=?",
                (user_id,)
            ).fetchone()
            if not row or not row["is_active"]:
                return False
            if row["subscription_end"]:
                end = datetime.fromisoformat(row["subscription_end"])
                if datetime.now() > end:
                    conn.execute("UPDATE users SET is_active=0 WHERE user_id=?", (user_id,))
                    return False
            return True

    def get_subscription_info(self, user_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT is_active, subscription_end FROM users WHERE user_id=?",
                (user_id,)
            ).fetchone()
            if not row:
                return {"is_active": False, "days_left": 0, "end_date": None}
            days_left = 0
            end_date = None
            if row["subscription_end"]:
                end_date = datetime.fromisoformat(row["subscription_end"])
                days_left = max(0, (end_date - datetime.now()).days)
            active = bool(row["is_active"]) and days_left > 0
            return {"is_active": active, "days_left": days_left, "end_date": end_date}

    def activate_subscription(self, user_id: int) -> str:
        """Obunani faollashtiradi yoki muddatini uzaytiradi."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT subscription_end, is_active FROM users WHERE user_id=?",
                (user_id,)
            ).fetchone()
            now = datetime.now()
            if row and row["is_active"] and row["subscription_end"]:
                current_end = datetime.fromisoformat(row["subscription_end"])
                base = current_end if current_end > now else now
            else:
                base = now
            end_date = (base + timedelta(days=Config.SUBSCRIPTION_DAYS)).isoformat()
            conn.execute(
                "UPDATE users SET is_active=1, subscription_end=? WHERE user_id=?",
                (end_date, user_id)
            )
            return end_date

    def deactivate_subscription(self, user_id: int):
        with self._conn() as conn:
            conn.execute("UPDATE users SET is_active=0 WHERE user_id=?", (user_id,))

    def get_expiring_users(self) -> list:
        """Obunasi {EXPIRY_WARN_DAYS} kun ichida tugaydigan foydalanuvchilar."""
        warn = (datetime.now() + timedelta(days=Config.EXPIRY_WARN_DAYS)).isoformat()
        now  = datetime.now().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT user_id, full_name, subscription_end
                   FROM users
                   WHERE is_active=1 AND subscription_end IS NOT NULL
                     AND subscription_end <= ? AND subscription_end >= ?""",
                (warn, now)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_users(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT user_id, username, full_name, is_active, subscription_end FROM users ORDER BY id DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_active_subscribers(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT user_id FROM users WHERE is_active=1"
            ).fetchall()
            return [r["user_id"] for r in rows]

    def get_all_user_ids(self) -> list:
        with self._conn() as conn:
            rows = conn.execute("SELECT user_id FROM users").fetchall()
            return [r["user_id"] for r in rows]

    # ─── TO'LOVLAR ────────────────────────────────────────────────────────────

    def add_payment(self, user_id: int, file_id: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO payments (user_id, file_id) VALUES (?,?)",
                (user_id, file_id)
            )
            return cur.lastrowid

    def update_payment_status(self, payment_id: int, status: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE payments SET status=? WHERE id=?",
                (status, payment_id)
            )

    def get_pending_payments(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT p.id, p.user_id, p.file_id, p.created_at, u.full_name, u.username
                   FROM payments p JOIN users u ON p.user_id=u.user_id
                   WHERE p.status='pending' ORDER BY p.created_at DESC"""
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── SUHBAT TARIXI (volume da saqlanadi) ──────────────────────────────────

    def get_history(self, user_id: int, limit: int = 20) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT role, content FROM chat_history
                   WHERE user_id=? ORDER BY id DESC LIMIT ?""",
                (user_id, limit)
            ).fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def add_history(self, user_id: int, role: str, content: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES (?,?,?)",
                (user_id, role, content[:4000])
            )

    def clear_history(self, user_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))

    # ─── KUNLIK LIMIT ─────────────────────────────────────────────────────────

    def get_daily_count(self, user_id: int) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        with self._conn() as conn:
            row = conn.execute(
                "SELECT message_count FROM daily_usage WHERE user_id=? AND usage_date=?",
                (user_id, today)
            ).fetchone()
            return row["message_count"] if row else 0

    def increment_daily(self, user_id: int):
        today = datetime.now().strftime("%Y-%m-%d")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO daily_usage (user_id, usage_date, message_count) VALUES (?,?,1)
                   ON CONFLICT(user_id, usage_date) DO UPDATE SET message_count=message_count+1""",
                (user_id, today)
            )

    # ─── MAJBURIY KANALLAR (admin panel) ─────────────────────────────────────

    def get_channels(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, channel_id, name, link FROM required_channels ORDER BY id"
            ).fetchall()
            return [dict(r) for r in rows]

    def add_channel(self, channel_id: str, name: str, link: str) -> bool:
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO required_channels (channel_id, name, link) VALUES (?,?,?)",
                    (channel_id, name, link)
                )
            return True
        except Exception as e:
            logger.error(f"add_channel error: {e}")
            return False

    def remove_channel(self, channel_id: str) -> bool:
        try:
            with self._conn() as conn:
                conn.execute(
                    "DELETE FROM required_channels WHERE channel_id=?", (channel_id,)
                )
            return True
        except Exception as e:
            logger.error(f"remove_channel error: {e}")
            return False

    # ─── SOZLAMALAR ───────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                (key, value)
            )

    # ─── XABARLAR LOGI ────────────────────────────────────────────────────────

    def log_message(self, user_id: int, user_text: str, bot_reply: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO messages (user_id, user_text, bot_reply) VALUES (?,?,?)",
                (user_id, user_text[:1000], bot_reply[:2000])
            )

    # ─── STATISTIKA ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        with self._conn() as conn:
            return {
                "total_users":      conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "active_subs":      conn.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0],
                "pending":          conn.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0],
                "total_messages":   conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
                "approved":         conn.execute("SELECT COUNT(*) FROM payments WHERE status='approved'").fetchone()[0],
                "today_messages":   conn.execute(
                    "SELECT COALESCE(SUM(message_count),0) FROM daily_usage WHERE usage_date=?", (today,)
                ).fetchone()[0],
                "channels":         conn.execute("SELECT COUNT(*) FROM required_channels").fetchone()[0],
            }

    # ─── OYLIK TOZALASH (Railway volume) ─────────────────────────────────────

    def monthly_cleanup(self):
        """
        Har oy boshida chaqiriladi.
        - Muddati o'tgan chat tarixi (30 kundan eski) o'chiriladi.
        - Eski kunlik statistika (60 kundan eski) o'chiriladi.
        - Muddati tugagan obunalar o'chiriladi.
        Volume da baza saqlanadi, faqat ichidagi eski ma'lumotlar tozalanadi.
        """
        cutoff_history = (datetime.now() - timedelta(days=30)).isoformat()
        cutoff_daily   = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        cutoff_msgs    = (datetime.now() - timedelta(days=90)).isoformat()

        with self._conn() as conn:
            conn.execute("DELETE FROM chat_history WHERE created_at < ?", (cutoff_history,))
            conn.execute("DELETE FROM daily_usage WHERE usage_date < ?", (cutoff_daily,))
            conn.execute("DELETE FROM messages WHERE created_at < ?", (cutoff_msgs,))
            conn.execute(
                "UPDATE users SET is_active=0 WHERE is_active=1 AND subscription_end < ?",
                (datetime.now().isoformat(),)
            )
            conn.execute("VACUUM")
        logger.info("✅ Oylik tozalash bajarildi!")
