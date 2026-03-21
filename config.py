import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    BOT_TOKEN        = os.getenv("BOT_TOKEN", "")
    OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")

    _raw_ids         = os.getenv("ADMIN_IDS", "")
    ADMIN_IDS        = [int(x) for x in _raw_ids.split(",") if x.strip().isdigit()]
    ADMIN_USERNAME   = os.getenv("ADMIN_USERNAME", "admin")

    SUBSCRIPTION_DAYS      = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
    SUBSCRIPTION_PRICE_UZS = int(os.getenv("SUBSCRIPTION_PRICE_UZS", "19999"))
    VIP_PRICE_UZS          = int(os.getenv("VIP_PRICE_UZS", "39999"))

    DAILY_LIMIT_NORMAL = int(os.getenv("DAILY_LIMIT_NORMAL", "5"))
    DAILY_LIMIT_VIP    = int(os.getenv("DAILY_LIMIT_VIP", "50"))
    DAILY_MESSAGE_LIMIT = DAILY_LIMIT_NORMAL

    # ── Trial (sinov) — obunasiz userlarga bepul xabarlar ────────────────────
    TRIAL_LIMIT = int(os.getenv("TRIAL_LIMIT", "5"))

    REFERRAL_BONUS_UZS = int(os.getenv("REFERRAL_BONUS_UZS", "200"))

    # ── VIP admin — faqat shu admin VIP to'lovlarini ko'radi va tasdiqlaydi ──
    VIP_ADMIN_USERNAME = os.getenv("VIP_ADMIN_USERNAME", "Teacher_texnoo")
    _vip_admin_id      = os.getenv("VIP_ADMIN_ID", "")
    VIP_ADMIN_ID       = int(_vip_admin_id) if _vip_admin_id.strip().isdigit() else None

    VOLUME_PATH = os.getenv("VOLUME_PATH", "/app/data")
    DB_PATH     = os.path.join(VOLUME_PATH, "bot_database.db")

    EXPIRY_WARN_DAYS = 3

    @classmethod
    def validate(cls):
        errors = []
        if not cls.BOT_TOKEN:      errors.append("❌ BOT_TOKEN o'rnatilmagan!")
        if not cls.OPENAI_API_KEY: errors.append("❌ OPENAI_API_KEY o'rnatilmagan!")
        if not cls.ADMIN_IDS:      errors.append("❌ ADMIN_IDS o'rnatilmagan!")
        if errors:
            for e in errors: print(e)
            sys.exit(1)
        import os as _os
        _os.makedirs(cls.VOLUME_PATH, exist_ok=True)
        print(f"✅ Config OK | Adminlar: {cls.ADMIN_IDS}")
        print(f"💰 Narxlar: Oddiy={cls.SUBSCRIPTION_PRICE_UZS} | VIP={cls.VIP_PRICE_UZS}")
        print(f"📊 Limitlar: Oddiy={cls.DAILY_LIMIT_NORMAL} | VIP={cls.DAILY_LIMIT_VIP}")
        print(f"👑 VIP admin: @{cls.VIP_ADMIN_USERNAME} (ID: {cls.VIP_ADMIN_ID})")
