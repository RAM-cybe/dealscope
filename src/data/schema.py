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
    "net_income",
    # Phase 2 data-foundation fields (data/enriched/dealscope_base_2026-07-12.csv)
    "financial_currency",
    "currency_flag",
    "total_assets",
    "retained_earnings",
    "working_capital",
    "current_ratio",
    "quick_ratio",
    "debt_to_equity",
    "return_on_assets",
    "beta",
    "peg_ratio",
    "enterprise_value",
    "total_cash",
    "operating_cash_flow",
    "free_cash_flow",
    "price_to_book",
    "trailing_pe",
    "data_pull_date",
    # Part 1 financial-health-score fields (2026-07-17 data pull). ebit and
    # total_liabilities are the real new absolute fields (Part 1a); the
    # remaining 18 are two-annual-period (fy0=latest, fy1=prior) raw inputs
    # for the Piotroski F-Score, computed live by src/logic/piotroski.py --
    # same "raw fields in the CSV, score computed at runtime" pattern
    # src/logic/scoring.py already uses. See archive/data_pipeline_scripts/
    # merge_financial_health.py for provenance and the currency guard.
    "ebit",
    "total_liabilities",
    "net_income_fy0", "net_income_fy1",
    "operating_cash_flow_fy0", "operating_cash_flow_fy1",
    "total_assets_fy0", "total_assets_fy1",
    "long_term_debt_fy0", "long_term_debt_fy1",
    "current_assets_fy0", "current_assets_fy1",
    "current_liabilities_fy0", "current_liabilities_fy1",
    "total_revenue_fy0", "total_revenue_fy1",
    "cost_of_revenue_fy0", "cost_of_revenue_fy1",
    "shares_outstanding_fy0", "shares_outstanding_fy1",
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
    "net_income",
    # Phase 2 fields -- financial_currency, currency_flag, and data_pull_date
    # are categorical/date text, not numeric, so they're deliberately excluded
    # from this list (see REQUIRED_COMPANY_COLUMNS above for those three).
    "total_assets",
    "retained_earnings",
    "working_capital",
    "current_ratio",
    "quick_ratio",
    "debt_to_equity",
    "return_on_assets",
    "beta",
    "peg_ratio",
    "enterprise_value",
    "total_cash",
    "operating_cash_flow",
    "free_cash_flow",
    "price_to_book",
    "trailing_pe",
    "ebit",
    "total_liabilities",
    "net_income_fy0", "net_income_fy1",
    "operating_cash_flow_fy0", "operating_cash_flow_fy1",
    "total_assets_fy0", "total_assets_fy1",
    "long_term_debt_fy0", "long_term_debt_fy1",
    "current_assets_fy0", "current_assets_fy1",
    "current_liabilities_fy0", "current_liabilities_fy1",
    "total_revenue_fy0", "total_revenue_fy1",
    "cost_of_revenue_fy0", "cost_of_revenue_fy1",
    "shares_outstanding_fy0", "shares_outstanding_fy1",
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
