#!/usr/bin/env python3
"""Targeted, resumable v2 enrichment for the M&A screening dataset.

This intentionally starts from companies_full.csv.  It does not re-pull any of
the financial fields already delivered in v1.  It only appends (a) calculated
ROCE from Yahoo annual statements, (b) promoter pledge from the latest NSE
shareholding XBRL, and (c) an NSE quote-page fallback for v1 market-cap gaps.
"""
import csv
import datetime as dt
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
import yfinance as yf

BASE = Path(__file__).resolve().parent
COMPANIES = BASE / "companies_full.csv"
OUT = BASE / "companies_full_v2.csv"
FIN_CACHE = BASE / "_v2_roce_cache.csv"
PLEDGE_CACHE = BASE / "_v2_pledge_cache.csv"
MCAP_CACHE = BASE / "_v2_mcap_cache.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def load_csv(path):
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {r["symbol"]: r for r in csv.DictReader(f) if r.get("symbol")}


def save_cache(path, values, fields):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for symbol in sorted(values):
            w.writerow({k: values[symbol].get(k, "") for k in fields})
    tmp.replace(path)


def scalar_at(df, label, period):
    if label not in df.index or period not in df.columns:
        return None
    value = df.loc[label, period]
    try:
        if value is None or str(value).lower() == "nan":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_roce(symbol):
    """Return the most-recent annual EBIT/(assets-current liabilities) x 100.

    ROCE is intentionally blank for banks/financial companies whose Yahoo
    balance sheets do not expose Current Liabilities, rather than substituting
    an unrelated return ratio.
    """
    last_reason = ""
    for attempt in range(3):
        try:
            # GYFTR was listed on NSE only days ago after LKP Finance's name
            # change; Yahoo has the active BSE instrument but not the NSE one.
            ticker = yf.Ticker(symbol + (".BO" if symbol == "GYFTR" else ".NS"))
            # yfinance exposes this same Yahoo annual-statement request through
            # its financials object.  Asking for the three required facts in a
            # single yfinance timeseries call prevents a second request per name.
            statement = ticker._fundamentals.financials._get_financials_time_series(
                "yearly", ["EBIT", "TotalAssets", "CurrentLiabilities"])
            if statement.empty:
                raise ValueError("Yahoo annual statement unavailable")
            needed = {"TotalAssets", "CurrentLiabilities", "EBIT"}
            missing = sorted(needed - set(statement.index))
            if missing:
                return "", "Yahoo statement missing " + ", ".join(missing)
            for period in statement.columns:
                ebit = scalar_at(statement, "EBIT", period)
                assets = scalar_at(statement, "TotalAssets", period)
                liabilities = scalar_at(statement, "CurrentLiabilities", period)
                if ebit is None or assets is None or liabilities is None:
                    continue
                capital_employed = assets - liabilities
                if capital_employed <= 0:
                    return "", "non-positive capital employed in latest complete Yahoo period"
                return f"{round(100 * ebit / capital_employed, 4)}", ""
            return "", "no Yahoo annual period with EBIT, Total Assets and Current Liabilities"
        except Exception as exc:  # endpoint throttles are transient
            last_reason = str(exc).replace("\n", " ")[:180]
            time.sleep(3 * (attempt + 1))
    return "", "Yahoo annual statements unavailable after 3 attempts: " + last_reason


def newest_filing(rows):
    def key(row):
        try:
            return dt.datetime.strptime(row.get("date", ""), "%d-%b-%Y")
        except ValueError:
            return dt.datetime.min
    return max(rows, key=key) if rows else None


def tag_value(soup, tag_fragment, context_fragment):
    candidates = [e for e in soup.find_all() if e.name and tag_fragment in e.name
                  and context_fragment in (e.get("contextRef") or "")]
    if not candidates:
        return None
    try:
        return float(candidates[-1].get_text(strip=True))
    except ValueError:
        return None


def fetch_pledge(symbol):
    """Use NSE's most recent shareholding XBRL, never a modelled value.

    In the NSE schema the promoter-and-promoter-group percentage is encoded as
    a fraction (e.g. 0.0538 for 5.38%), so it is converted to percent here.

    NSE's own API uses the literal string "-" as a placeholder for filings
    that predate XBRL (seen on pre-2013 rows for e.g. BATLIBOI/BIMETAL/KOVAI/
    RAJPALAYAM/SAYAJIHOTL, 2026-07-20 backfill run) -- a bare `r.get("xbrl")`
    truthiness check treats "-" as a real URL, so `newest_filing` picks a
    placeholder row and the subsequent GET fails with "Invalid URL '-'"
    instead of the correct, honest "no current shareholding XBRL" outcome.
    Confirmed empirically that none of the 5 affected symbols have any real
    XBRL row at all (so this fix doesn't change what those return -- it just
    reports why correctly), but a future, less complete symbol could have a
    real filing sitting behind other placeholder rows, so filtering "-" out
    here is a genuine correctness fix, not only a cosmetic one.
    """
    last_reason = ""
    for attempt in range(3):
        try:
            session = requests.Session()
            url = "https://www.nseindia.com/api/corporate-share-holdings-master"
            response = session.get(url, params={"index": "equities", "symbol": symbol},
                                   headers=HEADERS, timeout=25)
            if response.status_code != 200:
                raise ValueError(f"NSE shareholding endpoint HTTP {response.status_code}")
            rows = response.json()
            filing = newest_filing([r for r in rows if r.get("xbrl") and r.get("xbrl") != "-"])
            if not filing:
                return "", "NSE has no current shareholding XBRL"
            xml = session.get(filing["xbrl"], headers=HEADERS, timeout=25)
            if xml.status_code != 200:
                raise ValueError(f"NSE XBRL HTTP {xml.status_code}")
            soup = BeautifulSoup(xml.content, "xml")
            boolean = tag_value(soup, "WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged", "MainI")
            # Boolean tags cannot be converted by tag_value; read their text directly.
            if boolean is None:
                flags = [e.get_text(strip=True).lower() for e in soup.find_all()
                         if e.name and "WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged" in e.name
                         and (e.get("contextRef") or "") == "MainI"]
                if flags and flags[0] == "false":
                    return "0.0", f"NSE XBRL {filing.get('date', '')}: no promoter pledge disclosed"
            ratio = tag_value(soup, "EncumberedShareUnderPledgedAsPercentageOfTotalNumberOfShares",
                              "ShareholdingOfPromoterAndPromoterGroup_ContextI")
            if ratio is None:
                return "", f"NSE XBRL {filing.get('date', '')}: pledge flag/value not reported"
            value = ratio * 100 if abs(ratio) <= 1 else ratio
            return f"{round(value, 4)}", f"NSE XBRL {filing.get('date', '')}"
        except Exception as exc:
            last_reason = str(exc).replace("\n", " ")[:180]
            time.sleep(2 * (attempt + 1))
    return "", "NSE filing unavailable after 3 attempts: " + last_reason


def fetch_nse_market_cap(symbol):
    """Strictly attempt NSE's public quote endpoint for v1 gaps.

    This deliberately does not fall back to third-party sites or calculate an
    estimate.  If NSE blocks the public endpoint, the blank remains a blank.
    """
    try:
        response = requests.get("https://www.nseindia.com/api/quote-equity",
                                params={"symbol": symbol}, headers=HEADERS, timeout=25)
        if response.status_code != 200:
            return "", f"NSE public quote endpoint HTTP {response.status_code}"
        data = response.json()
        candidates = [data.get("marketCap"), data.get("priceInfo", {}).get("marketCap"),
                      data.get("metadata", {}).get("marketCap")]
        for value in candidates:
            try:
                if value is not None and float(value) > 0:
                    return str(value), "NSE public quote endpoint"
            except (TypeError, ValueError):
                pass
        return "", "NSE public quote response has no market cap"
    except Exception as exc:
        return "", "NSE public quote unavailable: " + str(exc).replace("\n", " ")[:180]


def main():
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))
        original_fields = list(companies[0].keys())
    # Recover the one v1 Yahoo-NSE failure under its active exchange symbol.
    # It remains GYFTR in the output, so the NSE universe is not relabelled.
    if not any(r["symbol"] == "GYFTR" for r in companies):
        info = yf.Ticker("GYFTR.BO").info
        def pct(key):
            value = info.get(key)
            return round(float(value) * 100, 4) if value is not None else ""
        companies.append({
            "symbol": "GYFTR", "name": info.get("longName") or info.get("shortName") or "Gyftr Limited",
            "sector": info.get("sector") or "", "industry": info.get("industry") or "",
            "revenue": info.get("totalRevenue") if info.get("totalRevenue") is not None else "",
            "ebitda": info.get("ebitda") if info.get("ebitda") is not None else "",
            "ebitda_margin_pct": pct("ebitdaMargins"),
            "total_debt": info.get("totalDebt") if info.get("totalDebt") is not None else "",
            "market_cap": info.get("marketCap") if info.get("marketCap") is not None else "",
            "insider_holding_pct": pct("heldPercentInsiders"),
            "revenue_growth_pct": pct("revenueGrowth"), "return_on_equity_pct": pct("returnOnEquity"),
            "status": "recovered_bse_yfinance",
        })
    fin = load_csv(FIN_CACHE)
    pledge = load_csv(PLEDGE_CACHE)
    mcap = load_csv(MCAP_CACHE)

    # A small worker pool keeps the two public data sources usable while making
    # this run practical for a 2,046-name universe. Cache writes stay in the
    # parent thread, so an interrupted run can be safely resumed.
    roce_todo = [r["symbol"] for r in companies if r["symbol"] not in fin]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_roce, symbol): symbol for symbol in roce_todo}
        for i, future in enumerate(as_completed(futures), 1):
            symbol = futures[future]
            value, reason = future.result()
            fin[symbol] = {"symbol": symbol, "return_on_capital_employed_pct": value, "roce_reason": reason}
            save_cache(FIN_CACHE, fin, ["symbol", "return_on_capital_employed_pct", "roce_reason"])
            if i % 25 == 0 or i == len(roce_todo):
                print(f"ROCE {i}/{len(roce_todo)}", flush=True)

    pledge_todo = [r["symbol"] for r in companies if r["symbol"] not in pledge]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_pledge, symbol): symbol for symbol in pledge_todo}
        for i, future in enumerate(as_completed(futures), 1):
            symbol = futures[future]
            value, reason = future.result()
            pledge[symbol] = {"symbol": symbol, "promoter_pledge_pct": value, "promoter_pledge_reason": reason}
            save_cache(PLEDGE_CACHE, pledge, ["symbol", "promoter_pledge_pct", "promoter_pledge_reason"])
            if i % 25 == 0 or i == len(pledge_todo):
                print(f"pledge {i}/{len(pledge_todo)}", flush=True)

    mcap_todo = [r["symbol"] for r in companies
                 if not r.get("market_cap", "").strip() and r["symbol"] not in mcap]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_nse_market_cap, symbol): symbol for symbol in mcap_todo}
        for i, future in enumerate(as_completed(futures), 1):
            symbol = futures[future]
            value, reason = future.result()
            mcap[symbol] = {"symbol": symbol, "market_cap": value, "market_cap_source": reason}
            save_cache(MCAP_CACHE, mcap, ["symbol", "market_cap", "market_cap_source"])
            if i % 20 == 0 or i == len(mcap_todo):
                print(f"market cap {i}/{len(mcap_todo)}", flush=True)

    new_fields = original_fields + ["return_on_capital_employed_pct", "roce_reason",
                                    "promoter_pledge_pct", "promoter_pledge_reason", "market_cap_source"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=new_fields)
        w.writeheader()
        for row in companies:
            symbol = row["symbol"]
            row = dict(row)
            row["return_on_capital_employed_pct"] = fin.get(symbol, {}).get("return_on_capital_employed_pct", "")
            row["roce_reason"] = fin.get(symbol, {}).get("roce_reason", "")
            row["promoter_pledge_pct"] = pledge.get(symbol, {}).get("promoter_pledge_pct", "")
            row["promoter_pledge_reason"] = pledge.get(symbol, {}).get("promoter_pledge_reason", "")
            if not row.get("market_cap", "").strip():
                row["market_cap"] = mcap.get(symbol, {}).get("market_cap", "")
                row["market_cap_source"] = mcap.get(symbol, {}).get("market_cap_source", "")
            else:
                row["market_cap_source"] = "yfinance BSE recovery" if symbol == "GYFTR" else "yfinance v1"
            w.writerow(row)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
