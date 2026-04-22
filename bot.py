import os, json, logging, aiohttp
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# ── DATA ──────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data, uid):
    k = str(uid)
    if k not in data:
        data[k] = {"months": {}, "settings": {"target": 5000, "mono_token": ""}}
    return data[k]

def mk():
    return datetime.now().strftime("%Y-%m")

def ml(key):
    y, m = key.split("-")
    names = ["","Січень","Лютий","Березень","Квітень","Травень","Червень","Липень","Серпень","Вересень","Жовтень","Листопад","Грудень"]
    return f"{names[int(m)]} {y}"

def fmt(n): return f"{n:,.0f} ₴".replace(",", " ")
def fmtd(n): return f"${n:.2f}"

# ── APIS ──────────────────────────────────────────────
async def get_rate():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.binance.com/api/v3/ticker/price?symbol=USDTUAH",
                             timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    j = await r.json()
                    return float(j["price"])
    except Exception as e:
        logger.warning(f"Rate fetch failed: {e}")
    return 41.5

async def ask_claude(prompt: str, max_tokens: int = 600) -> str | None:
    if not ANTHROPIC_KEY:
        logger.error("ANTHROPIC_KEY not set!")
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                if r.status != 200:
                    text = await r.text()
                    logger.error(f"Claude API error {r.status}: {text}")
                    return None
                data = await r.json()
                return data["content"][0]["text"]
    except Exception as e:
        logger.error(f"Claude request failed: {e}")
        return None

# ── KEYBOARDS ─────────────────────────────────────────
def main_kb():
    return ReplyKeyboardMarkup([
        ["📊 Дашборд", "➕ Додати"],
        ["🏦 Monobank", "🤖 AI Аналіз"],
        ["📋 Записи", "💡 Інвестиції"],
        ["⚙️ Налаштування"],
    ], resize_keyboard=True)

# ── HANDLERS ──────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Привіт, {name}!\n\n"
        "Я твій фінансовий менеджер 💰\n\n"
        "Просто напиши мені:\n"
        "• «витратив 350 на каву»\n"
        "• «зарплата 500 usdt»\n"
        "• «купив ліки за 280»\n\n"
        "І я сам все занесу! ✨",
        reply_markup=main_kb(),
    )

async def send_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_data()
    u = get_user(data, uid)
    month = u["months"].get(mk(), {"income": [], "expenses": []})

    inc = sum(i["amount_uah"] for i in month.get("income", []))
    exp = sum(e["amount_uah"] for e in month.get("expenses", []))
    bal = inc - exp
    sav = sum(e["amount_uah"] for e in month.get("expenses", []) if e.get("category") in ["savings", "invest"])
    tgt = u["settings"].get("target", 5000)
    rate = await get_rate()
    pct = min(100, int(sav / tgt * 100)) if tgt > 0 else 0
    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))

    cats = {}
    for e in month.get("expenses", []):
        c = e.get("category", "other")
        cats[c] = cats.get(c, 0) + e["amount_uah"]

    text = (
        f"╔══════════════════════╗\n"
        f"║  💰 ФІНАНСОВИЙ МЕНЕДЖЕР  ║\n"
        f"╚══════════════════════╝\n\n"
        f"📅 {ml(mk())}\n"
        f"💱 Курс USDT: {fmt(rate)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📈 Дохід: {fmt(inc)}\n"
        f"📉 Витрати: {fmt(exp)}\n"
        f"💳 Баланс: {fmt(bal)}\n"
        f"💰 Накопичено: {fmt(sav)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Ціль: {fmt(tgt)}\n"
        f"{bar} {pct}%"
    )

    if cats:
        text += "\n\n━━━━━━━━━━━━━━━━━━━━━━\n\n📊 По категоріям:\n"
        for cid, amt in sorted(cats.items(), key=lambda x: -x[1]):
            icon, cname = CATEGORIES.get(cid, ("📦", cid))
            p = int(amt / exp * 100) if exp > 0 else 0
            text += f"{icon} {cname}: {fmt(amt)} ({p}%)\n"

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Оновити", callback_data="dashboard")]])
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)

async def process_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    uid = update.effective_user.id
    rate = await get_rate()
    msg = await update.message.reply_text("⏳ Аналізую...")

    cats = ", ".join([f"{k}: {v[1]}" for k, v in CATEGORIES.items()])
    incs = ", ".join([f"{k}: {v[1]}" for k, v in INCOME_TYPES.items()])

    prompt = (
        f"Ти фінансовий асистент. Курс USDT/UAH: {rate:.2f}.\n"
        f"Проаналізуй текст і поверни ТІЛЬКИ валідний JSON без markdown:\n"
        f'{{"type":"expense або income","amount":число,"currency":"UAH або USDT або USD",'
        f'"amount_uah":сума_в_гривнях,"category":"catId","income_type":"typeId","desc":"опис","message":"підтвердження"}}\n'
        f"Категорії витрат: {cats}\n"
        f"Типи доходів: {incs}\n"
        f'Якщо не фінанси: {{"error":"не фінансова операція"}}\n'
        f'Текст: "{text}"'
    )

    res = await ask_claude(prompt, 400)
    if not res:
        await msg.edit_text("❌ AI недоступний. Скористайтесь ➕ Додати")
        return

    # Очищення відповіді від markdown
    cleaned = res.strip()
    if "```" in cleaned:
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}, raw: {res}")
        await msg.edit_text("❌ Не вдалось розпізнати. Спробуйте ще раз або скористайтесь ➕ Додати")
        return

    if "error" in parsed:
        await msg.edit_text(f"ℹ️ {parsed['error']}")
        return

    data = load_data()
    u = get_user(data, uid)
    m = mk()
    if m not in u["months"]:
        u["months"][m] = {"income": [], "expenses": []}

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
        u["months"][m]["expenses"].append(entry)
        icon, cname = CATEGORIES.get(entry["category"], ("📦", "Інше"))
        cs = f" ({fmtd(entry['amount'])} × ₴{rate:.2f})" if entry["currency"] != "UAH" else ""
        resp = f"✅ {parsed.get('message', 'Додано!')}\n\n{icon} {cname}\n💸 {fmt(entry['amount_uah'])}{cs}"
    else:
        entry["income_type"] = parsed.get("income_type", "other_income")
        u["months"][m]["income"].append(entry)
        icon, iname = INCOME_TYPES.get(entry["income_type"], ("➕", "Інше"))
        cs = f" ({fmtd(entry['amount'])} × ₴{rate:.2f})" if entry["currency"] != "UAH" else ""
        resp = f"✅ {parsed.get('message', 'Додано!')}\n\n{icon} {iname}\n💰 {fmt(entry['amount_uah'])}{cs}"

    save_data(data)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📊 Дашборд", callback_data="dashboard"),
        InlineKeyboardButton("🗑 Видалити", callback_data=f"del_{parsed['type']}_{entry['id']}_{m}"),
    ]])
    await msg.edit_text(resp, reply_markup=kb)

async def show_mono(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_data()
    u = get_user(data, uid)
    token = u["settings"].get("mono_token", "")
    if not token:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔑 Ввести токен", callback_data="enter_mono")]])
        await update.message.reply_text(
            "🏦 Підключення Monobank\n\n"
            "1. Відкрийте api.monobank.ua\n"
            "2. Авторизуйтесь QR-кодом\n"
            "3. Скопіюйте токен і надішліть мені",
            reply_markup=kb,
        )
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Синхронізувати", callback_data="sync_mono")],
            [InlineKeyboardButton("❌ Відключити", callback_data="disc_mono")],
        ])
        await update.message.reply_text("🏦 Monobank підключено ✅\n\nОберіть дію:", reply_markup=kb)

async def do_sync_mono(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_data()
    u = get_user(data, uid)
    token = u["settings"].get("mono_token", "")
    if not token:
        await update.callback_query.answer("❌ Токен не встановлено")
        return
    await update.callback_query.edit_message_text("⏳ Синхронізую з Monobank...")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.monobank.ua/personal/client-info",
                             headers={"X-Token": token},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    await update.callback_query.edit_message_text("❌ Невірний токен Monobank")
                    return
                info = await r.json()

            accounts = info.get("accounts", [])
            account = next((a for a in accounts if a.get("currencyCode") == 980), accounts[0] if accounts else None)
            if not account:
                await update.callback_query.edit_message_text("❌ Рахунки не знайдені")
                return

            now = datetime.now()
            from_ts = int(datetime(now.year, now.month, 1).timestamp())
            to_ts = int(now.timestamp())

            await asyncio.sleep(1)
            async with s.get(
                f"https://api.monobank.ua/personal/statement/{account['id']}/{from_ts}/{to_ts}",
                headers={"X-Token": token},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status != 200:
                    err = await r.json()
                    await update.callback_query.edit_message_text(f"❌ {err.get('errorDescription', 'Помилка')}")
                    return
                transactions = await r.json()

        if not isinstance(transactions, list):
            await update.callback_query.edit_message_text("✅ Нових транзакцій немає")
            return

        m = mk()
        if m not in u["months"]:
            u["months"][m] = {"income": [], "expenses": []}

        existing = set(
            e.get("mono_id") for e in
            u["months"][m].get("expenses", []) + u["months"][m].get("income", [])
            if e.get("mono_id")
        )

        mcc_map = {
            "food": [5411,5412,5441,5451,5462,5499,5812,5813,5814],
            "transport": [4111,4121,4511,5541,5542,7523],
            "health": [5122,5912,8011,8021,8062],
            "fun": [5815,5816,7832,7841,7922,7993],
        }

        count = 0
        for tx in transactions:
            if tx["id"] in existing:
                continue
            amount = abs(tx["amount"]) / 100
            desc = tx.get("description") or tx.get("comment") or "Mono транзакція"
            mcc = tx.get("mcc", 0)
            cat = "other"
            for cat_id, mccs in mcc_map.items():
                if mcc in mccs:
                    cat = cat_id
                    break
            entry = {
                "id": int(datetime.now().timestamp() * 1000) + count,
                "mono_id": tx["id"],
                "amount": amount,
                "currency": "UAH",
                "amount_uah": amount,
                "desc": desc,
                "date": datetime.fromtimestamp(tx["time"]).isoformat(),
                "source": "monobank",
            }
            if tx["amount"] < 0:
                entry["category"] = cat
                u["months"][m]["expenses"].append(entry)
            else:
                entry["income_type"] = "other_income"
                u["months"][m]["income"].append(entry)
            count += 1

        save_data(data)
        if count == 0:
            await update.callback_query.edit_message_text("✅ Все актуально — нових транзакцій немає!")
        else:
            await update.callback_query.edit_message_text(f"✅ Додано {count} нових транзакцій з Monobank 🏦")
    except Exception as e:
        logger.error(f"Mono sync error: {e}")
        await update.callback_query.edit_message_text(f"❌ Помилка синхронізації: {str(e)[:100]}")

async def run_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = await (update.message or update.callback_query).reply_text("🤖 Аналізую ваші фінанси...")
    if update.callback_query:
        msg = await update.callback_query.edit_message_text("🤖 Аналізую...")

    data = load_data()
    u = get_user(data, uid)
    month = u["months"].get(mk(), {"income": [], "expenses": []})
    inc = sum(i["amount_uah"] for i in month.get("income", []))
    exp = sum(e["amount_uah"] for e in month.get("expenses", []))
    sav = sum(e["amount_uah"] for e in month.get("expenses", []) if e.get("category") in ["savings","invest"])
    tgt = u["settings"].get("target", 5000)
    cats = {}
    for e in month.get("expenses", []):
        c = e.get("category","other")
        cats[c] = cats.get(c,0) + e["amount_uah"]
    cat_str = ", ".join([f"{CATEGORIES.get(k,('',''))[1]}: {fmt(v)}" for k,v in cats.items()]) or "немає даних"
    pct = int(sav/inc*100) if inc > 0 else 0

    prompt = (
        f"Ти дружній фінансовий аналітик. Відповідай українською, чітко.\n"
        f"Дані за {ml(mk())}:\n"
        f"Дохід: {fmt(inc)}, Витрати: {fmt(exp)}, Баланс: {fmt(inc-exp)}\n"
        f"Накопичено: {fmt(sav)} ({pct}%), Ціль: {fmt(tgt)}\n"
        f"По категоріям: {cat_str}\n\n"
        f"Зроби аналіз:\n"
        f"📊 Загальна картина — 2 речення\n"
        f"🔴 На чому зекономити — 2-3 пункти з цифрами\n"
        f"✅ Що добре — 1-2 пункти\n"
        f"💡 Порада на сьогодні — одна конкретна дія"
    )

    res = await ask_claude(prompt, 600)
    if not res:
        await msg.edit_text("❌ AI недоступний")
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Оновити", callback_data="analysis")]])
    await msg.edit_text(f"🤖 AI Аналіз — {ml(mk())}\n\n{res}", reply_markup=kb)

async def show_invest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = await update.message.reply_text("💡 Формую рекомендації...")
    data = load_data(); u = get_user(data, uid)
    month = u["months"].get(mk(), {"income":[],"expenses":[]})
    inc = sum(i["amount_uah"] for i in month.get("income",[]))
    exp = sum(e["amount_uah"] for e in month.get("expenses",[]))
    bal = max(0, inc - exp)
    rate = await get_rate()

    prompt = (
        f"Ти фінансовий консультант. Відповідай українською.\n"
        f"Попередь що це загальна інформація, не фінансова порада.\n"
        f"Вільний капітал: {fmt(bal)} ({fmtd(bal/rate)}), Дохід: {fmt(inc)}\n"
        f"Дай 4 варіанти від низького до високого ризику: ОВДП, депозит в банку, ETF, стейкінг USDT на Binance.\n"
        f"Для кожного: очікувана дохідність за місяць, конкретна сума і результат, головний ризик."
    )

    res = await ask_claude(prompt, 1000)
    if not res:
        await msg.edit_text("❌ AI недоступний")
        return

    header = (
        f"💡 Куди вкласти заощадження\n\n"
        f"⚠️ Загальна інформація, не фінансова порада.\n\n"
        f"💳 Вільний капітал: {fmt(bal)}\n\n"
    )
    full_text = header + res

    # Розбиваємо на частини якщо довше 4000 символів
    if len(full_text) <= 4000:
        await msg.edit_text(full_text)
    else:
        await msg.edit_text(header + res[:4000 - len(header)])
        remaining = res[4000 - len(header):]
        while remaining:
            chunk = remaining[:4000]
            remaining = remaining[4000:]
            await update.message.reply_text(chunk)
    return

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_data(); u = get_user(data, uid)
    month = u["months"].get(mk(), {"income":[],"expenses":[]})
    expenses = month.get("expenses",[])[-10:]
    income = month.get("income",[])[-5:]

    if not expenses and not income:
        await update.message.reply_text("📋 Записів поки немає!")
        return

    text = f"📋 Останні записи — {ml(mk())}\n\n"
    if income:
        text += "💰 Доходи:\n"
        for i in reversed(income):
            icon, name = INCOME_TYPES.get(i.get("income_type","other_income"), ("➕","Інше"))
            src = " 🏦" if i.get("source") == "monobank" else ""
            text += f"{icon} {i['desc']}{src} — {fmt(i['amount_uah'])}\n"
    if expenses:
        text += "\n📉 Витрати:\n"
        for e in reversed(expenses):
            icon, name = CATEGORIES.get(e.get("category","other"), ("📦","Інше"))
            src = " 🏦" if e.get("source") == "monobank" else ""
            text += f"{icon} {e['desc']}{src} — {fmt(e['amount_uah'])}\n"

    await update.message.reply_text(text)

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_data(); u = get_user(data, uid)
    tgt = u["settings"].get("target", 5000)
    has_mono = bool(u["settings"].get("mono_token",""))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Змінити ціль", callback_data="set_target")],
        [InlineKeyboardButton("🏦 Налаштування Mono", callback_data="mono_settings")],
    ])
    await update.message.reply_text(
        f"⚙️ Налаштування\n\n"
        f"🎯 Ціль накопичень: {fmt(tgt)}\n"
        f"🏦 Monobank: {'Підключено ✅' if has_mono else 'Не підключено'}",
        reply_markup=kb,
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    uid = update.effective_user.id

    if d == "dashboard":
        await send_dashboard(update, context)
    elif d == "analysis":
        await run_analysis(update, context)
    elif d == "sync_mono":
        await do_sync_mono(update, context)
    elif d == "enter_mono":
        context.user_data["state"] = "set_mono"
        await q.edit_message_text("🔑 Введіть ваш токен Monobank:\n\n(Отримайте на api.monobank.ua)")
    elif d == "disc_mono":
        data = load_data(); u = get_user(data, uid)
        u["settings"]["mono_token"] = ""; save_data(data)
        await q.edit_message_text("✅ Monobank відключено")
    elif d == "set_target":
        context.user_data["state"] = "set_target"
        await q.edit_message_text("🎯 Введіть суму цілі накопичень (₴):\n\nНаприклад: 5000")
    elif d == "mono_settings":
        data = load_data(); u = get_user(data, uid)
        has = bool(u["settings"].get("mono_token",""))
        btns = [[InlineKeyboardButton("🔑 Змінити токен", callback_data="enter_mono")]]
        if has:
            btns.append([InlineKeyboardButton("🔄 Синхронізувати", callback_data="sync_mono")])
            btns.append([InlineKeyboardButton("❌ Відключити", callback_data="disc_mono")])
        await q.edit_message_text("🏦 Налаштування Monobank", reply_markup=InlineKeyboardMarkup(btns))
    elif d.startswith("del_"):
        parts = d.split("_")
        etype, eid, emk = parts[1], int(parts[2]), parts[3]
        data = load_data(); u = get_user(data, uid)
        if etype == "expense":
            u["months"][emk]["expenses"] = [e for e in u["months"][emk].get("expenses",[]) if e["id"] != eid]
        else:
            u["months"][emk]["income"] = [i for i in u["months"][emk].get("income",[]) if i["id"] != eid]
        save_data(data)
        await q.edit_message_text("🗑 Запис видалено")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    state = context.user_data.get("state")

    if text == "📊 Дашборд": await send_dashboard(update, context); return
    if text == "🏦 Monobank": await show_mono(update, context); return
    if text == "🤖 AI Аналіз": await run_analysis(update, context); return
    if text == "📋 Записи": await show_history(update, context); return
    if text == "💡 Інвестиції": await show_invest(update, context); return
    if text == "⚙️ Налаштування": await show_settings(update, context); return
    if text == "➕ Додати":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("📉 Витрата", callback_data="add_exp"),
            InlineKeyboardButton("📈 Дохід", callback_data="add_inc"),
        ]])
        await update.message.reply_text("Що додати?", reply_markup=kb)
        return

    if state == "set_target":
        try:
            t = float(text.replace(" ","").replace(",","."))
            data = load_data(); u = get_user(data, uid)
            u["settings"]["target"] = t; save_data(data)
            context.user_data["state"] = None
            await update.message.reply_text(f"✅ Ціль: {fmt(t)}", reply_markup=main_kb())
        except:
            await update.message.reply_text("❌ Введіть число, наприклад: 5000")
        return

    if state == "set_mono":
        data = load_data(); u = get_user(data, uid)
        u["settings"]["mono_token"] = text.strip(); save_data(data)
        context.user_data["state"] = None
        await update.message.reply_text("✅ Токен збережено!", reply_markup=main_kb())
        return

    await process_ai(update, context, text)

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    import asyncio
    main()
