#!/usr/bin/env python3
"""
AI Ecosystem Media Monitor — Telegram Bot
Fetches AI/tech/fintech news from RSS feeds across global regions,
filters for relevance, and sends a formatted daily digest to your Telegram.

Deploy free on Railway.app. Runs once daily at your chosen local time.
"""

import os
import time
import logging
import datetime
import textwrap
from zoneinfo import ZoneInfo

import feedparser
import requests
import schedule
from dotenv import load_dotenv

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]   # from BotFather
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]    # your personal chat ID
SEND_TIME        = os.getenv("SEND_TIME", "07:00")   # HH:MM in TIMEZONE
TIMEZONE         = os.getenv("TIMEZONE", "Asia/Singapore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── AI/Tech/Fintech Filter Keywords ─────────────────────────────────────────
AI_KEYWORDS = [
    "artificial intelligence", " AI ", "machine learning", "deep learning",
    "large language model", "LLM", "GPT", "Claude", "Gemini", "generative AI",
    "agentic", "AI agent", "OpenAI", "Anthropic", "Google DeepMind", "NVIDIA",
    "fintech", "AI regulation", "AI safety", "sovereign AI", "AI model",
    "chatbot", "AI startup", "AI investment", "AI funding", "AI chip",
    "semiconductor", "AI governance", "AI policy", "AI deployment",
]

# ── RSS Feed Registry ────────────────────────────────────────────────────────
# Each entry: (region_label, feed_url, source_name)
FEEDS = [
    # ── Global / US ──
    ("🌐 Global",  "https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch"),
    ("🌐 Global",  "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml", "The Verge"),
    ("🌐 Global",  "https://www.wired.com/feed/tag/artificial-intelligence/rss", "Wired"),
    ("🇺🇸 US",     "https://feeds.a.dj.com/rss/RSSWSJD.xml", "WSJ (Tech)"),
    ("🇺🇸 US",     "https://fortune.com/section/technology/feed/", "Fortune"),
    ("🇺🇸 US",     "https://www.cnbc.com/id/19854910/device/rss/rss.html", "CNBC Tech"),
    ("🇺🇸 US",     "https://feeds.feedburner.com/Techcrunch", "TechCrunch"),
    ("🇺🇸 US",     "https://www.pymnts.com/artificial-intelligence-2/feed/", "PYMNTS AI"),
    ("🇺🇸 US",     "https://www.americanbanker.com/feed", "American Banker"),
    # ── Singapore / SE Asia ──
    ("🇸🇬 Singapore", "https://www.businesstimes.com.sg/rss/technology", "Business Times SG"),
    ("🇸🇬 Singapore", "https://www.channelnewsasia.com/rssfeeds/8395884", "CNA Tech"),
    ("🇸🇬 Singapore", "https://technode.global/feed/", "TechNode Global"),
    ("🇸🇬 Singapore", "https://www.techedt.com/feed", "Tech Edition"),
    # ── Hong Kong ──
    ("🇭🇰 Hong Kong", "https://www.scmp.com/rss/5/feed", "SCMP Tech"),
    ("🇭🇰 Hong Kong", "https://aiinasia.com/feed/", "AI in Asia"),
    ("🇭🇰 Hong Kong", "https://hongkongbusiness.hk/rss.xml", "HK Business"),
    # ── Japan ──
    ("🇯🇵 Japan", "https://www.japantimes.co.jp/feed/", "Japan Times"),
    ("🇯🇵 Japan", "https://asia.nikkei.com/rss/feed/nar", "Nikkei Asia"),
    ("🇯🇵 Japan", "https://www.nippon.com/en/feed/", "Nippon.com"),
    # ── Middle East ──
    ("🇦🇪 Middle East", "https://www.arabianbusiness.com/rss", "Arabian Business"),
    ("🇦🇪 Middle East", "https://www.thenationalnews.com/rss", "The National"),
    ("🇦🇪 Middle East", "https://www.khaleejtimes.com/feed", "Khaleej Times"),
    # ── Latin America ──
    ("🌎 LatAm", "https://mexicobusiness.news/rss.xml", "Mexico Business News"),
    ("🌎 LatAm", "https://www.bnamericas.com/en/rss/all", "BNamericas"),
    # ── Fintech / Regulation ──
    ("💳 Fintech", "https://fintech.global/feed/", "Fintech Global"),
    ("💳 Fintech", "https://www.thebanker.com/rss", "The Banker"),
    ("💳 Fintech", "https://www.financialregnews.com/feed/", "Financial Reg News"),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def is_ai_relevant(title: str, summary: str) -> bool:
    """Return True if the item mentions AI/tech/fintech topics."""
    text = (title + " " + summary).lower()
    return any(kw.lower() in text for kw in AI_KEYWORDS)


def fetch_region_stories(feeds: list, max_per_feed: int = 3) -> dict:
    """
    Fetch RSS feeds, filter for AI relevance, and group by region.
    Returns: {region: [(title, link, source, published), ...]}
    """
    results: dict = {}
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(hours=26)

    for region, url, source in feeds:
        try:
            log.info(f"Fetching {source} …")
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries:
                if count >= max_per_feed:
                    break
                title   = entry.get("title", "").strip()
                link    = entry.get("link", "")
                summary = entry.get("summary", "") or entry.get("description", "")

                # Date filter — last 26 hours
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if published:
                    pub_dt = datetime.datetime(*published[:6], tzinfo=datetime.timezone.utc)
                    if pub_dt < cutoff:
                        continue

                if is_ai_relevant(title, summary):
                    results.setdefault(region, []).append(
                        (title, link, source)
                    )
                    count += 1
        except Exception as e:
            log.warning(f"Failed to fetch {source}: {e}")

    return results


def truncate(text: str, limit: int = 90) -> str:
    return textwrap.shorten(text, width=limit, placeholder="…")


def build_messages(stories: dict) -> list[str]:
    """
    Build a list of Telegram HTML messages (≤4096 chars each).
    Splits by region into separate messages if needed.
    """
    today = datetime.datetime.now(tz=ZoneInfo(TIMEZONE)).strftime("%A, %-d %B %Y")
    messages = []

    # ── Header message ──
    total = sum(len(v) for v in stories.values())
    header = (
        f"📡 <b>AI Media Monitor</b>\n"
        f"<i>{today}</i>\n"
        f"{'─' * 30}\n"
        f"Found <b>{total} AI stories</b> across {len(stories)} regions in the last 24h.\n"
        f"Tap any headline to read the full article."
    )
    messages.append(header)

    # ── One message per region ──
    region_order = [
        "🌐 Global", "🇺🇸 US", "🇸🇬 Singapore", "🇭🇰 Hong Kong",
        "🇯🇵 Japan", "🇦🇪 Middle East", "🌎 LatAm", "💳 Fintech"
    ]
    for region in region_order:
        items = stories.get(region, [])
        if not items:
            continue

        lines = [f"<b>{region}</b>\n"]
        for title, link, source in items[:5]:
            short_title = truncate(title, 100)
            lines.append(f'• <a href="{link}">{short_title}</a>')
            lines.append(f'  <i>— {source}</i>')

        msg = "\n".join(lines)
        if len(msg) <= 4096:
            messages.append(msg)
        else:
            # Safety split if somehow too long
            messages.append(msg[:4090] + "…")

    # ── Footer ──
    messages.append(
        "─" * 30 + "\n"
        "💡 <i>Run in Writer Agent for the full interactive report with source links, "
        "cross-regional sentiment analysis, journalist tracker, and LinkedIn KOL monitor.</i>"
    )

    return messages


def send_telegram(messages: list[str]) -> None:
    """Send a list of messages to the configured Telegram chat."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for i, text in enumerate(messages):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=15)
            r.raise_for_status()
            log.info(f"Sent message {i+1}/{len(messages)} OK")
        except requests.RequestException as e:
            log.error(f"Failed to send message {i+1}: {e}")
        time.sleep(0.5)  # avoid Telegram flood limits


def run_daily_report() -> None:
    """Main function: fetch, filter, format, and send the daily report."""
    log.info("=== Starting daily AI media monitor run ===")
    stories = fetch_region_stories(FEEDS, max_per_feed=4)

    if not stories:
        send_telegram(["⚠️ <b>AI Monitor:</b> No AI stories found in the last 24h. Check feed connectivity."])
        return

    messages = build_messages(stories)
    send_telegram(messages)
    log.info(f"=== Done. Sent {len(messages)} messages. ===")


# ── Scheduler ────────────────────────────────────────────────────────────────

def poll_commands() -> None:
    """
    Long-poll Telegram for incoming messages.
    Responds to /report by sending an immediate digest.
    Runs in a background thread alongside the scheduler.
    """
    base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    offset = 0
    log.info("Command polling started — send /report in Telegram for an instant digest.")

    while True:
        try:
            r = requests.get(
                f"{base_url}/getUpdates",
                params={"timeout": 30, "offset": offset},
                timeout=40
            )
            r.raise_for_status()
            updates = r.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                text = message.get("text", "").strip().lower()
                chat_id = str(message.get("chat", {}).get("id", ""))

                if text.startswith("/report"):
                    log.info(f"Received /report from chat {chat_id} — sending digest now.")
                    send_telegram(["⏳ <b>Fetching your AI digest now...</b> Give me ~30 seconds."])
                    run_daily_report()
                elif text.startswith("/start"):
                    send_telegram([
                        "✅ <b>AI Monitor Bot is live!</b>\n"
                        f"Daily digest arrives at <b>{SEND_TIME} {TIMEZONE}</b> every morning.\n"
                        "Type /report anytime for an instant digest."
                    ])
        except Exception as e:
            log.warning(f"Polling error: {e}")
            time.sleep(5)


def main():
    import threading

    log.info(f"Bot started. Daily report scheduled at {SEND_TIME} ({TIMEZONE}).")

    # Send startup confirmation
    send_telegram([
        "✅ <b>AI Monitor Bot is live!</b>\n"
        f"Daily digest will arrive at <b>{SEND_TIME} {TIMEZONE}</b> every morning.\n"
        "Type /report anytime for an instant digest."
    ])

    # Convert SEND_TIME to UTC for the scheduler
    local_tz  = ZoneInfo(TIMEZONE)
    utc_tz    = ZoneInfo("UTC")
    h, m      = map(int, SEND_TIME.split(":"))
    local_dt  = datetime.datetime.now(local_tz).replace(hour=h, minute=m, second=0, microsecond=0)
    utc_dt    = local_dt.astimezone(utc_tz)
    utc_time  = utc_dt.strftime("%H:%M")
    log.info(f"Scheduling at {SEND_TIME} {TIMEZONE} = {utc_time} UTC")

    schedule.every().day.at(utc_time).do(run_daily_report)

    # Start command polling in a background thread
    t = threading.Thread(target=poll_commands, daemon=True)
    t.start()

    # Run the scheduler in the main thread
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    # Allow CLI override: `python ai_monitor_bot.py --now` to send immediately
    import sys
    if "--now" in sys.argv:
        run_daily_report()
    else:
        main()