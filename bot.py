import logging
import re
from datetime import datetime
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
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

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

Config.validate()

db     = Database()
client = OpenAI(api_key=Config.OPENAI_API_KEY)

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

🏫 Asosiy yo'nalishlar:
- Web dasturlash (HTML, CSS, JS, React, Vue)
- Backend (Python, Node.js, Django, FastAPI)
- Ma'lumotlar bazasi (SQL, MongoDB, PostgreSQL)
- Algoritmlar va ma'lumotlar strukturasi
- DevOps va deployment
- Telegram bot yaratish
- API integratsiya"""

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in Config.ADMIN_IDS


async def check_channel_membership(bot, user_id: int) -> list:
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
    buttons = [[InlineKeyboardButton(f"📢 {ch['name']}", url=ch["link"])] for ch in not_joined]
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(buttons)


def sub_keyboard():
    """
    BUG FIX: Oddiy va VIP narxlari alohida ko'rsatiladi.
    Ilgari faqat bir tugma bor edi, VIP ni qanday sotib olish noaniq edi.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"⭐ Oddiy obuna ({Config.SUBSCRIPTION_PRICE_UZS:,} so'm/oy)",
            url=f"https://t.me/{Config.ADMIN_USERNAME}"
        )],
        [InlineKeyboardButton(
            f"👑 VIP obuna ({Config.VIP_PRICE_UZS:,} so'm/oy)",
            url=f"https://t.me/{Config.VIP_ADMIN_USERNAME}"
        )],
        [InlineKeyboardButton("📸 Oddiy chek yuborish", callback_data="send_check_normal")],
        [InlineKeyboardButton("👑 VIP chek yuborish",   callback_data="send_check_vip")],
    ])


def main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton("🤖 AI Savol"), KeyboardButton("📊 Hisobim")],
        [KeyboardButton("👥 Referral"), KeyboardButton("ℹ️ Status")],
        [KeyboardButton("🗑 Tarixni tozalash"), KeyboardButton("📖 Yordam")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def admin_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton("📊 Statistika"), KeyboardButton("⏳ To'lovlar")],
        [KeyboardButton("👥 Foydalanuvchilar"), KeyboardButton("📢 E'lon")],
        [KeyboardButton("📋 Kanallar"), KeyboardButton("⚙️ Limitlar")],
        [KeyboardButton("👑 VIP berish"), KeyboardButton("💰 Balans")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


async def safe_send(message, text: str, **kwargs):
    try:
        if len(text) > 4096:
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await message.reply_text(part, parse_mode=ParseMode.MARKDOWN, **kwargs)
        else:
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, **kwargs)
    except Exception:
        try:
            await message.reply_text(text, **kwargs)
        except Exception as e:
            logger.error(f"safe_send error: {e}")

# ─── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    referred_by = None
    if context.args:
        ref_code = context.args[0]
        referrer = db.get_user_by_referral_code(ref_code)
        if referrer and referrer["user_id"] != user.id:
            referred_by = referrer["user_id"]

    db.add_user(user.id, user.username, user.full_name, referred_by=referred_by)

    if referred_by:
        bonus_given = db.process_referral(referred_by, user.id)
        if bonus_given:
            try:
                await context.bot.send_message(
                    chat_id=referred_by,
                    text=f"🎉 <b>Yangi referal!</b>\n\n"
                         f"👤 <b>{user.full_name}</b> sizning taklifingiz bilan keldi!\n"
                         f"💰 Hisobingizga <b>{Config.REFERRAL_BONUS_UZS:,} so'm</b> qo'shildi! 🎁",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Referral notify error: {e}")

    if is_admin(user.id):
        await update.message.reply_text(
            f"👑 <b>Xush kelibsiz, Admin!</b>\n\nAdmin klaviaturasi tayyor 👇",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard()
        )
        return

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
        limit = db.get_user_limit(user.id)
        daily = db.get_daily_count(user.id)
        vip_badge = " 👑 VIP" if info["is_vip"] else ""
        await update.message.reply_text(
            f"🎉 Xush kelibsiz, <b>{user.first_name}</b>{vip_badge}!\n\n"
            f"📅 Obuna: <b>{info['days_left']} kun</b> qolgan\n"
            f"💬 Bugungi xabarlar: <b>{daily}/{limit}</b>\n"
            f"💰 Balans: <b>{info['balance']:,} so'm</b>\n\n"
            f"Istalgan savol bering! 🚀",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(user.id)
        )
    else:
        my_code = db.get_referral_code(user.id)
        bot_username = (await context.bot.get_me()).username
        await update.message.reply_text(
            f"👋 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
            f"🤖 Men <b>Texno Ai</b> — AI dasturlash o'qituvchisi!\n\n"
            f"💰 <b>Tariflar:</b>\n"
            f"⭐ Oddiy — {Config.SUBSCRIPTION_PRICE_UZS:,} so'm/oy ({Config.DAILY_LIMIT_NORMAL} ta xabar/kun)\n"
            f"👑 VIP — {Config.VIP_PRICE_UZS:,} so'm/oy ({Config.DAILY_LIMIT_VIP} ta xabar/kun)\n\n"
            f"🎁 Do'st taklif qiling — har biri uchun <b>{Config.REFERRAL_BONUS_UZS:,} so'm</b> bonus!\n"
            f"🔗 <code>https://t.me/{bot_username}?start={my_code}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=sub_keyboard()
        )

# ─── /status ──────────────────────────────────────────────────────────────────

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    info = db.get_subscription_info(user.id)
    daily = db.get_daily_count(user.id)
    limit = db.get_user_limit(user.id)

    if info["is_active"]:
        end_str = info["end_date"].strftime("%d.%m.%Y") if info["end_date"] else "—"
        vip_str = "👑 VIP" if info["is_vip"] else "⭐ Oddiy"
        await update.message.reply_text(
            f"📊 <b>Sizning holatiz:</b>\n\n"
            f"✅ Obuna: <b>Faol</b>\n"
            f"🏷 Tur: <b>{vip_str}</b>\n"
            f"📅 Tugash: <b>{end_str}</b>\n"
            f"⏳ Qolgan: <b>{info['days_left']} kun</b>\n\n"
            f"💬 Bugungi xabarlar: <b>{daily}/{limit}</b>\n"
            f"💰 Balans: <b>{info['balance']:,} so'm</b>",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "❌ <b>Obuna yo'q</b>\n\nObuna bo'lish uchun:",
            parse_mode=ParseMode.HTML,
            reply_markup=sub_keyboard()
        )

# ─── /help ────────────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        not_joined = await check_channel_membership(context.bot, user.id)
        if not_joined:
            await update.message.reply_text("📢 Avval kanallarga obuna bo'ling:", reply_markup=channel_keyboard(not_joined))
            return
        if not db.is_active_subscriber(user.id):
            await update.message.reply_text("🔒 Bu funksiya faqat obunachilarga mavjud!", reply_markup=sub_keyboard())
            return
    await update.message.reply_text(
        "📖 <b>Men nima qila olaman?</b>\n\n"
        "💻 Python, JS, Java, C++, HTML, CSS, SQL...\n"
        "🛠 Kod yozish, bug tuzatish, algoritmlar\n\n"
        "📌 <b>Tugmalar:</b>\n"
        "🤖 AI Savol — savol yuboring\n"
        "📊 Hisobim — balans va referral\n"
        "👥 Referral — do'stlarni taklif\n"
        "ℹ️ Status — obuna holati\n"
        "🗑 Tarixni tozalash — yangi suhbat\n\n"
        "✍️ Shunchaki savol yozing — javob beraman! 🚀",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(user.id)
    )

# ─── /balance ─────────────────────────────────────────────────────────────────

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = db.get_referral_stats(user.id)
    ref_code = db.get_referral_code(user.id)
    bot_username = (await context.bot.get_me()).username
    await update.message.reply_text(
        f"💰 <b>Hisobim</b>\n\n"
        f"💵 Joriy balans: <b>{stats['balance']:,} so'm</b>\n\n"
        f"👥 <b>Referral:</b>\n"
        f"• Taklif qilinganlar: <b>{stats['count']} kishi</b>\n"
        f"• Jami bonus: <b>{stats['total_bonus']:,} so'm</b>\n\n"
        f"🔗 Havolangiz:\n"
        f"<code>https://t.me/{bot_username}?start={ref_code}</code>\n\n"
        f"💡 Har bir do'st uchun <b>{Config.REFERRAL_BONUS_UZS:,} so'm</b>!",
        parse_mode=ParseMode.HTML
    )

# ─── /referral ────────────────────────────────────────────────────────────────

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_code = db.get_referral_code(user.id)
    bot_username = (await context.bot.get_me()).username
    stats = db.get_referral_stats(user.id)
    await update.message.reply_text(
        f"👥 <b>Referral tizimi</b>\n\n"
        f"🎁 Har bir do'stingiz uchun <b>{Config.REFERRAL_BONUS_UZS:,} so'm</b> bonus!\n\n"
        f"📊 <b>Statistika:</b>\n"
        f"• Taklif: <b>{stats['count']} kishi</b>\n"
        f"• Bonus: <b>{stats['total_bonus']:,} so'm</b>\n"
        f"• Balans: <b>{stats['balance']:,} so'm</b>\n\n"
        f"🔗 <b>Havolangiz:</b>\n"
        f"<code>https://t.me/{bot_username}?start={ref_code}</code>",
        parse_mode=ParseMode.HTML
    )

# ─── /clear ───────────────────────────────────────────────────────────────────

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.clear_history(update.effective_user.id)
    await update.message.reply_text("🗑 Suhbat tarixi tozalandi! Yangi suhbat boshlash mumkin. 🚀")

# ─── CALLBACK QUERY ───────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user  = query.from_user

    if query.data == "check_sub":
        await query.answer()
        not_joined = await check_channel_membership(context.bot, user.id)
        if not_joined:
            await query.edit_message_text("❌ Hali ham quyidagi kanallarga obuna bo'lmadingiz:", reply_markup=channel_keyboard(not_joined))
        else:
            if db.is_active_subscriber(user.id):
                await query.edit_message_text("✅ Botdan foydalanishingiz mumkin!\n\nSavolingizni yozing 👇")
            else:
                await query.edit_message_text("✅ Kanallarga obuna bo'ldingiz!\n\nObuna sotib oling:", reply_markup=sub_keyboard())
        return

    # ─── BUG FIX: send_check_normal va send_check_vip alohida ───
    if query.data in ("send_check_normal", "send_check_vip"):
        await query.answer()
        ptype = "vip" if query.data == "send_check_vip" else "normal"
        price = Config.VIP_PRICE_UZS if ptype == "vip" else Config.SUBSCRIPTION_PRICE_UZS
        label = "👑 VIP" if ptype == "vip" else "⭐ Oddiy"

        # waiting_check DB ga va user_data ga yozamiz
        db.set_setting(f"waiting_check_{user.id}", ptype)   # 'normal' yoki 'vip'
        context.user_data["waiting_check"] = ptype

        await query.edit_message_text(
            f"📸 <b>{label} to'lov chekini yuboring:</b>\n\n"
            f"To'lov cheki (screenshot) shu chatga yuboring.\n\n"
            f"📌 To'lov ma'lumotlari:\n"
            f"• Narx: <b>{price:,} so'm/oy</b>\n"
            f"• Tur: <b>{label}</b>\n"
            f"• Admin: @{Config.VIP_ADMIN_USERNAME if ptype == 'vip' else Config.ADMIN_USERNAME}\n\n"
            f"⚡ Admin 5–15 daqiqa ichida faollashtiradi!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")
            ]])
        )
        return

    # Eski send_check callback (backward compatibility)
    if query.data == "send_check":
        await query.answer()
        db.set_setting(f"waiting_check_{user.id}", "normal")
        context.user_data["waiting_check"] = "normal"
        await query.edit_message_text(
            f"📸 <b>To'lov chekini yuboring:</b>\n\n"
            f"• Narx: <b>{Config.SUBSCRIPTION_PRICE_UZS:,} so'm/oy</b>\n"
            f"• Admin: @{Config.ADMIN_USERNAME}\n\n"
            f"⚡ Admin 5–15 daqiqa ichida faollashtiradi!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")
            ]])
        )
        return

    if query.data == "cancel":
        await query.answer()
        db.clear_pending_check(user.id)
        context.user_data.pop("waiting_check", None)
        await query.edit_message_text("❌ Bekor qilindi.\n\n/start — bosh menyuga qaytish")
        return

    # ─── BUG FIX: approve_ da payment_type tekshiriladi ───────────
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

        # To'lov turini bilish va mos faollashtirish
        ptype = db.get_payment_type(payment_id) if payment_id else "normal"
        if ptype == "vip":
            end_date = db.activate_vip_subscription(target_id)
        else:
            end_date = db.activate_subscription(target_id)

        if payment_id:
            db.update_payment_status(payment_id, "approved")

        end_str = datetime.fromisoformat(end_date).strftime("%d.%m.%Y") if end_date else "—"
        ts = now_tashkent().strftime("%d.%m.%Y %H:%M")
        ptype_label = "👑 VIP" if ptype == "vip" else "⭐ Oddiy"

        old_caption = query.message.caption or ""
        new_caption = (
            old_caption + f"\n\n✅ TASDIQLANDI ({ptype_label})\n"
            f"👤 Admin: @{user.username or user.full_name}\n"
            f"🕐 {ts} (Toshkent)\n"
            f"📅 Obuna: {end_str} gacha"
        )
        if len(new_caption) > 1024:
            new_caption = f"✅ #{target_id} {ptype_label} TASDIQLANDI | 📅 {end_str} | 🕐 {ts}"

        caption_updated = False
        try:
            await query.edit_message_caption(caption=new_caption, parse_mode=None, reply_markup=None)
            caption_updated = True
        except Exception as e:
            logger.warning(f"edit_message_caption (approve) error: {e}")

        if caption_updated:
            await query.answer(f"✅ {ptype_label} tasdiqlandi! {end_str} gacha")
        else:
            await query.answer(f"✅ #{target_id} {ptype_label} tasdiqlandi!", show_alert=True)

        try:
            info = db.get_subscription_info(target_id)
            vip_str = " 👑 VIP" if info["is_vip"] else ""
            limit = db.get_user_limit(target_id)
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    f"🎉 <b>Tabriklaymiz!</b>\n\n"
                    f"✅ <b>{ptype_label}</b> obunangiz faollashtirildi{vip_str}!\n"
                    f"📅 Tugash sanasi: <b>{end_str}</b>\n"
                    f"💬 Kunlik limit: <b>{limit} ta xabar</b>\n\n"
                    f"🤖 Endi <b>Texno Ai</b>dan to'liq foydalanishingiz mumkin! 🚀"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(target_id)
            )
        except Exception as e:
            logger.error(f"approve notify error (user {target_id}): {e}")
        return

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
            old_caption + f"\n\n❌ RAD ETILDI\n"
            f"👤 Admin: @{user.username or user.full_name}\n"
            f"🕐 {ts} (Toshkent)"
        )
        if len(new_caption) > 1024:
            new_caption = f"❌ #{target_id} RAD ETILDI | 🕐 {ts}"
        caption_updated = False
        try:
            await query.edit_message_caption(caption=new_caption, parse_mode=None, reply_markup=None)
            caption_updated = True
        except Exception as e:
            logger.warning(f"edit_message_caption (reject) error: {e}")
        if caption_updated:
            await query.answer("❌ Rad etildi!")
        else:
            await query.answer(f"❌ #{target_id} rad etildi!", show_alert=True)
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    f"❌ <b>To'lovingiz tasdiqlanmadi.</b>\n\n"
                    f"Sabab: chek aniq ko'rinmaydi yoki summa noto'g'ri.\n\n"
                    f"📞 Admin: @{Config.ADMIN_USERNAME}\n\nQayta urinib ko'ring:"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=sub_keyboard()
            )
        except Exception as e:
            logger.error(f"reject notify error (user {target_id}): {e}")
        return

    await query.answer()

# ─── XABAR HANDLER ────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    message = update.message
    text    = message.text or ""

    # ── Rasm: to'lov cheki ────────────────────────────────────────────────────
    if message.photo:
        # BUG FIX: waiting_check dan ptype (normal/vip) olinadi
        ptype = context.user_data.get("waiting_check")
        if not ptype:
            db_val = db.get_setting(f"waiting_check_{user.id}", "")
            if db_val in ("normal", "vip", "1"):
                ptype = "normal" if db_val == "1" else db_val

        if ptype:
            context.user_data.pop("waiting_check", None)
            # BUG FIX: clear_pending_check ishlatiladi (o'chiradi, 0 qilmaydi)
            db.clear_pending_check(user.id)

            file_id    = message.photo[-1].file_id
            # BUG FIX: payment_type DB ga saqlanadi
            payment_id = db.add_payment(user.id, file_id, payment_type=ptype)
            ts = now_tashkent().strftime("%d.%m.%Y  %H:%M:%S")
            price = Config.VIP_PRICE_UZS if ptype == "vip" else Config.SUBSCRIPTION_PRICE_UZS
            ptype_label = "👑 VIP" if ptype == "vip" else "⭐ Oddiy"

            await message.reply_text(
                f"✅ <b>{ptype_label} chek qabul qilindi!</b>\n\n"
                f"⏳ Admin tekshirmoqda... (5–15 daqiqa)\n\n"
                f"Tasdiqlangandan so'ng sizga xabar yuboriladi! 📬",
                parse_mode=ParseMode.HTML
            )
            caption = (
                f"💳 <b>Yangi to'lov cheki!</b>\n"
                f"{'─' * 28}\n"
                f"👤 Ismi: <b>{user.full_name}</b>\n"
                f"🔗 Username: @{user.username or '—'}\n"
                f"🆔 User ID: <code>{user.id}</code>\n"
                f"🏷 Tur: <b>{ptype_label}</b>\n"
                f"💰 Summa: <b>{price:,} so'm</b>\n"
                f"🕐 Vaqt: <b>{ts} (Toshkent)</b>\n"
                f"🗂 To'lov №: <code>{payment_id}</code>\n"
                f"{'─' * 28}\n⬇️ Tasdiqlash yoki rad etish:"
            )
            approve_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{user.id}_{payment_id}"),
                InlineKeyboardButton("❌ Rad etish",  callback_data=f"reject_{user.id}_{payment_id}"),
            ]])

            # VIP to'lovlar faqat VIP adminga, oddiy to'lovlar barcha adminlarga
            if ptype == "vip":
                recipients = []
                if Config.VIP_ADMIN_ID:
                    recipients.append(Config.VIP_ADMIN_ID)
                else:
                    # VIP_ADMIN_ID sozlanmagan bo'lsa barcha adminlarga yuboriladi
                    recipients = Config.ADMIN_IDS
            else:
                recipients = Config.ADMIN_IDS

            for admin_id in recipients:
                try:
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=file_id,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=approve_kb
                    )
                except Exception as e:
                    logger.error(f"Admin notify error (admin={admin_id}): {e}")
            return

    # ── Admin klaviatura tugmalari ─────────────────────────────────────────────
    if is_admin(user.id):
        if text == "📊 Statistika":
            await admin_stats_msg(update, context); return
        elif text == "⏳ To'lovlar":
            await admin_pending_msg(update, context); return
        elif text == "👥 Foydalanuvchilar":
            await admin_users_msg(update, context); return
        elif text == "📢 E'lon":
            await update.message.reply_text(
                "📢 /broadcast <xabar> — obunachilarga\n/broadcast all <xabar> — hammaga"
            ); return
        elif text == "📋 Kanallar":
            await admin_list_channels_msg(update, context); return
        elif text == "⚙️ Limitlar":
            normal = db.get_setting("normal_limit", str(Config.DAILY_LIMIT_NORMAL))
            vip    = db.get_setting("vip_limit",    str(Config.DAILY_LIMIT_VIP))
            await update.message.reply_text(
                f"⚙️ <b>Joriy limitlar:</b>\n\n"
                f"⭐ Oddiy: <b>{normal} ta/kun</b>\n"
                f"👑 VIP: <b>{vip} ta/kun</b>\n\n"
                f"O'zgartirish:\n/setlimit normal 5\n/setlimit vip 50",
                parse_mode=ParseMode.HTML
            ); return
        elif text == "👑 VIP berish":
            await update.message.reply_text(
                "👑 <b>VIP boshqaruvi:</b>\n\n"
                "/setvip <user_id> — VIP berish\n"
                "/removevip <user_id> — VIP olish",
                parse_mode=ParseMode.HTML
            ); return
        elif text == "💰 Balans":
            await update.message.reply_text(
                "💰 /addbalance <user_id> <summa> — balans qo'shish",
                parse_mode=ParseMode.HTML
            ); return

    # ── Foydalanuvchi klaviatura tugmalari ────────────────────────────────────
    if not is_admin(user.id):
        if text == "📊 Hisobim":
            await balance_command(update, context); return
        elif text == "👥 Referral":
            await referral_command(update, context); return
        elif text == "ℹ️ Status":
            await status_command(update, context); return
        elif text == "🗑 Tarixni tozalash":
            await clear_command(update, context); return
        elif text == "📖 Yordam":
            await help_command(update, context); return
        elif text == "🤖 AI Savol":
            await message.reply_text("💬 Savolingizni yozing! 🚀"); return

    # ── Majburiy kanal tekshirish ──────────────────────────────────────────────
    if not is_admin(user.id):
        not_joined = await check_channel_membership(context.bot, user.id)
        if not_joined:
            await message.reply_text("📢 Avval quyidagi kanallarga obuna bo'ling:", reply_markup=channel_keyboard(not_joined))
            return

    # ── Obuna tekshirish ───────────────────────────────────────────────────────
    if not is_admin(user.id) and not db.is_active_subscriber(user.id):
        await message.reply_text(
            f"🔒 <b>Obuna kerak!</b>\n\n"
            f"⭐ Oddiy — {Config.SUBSCRIPTION_PRICE_UZS:,} so'm/oy\n"
            f"👑 VIP — {Config.VIP_PRICE_UZS:,} so'm/oy",
            parse_mode=ParseMode.HTML,
            reply_markup=sub_keyboard()
        )
        return

    # ── Matn tekshirish ────────────────────────────────────────────────────────
    if not text:
        await message.reply_text("💬 Iltimos, matn yozing!")
        return

    # ── Kunlik limit ──────────────────────────────────────────────────────────
    if not is_admin(user.id):
        limit = db.get_user_limit(user.id)
        daily = db.get_daily_count(user.id)
        if daily >= limit:
            is_vip_user = db.is_vip(user.id)
            if is_vip_user:
                msg = (
                    f"⏳ <b>VIP limit tugadi!</b>\n\n"
                    f"Bugun <b>{limit} ta</b> xabar yuborish mumkin edi.\n"
                    f"Ertaga soat 00:00 da yangilanadi. 🙏"
                )
            else:
                msg = (
                    f"⏳ <b>Kunlik limit tugadi!</b>\n\n"
                    f"⭐ Oddiy limit: <b>{limit} ta/kun</b>\n"
                    f"👑 VIP ga o'tib <b>{db.get_setting('vip_limit', str(Config.DAILY_LIMIT_VIP))} ta/kun</b> yuboring!\n\n"
                    f"Ertaga 00:00 da yangilanadi 🙏"
                )
            await message.reply_text(
                msg,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"👑 VIP sotib olish", callback_data="send_check_vip")
                ]])
            )
            return

    # ── AI javob ──────────────────────────────────────────────────────────────
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
        await message.reply_text("⚠️ Xatolik yuz berdi. Qayta urinib ko'ring.")

# ─── ADMIN BUYRUQLARI ─────────────────────────────────────────────────────────

async def admin_pending_msg(update, context):
    payments = db.get_pending_payments()
    if not payments:
        await update.message.reply_text("📭 Kutayotgan to'lovlar yo'q!")
        return
    await update.message.reply_text(f"⏳ <b>Kutayotgan to'lovlar: {len(payments)} ta</b>", parse_mode=ParseMode.HTML)
    for p in payments:
        try:
            raw_dt = datetime.fromisoformat(p["created_at"])
            local_dt = raw_dt.astimezone(TZ) if raw_dt.tzinfo else TZ.localize(raw_dt)
            ts_str = local_dt.strftime("%d.%m.%Y  %H:%M:%S")
        except Exception:
            ts_str = p["created_at"]
        ptype = p.get("payment_type", "normal")
        ptype_label = "👑 VIP" if ptype == "vip" else "⭐ Oddiy"
        price = Config.VIP_PRICE_UZS if ptype == "vip" else Config.SUBSCRIPTION_PRICE_UZS
        caption = (
            f"💳 <b>To'lov cheki</b>\n{'─'*28}\n"
            f"👤 Ismi: <b>{p['full_name']}</b>\n"
            f"🔗 Username: @{p['username'] or '—'}\n"
            f"🆔 User ID: <code>{p['user_id']}</code>\n"
            f"🏷 Tur: <b>{ptype_label}</b>\n"
            f"💰 Summa: <b>{price:,} so'm</b>\n"
            f"🕐 Vaqt: <b>{ts_str} (Toshkent)</b>\n"
            f"🗂 To'lov №: <code>{p['id']}</code>"
        )
        await update.message.reply_photo(
            photo=p["file_id"], caption=caption, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{p['user_id']}_{p['id']}"),
                InlineKeyboardButton("❌ Rad etish",  callback_data=f"reject_{p['user_id']}_{p['id']}"),
            ]])
        )


async def admin_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await admin_pending_msg(update, context)


async def admin_stats_msg(update, context):
    s = db.get_stats()
    normal_limit = db.get_setting("normal_limit", str(Config.DAILY_LIMIT_NORMAL))
    vip_limit    = db.get_setting("vip_limit",    str(Config.DAILY_LIMIT_VIP))
    await update.message.reply_text(
        f"📊 <b>Statistika:</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{s['total_users']}</b>\n"
        f"✅ Faol obunalar: <b>{s['active_subs']}</b>\n"
        f"👑 VIP foydalanuvchilar: <b>{s['vip_users']}</b>\n"
        f"⏳ Kutayotgan to'lovlar: <b>{s['pending']}</b> (VIP: {s['pending_vip']})\n"
        f"💬 Jami xabarlar: <b>{s['total_messages']}</b>\n"
        f"📅 Bugungi xabarlar: <b>{s['today_messages']}</b>\n"
        f"💰 Tasdiqlangan: <b>{s['approved']}</b>\n"
        f"📢 Kanallar: <b>{s['channels']}</b>\n"
        f"👥 Referrallar: <b>{s['total_referrals']}</b>\n"
        f"🎁 Bonuslar: <b>{s['total_bonuses']:,} so'm</b>\n\n"
        f"⚙️ <b>Limitlar:</b>\n"
        f"⭐ Oddiy: <b>{normal_limit} ta/kun</b>\n"
        f"👑 VIP: <b>{vip_limit} ta/kun</b>",
        parse_mode=ParseMode.HTML
    )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await admin_stats_msg(update, context)


async def admin_users_msg(update, context):
    users = db.get_all_users()
    text = "👥 <b>Foydalanuvchilar:</b>\n\n"
    for u in users[:30]:
        icon     = "✅" if u["is_active"] else "❌"
        vip_icon = " 👑" if u.get("is_vip") and u["is_active"] else ""
        end_str  = ""
        if u["subscription_end"]:
            try:
                end = datetime.fromisoformat(u["subscription_end"])
                end_str = f" | {end.strftime('%d.%m.%Y')}"
            except Exception:
                pass
        balance = u.get("balance", 0) or 0
        text += f"{icon}{vip_icon} {u['full_name']} (@{u['username'] or '-'}) — <code>{u['user_id']}</code>{end_str} | 💰{balance:,}\n"
    if len(users) > 30:
        text += f"\n... va yana {len(users)-30} ta"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await admin_users_msg(update, context)


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("/broadcast <xabar> — obunachilarga\n/broadcast all <xabar> — hammaga")
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
            await context.bot.send_message(chat_id=uid, text=f"📢 <b>E'lon:</b>\n\n{text}", parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ {sent} ta {label} yuborildi!")


async def admin_list_channels_msg(update, context):
    channels = db.get_channels()
    if not channels:
        await update.message.reply_text("📭 Hozircha majburiy kanallar yo'q.\n\n/addchannel @username Nom https://t.me/username")
        return
    text = "📢 <b>Majburiy kanallar:</b>\n\n"
    for ch in channels:
        text += f"• <b>{ch['name']}</b> — {ch['channel_id']}\n  {ch['link']}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def admin_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    args = context.args
    if not args or len(args) < 3:
        await update.message.reply_text("<code>/addchannel @username Nom https://t.me/username</code>", parse_mode=ParseMode.HTML)
        return
    channel_id = args[0]; link = args[-1]; name = " ".join(args[1:-1])
    if not link.startswith("http"):
        await update.message.reply_text("❌ Link to'g'ri emas!")
        return
    ok = db.add_channel(channel_id, name, link)
    await update.message.reply_text(f"✅ {name} qo'shildi!" if ok else "❌ Xatolik!")


async def admin_del_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("<code>/delchannel @username</code>", parse_mode=ParseMode.HTML)
        return
    ok = db.remove_channel(context.args[0])
    await update.message.reply_text(f"✅ {context.args[0]} o'chirildi!" if ok else "❌ Xatolik!")


async def admin_list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await admin_list_channels_msg(update, context)


async def admin_set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    args = context.args
    normal_limit = db.get_setting("normal_limit", str(Config.DAILY_LIMIT_NORMAL))
    vip_limit    = db.get_setting("vip_limit",    str(Config.DAILY_LIMIT_VIP))
    if not args:
        await update.message.reply_text(
            f"⚙️ <b>Joriy:</b> Oddiy={normal_limit}, VIP={vip_limit}\n\n"
            f"<code>/setlimit normal 5</code>\n<code>/setlimit vip 50</code>",
            parse_mode=ParseMode.HTML
        ); return
    if len(args) == 2 and args[0] in ("normal", "vip") and args[1].isdigit():
        key = "normal_limit" if args[0] == "normal" else "vip_limit"
        label = "⭐ Oddiy" if args[0] == "normal" else "👑 VIP"
        db.set_setting(key, args[1])
        await update.message.reply_text(f"✅ {label} limit <b>{args[1]}</b> ga o'rnatildi!", parse_mode=ParseMode.HTML)
    elif len(args) == 1 and args[0].isdigit():
        db.set_setting("normal_limit", args[0])
        await update.message.reply_text(f"✅ Oddiy limit <b>{args[0]}</b> ga o'rnatildi!", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ Format: <code>/setlimit normal 5</code>", parse_mode=ParseMode.HTML)


async def admin_set_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("❓ <code>/setvip 123456789</code>", parse_mode=ParseMode.HTML); return
    target_id = int(context.args[0])
    # BUG FIX: VIP berishda obuna ham faollashtiriladi
    db.set_vip(target_id, True)
    if not db.is_active_subscriber(target_id):
        db.activate_subscription(target_id)
    vip_limit = db.get_setting("vip_limit", str(Config.DAILY_LIMIT_VIP))
    await update.message.reply_text(
        f"✅ <code>{target_id}</code> ga 👑 VIP berildi!\nLimit: {vip_limit} ta/kun",
        parse_mode=ParseMode.HTML
    )
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎉 <b>Sizga 👑 VIP status berildi!</b>\nKunlik limit: <b>{vip_limit} ta xabar</b> 🚀",
            parse_mode=ParseMode.HTML, reply_markup=main_keyboard(target_id)
        )
    except Exception: pass


async def admin_remove_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("❓ <code>/removevip 123456789</code>", parse_mode=ParseMode.HTML); return
    target_id = int(context.args[0])
    db.set_vip(target_id, False)
    await update.message.reply_text(f"✅ <code>{target_id}</code> dan VIP olindi.", parse_mode=ParseMode.HTML)


async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❓ <code>/addbalance 123456789 1000</code>", parse_mode=ParseMode.HTML); return
    try:
        target_id = int(context.args[0]); amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri format!"); return
    with db._conn() as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, target_id))
    new_balance = db.get_balance(target_id)
    await update.message.reply_text(
        f"✅ <code>{target_id}</code> ga <b>{amount:,} so'm</b> qo'shildi!\nYangi balans: <b>{new_balance:,} so'm</b>",
        parse_mode=ParseMode.HTML
    )


async def admin_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("❓ <code>/activate 123456789</code>", parse_mode=ParseMode.HTML); return
    target_id = int(context.args[0])
    end_date  = db.activate_subscription(target_id)
    end_str   = datetime.fromisoformat(end_date).strftime("%d.%m.%Y") if end_date else "—"
    await update.message.reply_text(
        f"✅ <code>{target_id}</code> obunasi faollashtirildi!\n📅 {end_str}", parse_mode=ParseMode.HTML
    )
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎉 <b>Obunangiz faollashtirildi!</b>\n📅 {end_str} gacha 🚀",
            parse_mode=ParseMode.HTML, reply_markup=main_keyboard(target_id)
        )
    except Exception: pass


async def admin_deactivate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("❓ <code>/deactivate 123456789</code>", parse_mode=ParseMode.HTML); return
    target_id = int(context.args[0])
    db.deactivate_subscription(target_id)
    await update.message.reply_text(f"✅ <code>{target_id}</code> obunasi o'chirildi!", parse_mode=ParseMode.HTML)

# ─── SCHEDULER ────────────────────────────────────────────────────────────────

async def notify_expiring(app):
    for u in db.get_expiring_users():
        try:
            end = datetime.fromisoformat(u["subscription_end"])
            days_left = max(0, (end - datetime.now()).days)
            await app.bot.send_message(
                chat_id=u["user_id"],
                text=f"⚠️ <b>Obuna tugayapti!</b>\n\n📅 <b>{days_left} kun</b> qoldi.\n\nYangilang 👇",
                parse_mode=ParseMode.HTML, reply_markup=sub_keyboard()
            )
        except Exception as e:
            logger.warning(f"Expiry notify error {u['user_id']}: {e}")


async def monthly_cleanup_job(app):
    db.monthly_cleanup()
    for admin_id in Config.ADMIN_IDS:
        try:
            await app.bot.send_message(
                chat_id=admin_id, text="🧹 <b>Oylik tozalash bajarildi!</b>", parse_mode=ParseMode.HTML
            )
        except Exception: pass

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(Config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("help",       help_command))
    app.add_handler(CommandHandler("status",     status_command))
    app.add_handler(CommandHandler("clear",      clear_command))
    app.add_handler(CommandHandler("balance",    balance_command))
    app.add_handler(CommandHandler("referral",   referral_command))

    app.add_handler(CommandHandler("pending",    admin_pending))
    app.add_handler(CommandHandler("stats",      admin_stats))
    app.add_handler(CommandHandler("users",      admin_users))
    app.add_handler(CommandHandler("broadcast",  admin_broadcast))
    app.add_handler(CommandHandler("addchannel", admin_add_channel))
    app.add_handler(CommandHandler("delchannel", admin_del_channel))
    app.add_handler(CommandHandler("channels",   admin_list_channels))
    app.add_handler(CommandHandler("setlimit",   admin_set_limit))
    app.add_handler(CommandHandler("setvip",     admin_set_vip))
    app.add_handler(CommandHandler("removevip",  admin_remove_vip))
    app.add_handler(CommandHandler("addbalance", admin_add_balance))
    app.add_handler(CommandHandler("activate",   admin_activate))
    app.add_handler(CommandHandler("deactivate", admin_deactivate))

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(notify_expiring,     "cron", hour=10, minute=0, args=[app])
    scheduler.add_job(monthly_cleanup_job, "cron", day=1,  hour=3,   args=[app])
    scheduler.start()

    logger.info("🤖 Texno Ai boti ishga tushdi!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
