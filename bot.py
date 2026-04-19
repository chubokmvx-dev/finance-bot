import os
import json
import asyncio
import aiohttp
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

# ═══════════════════════════════════════════
# КОНФІГУРАЦІЯ
# ═══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
DATA_FILE = "data.json"

CATEGORIES = {
    "food": ("🛒", "Їжа та продукти"),
    "rent": ("🏠", "Оренда / комуналка"),
    "transport": ("🚗", "Транспорт"),
    "fun": ("🎉", "Розваги та кафе"),
    "health": ("💊", "Здоров'я"),
    "clothes": ("👕", "Одяг"),
    "savings": ("💰", "Накопичення"),
    "invest": ("📈", "Інвестиції"),
    "other": ("📦", "Інше"),
}

INCOME_TYPES = {
    "salary": ("💼", "Зарплата"),
    "freelance": ("💻", "Фріланс"),
    "passive": ("📊", "Пасивний дохід"),
    "gift": ("🎁", "Подарунок"),
    "other_income": ("➕", "Інше"),
}

# ═══════════════════════════════════════════
# ЗБЕРІГАННЯ ДАНИХ
# ═══════════════════════════════════════════
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_data(data, user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"months": {}, "settings": {"target": 5000, "mono_token": ""}}
    return data[uid]

def get_month_key():
    now = datetime.now()
    return f"{now.year}-{now.month:02d}"

def get_month_label(key):
    year, month = key.split("-")
    months_uk = ["", "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
                 "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]
    return f"{months_uk[int(month)]} {year}"

def fmt_uah(n):
    return f"{n:,.0f} ₴".replace(",", " ")

def fmt_usdt(n):
    return f"${n:.2f}"

# ═══════════════════════════════════════════
# API ВИКЛИКИ
# ═══════════════════════════════════════════
async def get_usdt_rate():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=USDTUAH", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    data = await r.json()
                    return float(data["price"])
    except:
        pass
    return 41.5

async def ask_claude(prompt, max_tokens=500):
    if not ANTHROPIC_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": "claude-sonnet-4-20250514", "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                data = await r.json()
                return data["content"][0]["text"]
    except:
        return None

# ═══════════════════════════════════════════
# ГОЛОВНЕ МЕНЮ
# ═══════════════════════════════════════════
def main_keyboard():
    return ReplyKeyboardMarkup([
        ["📊 Дашборд", "➕ Додати"],
        ["🏦 Monobank", "🤖 AI Аналіз"],
        ["📋 Записи", "💡 Інвестиції"],
        ["⚙️ Налаштування"]
    ], resize_keyboard=True)

async def send_dashboard(update, context, user_id=None):
    uid = user_id or update.effective_user.id
    data = load_data()
    udata = get_user_data(data, uid)
    month_key = get_month_key()
    month = udata["months"].get(month_key, {"income": [], "expenses": []})
    
    total_income = sum(i["amount_uah"] for i in month.get("income", []))
    total_expenses = sum(e["amount_uah"] for e in month.get("expenses", []))
    balance = total_income - total_expenses
    savings = sum(e["amount_uah"] for e in month.get("expenses", []) if e.get("category") in ["savings", "invest"])
    target = udata["settings"].get("target", 5000)
    
    rate = await get_usdt_rate()
    
    # Витрати по категоріям
    cat_totals = {}
    for e in month.get("expenses", []):
        cat = e.get("category", "other")
        cat_totals[cat] = cat_totals.get(cat, 0) + e["amount_uah"]
    
    # Прогрес накопичень
    pct = min(100, int((savings / target * 100))) if target > 0 else 0
    bar_filled = int(pct / 10)
    progress_bar = "█" * bar_filled + "░" * (10 - bar_filled)
    
    text = f"""
╔══════════════════════════╗
║  💰 *ФІНАНСОВИЙ МЕНЕДЖЕР*  ║
╚══════════════════════════╝

📅 *{get_month_label(month_key)}*
💱 Курс USDT: *{fmt_uah(rate)}*

━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 *Дохід:* {fmt_uah(total_income)}
📉 *Витрати:* {fmt_uah(total_expenses)}
💳 *Баланс:* {fmt_uah(balance)}
💰 *Накопичено:* {fmt_uah(savings)}

━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 *Ціль накопичень:* {fmt_uah(target)}
`{progress_bar}` {pct}%
"""
    
    if cat_totals:
        text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n📊 *Витрати по категоріям:*\n"
        for cat_id, amount in sorted(cat_totals.items(), key=lambda x: -x[1]):
            icon, name = CATEGORIES.get(cat_id, ("📦", cat_id))
            pct_cat = int(amount / total_expenses * 100) if total_expenses > 0 else 0
            text += f"{icon} {name}: *{fmt_uah(amount)}* ({pct_cat}%)\n"
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Оновити", callback_data="refresh_dashboard")
    ]])
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

# ═══════════════════════════════════════════
# ОБРОБНИКИ КОМАНД
# ═══════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    text = f"""
👋 *Привіт, {name}!*

Я твій персональний фінансовий менеджер 💰

*Що я вмію:*
• 📊 Відстежувати доходи і витрати
• 🤖 Розуміти звичайний текст — просто напиши що витратив
• 💱 Конвертувати USDT/USD в гривні за актуальним курсом
• 🏦 Синхронізуватись з Monobank
• 📈 Аналізувати фінанси та радити де заощадити
• 💡 Підказувати куди вкласти заощадження

*Просто напиши мені:*
_«витратив 350 на каву»_
_«зарплата 500 usdt»_
_«купив ліки за 280»_

І я сам все занесу! ✨
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    # Обробка кнопок меню
    if text == "📊 Дашборд":
        await send_dashboard(update, context)
        return
    elif text == "➕ Додати":
        await show_add_menu(update, context)
        return
    elif text == "🏦 Monobank":
        await show_mono_menu(update, context)
        return
    elif text == "🤖 AI Аналіз":
        await run_analysis(update, context)
        return
    elif text == "📋 Записи":
        await show_history(update, context)
        return
    elif text == "💡 Інвестиції":
        await show_invest(update, context)
        return
    elif text == "⚙️ Налаштування":
        await show_settings(update, context)
        return
    
    # Перевірка стану
    state = context.user_data.get("state")
    
    if state == "set_target":
        try:
            target = float(text.replace(" ", "").replace(",", "."))
            data = load_data()
            udata = get_user_data(data, uid)
            udata["settings"]["target"] = target
            save_data(data)
            context.user_data["state"] = None
            await update.message.reply_text(f"✅ Ціль накопичень встановлена: *{fmt_uah(target)}*", parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())
        except:
            await update.message.reply_text("❌ Введіть число, наприклад: 5000")
        return
    
    if state == "set_mono":
        token = text.strip()
        data = load_data()
        udata = get_user_data(data, uid)
        udata["settings"]["mono_token"] = token
        save_data(data)
        context.user_data["state"] = None
        await update.message.reply_text("✅ Токен збережено! Натисніть *🏦 Monobank* для синхронізації.", parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())
        return
    
    # AI розпізнавання фінансової операції
    await process_ai_input(update, context, text)

async def process_ai_input(update, context, text):
    uid = update.effective_user.id
    rate = await get_usdt_rate()
    
    msg = await update.message.reply_text("⏳ Аналізую...")
    
    cat_list = ", ".join([f"{k}: {v[1]}" for k, v in CATEGORIES.items()])
    inc_list = ", ".join([f"{k}: {v[1]}" for k, v in INCOME_TYPES.items()])
    
    prompt = f"""Ти — фінансовий асистент. Курс USDT/UAH: {rate:.2f}.
Проаналізуй текст і поверни ТІЛЬКИ JSON без markdown:
{{"type":"expense"або"income","amount":число,"currency":"UAH"або"USDT"або"USD","amount_uah":числоВгривнях,"category":"catId","income_type":"typeId","desc":"короткий опис","message":"підтвердження українською"}}
Категорії витрат: {cat_list}
Типи доходів: {inc_list}
Якщо не фінанси: {{"error":"повідомлення"}}
Текст: "{text}" """
    
    result = await ask_claude(prompt, 300)
    
    if not result:
        await msg.edit_text("❌ AI недоступний. Скористайтесь кнопкою ➕ Додати для ручного введення.")
        return
    
    try:
        parsed = json.loads(result.replace("```json", "").replace("```", "").strip())
    except:
        await msg.edit_text("❌ Не вдалось розпізнати. Спробуйте ще раз або скористайтесь ➕ Додати")
        return
    
    if "error" in parsed:
        await msg.edit_text(f"ℹ️ {parsed['error']}")
        return
    
    data = load_data()
    udata = get_user_data(data, uid)
    month_key = get_month_key()
    if month_key not in udata["months"]:
        udata["months"][month_key] = {"income": [], "expenses": []}
    
    entry = {
        "id": int(datetime.now().timestamp() * 1000),
        "amount": parsed.get("amount", 0),
        "currency": parsed.get("currency", "UAH"),
        "amount_uah": parsed.get("amount_uah", parsed.get("amount", 0)),
        "rate_used": rate if parsed.get("currency") != "UAH" else None,
        "desc": parsed.get("desc", ""),
        "date": datetime.now().isoformat(),
    }
    
    if parsed["type"] == "expense":
        entry["category"] = parsed.get("category", "other")
        udata["months"][month_key]["expenses"].append(entry)
        icon, name = CATEGORIES.get(entry["category"], ("📦", "Інше"))
        currency_str = f" ({fmt_usdt(entry['amount'])} × ₴{rate:.2f})" if entry["currency"] != "UAH" else ""
        response = f"✅ *{parsed.get('message', 'Додано!')}*\n\n{icon} {name}\n💸 {fmt_uah(entry['amount_uah'])}{currency_str}"
    else:
        entry["income_type"] = parsed.get("income_type", "other_income")
        udata["months"][month_key]["income"].append(entry)
        icon, name = INCOME_TYPES.get(entry["income_type"], ("➕", "Інше"))
        currency_str = f" ({fmt_usdt(entry['amount'])} × ₴{rate:.2f})" if entry["currency"] != "UAH" else ""
        response = f"✅ *{parsed.get('message', 'Додано!')}*\n\n{icon} {name}\n💰 {fmt_uah(entry['amount_uah'])}{currency_str}"
    
    save_data(data)
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📊 Дашборд", callback_data="dashboard"),
        InlineKeyboardButton("🗑 Видалити", callback_data=f"del_{parsed['type']}_{entry['id']}_{month_key}")
    ]])
    await msg.edit_text(response, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

# ═══════════════════════════════════════════
# ДОДАТИ ВРУЧНУ
# ═══════════════════════════════════════════
async def show_add_menu(update, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📉 Витрата", callback_data="add_expense"),
         InlineKeyboardButton("📈 Дохід", callback_data="add_income")],
    ])
    await update.message.reply_text("*Що додати?*", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

# ═══════════════════════════════════════════
# MONOBANK
# ═══════════════════════════════════════════
async def show_mono_menu(update, context):
    uid = update.effective_user.id
    data = load_data()
    udata = get_user_data(data, uid)
    token = udata["settings"].get("mono_token", "")
    
    if not token:
        text = """
🏦 *Підключення Monobank*

Для підключення потрібен токен API.

*Як отримати:*
1. Відкрийте браузер
2. Зайдіть на *api.monobank.ua*
3. Авторизуйтесь QR-кодом з додатку Mono
4. Скопіюйте токен
5. Надішліть його мені

⚠️ Токен зберігається лише на сервері бота і ніде не передається.
"""
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔑 Ввести токен", callback_data="enter_mono_token")
        ]])
    else:
        text = "🏦 *Monobank підключено* ✅\n\nОберіть дію:"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Синхронізувати", callback_data="sync_mono")],
            [InlineKeyboardButton("❌ Відключити", callback_data="disconnect_mono")]
        ])
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def sync_monobank(update, context):
    uid = update.effective_user.id
    data = load_data()
    udata = get_user_data(data, uid)
    token = udata["settings"].get("mono_token", "")
    
    if not token:
        await update.callback_query.answer("❌ Токен не встановлено")
        return
    
    await update.callback_query.edit_message_text("⏳ Синхронізую з Monobank...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Отримати рахунки
            async with session.get("https://api.monobank.ua/personal/client-info",
                                   headers={"X-Token": token}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    await update.callback_query.edit_message_text("❌ Невірний токен Monobank")
                    return
                info = await r.json()
            
            accounts = info.get("accounts", [])
            if not accounts:
                await update.callback_query.edit_message_text("❌ Рахунки не знайдені")
                return
            
            # Вибрати перший UAH рахунок
            account = next((a for a in accounts if a.get("currencyCode") == 980), accounts[0])
            account_id = account["id"]
            
            # Отримати транзакції за поточний місяць
            now = datetime.now()
            from_ts = int(datetime(now.year, now.month, 1).timestamp())
            to_ts = int(now.timestamp())
            
            await asyncio.sleep(1)  # Rate limit
            async with session.get(
                f"https://api.monobank.ua/personal/statement/{account_id}/{from_ts}/{to_ts}",
                headers={"X-Token": token}, timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status != 200:
                    err = await r.json()
                    await update.callback_query.edit_message_text(f"❌ {err.get('errorDescription', 'Помилка')}")
                    return
                transactions = await r.json()
        
        if not isinstance(transactions, list):
            await update.callback_query.edit_message_text("❌ Помилка відповіді від Monobank")
            return
        
        month_key = get_month_key()
        if month_key not in udata["months"]:
            udata["months"][month_key] = {"income": [], "expenses": []}
        
        existing_ids = set(
            e.get("mono_id") for e in udata["months"][month_key].get("expenses", []) + udata["months"][month_key].get("income", [])
            if e.get("mono_id")
        )
        
        new_count = 0
        for tx in transactions:
            if tx["id"] in existing_ids:
                continue
            
            amount = abs(tx["amount"]) / 100
            is_expense = tx["amount"] < 0
            desc = tx.get("description", "") or tx.get("comment", "") or "Транзакція Mono"
            mcc = tx.get("mcc", 0)
            
            # Проста категоризація по MCC
            cat = "other"
            mcc_map = {
                "food": [5411,5412,5441,5451,5462,5499,5812,5813,5814],
                "transport": [4111,4121,4511,5541,5542,7523],
                "health": [5122,5912,8011,8021,8062],
                "fun": [5815,5816,7832,7841,7922,7993],
            }
            for cat_id, mccs in mcc_map.items():
                if mcc in mccs:
                    cat = cat_id
                    break
            
            entry = {
                "id": int(datetime.now().timestamp() * 1000) + new_count,
                "mono_id": tx["id"],
                "amount": amount,
                "currency": "UAH",
                "amount_uah": amount,
                "desc": desc,
                "date": datetime.fromtimestamp(tx["time"]).isoformat(),
                "source": "monobank",
            }
            
            if is_expense:
                entry["category"] = cat
                udata["months"][month_key]["expenses"].append(entry)
            else:
                entry["income_type"] = "other_income"
                udata["months"][month_key]["income"].append(entry)
            
            new_count += 1
        
        save_data(data)
        
        if new_count == 0:
            await update.callback_query.edit_message_text("✅ Все актуально — нових транзакцій немає!")
        else:
            await update.callback_query.edit_message_text(
                f"✅ Синхронізовано!\n\nДодано *{new_count}* нових транзакцій з Monobank 🏦",
                parse_mode=ParseMode.MARKDOWN
            )
    
    except Exception as e:
        await update.callback_query.edit_message_text(f"❌ Помилка: {str(e)[:100]}")

# ═══════════════════════════════════════════
# AI АНАЛІЗ
# ═══════════════════════════════════════════
async def run_analysis(update, context):
    uid = update.effective_user.id
    
    if update.message:
        msg = await update.message.reply_text("🤖 Аналізую ваші фінанси...")
    else:
        msg = await update.callback_query.edit_message_text("🤖 Аналізую ваші фінанси...")
    
    data = load_data()
    udata = get_user_data(data, uid)
    month_key = get_month_key()
    month = udata["months"].get(month_key, {"income": [], "expenses": []})
    
    total_income = sum(i["amount_uah"] for i in month.get("income", []))
    total_expenses = sum(e["amount_uah"] for e in month.get("expenses", []))
    balance = total_income - total_expenses
    savings = sum(e["amount_uah"] for e in month.get("expenses", []) if e.get("category") in ["savings", "invest"])
    target = udata["settings"].get("target", 5000)
    
    cat_totals = {}
    for e in month.get("expenses", []):
        cat = e.get("category", "other")
        cat_totals[cat] = cat_totals.get(cat, 0) + e["amount_uah"]
    
    cat_summary = ", ".join([f"{CATEGORIES.get(k, ('', k))[1]}: {fmt_uah(v)}" for k, v in cat_totals.items()])
    savings_pct = int(savings / total_income * 100) if total_income > 0 else 0
    
    prompt = f"""Ти — дружній фінансовий аналітик. Говори українською, чітко і по справі.

Дані за {get_month_label(month_key)}:
- Дохід: {fmt_uah(total_income)}, Витрати: {fmt_uah(total_expenses)}, Баланс: {fmt_uah(balance)}
- Накопичено: {fmt_uah(savings)} ({savings_pct}% від доходу), Ціль: {fmt_uah(target)}
- По категоріям: {cat_summary or "немає даних"}

Зроби аналіз:
📊 Загальна картина — 2 речення
🔴 На чому зекономити — 2-3 конкретні пункти з цифрами
✅ Що добре — 1-2 пункти
💡 Порада на сьогодні — одна конкретна дія"""
    
    result = await ask_claude(prompt, 600)
    
    if not result:
        if update.message:
            await msg.edit_text("❌ AI недоступний. Перевірте наявність API ключа.")
        else:
            await msg.edit_text("❌ AI недоступний.")
        return
    
    text = f"🤖 *AI Аналіз — {get_month_label(month_key)}*\n\n{result}"
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Оновити", callback_data="analysis")
    ]])
    
    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

# ═══════════════════════════════════════════
# ІНВЕСТИЦІЇ
# ═══════════════════════════════════════════
async def show_invest(update, context):
    uid = update.effective_user.id
    msg = await update.message.reply_text("💡 Формую рекомендації...")
    
    data = load_data()
    udata = get_user_data(data, uid)
    month_key = get_month_key()
    month = udata["months"].get(month_key, {"income": [], "expenses": []})
    
    total_income = sum(i["amount_uah"] for i in month.get("income", []))
    total_expenses = sum(e["amount_uah"] for e in month.get("expenses", []))
    balance = max(0, total_income - total_expenses)
    rate = await get_usdt_rate()
    
    prompt = f"""Ти — фінансовий консультант. Говори українською. 
Попередь що це загальна інформація, не фінансова порада.

Вільний капітал: {fmt_uah(balance)} ({fmt_usdt(balance/rate)}), Дохід: {fmt_uah(total_income)}

Дай 4 варіанти куди вкласти від найнижчого до найвищого ризику:
1. ОВДП
2. Депозит в українському банку  
3. ETF через Interactive Brokers або Freedom Finance
4. Стейкінг USDT на Binance

Для кожного: назва, очікувана дохідність за місяць, конкретна сума і результат через місяць для клієнта, головний ризик.
Формат: емоджі + назва, потім деталі. Коротко і конкретно."""
    
    result = await ask_claude(prompt, 800)
    
    if not result:
        await msg.edit_text("❌ AI недоступний.")
        return
    
    text = f"💡 *Куди вкласти заощадження*\n\n⚠️ _Це загальна інформація, не фінансова порада. Ризики несете самостійно._\n\n💳 Вільний капітал: *{fmt_uah(balance)}*\n\n{result}"
    
    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)

# ═══════════════════════════════════════════
# ЗАПИСИ
# ═══════════════════════════════════════════
async def show_history(update, context):
    uid = update.effective_user.id
    data = load_data()
    udata = get_user_data(data, uid)
    month_key = get_month_key()
    month = udata["months"].get(month_key, {"income": [], "expenses": []})
    
    expenses = month.get("expenses", [])[-10:]
    income = month.get("income", [])[-5:]
    
    if not expenses and not income:
        await update.message.reply_text("📋 Записів поки немає. Напишіть мені про витрату або дохід!")
        return
    
    text = f"📋 *Останні записи — {get_month_label(month_key)}*\n\n"
    
    if income:
        text += "💰 *Доходи:*\n"
        for i in reversed(income[-5:]):
            icon, name = INCOME_TYPES.get(i.get("income_type", "other_income"), ("➕", "Інше"))
            source = " 🏦" if i.get("source") == "monobank" else ""
            text += f"{icon} {i['desc']}{source} — *{fmt_uah(i['amount_uah'])}*\n"
    
    if expenses:
        text += "\n📉 *Витрати:*\n"
        for e in reversed(expenses[-10:]):
            icon, name = CATEGORIES.get(e.get("category", "other"), ("📦", "Інше"))
            source = " 🏦" if e.get("source") == "monobank" else ""
            text += f"{icon} {e['desc']}{source} — *{fmt_uah(e['amount_uah'])}*\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ═══════════════════════════════════════════
# НАЛАШТУВАННЯ
# ═══════════════════════════════════════════
async def show_settings(update, context):
    uid = update.effective_user.id
    data = load_data()
    udata = get_user_data(data, uid)
    target = udata["settings"].get("target", 5000)
    has_mono = bool(udata["settings"].get("mono_token", ""))
    
    text = f"""
⚙️ *Налаштування*

🎯 Ціль накопичень: *{fmt_uah(target)}*
🏦 Monobank: *{"Підключено ✅" if has_mono else "Не підключено"}*
"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Змінити ціль", callback_data="set_target")],
        [InlineKeyboardButton("🏦 Налаштування Mono", callback_data="mono_settings")],
    ])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

# ═══════════════════════════════════════════
# CALLBACK ОБРОБНИК
# ═══════════════════════════════════════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_cb = query.data
    uid = update.effective_user.id
    
    if data_cb == "dashboard" or data_cb == "refresh_dashboard":
        await send_dashboard(update, context, uid)
    
    elif data_cb == "analysis":
        await run_analysis(update, context)
    
    elif data_cb == "sync_mono":
        await sync_monobank(update, context)
    
    elif data_cb == "enter_mono_token":
        context.user_data["state"] = "set_mono"
        await query.edit_message_text(
            "🔑 Введіть ваш токен Monobank:\n\n_(Отримайте на api.monobank.ua)_",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data_cb == "disconnect_mono":
        data = load_data()
        udata = get_user_data(data, uid)
        udata["settings"]["mono_token"] = ""
        save_data(data)
        await query.edit_message_text("✅ Monobank відключено")
    
    elif data_cb == "set_target":
        context.user_data["state"] = "set_target"
        await query.edit_message_text("🎯 Введіть суму цілі накопичень (₴):\n\nНаприклад: *5000*", parse_mode=ParseMode.MARKDOWN)
    
    elif data_cb == "mono_settings":
        data = load_data()
        udata = get_user_data(data, uid)
        has_mono = bool(udata["settings"].get("mono_token", ""))
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Змінити токен", callback_data="enter_mono_token")],
            [InlineKeyboardButton("🔄 Синхронізувати", callback_data="sync_mono")] if has_mono else [],
            [InlineKeyboardButton("❌ Відключити", callback_data="disconnect_mono")] if has_mono else [],
        ])
        await query.edit_message_text("🏦 *Налаштування Monobank*", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    
    elif data_cb.startswith("del_"):
        parts = data_cb.split("_")
        entry_type = parts[1]
        entry_id = int(parts[2])
        month_key = parts[3]
        
        data = load_data()
        udata = get_user_data(data, uid)
        
        if entry_type == "expense":
            udata["months"][month_key]["expenses"] = [
                e for e in udata["months"][month_key].get("expenses", []) if e["id"] != entry_id
            ]
        else:
            udata["months"][month_key]["income"] = [
                i for i in udata["months"][month_key].get("income", []) if i["id"] != entry_id
            ]
        
        save_data(data)
        await query.edit_message_text("🗑 Запис видалено")

# ═══════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не встановлено!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🚀 Бот запущено!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
