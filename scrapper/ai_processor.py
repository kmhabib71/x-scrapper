"""
Claude AI processor — qualifies posts as genuine hiring leads and
generates two reply drafts (public comment + DM) for each one.

Personalized for: Km Habib (@kmhabibs) — 8 years experience, Full-Stack + AI Dev
"""

import os
import logging
import anthropic

logger = logging.getLogger(__name__)

# Km Habib's full developer profile — injected into every reply prompt
DEVELOPER_PROFILE = """
Name: Km Habib (@kmhabibs)
GitHub: https://github.com/kmhabib71
Experience: 8 years building production full-stack and AI systems
Rate: $45/hour (Payoneer/Western Union)

Core Skills:
- Full-Stack: Next.js, React, Node.js (Express), TypeScript, Python, MongoDB Atlas, PostgreSQL, AWS, Docker
- AI/LLM: OpenAI, Anthropic Claude, custom AI agents, RAG pipelines, vector embeddings, MongoDB Atlas Vector Search, HuggingFace, LangChain, LlamaIndex, Groq, Venice AI
- Other: Tailwind CSS, REST/GraphQL APIs, webhooks, Pinecone, Weaviate, voice agents (Vapi/Retell), Make/Zapier/n8n

Real Projects Shipped:
1. bhara.com — No-broker rent marketplace (full-stack SaaS)
2. snappair.com — LFG social network
3. heartattack.me — Chain online restaurant ordering system
4. banffadvisors.com — Advisory firm automation platform
5. RomanceCanvas — Credit-based AI SaaS with custom agents, RAG pipelines, and vector embeddings for complex memory (full production, ready to launch)

Teaching: Udemy instructor — 10 courses, 50,000+ students (5 years)

Winning reply example (landed a year-long contract):
Post was: AI Developer hiring for Kortex Labs — custom agents, RAG, vector DBs
My public reply: "Experienced 6 years AI/Full-Stack Dev here. I specialize in the exact stack you listed. I recently built an AI-powered Romance Generator utilizing custom agents, RAG, and vector embeddings for complex memory. I can handle the entire production pipeline (frontend to deployment)."
My DM included: GitHub link, 2 specific AI projects, tool stack breakdown, rate of $45/hr, 6 years experience + Udemy credibility

Key winning formula: Lead with a specific past project that mirrors their need → mention the exact tools they listed → quantify credibility → soft CTA with rate
"""

QUALIFY_PROMPT = """You are a filter for a freelance full-stack and AI developer's lead-generation tool.

A post from X (Twitter) is shown below. Decide if it represents a genuine, active hiring signal — someone looking to hire, commission, or get help from a web developer, full-stack developer, or AI developer (freelance or contract).

Answer ONLY in this exact format:
VERDICT: YES or NO
REASON: one sentence explaining why

Post text:
{text}

Username: @{username}"""

REPLY_PROMPT = """You are writing outreach replies ON BEHALF of Km Habib, a real freelance developer. Write in first person as him. Sound like a real human — not a bot, not a template.

Here is Km Habib's full profile:
{profile}

The goal: write two replies that feel personal, reference something specific from the post, and mirror the winning formula from the example above.

Rules:
- ALWAYS reference a specific past project from his profile that is most relevant to this post
- ALWAYS mention the exact tools/stack the poster asked for (if stated)
- Sound confident but humble — not salesy
- Reply A (public comment): max 250 characters, one punchy sentence that shows he's done this exact thing before
- Reply B (DM): 3–4 sentences. Open by mirroring their specific need, name-drop the most relevant past project, list matching tools, state rate ($45/hr), end with a question or soft CTA. Include GitHub: https://github.com/kmhabib71

Post by @{username}:
{text}

Output ONLY in this exact format:
REPLY_A: [public comment]
REPLY_B: [DM text]"""


def _parse_qualify(response_text: str) -> tuple[bool, str]:
    """Parse YES/NO verdict and reason from Claude's qualification response."""
    verdict = False
    reason = "No reason provided"
    for line in response_text.strip().splitlines():
        if line.startswith("VERDICT:"):
            verdict = "YES" in line.upper()
        elif line.startswith("REASON:"):
            reason = line.replace("REASON:", "").strip()
    return verdict, reason


def _parse_replies(response_text: str) -> tuple[str, str]:
    """Parse Reply A and Reply B from Claude's reply generation response."""
    reply_a = ""
    reply_b_lines = []
    in_b = False

    for line in response_text.strip().splitlines():
        if line.startswith("REPLY_A:"):
            reply_a = line.replace("REPLY_A:", "").strip()
            in_b = False
        elif line.startswith("REPLY_B:"):
            reply_b_lines = [line.replace("REPLY_B:", "").strip()]
            in_b = True
        elif in_b and line.strip():
            reply_b_lines.append(line.strip())

    return reply_a, " ".join(reply_b_lines)


def process_post(post: dict) -> dict | None:
    """
    Run post through Claude:
    1. Qualify as genuine hiring lead
    2. If YES → generate two reply drafts

    Returns enriched post dict or None if not a lead.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    text = post["text"]
    username = post["username"]

    # Step 1: Qualify
    try:
        qualify_response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            system="You are a precise, concise hiring-intent classifier. Follow the output format exactly.",
            messages=[{
                "role": "user",
                "content": QUALIFY_PROMPT.format(text=text, username=username)
            }],
        )
        qualify_text = qualify_response.content[0].text
        is_lead, reason = _parse_qualify(qualify_text)
        logger.info(f"Post {post['id']} — verdict: {'YES' if is_lead else 'NO'} — {reason}")
    except Exception as e:
        logger.error(f"Claude qualify error for {post['id']}: {e}")
        return None

    if not is_lead:
        return None

    # Step 2: Generate replies
    try:
        reply_response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system="You are a professional outreach writer. Follow the output format exactly.",
            messages=[{
                "role": "user",
                "content": REPLY_PROMPT.format(
                    profile=DEVELOPER_PROFILE,
                    username=username,
                    text=text,
                )
            }],
        )
        reply_text = reply_response.content[0].text
        reply_a, reply_b = _parse_replies(reply_text)
    except Exception as e:
        logger.error(f"Claude reply generation error for {post['id']}: {e}")
        reply_a = ""
        reply_b = ""

    return {
        **post,
        "is_lead": True,
        "ai_reason": reason,
        "reply_a": reply_a,
        "reply_b": reply_b,
    }


def process_posts(posts: list[dict]) -> list[dict]:
    """Process a list of posts through Claude. Returns only confirmed leads."""
    leads = []
    for post in posts:
        result = process_post(post)
        if result:
            leads.append(result)
    logger.info(f"AI processing: {len(posts)} posts → {len(leads)} confirmed leads")
    return leads
