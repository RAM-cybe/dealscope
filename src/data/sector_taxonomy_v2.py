"""Sector taxonomy v2 — 13-bucket, Yahoo-industry-anchored classification.

Replaces the keyword-matching approach of sector_mapping.py (which produced a
956-company "Industrials and Auto" mega-bucket and systematic misroutes like
Bharti Airtel -> Technology and Adani Enterprises -> Industrials) with an
explicit, auditable lookup: every Yahoo Finance `industry` label observed in
the dataset maps to exactly one v2 sector. No substring matching, no rule
ordering, no accidents.

Design decisions (owner-approved 2026-07-17):
- 13 buckets: Materials split into Chemicals vs Metals/Mining/Materials;
  Real Estate standalone (not merged into Infrastructure).
- Textile Manufacturing + Packaging & Containers -> Consumer Discretionary
  (follows Yahoo's own Consumer Cyclical placement; consumer value chain).
- Solar -> Energy & Utilities (panel/EPC players are energy-transition assets,
  not IT peers).
- Agricultural Inputs (fertilizers/agrochem) -> Chemicals per GICS convention.

Companies whose classification is ambiguous are flagged via REVIEW_INDUSTRIES
(kept in their default bucket until a human review moves them).

The legacy 6-bucket `ey_bucket` remains in place for deals-comps matching
until deals_full_v2.csv is remapped (see docs/IMPLEMENTATION_PLAN.md).
"""

# Bump whenever bucket definitions or overrides change in a way that alters
# peer groups — consumers (e.g. the AI-rationale cache key) use it to
# invalidate derived artifacts that baked in old sector labels.
TAXONOMY_VERSION = "v2.1"

SECTOR_V2_BUCKETS = (
    "Financial Services",
    "Technology & IT Services",
    "Healthcare & Lifesciences",
    "Consumer Discretionary & Retail",
    "Consumer Staples & Agri",
    "Automotive & Mobility",
    "Industrials & Capital Goods",
    "Chemicals",
    "Metals, Mining & Materials",
    "Energy & Utilities",
    "Infrastructure & Construction",
    "Real Estate",
    "Telecom, Media & Entertainment",
)
UNCLASSIFIED_V2 = "Unclassified"
ALL_V2_BUCKETS = SECTOR_V2_BUCKETS + (UNCLASSIFIED_V2,)

# Every Yahoo `industry` label present in dealscope_base_2026-07-12.csv.
# Coverage is validated by tests/audits: an industry missing here maps to
# Unclassified, which the quality report treats as a defect to fix.
INDUSTRY_TO_SECTOR_V2 = {
    # --- Financial Services (unchanged from Yahoo) ---
    "Credit Services": "Financial Services",
    "Capital Markets": "Financial Services",
    "Banks - Regional": "Financial Services",
    "Asset Management": "Financial Services",
    "Mortgage Finance": "Financial Services",
    "Insurance - Life": "Financial Services",
    "Financial Conglomerates": "Financial Services",
    "Financial Data & Stock Exchanges": "Financial Services",
    "Shell Companies": "Financial Services",            # review: holdcos
    "Insurance - Diversified": "Financial Services",
    "Insurance Brokers": "Financial Services",
    "Insurance - Property & Casualty": "Financial Services",
    "Insurance - Reinsurance": "Financial Services",

    # --- Technology & IT Services ---
    "Information Technology Services": "Technology & IT Services",
    "Software - Application": "Technology & IT Services",
    "Software - Infrastructure": "Technology & IT Services",
    "Communication Equipment": "Technology & IT Services",
    "Electronic Components": "Technology & IT Services",
    "Consumer Electronics": "Technology & IT Services",
    "Electronics & Computer Distribution": "Technology & IT Services",
    "Computer Hardware": "Technology & IT Services",
    "Scientific & Technical Instruments": "Technology & IT Services",
    "Semiconductor Equipment & Materials": "Technology & IT Services",

    # --- Healthcare & Lifesciences ---
    "Drug Manufacturers - Specialty & Generic": "Healthcare & Lifesciences",
    "Medical Care Facilities": "Healthcare & Lifesciences",
    "Drug Manufacturers - General": "Healthcare & Lifesciences",
    "Biotechnology": "Healthcare & Lifesciences",
    "Diagnostics & Research": "Healthcare & Lifesciences",
    "Medical Instruments & Supplies": "Healthcare & Lifesciences",
    "Health Information Services": "Healthcare & Lifesciences",
    "Medical Devices": "Healthcare & Lifesciences",
    "Pharmaceutical Retailers": "Healthcare & Lifesciences",
    "Healthcare Plans": "Healthcare & Lifesciences",
    "Medical Distribution": "Healthcare & Lifesciences",

    # --- Consumer Discretionary & Retail (Consumer Cyclical minus autos) ---
    "Textile Manufacturing": "Consumer Discretionary & Retail",
    "Furnishings, Fixtures & Appliances": "Consumer Discretionary & Retail",
    "Luxury Goods": "Consumer Discretionary & Retail",
    "Lodging": "Consumer Discretionary & Retail",
    "Packaging & Containers": "Consumer Discretionary & Retail",
    "Apparel Manufacturing": "Consumer Discretionary & Retail",
    "Footwear & Accessories": "Consumer Discretionary & Retail",
    "Apparel Retail": "Consumer Discretionary & Retail",
    "Restaurants": "Consumer Discretionary & Retail",
    "Internet Retail": "Consumer Discretionary & Retail",
    "Travel Services": "Consumer Discretionary & Retail",
    "Department Stores": "Consumer Discretionary & Retail",
    "Resorts & Casinos": "Consumer Discretionary & Retail",
    "Specialty Retail": "Consumer Discretionary & Retail",
    "Leisure": "Consumer Discretionary & Retail",
    "Home Improvement Retail": "Consumer Discretionary & Retail",

    # --- Consumer Staples & Agri ---
    "Packaged Foods": "Consumer Staples & Agri",
    "Confectioners": "Consumer Staples & Agri",
    "Household & Personal Products": "Consumer Staples & Agri",
    "Farm Products": "Consumer Staples & Agri",          # was hijacked to Industrials by "farm" keyword
    # Yahoo files education under Consumer Defensive (US-centric quirk);
    # tuition/edtech spend in India is discretionary (PhysicsWallah, NIIT).
    "Education & Training Services": "Consumer Discretionary & Retail",
    "Beverages - Wineries & Distilleries": "Consumer Staples & Agri",
    "Beverages - Non-Alcoholic": "Consumer Staples & Agri",
    "Tobacco": "Consumer Staples & Agri",
    "Beverages - Brewers": "Consumer Staples & Agri",
    "Discount Stores": "Consumer Staples & Agri",
    "Food Distribution": "Consumer Staples & Agri",
    "Grocery Stores": "Consumer Staples & Agri",

    # --- Automotive & Mobility (India M&A vertical; was buried in Industrials) ---
    "Auto Manufacturers": "Automotive & Mobility",
    "Auto Parts": "Automotive & Mobility",
    "Auto & Truck Dealerships": "Automotive & Mobility",

    # --- Industrials & Capital Goods ---
    "Specialty Industrial Machinery": "Industrials & Capital Goods",
    "Electrical Equipment & Parts": "Industrials & Capital Goods",
    "Building Products & Equipment": "Industrials & Capital Goods",
    "Conglomerates": "Industrials & Capital Goods",      # review: diversified holdcos
    "Metal Fabrication": "Industrials & Capital Goods",
    "Specialty Business Services": "Industrials & Capital Goods",
    "Integrated Freight & Logistics": "Industrials & Capital Goods",
    "Aerospace & Defense": "Industrials & Capital Goods",
    "Farm & Heavy Construction Machinery": "Industrials & Capital Goods",
    "Tools & Accessories": "Industrials & Capital Goods",
    "Business Equipment & Supplies": "Industrials & Capital Goods",
    "Staffing & Employment Services": "Industrials & Capital Goods",
    "Rental & Leasing Services": "Industrials & Capital Goods",
    "Consulting Services": "Industrials & Capital Goods",
    "Industrial Distribution": "Industrials & Capital Goods",
    "Security & Protection Services": "Industrials & Capital Goods",
    "Trucking": "Industrials & Capital Goods",
    "Airlines": "Industrials & Capital Goods",
    # Data check 2026-07-17: this dataset's "Railroads" is 4/5 rail-equipment
    # manufacturers (Jupiter Wagons, Texmaco, Titagarh) + CONCOR (rail
    # logistics operator) — capital goods, not rail infrastructure.
    "Railroads": "Industrials & Capital Goods",
    "Pollution & Treatment Controls": "Industrials & Capital Goods",
    "Waste Management": "Industrials & Capital Goods",

    # --- Chemicals (split out of Basic Materials) ---
    "Specialty Chemicals": "Chemicals",
    "Chemicals": "Chemicals",
    "Agricultural Inputs": "Chemicals",                  # fertilizers/agrochem per GICS

    # --- Metals, Mining & Materials (split out of Basic Materials) ---
    "Steel": "Metals, Mining & Materials",
    "Building Materials": "Metals, Mining & Materials",  # cement majors
    "Other Industrial Metals & Mining": "Metals, Mining & Materials",
    "Aluminum": "Metals, Mining & Materials",
    "Copper": "Metals, Mining & Materials",
    "Lumber & Wood Production": "Metals, Mining & Materials",
    "Paper & Paper Products": "Metals, Mining & Materials",
    "Coking Coal": "Metals, Mining & Materials",
    "Other Precious Metals & Mining": "Metals, Mining & Materials",

    # --- Energy & Utilities (Reliance/ONGC/Adani coal/NTPC in one bucket) ---
    "Oil & Gas Refining & Marketing": "Energy & Utilities",
    "Oil & Gas Equipment & Services": "Energy & Utilities",
    "Thermal Coal": "Energy & Utilities",                # was "coal"-keyworded into Industrials
    "Oil & Gas E&P": "Energy & Utilities",
    "Oil & Gas Integrated": "Energy & Utilities",
    "Utilities - Independent Power Producers": "Energy & Utilities",
    "Utilities - Renewable": "Energy & Utilities",
    "Utilities - Regulated Electric": "Energy & Utilities",
    "Utilities - Regulated Gas": "Energy & Utilities",
    "Utilities - Regulated Water": "Energy & Utilities",
    "Solar": "Energy & Utilities",                       # Yahoo tags under Technology

    # --- Infrastructure & Construction ---
    "Engineering & Construction": "Infrastructure & Construction",
    "Infrastructure Operations": "Infrastructure & Construction",
    "Marine Shipping": "Infrastructure & Construction",  # review: ports vs shipping lines
    "Airports & Air Services": "Infrastructure & Construction",

    # --- Real Estate (standalone; was merged into Infrastructure) ---
    "Real Estate - Development": "Real Estate",
    "Real Estate Services": "Real Estate",
    "Real Estate - Diversified": "Real Estate",

    # --- Telecom, Media & Entertainment (was pooled with IT services) ---
    "Entertainment": "Telecom, Media & Entertainment",
    "Broadcasting": "Telecom, Media & Entertainment",
    "Telecom Services": "Telecom, Media & Entertainment",
    "Publishing": "Telecom, Media & Entertainment",
    "Advertising Agencies": "Telecom, Media & Entertainment",
    "Internet Content & Information": "Telecom, Media & Entertainment",
    "Electronic Gaming & Multimedia": "Telecom, Media & Entertainment",
}

# Industries whose default bucket is a judgment call: companies here are
# classified (never left Unclassified) but surfaced in the needs-review report
# so a human can override per company via MANUAL_OVERRIDES below.
REVIEW_INDUSTRIES = {
    "Conglomerates": "Diversified holdcos — verify each against dominant revenue segment",
    "Shell Companies": "Listed investment holdcos — verify underlying assets",
    "Marine Shipping": "Ports (infra assets) vs shipping lines (transport operators)",
    "Railroads": "CONCOR is a logistics operator; the rest are wagon manufacturers",
}

# Per-symbol overrides beat the industry mapping. Every entry carries its
# reason so the classification stays auditable. Reviewed 2026-07-17 against
# each company's actual dominant business (annual-report segments / public
# filings knowledge); prioritized by market cap from the needs-review queue.
MANUAL_OVERRIDES = {
    # -- Yahoo "Conglomerates" resolved by dominant revenue segment --
    "SRF": "Chemicals",                          # fluorochemicals + specialty chem + packaging films
    "CYIENT": "Technology & IT Services",        # ER&D/IT services company, not a conglomerate
    "JSWHL": "Financial Services",               # pure investment holdco (JSW group stakes)
    "HNDFDS": "Consumer Staples & Agri",         # contract FMCG manufacturer
    "NESCO": "Real Estate",                      # IT parks + Bombay Exhibition Centre licensing

    # -- Yahoo "Marine Shipping" split: port infra vs vessel operators --
    "GESHIP": "Industrials & Capital Goods",     # tanker/bulk shipping line (transport operator)
    "SCI": "Industrials & Capital Goods",        # shipping line (transport operator)
    "ESSARSHPNG": "Industrials & Capital Goods", # shipping line (transport operator)
    "SHREEJISPG": "Industrials & Capital Goods", # shipping & cargo logistics services
    "CORDELIA": "Consumer Discretionary & Retail",  # Cordelia Cruises — leisure travel
    "SEAMECLTD": "Energy & Utilities",           # subsea/offshore oilfield services

    # -- Null Yahoo data, classified from public business descriptions --
    "JSWDULUX": "Chemicals",                     # paints (JSW Paints / AkzoNobel-Dulux India); peer of Asian Paints
    "MAFATIND": "Consumer Discretionary & Retail",  # textiles
    "ELPROINTL": "Real Estate",                  # property development + investment holdings
}


def classify_sector_v2(symbol, industry):
    """Map a company to its v2 sector. Overrides > industry lookup > Unclassified."""
    if symbol is not None:
        override = MANUAL_OVERRIDES.get(str(symbol).strip())
        if override:
            return override
    if industry is None:
        return UNCLASSIFIED_V2
    label = str(industry).strip()
    if not label or label.upper() in ("NA", "NAN"):
        return UNCLASSIFIED_V2
    return INDUSTRY_TO_SECTOR_V2.get(label, UNCLASSIFIED_V2)
