import requests
import logging
from datetime import datetime, timedelta
import config

logger = logging.getLogger(__name__)

RAPIDAPI_HOST = "api-football-v1.p.rapidapi.com"
HEADERS = {
    "X-RapidAPI-Key":  config.FOOTBALL_API_KEY,
    "X-RapidAPI-Host": RAPIDAPI_HOST,
}

class FootballTracker:

    def _get(self, endpoint: str, params: dict) -> dict | None:
        try:
            r = requests.get(
                f"https://{RAPIDAPI_HOST}/v3/{endpoint}",
                headers=HEADERS,
                params=params,
                timeout=10
            )
            data = r.json()
            if data.get("errors"):
                logger.error(f"Football API errors: {data['errors']}")
                return None
            return data
        except Exception as e:
            logger.error(f"Football API exception: {e}")
            return None

    def get_live_match(self) -> dict | None:
        """Повертає поточний live-матч Буковини або None."""
        data = self._get("fixtures", {
            "team": config.BUKOVYNA_TEAM_ID,
            "live": "all"
        })
        if not data or not data.get("response"):
            return None

        fixture = data["response"][0]
        return self._parse_fixture(fixture)

    def get_upcoming_match(self) -> dict | None:
        """Повертає наступний матч Буковини (в межах 3 днів)."""
        today = datetime.now().strftime("%Y-%m-%d")
        in_3_days = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

        data = self._get("fixtures", {
            "team": config.BUKOVYNA_TEAM_ID,
            "from": today,
            "to":   in_3_days,
            "status": "NS"   # Not Started
        })
        if not data or not data.get("response"):
            return None

        return self._parse_fixture(data["response"][0])

    def get_today_match(self) -> dict | None:
        """Повертає матч Буковини сьогодні."""
        today = datetime.now().strftime("%Y-%m-%d")
        data = self._get("fixtures", {
            "team": config.BUKOVYNA_TEAM_ID,
            "date": today,
        })
        if not data or not data.get("response"):
            return None
        return self._parse_fixture(data["response"][0])

    def _parse_fixture(self, f: dict) -> dict:
        fixture   = f.get("fixture", {})
        teams     = f.get("teams", {})
        goals     = f.get("goals", {})
        league    = f.get("league", {})
        score_obj = f.get("score", {})

        # Рахунок поточного тайму
        home_score = goals.get("home") or 0
        away_score = goals.get("away") or 0

        return {
            "id":         str(fixture.get("id", "")),
            "status":     fixture.get("status", {}).get("short", "NS"),
            "minute":     fixture.get("status", {}).get("elapsed", 0),
            "date":       fixture.get("date", ""),
            "home_team":  teams.get("home", {}).get("name", ""),
            "away_team":  teams.get("away", {}).get("name", ""),
            "home_score": home_score,
            "away_score": away_score,
            "league":     league.get("name", ""),
            "round":      league.get("round", ""),
        }

    def is_match_day(self) -> bool:
        """Чи є матч Буковини сьогодні?"""
        return self.get_today_match() is not None
