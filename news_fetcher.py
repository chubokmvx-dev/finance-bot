import feedparser
import requests
import logging
import re
import calendar
from datetime import datetime, timezone, timedelta
import config

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}

def _extract_og_image(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=6)
        match = re.search(
            r'<meta[^>]+(?:property=["\']og:image["\'])[^>]+content=["\']([^"\']+)["\']',
            r.text, re.IGNORECASE
        )
        if not match:
            match = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                r.text, re.IGNORECASE
            )
        if match:
            img = match.group(1).strip()
            if img and not img.endswith(('.svg', '.ico')) and len(img) > 10:
                return img
    except Exception as e:
        logger.debug(f"og:image fetch failed for {url}: {e}")
    return None


class NewsFetcher:

    def _is_recent(self, entry) -> bool:
        """Чи опублікована новина за останні 24 години."""
        try:
            t = entry.get("published_parsed")
            if not t:
                return True  # немає дати — беремо
            pub = datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
            return datetime.now(timezone.utc) - pub < timedelta(hours=12)

        except:
            return True

    def fetch_all(self) -> list[dict]:
        articles = []
        for feed_url in config.RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:15]:
                    image_url = None
                    if hasattr(entry, "media_content"):
                        for m in entry.media_content:
                            if m.get("medium") == "image" or str(m.get("url","")).endswith((".jpg",".jpeg",".png",".webp")):
                                image_url = m.get("url"); break
                    if not image_url and hasattr(entry, "enclosures"):
                        for enc in entry.enclosures:
                            if enc.get("type","").startswith("image/"):
                                image_url = enc.get("href") or enc.get("url"); break

                    article = {
                        "title":     entry.get("title", "").strip(),
                        "summary":   entry.get("summary", entry.get("description", "")).strip(),
                        "url":       entry.get("link", ""),
                        "source":    feed.feed.get("title", feed_url),
                        "published": entry.get("published", ""),
                        "image_url": image_url,
                    }
                    if article["title"] and article["url"] and self._is_recent(entry):
                        articles.append(article)
            except Exception as e:
                logger.warning(f"Feed error {feed_url}: {e}")

        logger.info(f"Fetched {len(articles)} articles total")
        return articles

    def enrich_with_image(self, article: dict) -> dict:
        if not article.get("image_url") and article.get("url"):
            article["image_url"] = _extract_og_image(article["url"])
        return article
