# X Scraper — Deployment Guide

## Stack
- **Vercel** — hosts the FastAPI endpoint (free tier)
- **cron-job.org** — triggers the scrape every 30 min (free)
- **Upstash Redis** — deduplication store (free, already configured)
- **Telegram** — lead notifications (free)
- **Gmail** — email fallback
- **Claude API** — AI qualification + reply generation

---

## Step 1 — Get Your X Cookies

1. Open Chrome → go to **https://x.com** and log in with your X Premium account
2. Press `F12` → **Application** tab → **Cookies** → click `https://x.com`
3. Find and copy these cookie values:

| Cookie Name | Env Variable |
|---|---|
| `auth_token` | `X_AUTH_TOKEN` |
| `ct0` | `X_CT0` |
| `guest_id` | `X_GUEST_ID` |
| `twid` | `X_TWID` |

> Cookies expire after ~30-60 days. You'll need to refresh them when the scraper stops returning results.

---

## Step 2 — Set Up Telegram Bot

1. Open Telegram → search for **@BotFather** → send `/newbot`
2. Follow prompts → copy the **bot token** (format: `123456:ABC-DEF...`)
3. Start a conversation with your new bot (send any message)
4. Visit in browser: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
5. Find `"chat": {"id": 123456789}` → that number is your `TELEGRAM_CHAT_ID`

---

## Step 3 — Gmail App Password

1. Go to **myaccount.google.com → Security → 2-Step Verification** (enable if not already)
2. Go to **myaccount.google.com → Security → App passwords**
3. Generate password for "Mail" → copy the 16-character password
4. Use this as `SMTP_PASSWORD` (NOT your Gmail login password)

---

## Step 4 — Deploy to Vercel

```bash
# Install Vercel CLI
npm install -g vercel

# From the x-scrapper directory
cd x-scrapper
vercel login
vercel --prod
```

Or push to GitHub and connect the repo at **vercel.com/new**.

---

## Step 5 — Set Environment Variables in Vercel

Go to your project on **vercel.com** → **Settings** → **Environment Variables**.
Add each variable from `.env.example`:

```
X_AUTH_TOKEN          = (from Chrome DevTools)
X_CT0                 = (from Chrome DevTools)
X_GUEST_ID            = (from Chrome DevTools)
X_TWID                = (from Chrome DevTools)
ANTHROPIC_API_KEY     = (your Anthropic key)
UPSTASH_REDIS_REST_URL    = https://x-scrap.upstash.io
UPSTASH_REDIS_REST_TOKEN  = 1163a65a-4ad6-4a60-b138-b23173616347
TELEGRAM_BOT_TOKEN    = (from BotFather)
TELEGRAM_CHAT_ID      = (from getUpdates)
SMTP_EMAIL            = km.habibs@gmail.com
SMTP_PASSWORD         = (Gmail app password)
SMTP_TO               = km.habibs@gmail.com
CRON_SECRET           = (make up any random string, e.g. "mysecret123")
MAX_RESULTS           = 25
```

---

## Step 6 — Set Up cron-job.org

1. Go to **https://cron-job.org** → sign up free
2. Create new cron job:
   - **URL**: `https://your-project.vercel.app/api/scrape`
   - **Schedule**: Every 30 minutes
   - **Request method**: GET
   - **Headers**: Add `x-cron-secret` = your `CRON_SECRET` value
3. Save → enable

---

## Step 7 — Test It

Check health first:
```
https://your-project.vercel.app/api/health
```
Should return `{"status": "healthy", ...}` with all `true` values.

Then trigger manually:
```
curl -H "x-cron-secret: mysecret123" https://your-project.vercel.app/api/scrape
```

You should get a Telegram message within 30 seconds.

---

## What You Get in Telegram

For each confirmed lead:

```
🎯 Lead 1/3 — @johndoe

📝 Post:
Looking for a Next.js developer to build my SaaS dashboard...

🔗 https://x.com/johndoe/status/...

🤖 AI Reason: User is explicitly seeking to hire a Next.js developer for a paid project

💬 Reply A (Public Comment):
Built several SaaS dashboards in Next.js + MongoDB — happy to share what's worked well. What's the core feature you're prioritizing?

📩 Reply B (DM):
Hi John! Saw your post about the SaaS dashboard — I specialize in exactly this (Next.js, MongoDB Atlas, Tailwind). I've shipped 3 similar products recently. Would love to chat if you're still looking — what's your timeline looking like?

👥 Followers: 2400
```

You then manually go to X, review the post, and paste whichever reply fits.

---

## Costs

| Service | Cost |
|---|---|
| Vercel | Free |
| cron-job.org | Free |
| Upstash Redis | Free (10k cmds/day) |
| Telegram | Free |
| Claude API | ~$0.01–0.05 per run (pennies/month) |
| **Total** | **~$0–2/month** |
