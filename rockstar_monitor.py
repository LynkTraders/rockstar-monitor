#!/usr/bin/env python3
"""
Rockstar Monitor — WhatsApp-alerts bij officiele Rockstar-aankondigingen.

Bronnen (alleen Rockstar/Take-Two zelf, geen gamingpers):
  1. Rockstar Newswire  — de officiele nieuwsbron, met tags per game
  2. Rockstar YouTube   — trailers en video's
  3. Take-Two IR        — persberichten (releasedata, uitstel, cijfers)
  4. X / @RockstarGames — optioneel: ping zodra de tweetteller oploopt

Draait eenmalig per aanroep. State staat in monitor_state.json.
"""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import feedparser
import requests

# ── Config via environment ────────────────────────────────────────────
WHATSAPP_PHONE = os.environ.get("WHATSAPP_PHONE", "").strip()
WHATSAPP_APIKEY = os.environ.get("WHATSAPP_APIKEY", "").strip()

# "true" = alleen posts met een Grand Theft Auto VI-tag.
# "false" = alles wat Rockstar officieel naar buiten brengt.
ONLY_GTA6 = os.environ.get("ONLY_GTA6", "false").lower() == "true"

# X-account in de gaten houden (alleen een "er is iets gepost"-ping,
# de inhoud van tweets is niet gratis op te halen).
WATCH_X = os.environ.get("WATCH_X", "true").lower() == "true"

# Droogloop: wel detecteren en loggen, niets versturen.
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

# Draait de monitor elke minuut, dan hoeven de trage bronnen niet elke keer
# mee. Take-Two publiceert hooguit wekelijks, het YouTube-kanaal ook. Alleen
# de Newswire wordt elke run bevraagd; die is de snelste officiele bron.
# 1 = elke run alles (zo staat het op GitHub, dat maar paar keer per dag draait).
SLOW_EVERY = max(1, int(os.environ.get("SLOW_EVERY", "1")))
X_EVERY = max(1, int(os.environ.get("X_EVERY", "1")))

STATE_FILE = os.environ.get("STATE_FILE", "monitor_state.json")
# Het runnummer hoort niet in de gedeelde state: dat verandert elke run en
# zou dus elke minuut een commit naar de repo opleveren. Bovendien is het
# per machine verschillend -- de Mac draait vaker dan GitHub.
RUN_FILE = os.environ.get("RUN_FILE", ".run_no")
MAX_ALERTS_PER_RUN = 8  # noodrem tegen een stortvloed

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ── Bronnen ───────────────────────────────────────────────────────────
NEWSWIRE_GRAPH = "https://graph.rockstargames.com/"
NEWSWIRE_HASH = "7ec00215aecc70de257b0719a1dfcfa84fe57fdc7bf5c10ec2e8f377defede58"
NEWSWIRE_WEB = "https://www.rockstargames.com"

YOUTUBE_FEED = (
    "https://www.youtube.com/feeds/videos.xml"
    "?channel_id=UC6VcWc1rAoWdBCM0JxrRQ3A"  # Rockstar Games
)
TAKETWO_FEED = "https://ir.take2games.com/rss/news-releases.xml"
X_PROFILE_API = "https://api.fxtwitter.com/rockstargames"
X_URL = "https://x.com/RockstarGames"

GTA6_MARKERS = (
    "grand theft auto vi",
    "grand theft auto 6",
    "gta vi",
    "gta 6",
)
# Take-Two publiceert ook NBA 2K, Zynga, WWE enz. — alleen Rockstar doorlaten.
ROCKSTAR_MARKERS = GTA6_MARKERS + (
    "rockstar",
    "grand theft auto",
    "red dead",
)


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}Z] {msg}", flush=True)


# ── State ─────────────────────────────────────────────────────────────
def next_run_no():
    try:
        with open(RUN_FILE) as f:
            n = int(f.read().strip() or 0)
    except (OSError, ValueError):
        n = 0
    n += 1
    try:
        with open(RUN_FILE, "w") as f:
            f.write(str(n))
    except OSError as e:
        log(f"Runteller niet op te slaan: {e}")
    return n


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log(f"State onleesbaar ({e}) — begin opnieuw")
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


# ── WhatsApp ──────────────────────────────────────────────────────────
def send_whatsapp(message):
    if DRY_RUN:
        log(f"[DRY RUN] zou versturen:\n{message}\n")
        return True
    if not WHATSAPP_PHONE or not WHATSAPP_APIKEY:
        log("FOUT: WHATSAPP_PHONE of WHATSAPP_APIKEY ontbreekt")
        return False
    try:
        r = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={
                "phone": WHATSAPP_PHONE,
                "text": message,
                "apikey": WHATSAPP_APIKEY,
            },
            timeout=20,
        )
        ok = r.status_code == 200
        log(f"WhatsApp {'verstuurd' if ok else 'MISLUKT'} (HTTP {r.status_code})")
        return ok
    except requests.RequestException as e:
        # Niet de exceptie zelf loggen: requests zet de volledige URL in de
        # tekst, inclusief de apikey-parameter. Actions-logs zijn openbaar.
        log(f"WhatsApp fout: {type(e).__name__}")
        return False


# ── Bron 1: Newswire ──────────────────────────────────────────────────
def fetch_newswire(limit=20):
    variables = {
        "tagIdHash": None,
        "page": 1,
        "metaUrl": "/newswire",
        "limit": limit,
        "locale": "en_us",
    }
    extensions = {
        "persistedQuery": {"version": 1, "sha256Hash": NEWSWIRE_HASH}
    }
    r = requests.get(
        NEWSWIRE_GRAPH,
        params={
            "origin": NEWSWIRE_WEB,
            "operationName": "NewswireList",
            "variables": json.dumps(variables, separators=(",", ":")),
            "extensions": json.dumps(extensions, separators=(",", ":")),
        },
        headers={
            "Accept": "application/json",
            "Origin": NEWSWIRE_WEB,
            "Referer": f"{NEWSWIRE_WEB}/newswire",
            "User-Agent": UA,
        },
        timeout=25,
    )
    r.raise_for_status()
    results = (r.json().get("data") or {}).get("posts", {}).get("results") or []

    items = []
    for post in results:
        tags = []
        for key in ("primary_tags", "secondary_tags"):
            for tag in post.get(key) or []:
                name = (tag or {}).get("name")
                if name:
                    tags.append(name)
        url = post.get("url") or ""
        items.append(
            {
                "uid": f"newswire:{post.get('id')}",
                "source": "Rockstar Newswire",
                "title": post.get("title") or "(geen titel)",
                "link": NEWSWIRE_WEB + url if url.startswith("/") else url,
                "date": post.get("created_formatted") or "",
                "tags": tags,
                "haystack": " ".join([post.get("title") or ""] + tags).lower(),
            }
        )
    return items


# ── Bronnen 2 & 3: RSS ────────────────────────────────────────────────
def fetch_rss(source, url, prefix, attempts=2):
    # YouTube levert af en toe afgekapte XML ("not well-formed"). Een
    # tweede poging een paar seconden later is bijna altijd genoeg.
    feed = None
    for attempt in range(1, attempts + 1):
        feed = feedparser.parse(url, agent=UA)
        if feed.entries:
            break
        if attempt < attempts:
            log(f"  {source}: lege/kapotte feed, nieuwe poging")
            time.sleep(3)
    if getattr(feed, "bozo", 0) and not feed.entries:
        raise RuntimeError(getattr(feed, "bozo_exception", "feed onleesbaar"))

    items = []
    for entry in feed.entries[:25]:
        raw_id = entry.get("id") or entry.get("link") or entry.get("title", "")
        uid = f"{prefix}:{hashlib.sha1(raw_id.encode()).hexdigest()[:16]}"
        title = entry.get("title") or "(geen titel)"
        summary = entry.get("summary") or ""
        items.append(
            {
                "uid": uid,
                "source": source,
                "title": title,
                "link": entry.get("link") or "",
                "date": entry.get("published", "")[:16],
                "tags": [],
                "haystack": f"{title} {summary}".lower(),
            }
        )
    return items


# ── Bron 4: X-teller ──────────────────────────────────────────────────
def check_x(state, alerts):
    try:
        r = requests.get(X_PROFILE_API, headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        count = (r.json().get("user") or {}).get("tweets")
        if not isinstance(count, int):
            log("X: geen tweetteller in respons")
            return
    except (requests.RequestException, ValueError) as e:
        log(f"X fout: {e}")
        return

    previous = state.get("x_tweet_count")
    state["x_tweet_count"] = count

    if previous is None:
        log(f"X: teller vastgelegd op {count} (geen alert bij eerste run)")
        return
    if count <= previous:
        log(f"X: geen nieuwe posts ({count})")
        return

    new = count - previous
    log(f"X: {new} nieuwe post(s) — teller {previous} -> {count}")
    alerts.append(
        {
            "prev_count": previous,
            "priority": "x",
            "source": "X / @RockstarGames",
            "title": f"{new} nieuwe post{'s' if new > 1 else ''} op X",
            "link": X_URL,
            "date": "",
        }
    )


# ── Filteren ──────────────────────────────────────────────────────────
def is_gta6(item):
    return any(m in item["haystack"] for m in GTA6_MARKERS)


def title_key(title):
    """Normaliseer een titel zodat regio-varianten en cross-post duplicaten
    van dezelfde aankondiging als een en hetzelfde item tellen."""
    t = re.sub(r"[^a-z0-9]+", " ", title.lower())
    return " ".join(t.split())


def collect(state):
    seen = set(state.get("seen_ids", []))
    alerted_titles = list(state.get("alerted_titles", []))
    alerted_set = set(alerted_titles)
    # Pas "ingericht" als elke bron minstens een keer goed is opgehaald.
    # Faalt er een bron tijdens de eerste run, dan blijft die vlag uit en
    # wordt er de volgende run opnieuw stil ingelezen in plaats van dat
    # de hele achterstand alsnog als nieuws binnenkomt.
    first_run = not state.get("bootstrapped")
    failed = []
    alerts = []

    run_no = next_run_no()
    slow_turn = first_run or run_no % SLOW_EVERY == 0

    sources = [("Newswire", lambda: fetch_newswire())]
    if slow_turn:
        sources += [
            ("YouTube", lambda: fetch_rss("Rockstar YouTube", YOUTUBE_FEED, "yt")),
            ("Take-Two IR", lambda: fetch_rss("Take-Two IR", TAKETWO_FEED, "ttwo")),
        ]
    else:
        log(f"run {run_no}: alleen Newswire (trage bronnen elke {SLOW_EVERY} runs)")

    for name, fetcher in sources:
        try:
            items = fetcher()
        except Exception as e:
            log(f"Bron '{name}' mislukt: {e}")
            failed.append(name)
            continue

        log(f"Bron '{name}': {len(items)} items opgehaald")
        for item in items:
            if item["uid"] in seen:
                continue
            seen.add(item["uid"])

            # Take-Two publiceert veel niet-Rockstar nieuws.
            if item["source"] == "Take-Two IR" and not any(
                m in item["haystack"] for m in ROCKSTAR_MARKERS
            ):
                continue

            gta6 = is_gta6(item)
            if ONLY_GTA6 and not gta6:
                continue

            # Een trailer staat vaak in Newswire en (soms meermaals) op
            # YouTube. Een aankondiging is een appje waard, geen zes.
            key = title_key(item["title"])
            if key in alerted_set:
                log(f"  dubbel, overgeslagen: {item['title'][:60]}")
                continue
            alerted_set.add(key)
            alerted_titles.append(key)

            alerts.append(
                {
                    "uid": item["uid"],
                    "key": key,
                    "priority": "gta6" if gta6 else "rockstar",
                    "source": item["source"],
                    "title": item["title"],
                    "link": item["link"],
                    "date": item["date"],
                    "tags": item["tags"],
                }
            )
            log(f"  NIEUW [{'GTA VI' if gta6 else 'Rockstar'}] {item['title'][:70]}")

    state["seen_ids"] = sorted(seen)[-3000:]
    state["alerted_titles"] = alerted_titles[-500:]

    if WATCH_X and (first_run or run_no % X_EVERY == 0):
        check_x(state, alerts)

    if first_run:
        if failed:
            log(f"Eerste run: bron(nen) {', '.join(failed)} mislukt — "
                f"volgende run leest opnieuw stil in")
        else:
            state["bootstrapped"] = True
        log(f"Eerste run: {len(alerts)} item(s) als 'gezien' gemarkeerd, niets verstuurd")
        return []

    # Nieuwste bovenaan, GTA VI eerst.
    order = {"gta6": 0, "x": 1, "rockstar": 2}
    alerts.sort(key=lambda a: order.get(a["priority"], 9))
    return alerts


def requeue(state, alert):
    """Zet een alert die niet verstuurd kon worden terug in de wachtrij.

    Zonder dit zou een item als 'gemeld' blijven staan terwijl het appje
    nooit aankwam — en dan hoor je er nooit meer iets over. Precies het
    soort stille storing waar je pas achter komt als je iets gemist hebt.
    """
    uid = alert.get("uid")
    if uid and uid in state.get("seen_ids", []):
        state["seen_ids"].remove(uid)

    key = alert.get("key")
    if key and key in state.get("alerted_titles", []):
        state["alerted_titles"].remove(key)

    if alert.get("priority") == "x" and alert.get("prev_count") is not None:
        state["x_tweet_count"] = alert["prev_count"]


def format_alert(alert):
    if alert["priority"] == "gta6":
        head = "GTA VI — OFFICIEEL VAN ROCKSTAR"
    elif alert["priority"] == "x":
        head = "ROCKSTAR OP X"
    else:
        head = "ROCKSTAR NIEUWS"

    lines = [head, "", alert["title"]]
    if alert.get("tags"):
        lines.append("Tags: " + ", ".join(alert["tags"]))
    meta = " · ".join(p for p in (alert["source"], alert.get("date")) if p)
    if meta:
        lines.append(meta)
    if alert["link"]:
        lines += ["", alert["link"]]
    return "\n".join(lines)


def send_test():
    """Stuurt een testappje, zodat je kunt controleren of de ketting klopt.

    Zonder dit is 'geen appje' niet te onderscheiden van 'stuk': als Rockstar
    niets publiceert hoort de monitor stil te zijn, en dat ziet er precies
    hetzelfde uit als een verkeerde apikey.
    """
    log("=== Testbericht ===")
    now = datetime.now().strftime("%d-%m-%Y %H:%M")
    ok = send_whatsapp(
        "ROCKSTAR MONITOR — TEST\n\n"
        "Als je dit leest werkt de verbinding met CallMeBot.\n"
        f"Verstuurd op {now}.\n\n"
        "Dit is geen nieuws van Rockstar — die krijg je alleen als er "
        "echt iets aangekondigd wordt."
    )
    if ok:
        log("Testbericht verstuurd — check je WhatsApp")
        return 0
    log("Testbericht MISLUKT — controleer WHATSAPP_PHONE en WHATSAPP_APIKEY")
    return 1


def main():
    if "--test" in sys.argv or os.environ.get("TEST", "").lower() == "true":
        return send_test()

    log("=== Rockstar Monitor ===")
    log(f"filter={'alleen GTA VI' if ONLY_GTA6 else 'alles van Rockstar'} "
        f"x={'aan' if WATCH_X else 'uit'} dry_run={DRY_RUN}")

    state = load_state()
    alerts = collect(state)

    if len(alerts) > MAX_ALERTS_PER_RUN:
        log(f"{len(alerts)} alerts — afgekapt op {MAX_ALERTS_PER_RUN}")
        alerts = alerts[:MAX_ALERTS_PER_RUN]

    sent = 0
    failed = 0
    for i, alert in enumerate(alerts):
        if send_whatsapp(format_alert(alert)):
            sent += 1
        else:
            failed += 1
            requeue(state, alert)
            log(f"  terug in de wachtrij: {alert['title'][:60]}")
        if i < len(alerts) - 1:
            time.sleep(6)  # CallMeBot wil rust tussen berichten

    save_state(state)
    if failed:
        log(f"=== Klaar — {sent} verstuurd, {failed} MISLUKT "
            f"(volgende run opnieuw geprobeerd) ===")
        return 1
    log(f"=== Klaar — {sent} alert(s) verstuurd ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
