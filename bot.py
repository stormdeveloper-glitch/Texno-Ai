import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from database import Database
from config import Config
from openai import OpenAI

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config tekshirish
Config.validate()

# States
WAITING_CHECK = 1

db = Database()
client = OpenAI(api_key=Config.OPENAI_API_KEY)

# ─── SYSTEM PROMPT ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Siz "Texno Ai" nomli AI dasturlash o'qituvchisisiz.

👨‍💻 Shaxsiyat:
- Ismingiz: Texno Ai
- Siz professional dasturchi va o'qituvchisiz
- Har doim iliq, samimiy va rag'batlantiruvchi muloqot qilasiz
- Murakkab tushunchalarni oddiy, tushunarli tilda tushuntirasiz

👨‍💻Dasturchilar:
- Dasturchilar: @Teacher_texnoo va @Stormdev_coder

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

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def is_subscribed(user_id: int) -> bool:
    return db.is_active_subscriber(user_id)

def is_admin(user_id: int) -> bool:
    return user_id in Config.ADMIN_IDS

def get_subscription_keyboard():
    keyboard = [
        [InlineKeyboardButton("💰 Obuna bo'lish (19.999 so'm/oy)", url=f"https://t.me/{Config.ADMIN_USERNAME}")],
        [InlineKeyboardButton("📸 To'lov chekini yuborish", callback_data="send_check")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")]])

# ─── COMMANDS ────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.full_name)

    if is_admin(user.id):
        await update.message.reply_text(
            f"👑 Xush kelibsiz, Admin!\n\n"
            f"🔧 Admin buyruqlari:\n"
            f"/pending — Kutayotgan to'lovlar\n"
            f"/users — Barcha foydalanuvchilar\n"
            f"/broadcast — Xabar yuborish\n"
            f"/stats — Statistika"
        )
        return

    if is_subscribed(user.id):
        await update.message.reply_text(
            f"🎉 Xush kelibsiz, {user.first_name}!\n\n"
            f"🤖 Men <b>Texno Ai</b> — sizning shaxsiy dasturlash o'qituvchingizman!\n\n"
            f"💬 Istalgan savol bering, men 24/7 yordam berishga tayyorman!\n\n"
            f"📚 /help — nima qila olishim haqida",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"👋 Assalomu alaykum, {user.first_name}!\n\n"
            f"🤖 Men <b>Texno Ai</b> — AI dasturlash o'qituvchisi!\n\n"
            f"📚 <b>Nima qila olaman?</b>\n"
            f"• Python, JS, Java, C++ va boshqa tillarda yordam\n"
            f"• Kod yozish, xatolarni tuzatish\n"
            f"• Loyiha yaratishda qo'llab-quvvatlash\n"
            f"• 24/7 darslar va tushuntirishlar\n\n"
            f"💰 <b>Narx:</b> Oyiga faqat $5\n\n"
            f"1️⃣ <b>Obuna bo'lish</b> tugmasini bosing — admin to'lov ma'lumotlarini yuboradi\n"
            f"2️⃣ To'lovdan so'ng chek yuboring — 5-15 daqiqada faollashadi ⚡",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard()
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_subscribed(update.effective_user.id) and not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "⚠️ Ushbu funksiya faqat obunachilarga mavjud!",
            reply_markup=get_subscription_keyboard()
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
        "✍️ Shunchaki savol yozing — men javob beraman! 🚀",
        parse_mode="HTML"
    )

# ─── SUBSCRIPTION FLOW ───────────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "send_check":
        await query.edit_message_text(
            "📸 <b>To'lov chekini yuboring:</b>\n\n"
            "Admin bilan gaplashib to'lovni amalga oshiring,\n"
            "so'ng to'lov cheki (screenshot)ni shu yerga yuboring.\n\n"
            "⚡ Admin 5-15 daqiqa ichida faollashtiradi!",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        context.user_data['waiting_check'] = True

    elif query.data == "cancel":
        context.user_data.pop('waiting_check', None)
        await query.edit_message_text(
            "❌ Bekor qilindi.\n\n/start — bosh menyuga qaytish"
        )

    # Admin: approve/reject
    elif query.data.startswith("approve_"):
        if not is_admin(user.id):
            return
        target_user_id = int(query.data.split("_")[1])
        payment_id = query.data.split("_")[2] if len(query.data.split("_")) > 2 else None
        
        db.activate_subscription(target_user_id)
        if payment_id:
            db.update_payment_status(payment_id, "approved")

        await query.edit_message_text(
            f"✅ Foydalanuvchi #{target_user_id} obunasi faollashtirildi!"
        )

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="🎉 <b>Tabriklaymiz!</b>\n\n"
                     "✅ Obunangiz faollashtirildi!\n\n"
                     "🤖 Endi <b>Texno Ai</b>dan to'liq foydalanishingiz mumkin!\n\n"
                     "💬 Istalgan savolingizni yuboring — men yordam berishga tayyorman! 🚀\n\n"
                     "/help — imkoniyatlarni ko'rish",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Notification error: {e}")

    elif query.data.startswith("reject_"):
        if not is_admin(user.id):
            return
        target_user_id = int(query.data.split("_")[1])
        payment_id = query.data.split("_")[2] if len(query.data.split("_")) > 2 else None
        
        if payment_id:
            db.update_payment_status(payment_id, "rejected")

        await query.edit_message_text(
            f"❌ Foydalanuvchi #{target_user_id} to'lovi rad etildi!"
        )

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ <b>To'lovingiz tasdiqlanmadi.</b>\n\n"
                     "Sabab: Chek aniq ko'rinmaydi yoki summa noto'g'ri.\n\n"
                     "📞 Admin bilan bog'laning yoki qayta urinib ko'ring.\n"
                     f"Admin: @{Config.ADMIN_USERNAME}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Notification error: {e}")

# ─── MESSAGE HANDLER ─────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    # Check photo (payment check)
    if message.photo and context.user_data.get('waiting_check'):
        context.user_data.pop('waiting_check', None)
        
        file_id = message.photo[-1].file_id
        payment_id = db.add_payment(user.id, file_id)

        await message.reply_text(
            "✅ <b>Chek qabul qilindi!</b>\n\n"
            "⏳ Admin tekshirmoqda... (5-15 daqiqa)\n\n"
            "Tasdiqlangandan so'ng sizga xabar yuboriladi! 📬",
            parse_mode="HTML"
        )

        # Notify admins
        for admin_id in Config.ADMIN_IDS:
            try:
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{user.id}_{payment_id}"),
                        InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{user.id}_{payment_id}")
                    ]
                ])
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=file_id,
                    caption=f"💳 <b>Yangi to'lov cheki!</b>\n\n"
                            f"👤 Foydalanuvchi: {user.full_name}\n"
                            f"🆔 ID: <code>{user.id}</code>\n"
                            f"👤 Username: @{user.username or 'yoq'}\n\n"
                            f"⬇️ Tasdiqlash yoki rad etish:",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Admin notify error: {e}")
        return

    # If not subscribed
    if not is_subscribed(user.id) and not is_admin(user.id):
        await message.reply_text(
            "🔒 <b>Obuna kerak!</b>\n\n"
            "Bu xizmatdan foydalanish uchun oylik $5 obuna talab qilinadi.\n\n"
            "👇 Obuna bo'lish uchun:",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard()
        )
        return

    # AI Response
    text = message.text
    if not text:
        await message.reply_text("💬 Iltimos, matn yozing!")
        return

    # Save to history
    history = context.user_data.get('history', [])
    history.append({"role": "user", "content": text})
    
    # Keep last 20 messages
    if len(history) > 20:
        history = history[-20:]

    typing_msg = await message.reply_text("⌨️ Yozmoqdaman...")

    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=1500,
            temperature=0.7
        )

        ai_reply = response.choices[0].message.content
        history.append({"role": "assistant", "content": ai_reply})
        context.user_data['history'] = history

        db.log_message(user.id, text, ai_reply)

        await typing_msg.delete()
        
        # Split long messages
        if len(ai_reply) > 4000:
            parts = [ai_reply[i:i+4000] for i in range(0, len(ai_reply), 4000)]
            for part in parts:
                await message.reply_text(part, parse_mode="Markdown")
        else:
            await message.reply_text(ai_reply, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        await typing_msg.delete()
        await message.reply_text(
            "⚠️ Xatolik yuz berdi. Iltimos qayta urinib ko'ring.\n\n"
            "Agar muammo davom etsa, /start bosing."
        )

# ─── ADMIN COMMANDS ──────────────────────────────────────────────────────────
async def admin_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    payments = db.get_pending_payments()
    if not payments:
        await update.message.reply_text("📭 Kutayotgan to'lovlar yo'q!")
        return

    await update.message.reply_text(f"⏳ <b>Kutayotgan to'lovlar: {len(payments)} ta</b>", parse_mode="HTML")
    
    for p in payments:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{p['user_id']}_{p['id']}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{p['user_id']}_{p['id']}")
            ]
        ])
        await update.message.reply_photo(
            photo=p['file_id'],
            caption=f"👤 {p['full_name']}\n🆔 {p['user_id']}\n📅 {p['created_at']}",
            reply_markup=keyboard
        )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    stats = db.get_stats()
    await update.message.reply_text(
        f"📊 <b>Statistika:</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{stats['total_users']}</b>\n"
        f"✅ Faol obunalar: <b>{stats['active_subs']}</b>\n"
        f"⏳ Kutayotgan: <b>{stats['pending']}</b>\n"
        f"💬 Jami xabarlar: <b>{stats['total_messages']}</b>\n"
        f"💰 Tasdiqlangan to'lovlar: <b>{stats['approved_payments']}</b>",
        parse_mode="HTML"
    )

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    users = db.get_all_users()
    text = "👥 <b>Foydalanuvchilar:</b>\n\n"
    for u in users[:30]:
        status = "✅" if u['is_active'] else "❌"
        text += f"{status} {u['full_name']} (@{u['username'] or '-'}) — ID: {u['user_id']}\n"
    
    if len(users) > 30:
        text += f"\n... va yana {len(users)-30} ta"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("❓ Ishlatish: /broadcast <xabar matni>")
        return
    
    text = " ".join(context.args)
    users = db.get_active_subscribers()
    sent = 0
    
    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 <b>E'lon:</b>\n\n{text}",
                parse_mode="HTML"
            )
            sent += 1
        except:
            pass
    
    await update.message.reply_text(f"✅ {sent} ta foydalanuvchiga yuborildi!")

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['history'] = []
    await update.message.reply_text("🗑 Suhbat tarixi tozalandi! Yangi suhbat boshlash mumkin. 🚀")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(Config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("pending", admin_pending))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("users", admin_users))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    logger.info("🤖 Texno Ai boti ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()