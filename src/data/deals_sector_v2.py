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

Blank sector_raw (and one 'Others' landmark) is rescued by an explicit
(target, acquirer, year) map — identity only, never a guessed label.
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


def _is_blank(value):
    if value is None:
        return True
    # NaN is the only float that is not equal to itself.
    if isinstance(value, float) and value != value:
        return True
    text = str(value).strip()
    return (not text) or text.upper() in ("NA", "NAN", "NONE")


def landmark_deal_key(target, acquirer, report_year):
    """Identity key for a landmark rescue: exact CSV target + acquirer + year."""
    if _is_blank(target) or _is_blank(acquirer) or _is_blank(report_year):
        return None
    try:
        year = int(float(report_year))
    except (TypeError, ValueError):
        return None
    return (str(target).strip(), str(acquirer).strip(), year)


# 48 landmark deals whose sector_raw is blank (or the one labelled "Others")
# and therefore fell to Unclassified. Keys are the live CSV identity
# (target, acquirer, report_year) — not the shorter names in the lock
# document — so Flipkart 2015/2023, the labelled Credila 2023 row, and
# the labelled Manipal 2023 row stay on their existing sector_raw map.
# Source: GROUP6_DECISION_LOCK.md. Do not invent rows; if a CSV identity
# drifts, leave the deal Unclassified and fail the rescue test.
LANDMARK_DEAL_SECTOR_V2 = {
    ("Sanmar Engineering Services Ltd.", "Fairfax India Holdings Corporation", 2016): _IND,
    ("Air India", "Talace (Tata Group)", 2021): _IND,
    ("BillDesk", "PayU", 2021): _FS,
    ("Byju's", "Footpath Ventures, GSV Ventures, ADQ, Owl Ventures, B Capital Group, Prosus Ventures, Silver Lake, Blackstone and others", 2021): _TECH,
    ("Dewan Housing Finance Corporation", "Piramal Capital and Housing Finance", 2021): _FS,
    ("Encora", "Advent International", 2021): _TECH,
    ("Flipkart", "Antara Capital, Tencent, Qatar Investment Authority, CPPIB, SoftBank Corp, Franklin Templeton PE, Tiger Global, GIC, Others", 2021): _DISC,
    ("Fullerton India", "Sumitomo Mitsui Financial Group", 2021): _FS,
    ("Hexaware", "Carlyle", 2021): _TECH,
    ("Mphasis", "Blackstone", 2021): _TECH,
    ("SB Energy", "Adani Green", 2021): _ENERGY,
    ("Adani Group, three portfolio companies", "International Holding Company", 2022): _ENERGY,
    ("Ambuja Cements Ltd", "Adani Enterprises Ltd", 2022): _IND,
    ("Citibank N.A., Indian consumer banking business", "Axis Bank Ltd", 2022): _FS,
    ("Essar Group, infrastructure assets", "ArcelorMittal Nippon Steel India Ltd", 2022): _INFRA,
    ("Housing Development Finance Corporation Ltd", "HDFC Bank Ltd", 2022): _FS,
    ("MindTree Ltd", "Larsen and Toubro Infotech Ltd", 2022): _TECH,
    ("Neelachal Ispat Nigam Ltd", "Tata Steel Long Products Pvt Ltd", 2022): _METALS,
    ("Sembcorp Energy India Ltd", "Tanweer Infrastructure Pte Ltd", 2022): _ENERGY,
    ("SolEnergi Power Pvt Ltd", "Shell Plc", 2022): _ENERGY,
    ("Viatris Inc., biosimilars assets", "Biocon Biologics Ltd", 2022): _HC,
    ("AMG Ammonia (Greenko Group)", "Gentari Sdn Bhd (Petronas), GIC", 2023): _ENERGY,
    ("AdPushup", "Geniee", 2023): _TECH,
    ("Aster DM Healthcare FZC", "Fajr Capital, Moopen Family and consortium", 2023): _HC,
    ("GMR Airports Ltd", "GMR Airports Infrastructure Ltd", 2023): _INFRA,
    ("HDFC Credila Financial Services Ltd", "BPEA EQT Ltd, ChrysCapital Investment Advisors Pvt Ltd", 2023): _FS,
    ("Manipal Health Enterprises Pvt Ltd", "Temasek Holdings Pte Ltd", 2023): _HC,
    ("ONGC Petro additions Ltd", "Oil and Natural Gas Corporation Ltd", 2023): _CHEM,
    ("SREI Infrastructure Finance Ltd", "National Asset Reconstruction Company Ltd, India Debt Resolution Company Ltd", 2023): _FS,
    ("TV18 Broadcast Ltd", "Network18 Media & Investments Ltd", 2023): _TMT,
    ("Zinc International assets of Vedanta Ltd", "Hindustan Zinc Ltd", 2023): _METALS,
    ("ATC Telecom Infrastructure Pvt Ltd", "Data Infrastructure Trust", 2024): _TMT,
    ("BT Group plc", "Bharti Enterprises (BhartiTeleventures UK)", 2024): _TMT,
    ("Bharat Serums & Vaccines Ltd", "Mankind Pharma Ltd", 2024): _HC,
    ("Hindustan Coca Cola Holdings Pvt Ltd", "Jubilant Bhartia Group", 2024): _STAPLES,
    ("Nidar Infrastructure Ltd", "Cartica Acquisition Corp", 2024): _TECH,
    ("Quality Care India Ltd", "Aster DM Healthcare Ltd", 2024): _HC,
    ("Seven Toll Road projects concession", "NHIT Eastern Projects Pvt Ltd", 2024): _INFRA,
    ("TS Global Holdings Pte Ltd", "Tata Steel Ltd", 2024): _METALS,
    ("Abbot Point Port Holdings Pte Ltd", "Adani Ports and Special Economic Zone Ltd", 2025): _INFRA,
    ("Encora Digital LLC", "Coforge Ltd", 2025): _TECH,
    ("Hypervault AI Data Center Ltd", "Tata Consultancy Services Ltd, TPG Terabyte Bidco", 2025): _TECH,
    ("Iveco Group N.V.", "Tata Motors Ltd", 2025): _AUTO,
    ("RBL Bank Ltd", "Emirates NBD PJSC", 2025): _FS,
    ("Sapient Finserv Pvt Ltd", "Equirus Capital Pvt Ltd", 2025): _FS,
    ("Schneider Electric India Pvt Ltd", "Schneider Electric SE", 2025): _IND,
    ("Shriram Finance Ltd", "MUFG Bank Ltd", 2025): _FS,
    ("WNS Holdings Ltd", "Capgemini SE", 2025): _TECH,
}


def classify_deal_sector_v2(sector_raw, target=None, acquirer=None, report_year=None):
    """Map a deal to a v2 bucket.

    Landmark identity (target + acquirer + year) wins when present, so the
    48 blank-sector_raw deals can be rescued without inventing a sector_raw
    label and without remapping every 'Others' row. Otherwise this is the
    existing normalized sector_raw lookup; unknown stays Unclassified.
    """
    key = landmark_deal_key(target, acquirer, report_year)
    if key in LANDMARK_DEAL_SECTOR_V2:
        return LANDMARK_DEAL_SECTOR_V2[key]
    if _is_blank(sector_raw):
        return UNCLASSIFIED_V2
    return NORMALIZED_DEAL_SECTOR_TO_V2.get(_norm(sector_raw), UNCLASSIFIED_V2)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.data.loaders import load_deals

    deals = load_deals()

    has_label = deals["sector_raw"].notna()
    unmapped = deals[has_label & (deals["sector_v2"] == UNCLASSIFIED_V2)]
    genuinely_other = unmapped["sector_raw"].str.strip().str.lower().eq("others")
    gaps = unmapped[~genuinely_other]["sector_raw"].unique()
    leftover = deals[deals["sector_v2"] == UNCLASSIFIED_V2]

    print(f"deals: {len(deals)} | labelled: {has_label.sum()} | "
          f"mapped: {(deals['sector_v2'] != UNCLASSIFIED_V2).sum()}")
    print(deals["sector_v2"].value_counts().to_string())
    print(f"landmark rescues: {len(LANDMARK_DEAL_SECTOR_V2)} | "
          f"unclassified leftover: {len(leftover)}")
    if len(gaps):
        print(f"\nMAPPING GAPS ({len(gaps)}):")
        for g in gaps:
            print(f"  {g!r}")
        sys.exit(1)
    print("\ncoverage OK: every labelled deal maps; leftover Unclassified "
          "is only unmatched blank/'Others' rows")
