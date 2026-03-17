# 🤖 Texno Ai Bot

AI dasturlash o'qituvchisi — GPT-4o-mini bilan ishlaydi.
Majburiy $5/oy obuna, admin panel va to'lov tasdiqlash.

---

## 🚀 Railway.app ga Deploy

### 1-qadam — GitHub repo
```bash
git init
git add .
git commit -m "Initial bot setup"
git remote add origin https://github.com/USERNAME/REPO.git
git push -u origin main
```

### 2-qadam — Railway
1. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
2. Repongizni tanlang — Railway avtomatik build qiladi ✅

### 3-qadam — Variables (muhim!)
Railway dashboard → loyiha → **Variables** tab:

| Kalit | Qiymat |
|-------|--------|
| `BOT_TOKEN` | @BotFather dan token |
| `OPENAI_API_KEY` | platform.openai.com dan |
| `ADMIN_IDS` | Telegram ID raqamingiz |
| `ADMIN_USERNAME` | @ belgisisiz username |
| `CARD_NUMBER` | To'lov karta raqami |
| `CARD_OWNER` | Karta egasi ismi |

### 4-qadam — Tekshirish
Logs tabda `✅ Config tekshirildi` va bot ishga tushgani ko'rinsa — tayyor! 🎉

---

## 💾 Volume (tavsiya)
DB yo'qolmasligi uchun: Railway → **Add Volume** → mount: `/app`

---

## 👑 Admin buyruqlari
- `/pending` — kutayotgan to'lovlar + tasdiqlash tugmalari
- `/stats` — statistika
- `/users` — foydalanuvchilar
- `/broadcast <matn>` — hammaga xabar

## 👤 Foydalanuvchi buyruqlari
- `/start` — boshlash
- `/help` — yordam
- `/clear` — tarixni tozalash
