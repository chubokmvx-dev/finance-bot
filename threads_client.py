import httpx
import logging
import json
import os
import config

logger = logging.getLogger(__name__)

SEEN_COMMENTS_FILE = "seen_comments.json"


def _load_seen_comments() -> set:
    if os.path.exists(SEEN_COMMENTS_FILE):
        with open(SEEN_COMMENTS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def _save_seen_comments(seen: set):
    with open(SEEN_COMMENTS_FILE, "w") as f:
        json.dump(list(seen), f)


async def create_post(text: str, image_url: str | None) -> str:
    """
    Creates a Threads post. Returns the post ID.
    Two-step process: create container → publish.
    """
    async with httpx.AsyncClient(timeout=30) as client:

        # Step 1: Create media container
        params = {
            "access_token": config.THREADS_ACCESS_TOKEN,
            "text": text,
        }
        if image_url:
            params["media_type"] = "IMAGE"
            params["image_url"] = image_url
        else:
            params["media_type"] = "TEXT"

        resp = await client.post(
            f"{config.THREADS_API_BASE}/{config.THREADS_USER_ID}/threads",
            params=params,
        )
        resp.raise_for_status()
        creation_id = resp.json()["id"]
        logger.info(f"Container created: {creation_id}")

        # Step 2: Publish
        resp2 = await client.post(
            f"{config.THREADS_API_BASE}/{config.THREADS_USER_ID}/threads_publish",
            params={
                "access_token": config.THREADS_ACCESS_TOKEN,
                "creation_id": creation_id,
            },
        )
        resp2.raise_for_status()
        post_id = resp2.json()["id"]
        logger.info(f"Post published: {post_id}")
        return post_id


async def get_user_posts(limit: int = 10) -> list[dict]:
    """Get recent posts by the user"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{config.THREADS_API_BASE}/{config.THREADS_USER_ID}/threads",
            params={
                "access_token": config.THREADS_ACCESS_TOKEN,
                "fields": "id,text,timestamp",
                "limit": limit,
            },
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


async def get_new_comments() -> list[dict]:
    """
    Checks all recent posts for new comments.
    Returns list of new comments not seen before.
    """
    seen = _load_seen_comments()
    new_comments = []

    posts = await get_user_posts(limit=5)

    async with httpx.AsyncClient(timeout=30) as client:
        for post in posts:
            resp = await client.get(
                f"{config.THREADS_API_BASE}/{post['id']}/replies",
                params={
                    "access_token": config.THREADS_ACCESS_TOKEN,
                    "fields": "id,text,username,timestamp,replied_to",
                },
            )
            if resp.status_code != 200:
                continue

            replies = resp.json().get("data", [])
            for reply in replies:
                comment_id = reply["id"]
                if comment_id not in seen:
                    seen.add(comment_id)
                    new_comments.append({
                        "comment_id": comment_id,
                        "post_id": post["id"],
                        "post_text": post.get("text", ""),
                        "username": reply.get("username", "unknown"),
                        "text": reply.get("text", ""),
                        "timestamp": reply.get("timestamp", ""),
                    })

    _save_seen_comments(seen)
    return new_comments


async def reply_to_comment(comment_id: str, text: str) -> str:
    """Reply to a specific comment. Returns reply ID."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Create reply container
        resp = await client.post(
            f"{config.THREADS_API_BASE}/{config.THREADS_USER_ID}/threads",
            params={
                "access_token": config.THREADS_ACCESS_TOKEN,
                "media_type": "TEXT",
                "text": text,
                "reply_to_id": comment_id,
            },
        )
        resp.raise_for_status()
        creation_id = resp.json()["id"]

        # Publish reply
        resp2 = await client.post(
            f"{config.THREADS_API_BASE}/{config.THREADS_USER_ID}/threads_publish",
            params={
                "access_token": config.THREADS_ACCESS_TOKEN,
                "creation_id": creation_id,
            },
        )
        resp2.raise_for_status()
        return resp2.json()["id"]
