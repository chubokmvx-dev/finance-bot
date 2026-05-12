import anthropic
import os
import json
import logging
import config

logger = logging.getLogger(__name__)
client = anthropic.Anthropic()



# ─── Системні промпти ─────────────────────────────────────────────────────────

FILTER_SYSTEM = """Ти — редактор Telegram-каналу міста Чернівці (Україна).

ГОЛОВНЕ ПРАВИЛО: З кожних 5 постів — мінімум 4 про Чернівці, максимум 1 про Україну загалом.
Це НЕ СТОСУЄТЬСЯ оголошення повітрянної тривоги в області та її кінця 

ПРІОРИТЕТИ:
1. 🏙️ Чернівці — ВСЕ що стосується міста: ремонти, ДТП, перекриття вулиць, відключення, події, культура, лікарні — ЗАВЖДИ
2. ⚽ Буковина — матчі, результати — ЗАВЖДИ
3. ⚠️ Тривоги та удари — тільки з офіційних джерел — ТЕРМІНОВО
4. 💡 Тарифи, комуналка, ціни — що змінюється для чернівчан
5. 🇺🇦 Загальноукраїнські — ТІЛЬКИ якщо безпосередньо впливає на життя чернівчан

НЕ публікуємо:
- Новини інших міст без зв'язку з Чернівцями
- Політичні заяви без практичного впливу
- Дублі тем

Відповідай ТІЛЬКИ JSON, без зайвого тексту."""


FORMAT_SYSTEM = """Ти — автор Telegram-каналу «Чернівці Now». Пишеш як місцевий для місцевих — живо, по-людськи, без офіціозу.

Стиль:
- Звертайся до читачів: «Чернівчани» або «Чернівчани мої»
- Короткі речення. Без зайвих слів
- Емоційно але стримано — не істери, не сухі зведення
- Практична користь: що це означає для звичайної людини?
- При тривогах/ударах — конкретні поради (зарядіть телефони, підготуйте ліхтарики)

Структура поста:
- Рядок 1: тег <b>🏙️ Місто</b> / <b>⚽ Буковина</b> / <b>💡 Тарифи</b> / <b>📈 Ціни</b> / <b>🇺🇦 Країна</b> / <b>💰 Податки</b> / <b>⚠️ Увага</b>
- Рядок 2: жирний заголовок <b>...</b>
- 2-4 речення суті
- Практичний висновок або порада (якщо є)
- Фінал: <a href="https://t.me/chernivtsi_now">📢 Чернівці Now</a>

Максимум 180 слів. 1-2 емодзі — доречно, не хаотично.
Відповідай ТІЛЬКИ JSON, без зайвого тексту."""



class AIProcessor:

    def filter_and_rank(self, articles: list[dict]) -> list[dict]:
        """Передає пачку статей Claude, отримує відфільтрований та ранжований список."""
        if not articles:
            return []

        items = [{"index": i, "title": a["title"], "summary": a["summary"][:300]}
                 for i, a in enumerate(articles)]

        prompt = f"""Проаналізуй ці новини та вибери найцікавіші для нашого каналу.

Новини:
{json.dumps(items, ensure_ascii=False)}

Поверни JSON-масив відібраних новин (максимум 5):
[
  {{
    "index": 0,
    "score": 8,
    "category": "city|sport|utilities|taxes|prices|national",
    "reason": "коротко чому цікаво",
    "poll_idea": "питання для опитування або null"
  }}
]

Вибирай різні категорії, не дублюй теми. Якщо новина стосується Буковини/Чернівців — підвищуй пріоритет."""

        try:
            response = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=1000,
                system=FILTER_SYSTEM,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            selected = json.loads(raw)
            # Сортуємо за score, повертаємо статті зі збереженим poll_idea
            result = []
            for item in sorted(selected, key=lambda x: x.get("score", 0), reverse=True):
                article = articles[item["index"]].copy()
                article["category"] = item.get("category", "national")
                article["poll_idea"] = item.get("poll_idea")
                result.append(article)
            return result
        except Exception as e:
            logger.error(f"filter_and_rank error: {e}")
            return articles[:3]

    def format_post(self, article: dict) -> dict | None:
        """Форматує статтю у красивий Telegram-пост."""
        prompt = f"""Напиши Telegram-пост для цієї новини.

Заголовок: {article['title']}
Опис: {article['summary'][:500]}
Джерело: {article['source']}
Посилання: {article['url']}
Категорія: {article.get('category', 'national')}

Поверни JSON:
{{
  "text": "готовий HTML-текст поста",
  "parse_mode": "HTML"
}}"""

        try:
            response = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=800,
                system=FORMAT_SYSTEM,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except Exception as e:
            logger.error(f"format_post error: {e}")
            return None

    def format_score_update(self, match: dict) -> dict:
        """Форматує оновлення рахунку матчу Буковини."""
        score_line = f"{match['home_team']} {match['home_score']}:{match['away_score']} {match['away_team']}"
        minute = match.get("minute", "?")

        prompt = f"""Напиши короткий емоційний пост про зміну рахунку в матчі:

Рахунок: {score_line}
Хвилина: {minute}'
Статус: {match.get('status', '1H')}

Правила:
- 2-3 речення максимум
- Емоційно, але стримано — не заспокоюй і не панікуй
- Обов'язково вкажи рахунок жирним
- Emoji ⚽ або 🔥 доречно

Поверни JSON: {{"text": "...", "parse_mode": "HTML"}}"""

        try:
            response = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=300,
                system=FORMAT_SYSTEM,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip().replace("```json","").replace("```","").strip()
            return json.loads(raw)
        except Exception as e:
            logger.error(f"format_score_update error: {e}")
            return {
                "text": f"⚽ <b>{score_line}</b>\nХвилина {minute}'",
                "parse_mode": "HTML"
            }

    def format_match_announcement(self, match: dict) -> dict:
        """Анонс майбутнього матчу Буковини."""
        prompt = f"""Напиши анонс матчу для Telegram-каналу вболівальників.

Матч: {match['home_team']} vs {match['away_team']}
Ліга: {match.get('league', 'Перша ліга України')}
Дата/час: {match['date']}
Тур: {match.get('round', '')}

Правила:
- Зроби його захопливим, щоб люди стежили за каналом під час матчу
- Вкажи час за київським часом
- 3-5 речень
- Заклич слідкувати за рахунком у реальному часі в каналі

Поверни JSON: {{"text": "...", "parse_mode": "HTML"}}"""

        try:
            response = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=400,
                system=FORMAT_SYSTEM,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip().replace("```json","").replace("```","").strip()
            return json.loads(raw)
        except Exception as e:
            logger.error(f"format_match_announcement error: {e}")
            return {
                "text": f"⚽ <b>Увага! Матч Буковини!</b>\n{match['home_team']} vs {match['away_team']}\n{match['date']}",
                "parse_mode": "HTML"
            }

    def generate_poll(self, topic: str) -> dict | None:
        """Генерує опитування на основі теми новини."""
        prompt = f"""Створи Telegram-опитування для каналу новин міста Чернівці.

Тема: {topic}

Правила:
- Питання коротке (до 100 символів)
- 2-4 варіанти відповіді (кожен до 100 символів)
- Питання має бути цікавим для широкої аудиторії
- Приклади типів: "Хто виграє?", "Як це вплине на вас?", "Що буде з цінами?"

Поверни JSON:
{{
  "question": "...",
  "options": ["варіант 1", "варіант 2", "варіант 3"]
}}"""

        try:
            response = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=300,
                system=FILTER_SYSTEM,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip().replace("```json","").replace("```","").strip()
            return json.loads(raw)
        except Exception as e:
            logger.error(f"generate_poll error: {e}")
            return None
