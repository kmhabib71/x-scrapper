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
