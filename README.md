# 🤖 Crypto Autopost Bot — Threads + Telegram

Автоматически генерирует крипто-посты (текст + картинка) и публикует в Threads.
Новые комментарии приходят в Telegram — ты отвечаешь кнопкой прямо из бота.

---

## Как работает

```
Claude API → генерирует текст поста
Pollinations.ai → генерирует картинку (бесплатно)
Threads API → публикует пост
         ↓
     каждые 5 мин
         ↓
Threads API → проверяет новые комменты
         ↓
Telegram бот → присылает коммент + кнопки [Ответить / Игнор]
         ↓
Ты пишешь ответ → бот публикует его в Threads
```

---

## 1. Получи все токены

### Telegram Bot
1. Напиши @BotFather → `/newbot`
2. Скопируй токен → `TELEGRAM_BOT_TOKEN`
3. Напиши @userinfobot → скопируй свой ID → `TELEGRAM_CHAT_ID`

### Anthropic API
1. https://console.anthropic.com → API Keys → Create Key
2. → `ANTHROPIC_API_KEY`

### Threads (Meta)
1. Зайди на https://developers.facebook.com → создай приложение
2. Добавь продукт **Threads API**
3. В настройках получи **Long-lived Access Token** (действует 60 дней, потом надо обновить)
4. Получи User ID:
   ```
   GET https://graph.threads.net/v1.0/me?fields=id&access_token=ТВОЙ_ТОКЕН
   ```
5. → `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`

---

## 2. Установка

```bash
# Клонируй / скопируй папку проекта
cd crypto_autopost

# Создай виртуальное окружение
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Установи зависимости
pip install -r requirements.txt

# Настрой переменные
cp .env.example .env
nano .env   # заполни все значения
```

---

## 3. Запуск

```bash
python main.py
```

Бот стартует, через 10 секунд опубликует первый пост, и начнёт мониторить комменты.

---

## 4. Команды Telegram бота

| Команда | Что делает |
|---------|------------|
| `/status` | Статус бота, расписание, сколько комментов ждут ответа |
| `/postnow` | Сгенерировать и опубликовать пост прямо сейчас |

---

## 5. Автозапуск на VPS (systemd)

```ini
# /etc/systemd/system/cryptobot.service
[Unit]
Description=Crypto Autopost Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/crypto_autopost
ExecStart=/home/ubuntu/crypto_autopost/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable cryptobot
sudo systemctl start cryptobot
sudo systemctl status cryptobot
```

---

## 6. Обновление Threads токена (каждые 60 дней)

```bash
curl "https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=ТВОЙ_ТОКЕН"
```
Скопируй новый токен в `.env`.

---

## Структура проекта

```
crypto_autopost/
├── main.py              # Точка входа, планировщик
├── content_generator.py # Claude API + Pollinations
├── threads_client.py    # Threads API (пост, комменты, ответы)
├── telegram_bot.py      # Telegram бот
├── config.py            # Конфиг из .env
├── requirements.txt
├── .env.example
└── seen_comments.json   # Создаётся автоматически
```

---

## Рекомендуемый VPS
- **Hetzner CX11** — €3.85/мес, Германия ✅
- **DigitalOcean Droplet** — $4/мес ✅
- Python 3.11+
