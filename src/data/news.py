"""General news via Google News RSS (Part 2b).

SOURCING DISCIPLINE: every item returned carries its real publisher (parsed
from Google News RSS's own <source> tag, e.g. "NDTV Profit", "Livemint" --
not invented) and a real working link (Google News's redirect URL, which
resolves to the original article -- this is simply how Google News RSS
always works, not a shortcut taken by this project). Titles/descriptions are
shown verbatim as published, never paraphrased or summarized into a claim
this project can't verify -- see the project's locked no-fabrication rule.
"""

import re
from xml.etree import ElementTree

import requests

REQUEST_TIMEOUT = 10  # seconds -- Part 2d
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


def fetch_google_news(query, max_items=10, timeout=REQUEST_TIMEOUT):
    """Query Google News RSS for `query` (a company name or sector term).
    Returns (items, error). Each item: title, link, source, source_url,
    pub_date. error is None on success or a short honest reason on failure
    (timeout, HTTP status, parse failure) -- never silently empty without
    saying why."""
    params = {"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    try:
        response = requests.get(GOOGLE_NEWS_RSS, params=params,
                                 headers={"User-Agent": USER_AGENT}, timeout=timeout)
        if response.status_code != 200:
            return [], f"Google News RSS HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return [], f"Google News RSS timed out after {timeout}s"
    except requests.exceptions.RequestException as exc:
        return [], f"Google News RSS unavailable: {str(exc)[:150]}"

    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError:
        return [], "Google News RSS returned malformed XML"

    items = []
    for item in root.findall(".//item")[:max_items]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        source_url = source_el.get("url", "") if source_el is not None else ""
        # Google News titles are "<headline> - <publisher>"; the <source>
        # tag already carries the real publisher name cleanly, so strip the
        # redundant " - Publisher" suffix from the displayed headline only
        # if it exactly matches -- never alter the headline text itself
        # beyond that, and never invent a summary.
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)]
        if title:
            items.append({
                "title": title, "link": link, "source": source or "Unknown source",
                "source_url": source_url, "pub_date": pub_date,
            })
    return items, None


def fetch_company_news(company_name, max_items=8, timeout=REQUEST_TIMEOUT):
    """Convenience wrapper: query Google News for a company, appending
    "India" to reduce false matches against similarly-named non-Indian
    companies (a real, disclosed limitation -- literal name search, not
    entity-resolved, same design tradeoff already made for the app's
    ticker/company search, see app.py's search implementation)."""
    return fetch_google_news(f'"{company_name}" India', max_items=max_items, timeout=timeout)


if __name__ == "__main__":
    print("=== fetch_company_news() live check ===")
    for name in ["Reliance Industries", "Tata Consultancy Services", "Zomato"]:
        items, error = fetch_company_news(name, max_items=5)
        print(f"\n{name}: {len(items)} items, error={error}")
        for item in items[:3]:
            print(f"  [{item['source']}] {item['title']}")
            print(f"    {item['link'][:90]}...")
