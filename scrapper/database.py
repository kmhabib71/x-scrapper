"""
MongoDB Atlas integration — saves every confirmed lead so the
Next.js dashboard can display them.

Collection: leads
Database:   x_scrapper
"""

import os
import logging
from datetime import datetime, timezone
from pymongo import MongoClient, DESCENDING
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

_client = None


def _get_db():
    global _client
    if _client is None:
        uri = os.environ["MONGODB_URI"]
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _client["x_scrapper"]


def save_lead(lead: dict) -> bool:
    """
    Save a confirmed lead to MongoDB.
    Returns True if saved, False if already exists (duplicate).
    """
    try:
        db = _get_db()
        doc = {
            "_id": lead["id"],           # tweet ID as primary key — prevents duplicates
            "tweet_id": lead["id"],
            "username": lead["username"],
            "display_name": lead.get("display_name", lead["username"]),
            "text": lead["text"],
            "url": lead["url"],
            "followers": lead.get("followers", 0),
            "tweet_created_at": lead.get("created_at", ""),
            "ai_reason": lead.get("ai_reason", ""),
            "reply_a": lead.get("reply_a", ""),
            "reply_b": lead.get("reply_b", ""),
            "status": "pending",         # pending | replied | skipped
            "saved_at": datetime.now(timezone.utc),
        }
        db["leads"].insert_one(doc)
        logger.info(f"Saved lead {lead['id']} (@{lead['username']}) to MongoDB")
        return True
    except DuplicateKeyError:
        logger.debug(f"Lead {lead['id']} already in MongoDB — skipping")
        return False
    except Exception as e:
        logger.error(f"MongoDB save error for {lead['id']}: {e}")
        return False


def save_leads(leads: list[dict]) -> int:
    """Save multiple leads. Returns count of newly saved leads."""
    saved = sum(1 for lead in leads if save_lead(lead))
    logger.info(f"MongoDB: saved {saved}/{len(leads)} leads")
    return saved


def get_leads(status: str = None, limit: int = 100, skip: int = 0) -> list[dict]:
    """Fetch leads for dashboard. Optionally filter by status."""
    try:
        db = _get_db()
        query = {}
        if status:
            query["status"] = status
        cursor = (
            db["leads"]
            .find(query, {"_id": 0})
            .sort("saved_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        leads = []
        for doc in cursor:
            # Convert datetime to ISO string for JSON serialization
            if "saved_at" in doc and hasattr(doc["saved_at"], "isoformat"):
                doc["saved_at"] = doc["saved_at"].isoformat()
            leads.append(doc)
        return leads
    except Exception as e:
        logger.error(f"MongoDB fetch error: {e}")
        return []


def update_lead_status(tweet_id: str, status: str) -> bool:
    """Update a lead's status (pending → replied / skipped)."""
    try:
        db = _get_db()
        db["leads"].update_one(
            {"tweet_id": tweet_id},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
        )
        return True
    except Exception as e:
        logger.error(f"MongoDB update error for {tweet_id}: {e}")
        return False


def get_stats() -> dict:
    """Get summary stats for dashboard header."""
    try:
        db = _get_db()
        total = db["leads"].count_documents({})
        pending = db["leads"].count_documents({"status": "pending"})
        replied = db["leads"].count_documents({"status": "replied"})
        skipped = db["leads"].count_documents({"status": "skipped"})
        return {"total": total, "pending": pending, "replied": replied, "skipped": skipped}
    except Exception as e:
        logger.error(f"MongoDB stats error: {e}")
        return {"total": 0, "pending": 0, "replied": 0, "skipped": 0}
