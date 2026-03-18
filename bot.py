import logging
import re
from datetime import datetime
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TZ = pytz.timezone("Asia/Tashkent")

def now_tashkent() -> datetime:
    return datetime.now(TZ)

from database import Database
from config import Config
from openai import OpenAI

# ─── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

Config.validate()

db     = Database()
client = OpenAI(api_key=Config.OPENAI_API_KEY)

# ─── SYSTEM PROMPT ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Siz "Texno Ai" nomli AI dasturlash o'qituvchisisiz.

👨‍💻 Shaxsiyat:
- Ismingiz: Texno Ai
- Siz professional dasturchi va o'qituvchisiz
- Har doim iliq, samimiy va rag'batlantiruvchi muloqot qilasiz
- Murakkab tushunchalarni oddiy, tushunarli tilda tushuntirasiz

👨‍💻 Dasturchilar:
- @Teacher_texnoo va @Stormdev_coder

🎯 Qoidalar:
- Foydalanuvchilarga dasturlashda yordam bering (Python, JavaScript, Java, C++, va boshqa tillar)
- Kodni har doim ✅ ishlaydigan holda, izohlar bilan yozing
- Xatolarni tushuntirib, to'g'ri yo'l ko'rsating
- Savollarga to'liq va aniq javob bering
- Har bir javobda motivatsion gap qo'shing
- O'zbek, Rus yoki Ingliz tilida muloqot qiling (foydalanuvchi qaysi tilda yozsa)

💡 Uslub:
- Emoji'lar bilan hayotli va qiziqarli yozing
- Kodlarni ``` ``` ichiga joylashtiring
- Bosqichma-bosqich tushuntiring
- "Siz uddalaysiz! 💪" kabi rag'batlantiruvchi iboralar ishlating

🏫 Asosiy yo'nalishlar:
- Web dasturlash (HTML, CSS, JS, React, Vue)
- Backend (Python, Node.js, Django, FastAPI)
- Ma'lumotlar bazasi (SQL, MongoDB, PostgreSQL)
- Algoritmlar va ma'lumotlar strukturasi
- DevOps va deployment
- Telegram bot yaratish
- API integratsiya

Har doim: "Savolingiz bormi? Men yordam berishga tayyorman! 🚀" degan ruhda bo'ling."""

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in Config.ADMIN_IDS


async def check_channel_membership(bot, user_id: int) -> list:
    """
    Foydalanuvchi obuna bo'lmagan kanallar ro'yxatini qaytaradi.
    Bo'sh ro'yxat = hammaga obuna.
    """
    channels = db.get_channels()
    not_joined = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch["channel_id"], user_id=user_id)
            if member.status in ("left", "kicked", "banned"):
                not_joined.append(ch)
        except Exception as e:
            logger.warning(f"Kanal tekshirishda xatolik {ch['channel_id']}: {e}")
            not_joined.append(ch)
    return not_joined


def channel_keyboard(not_joined: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in not_joined:
        buttons.append([InlineKeyboardButton(f"📢 {ch['name']}", url=ch["link"])])
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(buttons)


def sub_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"💰 Obuna bo'lish ({Config.SUBSCRIPTION_PRICE_UZS:,} so'm/oy)",
            url=f"https://t.me/{Config.ADMIN_USERNAME}"
        )],
        [InlineKeyboardButton("📸 To'lov chekini yuborish", callback_data="send_check")],
    ])


def escape_md(text: str) -> str:
    """MarkdownV2 uchun maxsus belgilarni himoyalash."""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', text)


async def safe_send(message, text: str, **kwargs):
    """Avval Markdown bilan yuboradi, xato bo'lsa oddiy matn bilan."""
    try:
        if len(text) > 4096:
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await message.reply_text(part, parse_mode=ParseMode.MARKDOWN, **kwargs)
        else:
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, **kwargs)
    except Exception:
        # Markdown xato bo'lsa oddiy matn
        try:
            await message.reply_text(text, **kwargs)
        except Exception as e:
            logger.error(f"safe_send error: {e}")

# ─── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.full_name)

    # Admin
    if is_admin(user.id):
        await update.message.reply_text(
            f"👑 <b>Xush kelibsiz, Admin!</b>\n\n"
            f"🔧 <b>Admin buyruqlari:</b>\n"
            f"/pending — Kutayotgan to'lovlar\n"
            f"/users — Barcha foydalanuvchilar\n"
            f"/broadcast — Hammaga xabar\n"
            f"/stats — Statistika\n"
            f"/addchannel — Kanal qo'shish\n"
            f"/delchannel — Kanal o'chirish\n"
            f"/channels — Kanallar ro'yxati\n"
            f"/setlimit — Kunlik limit o'zgartirish\n"
            f"/activate — Obunani qo'lda faollashtirish\n"
            f"/deactivate — Obunani o'chirish",
            parse_mode=ParseMode.HTML
        )
        return

    # Majburiy kanal tekshirish
    not_joined = await check_channel_membership(context.bot, user.id)
    if not_joined:
        await update.message.reply_text(
            f"👋 Salom, <b>{user.first_name}</b>!\n\n"
            f"🤖 Men <b>Texno Ai</b> — AI dasturlash o'qituvchisi!\n\n"
            f"📢 Botdan foydalanish uchun avval quyidagi kanallarga obuna bo'ling:",
            parse_mode=ParseMode.HTML,
            reply_markup=channel_keyboard(not_joined)
        )
        return

    if db.is_active_subscriber(user.id):
        info  = db.get_subscription_info(user.id)
        limit = int(db.get_setting("daily_limit", str(Config.DAILY_MESSAGE_LIMIT)))
        daily = db.get_daily_count(user.id)
        await update.message.reply_text(
            f"🎉 Xush kelibsiz, <b>{user.first_name}</b>!\n\n"
            f"🤖 Men <b>Texno Ai</b> — sizning shaxsiy dasturlash o'qituvchingizman!\n\n"
            f"📅 Obuna: <b>{info['days_left']} kun</b> qolgan\n"
            f"💬 Bugungi xabarlar: <b>{daily}/{limit}</b>\n\n"
            f"Istalgan savol bering, men 24/7 yordam berishga tayyorman!\n"
            f"📚 /help — imkoniyatlar | /status — obuna holati",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            f"👋 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
            f"🤖 Men <b>Texno Ai</b> — AI dasturlash o'qituvchisi!\n\n"
            f"📚 <b>Nima qila olaman?</b>\n"
            f"• Python, JS, Java, C++ va boshqa tillarda yordam\n"
            f"• Kod yozish, xatolarni tuzatish\n"
            f"• Loyiha yaratishda qo'llab-quvvatlash\n"
            f"• 24/7 darslar va tushuntirishlar\n\n"
            f"💰 <b>Narx:</b> Oyiga {Config.SUBSCRIPTION_PRICE_UZS:,} so'm\n\n"
            f"1️⃣ <b>Obuna bo'lish</b> tugmasini bosing\n"
            f"2️⃣ To'lovdan so'ng chek yuboring ⚡",
            parse_mode=ParseMode.HTML,
            reply_markup=sub_keyboard()
        )

# ─── /help ────────────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        not_joined = await check_channel_membership(context.bot, user.id)
        if not_joined:
            await update.message.reply_text(
                "📢 Avval kanallarga obuna bo'ling:",
                reply_markup=channel_keyboard(not_joined)
            )
            return
        if not db.is_active_subscriber(user.id):
            await update.message.reply_text(
                "🔒 Bu funksiya faqat obunachilarga mavjud!",
                reply_markup=sub_keyboard()
            )
            return

    await update.message.reply_text(
        "📖 <b>Men nima qila olaman?</b>\n\n"
        "💻 <b>Dasturlash tillari:</b>\n"
        "• Python, JavaScript, TypeScript\n"
        "• Java, C, C++, C#\n"
        "• HTML, CSS, React, Vue\n"
        "• SQL, MongoDB, PostgreSQL\n\n"
        "🛠 <b>Amaliy yordam:</b>\n"
        "• Kod yozish va tushuntirish\n"
        "• Bug topish va tuzatish\n"
        "• Algoritmlar va mantiq\n"
        "• Telegram bot, API, Web\n\n"
        "📌 <b>Buyruqlar:</b>\n"
        "/status — obuna holatim\n"
        "/clear — suhbat tarixini tozalash\n\n"
        "✍️ Shunchaki savol yozing — men javob beraman! 🚀",
        parse_mode=ParseMode.HTML
    )

# ─── /status ──────────────────────────────────────────────────────────────────

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    info = db.get_subscription_info(user.id)
    daily = db.get_daily_count(user.id)
    limit = int(db.get_setting("daily_limit", str(Config.DAILY_MESSAGE_LIMIT)))

    if info["is_active"]:
        end_str = info["end_date"].strftime("%d.%m.%Y") if info["end_date"] else "—"
        await update.message.reply_text(
            f"📊 <b>Sizning holatiz:</b>\n\n"
            f"✅ Obuna: <b>Faol</b>\n"
            f"📅 Tugash sanasi: <b>{end_str}</b>\n"
            f"⏳ Qolgan kunlar: <b>{info['days_left']} kun</b>\n\n"
            f"💬 Bugungi xabarlar: <b>{daily}/{limit}</b>",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            f"❌ <b>Obuna yo'q</b>\n\n"
            f"Botdan foydalanish uchun obuna bo'ling:",
            parse_mode=ParseMode.HTML,
            reply_markup=sub_keyboard()
        )

# ─── /clear ───────────────────────────────────────────────────────────────────

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.clear_history(update.effective_user.id)
    await update.message.reply_text("🗑 Suhbat tarixi tozalandi! Yangi suhbat boshlash mumkin. 🚀")

# ─── CALLBACK QUERY ───────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # answer() ni shu yerda CHAQIRMAYMIZ — har bir branch o'zi chaqiradi
    user  = query.from_user

    # ── Kanal obunasini tekshirish ──
    if query.data == "check_sub":
        await query.answer()
        not_joined = await check_channel_membership(context.bot, user.id)
        if not_joined:
            await query.edit_message_text(
                "❌ Hali ham quyidagi kanallarga obuna bo'lmadingiz:",
                reply_markup=channel_keyboard(not_joined)
            )
        else:
            if db.is_active_subscriber(user.id):
                await query.edit_message_text(
                    "✅ Kanallarga obunasiz va botdan foydalanishingiz mumkin!\n\n"
                    "Savolingizni yozing 👇"
                )
            else:
                await query.edit_message_text(
                    "✅ Kanallarga obuna bo'ldingiz!\n\n"
                    "Endi botdan foydalanish uchun obuna sotib oling:",
                    reply_markup=sub_keyboard()
                )
        return

    # ── Chek yuborish ──
    if query.data == "send_check":
        await query.answer()
        db.set_setting(f"waiting_check_{user.id}", "1")
        context.user_data["waiting_check"] = True
        await query.edit_message_text(
            "📸 <b>To'lov chekini yuboring:</b>\n\n"
            "To'lov cheki (screenshot yoki rasmini) shu chatga yuboring.\n\n"
            "📌 To'lov ma'lumotlari:\n"
            f"• Narx: <b>{Config.SUBSCRIPTION_PRICE_UZS:,} so'm/oy</b>\n"
            f"• Admin: @{Config.ADMIN_USERNAME}\n\n"
            "⚡ Admin 5–15 daqiqa ichida faollashtiradi!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")
            ]])
        )
        return

    if query.data == "cancel":
        await query.answer()
        db.set_setting(f"waiting_check_{user.id}", "0")
        context.user_data.pop("waiting_check", None)
        await query.edit_message_text("❌ Bekor qilindi.\n\n/start — bosh menyuga qaytish")
        return

    # ── Admin: tasdiqlash ──
    if query.data.startswith("approve_"):
        if not is_admin(user.id):
            await query.answer("❌ Siz admin emassiz!", show_alert=True)
            return

        parts = query.data.split("_")
        try:
            target_id  = int(parts[1])
            payment_id = int(parts[2]) if len(parts) > 2 else None
        except (IndexError, ValueError):
            await query.answer("❌ Xato format!", show_alert=True)
            return

        # Obunani faollashtirish
        end_date = db.activate_subscription(target_id)
        if payment_id:
            db.update_payment_status(payment_id, "approved")

        end_str = datetime.fromisoformat(end_date).strftime("%d.%m.%Y") if end_date else "—"
        ts = now_tashkent().strftime("%d.%m.%Y %H:%M")

        # Admin xabarini yangilash
        old_caption = query.message.caption or ""
        new_caption = (
            old_caption + "\n\n"
            f"✅ TASDIQLANDI\n"
            f"👤 Admin: @{user.username or user.full_name}\n"
            f"🕐 {ts} (Toshkent)\n"
            f"📅 Obuna: {end_str} gacha"
        )
        if len(new_caption) > 1024:
            new_caption = (
                f"✅ #{target_id} TASDIQLANDI\n"
                f"📅 {end_str} gacha | 🕐 {ts}"
            )

        caption_updated = False
        try:
            await query.edit_message_caption(
                caption=new_caption,
                parse_mode=None,
                reply_markup=None
            )
            caption_updated = True
        except Exception as e:
            logger.warning(f"edit_message_caption (approve) error: {e}")

        # Bir marta answer() — caption yangilansa oddiy, bo'lmasa alert
        if caption_updated:
            await query.answer(f"✅ Tasdiqlandi! {end_str} gacha")
        else:
            await query.answer(f"✅ #{target_id} tasdiqlandi! Obuna: {end_str} gacha", show_alert=True)

        # Foydalanuvchiga xabar
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    f"🎉 <b>Tabriklaymiz!</b>\n\n"
                    f"✅ Obunangiz faollashtirildi!\n"
                    f"📅 Tugash sanasi: <b>{end_str}</b>\n\n"
                    f"🤖 Endi <b>Texno Ai</b>dan to'liq foydalanishingiz mumkin!\n"
                    f"💬 Istalgan savolingizni yuboring — men yordam berishga tayyorman! 🚀"
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"approve notify error (user {target_id}): {e}")
        return

    # ── Admin: rad etish ──
    if query.data.startswith("reject_"):
        if not is_admin(user.id):
            await query.answer("❌ Siz admin emassiz!", show_alert=True)
            return

        parts = query.data.split("_")
        try:
            target_id  = int(parts[1])
            payment_id = int(parts[2]) if len(parts) > 2 else None
        except (IndexError, ValueError):
            await query.answer("❌ Xato format!", show_alert=True)
            return

        if payment_id:
            db.update_payment_status(payment_id, "rejected")

        ts = now_tashkent().strftime("%d.%m.%Y %H:%M")
        old_caption = query.message.caption or ""
        new_caption = (
            old_caption + "\n\n"
            f"❌ RAD ETILDI\n"
            f"👤 Admin: @{user.username or user.full_name}\n"
            f"🕐 {ts} (Toshkent)"
        )
        if len(new_caption) > 1024:
            new_caption = f"❌ #{target_id} RAD ETILDI | 🕐 {ts}"

        caption_updated = False
        try:
            await query.edit_message_caption(
                caption=new_caption,
                parse_mode=None,
                reply_markup=None
            )
            caption_updated = True
        except Exception as e:
            logger.warning(f"edit_message_caption (reject) error: {e}")

        if caption_updated:
            await query.answer(f"❌ Rad etildi!")
        else:
            await query.answer(f"❌ #{target_id} rad etildi!", show_alert=True)

        # Foydalanuvchiga xabar
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    f"❌ <b>To'lovingiz tasdiqlanmadi.</b>\n\n"
                    f"Sabab: chek aniq ko'rinmaydi yoki summa noto'g'ri.\n\n"
                    f"📞 Admin bilan bog'laning: @{Config.ADMIN_USERNAME}\n\n"
                    f"Qayta urinib ko'ring:"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=sub_keyboard()
            )
        except Exception as e:
            logger.error(f"reject notify error (user {target_id}): {e}")
        return

    # Noma'lum callback
    await query.answer()

# ─── XABAR HANDLER ────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    message = update.message

    # ── Rasm: to'lov cheki ──
    if message.photo:
        # waiting_check ni ham DB dan, ham user_data dan tekshiramiz
        waiting = (
            context.user_data.get("waiting_check")
            or db.get_setting(f"waiting_check_{user.id}") == "1"
        )
        if waiting:
            # Holatni tozalaymiz
            context.user_data.pop("waiting_check", None)
            db.set_setting(f"waiting_check_{user.id}", "0")

            file_id    = message.photo[-1].file_id
            payment_id = db.add_payment(user.id, file_id)

            # Toshkent vaqti
            ts = now_tashkent().strftime("%d.%m.%Y  %H:%M:%S")

            await message.reply_text(
                "✅ <b>Chek qabul qilindi!</b>\n\n"
                "⏳ Admin tekshirmoqda... (5–15 daqiqa)\n\n"
                "Tasdiqlangandan so'ng sizga xabar yuboriladi! 📬",
                parse_mode=ParseMode.HTML
            )

            caption = (
                f"💳 <b>Yangi to'lov cheki!</b>\n"
                f"{'─' * 28}\n"
                f"👤 Ismi: <b>{user.full_name}</b>\n"
                f"🔗 Username: @{user.username or '—'}\n"
                f"🆔 User ID: <code>{user.id}</code>\n"
                f"💰 Summa: <b>{Config.SUBSCRIPTION_PRICE_UZS:,} so'm</b>\n"
                f"🕐 Vaqt: <b>{ts} (Toshkent)</b>\n"
                f"🗂 To'lov №: <code>{payment_id}</code>\n"
                f"{'─' * 28}\n"
                f"⬇️ Tasdiqlash yoki rad etish:"
            )
            for admin_id in Config.ADMIN_IDS:
                try:
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=file_id,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{user.id}_{payment_id}"),
                            InlineKeyboardButton("❌ Rad etish",  callback_data=f"reject_{user.id}_{payment_id}"),
                        ]])
                    )
                except Exception as e:
                    logger.error(f"Admin notify error: {e}")
            return

    # ── Majburiy kanal tekshirish (admindan tashqari) ──
    if not is_admin(user.id):
        not_joined = await check_channel_membership(context.bot, user.id)
        if not_joined:
            await message.reply_text(
                "📢 Avval quyidagi kanallarga obuna bo'ling:",
                reply_markup=channel_keyboard(not_joined)
            )
            return

    # ── Obuna tekshirish ──
    if not is_admin(user.id) and not db.is_active_subscriber(user.id):
        await message.reply_text(
            "🔒 <b>Obuna kerak!</b>\n\n"
            f"Bu xizmatdan foydalanish uchun oylik {Config.SUBSCRIPTION_PRICE_UZS:,} so'm obuna talab qilinadi.",
            parse_mode=ParseMode.HTML,
            reply_markup=sub_keyboard()
        )
        return

    # ── Matn tekshirish ──
    text = message.text
    if not text:
        await message.reply_text("💬 Iltimos, matn yozing!")
        return

    # ── Kunlik limit (admindan tashqari) ──
    if not is_admin(user.id):
        limit = int(db.get_setting("daily_limit", str(Config.DAILY_MESSAGE_LIMIT)))
        daily = db.get_daily_count(user.id)
        if daily >= limit:
            await message.reply_text(
                f"⏳ <b>Kunlik limit tugadi!</b>\n\n"
                f"Bugun <b>{limit} ta</b> xabar yuborish mumkin edi.\n"
                f"Ertaga soat 00:00 da yangilanadi. Sabr qiling! 🙏\n\n"
                f"💡 Limitni oshirish uchun adminga murojaat qiling:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        f"💰 Obuna ({Config.SUBSCRIPTION_PRICE_UZS:,} so'm/oy)",
                        url=f"https://t.me/{Config.ADMIN_USERNAME}"
                    )
                ]])
            )
            return

    # ── AI javob ──
    history = db.get_history(user.id, limit=20)
    history.append({"role": "user", "content": text})

    typing = await message.reply_text("⌨️ Yozmoqdaman...")
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
            max_tokens=1500,
            temperature=0.7
        )
        ai_reply = response.choices[0].message.content

        db.add_history(user.id, "user", text)
        db.add_history(user.id, "assistant", ai_reply)
        db.log_message(user.id, text, ai_reply)
        if not is_admin(user.id):
            db.increment_daily(user.id)

        await typing.delete()
        await safe_send(message, ai_reply)

    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        await typing.delete()
        await message.reply_text(
            "⚠️ Xatolik yuz berdi. Iltimos qayta urinib ko'ring.\n"
            "Agar muammo davom etsa, /start bosing."
        )

# ─── ADMIN BUYRUQLARI ─────────────────────────────────────────────────────────

async def admin_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    payments = db.get_pending_payments()
    if not payments:
        await update.message.reply_text("📭 Kutayotgan to'lovlar yo'q!")
        return
    await update.message.reply_text(f"⏳ <b>Kutayotgan to'lovlar: {len(payments)} ta</b>", parse_mode=ParseMode.HTML)
    for p in payments:
        try:
            # created_at ni Toshkent vaqtiga o'tkazish
            raw_dt = datetime.fromisoformat(p["created_at"])
            local_dt = raw_dt.astimezone(TZ) if raw_dt.tzinfo else TZ.localize(raw_dt)
            ts_str = local_dt.strftime("%d.%m.%Y  %H:%M:%S")
        except Exception:
            ts_str = p["created_at"]

        caption = (
            f"💳 <b>To'lov cheki</b>\n"
            f"{'─' * 28}\n"
            f"👤 Ismi: <b>{p['full_name']}</b>\n"
            f"🔗 Username: @{p['username'] or '—'}\n"
            f"🆔 User ID: <code>{p['user_id']}</code>\n"
            f"💰 Summa: <b>{Config.SUBSCRIPTION_PRICE_UZS:,} so'm</b>\n"
            f"🕐 Vaqt: <b>{ts_str} (Toshkent)</b>\n"
            f"🗂 To'lov №: <code>{p['id']}</code>"
        )
        await update.message.reply_photo(
            photo=p["file_id"],
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{p['user_id']}_{p['id']}"),
                InlineKeyboardButton("❌ Rad etish",  callback_data=f"reject_{p['user_id']}_{p['id']}"),
            ]])
        )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    s = db.get_stats()
    limit = db.get_setting("daily_limit", str(Config.DAILY_MESSAGE_LIMIT))
    await update.message.reply_text(
        f"📊 <b>Statistika:</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{s['total_users']}</b>\n"
        f"✅ Faol obunalar: <b>{s['active_subs']}</b>\n"
        f"⏳ Kutayotgan to'lovlar: <b>{s['pending']}</b>\n"
        f"💬 Jami xabarlar: <b>{s['total_messages']}</b>\n"
        f"📅 Bugungi xabarlar: <b>{s['today_messages']}</b>\n"
        f"💰 Tasdiqlangan to'lovlar: <b>{s['approved']}</b>\n"
        f"📢 Majburiy kanallar: <b>{s['channels']}</b>\n"
        f"📏 Kunlik limit: <b>{limit}</b>",
        parse_mode=ParseMode.HTML
    )


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    users = db.get_all_users()
    text  = "👥 <b>Foydalanuvchilar:</b>\n\n"
    for u in users[:30]:
        icon    = "✅" if u["is_active"] else "❌"
        end_str = ""
        if u["subscription_end"]:
            try:
                end = datetime.fromisoformat(u["subscription_end"])
                end_str = f" | {end.strftime('%d.%m.%Y')}"
            except Exception:
                pass
        text += f"{icon} {u['full_name']} (@{u['username'] or '-'}) — <code>{u['user_id']}</code>{end_str}\n"
    if len(users) > 30:
        text += f"\n... va yana {len(users)-30} ta"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "❓ Ishlatish:\n"
            "/broadcast <xabar> — faqat obunachilarga\n"
            "/broadcast all <xabar> — hammaga"
        )
        return

    if context.args[0] == "all":
        text  = " ".join(context.args[1:])
        users = db.get_all_user_ids()
        label = "barcha foydalanuvchilarga"
    else:
        text  = " ".join(context.args)
        users = db.get_active_subscribers()
        label = "obunachilarga"

    if not text:
        await update.message.reply_text("❌ Xabar matni bo'sh!")
        return

    sent = 0
    for uid in users:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 <b>E'lon:</b>\n\n{text}",
                parse_mode=ParseMode.HTML
            )
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ {sent} ta {label} yuborildi!")


# ── Kanal boshqaruvi ──────────────────────────────────────────────────────────

async def admin_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addchannel <channel_id> <nom> <link>
    Misol: /addchannel @texno_ai Texno Ai https://t.me/texno_ai
    yoki:  /addchannel -1001234567890 Texno Ai https://t.me/texno_ai
    """
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args or len(args) < 3:
        await update.message.reply_text(
            "❓ Ishlatish:\n"
            "<code>/addchannel @kanal_username Kanal nomi https://t.me/kanal</code>\n\n"
            "Misol:\n"
            "<code>/addchannel @texno_ai Texno Ai https://t.me/texno_ai</code>",
            parse_mode=ParseMode.HTML
        )
        return

    channel_id = args[0]          # @username yoki -100xxx
    link       = args[-1]         # oxirgi — link
    name       = " ".join(args[1:-1])  # o'rtadagilar — nom

    if not link.startswith("http"):
        await update.message.reply_text("❌ Link to'g'ri emas! https://t.me/... bilan boshlaning.")
        return

    ok = db.add_channel(channel_id, name, link)
    if ok:
        await update.message.reply_text(
            f"✅ Kanal qo'shildi!\n\n"
            f"📢 <b>{name}</b>\n"
            f"🆔 {channel_id}\n"
            f"🔗 {link}",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text("❌ Xatolik! Kanal qo'shilmadi.")


async def admin_del_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/delchannel @username yoki -100xxx"""
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "❓ Ishlatish: <code>/delchannel @kanal_username</code>",
            parse_mode=ParseMode.HTML
        )
        return
    channel_id = context.args[0]
    ok = db.remove_channel(channel_id)
    if ok:
        await update.message.reply_text(f"✅ {channel_id} o'chirildi!")
    else:
        await update.message.reply_text("❌ Xatolik!")


async def admin_list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/channels — kanallar ro'yxati"""
    if not is_admin(update.effective_user.id):
        return
    channels = db.get_channels()
    if not channels:
        await update.message.reply_text(
            "📭 Hozircha majburiy kanallar yo'q.\n\n"
            "Qo'shish uchun:\n"
            "<code>/addchannel @username Nom https://t.me/username</code>",
            parse_mode=ParseMode.HTML
        )
        return
    text = "📢 <b>Majburiy kanallar:</b>\n\n"
    for ch in channels:
        text += f"• <b>{ch['name']}</b> — {ch['channel_id']}\n  {ch['link']}\n\n"
    text += "O'chirish: <code>/delchannel @username</code>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def admin_set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/setlimit 100 — kunlik xabar limitini o'zgartirish"""
    if not is_admin(update.effective_user.id):
        return
    if not context.args or not context.args[0].isdigit():
        current = db.get_setting("daily_limit", str(Config.DAILY_MESSAGE_LIMIT))
        await update.message.reply_text(
            f"📏 Hozirgi kunlik limit: <b>{current}</b>\n\n"
            f"O'zgartirish: <code>/setlimit 100</code>",
            parse_mode=ParseMode.HTML
        )
        return
    new_limit = int(context.args[0])
    db.set_setting("daily_limit", str(new_limit))
    await update.message.reply_text(
        f"✅ Kunlik limit <b>{new_limit}</b> ga o'rnatildi!",
        parse_mode=ParseMode.HTML
    )


async def admin_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/activate <user_id> — qo'lda obuna faollashtirish"""
    if not is_admin(update.effective_user.id):
        return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text(
            "❓ Ishlatish: <code>/activate 123456789</code>",
            parse_mode=ParseMode.HTML
        )
        return
    target_id = int(context.args[0])
    end_date  = db.activate_subscription(target_id)
    end_str   = datetime.fromisoformat(end_date).strftime("%d.%m.%Y") if end_date else "—"
    ts        = now_tashkent().strftime("%d.%m.%Y %H:%M")
    await update.message.reply_text(
        f"✅ <code>{target_id}</code> obunasi faollashtirildi!\n"
        f"📅 Tugash: {end_str}\n"
        f"🕐 Vaqt: {ts} (Toshkent)",
        parse_mode=ParseMode.HTML
    )
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎉 <b>Obunangiz faollashtirildi!</b>\n📅 {end_str} gacha\n\n"
                 f"Savolingizni yuboring! 🚀",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass


async def admin_deactivate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/deactivate <user_id> — obunani o'chirish"""
    if not is_admin(update.effective_user.id):
        return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text(
            "❓ Ishlatish: <code>/deactivate 123456789</code>",
            parse_mode=ParseMode.HTML
        )
        return
    target_id = int(context.args[0])
    db.deactivate_subscription(target_id)
    await update.message.reply_text(
        f"✅ <code>{target_id}</code> obunasi o'chirildi!",
        parse_mode=ParseMode.HTML
    )

# ─── SCHEDULER VAZIFALAR ──────────────────────────────────────────────────────

async def notify_expiring(app):
    """Har kuni soat 10:00 da — muddati 3 kun qolganlarni ogohlantiradi."""
    users = db.get_expiring_users()
    for u in users:
        try:
            end = datetime.fromisoformat(u["subscription_end"])
            days_left = max(0, (end - datetime.now()).days)
            await app.bot.send_message(
                chat_id=u["user_id"],
                text=f"⚠️ <b>Obuna muddati tugayapti!</b>\n\n"
                     f"📅 Faqat <b>{days_left} kun</b> qoldi.\n\n"
                     f"Uzluksiz foydalanish uchun obunani yangilang 👇",
                parse_mode=ParseMode.HTML,
                reply_markup=sub_keyboard()
            )
        except Exception as e:
            logger.warning(f"Expiry notify error {u['user_id']}: {e}")


async def monthly_cleanup_job(app):
    """Har oy 1-sanasida tozalash."""
    db.monthly_cleanup()
    for admin_id in Config.ADMIN_IDS:
        try:
            await app.bot.send_message(
                chat_id=admin_id,
                text="🧹 <b>Oylik tozalash bajarildi!</b>\n"
                     "Eski suhbat tarixi, statistika va muddati o'tgan obunalar tozalandi.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(Config.BOT_TOKEN).build()

    # Foydalanuvchi buyruqlari
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("help",       help_command))
    app.add_handler(CommandHandler("status",     status_command))
    app.add_handler(CommandHandler("clear",      clear_command))

    # Admin buyruqlari
    app.add_handler(CommandHandler("pending",    admin_pending))
    app.add_handler(CommandHandler("stats",      admin_stats))
    app.add_handler(CommandHandler("users",      admin_users))
    app.add_handler(CommandHandler("broadcast",  admin_broadcast))
    app.add_handler(CommandHandler("addchannel", admin_add_channel))
    app.add_handler(CommandHandler("delchannel", admin_del_channel))
    app.add_handler(CommandHandler("channels",   admin_list_channels))
    app.add_handler(CommandHandler("setlimit",   admin_set_limit))
    app.add_handler(CommandHandler("activate",   admin_activate))
    app.add_handler(CommandHandler("deactivate", admin_deactivate))

    # Callback va xabarlar
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    # Scheduler
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(notify_expiring,    "cron", hour=10, minute=0, args=[app])
    scheduler.add_job(monthly_cleanup_job,"cron", day=1,  hour=3,   args=[app])
    scheduler.start()

    logger.info("🤖 Texno Ai boti ishga tushdi!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
