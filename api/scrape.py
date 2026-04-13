"""
FastAPI endpoint for Vercel serverless deployment.

Vercel treats any file in /api as a serverless function.
This endpoint is triggered by cron-job.org every 30-60 minutes.

Deployment flow:
1. Deploy this repo to Vercel
2. Add all env vars in Vercel dashboard → Settings → Environment Variables
3. Go to https://cron-job.org → create a free cron job:
   - URL: https://your-project.vercel.app/api/scrape
   - Schedule: every 30 minutes
   - Add header: x-cron-secret: <your CRON_SECRET value>
4. Done — leads arrive in Telegram automatically.

Security: the endpoint requires a secret header to prevent unauthorized triggers.
"""

import os
import sys
import logging

# Ensure scrapper package is importable when running as Vercel function
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="X Scraper API", version="1.0.0")


@app.get("/api/scrape")
async def scrape_endpoint(request: Request):
    """
    Main scraping endpoint. Called by cron-job.org on schedule.
    Protected by CRON_SECRET header.
    """
    # Security: validate secret header
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

        max_results = int(os.environ.get("MAX_RESULTS", "25"))

        logger.info("Starting X scrape run...")

        # 1. Scrape X
        posts = search_x(max_results=max_results)
        logger.info(f"Fetched {len(posts)} posts from X")

        # 2. Filter already-seen posts
        new_posts = filter_new_posts(posts)

        # 3. AI qualify + generate replies
        leads = process_posts(new_posts)

        # 4. Notify
        notify_leads(leads)
        notify_summary(len(leads), len(posts))

        return JSONResponse({
            "status": "ok",
            "posts_fetched": len(posts),
            "new_posts": len(new_posts),
            "leads_found": len(leads),
        })

    except ValueError as e:
        # Auth errors, rate limits — don't retry immediately
        logger.error(f"Scrape run failed (value error): {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Scrape run failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/api/health")
async def health():
    """Health check — verify env vars are set."""
    checks = {
        "X_AUTH_TOKEN": bool(os.environ.get("X_AUTH_TOKEN")),
        "X_CT0": bool(os.environ.get("X_CT0")),
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "UPSTASH_REDIS_REST_URL": bool(os.environ.get("UPSTASH_REDIS_REST_URL")),
        "UPSTASH_REDIS_REST_TOKEN": bool(os.environ.get("UPSTASH_REDIS_REST_TOKEN")),
        "TELEGRAM_BOT_TOKEN": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "TELEGRAM_CHAT_ID": bool(os.environ.get("TELEGRAM_CHAT_ID")),
    }
    all_ok = all(checks.values())
    return JSONResponse(
        {"status": "healthy" if all_ok else "missing_env_vars", "checks": checks},
        status_code=200 if all_ok else 500,
    )


# Allow running locally: python api/scrape.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
