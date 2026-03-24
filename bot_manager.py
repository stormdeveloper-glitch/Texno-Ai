"""
bot_manager.py — Railway Volume da bots.json orqali
ko'p botlarni real vaqtda boshqarish tizimi.

bots.json strukturasi:
{
  "bots": [
    {
      "token": "123456:ABC...",
      "name": "MyBot",
      "owner_id": 123456789,
      "owner_username": "stormdev",
      "created_at": "2026-01-01T00:00:00",
      "status": "running"
    }
  ]
}
"""

import json
import os
import asyncio
import logging
import threading
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

logger = logging.getLogger(__name__)

BOTS_FILE = os.path.join(os.getenv("VOLUME_PATH", "/app/data"), "bots.json")

_running_bots: dict[str, Application] = {}
_lock = threading.Lock()


# ─── ENV HELPERS (circular import bo'lmasligi uchun config ishlatmaymiz) ───────

def _get_admin_username() -> str:
    return os.getenv("ADMIN_USERNAME", "admin")

def _get_vip_admin_username() -> str:
    return os.getenv("VIP_ADMIN_USERNAME", "admin")

def _get_sub_price() -> int:
    return int(os.getenv("SUBSCRIPTION_PRICE_UZS", "19999"))

def _get_vip_price() -> int:
    return int(os.getenv("VIP_PRICE_UZS", "39999"))


# ─── JSON HELPERS ─────────────────────────────────────────────────────────────

def _read_bots() -> list:
    if not os.path.exists(BOTS_FILE):
        return []
    try:
        with open(BOTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("bots", [])
    except Exception as e:
        logger.error(f"bots.json o'qishda xato: {e}")
        return []


def _write_bots(bots: list) -> None:
    os.makedirs(os.path.dirname(BOTS_FILE), exist_ok=True)
    try:
        with open(BOTS_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"bots": bots, "updated_at": datetime.utcnow().isoformat()},
                f, ensure_ascii=False, indent=2
            )
    except Exception as e:
        logger.error(f"bots.json yozishda xato: {e}")


def add_bot_record(token: str, name: str, owner_id: int, owner_username: str = "") -> bool:
    bots = _read_bots()
    if any(b["token"] == token for b in bots):
        return False
    bots.append({
        "token": token,
        "name": name,
        "owner_id": owner_id,
        "owner_username": owner_username,
        "created_at": datetime.utcnow().isoformat(),
        "status": "stopped"
    })
    _write_bots(bots)
    return True


def remove_bot_record(token: str) -> bool:
    bots = _read_bots()
    new_bots = [b for b in bots if b["token"] != token]
    if len(new_bots) == len(bots):
        return False
    _write_bots(new_bots)
    return True


def update_bot_status(token: str, status: str) -> None:
    bots = _read_bots()
    for b in bots:
        if b["token"] == token:
            b["status"] = status
            break
    _write_bots(bots)


def get_all_bots() -> list:
    return _read_bots()


def get_bot_record(token: str) -> Optional[dict]:
    for b in _read_bots():
        if b["token"] == token:
            return b
    return None


# ─── HANDLER FACTORY ──────────────────────────────────────────────────────────

def _make_start_handler(owner_id: int, owner_username: str):
    """
    Har bir yangi bot uchun /start handler yaratadi.
    owner_id/owner_username — token yuborgan kishi (bu botning admini).
    To'lovlar shu odamga yo'naltiriladi.
    """
    async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user   = update.effective_user
        bot_me = await context.bot.get_me()

        sub_price     = _get_sub_price()
        vip_price     = _get_vip_price()
        admin_uname   = owner_username or _get_admin_username()
        vip_uname     = _get_vip_admin_username()

        buttons = [
            [InlineKeyboardButton(
                f"⭐ Oddiy — {sub_price:,} so'm/oy",
                url=f"https://t.me/{admin_uname}"
            )],
            [InlineKeyboardButton(
                f"👑 VIP — {vip_price:,} so'm/oy",
                url=f"https://t.me/{vip_uname}"
            )],
            [InlineKeyboardButton(
                "📸 To'lov cheki yuborish",
                callback_data="sub_send_check"
            )],
        ]

        await update.message.reply_text(
            f"👋 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
            f"🤖 Men <b>{bot_me.first_name}</b> — AI yordamchisiman!\n\n"
            f"✨ <b>Imkoniyatlar:</b>\n"
            f"📝 GPT, Claude, Gemini va boshqa modellar\n"
            f"🖼 20+ tasvir modeli\n"
            f"💬 Suhbat tarixini eslab qoladi\n"
            f"🎵 Musiqa va audio yaratish\n\n"
            f"💰 <b>Tariflar:</b>\n"
            f"⭐ Oddiy — <b>{sub_price:,} so'm/oy</b>\n"
            f"👑 VIP — <b>{vip_price:,} so'm/oy</b>\n\n"
            f"👇 Obuna bo'lish uchun pastdagi tugmani bosing:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    return start_handler


def _make_payment_callback(owner_id: int, owner_username: str):
    """To'lov cheki bosqichi."""
    async def payment_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data != "sub_send_check":
            return

        sub_price   = _get_sub_price()
        vip_price   = _get_vip_price()
        admin_uname = owner_username or _get_admin_username()
        vip_uname   = _get_vip_admin_username()

        buttons = [
            [InlineKeyboardButton("⭐ Oddiy admin", url=f"https://t.me/{admin_uname}")],
            [InlineKeyboardButton("👑 VIP admin",   url=f"https://t.me/{vip_uname}")],
        ]

        await query.edit_message_text(
            f"💳 <b>To'lov qilish tartibi</b>\n\n"
            f"📌 <b>Narxlar:</b>\n"
            f"• ⭐ Oddiy: <b>{sub_price:,} so'm/oy</b>\n"
            f"• 👑 VIP: <b>{vip_price:,} so'm/oy</b>\n\n"
            f"📋 <b>Qadamlar:</b>\n"
            f"1️⃣ Admin kartasiga pul o'tkazing\n"
            f"2️⃣ To'lov chekini (screenshot) adminga yuboring\n"
            f"3️⃣ Admin 5–15 daqiqada faollashtiradi ✅\n\n"
            f"👇 Admin bilan bog'laning:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    return payment_cb


# ─── BOT LIFECYCLE ────────────────────────────────────────────────────────────

async def _launch_bot_async(token: str, name: str) -> bool:
    with _lock:
        if token in _running_bots:
            logger.info(f"Bot allaqachon ishlamoqda: {name}")
            return True

    rec            = get_bot_record(token)
    owner_id       = rec["owner_id"]              if rec else 0
    owner_username = rec.get("owner_username", "") if rec else ""

    try:
        app = Application.builder().token(token).build()

        app.add_handler(CommandHandler("start", _make_start_handler(owner_id, owner_username)))
        app.add_handler(CallbackQueryHandler(
            _make_payment_callback(owner_id, owner_username),
            pattern="^sub_send_check$"
        ))

        loop = asyncio.new_event_loop()

        def run_in_thread():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_run_app(app))

        t = threading.Thread(target=run_in_thread, daemon=True, name=f"bot-{name}")
        t.start()

        with _lock:
            _running_bots[token] = app

        update_bot_status(token, "running")
        logger.info(f"✅ Bot ishga tushdi: {name} (owner_id={owner_id})")
        return True

    except Exception as e:
        logger.error(f"❌ Bot ishga tushmadi ({name}): {e}")
        update_bot_status(token, "error")
        return False


async def _run_app(app: Application):
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    while True:
        await asyncio.sleep(3600)


async def stop_bot_async(token: str) -> bool:
    with _lock:
        app = _running_bots.pop(token, None)
    if not app:
        return False
    try:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        update_bot_status(token, "stopped")
        return True
    except Exception as e:
        logger.error(f"Bot to'xtatishda xato: {e}")
        return False


async def launch_bot(token: str, name: str) -> bool:
    return await _launch_bot_async(token, name)


async def restart_all_running_bots() -> int:
    bots  = _read_bots()
    count = 0
    for b in bots:
        if b.get("status") == "running":
            logger.info(f"Tiklash: {b['name']}")
            ok = await _launch_bot_async(b["token"], b["name"])
            if ok:
                count += 1
    logger.info(f"✅ {count} ta bot tiklandi.")
    return count


def get_running_count() -> int:
    with _lock:
        return len(_running_bots)


def is_running(token: str) -> bool:
    with _lock:
        return token in _running_bots
