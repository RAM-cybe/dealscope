"""Indicative valuation range via sector-median multiples (PRD section 3, feature 4).

COMPOSITION-ORDER CONTRACT (do not violate this in Module 4 or anywhere else):
valuation_range() must always be called on the full, unfiltered company
universe -- never on output that has already passed through
filter_companies(). Peer multiples (EV/EBITDA, P/E) are computed within a
company's own ey_bucket; if that peer group has been narrowed by an active
filter, a company's implied valuation range would drift every time the user
adjusts a filter, even though nothing about the company itself changed. The
correct pipeline order is: score_companies() and valuation_range() both run
first (once, on the full universe), then filter_companies() purely for
display. filter_companies() must never feed back into either of them.
"""

import pandas as pd

MIN_PEERS = 3


def valuation_range(df):
    """Compute an indicative EV/EBITDA- and P/E-implied valuation range.

    See the module docstring for the composition-order contract: call this
    on the full unfiltered universe, then filter the result for display.

    EV/EBITDA method: within each ey_bucket, the peer set is every company
    (including the subject company itself, if it qualifies) with ebitda > 0.
    Requires at least MIN_PEERS such peers. The peer set's 25th/75th
    percentile EV/EBITDA multiple (EV = market_cap + total_debt, missing
    total_debt treated as 0) is applied to the company's own ebitda to get
    an implied EV range, then the company's own total_debt is subtracted to
    get an implied equity value range. Null (with a reason in
    valuation_note) if the company's own ebitda is missing, zero, or
    negative, or if fewer than MIN_PEERS qualifying peers exist in its
    bucket.

    P/E-implied method: same structure, peer set is companies with
    net_income > 0, multiple is market_cap / net_income, applied directly to
    the company's own net_income (no debt adjustment -- a P/E multiple
    already implies equity value). Same null conditions, substituting
    net_income for ebitda.

    Returns a copy of df with 5 new columns: ev_ebitda_low, ev_ebitda_high,
    pe_implied_low, pe_implied_high (all in the same currency units as
    market_cap/total_debt/ebitda/net_income), and valuation_note (a combined
    human-readable explanation of whichever method(s) could not be computed;
    empty string when both succeed).
    """
    df = df.copy()
    df["ev"] = df["market_cap"] + df["total_debt"].fillna(0)

    ev_ebitda_low = pd.Series(float("nan"), index=df.index, dtype="float64")
    ev_ebitda_high = pd.Series(float("nan"), index=df.index, dtype="float64")
    pe_low = pd.Series(float("nan"), index=df.index, dtype="float64")
    pe_high = pd.Series(float("nan"), index=df.index, dtype="float64")
    notes = pd.Series("", index=df.index, dtype="object")

    for bucket, group in df.groupby("ey_bucket"):
        ebitda_peers = group[group["ebitda"] > 0]
        ebitda_multiples = ebitda_peers["ev"] / ebitda_peers["ebitda"]
        ebitda_peer_count = len(ebitda_multiples)
        if ebitda_peer_count >= MIN_PEERS:
            ebitda_q25 = ebitda_multiples.quantile(0.25)
            ebitda_q75 = ebitda_multiples.quantile(0.75)
        else:
            ebitda_q25 = ebitda_q75 = None

        ni_peers = group[group["net_income"] > 0]
        pe_multiples = ni_peers["market_cap"] / ni_peers["net_income"]
        ni_peer_count = len(pe_multiples)
        if ni_peer_count >= MIN_PEERS:
            pe_q25 = pe_multiples.quantile(0.25)
            pe_q75 = pe_multiples.quantile(0.75)
        else:
            pe_q25 = pe_q75 = None

        for idx, row in group.iterrows():
            row_notes = []

            own_ebitda = row["ebitda"]
            if pd.isna(own_ebitda) or own_ebitda <= 0:
                row_notes.append("EV/EBITDA: own ebitda missing, zero, or negative")
            elif ebitda_peer_count < MIN_PEERS:
                row_notes.append(
                    f"EV/EBITDA: insufficient sector peer data "
                    f"({ebitda_peer_count} peer(s) with positive ebitda in {bucket}, need {MIN_PEERS})"
                )
            else:
                own_debt = row["total_debt"] if pd.notna(row["total_debt"]) else 0
                ev_ebitda_low[idx] = own_ebitda * ebitda_q25 - own_debt
                ev_ebitda_high[idx] = own_ebitda * ebitda_q75 - own_debt

            own_ni = row["net_income"]
            if pd.isna(own_ni) or own_ni <= 0:
                row_notes.append("P/E: own net_income missing, zero, or negative")
            elif ni_peer_count < MIN_PEERS:
                row_notes.append(
                    f"P/E: insufficient sector peer data "
                    f"({ni_peer_count} peer(s) with positive net_income in {bucket}, need {MIN_PEERS})"
                )
            else:
                pe_low[idx] = own_ni * pe_q25
                pe_high[idx] = own_ni * pe_q75

            if row_notes:
                notes[idx] = ". ".join(row_notes) + "."

    df["ev_ebitda_low"] = ev_ebitda_low
    df["ev_ebitda_high"] = ev_ebitda_high
    df["pe_implied_low"] = pe_low
    df["pe_implied_high"] = pe_high
    df["valuation_note"] = notes
    df = df.drop(columns=["ev"])

    return df


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.data.loaders import load_companies

    companies = load_companies()
    valued = valuation_range(companies)

    print("=== valuation_range manual-verification sample ===")

    # Pick one company per bucket with a full happy-path valuation.
    happy_path_symbols = []
    for bucket in ["Technology", "Financial Services"]:
        peers = valued[valued["ey_bucket"] == bucket]
        candidates = peers[peers["ev_ebitda_low"].notna() & peers["pe_implied_low"].notna()]
        if not candidates.empty:
            happy_path_symbols.append(candidates.iloc[0]["symbol"])

    # HCLTECH/INFY were blanked by the currency-contamination fix -- their
    # net_income (and ebitda) are null, so this exercises the "insufficient
    # data" path for real, not a synthetic case.
    null_path_symbols = ["HCLTECH", "INFY"]

    for symbol in happy_path_symbols + null_path_symbols:
        row = valued[valued["symbol"] == symbol].iloc[0]
        bucket = row["ey_bucket"]
        peers = valued[valued["ey_bucket"] == bucket]

        print(f"\n--- {row['name']} ({symbol}), bucket={bucket} ---")
        print(f"  own ebitda={row['ebitda']}, own net_income={row['net_income']}, "
              f"own total_debt={row['total_debt']}, own market_cap={row['market_cap']}")

        ebitda_peers = peers[peers["ebitda"] > 0]
        ev = ebitda_peers["market_cap"] + ebitda_peers["total_debt"].fillna(0)
        ebitda_multiples = ev / ebitda_peers["ebitda"]
        print(f"  EV/EBITDA peer count={len(ebitda_multiples)}, "
              f"25th={ebitda_multiples.quantile(0.25):.4f}, 75th={ebitda_multiples.quantile(0.75):.4f}"
              if len(ebitda_multiples) else "  EV/EBITDA peer count=0")

        ni_peers = peers[peers["net_income"] > 0]
        pe_multiples = ni_peers["market_cap"] / ni_peers["net_income"]
        print(f"  P/E peer count={len(pe_multiples)}, "
              f"25th={pe_multiples.quantile(0.25):.4f}, 75th={pe_multiples.quantile(0.75):.4f}"
              if len(pe_multiples) else "  P/E peer count=0")

        print(f"  ev_ebitda_low={row['ev_ebitda_low']}, ev_ebitda_high={row['ev_ebitda_high']}")
        print(f"  pe_implied_low={row['pe_implied_low']}, pe_implied_high={row['pe_implied_high']}")
        print(f"  valuation_note={row['valuation_note']!r}")

        if pd.notna(row["ev_ebitda_low"]):
            manual_debt = row["total_debt"] if pd.notna(row["total_debt"]) else 0
            manual_low = row["ebitda"] * ebitda_multiples.quantile(0.25) - manual_debt
            manual_high = row["ebitda"] * ebitda_multiples.quantile(0.75) - manual_debt
            match = abs(manual_low - row["ev_ebitda_low"]) < 1e-6 and abs(manual_high - row["ev_ebitda_high"]) < 1e-6
            print(f"  manual EV/EBITDA check: low={manual_low:.4f}, high={manual_high:.4f}, match={match}")

        if pd.notna(row["pe_implied_low"]):
            manual_pe_low = row["net_income"] * pe_multiples.quantile(0.25)
            manual_pe_high = row["net_income"] * pe_multiples.quantile(0.75)
            match = abs(manual_pe_low - row["pe_implied_low"]) < 1e-6 and abs(manual_pe_high - row["pe_implied_high"]) < 1e-6
            print(f"  manual P/E check: low={manual_pe_low:.4f}, high={manual_pe_high:.4f}, match={match}")
