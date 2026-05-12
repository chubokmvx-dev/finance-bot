# 🏙️ Chernivtsi Bot — автопостинг новин у Telegram

## Структура проєкту
```
chernivtsi_bot/
├── main.py              — планувальник, точка входу
├── config.py            — всі налаштування
├── database.py          — SQLite (дедублікація, стан матчу)
├── news_fetcher.py      — парсинг RSS-стрічок
├── ai_processor.py      — фільтрація та форматування через Claude AI
├── telegram_poster.py   — публікація в Telegram
├── football_tracker.py  — live-рахунок Буковини
├── poll_manager.py      — опитування (1-2 на день)
├── requirements.txt
└── .env                 — твої ключі (не комітити!)
```

---

## Крок 1 — Telegram-бот

1. Напиши [@BotFather](https://t.me/BotFather) → `/newbot`
2. Отримай `TELEGRAM_BOT_TOKEN`
3. Додай бота адміністратором у свій канал
4. `TELEGRAM_CHANNEL_ID` = юзернейм каналу (`@mychannel`) або числовий ID

---

## Крок 2 — Claude API

1. Зареєструйся на [console.anthropic.com](https://console.anthropic.com)
2. Створи API Key → `ANTHROPIC_API_KEY`
3. Безкоштовного кредиту вистачить на старт

---

## Крок 3 — Football API (для Буковини)

1. Зареєструйся на [RapidAPI](https://rapidapi.com/api-sports/api/api-football)
2. Підпишись на **безкоштовний** план (100 запитів/день — вистачає)
3. Скопіюй ключ → `FOOTBALL_API_KEY`
4. Знайди ID Буковини:
   ```
   GET https://api-football-v1.p.rapidapi.com/v3/teams?name=Буковина&country=Ukraine
   ```
   Скопіюй `team.id` → встав у `config.py` замість `BUKOVYNA_TEAM_ID`

---

## Крок 4 — Запуск

```bash
# Клонуй або скопіюй папку на сервер
cd chernivtsi_bot

# Встанови залежності
pip install -r requirements.txt

# Заповни .env
cp .env.example .env
nano .env

# Запуск
python main.py
```

### Для запуску у фоні (на VPS):
```bash
# Через screen
screen -S chernivtsibot
python main.py
# Ctrl+A, D — відʼєднатись від screen

# Або через systemd-сервіс (надійніше)
# Напиши /etc/systemd/system/chernivtsibot.service
```

### Безкоштовний хостинг:
- **Railway.app** — просто підʼєднай GitHub-репозиторій
- **Render.com** — Worker service, безкоштовний tier

---

## Що робить бот

| Подія | Дія |
|---|---|
| Кожні 20 хв | Перевіряє RSS, AI відбирає найцікавіше, публікує 1-2 пости |
| При зміні рахунку | Публікує оновлення з відповіддю на анонс матчу |
| Вранці (08:00) | Анонс матчу Буковини (якщо є найближчих 3 дні) |
| Після анонсу | Опитування "Хто виграє?" |
| 1-2 рази на день | Контекстне опитування до цікавої новини |

---

## Налаштування під себе

У `config.py`:
- `NEWS_FETCH_INTERVAL_MIN` — як часто перевіряти новини
- `MAX_POSTS_PER_CYCLE` — скільки постів за один цикл
- `MAX_POLLS_PER_DAY` — ліміт опитувань
- `RSS_FEEDS` — додавай/прибирай джерела

У `ai_processor.py` → `FORMAT_SYSTEM` — можна змінити стиль подачі матеріалу.
