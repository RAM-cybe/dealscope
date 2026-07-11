"""EY 6-bucket sector classification.

The keyword rules below are the same ones used to classify deals_full_v2.csv's
`ey_bucket` column (see reclassify_deals_v2.py / merge_build.py in the project
root). Reusing them here means a company and a deal that share a bucket label
match by exact string equality, per BLUEPRINT.md's SectorMapping -> DealComp
relationship.
"""

from .schema import EY_BUCKETS, UNCLASSIFIED_BUCKET

_RULES = [
    (
        "Lifesciences",
        [
            "health", "hospital", "pharma", "diagnos", "biotech", "medtech",
            "medical", "life scien", "clinic", "wellness", "drug",
        ],
    ),
    (
        "Financial Services",
        [
            "bank", "nbfc", "insur", "asset manag", "wealth", "capital market",
            "fintech", "financial servic", "financial conglomerat", "broking",
            "stock exchange", "mutual fund", "payment", "lending", "microfinance",
            "credit servic", "mortgage",
        ],
    ),
    (
        "Consumer Products and Retail",
        [
            "retail", "fmcg", "consumer", "d2c", "food", "beverage", "apparel",
            "personal care", "e-commerce", "ecommerce", "quick commerce",
            "hospitality", "restaurant", "fashion", "cosmetic", "beauty",
            "grocery", "footwear", "luxury", "leisure", "resort", "lodging",
            "department store", "discount store", "furnishing", "tobacco",
            "confection",
        ],
    ),
    (
        "Technology",
        [
            "it services", "software", "technology", "tech services", "saas",
            "internet", "telecom", "semiconductor", "data center", "datacenter",
            "ai ", "artificial intelligence", "cloud", "digital", "electronics",
            "computer", "deeptech", "gaming", "media", "platform",
            "cybersecurity", "edtech", "broadcast", "publishing",
            "entertainment", "communication equip", "advertis",
        ],
    ),
    (
        "Industrials and Auto",
        [
            "manufactur", "industrial", "engineering", "auto", "aerospace",
            "defence", "defense", "chemical", "metal", "mining", "steel",
            "machinery", "cement", "construction", "material", "textile",
            "logistics", "transport", "ev ", "electric vehicle", "ems",
            "aluminum", "copper", "coal", "packaging", "paper", "lumber",
            "railroad", "airline", "airport", "marine shipping", "trucking",
            "farm", "waste manag", "conglomerate",
        ],
    ),
    (
        "Infrastructure",
        [
            "infra", "road", "highway", "power", "energy", "renewable",
            "solar", "thermal", "port", "real estate", "reit", "invit",
            "utilit", "water", "cleantech", "green energy", "oil & gas",
            "oil and gas",
        ],
    ),
]


def classify_sector(sector, industry):
    """Map a company's raw sector/industry labels to one of the 6 EY buckets.

    Tries `industry` first (the more granular signal), falls back to `sector`.
    Never raises and never returns anything outside EY_BUCKETS + "Unclassified".
    """
    for text in (industry, sector):
        bucket = _classify_text(text)
        if bucket != UNCLASSIFIED_BUCKET:
            return bucket
    return UNCLASSIFIED_BUCKET


def _classify_text(text):
    if text is None:
        return UNCLASSIFIED_BUCKET
    t = str(text).strip()
    if not t or t.upper() in ("NA", "NAN"):
        return UNCLASSIFIED_BUCKET
    t = t.lower()
    # Exact-equality only: a loose "bucket name is a substring of the text"
    # check misclassifies compound labels, e.g. "Biotechnology" contains
    # "technology" and "Software - Infrastructure" contains "infrastructure".
    # This still catches the common case where `sector` is literally one of
    # our bucket names verbatim (e.g. Yahoo's broad sector "Financial
    # Services"); everything else is left to the ordered keyword rules below.
    for bucket in EY_BUCKETS:
        if t == bucket.lower():
            return bucket
    for bucket, keywords in _RULES:
        for kw in keywords:
            if kw in t:
                return bucket
    return UNCLASSIFIED_BUCKET
