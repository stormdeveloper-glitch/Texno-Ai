import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    # ── Bot ──────────────────────────────────────────────────────────────────
    BOT_TOKEN        = os.getenv("BOT_TOKEN", "")

    # ── OpenAI ───────────────────────────────────────────────────────────────
    OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")

    # ── Adminlar (vergul bilan: 123,456) ─────────────────────────────────────
    _raw_ids         = os.getenv("ADMIN_IDS", "")
    ADMIN_IDS        = [int(x) for x in _raw_ids.split(",") if x.strip().isdigit()]
    ADMIN_USERNAME   = os.getenv("ADMIN_USERNAME", "admin")

    # ── Obuna ────────────────────────────────────────────────────────────────
    SUBSCRIPTION_DAYS        = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
    DAILY_MESSAGE_LIMIT      = int(os.getenv("DAILY_MESSAGE_LIMIT", "50"))
    SUBSCRIPTION_PRICE_UZS   = int(os.getenv("SUBSCRIPTION_PRICE_UZS", "19999"))

    # ── Majburiy kanallar — DB dan boshqariladi (admin panel orqali) ─────────
    # Bu yerda bo'sh, chunki ular bazada saqlanadi va /addchannel orqali qo'shiladi

    # ── Volume (Railway persistent storage) ──────────────────────────────────
    # Railway volumeni /data ga mount qiling
    VOLUME_PATH = os.getenv("VOLUME_PATH", "/data")
    DB_PATH     = os.path.join(VOLUME_PATH, "bot_database.db")

    # ── Muddati tugashiga necha kun qolsa ogohlantirish ──────────────────────
    EXPIRY_WARN_DAYS = 3

    @classmethod
    def validate(cls):
        errors = []
        if not cls.BOT_TOKEN:
            errors.append("❌ BOT_TOKEN o'rnatilmagan!")
        if not cls.OPENAI_API_KEY:
            errors.append("❌ OPENAI_API_KEY o'rnatilmagan!")
        if not cls.ADMIN_IDS:
            errors.append("❌ ADMIN_IDS o'rnatilmagan!")

        if errors:
            for e in errors:
                print(e)
            sys.exit(1)

        import os as _os
        _os.makedirs(cls.VOLUME_PATH, exist_ok=True)
        print(f"✅ Config OK | DB: {cls.DB_PATH} | Adminlar: {cls.ADMIN_IDS}")
