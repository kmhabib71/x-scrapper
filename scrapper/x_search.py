"""
X (Twitter) scraper — uses X Premium cookies + internal search API.
No official API key required.

HOW TO GET YOUR X COOKIES (Chrome DevTools):
1. Open Chrome and go to https://x.com and log in
2. Press F12 → Network tab → search for "SearchTimeline" in filter
3. OR: Application tab → Cookies → https://x.com
4. Copy: auth_token, ct0, guest_id, twid into your .env file

HOW TO FIND THE CURRENT GRAPHQL HASH (if 404 happens again):
1. Open Chrome → go to x.com → search anything in the search bar
2. Press F12 → Network tab → filter by "SearchTimeline"
3. Click the request → copy the URL path hash (the part after /graphql/)
4. Update GRAPHQL_HASH below
"""

import os
import json
import time
import random
import logging
import httpx

logger = logging.getLogger(__name__)

# Advanced search query targeting genuine hiring intent for web/AI developers
SEARCH_QUERY = (
    '("hiring" OR "looking for" OR "need a" OR "recommend" OR "freelance" OR '
    '"build me" OR "help me build") '
    '("web developer" OR "web dev" OR "frontend developer" OR "full stack" OR '
    '"react developer" OR "next.js" OR "nextjs" OR "AI developer" OR "python developer") '
    '-is:retweet lang:en'
)

# X internal GraphQL hash — update this if you get 404 errors
# To find current hash: Chrome DevTools → Network → filter "SearchTimeline" → copy URL hash
GRAPHQL_HASH = "pCd62NDD9dlCDgEGgEVHMg"
GRAPHQL_SEARCH_URL = f"https://x.com/i/api/graphql/{GRAPHQL_HASH}/SearchTimeline"

# Stable bearer token (same for all X web clients)
BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

# Exact features from live browser request (April 2026)
FEATURES = {
    "rweb_video_screen_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": True,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

FIELD_TOGGLES = {
    "withArticleRichContentState": True,
    "withArticlePlainText": False,
    "withGrokAnalyze": False,
    "withDisallowedReplyControls": False,
}


def _build_headers() -> dict:
    auth_token = os.environ["X_AUTH_TOKEN"]
    ct0 = os.environ["X_CT0"]
    guest_id = os.environ.get("X_GUEST_ID", "")
    twid = os.environ.get("X_TWID", "")

    # X_FULL_COOKIE: paste the entire cookie string from Chrome DevTools
    # Network tab → any x.com request → Request Headers → cookie → copy full value
    # This includes cf_clearance which helps bypass Cloudflare on server IPs
    full_cookie = os.environ.get("X_FULL_COOKIE", "")
    if full_cookie:
        cookie_str = full_cookie
    else:
        cookie_parts = [f"auth_token={auth_token}", f"ct0={ct0}"]
        if guest_id:
            cookie_parts.append(f"guest_id={guest_id}")
        if twid:
            cookie_parts.append(f"twid={twid}")
        cookie_str = "; ".join(cookie_parts)

    return {
        "authorization": f"Bearer {BEARER_TOKEN}",
        "x-csrf-token": ct0,
        "cookie": cookie_str,
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": "https://x.com/search?q=hiring+web+developer&src=typed_query&f=live",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "priority": "u=1, i",
    }


def _extract_posts(response_data: dict) -> list[dict]:
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

                if tweet_result.get("__typename") == "TweetWithVisibilityResults":
                    tweet_result = tweet_result.get("tweet", tweet_result)

                core = tweet_result.get("core", {})
                user_result = core.get("user_results", {}).get("result", {})
                legacy_user = user_result.get("legacy", {})
                legacy_tweet = tweet_result.get("legacy", {})

                if not legacy_tweet or not legacy_user:
                    continue
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


def _get_current_graphql_hash(headers: dict) -> str | None:
    """
    Auto-discover the current SearchTimeline GraphQL hash from X's main JS bundle.
    Falls back to None if it can't find it.
    """
    try:
        resp = httpx.get(
            "https://x.com/search?q=hiring+developer&src=typed_query&f=live",
            headers={
                "user-agent": headers["user-agent"],
                "cookie": headers["cookie"],
                "authorization": headers["authorization"],
            },
            timeout=15,
            follow_redirects=True,
        )
        # Look for the hash in the HTML (X embeds it in script tags)
        import re
        match = re.search(r'"SearchTimeline"\s*:\s*"([a-zA-Z0-9_-]{20,})"', resp.text)
        if match:
            found = match.group(1)
            logger.info(f"Auto-discovered GraphQL hash: {found}")
            return found
    except Exception as e:
        logger.warning(f"Hash auto-discovery failed: {e}")
    return None


def _get_proxy() -> dict | None:
    """
    Build proxy config from env vars if set.
    Supports any HTTP proxy — Webshare, Oxylabs, Brightdata, etc.

    Set these env vars (from Webshare free tier):
      PROXY_HOST     e.g. proxy.webshare.io
      PROXY_PORT     e.g. 80
      PROXY_USER     your proxy username
      PROXY_PASS     your proxy password
    """
    host = os.environ.get("PROXY_HOST", "")
    port = os.environ.get("PROXY_PORT", "80")
    user = os.environ.get("PROXY_USER", "")
    passwd = os.environ.get("PROXY_PASS", "")

    if not host:
        return None

    if user and passwd:
        proxy_url = f"http://{user}:{passwd}@{host}:{port}"
    else:
        proxy_url = f"http://{host}:{port}"

    logger.info(f"Using proxy: {host}:{port}")
    return {"http://": proxy_url, "https://": proxy_url}


def search_x(max_results: int = 25) -> list[dict]:
    """
    Search X for hiring-intent posts. Returns list of post dicts.
    Uses residential proxy if PROXY_HOST is set (required for cloud hosting).
    """
    headers = _build_headers()
    proxy = _get_proxy()

    params = {
        "variables": json.dumps({
            "rawQuery": SEARCH_QUERY,
            "count": max_results,
            "querySource": "typed_query",
            "product": "Latest",
        }),
        "features": json.dumps(FEATURES),
        "fieldToggles": json.dumps(FIELD_TOGGLES),
    }

    time.sleep(random.uniform(2, 4))

    client_kwargs = {"timeout": 40}
    if proxy:
        client_kwargs["proxy"] = proxy

    with httpx.Client(**client_kwargs) as client:
        search_url = GRAPHQL_SEARCH_URL

        try:
            response = client.get(search_url, params=params, headers=headers, follow_redirects=True)

            # If 404, try to auto-discover the new hash
            if response.status_code == 404:
                logger.warning("GraphQL 404 — attempting hash auto-discovery")
                new_hash = _get_current_graphql_hash(headers)
                if new_hash:
                    search_url = f"https://x.com/i/api/graphql/{new_hash}/SearchTimeline"
                    time.sleep(random.uniform(1, 3))
                    response = client.get(search_url, params=params, headers=headers, follow_redirects=True)
                else:
                    raise ValueError(
                        "X is blocking this IP (404). Set PROXY_HOST/PROXY_USER/PROXY_PASS "
                        "env vars with a residential proxy (Webshare free tier works)."
                    )

            if response.status_code == 401:
                raise ValueError("X auth failed — refresh your X cookies in env vars")
            if response.status_code == 429:
                raise ValueError("X rate limit hit — reduce MAX_RESULTS or increase interval")

            response.raise_for_status()

            data = response.json()
            posts = _extract_posts(data)
            logger.info(f"X search returned {len(posts)} posts")
            return posts

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from X: {e.response.status_code} — {e.response.text[:300]}")
            raise
        except Exception as e:
            logger.error(f"X search error: {e}")
            raise
