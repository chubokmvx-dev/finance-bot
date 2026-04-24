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
# КЕШ — зменшує кількість запитів
# ══════════════════════════════════════════
CACHE = {}
CACHE_TTL = {
    "live": 60,        # live матчі — 1 хв
    "upcoming": 300,   # майбутні — 5 хв
    "stats": 90,       # статистика — 1.5 хв
    "h2h": 3600,       # h2h — 1 година (не змінюється)
    "odds": 120,       # коефіцієнти — 2 хв
}

def cache_get(key):
    if key in CACHE:
        data, ts, ttl = CACHE[key]
        if (datetime.now().timestamp() - ts) < ttl:
            return data
        del CACHE[key]
    return None

def cache_set(key, data, ttl_type="stats"):
    CACHE[key] = (data, datetime.now().timestamp(), CACHE_TTL.get(ttl_type, 120))

# ══════════════════════════════════════════
# API FOOTBALL
# ══════════════════════════════════════════
async def football_request(endpoint, params={}, cache_type="stats"):
    cache_key = f"{endpoint}_{json.dumps(params, sort_keys=True)}"
    cached = cache_get(cache_key)
    if cached is not None:
        logger.info(f"Cache hit: {cache_key[:50]}")
        return cached

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
                    if data.get("errors") and data["errors"] != []:
                        logger.error(f"API error: {data['errors']}")
                        return None
                    result = data.get("response", [])
                    cache_set(cache_key, result, cache_type)
                    return result
                elif r.status == 429:
                    logger.warning("Rate limit hit!")
                    return None
    except Exception as e:
        logger.error(f"Football API error: {e}")
    return None

async def get_live_matches():
    return await football_request("fixtures", {"live": "all"}, "live")

async def get_upcoming_matches():
    date = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    return await football_request("fixtures", {"date": date, "status": "NS", "timezone": "Europe/Kiev"}, "upcoming")

def filter_next_12h(matches):
    now = datetime.now(TIMEZONE)
    cutoff = now + timedelta(hours=12)
    result = []
    for fix in (matches or []):
        try:
            dt = datetime.fromisoformat(fix.get("fixture",{}).get("date","").replace("Z","+00:00"))
            dt = dt.astimezone(TIMEZONE)
            if now <= dt <= cutoff:
                result.append(fix)
        except: pass
    return result

async def get_fixture_stats(fixture_id):
    return await football_request("fixtures/statistics", {"fixture": fixture_id}, "stats")

async def get_h2h(team1_id, team2_id):
    key = f"{min(team1_id,team2_id)}-{max(team1_id,team2_id)}"
    return await football_request("fixtures/headtohead", {"h2h": f"{team1_id}-{team2_id}", "last": 8}, "h2h")

# ══════════════════════════════════════════
# ПАРСИНГ ДАНИХ
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
            "elapsed": f.get("status", {}).get("elapsed", 0) or 0,
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
                try: val = float(val.replace("%", ""))
                except: val = 0
            elif isinstance(val, str):
                try: val = float(val)
                except: val = 0
            key_map = {
                "Shots on Goal": f"{prefix}_shots_on",
                "Shots off Goal": f"{prefix}_shots_off",
                "Total Shots": f"{prefix}_shots_total",
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

# ══════════════════════════════════════════
# АНАЛІЗ І СКОР
# ══════════════════════════════════════════
def calc_goal_probability(match, stats, h2h_data):
    score = 0
    factors = []
    elapsed = match.get("elapsed", 0) or 0
    total = match.get("total_goals", 0)

    # 1. Темп гри
    if elapsed > 5:
        gpm = total / elapsed
        projected = gpm * 90
        if projected >= 4.0:
            score += 30
            factors.append(f"⚡ Темп: {projected:.1f} голів (дуже високий)")
        elif projected >= 3.0:
            score += 22
            factors.append(f"⚡ Темп: {projected:.1f} голів (високий)")
        elif projected >= 2.0:
            score += 14
            factors.append(f"📊 Темп: {projected:.1f} голів (середній)")
        elif projected >= 1.0:
            score += 6
            factors.append(f"📊 Темп: {projected:.1f} голів (низький)")

    # 2. Удари
    h_shots = stats.get("home_shots_total", 0)
    a_shots = stats.get("away_shots_total", 0)
    h_on = stats.get("home_shots_on", 0)
    a_on = stats.get("away_shots_on", 0)
    total_shots = h_shots + a_shots
    total_on = h_on + a_on

    if total_shots >= 25:
        score += 20
        factors.append(f"🎯 Удари: {total_shots} (в ціль: {total_on})")
    elif total_shots >= 15:
        score += 13
        factors.append(f"🎯 Удари: {total_shots} (в ціль: {total_on})")
    elif total_shots >= 8:
        score += 7
        factors.append(f"🎯 Удари: {total_shots} (в ціль: {total_on})")
    elif total_shots > 0:
        score += 3
        factors.append(f"🎯 Мало ударів: {total_shots}")

    # 3. xG
    h_xg = float(stats.get("home_xg", 0) or 0)
    a_xg = float(stats.get("away_xg", 0) or 0)
    total_xg = h_xg + a_xg
    if total_xg >= 3.5:
        score += 20
        factors.append(f"📈 xG: {total_xg:.2f} (дуже небезпечно)")
    elif total_xg >= 2.5:
        score += 14
        factors.append(f"📈 xG: {total_xg:.2f} (небезпечно)")
    elif total_xg >= 1.5:
        score += 8
        factors.append(f"📈 xG: {total_xg:.2f}")
    elif total_xg > 0:
        score += 4
        factors.append(f"📈 xG: {total_xg:.2f}")

    # 4. Кути
    total_corners = stats.get("home_corners", 0) + stats.get("away_corners", 0)
    if total_corners >= 12:
        score += 12
        factors.append(f"🚩 Кути: {total_corners} (багато)")
    elif total_corners >= 7:
        score += 7
        factors.append(f"🚩 Кути: {total_corners}")
    elif total_corners > 0:
        score += 3
        factors.append(f"🚩 Кути: {total_corners}")

    # 5. H2H
    if h2h_data:
        goals_list = []
        for fix in h2h_data[:6]:
            g = fix.get("goals", {})
            goals_list.append((g.get("home", 0) or 0) + (g.get("away", 0) or 0))
        if goals_list:
            avg = sum(goals_list) / len(goals_list)
            over25 = sum(1 for g in goals_list if g > 2.5)
            if avg >= 3.5:
                score += 15
                factors.append(f"📋 H2H: {avg:.1f} голів в середньому")
            elif avg >= 2.5:
                score += 10
                factors.append(f"📋 H2H: {avg:.1f} голів")
            elif avg >= 1.5:
                score += 5
                factors.append(f"📋 H2H: {avg:.1f} голів")
            if over25 >= 4:
                score += 8
                factors.append(f"📋 H2H: {over25}/6 матчів ТБ2.5")

    # 6. Час матчу
    if 55 <= elapsed <= 75:
        score += 5
        factors.append(f"⏱ {elapsed}' — активна фаза")
    elif elapsed > 80:
        score -= 8
        factors.append(f"⏱ {elapsed}' — мало часу")
    elif elapsed > 75:
        score -= 4

    # 7. Поточний рахунок — рівний рахунок = більше голів
    if match["home_goals"] == match["away_goals"] and elapsed > 30:
        score += 5
        factors.append("⚖️ Рівний рахунок — обидві команди атакують")

    return min(100, max(0, score)), factors

def calc_ht_probability(h2h_data):
    if not h2h_data or len(h2h_data) < 3:
        return 50, []
    score = 0
    factors = []
    ht_goals = []
    for fix in h2h_data[:8]:
        s = fix.get("score", {})
        ht = s.get("halftime", {})
        h = ht.get("home") or 0
        a = ht.get("away") or 0
        ht_goals.append(h + a)

    if not ht_goals: return 50, []

    avg = sum(ht_goals) / len(ht_goals)
    over05 = sum(1 for g in ht_goals if g >= 1)
    over15 = sum(1 for g in ht_goals if g >= 2)
    over25 = sum(1 for g in ht_goals if g >= 3)
    n = len(ht_goals)

    if avg >= 2.0:
        score += 35; factors.append(f"⚽ H2H 1Т: {avg:.1f} голів в середньому")
    elif avg >= 1.5:
        score += 25; factors.append(f"⚽ H2H 1Т: {avg:.1f} голів")
    elif avg >= 1.0:
        score += 15; factors.append(f"⚽ H2H 1Т: {avg:.1f} голів")
    else:
        score += 5; factors.append(f"⚽ H2H 1Т: {avg:.1f} голів (мало)")

    if over05 >= n * 0.8:
        score += 25; factors.append(f"✅ {over05}/{n} матчів — гол в 1Т")
    elif over05 >= n * 0.6:
        score += 15; factors.append(f"🟡 {over05}/{n} матчів — гол в 1Т")

    if over15 >= n * 0.6:
        score += 20; factors.append(f"✅ {over15}/{n} матчів — 2+ голів в 1Т")
    elif over15 >= n * 0.4:
        score += 10; factors.append(f"🟡 {over15}/{n} матчів — 2+ голів в 1Т")

    if over25 >= n * 0.4:
        score += 15; factors.append(f"🔥 {over25}/{n} матчів — 3+ голів в 1Т")

    return min(100, score), factors

def recommend_totals(match, prob_score, is_live=True, h2h_data=None):
    total = match["total_goals"]
    elapsed = match.get("elapsed", 0) or 0
    remaining = 90 - elapsed
    recs = []

    if is_live:
        gpm = total / elapsed if elapsed > 5 else 0
        projected_add = gpm * remaining

        for t in [0.5, 1.5, 2.5, 3.5, 4.5]:
            if total >= t:
                recs.append({"bet": f"ТБ {t}", "status": "done", "confidence": 100, "note": f"✅ Вже виконано ({total} голів)"})
            else:
                needed = t - total
                if needed <= 0.5:
                    conf = min(92, prob_score + 20)
                    recs.append({"bet": f"ТБ {t}", "status": "hot", "confidence": conf, "note": f"Потрібен 1 гол, {remaining:.0f}хв залишилось"})
                elif needed <= 1.5 and prob_score >= 55:
                    conf = min(85, prob_score + 5)
                    recs.append({"bet": f"ТБ {t}", "status": "good", "confidence": conf, "note": f"Потрібно {needed:.0f} голів, {remaining:.0f}хв"})
                elif needed <= 2.5 and prob_score >= 65:
                    conf = min(75, prob_score - 5)
                    recs.append({"bet": f"ТБ {t}", "status": "ok", "confidence": conf, "note": f"Потрібно {needed:.0f} голів, {remaining:.0f}хв"})

        if elapsed >= 55 and total == 0:
            recs.append({"bet": "ТМ 0.5", "status": "good", "confidence": 70, "note": f"55+ хв, рахунок 0:0"})
        if elapsed >= 65 and total <= 1:
            recs.append({"bet": f"ТМ 2.5", "status": "ok", "confidence": 72, "note": f"65+ хв, лише {total} гол(и)"})
        if elapsed >= 75 and total <= 2:
            recs.append({"bet": f"ТМ 3.5", "status": "ok", "confidence": 75, "note": f"75+ хв, {total} голів"})

    else:
        # ── Весь матч ──
        if prob_score >= 65:
            recs.append({"bet": "ТБ 2.5", "status": "good", "confidence": prob_score, "note": "Висока атакуючість за H2H"})
            recs.append({"bet": "ТБ 1.5", "status": "hot", "confidence": min(92, prob_score+12), "note": "Надійний варіант"})
        elif prob_score >= 50:
            recs.append({"bet": "ТБ 1.5", "status": "good", "confidence": prob_score+5, "note": "Помірна атакуючість"})
            recs.append({"bet": "ТМ 2.5", "status": "ok", "confidence": 58, "note": "Можливий закритий матч"})
        else:
            recs.append({"bet": "ТМ 2.5", "status": "ok", "confidence": 62, "note": "Очікується закритий матч"})
            recs.append({"bet": "ТМ 1.5", "status": "ok", "confidence": 55, "note": "Мало голів за H2H"})

        # ── 1-й тайм ──
        ht_score, ht_factors = calc_ht_probability(h2h_data)

        if ht_score >= 60:
            recs.append({"bet": "1Т ТБ 0.5", "status": "hot", "confidence": ht_score, "note": f"Гол в першому таймі"})
        if ht_score >= 50:
            recs.append({"bet": "1Т ТБ 1.5", "status": "good", "confidence": max(55, ht_score-10), "note": "2+ голів в 1Т"})
        if ht_score >= 70:
            recs.append({"bet": "1Т ТБ 2.5", "status": "ok", "confidence": max(55, ht_score-20), "note": "3+ голів в 1Т"})
        if ht_score < 40:
            recs.append({"bet": "1Т ТМ 0.5", "status": "good", "confidence": 65, "note": "Закритий перший тайм за H2H"})
            recs.append({"bet": "1Т ТМ 1.5", "status": "hot", "confidence": 72, "note": "Мало голів в 1Т за H2H"})

    recs = [r for r in recs if r["confidence"] >= 55]
    recs.sort(key=lambda x: -x["confidence"])
    return recs
    total = match["total_goals"]
    elapsed = match.get("elapsed", 0) or 0
    remaining = 90 - elapsed
    recs = []

    if is_live:
        gpm = total / elapsed if elapsed > 5 else 0
        projected_add = gpm * remaining

        for t in [0.5, 1.5, 2.5, 3.5, 4.5]:
            if total >= t:
                recs.append({"bet": f"ТБ {t}", "status": "done", "confidence": 100, "note": f"✅ Вже виконано ({total} голів)"})
            else:
                needed = t - total
                if needed <= 0.5:
                    conf = min(92, prob_score + 20)
                    recs.append({"bet": f"ТБ {t}", "status": "hot", "confidence": conf, "note": f"Потрібен 1 гол, {remaining:.0f}хв залишилось"})
                elif needed <= 1.5 and prob_score >= 55:
                    conf = min(85, prob_score + 5)
                    recs.append({"bet": f"ТБ {t}", "status": "good", "confidence": conf, "note": f"Потрібно {needed:.0f} голів, {remaining:.0f}хв"})
                elif needed <= 2.5 and prob_score >= 65:
                    conf = min(75, prob_score - 5)
                    recs.append({"bet": f"ТБ {t}", "status": "ok", "confidence": conf, "note": f"Потрібно {needed:.0f} голів, {remaining:.0f}хв"})

        # ТМ — якщо закритий матч
        if elapsed >= 55 and total == 0:
            recs.append({"bet": "ТМ 0.5", "status": "good", "confidence": 70, "note": f"55+ хв, рахунок 0:0"})
        if elapsed >= 65 and total <= 1:
            recs.append({"bet": f"ТМ 2.5", "status": "ok", "confidence": 72, "note": f"65+ хв, лише {total} гол(и)"})
        if elapsed >= 75 and total <= 2:
            recs.append({"bet": f"ТМ 3.5", "status": "ok", "confidence": 75, "note": f"75+ хв, {total} голів"})

    else:
        # Лінія — прематч
        if prob_score >= 65:
            recs.append({"bet": "ТБ 2.5", "status": "good", "confidence": prob_score, "note": "Висока атакуючість за H2H"})
            recs.append({"bet": "ТБ 1.5", "status": "hot", "confidence": min(92, prob_score+12), "note": "Надійний варіант"})
        elif prob_score >= 50:
            recs.append({"bet": "ТБ 1.5", "status": "good", "confidence": prob_score+5, "note": "Помірна атакуючість"})
            recs.append({"bet": "ТМ 2.5", "status": "ok", "confidence": 58, "note": "Можливий закритий матч"})
        else:
            recs.append({"bet": "ТМ 2.5", "status": "ok", "confidence": 62, "note": "Очікується закритий матч"})
            recs.append({"bet": "ТМ 1.5", "status": "ok", "confidence": 55, "note": "Мало голів за H2H"})

    # Фільтруємо лише >= 55%
    recs = [r for r in recs if r["confidence"] >= 55]
    recs.sort(key=lambda x: -x["confidence"])
    return recs

def format_analysis(match, stats, recs, factors, is_live):
    home = match["home"]; away = match["away"]
    hg = match["home_goals"]; ag = match["away_goals"]
    elapsed = match.get("elapsed", 0) or 0
    league = match.get("league", ""); country = match.get("country", "")

    if is_live:
        header = (f"⚽ *{home}* vs *{away}*\n"
                  f"🏆 {country} — {league}\n"
                  f"🔴 LIVE | ⏱ {elapsed}' | Рахунок: *{hg}:{ag}*\n\n")
    else:
        try:
            dt = datetime.fromisoformat(match.get("date","").replace("Z","+00:00"))
            t = dt.astimezone(TIMEZONE).strftime("%d.%m %H:%M")
        except: t = "??:??"
        header = (f"⚽ *{home}* vs *{away}*\n"
                  f"🏆 {country} — {league}\n"
                  f"📅 {t}\n\n")

    stats_text = ""
    if stats and is_live:
        hs = stats.get("home_shots_total",0); as_ = stats.get("away_shots_total",0)
        ho = stats.get("home_shots_on",0); ao = stats.get("away_shots_on",0)
        hc = stats.get("home_corners",0); ac = stats.get("away_corners",0)
        hx = float(stats.get("home_xg",0) or 0); ax = float(stats.get("away_xg",0) or 0)
        stats_text = (f"📊 *Статистика:*\n"
                      f"Удари: {hs} — {as_} | В ціль: {ho} — {ao}\n"
                      f"Кути: {hc} — {ac}")
        if hx or ax: stats_text += f" | xG: {hx:.1f}—{ax:.1f}"
        stats_text += "\n\n"

    factors_text = ""
    if factors:
        factors_text = "🔍 *Ключові фактори:*\n" + "".join([f"• {f}\n" for f in factors[:4]]) + "\n"

    icons = {"done": "✅", "hot": "🔥", "good": "🎯", "ok": "🟡"}

    # Розділяємо на 1Т і весь матч
    ht_recs = [r for r in recs if r["bet"].startswith("1Т")]
    ft_recs = [r for r in recs if not r["bet"].startswith("1Т")]

    recs_text = ""

    if ft_recs:
        recs_text += "💡 *Весь матч:*\n\n"
        for rec in ft_recs[:4]:
            icon = icons.get(rec["status"], "🟡")
            bar = "█"*(rec["confidence"]//20) + "░"*(5-rec["confidence"]//20)
            recs_text += f"{icon} *{rec['bet']}* — {rec['confidence']}%\n`{bar}` _{rec['note']}_\n\n"

    if ht_recs:
        recs_text += "⏱ *1-й тайм:*\n\n"
        for rec in ht_recs[:4]:
            icon = icons.get(rec["status"], "🟡")
            bar = "█"*(rec["confidence"]//20) + "░"*(5-rec["confidence"]//20)
            recs_text += f"{icon} *{rec['bet']}* — {rec['confidence']}%\n`{bar}` _{rec['note']}_\n\n"

    if not ft_recs and not ht_recs:
        recs_text = "😐 Немає рекомендацій (>55%)\n\n"

    return header + stats_text + factors_text + recs_text + "⚠️ _Аналітика для розваги. Ставте відповідально!_"

# ══════════════════════════════════════════
# МЕНЮ
# ══════════════════════════════════════════
def main_kb():
    return ReplyKeyboardMarkup([
        ["🔴 Live матчі", "📅 Лінія"],
        ["⭐ Топ ставки", "❓ Допомога"],
    ], resize_keyboard=True)

# ══════════════════════════════════════════
# ОБРОБНИКИ
# ══════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Привіт, {update.effective_user.first_name}!\n\n"
        "⚽ Бот аналізу футбольних тоталів\n\n"
        "🔴 *Live* — поточні матчі з аналізом\n"
        "📅 *Лінія* — майбутні матчі на сьогодні\n"
        "⭐ *Топ ставки* — найкращі рекомендації\n\n"
        "Тотали: ТБ/ТМ 0.5 / 1.5 / 2.5 / 3.5 / 4.5\n"
        "Поріг рекомендацій: від *55%*\n\n"
        "⚠️ _Тільки для розваги! Ставки — це ризик._",
        parse_mode="Markdown", reply_markup=main_kb()
    )

async def show_live(update, context):
    msg = await update.message.reply_text("🔴 Завантажую live матчі...")
    if not FOOTBALL_KEY:
        await msg.edit_text("❌ FOOTBALL_KEY не встановлено!\n\nДодайте ключ з api-football.com в Railway Variables.")
        return
    matches = await get_live_matches()
    if not matches:
        await msg.edit_text("😐 Зараз немає live матчів\nСпробуйте пізніше або 📅 Лінія")
        return
    text = f"🔴 *Live матчі ({len(matches)}):*\n\n"
    btns = []
    for fix in matches[:12]:
        m = parse_fixture(fix)
        if not m: continue
        text += f"⚽ {m['home']} *{m['home_goals']}:{m['away_goals']}* {m['away']} | {m['elapsed']}'\n"
        btns.append([InlineKeyboardButton(f"📊 {m['home'][:13]} vs {m['away'][:13]} ({m['elapsed']}')", callback_data=f"a_{m['id']}_1")])
    if not btns:
        await msg.edit_text("😐 Немає активних матчів"); return
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))

async def show_upcoming(update, context):
    msg = await update.message.reply_text("📅 Завантажую матчі...")
    if not FOOTBALL_KEY:
        await msg.edit_text("❌ FOOTBALL_KEY не встановлено!"); return
    matches = await get_upcoming_matches()
    if not matches:
        await msg.edit_text("😐 Немає запланованих матчів на сьогодні"); return
    matches = sorted(matches, key=lambda x: x.get("fixture",{}).get("date",""))[:15]
    text = f"📅 *Матчі на сьогодні ({len(matches)}):*\n\n"
    btns = []
    for fix in matches:
        m = parse_fixture(fix)
        if not m: continue
        try:
            dt = datetime.fromisoformat(m["date"].replace("Z","+00:00"))
            t = dt.astimezone(TIMEZONE).strftime("%H:%M")
        except: t = "??:??"
        text += f"🕐 {t} | {m['home']} vs {m['away']}\n"
        btns.append([InlineKeyboardButton(f"📊 {t} {m['home'][:11]} vs {m['away'][:11]}", callback_data=f"a_{m['id']}_0")])
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns[:10]))

async def show_top_bets(update, context):
    msg = await update.message.reply_text("⭐ Шукаю найкращі ставки (live + лінія 12г)...")
    if not FOOTBALL_KEY:
        await msg.edit_text("❌ FOOTBALL_KEY не встановлено!"); return

    top = []

    # ── LIVE матчі ──
    live = await get_live_matches()
    if live:
        await msg.edit_text("⭐ Аналізую live матчі...")
        for fix in live[:8]:
            m = parse_fixture(fix)
            if not m: continue
            stats_raw = await get_fixture_stats(m["id"])
            stats = parse_stats(stats_raw, m["home"], m["away"]) if stats_raw else {}
            h2h = await get_h2h(m["home_id"], m["away_id"]) if m.get("home_id") else []
            prob, factors = calc_goal_probability(m, stats, h2h)
            recs = recommend_totals(m, prob, True)
            strong = [r for r in recs if r["confidence"] >= 60 and r["status"] in ["hot","good"]]
            if strong:
                top.append({"m": m, "recs": strong[:2], "prob": prob, "type": "live"})
            await asyncio.sleep(0.3)

    # ── Лінія — наступні 12 годин ──
    await msg.edit_text("⭐ Аналізую лінію на 12 годин...")
    upcoming_all = await get_upcoming_matches()
    upcoming = filter_next_12h(upcoming_all)

    if upcoming:
        # Сортуємо по часу і беремо перші 10
        upcoming = sorted(upcoming, key=lambda x: x.get("fixture",{}).get("date",""))[:10]
        for fix in upcoming:
            m = parse_fixture(fix)
            if not m: continue
            # Для лінії беремо тільки H2H (статистики ще немає)
            h2h = await get_h2h(m["home_id"], m["away_id"]) if m.get("home_id") else []
            prob, factors = calc_goal_probability(m, {}, h2h)
            recs = recommend_totals(m, prob, False, h2h)
            strong = [r for r in recs if r["confidence"] >= 60]
            if strong:
                # Додаємо час матчу
                try:
                    dt = datetime.fromisoformat(m["date"].replace("Z","+00:00"))
                    m["kick_off"] = dt.astimezone(TIMEZONE).strftime("%H:%M")
                except:
                    m["kick_off"] = "??:??"
                top.append({"m": m, "recs": strong[:2], "prob": prob, "type": "pre"})
            await asyncio.sleep(0.3)

    if not top:
        await msg.edit_text(
            "😐 Зараз немає ставок >60%\n\n"
            "Live матчів немає або H2H не дає сигналів.\n"
            "Спробуйте пізніше!"
        )
        return

    top.sort(key=lambda x: -x["prob"])

    text = "⭐ *Топ ставки:*\n\n"
    for item in top[:8]:
        m = item["m"]
        if item["type"] == "live":
            text += f"🔴 *{m['home']} {m['home_goals']}:{m['away_goals']} {m['away']}* | {m['elapsed']}'\n"
        else:
            text += f"📅 *{m['home']} vs {m['away']}* | 🕐{m.get('kick_off','')}\n"
        for rec in item["recs"]:
            icon = "🔥" if rec["status"] == "hot" else "🎯"
            text += f"{icon} {rec['bet']} — {rec['confidence']}%\n"
        text += "\n"
    text += "⚠️ _Аналітика для розваги!_"

    btns = []
    for i in top[:6]:
        is_live = i["type"] == "live"
        label = f"{'🔴' if is_live else '📅'} {i['m']['home'][:10]} vs {i['m']['away'][:10]}"
        btns.append([InlineKeyboardButton(label, callback_data=f"a_{i['m']['id']}_{'1' if is_live else '0'}")])

    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔴 Live матчі": await show_live(update, context)
    elif text == "📅 Лінія": await show_upcoming(update, context)
    elif text == "⭐ Топ ставки": await show_top_bets(update, context)
    elif text == "❓ Допомога":
        await update.message.reply_text(
            "❓ *Як користуватись:*\n\n"
            "🔥 *90%+* — дуже сильний сигнал\n"
            "🎯 *70-89%* — сильний сигнал\n"
            "🟡 *55-69%* — помірний сигнал\n\n"
            "📊 *Що аналізую:*\n"
            "• Темп голів і прогноз\n"
            "• Удари і удари в ціль\n"
            "• xG (очікувані голи)\n"
            "• Кутові удари\n"
            "• H2H останні 8 матчів\n"
            "• Фаза матчу\n\n"
            "💡 Кеш зменшує запити до API\n"
            "Оновлення даних кожні 1-5 хв\n\n"
            "⚠️ _НЕ гарантія виграшу! Ставте відповідально!_",
            parse_mode="Markdown"
        )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    if not d.startswith("a_"): return
    parts = d.split("_")
    fixture_id = int(parts[1])
    is_live = parts[2] == "1"

    await q.edit_message_text("⏳ Аналізую матч...")

    if is_live:
        all_live = await get_live_matches()
        fix_data = next((f for f in (all_live or []) if f.get("fixture",{}).get("id") == fixture_id), None)
    else:
        result = await football_request("fixtures", {"id": fixture_id}, "stats")
        fix_data = result[0] if result else None

    if not fix_data:
        await q.edit_message_text("❌ Матч не знайдено або вже завершився"); return

    match = parse_fixture(fix_data)
    if not match:
        await q.edit_message_text("❌ Помилка даних"); return

    stats_raw = await get_fixture_stats(fixture_id)
    stats = parse_stats(stats_raw, match["home"], match["away"]) if stats_raw else {}

    h2h = []
    if match.get("home_id") and match.get("away_id"):
        h2h = await get_h2h(match["home_id"], match["away_id"]) or []

    prob, factors = calc_goal_probability(match, stats, h2h)
    recs = recommend_totals(match, prob, is_live, h2h)
    text = format_analysis(match, stats, recs, factors, is_live)

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Оновити", callback_data=f"a_{fixture_id}_{'1' if is_live else '0'}")]])
    try:
        await q.edit_message_text(text[:4096], parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        logger.error(f"Send error: {e}")
        await q.edit_message_text(text[:4000] + "\n\n⚠️ _Аналітика для розваги!_", parse_mode="Markdown", reply_markup=kb)

def main():
    if not BOT_TOKEN: logger.error("BOT_TOKEN not set!"); return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Bet bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
