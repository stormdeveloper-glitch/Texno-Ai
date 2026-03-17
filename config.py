import os
import sys

# Local dev: .env faylidan o'qish (Railway da bu fayl bo'lmaydi, lekin zarar qilmaydi)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Config:
    # ── Bot ──────────────────────────────────────────
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    
    # ── OpenAI ───────────────────────────────────────
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    # ── Admin ────────────────────────────────────────
    _admin_ids_raw = os.getenv("ADMIN_IDS", "")
    ADMIN_IDS = list(map(int, _admin_ids_raw.split(","))) if _admin_ids_raw else []
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    
    # ── Majburiy kanal/guruh obunasi ─────────────────
    # Kanal ID lari: @username uchun "-100..." formatda yoki "@username"
    # Bo'sh qoldiring agar kanal tekshiruvi shart emas bo'lsa: REQUIRED_CHANNEL_IDS=
    _ch_ids = os.getenv("REQUIRED_CHANNEL_IDS", "")
    REQUIRED_CHANNEL_IDS = [x.strip() for x in _ch_ids.split(",") if x.strip()] if _ch_ids else []

    # Kanal nomlari (foydalanuvchiga ko'rsatiladi)
    _ch_names = os.getenv("REQUIRED_CHANNEL_NAMES", "")
    REQUIRED_CHANNEL_NAMES = [x.strip() for x in _ch_names.split(",") if x.strip()] if _ch_names else []

    # Kanal invite/public linklari (https://t.me/... yoki https://t.me/+...)
    _ch_links = os.getenv("REQUIRED_CHANNEL_LINKS", "")
    REQUIRED_CHANNEL_LINKS = [x.strip() for x in _ch_links.split("|") if x.strip()] if _ch_links else []

    # ── To'lov — karta ma'lumotlari botda ko'rsatilmaydi,
    # admin o'zi lichkada xabar qiladi
    # ──────────────────────────────────────────────────
    
    # ── Obuna ────────────────────────────────────────
    SUBSCRIPTION_PRICE = 5        # USD
    SUBSCRIPTION_DAYS = 30
    DAILY_MESSAGE_LIMIT = 100
    
    # ── Database ─────────────────────────────────────
    # Railway da /app papkasida saqlanadi (persistent volume kerak emas SQLite uchun)
    DB_PATH = os.getenv("DB_PATH", "/app/bot_database.db")

    @classmethod
    def validate(cls):
        """Majburiy o'zgaruvchilarni tekshiradi"""
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
        
        print("✅ Config tekshirildi — hammasi joyida!")