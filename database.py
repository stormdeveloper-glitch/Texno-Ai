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
                    is_vip           INTEGER DEFAULT 0,
                    subscription_end TEXT,
                    balance          INTEGER DEFAULT 0,
                    referral_code    TEXT UNIQUE,
                    referred_by      INTEGER,
                    created_at       TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS payments (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id        INTEGER NOT NULL,
                    file_id        TEXT NOT NULL,
                    payment_type   TEXT DEFAULT 'normal',
                    status         TEXT DEFAULT 'pending',
                    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    user_text  TEXT,
                    bot_reply  TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS chat_history (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS daily_usage (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       INTEGER NOT NULL,
                    usage_date    TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    UNIQUE(user_id, usage_date)
                );

                CREATE TABLE IF NOT EXISTS required_channels (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT UNIQUE NOT NULL,
                    name       TEXT NOT NULL,
                    link       TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS referral_history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id  INTEGER NOT NULL,
                    referred_id  INTEGER NOT NULL,
                    bonus_amount INTEGER DEFAULT 0,
                    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS bot_orders (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NOT NULL,
                    payment_id   INTEGER,
                    token        TEXT,
                    bot_name     TEXT,
                    bot_username TEXT,
                    status       TEXT DEFAULT 'pending_payment',
                    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)
            # Migration: eski DB larga yangi ustunlar qo'shish
            for col, defval in [
                ("is_vip",        "INTEGER DEFAULT 0"),
                ("balance",       "INTEGER DEFAULT 0"),
                ("referral_code", "TEXT"),
                ("referred_by",   "INTEGER"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {col} {defval}")
                except Exception:
                    pass
            # payments ga payment_type ustuni qo'shish
            try:
                conn.execute("ALTER TABLE payments ADD COLUMN payment_type TEXT DEFAULT 'normal'")
            except Exception:
                pass
            # bot_orders migration
            for col, defval in [
                ("bot_username", "TEXT"),
                ("payment_id",   "INTEGER"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE bot_orders ADD COLUMN {col} {defval}")
                except Exception:
                    pass
        logger.info("✅ Database tayyor!")

    # ─── FOYDALANUVCHILAR ─────────────────────────────────────────────────────

    def add_user(self, user_id: int, username: str, full_name: str, referred_by: int = None):
        import random, string
        ref_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO users (user_id, username, full_name, referral_code, referred_by)
                   VALUES (?,?,?,?,?)""",
                (user_id, username or "", full_name or "", ref_code, referred_by)
            )
            conn.execute(
                "UPDATE users SET username=?, full_name=? WHERE user_id=?",
                (username or "", full_name or "", user_id)
            )
            # referral_code bo'sh bo'lsa yangi kod berish
            row = conn.execute("SELECT referral_code FROM users WHERE user_id=?", (user_id,)).fetchone()
            if not row or not row["referral_code"]:
                conn.execute("UPDATE users SET referral_code=? WHERE user_id=?", (ref_code, user_id))

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

    def is_vip(self, user_id: int) -> bool:
        """
        VIP faqat is_active=1 bo'lsa va muddati tugamagan bo'lsa True.
        BUG FIX: Ilgari obuna muddati tekshirilmay, is_vip=1 bo'lsa doim True qaytardi.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT is_vip, is_active, subscription_end FROM users WHERE user_id=?",
                (user_id,)
            ).fetchone()
            if not row or not row["is_vip"] or not row["is_active"]:
                return False
            if row["subscription_end"]:
                end = datetime.fromisoformat(row["subscription_end"])
                if datetime.now() > end:
                    # Obuna tugagan - VIP ham emas
                    conn.execute("UPDATE users SET is_active=0 WHERE user_id=?", (user_id,))
                    return False
            return True

    def set_vip(self, user_id: int, status: bool):
        with self._conn() as conn:
            conn.execute(
                "UPDATE users SET is_vip=? WHERE user_id=?",
                (1 if status else 0, user_id)
            )

    def activate_vip_subscription(self, user_id: int) -> str:
        """
        VIP obunani faollashtiradi — is_vip=1 va muddatni uzaytiradi.
        BUG FIX: Ilgari VIP ni faqat /setvip orqali berish mumkin edi,
        to'lov tasdiqlansa oddiy obuna faollashtirilardi.
        """
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
                "UPDATE users SET is_active=1, is_vip=1, subscription_end=? WHERE user_id=?",
                (end_date, user_id)
            )
            return end_date

    def get_user_limit(self, user_id: int) -> int:
        """
        Foydalanuvchi limitini qaytaradi.
        BUG FIX: is_vip() endi obuna muddatini ham tekshiradi.
        """
        if self.is_vip(user_id):
            return int(self.get_setting("vip_limit", str(Config.DAILY_LIMIT_VIP)))
        return int(self.get_setting("normal_limit", str(Config.DAILY_LIMIT_NORMAL)))

    def activate_subscription(self, user_id: int) -> str:
        """Oddiy obunani faollashtiradi (is_vip o'zgarmaydi)."""
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
            conn.execute(
                "UPDATE users SET is_active=0, is_vip=0 WHERE user_id=?",
                (user_id,)
            )

    def get_subscription_info(self, user_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT is_active, is_vip, subscription_end, balance FROM users WHERE user_id=?",
                (user_id,)
            ).fetchone()
            if not row:
                return {"is_active": False, "is_vip": False, "days_left": 0, "end_date": None, "balance": 0}
            days_left = 0
            end_date = None
            if row["subscription_end"]:
                end_date = datetime.fromisoformat(row["subscription_end"])
                days_left = max(0, (end_date - datetime.now()).days)
            active = bool(row["is_active"]) and days_left > 0
            # VIP faqat aktiv obuna bilan
            is_vip_active = bool(row["is_vip"]) and active
            return {
                "is_active": active,
                "is_vip": is_vip_active,
                "days_left": days_left,
                "end_date": end_date,
                "balance": row["balance"] or 0
            }

    def get_expiring_users(self) -> list:
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
                "SELECT user_id, username, full_name, is_active, is_vip, subscription_end, balance FROM users ORDER BY id DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_active_subscribers(self) -> list:
        with self._conn() as conn:
            rows = conn.execute("SELECT user_id FROM users WHERE is_active=1").fetchall()
            return [r["user_id"] for r in rows]

    def get_all_user_ids(self) -> list:
        with self._conn() as conn:
            rows = conn.execute("SELECT user_id FROM users").fetchall()
            return [r["user_id"] for r in rows]

    # ─── TO'LOVLAR ────────────────────────────────────────────────────────────

    def add_payment(self, user_id: int, file_id: str, payment_type: str = "normal") -> int:
        """
        BUG FIX: payment_type parametri qo'shildi.
        'normal' = oddiy obuna, 'vip' = VIP obuna.
        """
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO payments (user_id, file_id, payment_type) VALUES (?,?,?)",
                (user_id, file_id, payment_type)
            )
            return cur.lastrowid

    def get_payment_type(self, payment_id: int) -> str:
        """To'lov turini qaytaradi (normal yoki vip)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payment_type FROM payments WHERE id=?", (payment_id,)
            ).fetchone()
            return row["payment_type"] if row else "normal"

    def update_payment_status(self, payment_id: int, status: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE payments SET status=? WHERE id=?",
                (status, payment_id)
            )

    def get_pending_payments(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT p.id, p.user_id, p.file_id, p.payment_type, p.created_at, u.full_name, u.username
                   FROM payments p JOIN users u ON p.user_id=u.user_id
                   WHERE p.status='pending' ORDER BY p.created_at DESC"""
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── SUHBAT TARIXI ────────────────────────────────────────────────────────

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

    # ─── REFERRAL ─────────────────────────────────────────────────────────────

    def get_referral_code(self, user_id: int) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT referral_code FROM users WHERE user_id=?", (user_id,)
            ).fetchone()
            return row["referral_code"] if row else None

    def get_user_by_referral_code(self, code: str):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT user_id, full_name FROM users WHERE referral_code=?", (code,)
            ).fetchone()
            return dict(row) if row else None

    def process_referral(self, referrer_id: int, referred_id: int) -> bool:
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM referral_history WHERE referred_id=?", (referred_id,)
            ).fetchone()
            if existing:
                return False
            bonus = Config.REFERRAL_BONUS_UZS
            conn.execute(
                "INSERT INTO referral_history (referrer_id, referred_id, bonus_amount) VALUES (?,?,?)",
                (referrer_id, referred_id, bonus)
            )
            conn.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=?",
                (bonus, referrer_id)
            )
            return True

    def get_referral_stats(self, user_id: int) -> dict:
        with self._conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) as cnt FROM referral_history WHERE referrer_id=?", (user_id,)
            ).fetchone()["cnt"]
            total_bonus = conn.execute(
                "SELECT COALESCE(SUM(bonus_amount), 0) as total FROM referral_history WHERE referrer_id=?",
                (user_id,)
            ).fetchone()["total"]
            balance = conn.execute(
                "SELECT COALESCE(balance, 0) as bal FROM users WHERE user_id=?", (user_id,)
            ).fetchone()["bal"]
            return {"count": count, "total_bonus": total_bonus, "balance": balance}

    def get_balance(self, user_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(balance, 0) as bal FROM users WHERE user_id=?", (user_id,)
            ).fetchone()
            return row["bal"] if row else 0

    # ─── MAJBURIY KANALLAR ────────────────────────────────────────────────────

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
                conn.execute("DELETE FROM required_channels WHERE channel_id=?", (channel_id,))
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

    def clear_pending_check(self, user_id: int):
        """
        BUG FIX: waiting_check ni DB dan to'liq o'chiradi (0 qilmaydi, o'chiradi).
        Eski yondashuv '0' qiymati bilan yozgan va DB da chiqindi qolgan.
        """
        with self._conn() as conn:
            conn.execute("DELETE FROM settings WHERE key=?", (f"waiting_check_{user_id}",))

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
                "vip_users":        conn.execute("SELECT COUNT(*) FROM users WHERE is_vip=1 AND is_active=1").fetchone()[0],
                "pending":          conn.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0],
                "pending_vip":      conn.execute("SELECT COUNT(*) FROM payments WHERE status='pending' AND payment_type='vip'").fetchone()[0],
                "total_messages":   conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
                "approved":         conn.execute("SELECT COUNT(*) FROM payments WHERE status='approved'").fetchone()[0],
                "today_messages":   conn.execute(
                    "SELECT COALESCE(SUM(message_count),0) FROM daily_usage WHERE usage_date=?", (today,)
                ).fetchone()[0],
                "channels":         conn.execute("SELECT COUNT(*) FROM required_channels").fetchone()[0],
                "total_referrals":  conn.execute("SELECT COUNT(*) FROM referral_history").fetchone()[0],
                "total_bonuses":    conn.execute("SELECT COALESCE(SUM(bonus_amount),0) FROM referral_history").fetchone()[0],
            }

    # ─── OYLIK TOZALASH ───────────────────────────────────────────────────────

    def monthly_cleanup(self):
        cutoff_history = (datetime.now() - timedelta(days=30)).isoformat()
        cutoff_daily   = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        cutoff_msgs    = (datetime.now() - timedelta(days=90)).isoformat()
        with self._conn() as conn:
            conn.execute("DELETE FROM chat_history WHERE created_at < ?", (cutoff_history,))
            conn.execute("DELETE FROM daily_usage WHERE usage_date < ?", (cutoff_daily,))
            conn.execute("DELETE FROM messages WHERE created_at < ?", (cutoff_msgs,))
            conn.execute(
                "UPDATE users SET is_active=0, is_vip=0 WHERE is_active=1 AND subscription_end < ?",
                (datetime.now().isoformat(),)
            )
            # BUG FIX: waiting_check chiqindilari ham tozalanadi
            conn.execute("DELETE FROM settings WHERE key LIKE 'waiting_check_%'")
            conn.execute("VACUUM")
        logger.info("✅ Oylik tozalash bajarildi!")

    # ─── ADMIN: BATAFSIL USER MA'LUMOTLARI ───────────────────────────────────

    def get_user_detail(self, user_id: int):
        """Bitta foydalanuvchi haqida to'liq ma'lumot."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT user_id, username, full_name, is_active, is_vip,
                          subscription_end, balance, referral_code, referred_by, created_at
                   FROM users WHERE user_id=?""",
                (user_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            if d["referred_by"]:
                ref_row = conn.execute(
                    "SELECT full_name, username FROM users WHERE user_id=?", (d["referred_by"],)
                ).fetchone()
                d["referred_by_name"]     = ref_row["full_name"] if ref_row else "?"
                d["referred_by_username"] = ref_row["username"]  if ref_row else ""
            else:
                d["referred_by_name"]     = None
                d["referred_by_username"] = None
            ref_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM referral_history WHERE referrer_id=?", (user_id,)
            ).fetchone()["cnt"]
            d["referral_count"] = ref_count
            ref_earned = conn.execute(
                "SELECT COALESCE(SUM(bonus_amount),0) as total FROM referral_history WHERE referrer_id=?", (user_id,)
            ).fetchone()["total"]
            d["referral_earned"] = ref_earned
            today = datetime.now().strftime("%Y-%m-%d")
            today_row = conn.execute(
                "SELECT COALESCE(message_count,0) as cnt FROM daily_usage WHERE user_id=? AND usage_date=?",
                (user_id, today)
            ).fetchone()
            d["today_messages"] = today_row["cnt"] if today_row else 0
            total_msgs = conn.execute(
                "SELECT COUNT(*) as cnt FROM messages WHERE user_id=?", (user_id,)
            ).fetchone()["cnt"]
            d["total_messages"] = total_msgs
            return d

    def get_referral_tree(self, referrer_id: int) -> list:
        """Referrer taklif qilgan barcha odamlar ro'yxati."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT rh.referred_id, rh.bonus_amount, rh.created_at,
                          u.full_name, u.username, u.is_active
                   FROM referral_history rh
                   JOIN users u ON rh.referred_id = u.user_id
                   WHERE rh.referrer_id=?
                   ORDER BY rh.created_at DESC""",
                (referrer_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def search_users(self, query: str) -> list:
        """Username, full_name yoki user_id bo'yicha qidirish."""
        with self._conn() as conn:
            like = f"%{query}%"
            rows = conn.execute(
                """SELECT user_id, username, full_name, is_active, is_vip, subscription_end, balance
                   FROM users
                   WHERE CAST(user_id AS TEXT) LIKE ? OR username LIKE ? OR full_name LIKE ?
                   ORDER BY id DESC LIMIT 20""",
                (like, like, like)
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── TRIAL (SINOV) TIZIMI ────────────────────────────────────────────────

    def get_trial_count(self, user_id: int) -> int:
        """Obunasiz user nechta trial xabar yuborgan."""
        val = self.get_setting(f"trial_{user_id}", "0")
        try:
            return int(val)
        except Exception:
            return 0

    def increment_trial(self, user_id: int) -> int:
        """Trial hisobini oshiradi va yangi qiymatni qaytaradi."""
        count = self.get_trial_count(user_id) + 1
        self.set_setting(f"trial_{user_id}", str(count))
        return count

    def reset_trial(self, user_id: int):
        """Trial hisobini nolga qaytaradi (obuna olgandan keyin)."""
        with self._conn() as conn:
            conn.execute("DELETE FROM settings WHERE key=?", (f"trial_{user_id}",))
