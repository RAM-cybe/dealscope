"""Build deal-scope-interface/data/news.json for the whole company universe from
the REAL NSE / BSE / Google News sources -- replacing the hand-authored sample
that previously covered 5 companies with generic homepage links.

Reuses src/data/filings.py and src/data/news.py as-is (fetch_all_nse_filings,
fetch_bse_notices, match_filings_to_company, fetch_company_news) -- no fetching
or matching logic is reimplemented here. This script is only the batch driver
and the JSON shaping.

Two very different cost profiles, so they're separated:

  Filings/notices (--filings): NSE and BSE are pulled ONCE, broadly (512 NSE
  items and a handful of BSE notices in a single pass), then matched to all
  2,046 companies locally by name. Not rate-limited per company, so this
  completes in one short run and covers the entire universe.

  News (--news): Google News RSS is genuinely one query per company, so ~2,046
  calls. Paced, log-and-continue on failure, and resumable -- news.json is
  re-read at startup and rewritten after every batch, so an interrupted or
  rate-limited run resumes from where it stopped instead of restarting.

Output matches the schema deal-scope-interface/lib/dealscope-data.ts already
consumes (CompanyNews: filings[{category,date,link}], bseNotices[{title,date,
link}], news[{headline,source,date,link}]), keyed by ticker -- so no frontend
change is needed, only real data.

Run from the repo root:
    python3 export_news_and_filings.py --filings            # fast, whole universe
    python3 export_news_and_filings.py --news [--limit N]   # slow, resumable
    python3 export_news_and_filings.py --filings --news     # both
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from src.data.loaders import load_companies  # noqa: E402
from src.data.filings import (  # noqa: E402
    fetch_all_nse_filings,
    fetch_bse_notices,
    match_filings_to_company,
    parse_pub_date,
)
from src.data.news import fetch_company_news  # noqa: E402

OUT_PATH = REPO_ROOT / "deal-scope-interface" / "data" / "news.json"

# Per-company caps. The tear sheet shows these as short scannable columns, not
# archives -- more than this is noise the user has to scroll past.
MAX_FILINGS = 6
MAX_BSE = 6
MAX_NEWS = 6

NEWS_DELAY_SECONDS = 1.5
NEWS_SAVE_EVERY = 25  # flush to disk this often so progress survives a kill


def _fmt_date(raw):
    """RSS pubDate -> YYYY-MM-DD for the frontend, falling back to the raw
    string rather than dropping a date we simply couldn't parse."""
    dt = parse_pub_date(raw) if raw else None
    return dt.strftime("%Y-%m-%d") if dt else (raw or "")


def _sort_key(item):
    dt = parse_pub_date(item.get("pub_date", ""))
    return dt.timestamp() if dt else 0.0


def load_existing():
    if not OUT_PATH.exists():
        return {}
    try:
        data = json.loads(OUT_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save(payload):
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=0))


def entry_for(payload, ticker):
    return payload.setdefault(ticker, {"filings": [], "bseNotices": [], "news": []})


def build_filings(df, payload):
    """One broad NSE + BSE pull, matched locally to every company."""
    print("Fetching all NSE filing feeds (one pass, not per company) ...")
    nse_items, nse_errors = fetch_all_nse_filings()
    print(f"  {len(nse_items)} NSE items; {len(nse_errors)} feed(s) failed")
    for feed, reason in nse_errors.items():
        print(f"    {feed}: {str(reason)[:100]}")

    print("Fetching BSE notices ...")
    bse_items, bse_error = fetch_bse_notices()
    print(f"  {len(bse_items)} BSE notices; error={bse_error}")

    matched_nse = matched_bse = 0
    for _, row in df.iterrows():
        ticker, name = row["symbol"], row["name"]
        entry = entry_for(payload, ticker)

        hits = sorted(match_filings_to_company(nse_items, name), key=_sort_key, reverse=True)
        entry["filings"] = [
            {
                "category": h.get("category") or "General announcement",
                "date": _fmt_date(h.get("pub_date")),
                "link": h.get("link") or "",
            }
            for h in hits[:MAX_FILINGS]
            if h.get("link")
        ]
        if entry["filings"]:
            matched_nse += 1

        # BSE's notices feed mixes exchange-wide items ("Demat Auction 674",
        # "Suspension of trading in T-bills") with genuinely company-specific
        # ones ("Part Redemption of Debentures of Keystone Realtors Limited").
        # Only the latter are attached, using the same conservative name match
        # as NSE. Attaching the exchange-wide ones to all 2,046 companies would
        # imply they're about that company, which they aren't -- so most
        # companies correctly get an empty list and the tear sheet's existing
        # "No recent notices found" state renders honestly.
        bse_hits = sorted(match_filings_to_company(bse_items, name), key=_sort_key, reverse=True)
        entry["bseNotices"] = [
            {
                "title": h.get("title") or "",
                "date": _fmt_date(h.get("pub_date")),
                "link": h.get("link") or "",
            }
            for h in bse_hits[:MAX_BSE]
            if h.get("link")
        ]
        if entry["bseNotices"]:
            matched_bse += 1

    save(payload)
    print(f"\nFilings done: {matched_nse} companies with >=1 NSE filing, "
          f"{matched_bse} with >=1 BSE notice (of {len(df)}).")
    return payload


def build_news(df, payload, limit=None):
    """One Google News query per company -- paced, resumable, log-and-continue."""
    todo = [
        (row["symbol"], row["name"])
        for _, row in df.iterrows()
        if not payload.get(row["symbol"], {}).get("news")
    ]
    if limit:
        todo = todo[:limit]
    print(f"\n{len(todo)} companies still need news "
          f"(already have it: {len(df) - len(todo)}).")

    ok = failed = 0
    for i, (ticker, name) in enumerate(todo, 1):
        try:
            items, error = fetch_company_news(name, max_items=MAX_NEWS)
        except Exception as exc:
            items, error = [], f"{type(exc).__name__}: {str(exc)[:120]}"

        if items:
            entry_for(payload, ticker)["news"] = [
                {
                    "headline": it.get("title") or "",
                    "source": it.get("source") or "Unknown source",
                    "date": _fmt_date(it.get("pub_date")),
                    "link": it.get("link") or "",
                }
                for it in items
                if it.get("link")
            ]
            ok += 1
        else:
            # Leave news empty; the tear sheet's honest "No recent coverage
            # found" state is correct, and a re-run will retry this company.
            failed += 1

        if i % 25 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] {ok} with news, {failed} without"
                  + (f" (last error: {str(error)[:60]})" if error else ""))
        if i % NEWS_SAVE_EVERY == 0:
            save(payload)

        time.sleep(NEWS_DELAY_SECONDS)

    save(payload)
    print(f"\nNews done this run: {ok} fetched, {failed} returned nothing.")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--filings", action="store_true", help="rebuild NSE filings + BSE notices")
    parser.add_argument("--news", action="store_true", help="fetch per-company Google News")
    parser.add_argument("--limit", type=int, default=None, help="news: cap companies this run")
    args = parser.parse_args()
    if not args.filings and not args.news:
        parser.error("pass --filings and/or --news")

    df = load_companies()
    print(f"{len(df)} companies loaded.")
    payload = load_existing()
    print(f"Existing news.json entries: {len(payload)}")

    if args.filings:
        payload = build_filings(df, payload)
    if args.news:
        payload = build_news(df, payload, limit=args.limit)

    with_f = sum(1 for v in payload.values() if v.get("filings"))
    with_b = sum(1 for v in payload.values() if v.get("bseNotices"))
    with_n = sum(1 for v in payload.values() if v.get("news"))
    print(f"\n=== news.json coverage ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===")
    print(f"  entries:            {len(payload)} / {len(df)}")
    print(f"  with NSE filings:   {with_f}")
    print(f"  with BSE notices:   {with_b}")
    print(f"  with news articles: {with_n}")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
