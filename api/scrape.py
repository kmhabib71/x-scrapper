"""
FastAPI endpoint for Vercel serverless deployment.
Triggered by cron-job.org every 30 minutes.
Also serves dashboard API routes consumed by the Next.js frontend.
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(".env.example")  # local dev — Vercel uses dashboard env vars

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="X Scraper API", version="2.0.0")

# Allow Next.js dashboard (any Vercel domain) to call these APIs
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "PATCH"],
    allow_headers=["*"],
)


# ─── Root ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "status": "X Scraper is running",
        "endpoints": ["/api/health", "/api/scrape", "/api/leads", "/api/stats"],
    }


# ─── Scrape (called by cron-job.org) ─────────────────────────────────────────

@app.get("/api/scrape")
async def scrape_endpoint(request: Request):
    """Main scraping endpoint — protected by CRON_SECRET header."""
    cron_secret = os.environ.get("CRON_SECRET", "")
    if cron_secret:
        provided = request.headers.get("x-cron-secret", "")
        if provided != cron_secret:
            raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from scrapper.x_search import search_x
        from scrapper.dedup import filter_new_posts
        from scrapper.ai_processor import process_posts
        from scrapper.notifier import notify_leads, notify_summary
        from scrapper.database import save_leads

        max_results = int(os.environ.get("MAX_RESULTS", "25"))
        logger.info("Starting X scrape run...")

        # 1. Scrape X
        posts = search_x(max_results=max_results)

        # 2. Deduplicate via Upstash Redis
        new_posts = filter_new_posts(posts)

        # 3. AI qualify + generate replies
        leads = process_posts(new_posts)

        # 4. Save to MongoDB Atlas
        saved = save_leads(leads)

        # 5. Notify via Telegram
        notify_leads(leads)
        notify_summary(len(leads), len(posts))

        return JSONResponse({
            "status": "ok",
            "posts_fetched": len(posts),
            "new_posts": len(new_posts),
            "leads_found": len(leads),
            "leads_saved_to_db": saved,
        })

    except ValueError as e:
        logger.error(f"Scrape run failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Scrape run failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ─── Dashboard API routes (consumed by Next.js) ───────────────────────────────

@app.get("/api/leads")
async def get_leads(
    status: str = Query(None, description="Filter by status: pending, replied, skipped"),
    limit: int = Query(50, le=200),
    skip: int = Query(0),
):
    """Return leads for the dashboard."""
    try:
        from scrapper.database import get_leads
        leads = get_leads(status=status, limit=limit, skip=skip)
        return JSONResponse({"leads": leads, "count": len(leads)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/leads/{tweet_id}")
async def update_lead(tweet_id: str, request: Request):
    """Update a lead's status — called when user marks replied/skipped."""
    try:
        body = await request.json()
        status = body.get("status")
        if status not in ("pending", "replied", "skipped"):
            raise HTTPException(status_code=400, detail="status must be pending, replied, or skipped")
        from scrapper.database import update_lead_status
        update_lead_status(tweet_id, status)
        return JSONResponse({"ok": True})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats():
    """Summary stats for dashboard header."""
    try:
        from scrapper.database import get_stats
        return JSONResponse(get_stats())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Debug endpoint — shows raw X API response ───────────────────────────────

@app.get("/api/debug")
async def debug_x(request: Request):
    """Hits X directly and returns the raw status + response so we can diagnose issues."""
    cron_secret = os.environ.get("CRON_SECRET", "")
    if cron_secret:
        provided = request.headers.get("x-cron-secret", "")
        if provided != cron_secret:
            raise HTTPException(status_code=401, detail="Unauthorized")

    import json as _json
    import httpx as _httpx

    auth_token = os.environ.get("X_AUTH_TOKEN", "")
    ct0 = os.environ.get("X_CT0", "")
    guest_id = os.environ.get("X_GUEST_ID", "")
    twid = os.environ.get("X_TWID", "")

    cookie_parts = [f"auth_token={auth_token}", f"ct0={ct0}"]
    if guest_id:
        cookie_parts.append(f"guest_id={guest_id}")
    if twid:
        cookie_parts.append(f"twid={twid}")

    GRAPHQL_HASH = "pCd62NDD9dlCDgEGgEVHMg"
    url = f"https://x.com/i/api/graphql/{GRAPHQL_HASH}/SearchTimeline"

    features = {
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

    params = {
        "variables": _json.dumps({
            "rawQuery": "hiring web developer",
            "count": 5,
            "querySource": "typed_query",
            "product": "Latest",
        }),
        "features": _json.dumps(features),
    }

    headers = {
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "x-csrf-token": ct0,
        "cookie": "; ".join(cookie_parts),
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
        "content-type": "application/json",
    }

    try:
        with _httpx.Client(timeout=20) as client:
            resp = client.get(url, params=params, headers=headers, follow_redirects=True)
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:500]
            return JSONResponse({
                "status_code": resp.status_code,
                "hash_used": GRAPHQL_HASH,
                "response_preview": body if isinstance(body, dict) else body,
                "has_data": "data" in body if isinstance(body, dict) else False,
            })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    checks = {
        "X_AUTH_TOKEN": bool(os.environ.get("X_AUTH_TOKEN")),
        "X_CT0": bool(os.environ.get("X_CT0")),
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "UPSTASH_REDIS_REST_URL": bool(os.environ.get("UPSTASH_REDIS_REST_URL")),
        "UPSTASH_REDIS_REST_TOKEN": bool(os.environ.get("UPSTASH_REDIS_REST_TOKEN")),
        "TELEGRAM_BOT_TOKEN": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "TELEGRAM_CHAT_ID": bool(os.environ.get("TELEGRAM_CHAT_ID")),
        "MONGODB_URI": bool(os.environ.get("MONGODB_URI")),
    }
    all_ok = all(checks.values())
    return JSONResponse(
        {"status": "healthy" if all_ok else "missing_env_vars", "checks": checks},
        status_code=200 if all_ok else 500,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
