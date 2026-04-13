"""
X (Twitter) scraper — uses X Premium cookies + internal GraphQL API.
No official API key required. Uses httpx for async-capable HTTP.

HOW TO GET YOUR X COOKIES (Chrome DevTools):
1. Open Chrome and go to https://x.com
2. Press F12 → Application tab → Cookies → https://x.com
3. Copy the values for: auth_token, ct0, guest_id, twid
4. Put them in your .env file as X_AUTH_TOKEN, X_CT0, X_GUEST_ID, X_TWID
"""

import os
import json
import time
import random
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

# Advanced search query targeting genuine hiring intent for web developers
SEARCH_QUERY = (
    '("hiring" OR "looking for" OR "need a" OR "recommend" OR "freelance" OR '
    '"build me" OR "website" OR "help me build") '
    '("web developer" OR "web dev" OR "frontend developer" OR "full stack" OR '
    '"react developer" OR "next.js developer" OR "nextjs" OR "mongodb") '
    '-is:retweet lang:en'
)

GRAPHQL_SEARCH_URL = "https://x.com/i/api/graphql/nK1dw4oV3k4w5TdtcAdSww/SearchTimeline"

FEATURES = {
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}


def _build_headers() -> dict:
    """Build request headers using X cookies from environment."""
    auth_token = os.environ["X_AUTH_TOKEN"]
    ct0 = os.environ["X_CT0"]
    guest_id = os.environ.get("X_GUEST_ID", "")
    twid = os.environ.get("X_TWID", "")

    cookie_parts = [f"auth_token={auth_token}", f"ct0={ct0}"]
    if guest_id:
        cookie_parts.append(f"guest_id={guest_id}")
    if twid:
        cookie_parts.append(f"twid={twid}")

    return {
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "x-csrf-token": ct0,
        "cookie": "; ".join(cookie_parts),
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "accept-language": "en-US,en;q=0.9",
        "referer": "https://x.com/search",
    }


def _extract_posts(response_data: dict) -> list[dict]:
    """Parse GraphQL response and extract post objects."""
    posts = []
    try:
        instructions = (
            response_data
            .get("data", {})
            .get("search_by_raw_query", {})
            .get("search_timeline", {})
            .get("timeline", {})
            .get("instructions", [])
        )
        for instruction in instructions:
            if instruction.get("type") != "TimelineAddEntries":
                continue
            for entry in instruction.get("entries", []):
                content = entry.get("content", {})
                if content.get("entryType") != "TimelineTimelineItem":
                    continue
                item_content = content.get("itemContent", {})
                if item_content.get("itemType") != "TimelineTweet":
                    continue
                tweet_result = item_content.get("tweet_results", {}).get("result", {})
                if not tweet_result:
                    continue

                # Handle retweet wrapper
                if tweet_result.get("__typename") == "TweetWithVisibilityResults":
                    tweet_result = tweet_result.get("tweet", tweet_result)

                core = tweet_result.get("core", {})
                user_result = core.get("user_results", {}).get("result", {})
                legacy_user = user_result.get("legacy", {})
                legacy_tweet = tweet_result.get("legacy", {})

                if not legacy_tweet or not legacy_user:
                    continue

                # Skip retweets
                if legacy_tweet.get("retweeted_status_result"):
                    continue

                tweet_id = legacy_tweet.get("id_str", "")
                username = legacy_user.get("screen_name", "")
                text = legacy_tweet.get("full_text", "")
                created_at = legacy_tweet.get("created_at", "")

                if tweet_id and username and text:
                    posts.append({
                        "id": tweet_id,
                        "username": username,
                        "display_name": legacy_user.get("name", username),
                        "text": text,
                        "url": f"https://x.com/{username}/status/{tweet_id}",
                        "created_at": created_at,
                        "followers": legacy_user.get("followers_count", 0),
                    })
    except Exception as e:
        logger.error(f"Failed to parse X response: {e}")
    return posts


def search_x(max_results: int = 25) -> list[dict]:
    """
    Search X for hiring-intent posts targeting web developers.
    Returns list of post dicts. Raises on auth failure.
    """
    params = {
        "variables": json.dumps({
            "rawQuery": SEARCH_QUERY,
            "count": max_results,
            "querySource": "typed_query",
            "product": "Latest",
        }),
        "features": json.dumps(FEATURES),
    }

    headers = _build_headers()

    # Random delay to appear natural
    time.sleep(random.uniform(2, 5))

    with httpx.Client(timeout=30) as client:
        try:
            response = client.get(
                GRAPHQL_SEARCH_URL,
                params=params,
                headers=headers,
                follow_redirects=True,
            )

            if response.status_code == 401:
                raise ValueError("X auth failed — check your X_AUTH_TOKEN and X_CT0 cookies")
            if response.status_code == 429:
                raise ValueError("X rate limit hit — wait before retrying")
            response.raise_for_status()

            data = response.json()
            posts = _extract_posts(data)
            logger.info(f"X search returned {len(posts)} posts")
            return posts

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from X: {e.response.status_code} — {e.response.text[:200]}")
            raise
        except Exception as e:
            logger.error(f"X search error: {e}")
            raise
