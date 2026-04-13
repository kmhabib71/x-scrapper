"""
Notification module — sends lead alerts via Telegram (primary) with
Gmail SMTP as fallback.

Telegram setup:
1. Message @BotFather on Telegram → /newbot → copy the token
2. Start a chat with your bot, then visit:
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   to find your chat_id (look for "id" inside "chat")
3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env

Gmail SMTP setup:
1. Enable 2FA on your Google account
2. Go to myaccount.google.com → Security → App passwords
3. Generate an app password for "Mail"
4. Set SMTP_PASSWORD to that 16-char app password (not your Gmail password)
"""

import os
import logging
import smtplib
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _escape_md(text: str) -> str:
    """Escape characters that break Telegram MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _format_lead_message(lead: dict, index: int, total: int) -> str:
    """Format a single lead into a readable Telegram MarkdownV2 message."""
    post_text = lead['text'][:400] + ('…' if len(lead['text']) > 400 else '')
    return (
        f"🎯 *Lead {index}/{total} — @{_escape_md(lead['username'])}*\n\n"
        f"📝 *Post:*\n{_escape_md(post_text)}\n\n"
        f"🔗 {_escape_md(lead['url'])}\n\n"
        f"🤖 *AI Reason:* {_escape_md(lead['ai_reason'])}\n\n"
        f"💬 *Reply A \\(Public\\):*\n{_escape_md(lead['reply_a'])}\n\n"
        f"📩 *Reply B \\(DM\\):*\n{_escape_md(lead['reply_b'])}\n\n"
        f"👥 Followers: {lead.get('followers', 'N/A')}"
    )


def _send_telegram(message: str) -> bool:
    """Send a Telegram message. Returns True on success."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("Telegram not configured — skipping")
        return False

    try:
        response = httpx.post(
            TELEGRAM_API.format(token=token),
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        response.raise_for_status()
        logger.info("Telegram notification sent")
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def _send_email(subject: str, body: str) -> bool:
    """Send email via Gmail SMTP. Returns True on success."""
    smtp_email = os.environ.get("SMTP_EMAIL", "km.habibs@gmail.com")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_to = os.environ.get("SMTP_TO", "km.habibs@gmail.com")

    if not smtp_password:
        logger.warning("SMTP_PASSWORD not set — skipping email fallback")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_email
        msg["To"] = smtp_to

        # Plain text version
        text_part = MIMEText(body, "plain", "utf-8")
        msg.attach(text_part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, smtp_to, msg.as_string())

        logger.info(f"Email sent to {smtp_to}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def notify_leads(leads: list[dict]) -> None:
    """
    Send notifications for all confirmed leads.
    Tries Telegram first; falls back to email if Telegram fails.
    """
    if not leads:
        logger.info("No new leads to notify")
        return

    total = len(leads)
    logger.info(f"Sending notifications for {total} lead(s)")

    for i, lead in enumerate(leads, 1):
        message = _format_lead_message(lead, i, total)

        # Try Telegram first
        sent = _send_telegram(message)

        # Fallback to email
        if not sent:
            subject = f"[X Lead {i}/{total}] @{lead['username']} is hiring a web developer"
            # Strip markdown for email
            plain_body = message.replace("*", "").replace("🎯", ">>").replace("📝", "").replace("🔗", "").replace("🤖", "").replace("💬", "").replace("📩", "").replace("👥", "")
            _send_email(subject, plain_body)


def notify_summary(leads_count: int, posts_checked: int) -> None:
    """Send a brief run summary (useful for debugging/monitoring)."""
    msg = _escape_md(f"X Scraper run complete: checked {posts_checked} posts, found {leads_count} new lead(s).")
    if leads_count == 0:
        _send_telegram(f"ℹ️ {msg}")
