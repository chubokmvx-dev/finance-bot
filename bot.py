import os, json, logging, asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
FOOTBALL_KEY = os.environ.get("FOOTBALL_KEY", "")
TIMEZONE = ZoneInfo("Europe/Kyiv")

# ══════════════════════════════════════════
# API FOOTBALL
# ══════════════════════════════════════════
async def football_request(endpoint, params={}):
    if not FOOTBALL_KEY:
        logger.error("FOOTBALL_KEY not set!")
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://v3.football.api-sports.io/{endpoint}",
                headers={"x-apisports-key": FOOTBALL_KEY},
                params=params,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    if data.get("errors"):
                        logger.error(f"API error: {data['errors']}")
                        return None
                    return data.get("response", [])
    except Exception as e:
        logger.error(f"Football API error: {e}")
    return None

async def get_live_matches():
    return await football_request("fixtures", {"live": "all"})

async def get_upcoming_matches(hours=24):
    now = datetime.now(TIMEZONE)
    date_from = now.strftime("%Y-%m-%d")
    return await football_request("fixtures", {
        "date": date_from,
        "status": "NS",
        "timezone": "Europe/Kiev"
    })

async def get_fixture_stats(fixture_id):
    return await football_request("fixtures/statistics", {"fixture": fixture_id})

async def get_fixture_events(fixture_id):
    return await football_request("fixtures/events", {"fixture": fixture_id})

async def get_fixture_odds(fixture_id):
    return await football_request("odds/live", {"fixture": fixture_id})

async def get_prematch_odds(fixture_id):
    return await football_request("odds", {"fixture": fixture_id})

async def get_h2h(team1_id, team2_id):
    return await football_request("fixtures/headtohead", {
        "h2h": f"{team1_id}-{team2_id}",
        "last": 10
    })

# ══════════════════════════════════════════
# АНАЛІЗ МАТЧУ
# ══════════════════════════════════════════
def parse_fixture(fix):
    try:
        f = fix.get("fixture", {})
        teams = fix.get("teams", {})
        goals = fix.get("goals", {})
        score = fix.get("score", {})
        league = fix.get("league", {})

        return {
            "id": f.get("id"),
            "status": f.get("status", {}).get("short", ""),
            "elapsed": f.get("status", {}).get("elapsed", 0),
            "home": teams.get("home", {}).get("name", ""),
            "away": teams.get("away", {}).get("name", ""),
            "home_id": teams.get("home", {}).get("id"),
            "away_id": teams.get("away", {}).get("id"),
            "home_goals": goals.get("home", 0) or 0,
            "away_goals": goals.get("away", 0) or 0,
            "total_goals": (goals.get("home", 0) or 0) + (goals.get("away", 0) or 0),
            "ht_home": score.get("halftime", {}).get("home", 0) or 0,
            "ht_away": score.get("halftime", {}).get("away", 0) or 0,
            "league": league.get("name", ""),
            "country": league.get("country", ""),
            "date": f.get("date", ""),
        }
    except Exception as e:
        logger.error(f"Parse fixture error: {e}")
        return None

def parse_stats(stats_data, home_name, away_name):
    result = {}
    if not stats_data: return result
    for team_stats in stats_data:
        team_name = team_stats.get("team", {}).get("name", "")
        is_home = team_name == home_name
        prefix = "home" if is_home else "away"
        for stat in team_stats.get("statistics", []):
            stype = stat.get("type", "")
            val = stat.get("value") or 0
            if isinstance(val, str) and "%" in val:
                val = float(val.replace("%", ""))
            elif isinstance(val, str):
                try: val = float(val)
                except: val = 0
            key_map = {
                "Shots on Goal": f"{prefix}_shots_on",
                "Shots off Goal": f"{prefix}_shots_off",
                "Total Shots": f"{prefix}_shots_total",
                "Blocked Shots": f"{prefix}_shots_blocked",
                "Corner Kicks": f"{prefix}_corners",
                "Ball Possession": f"{prefix}_possession",
                "Yellow Cards": f"{prefix}_yellow",
                "Red Cards": f"{prefix}_red",
                "Dangerous Attacks": f"{prefix}_dangerous",
                "Attacks": f"{prefix}_attacks",
                "Expected Goals": f"{prefix}_xg",
            }
            if stype in key_map:
                result[key_map[stype]] = val
    return result

def calc_goal_probability(match, stats, h2h_data):
    score = 0
    factors = []
    elapsed = match.get("elapsed", 0) or 0
    total = match.get("total_goals", 0)
    home_goals = match.get("home_goals", 0)
    away_goals = match.get("away_goals", 0)

    # Поточний рахунок і темп
    if elapsed > 0:
        goals_per_min = total / elapsed if elapsed > 0 else 0
        projected_total = goals_per_min * 90

        if projected_total >= 3.5:
            score += 25
            factors.append(f"⚡ Темп: {goals_per_min:.2f} голи/хв (прогноз {projected_total:.1f})")
        elif projected_total >= 2.5:
            score += 15
            factors.append(f"📊 Темп: {projected_total:.1f} голів за матч")
        elif projected_total >= 1.5:
            score += 5
            factors.append(f"📊 Помірний темп: {projected_total:.1f}")

    # Статистика ударів
    home_shots = stats.get("home_shots_total", 0)
    away_shots = stats.get("away_shots_total", 0)
    home_on = stats.get("home_shots_on", 0)
    away_on = stats.get("away_shots_on", 0)
    total_shots = home_shots + away_shots
    total_on = home_on + away_on

    if total_shots > 20:
        score += 20
        factors.append(f"🎯 Багато ударів: {total_shots} (в ціль: {total_on})")
    elif total_shots > 12:
        score += 12
        factors.append(f"🎯 Удари: {total_shots} (в ціль: {total_on})")
    elif total_shots > 6:
        score += 5
        factors.append(f"🎯 Мало ударів: {total_shots}")

    # xG
    home_xg = stats.get("home_xg", 0)
    away_xg = stats.get("away_xg", 0)
    total_xg = (home_xg or 0) + (away_xg or 0)
    if total_xg > 3:
        score += 20
        factors.append(f"📈 xG: {total_xg:.2f} (дуже небезпечно)")
    elif total_xg > 2:
        score += 12
        factors.append(f"📈 xG: {total_xg:.2f}")
    elif total_xg > 1:
        score += 6
        factors.append(f"📈 xG: {total_xg:.2f}")

    # Кути
    home_corners = stats.get("home_corners", 0)
    away_corners = stats.get("away_corners", 0)
    total_corners = home_corners + away_corners
    if total_corners > 10:
        score += 15
        factors.append(f"🚩 Багато кутових: {total_corners}")
    elif total_corners > 6:
        score += 8
        factors.append(f"🚩 Кутові: {total_corners}")

    # Небезпечні атаки
    home_danger = stats.get("home_dangerous", 0)
    away_danger = stats.get("away_dangerous", 0)
    total_danger = home_danger + away_danger
    if total_danger > 50:
        score += 10
        factors.append(f"⚠️ Небезпечні атаки: {total_danger}")

    # H2H аналіз
    if h2h_data:
        h2h_goals = []
        for fix in h2h_data[:5]:
            g = fix.get("goals", {})
            h = g.get("home", 0) or 0
            a = g.get("away", 0) or 0
            h2h_goals.append(h + a)
        if h2h_goals:
            avg_h2h = sum(h2h_goals) / len(h2h_goals)
            over25_count = sum(1 for g in h2h_goals if g > 2.5)
            if avg_h2h > 3:
                score += 15
                factors.append(f"📋 H2H: {avg_h2h:.1f} голів в середньому")
            elif avg_h2h > 2:
                score += 8
                factors.append(f"📋 H2H: {avg_h2h:.1f} голів")
            if over25_count >= 3:
                score += 10
                factors.append(f"📋 H2H: {over25_count}/5 матчів >2.5 голів")

    # Час матчу — другий тайм активніший
    if 60 <= elapsed <= 75:
        score += 5
        factors.append("⏱ 60-75 хв — активна фаза")
    elif elapsed > 75:
        score -= 5
        factors.append("⏱ Кінець матчу — менше часу")

    return min(100, score), factors

def recommend_total(match, prob_score, stats, is_live=True):
    total = match.get("total_goals", 0)
    elapsed = match.get("elapsed", 0) or 0
    home_goals = match.get("home_goals", 0)
    away_goals = match.get("away_goals", 0)

    recommendations = []

    if is_live:
        remaining = 90 - elapsed
        goals_per_min = total / elapsed if elapsed > 0 else 0
        projected_additional = goals_per_min * remaining

        # Розрахунок рекомендацій по тоталам
        totals = [0.5, 1.5, 2.5, 3.5, 4.5]
        for t in totals:
            if total >= t:
                already_over = True
            else:
                needed = t - total
                probability = min(95, int(prob_score * (projected_additional / max(needed, 0.5))))
                already_over = False

            if already_over:
                recommendations.append({
                    "total": t,
                    "bet": f"ТБ {t}",
                    "result": "✅ Вже виконано",
                    "confidence": 100,
                    "note": f"Вже {total} голів"
                })
            elif t - total <= 1 and prob_score >= 60:
                confidence = min(90, prob_score)
                recommendations.append({
                    "total": t,
                    "bet": f"ТБ {t}",
                    "result": "🎯 Рекомендую",
                    "confidence": confidence,
                    "note": f"Потрібен ще {t-total:.1f} гол(и), {remaining:.0f} хв залишилось"
                })

        # ТМ (тотал менше)
        if elapsed > 60 and total <= 1:
            recommendations.append({
                "total": 2.5,
                "bet": "ТМ 2.5",
                "result": "🔒 Розглянути",
                "confidence": 70,
                "note": f"60+ хв, лише {total} голів"
            })
    else:
        # Для матчів лінії
        if prob_score >= 70:
            recommendations.append({"total": 2.5, "bet": "ТБ 2.5", "result": "🎯 Рекомендую", "confidence": prob_score, "note": "Висока активність очікується"})
        elif prob_score >= 50:
            recommendations.append({"total": 1.5, "bet": "ТБ 1.5", "result": "🟡 Можливо", "confidence": prob_score, "note": "Помірна активність"})
        else:
            recommendations.append({"total": 2.5, "bet": "ТМ 2.5", "result": "🔒 Розглянути", "confidence": 60, "note": "Очікується закритий матч"})

    return recommendations

def format_match_analysis(match, stats, recommendations, factors, is_live=True):
    home = match["home"]
    away = match["away"]
    home_g = match["home_goals"]
    away_g = match["away_goals"]
    elapsed = match.get("elapsed", 0) or 0
    league = match.get("league", "")
    country = match.get("country", "")

    if is_live:
        header = (
            f"⚽ *{home}* vs *{away}*\n"
            f"🏆 {country} — {league}\n"
            f"🔴 LIVE | ⏱ {elapsed}'\n\n"
            f"📊 Рахунок: *{home_g} : {away_g}*\n"
            f"Загалом голів: *{home_g + away_g}*\n\n"
        )
    else:
        try:
            dt = datetime.fromisoformat(match.get("date","").replace("Z","+00:00"))
            dt_kyiv = dt.astimezone(TIMEZONE)
            time_str = dt_kyiv.strftime("%d.%m %H:%M")
        except:
            time_str = match.get("date","")[:16]
        header = (
            f"⚽ *{home}* vs *{away}*\n"
            f"🏆 {country} — {league}\n"
            f"📅 {time_str}\n\n"
        )

    # Статистика
    stats_text = ""
    if stats:
        h_shots = stats.get("home_shots_total", 0)
        a_shots = stats.get("away_shots_total", 0)
        h_on = stats.get("home_shots_on", 0)
        a_on = stats.get("away_shots_on", 0)
        h_corn = stats.get("home_corners", 0)
        a_corn = stats.get("away_corners", 0)
        h_xg = stats.get("home_xg", 0) or 0
        a_xg = stats.get("away_xg", 0) or 0

        stats_text = (
            f"📈 *Статистика:*\n"
            f"Удари: {h_shots} — {a_shots}\n"
            f"В ціль: {h_on} — {a_on}\n"
            f"Кути: {h_corn} — {a_corn}\n"
        )
        if h_xg or a_xg:
            stats_text += f"xG: {h_xg:.2f} — {a_xg:.2f}\n"
        stats_text += "\n"

    # Фактори
    factors_text = ""
    if factors:
        factors_text = "🔍 *Ключові фактори:*\n"
        for f in factors[:4]:
            factors_text += f"• {f}\n"
        factors_text += "\n"

    # Рекомендації
    recs_text = "💡 *Рекомендації по тоталам:*\n\n"
    if recommendations:
        for rec in recommendations[:4]:
            conf_bar = "█" * (rec["confidence"]//20) + "░" * (5 - rec["confidence"]//20)
            recs_text += (
                f"{rec['result']} *{rec['bet']}*\n"
                f"`{conf_bar}` {rec['confidence']}%\n"
                f"_{rec['note']}_\n\n"
            )
    else:
        recs_text += "😐 Немає чітких рекомендацій\n\n"

    footer = "⚠️ _Це аналітика, не гарантія. Ставте відповідально!_"

    return header + stats_text + factors_text + recs_text + footer

# ══════════════════════════════════════════
# МЕНЮ
# ══════════════════════════════════════════
def main_kb():
    return ReplyKeyboardMarkup([
        ["🔴 Live матчі", "📅 Лінія"],
        ["⭐ Топ ставки", "📊 Статистика"],
        ["❓ Як користуватись"],
    ], resize_keyboard=True)

# ══════════════════════════════════════════
# ОБРОБНИКИ
# ══════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Привіт, {name}!\n\n"
        "⚽ Бот аналізу футбольних матчів\n\n"
        "🔴 *Live* — аналіз поточних матчів\n"
        "📅 *Лінія* — майбутні матчі на сьогодні\n"
        "⭐ *Топ ставки* — найкращі рекомендації\n\n"
        "Аналізую тотали: ТБ/ТМ 0.5 / 1.5 / 2.5 / 3.5\n\n"
        "⚠️ _Тільки для розваги! Ставки — це ризик._",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )

async def show_live_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔴 Завантажую live матчі...")

    if not FOOTBALL_KEY:
        await msg.edit_text("❌ FOOTBALL_KEY не встановлено!\n\nДодайте ключ з api-football.com в Railway Variables.")
        return

    matches = await get_live_matches()

    if not matches:
        await msg.edit_text("😐 Зараз немає live матчів\n\nСпробуйте пізніше або перегляньте 📅 Лінію")
        return

    text = f"🔴 *Live матчі ({len(matches)}):*\n\n"
    buttons = []

    for fix in matches[:10]:
        m = parse_fixture(fix)
        if not m: continue
        elapsed = m.get("elapsed", 0) or 0
        text += f"⚽ {m['home']} *{m['home_goals']}:{m['away_goals']}* {m['away']} | {elapsed}'\n"
        buttons.append([InlineKeyboardButton(
            f"📊 {m['home'][:12]} vs {m['away'][:12]}",
            callback_data=f"analyze_{m['id']}_live"
        )])

    if not buttons:
        await msg.edit_text("😐 Немає активних матчів")
        return

    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def show_upcoming_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📅 Завантажую майбутні матчі...")

    if not FOOTBALL_KEY:
        await msg.edit_text("❌ FOOTBALL_KEY не встановлено!")
        return

    matches = await get_upcoming_matches()

    if not matches:
        await msg.edit_text("😐 Немає запланованих матчів на сьогодні")
        return

    # Сортуємо по часу
    def get_time(fix):
        try: return fix.get("fixture",{}).get("date","")
        except: return ""

    matches = sorted(matches, key=get_time)[:15]

    text = f"📅 *Матчі на сьогодні ({len(matches)}):*\n\n"
    buttons = []

    for fix in matches:
        m = parse_fixture(fix)
        if not m: continue
        try:
            dt = datetime.fromisoformat(m["date"].replace("Z","+00:00"))
            dt_kyiv = dt.astimezone(TIMEZONE)
            time_str = dt_kyiv.strftime("%H:%M")
        except:
            time_str = "??:??"
        text += f"🕐 {time_str} | {m['home']} vs {m['away']}\n"
        buttons.append([InlineKeyboardButton(
            f"📊 {time_str} {m['home'][:10]} vs {m['away'][:10]}",
            callback_data=f"analyze_{m['id']}_pre"
        )])

    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons[:10]))

async def show_top_bets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⭐ Шукаю найкращі ставки...")

    if not FOOTBALL_KEY:
        await msg.edit_text("❌ FOOTBALL_KEY не встановлено!")
        return

    live = await get_live_matches()
    if not live:
        await msg.edit_text("😐 Немає live матчів для аналізу\n\nСпробуйте пізніше")
        return

    top_matches = []
    for fix in live[:8]:
        m = parse_fixture(fix)
        if not m: continue
        stats_raw = await get_fixture_stats(m["id"])
        stats = parse_stats(stats_raw, m["home"], m["away"]) if stats_raw else {}
        h2h = await get_h2h(m["home_id"], m["away_id"]) if m.get("home_id") else []
        prob_score, factors = calc_goal_probability(m, stats, h2h)
        recs = recommend_total(m, prob_score, stats, True)
        strong_recs = [r for r in recs if r.get("confidence", 0) >= 70 and "Рекомендую" in r.get("result","")]
        if strong_recs:
            top_matches.append({"match": m, "recs": strong_recs, "score": prob_score})
        await asyncio.sleep(0.5)

    if not top_matches:
        await msg.edit_text("😐 Зараз немає strong сигналів (>70%)\n\nСпробуйте пізніше — ситуація на полі змінюється!")
        return

    top_matches.sort(key=lambda x: -x["score"])
    text = "⭐ *Топ ставки зараз:*\n\n"
    for item in top_matches[:5]:
        m = item["match"]
        text += f"⚽ *{m['home']} {m['home_goals']}:{m['away_goals']} {m['away']}* ({m.get('elapsed',0)}')\n"
        for rec in item["recs"][:2]:
            text += f"• {rec['bet']} — {rec['confidence']}% ✅\n"
        text += "\n"

    text += "⚠️ _Аналітика, не гарантія!_"
    await msg.edit_text(text, parse_mode="Markdown")

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ *Як користуватись:*\n\n"
        "🔴 *Live матчі* — поточні матчі з аналізом\n"
        "📅 *Лінія* — майбутні матчі на сьогодні\n"
        "⭐ *Топ ставки* — автоматичний пошук найкращих\n\n"
        "📊 *Що аналізую:*\n"
        "• Темп гри і голів\n"
        "• Удари і удари в ціль\n"
        "• xG (очікувані голи)\n"
        "• Кутові удари\n"
        "• Небезпечні атаки\n"
        "• H2H (особисті зустрічі)\n\n"
        "💡 *Рекомендації:*\n"
        "✅ Рекомендую — висока впевненість\n"
        "🟡 Можливо — середня впевненість\n"
        "🔒 Розглянути — обережно\n\n"
        "⚠️ _ВАЖЛИВО: Це аналітичний інструмент, НЕ гарантія виграшу. Ставте лише те що готові втратити!_",
        parse_mode="Markdown"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔴 Live матчі": await show_live_matches(update, context)
    elif text == "📅 Лінія": await show_upcoming_matches(update, context)
    elif text == "⭐ Топ ставки": await show_top_bets(update, context)
    elif text == "❓ Як користуватись": await show_help(update, context)
    elif text == "📊 Статистика":
        await update.message.reply_text(
            "📊 Оберіть матч для статистики — натисніть 🔴 Live або 📅 Лінія і виберіть матч"
        )

async def analyze_match(update: Update, context: ContextTypes.DEFAULT_TYPE, fixture_id: int, is_live: bool):
    q = update.callback_query
    await q.edit_message_text("⏳ Аналізую матч...")

    # Отримуємо дані матчу
    if is_live:
        all_live = await get_live_matches()
        fix_data = None
        if all_live:
            for f in all_live:
                if f.get("fixture",{}).get("id") == fixture_id:
                    fix_data = f; break
    else:
        result = await football_request("fixtures", {"id": fixture_id})
        fix_data = result[0] if result else None

    if not fix_data:
        await q.edit_message_text("❌ Матч не знайдено")
        return

    match = parse_fixture(fix_data)
    if not match:
        await q.edit_message_text("❌ Помилка отримання даних")
        return

    # Статистика
    stats_raw = await get_fixture_stats(fixture_id)
    stats = parse_stats(stats_raw, match["home"], match["away"]) if stats_raw else {}

    # H2H
    h2h = []
    if match.get("home_id") and match.get("away_id"):
        h2h_raw = await get_h2h(match["home_id"], match["away_id"])
        h2h = h2h_raw or []

    # Аналіз
    prob_score, factors = calc_goal_probability(match, stats, h2h)
    recommendations = recommend_total(match, prob_score, stats, is_live)

    text = format_match_analysis(match, stats, recommendations, factors, is_live)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Оновити", callback_data=f"analyze_{fixture_id}_{'live' if is_live else 'pre'}")
    ]])

    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        # Якщо текст задовгий — скорочуємо
        short_text = text[:4000] + "\n\n⚠️ _Аналітика, не гарантія!_"
        await q.edit_message_text(short_text, parse_mode="Markdown", reply_markup=kb)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data

    if d.startswith("analyze_"):
        parts = d.split("_")
        fixture_id = int(parts[1])
        is_live = parts[2] == "live"
        await analyze_match(update, context, fixture_id, is_live)

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Betting bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
