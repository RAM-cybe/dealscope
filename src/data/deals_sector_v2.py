"""Map deals_full_v2.csv's free-text `sector_raw` labels to the v2 taxonomy.

The deals CSV carries 196 distinct hand-written sector labels from EY M&A
report extraction ("Pharma (CRAMS / generic APIs)", "IT & ITeS", "Fin Tech",
...). The tear sheet matches comparable deals to a company by bucket
equality, so deals must speak the same 13-sector language as
sector_taxonomy_v2.py.

Approach: light normalization (lowercase, collapse separators) followed by an
explicit lookup — no substring/keyword scoring, so no ordering traps. Every
observed label normalizes to exactly one entry below; unmapped labels fall to
Unclassified and are surfaced by the __main__ audit, which fails loudly if
coverage drops (e.g. a future deals refresh introduces new labels).
"""

import re

from .sector_taxonomy_v2 import UNCLASSIFIED_V2

_FS = "Financial Services"
_TECH = "Technology & IT Services"
_HC = "Healthcare & Lifesciences"
_DISC = "Consumer Discretionary & Retail"
_STAPLES = "Consumer Staples & Agri"
_AUTO = "Automotive & Mobility"
_IND = "Industrials & Capital Goods"
_CHEM = "Chemicals"
_METALS = "Metals, Mining & Materials"
_ENERGY = "Energy & Utilities"
_INFRA = "Infrastructure & Construction"
_RE = "Real Estate"
_TMT = "Telecom, Media & Entertainment"


def _norm(label):
    """lowercase; collapse '&'/'and', punctuation and whitespace to single spaces."""
    t = str(label).strip().lower()
    t = t.replace("&", " and ")
    t = re.sub(r"[/:,\-()]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# Keyed on _norm(sector_raw). Grouped by target bucket for reviewability.
NORMALIZED_DEAL_SECTOR_TO_V2 = {
    # --- Technology & IT Services ---
    "technology services": _TECH,
    "technology": _TECH,
    "it and ites": _TECH,
    "it and ites others": _TECH,
    "it and ites software development": _TECH,
    "it and ites bpo": _TECH,
    "it and ites (others)": _TECH,
    "it solutions": _TECH,
    "software development": _TECH,
    "computer software": _TECH,
    "computer services": _TECH,
    "cloud technology": _TECH,
    "tech services": _TECH,
    "tech creators saas": _TECH,
    "saas": _TECH,
    "software": _TECH,
    "information technology": _TECH,
    "it": _TECH,
    "it software": _TECH,
    "data analytics and big data and ai": _TECH,
    "data analytics and ai": _TECH,
    "mobile vas": _TECH,
    "networking platform": _TECH,
    "discovery platform": _TECH,
    "tech start ups": _TECH,
    "start up": _TECH,          # EY "start-up" deal sections are digital/tech
    "others it": _TECH,
    "technology services er and d": _TECH,
    "technology services bpm": _TECH,
    "technology services healthcare it": _TECH,
    "industrial automation": _IND,
    "electronics telecom": _TECH,
    "industrial electronics": _TECH,

    # --- Healthcare & Lifesciences ---
    "pharma": _HC,
    "pharmaceuticals": _HC,
    "pharma and biotech": _HC,
    "pharma healthcare and biotech": _HC,
    "pharma health care and biotech": _HC,
    "healthcare hospitals": _HC,
    "healthcare hospitals standalone hospital acquisition west central": _HC,
    "healthcare hospitals standalone hospital acquisition south": _HC,
    "healthcare hospitals standalone hospital acquisition north": _HC,
    "hospitals": _HC,
    "healthcare": _HC,
    "healthcare providers": _HC,
    "healthcare pharma": _HC,
    "healthcare diagnostics": _HC,
    "primary healthcare": _HC,
    "medical and pharma": _HC,
    "medical pharmaceuticals": _HC,
    "medical devices": _HC,
    "health tech": _HC,
    "pharma generics otc nutraceuticals": _HC,
    "pharma biogenerics u.s. and europe generics": _HC,
    "pharma crams branded formulations": _HC,
    "pharma formulations european generics": _HC,
    "pharma drug discovery research formulations": _HC,
    "pharma crams generic apis": _HC,
    "pharma api contract manufacturing": _HC,
    "pharma crams specialty chemicals": _HC,
    "pharma u.s. europe generic markets": _HC,
    "pharma contract manufacturing research services": _HC,
    "pharma generics apis formulations": _HC,
    "pharma branded formulations generics apis": _HC,
    "pharma contract manufacturing generics": _HC,
    "pharma enzymes": _HC,
    "others pharma": _HC,

    # --- Financial Services ---
    "nbfc": _FS,
    "financial services": _FS,
    "financials": _FS,
    "financials microfinance": _FS,
    "financial services microfinance": _FS,
    "financials asset reconstruction": _FS,
    "banking and financial services": _FS,
    "banking and nbfc": _FS,
    "banking": _FS,
    "banks": _FS,
    "bank": _FS,
    "bfsi": _FS,
    "insurance and tpas": _FS,
    "insurance": _FS,
    "fin tech": _FS,
    "fintech": _FS,
    "fintech e commerce": _FS,
    "investment banking": _FS,

    # --- Consumer Discretionary & Retail ---
    "retail": _DISC,
    "retail and consumer": _DISC,
    "retail e commerce": _DISC,
    "consumer products and retail": _DISC,
    "consumer discretionary": _DISC,
    "consumer other": _DISC,
    "consumer services": _DISC,
    "consumer durables": _DISC,
    "consumer durable": _DISC,
    "consumer durables and home furnishing": _DISC,
    "e commerce": _DISC,
    "consumer technology e commerce": _DISC,
    "consumer technology": _DISC,
    "d2c": _DISC,
    "fashion": _DISC,
    "textiles": _DISC,
    "textiles apparel and accessories": _DISC,
    "hospitality and leisure": _DISC,
    "food tech": _DISC,
    "foodtech": _DISC,
    "on demand services": _DISC,
    "discovery platform e commerce": _DISC,
    "education": _DISC,
    "education solutions": _DISC,
    "online education": _DISC,
    "edtech": _DISC,

    # --- Consumer Staples & Agri ---
    "fmcg": _STAPLES,
    "consumer products": _STAPLES,
    "consumer foods": _STAPLES,
    "food and beverages": _STAPLES,
    "f and b": _STAPLES,
    "personal care": _STAPLES,

    # --- Automotive & Mobility ---
    "automotive": _AUTO,
    "automotives": _AUTO,
    "automobiles": _AUTO,
    "auto": _AUTO,
    "auto components": _AUTO,
    "auto tech": _AUTO,
    "manufacturing auto": _AUTO,
    "electric vehicles": _AUTO,

    # --- Industrials & Capital Goods ---
    "manufacturing": _IND,
    "manufacturing other": _IND,
    "diversified industrial products": _IND,
    "industrial products and services": _IND,
    "industrials": _IND,
    "capital goods": _IND,
    "business services": _IND,
    "professional services": _IND,
    "services other": _IND,
    "aviation": _IND,
    "travel transport and logistics": _IND,
    "travel and transport": _IND,
    "transport and logistics": _IND,
    "logistics and transportation": _IND,
    "logistics": _IND,

    # --- Chemicals ---
    "chemicals": _CHEM,
    "chemicals and materials": _CHEM,

    # --- Metals, Mining & Materials ---
    "metals": _METALS,
    "cement and building products": _METALS,
    "construction and transport cement": _METALS,

    # --- Energy & Utilities ---
    "energy and natural resources": _ENERGY,
    "energy": _ENERGY,
    "power": _ENERGY,
    "thermal power": _ENERGY,
    "power renewable energy": _ENERGY,
    "renewable energy infrastructure": _ENERGY,
    "energy infrastructure": _ENERGY,
    "oil and gas": _ENERGY,
    "utilities": _ENERGY,
    "transmission and distribution": _ENERGY,
    "cleantech": _ENERGY,
    "diversified cleantech": _ENERGY,

    # --- Infrastructure & Construction ---
    "infrastructure": _INFRA,
    "infrastructure management": _INFRA,
    "infrastructure roads": _INFRA,
    "roads and highways": _INFRA,
    "construction": _INFRA,
    "invit": _INFRA,

    # --- Real Estate ---
    "real estate": _RE,
    "real estate residential": _RE,
    "real estate commercial": _RE,

    # --- Telecom, Media & Entertainment ---
    "telecom": _TMT,
    "telecommunications carriers": _TMT,
    "tmt": _TMT,
    "tmt telecom": _TMT,
    "media and entertainment": _TMT,

    # --- Genuinely unmappable ---
    "others": UNCLASSIFIED_V2,
}


def classify_deal_sector_v2(sector_raw):
    """Map a raw deal-sector label to a v2 bucket; Unclassified when unknown."""
    if sector_raw is None:
        return UNCLASSIFIED_V2
    label = str(sector_raw).strip()
    if not label or label.upper() in ("NA", "NAN"):
        return UNCLASSIFIED_V2
    return NORMALIZED_DEAL_SECTOR_TO_V2.get(_norm(label), UNCLASSIFIED_V2)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.data.loaders import load_deals

    deals = load_deals()
    deals["sector_v2"] = deals["sector_raw"].map(classify_deal_sector_v2)

    has_label = deals["sector_raw"].notna()
    unmapped = deals[has_label & (deals["sector_v2"] == UNCLASSIFIED_V2)]
    genuinely_other = unmapped["sector_raw"].str.strip().str.lower().eq("others")
    gaps = unmapped[~genuinely_other]["sector_raw"].unique()

    print(f"deals: {len(deals)} | labelled: {has_label.sum()} | "
          f"mapped: {(has_label & (deals['sector_v2'] != UNCLASSIFIED_V2)).sum()}")
    print(deals["sector_v2"].value_counts().to_string())
    if len(gaps):
        print(f"\nMAPPING GAPS ({len(gaps)}):")
        for g in gaps:
            print(f"  {g!r}")
        sys.exit(1)
    print("\ncoverage OK: every labelled deal maps (only 'Others' is Unclassified)")
