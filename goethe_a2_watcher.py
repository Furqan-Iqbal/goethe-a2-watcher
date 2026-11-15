#!/usr/bin/env python3
"""
Goethe-Institut Pakistan, A2 exam slot watcher (Islamabad)

What it does
  - Opens the official A2 exam page every 2 minutes in a headless browser
  - Looks for exam dates in Islamabad and whether they can be booked
  - The moment a bookable Islamabad date appears (or the Islamabad list changes):
      * sends an email (Gmail), optional WhatsApp / Telegram
      * plays an alarm sound
      * opens the booking page in your normal browser so you can book at once
      * saves a screenshot of what it saw

It does NOT book or pay by itself. You book manually (one booking per brother),
with the data sheet open next to you.

Setup (once):
    pip install playwright requests
    python -m playwright install chromium

Run:
    python goethe_a2_watcher.py              # check every 2 minutes
    python goethe_a2_watcher.py --once       # single check (good for testing)
    python goethe_a2_watcher.py --show       # show the browser window while checking
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    sys.exit("Playwright missing. Run:  pip install playwright requests  and  python -m playwright install chromium")

# ---------------------------------------------------------------- settings
EXAM_URL = os.environ.get("EXAM_URL", "https://www.goethe.de/ins/pk/en/spr/prf/gzsd2.cfm")
CITY = "Islamabad"

CHECK_EVERY_SECONDS = 120          # base interval (2 minutes), a random 0 to 20 s is added
HEARTBEAT_HOURS = 6                # "still running" WhatsApp every 6 hours, so you know it is alive

# WhatsApp alerts via CallMeBot (free). See README for the 1 minute setup.
WHATSAPP_PHONE = os.environ.get("WA_PHONE") or ""   # your WhatsApp number, set as env var / GitHub secret
WHATSAPP_APIKEY = os.environ.get("WA_APIKEY", "")

# Email alerts via Gmail (needs a Gmail "app password", see GITHUB_SETUP.txt)
MAIL_USER = os.environ.get("MAIL_USER") or ""     # the Gmail address that sends
MAIL_PASS = os.environ.get("MAIL_PASS") or ""     # 16-letter app password, NOT the normal password
MAIL_TO = os.environ.get("MAIL_TO") or MAIL_USER  # where alerts go

# Telegram (optional, second channel). Create a bot with @BotFather, send it one message,
# then get your chat id from https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN = os.environ.get("TG_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TG_CHAT", "")

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "watcher_state.json"
SHOT_DIR = HERE / "screenshots"

# words that mean "you can book" / "you cannot book" (English and German page versions)
BOOK_WORDS = re.compile(r"\b(book|select|choose|register|continue|buchen|auswählen|weiter|anmelden)\b", re.I)
FULL_WORDS = re.compile(
    r"(fully booked|booked out|sold out|no (free )?places|no seats|waiting list|not available|"
    r"registration (is )?closed|ausgebucht|warteliste|keine plätze|nicht verfügbar)", re.I)
MORE_WORDS = re.compile(r"^(show more|load more|more dates|mehr anzeigen|weitere termine)$", re.I)
# a real exam entry always has a date; this keeps the Islamabad *address* block
# (which is always on the page) from being counted as an exam date
DATE_RE = re.compile(
    r"(\b\d{1,2}[./]\d{1,2}[./]\d{2,4}(?!\d)|\b\d{1,2}\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}(?!\d)|"
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}(?!\d))", re.I)
NO_DATES_TEXT = "no examination dates are currently available"
ERROR_TEXTS = ("dates cannot be displayed temporarily", "internal server error")

# --------------------------------------------------------------- helpers
def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


PROBLEMS = []   # anything here makes a GitHub run fail (red), and GitHub then emails you


def whatsapp(text):
    if not (WHATSAPP_APIKEY and WHATSAPP_PHONE):
        return
    try:
        import requests
        r = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": WHATSAPP_PHONE, "text": text[:900], "apikey": WHATSAPP_APIKEY},
            timeout=30,
        )
        body = r.text.lower()
        if r.status_code != 200 or "invalid" in body or "error" in body:
            PROBLEMS.append(f"WhatsApp failed: HTTP {r.status_code} {r.text[:200]}")
            log(PROBLEMS[-1])
        else:
            log("WhatsApp sent")
    except Exception as e:
        PROBLEMS.append(f"WhatsApp failed: {e}")
        log(PROBLEMS[-1])


def email(text):
    if not (MAIL_USER and MAIL_PASS):
        return
    try:
        import smtplib
        from email.message import EmailMessage
        m = EmailMessage()
        m["Subject"] = text.split("\n")[0][:120]
        m["From"] = MAIL_USER
        m["To"] = MAIL_TO
        m.set_content(text)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(MAIL_USER, MAIL_PASS)
            smtp.send_message(m)
        log(f"Email sent to {MAIL_TO}")
    except Exception as e:
        PROBLEMS.append(f"Email failed: {e}")
        log(PROBLEMS[-1])


def notify(text):
    if not ((MAIL_USER and MAIL_PASS) or WHATSAPP_APIKEY or TELEGRAM_BOT_TOKEN):
        PROBLEMS.append("No alert channel set (MAIL_USER + MAIL_PASS missing), nobody can be notified")
        log(PROBLEMS[-1])
        return
    email(text)
    whatsapp(text)
    telegram(text)


def telegram(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
    except Exception as e:
        log(f"Telegram failed: {e}")


def alarm():
    try:
        if sys.platform.startswith("win"):
            import winsound
            for _ in range(6):
                winsound.Beep(1500, 400)
                time.sleep(0.15)
        elif sys.platform == "darwin":
            for _ in range(4):
                os.system("afplay /System/Library/Sounds/Glass.aiff")
        else:
            for _ in range(6):
                print("\a", end="", flush=True)
                time.sleep(0.3)
    except Exception:
        pass


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"hash": None, "alerted_bookable": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# JavaScript that runs inside the page: finds the smallest blocks that mention the city
# and reports their text plus whether they hold an active booking link/button.
EXTRACT_JS = r"""
(city) => {
  const els = Array.from(document.querySelectorAll('li, article, tr, td, div, section, span, p'));
  const hits = els.filter(e => {
    const t = (e.innerText || '');
    return t.toLowerCase().includes(city.toLowerCase()) && t.length < 1500;
  });
  // keep only the innermost matches (drop any element that contains another match)
  const inner = hits.filter(e => !hits.some(o => o !== e && e.contains(o)));
  return inner.map(e => {
    const btns = Array.from(e.querySelectorAll('a, button, input[type=submit]'))
      .filter(b => !b.disabled && b.getAttribute('aria-disabled') !== 'true')
      .map(b => ({text: (b.innerText || b.value || '').trim(), href: b.href || ''}));
    // the date card is often the parent of the location line, so look one level up too
    let card = e.closest('li, article, tr');
    if (!card || (card.innerText || '').length > 1500) {
      card = e;
      const hasDate = el => /\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}/i.test(el.innerText || '');
      // climb until the block holds a date (= one exam card), but never into a big list
      for (let i = 0; i < 4 && !hasDate(card) && card.parentElement && card.parentElement !== document.body; i++) {
        if ((card.parentElement.innerText || '').length > 700) break;
        card = card.parentElement;
      }
    }
    const cardBtns = Array.from(card.querySelectorAll('a, button, input[type=submit]'))
      .filter(b => !b.disabled && b.getAttribute('aria-disabled') !== 'true')
      .map(b => ({text: (b.innerText || b.value || '').trim(), href: b.href || ''}));
    return {text: (card.innerText || e.innerText).trim().replace(/\s+/g, ' '), buttons: btns.concat(cardBtns)};
  });
}
"""


def classify(entries):
    """Return (all_city_entries, bookable_entries)."""
    seen, out, bookable = set(), [], []
    for en in entries:
        txt = en["text"]
        if txt in seen:
            continue
        seen.add(txt)
        if not DATE_RE.search(txt):
            continue          # address / info block, not an exam date
        out.append(txt)
        if FULL_WORDS.search(txt):
            continue
        btn = next((b for b in en["buttons"] if BOOK_WORDS.search(b["text"] or "")), None)
        if btn:
            bookable.append({"text": txt, "link": btn["href"] or EXAM_URL})
    return out, bookable


def check(page):
    page.goto(EXAM_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except PWTimeout:
        pass

    # accept cookie banner if shown (otherwise it can hide the list)
    for label in ["Accept all", "Accept", "Alle akzeptieren", "Agree", "OK"]:
        try:
            page.get_by_role("button", name=label, exact=False).first.click(timeout=1500)
            break
        except Exception:
            continue

    # the exam dates load by JavaScript, give them time and open "show more" if present
    page.wait_for_timeout(4000)
    for _ in range(5):
        more = page.get_by_role("button", name=MORE_WORDS)
        if more.count() == 0:
            break
        try:
            more.first.click(timeout=3000)
            page.wait_for_timeout(2500)
        except Exception:
            break

    body = (page.inner_text("body") or "").lower()   # visible text only
    entries = page.evaluate(EXTRACT_JS, CITY)
    city_entries, bookable = classify(entries)
    if not city_entries:
        if any(t in body for t in ERROR_TEXTS):
            raise RuntimeError("Goethe page says dates cannot be displayed right now (server error)")
        if NO_DATES_TEXT in body:
            log("Page says: no examination dates currently available")
    return city_entries, bookable


def run(show=False, once=False, for_minutes=0):
    SHOT_DIR.mkdir(exist_ok=True)
    until = time.time() + for_minutes * 60 if for_minutes else None
    state = load_state()
    log(f"Watching {EXAM_URL} for {CITY}. Stop with Ctrl+C.")
    if WHATSAPP_APIKEY:
        log(f"WhatsApp alerts go to {WHATSAPP_PHONE}")
    else:
        log("WA_APIKEY not set, no WhatsApp alerts (see README step 2).")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not show)
        ctx = browser.new_context(
            locale="en-US",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        )
        page = ctx.new_page()
        fails = 0
        while True:
            try:
                city_entries, bookable = check(page)
                fails = 0
                h = hashlib.sha256("\n".join(city_entries).encode()).hexdigest()
                state["checks"] = state.get("checks", 0) + 1
                log(f"{len(city_entries)} {CITY} entries, {len(bookable)} bookable")
                status = (f"{len(city_entries)} {CITY} date(s), {len(bookable)} bookable"
                          if city_entries else "no Islamabad dates published yet")
                if not state.get("last_beat"):
                    notify(f"Goethe watcher STARTED. Checking every few minutes. Right now: {status}. "
                           "You only get a message when something changes.")
                    state["last_beat"] = time.time()
                elif time.time() - state["last_beat"] > HEARTBEAT_HOURS * 3600:
                    notify(f"Goethe watcher still running ({state['checks']} checks so far). Right now: {status}.")
                    state["last_beat"] = time.time()

                new_bookable = [b for b in bookable if b["text"] not in state["alerted_bookable"]]
                changed = state["hash"] is not None and h != state["hash"]

                if new_bookable or changed:
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    shot = SHOT_DIR / f"{stamp}.png"
                    page.screenshot(path=str(shot), full_page=True)

                    if new_bookable:
                        lines = "\n\n".join(b["text"][:300] for b in new_bookable)
                        msg = (f"GOETHE A2 {CITY.upper()}: BOOKING OPEN!\n\n{lines}\n\n"
                               f"Book now: {new_bookable[0]['link']}\n"
                               "Book Azlan and Faizan separately.")
                        log(msg)
                        notify(msg)
                        if not os.environ.get("CI"):
                            webbrowser.open(new_bookable[0]["link"])
                            alarm()
                        state["alerted_bookable"] += [b["text"] for b in new_bookable]
                    else:
                        msg = (f"Goethe A2 {CITY}: the date list changed (not bookable yet). "
                               f"Check: {EXAM_URL}")
                        log(msg)
                        notify(msg)

                    log(f"Screenshot saved: {shot}")

                state["hash"] = h
                state["fails"] = 0
                save_state(state)

            except Exception as e:
                fails += 1
                log(f"Check failed ({fails}): {e}")
                state["fails"] = state.get("fails", 0) + 1
                save_state(state)
                if state["fails"] >= 5:
                    PROBLEMS.append(f"Goethe page check failed {state['fails']} times in a row: {e}")
                if state["fails"] == 5:
                    notify("Goethe watcher: 5 failed checks in a row. Site may be down or changed. Check manually.")

            if once:
                break
            wait = CHECK_EVERY_SECONDS + random.randint(0, 20)
            if fails:
                wait = min(wait * (1 + fails), 900)   # back off when the site struggles
            if until and time.time() + wait > until:
                break
            time.sleep(wait)

        browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="check one time and exit")
    ap.add_argument("--show", action="store_true", help="show the browser window")
    ap.add_argument("--for-minutes", type=int, default=0, help="keep checking for N minutes, then exit (GitHub Actions)")
    ap.add_argument("--test-alert", action="store_true", help="only test sound + Telegram")
    a = ap.parse_args()
    if a.test_alert:
        notify("Goethe watcher test message. Alerts work.")
        alarm()
        log("Test alert done.")
    else:
        try:
            run(show=a.show, once=a.once, for_minutes=a.for_minutes)
        except KeyboardInterrupt:
            log("Stopped.")
    if PROBLEMS:
        log("PROBLEMS: " + " | ".join(dict.fromkeys(PROBLEMS)))
        sys.exit(1)
