import sqlite3
import logging
from datetime import datetime, timedelta
from config import Config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_path = Config.DB_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                is_active INTEGER DEFAULT 0,
                subscription_end TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_text TEXT,
                bot_reply TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.commit()
        conn.close()
        logger.info("✅ Database tayyor!")

    def add_user(self, user_id: int, username: str, full_name: str):
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO users (user_id, username, full_name)
                   VALUES (?, ?, ?)""",
                (user_id, username, full_name)
            )
            # Update info if exists
            conn.execute(
                """UPDATE users SET username=?, full_name=? WHERE user_id=?""",
                (username, full_name, user_id)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"add_user error: {e}")
        finally:
            conn.close()

    def is_active_subscriber(self, user_id: int) -> bool:
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT is_active, subscription_end FROM users WHERE user_id=?""",
                (user_id,)
            ).fetchone()
            
            if not row:
                return False
            
            if not row['is_active']:
                return False

            if row['subscription_end']:
                end_date = datetime.fromisoformat(row['subscription_end'])
                if datetime.now() > end_date:
                    # Expire
                    conn.execute(
                        "UPDATE users SET is_active=0 WHERE user_id=?", (user_id,)
                    )
                    conn.commit()
                    return False
            
            return True
        except Exception as e:
            logger.error(f"is_active_subscriber error: {e}")
            return False
        finally:
            conn.close()

    def activate_subscription(self, user_id: int):
        conn = self._get_conn()
        try:
            end_date = (datetime.now() + timedelta(days=Config.SUBSCRIPTION_DAYS)).isoformat()
            conn.execute(
                """UPDATE users SET is_active=1, subscription_end=? WHERE user_id=?""",
                (end_date, user_id)
            )
            conn.commit()
            logger.info(f"✅ User {user_id} subscription activated until {end_date}")
        except Exception as e:
            logger.error(f"activate_subscription error: {e}")
        finally:
            conn.close()

    def add_payment(self, user_id: int, file_id: str) -> int:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT INTO payments (user_id, file_id) VALUES (?, ?)""",
                (user_id, file_id)
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"add_payment error: {e}")
            return 0
        finally:
            conn.close()

    def update_payment_status(self, payment_id: int, status: str):
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE payments SET status=? WHERE id=?",
                (status, payment_id)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"update_payment_status error: {e}")
        finally:
            conn.close()

    def get_pending_payments(self) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT p.id, p.user_id, p.file_id, p.created_at, u.full_name, u.username
                   FROM payments p
                   JOIN users u ON p.user_id = u.user_id
                   WHERE p.status='pending'
                   ORDER BY p.created_at DESC"""
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_pending_payments error: {e}")
            return []
        finally:
            conn.close()

    def log_message(self, user_id: int, user_text: str, bot_reply: str):
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO messages (user_id, user_text, bot_reply) VALUES (?, ?, ?)""",
                (user_id, user_text[:1000], bot_reply[:2000])
            )
            conn.commit()
        except Exception as e:
            logger.error(f"log_message error: {e}")
        finally:
            conn.close()

    def get_stats(self) -> dict:
        conn = self._get_conn()
        try:
            total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            active_subs = conn.execute(
                "SELECT COUNT(*) FROM users WHERE is_active=1"
            ).fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM payments WHERE status='pending'"
            ).fetchone()[0]
            total_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            approved_payments = conn.execute(
                "SELECT COUNT(*) FROM payments WHERE status='approved'"
            ).fetchone()[0]
            
            return {
                "total_users": total_users,
                "active_subs": active_subs,
                "pending": pending,
                "total_messages": total_messages,
                "approved_payments": approved_payments
            }
        except Exception as e:
            logger.error(f"get_stats error: {e}")
            return {}
        finally:
            conn.close()

    def get_all_users(self) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT user_id, username, full_name, is_active, subscription_end FROM users ORDER BY id DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_all_users error: {e}")
            return []
        finally:
            conn.close()

    def get_active_subscribers(self) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT user_id FROM users WHERE is_active=1"
            ).fetchall()
            return [r['user_id'] for r in rows]
        except Exception as e:
            logger.error(f"get_active_subscribers error: {e}")
            return []
        finally:
            conn.close()
