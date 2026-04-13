"""
Standalone scraper script — run by GitHub Actions every 30 minutes.
Uses the same scrapper modules as the Vercel API.
"""

import os
import logging
import sys
from dotenv import load_dotenv

# Load local credentials — works both locally (.env) and in CI (env vars already set)
load_dotenv(".env")           # try .env first
load_dotenv(".env.example")   # fallback to .env.example for local dev

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=== X Lead Scraper starting ===")

    try:
        from scrapper.x_search import search_x
        from scrapper.dedup import filter_new_posts
        from scrapper.ai_processor import process_posts
        from scrapper.notifier import notify_leads, notify_summary
        from scrapper.database import save_leads

        max_results = int(os.environ.get("MAX_RESULTS", "25"))

        # 1. Scrape X
        logger.info("Searching X...")
        posts = search_x(max_results=max_results)
        logger.info(f"Fetched {len(posts)} posts from X")

        # 2. Deduplicate
        new_posts = filter_new_posts(posts)
        logger.info(f"New posts after dedup: {len(new_posts)}")

        if not new_posts:
            logger.info("No new posts — nothing to process")
            notify_summary(0, len(posts))
            return

        # 3. AI qualify + generate replies
        leads = process_posts(new_posts)
        logger.info(f"Confirmed leads: {len(leads)}")

        # 4. Save to MongoDB
        saved = save_leads(leads)
        logger.info(f"Saved to MongoDB: {saved}")

        # 5. Notify via Telegram
        notify_leads(leads)
        notify_summary(len(leads), len(posts))

        logger.info(f"=== Done — {len(leads)} leads found, {saved} saved ===")

    except Exception as e:
        logger.error(f"Scraper failed: {e}", exc_info=True)
        # Notify on failure so you know something went wrong
        try:
            from scrapper.notifier import _send_telegram
            _send_telegram(f"X Scraper ERROR: {str(e)[:200]}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
