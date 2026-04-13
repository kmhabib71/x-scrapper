"""
X (Twitter) scraper — uses Playwright to navigate X as a real browser,
intercepts the SearchTimeline GraphQL response automatically.
Cookies loaded from env vars — refresh every 30-60 days.
"""

import os
import json
import time
import random
import logging
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

SEARCH_QUERY = (
    '("hiring" OR "looking for" OR "need a" OR "freelance" OR '
    '"build me" OR "help me build") '
    '("web developer" OR "web dev" OR "frontend developer" OR "full stack" OR '
    '"react developer" OR "next.js" OR "nextjs" OR "AI developer" OR "python developer") '
    '-is:retweet lang:en'
)


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

                # Handle wrapper types
                if tweet_result.get("__typename") == "TweetWithVisibilityResults":
                    tweet_result = tweet_result.get("tweet", tweet_result)

                core = tweet_result.get("core", {})
                user_result = core.get("user_results", {}).get("result", {})

                # User fields — legacy is partial; screen_name/name moved to user_result.core
                legacy_user = user_result.get("legacy", {})
                user_core = user_result.get("core", {})

                # Tweet fields — try legacy first, fallback to note_tweet
                legacy_tweet = tweet_result.get("legacy", {})
                if not legacy_tweet:
                    legacy_tweet = tweet_result  # fallback

                # Get text — try full_text, then note_tweet body, then text
                text = (
                    legacy_tweet.get("full_text")
                    or tweet_result.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {}).get("text", "")
                    or legacy_tweet.get("text", "")
                )

                # Get username — X moved screen_name/name into user_result.core
                username = (
                    user_core.get("screen_name")
                    or legacy_user.get("screen_name")
                    or user_result.get("screen_name")
                    or ""
                )

                # Get tweet ID — try id_str, then rest_id
                tweet_id = (
                    legacy_tweet.get("id_str")
                    or tweet_result.get("rest_id", "")
                )

                created_at = legacy_tweet.get("created_at", "")

                # Skip retweets
                if legacy_tweet.get("retweeted_status_result"):
                    continue
                if text.startswith("RT @"):
                    continue

                if tweet_id and username and text:
                    display_name = (
                        user_core.get("name")
                        or legacy_user.get("name")
                        or username
                    )
                    posts.append({
                        "id": tweet_id,
                        "username": username,
                        "display_name": display_name,
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
    Search X by navigating a real Chromium browser with your cookies.
    Intercepts the SearchTimeline API response directly from network traffic.
    """
    auth_token = os.environ["X_AUTH_TOKEN"]
    ct0 = os.environ["X_CT0"]
    guest_id = os.environ.get("X_GUEST_ID", "")
    twid = os.environ.get("X_TWID", "")

    cookies = [
        {"name": "auth_token", "value": auth_token, "domain": ".x.com", "path": "/"},
        {"name": "ct0", "value": ct0, "domain": ".x.com", "path": "/"},
    ]
    if guest_id:
        cookies.append({"name": "guest_id", "value": guest_id, "domain": ".x.com", "path": "/"})
    if twid:
        cookies.append({"name": "twid", "value": twid, "domain": ".x.com", "path": "/"})

    captured_data = {}
    search_url = "https://x.com/search?q=hiring+web+developer&src=typed_query&f=live"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        context.add_cookies(cookies)
        page = context.new_page()

        # Intercept SearchTimeline response body
        def handle_response(response):
            if "SearchTimeline" in response.url and response.status == 200:
                try:
                    captured_data["data"] = response.json()
                    logger.info(f"Intercepted SearchTimeline — status 200")
                except Exception as e:
                    logger.warning(f"Could not parse SearchTimeline response: {e}")

        page.on("response", handle_response)

        try:
            time.sleep(random.uniform(1, 2))

            # Go to x.com home first to establish session
            page.goto("https://x.com", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # Navigate to search — browser makes the real API call automatically
            logger.info("Navigating to X search...")
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # Wait for the API response to be intercepted
            page.wait_for_timeout(6000)

        except Exception as e:
            logger.error(f"Playwright navigation error: {e}")
            browser.close()
            raise
        finally:
            browser.close()

    if not captured_data.get("data"):
        raise ValueError(
            "X search returned no data — cookies may be expired. "
            "Refresh X_AUTH_TOKEN and X_CT0 from Chrome DevTools."
        )

    posts = _extract_posts(captured_data["data"])
    logger.info(f"X search returned {len(posts)} posts")
    return posts
