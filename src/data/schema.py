"""Schema constants and validation for the two bundled CSVs."""

REQUIRED_COMPANY_COLUMNS = [
    "symbol",
    "name",
    "sector",
    "industry",
    "revenue",
    "ebitda",
    "ebitda_margin_pct",
    "total_debt",
    "market_cap",
    "insider_holding_pct",
    "revenue_growth_pct",
    "return_on_equity_pct",
    "status",
    "return_on_capital_employed_pct",
    "promoter_pledge_pct",
    "as_of_date",
]

COMPANY_NUMERIC_COLUMNS = [
    "revenue",
    "ebitda",
    "ebitda_margin_pct",
    "total_debt",
    "market_cap",
    "insider_holding_pct",
    "revenue_growth_pct",
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "promoter_pledge_pct",
]

REQUIRED_DEAL_COLUMNS = [
    "month",
    "target",
    "acquirer",
    "sector_raw",
    "deal_value_usdm",
    "deal_type",
    "stake_pct",
    "ey_bucket",
    "source_report",
    "report_year",
]

EY_BUCKETS = (
    "Infrastructure",
    "Industrials and Auto",
    "Consumer Products and Retail",
    "Lifesciences",
    "Technology",
    "Financial Services",
)
UNCLASSIFIED_BUCKET = "Unclassified"
ALL_BUCKETS = EY_BUCKETS + (UNCLASSIFIED_BUCKET,)


class SchemaError(Exception):
    """Raised when a required column is entirely absent from a bundled CSV."""


def validate_required_columns(df, required_columns, source_name):
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise SchemaError(
            f"{source_name} is missing required column(s): {', '.join(missing)}. "
            f"Expected columns: {', '.join(required_columns)}."
        )
