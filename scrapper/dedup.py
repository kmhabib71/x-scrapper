"""
Deduplication via Upstash Redis REST API.
Stores seen post IDs with a 30-day TTL so the set never grows unbounded.

Upstash Redis REST API docs: https://docs.upstash.com/redis/features/restapi
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)

POST_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days
KEY_PREFIX = "xscrap:seen:"


def _get_upstash_config() -> tuple[str, str]:
    url = os.environ["UPSTASH_REDIS_REST_URL"].rstrip("/")
    token = os.environ["UPSTASH_REDIS_REST_TOKEN"]
    return url, token


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def is_seen(post_id: str) -> bool:
    """Return True if this post ID has already been processed."""
    url, token = _get_upstash_config()
    key = f"{KEY_PREFIX}{post_id}"
    try:
        response = httpx.get(
            f"{url}/exists/{key}",
            headers=_headers(token),
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        # Upstash returns {"result": 1} if key exists, {"result": 0} if not
        return bool(data.get("result", 0))
    except Exception as e:
        logger.warning(f"Upstash is_seen check failed for {post_id}: {e} — treating as unseen")
        return False


def mark_seen(post_id: str) -> None:
    """Mark a post ID as processed with a 30-day TTL."""
    url, token = _get_upstash_config()
    key = f"{KEY_PREFIX}{post_id}"
    try:
        # SET key value EX ttl — pipeline via REST
        response = httpx.get(
            f"{url}/set/{key}/1/ex/{POST_TTL_SECONDS}",
            headers=_headers(token),
            timeout=10,
        )
        response.raise_for_status()
        logger.debug(f"Marked post {post_id} as seen in Upstash")
    except Exception as e:
        logger.warning(f"Upstash mark_seen failed for {post_id}: {e}")


def filter_new_posts(posts: list[dict]) -> list[dict]:
    """Return only posts that haven't been seen before, and mark them as seen."""
    new_posts = []
    for post in posts:
        pid = post["id"]
        if not is_seen(pid):
            new_posts.append(post)
            mark_seen(pid)
    logger.info(f"Dedup: {len(posts)} total → {len(new_posts)} new")
    return new_posts
