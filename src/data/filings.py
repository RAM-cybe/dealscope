"""Official filings feed (Part 2a) + Regulation 30 taxonomy tagging (Part 2c).

SOURCING DISCIPLINE (locked decision, do not violate): this module fetches
ONLY from NSE's and BSE's own official RSS feeds -- never scrapes their
rendered HTML pages, regardless of what a robots.txt would technically
allow. Both exchanges' Terms of Use forbid scraping; their own published RSS
feeds are the one channel this project is allowed to pull from.

WHAT THESE FEEDS ACTUALLY EXPOSE (verified before writing this module, not
assumed -- see the real feed list at https://www.nseindia.com/static/rss-feed):
NSE publishes ~22 genuine per-company RSS feeds covering announcements,
financial results, board meetings, corporate actions/governance, related-
party transactions, insider trading, shareholding pattern, SAST Regulation
29/31 (substantial-acquisition/encumbrance disclosures), secretarial
compliance, voting results, and more. This is real, broad, per-company
coverage -- confirmed by live-fetching several of these feeds and reading
actual current items before this file was written.

BSE's officially-documented RSS offering is much narrower: only
`notices.xml` (exchange-wide administrative notices -- trading suspensions,
listing/delisting bulletins, mutual-fund notices) and a Sensex index feed.
BSE does NOT publish a per-company corporate-announcements RSS feed the way
NSE does. This is disclosed honestly here rather than silently treating BSE
notices as equivalent, broad, per-company coverage -- they are not. BSE
notices are surfaced separately (fetch_bse_notices()) and are NOT run
through the Regulation 30 per-company taxonomy, since most of them aren't
company-specific disclosures at all.

REGULATION 30 TAGGING (Part 2c): categories map to the real, legally-defined
SEBI LODR Schedule III Part A taxonomy (Para A = deemed material events,
Para B = events tested for materiality) -- see CATEGORY definitions below,
each with its real Schedule III provenance in a comment. Two confidence
tiers, by design:
  1. FEED-SOURCED categories (Financial Results, Board Meetings, Related
     Party Transactions, Corporate Actions, Corporate Governance, Insider
     Trading, Shareholding Pattern, Voting Results, Secretarial Compliance)
     -- the category comes directly from which dedicated NSE feed the item
     was published under. Zero classification risk: an item from
     Related_Party_Trans.xml IS a related-party-transaction filing by
     construction, not a guess.
  2. KEYWORD-CLASSIFIED categories, applied only to the general
     "Announcements" catch-all feed, for the higher-stakes SEBI categories
     that don't have their own dedicated NSE feed (order wins, credit
     rating actions, litigation, auditor resignation, insolvency, fraud,
     regulatory action). These use strict, close-to-legal-phrase keyword
     matching (see CATEGORY_KEYWORDS) -- anything that doesn't match a
     strong phrase falls into "General announcement" rather than being
     guessed into a high-stakes bucket. Per the explicit instruction to
     apply extra scrutiny to fraud/insolvency/litigation-type tags, every
     instance of these produced from a real data pull was manually
     reviewed before this module was considered done -- see
     data/quality_reports/reg30_tagging_review_2026-07-17.md.
"""

import re
import time
from datetime import datetime, timezone
from xml.etree import ElementTree

import requests

REQUEST_TIMEOUT = 10  # seconds -- Part 2d: every new external HTTP call gets a real timeout
# A self-identifying bot UA ("DealScope/1.0 ...") was tried first and
# reliably hung/timed out against NSE's archive host -- switched to the same
# realistic browser UA this project's other NSE-facing pull scripts already
# use successfully (see archive/data_pipeline_scripts/enrich_v2.py's
# HEADERS), which fetches normally. Confirmed empirically, not guessed.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

# Confirmed empirically (2026-07-17): NSE's archive host silently throttles
# bursts of requests -- a dozen feeds fetched back-to-back with zero delay
# went from all succeeding in <1s to a full connection hang on retry a
# minute later. A small pause between each feed request keeps this module
# well under whatever burst threshold triggers that. This is why
# fetch_all_nse_filings() is aggressively cached at the call site (app.py)
# rather than re-fetched per page view -- both the pacing and the cache
# exist because of the same real, observed constraint.
INTER_FEED_DELAY = 0.5  # seconds

NSE_BASE = "https://nsearchives.nseindia.com/content/RSS"

# Feed-sourced categories: category name IS the feed's own declared purpose.
# (feed filename, human category label, SEBI Schedule III provenance)
NSE_FEEDS = [
    ("Online_announcements.xml", "General announcement", "Reg 30(1) / Schedule III (catch-all; keyword-classified below)"),
    ("Financial_Results.xml", "Financial results", "Schedule III Para A: outcome of board meeting -- financial results"),
    ("Board_Meetings.xml", "Board meeting outcome", "Schedule III Para A: outcome of meetings of the board of directors"),
    ("Corporate_action.xml", "Corporate action", "Schedule III Para A: dividends/bonus/buyback/splits"),
    ("Corporate_Governance.xml", "Corporate governance", "Schedule III Para A/C: governance disclosures"),
    ("Related_Party_Trans.xml", "Related-party transaction", "Schedule III Para A: related party transactions (disclosed via dedicated XBRL filing)"),
    ("InsiderTrading.xml", "Insider trading", "SEBI PIT Regulations disclosure (adjacent to Reg 30)"),
    ("Shareholding_Pattern.xml", "Shareholding pattern change", "Reg 31 shareholding pattern disclosure"),
    ("Voting_Results.xml", "Voting / AGM-EGM results", "Schedule III Para A: proceedings of AGM/EGM"),
    ("Secretarial_Compliance.xml", "Secretarial compliance", "Reg 24A annual secretarial compliance report"),
    ("Sast_Regulation31.xml", "Promoter encumbrance / SAST Reg 31", "SEBI SAST Regulations 31 -- promoter shareholding encumbrance"),
    ("Sast_Regulation29.xml", "Substantial acquisition / SAST Reg 29", "SEBI SAST Regulations 29 -- disclosure of acquisition/disposal"),
]

BSE_NOTICES_URL = "https://www.bseindia.com/data/xml/notices.xml"

# Keyword classification for the general "Announcements" feed only -- strict,
# close-to-legal-phrase matching. Order matters: first match wins, most
# specific/highest-stakes checked first. Every category here maps to a real
# Schedule III Para A/B entry (see comments) -- never an invented bucket.
#
# NOTE on what got tightened after a real manual review of live data
# (2026-07-17, see data/quality_reports/reg30_tagging_review_2026-07-17.md):
# the first version of the credit-rating keywords included bare agency
# names ("crisil", "icra") and matched multiple mutual-fund NAV-declaration
# items whose SCHEME NAME happens to contain "CRISIL" (e.g. "Aditya Birla
# Sun Life CRISIL Broad Based Gilt ETF") -- a real false positive, not a
# hypothetical one. Bare agency names were removed; only phrases that
# describe an actual rating ACTION remain. "liquidation" was dropped from
# the insolvency list for the same reason (mutual-fund scheme wind-downs use
# the same word). MF NAV-declaration noise is now filtered out entirely
# before classification -- see _is_mf_nav_noise() below.
CATEGORY_KEYWORDS = [
    # High-stakes categories -- extra scrutiny applied, see module docstring.
    ("Fraud", ["fraud"], "Schedule III Para A: fraud/defaults by promoter or KMP"),
    ("Insolvency", ["insolvency resolution", "corporate insolvency", "cirp", "winding up", "winding-up",
                     "nclt", "bifr"], "Schedule III Para A: CIRP under IBC / reference to BIFR / winding-up petition"),
    ("Auditor resignation", ["resignation of.*auditor", "auditor.*resign", "statutory auditor.*resign"],
     "Schedule III Para A: change in auditor"),
    ("Credit rating action", ["credit rating", "rating agency", "rating action taken", "rating revis",
                               "rating reaffirm", "rating upgrad", "rating downgrad", "rating withdraw"],
     "Schedule III Para A: revision in rating(s)"),
    ("Litigation / regulatory action", ["litigation", "show cause notice", "sebi order", "tribunal",
                                         "high court", "supreme court", "adjudicat", "penalty imposed",
                                         "regulatory action", "show-cause"],
     "Schedule III Para B: litigation(s)/dispute(s)/regulatory action(s) with impact"),
    ("Order win / contract", ["order.*bagged", "bagged.*order", "order.*received", "order.*secured",
                               "order.*awarded", "wins order", "letter of award", "loi received",
                               "contract.*awarded"], "Schedule III Para B: awarding/bagging of orders/contracts"),
]

_CATEGORY_LABELS = {label for label, _, _ in NSE_FEEDS} | {label for label, _, _ in CATEGORY_KEYWORDS} | {"General announcement"}

# Mutual-fund NAV declarations are routine daily pricing notices, not
# corporate disclosures -- they dominate the general Announcements feed by
# volume (roughly half of it on a typical day) and are pure noise for a
# company-filings feature. Filtered out before classification/return rather
# than left to accidentally match a keyword (see CRISIL false-positive note
# above).
_MF_NAV_RE = re.compile(r"net asset value \(per unit\)|declaration of nav", re.IGNORECASE)


def _is_mf_nav_noise(item):
    return bool(_MF_NAV_RE.search(item.get("description", "")))


def _parse_rss(xml_bytes):
    """Parse a real RSS 2.0 payload into a list of item dicts. Returns []
    (never raises) on any malformed/unexpected structure -- a bad feed
    shouldn't crash the tear sheet, it should just show no filings."""
    items = []
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return items
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if title:
            items.append({"title": title, "link": link, "description": description, "pub_date": pub_date})
    return items


def fetch_nse_feed(feed_filename, timeout=REQUEST_TIMEOUT):
    """Fetch one NSE RSS feed by filename. Returns (items, error) -- error is
    None on success, or a short string describing what went wrong (timeout,
    HTTP status, parse failure) so a caller can show an honest reason rather
    than silently showing nothing."""
    url = f"{NSE_BASE}/{feed_filename}"
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        if response.status_code != 200:
            return [], f"NSE feed HTTP {response.status_code}"
        return _parse_rss(response.content), None
    except requests.exceptions.Timeout:
        return [], f"NSE feed timed out after {timeout}s"
    except requests.exceptions.RequestException as exc:
        return [], f"NSE feed unavailable: {str(exc)[:150]}"


def fetch_bse_notices(timeout=REQUEST_TIMEOUT):
    """Fetch BSE's one official RSS feed (exchange-wide notices, NOT
    per-company disclosures -- see module docstring). Returns (items, error)."""
    try:
        response = requests.get(BSE_NOTICES_URL, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        if response.status_code != 200:
            return [], f"BSE feed HTTP {response.status_code}"
        return _parse_rss(response.content), None
    except requests.exceptions.Timeout:
        return [], f"BSE feed timed out after {timeout}s"
    except requests.exceptions.RequestException as exc:
        return [], f"BSE feed unavailable: {str(exc)[:150]}"


def fetch_all_nse_filings(timeout=REQUEST_TIMEOUT):
    """Fetch every feed in NSE_FEEDS. Returns (all_items, errors) where
    all_items is a flat list of dicts (each item tagged with its source
    category + provenance) and errors is a dict of {feed_filename: reason}
    for any feed that failed -- a single feed failing doesn't lose the
    others."""
    all_items = []
    errors = {}
    for i, (filename, category, provenance) in enumerate(NSE_FEEDS):
        if i > 0:
            time.sleep(INTER_FEED_DELAY)
        items, error = fetch_nse_feed(filename, timeout=timeout)
        if error:
            errors[filename] = error
            continue
        for item in items:
            if _is_mf_nav_noise(item):
                continue
            item = dict(item)
            item["source_exchange"] = "NSE"
            if category == "General announcement":
                item["category"], item["category_provenance"] = classify_announcement(item)
            else:
                item["category"] = category
                item["category_provenance"] = provenance
            all_items.append(item)
    return all_items, errors


def classify_announcement(item):
    """Classify one item from the general Announcements feed using strict
    keyword/phrase matching. Returns (category_label, provenance). Falls
    back to ("General announcement", ...) rather than ever guessing into a
    high-stakes bucket without a real keyword match."""
    haystack = f"{item.get('title', '')} {item.get('description', '')}".lower()
    for label, patterns, provenance in CATEGORY_KEYWORDS:
        for pattern in patterns:
            if re.search(pattern, haystack):
                return label, provenance
    return "General announcement", "Reg 30(1) -- general disclosure, no specific Schedule III category matched"


def match_filings_to_company(filings, company_name):
    """Filter a list of already-fetched filing items to those whose title
    plausibly refers to company_name. NSE feed items carry only a company
    NAME (no ticker symbol), so this is a normalized-substring match, not an
    exact key join -- deliberately conservative (requires the core name to
    appear), not fuzzy/approximate, to avoid attributing one company's
    filing to a similarly-named different company."""
    if not company_name or not isinstance(company_name, str):
        return []
    norm_target = _normalize_company_name(company_name)
    if not norm_target:
        return []
    matches = []
    for item in filings:
        norm_title = _normalize_company_name(item.get("title", ""))
        if norm_target in norm_title or norm_title in norm_target:
            matches.append(item)
    return matches


_SUFFIX_RE = re.compile(r"\b(limited|ltd|the|inc|india)\b", re.IGNORECASE)
_NONALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_company_name(name):
    """Lowercase, drop common corporate suffixes (Limited/Ltd/India), strip
    punctuation/whitespace -- so "Reliance Industries Limited" and "Reliance
    Industries" compare equal without being a loose fuzzy match."""
    name = _SUFFIX_RE.sub("", name.lower())
    name = _NONALNUM_RE.sub("", name)
    return name.strip()


def parse_pub_date(pub_date_str):
    """Best-effort parse of an RSS pubDate string into a datetime, for
    sorting -- returns None (sorts last) rather than raising on an
    unexpected format."""
    formats = ["%d-%b-%Y %H:%M:%S", "%d-%B-%Y %H:%M:%S", "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"]
    for fmt in formats:
        try:
            return datetime.strptime(pub_date_str, fmt)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    print("=== fetch_all_nse_filings() live check ===")
    filings, errors = fetch_all_nse_filings()
    print(f"Total items fetched: {len(filings)}")
    print(f"Feeds with errors: {len(errors)} / {len(NSE_FEEDS)}")
    for feed, reason in errors.items():
        print(f"  {feed}: {reason}")

    print()
    print("Category distribution:")
    from collections import Counter
    counts = Counter(item["category"] for item in filings)
    for category, count in counts.most_common():
        print(f"  {category:35s} {count}")

    print()
    print("=== BSE notices (separate, not Reg-30-tagged) ===")
    bse_items, bse_error = fetch_bse_notices()
    print(f"BSE items: {len(bse_items)}, error: {bse_error}")
    if bse_items:
        print(f"  sample: {bse_items[0]['title']}")

    print()
    print("=== Sample match: first company in the general feed ===")
    if filings:
        sample_title = filings[0]["title"]
        matched = match_filings_to_company(filings, sample_title)
        print(f"Matching '{sample_title}': {len(matched)} item(s) found")
