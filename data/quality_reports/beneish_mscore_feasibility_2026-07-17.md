# Beneish M-Score feasibility check (2026-07-17)

**Decision: not built.** Per the explicit instruction for this round ("only build it if [the fields are] genuinely available for a reasonable share of companies... if key fields are missing, document exactly which ones and stop -- don't force an approximation"), this is a documentation of why the M-Score was not built, not the score itself.

## Method

The same yfinance pull used for `ebit`/`total_liabilities` and the Piotroski F-Score inputs (`archive/data_pipeline_scripts/pull_financial_health.py`) also pulled every field the 8 Beneish (1999) indices need, at no extra network cost (same `balance_sheet`/`financials`/`cashflow` calls already return these rows). Population was measured across the full live 2,046-company universe, post currency-guard, both annual periods required where the index needs a year-over-year ratio.

## Field-by-field population (both periods, where required)

| Index | What it needs | Population |
|---|---|---|
| DSRI (receivables index) | Accounts Receivable + Revenue | 90.2% |
| GMI (gross margin index) | Revenue + COGS | 91.3% |
| AQI (asset quality index) | Current Assets + Net PPE + Securities + Total Assets | 86.4% |
| SGI (sales growth index) | Revenue | 96.2% |
| DEPI (depreciation index) | Depreciation + Gross PPE | 90.1% |
| **SGAI (SG&A index)** | **SG&A expense + Revenue** | **30.7%** |
| LVGI (leverage index) | LT Debt + Current Liabilities + Total Assets | 70.9% |
| TATA (total accruals / total assets) | Net Income + CFO + Total Assets (single period) | 95.8% |

## Finding

Every index except SGAI clears 70%+ (most 86-96%). **SGAI is a real, isolated blocker at 30.7%** -- confirmed as the dominant bottleneck, not just a weak link among several: removing the SGAI requirement alone raises the theoretical "all indices computable" population from **19.1%** (all 8 required) to **63.0%** (7 of 8, everything but SGAI).

Root cause, not a random gap: yfinance's standardized income statement for most NSE small/mid-cap companies does not break out "Selling General And Administration" as its own line -- it is folded into `Total Expenses` / `Other Operating Expenses` upstream at the source. This is a structural difference in how Indian company filings get mapped into yfinance's normalized statement template, not a data-quality defect specific to this project's pull.

## Why this isn't "worked around"

Substituting a proxy for missing SG&A (e.g. `Total Expenses - Cost of Revenue`) would not be genuine SG&A -- it would fold in R&D, other operating costs, and anything else not separately broken out, producing a number that looks like real SG&A but isn't one. That is exactly the kind of forced approximation this project's no-fabrication rule exists to prevent (see CONTEXT.md's "Locked decisions"). A Beneish M-Score built on a proxied SGAI term would be presented as a real fraud-risk score while resting on an invented input for a third of the universe and an unreliable one for the rest -- not shippable on a tool whose entire premise is that a genuine gap stays blank rather than getting quietly filled in.

## Status

Not built, not deferred as "later" -- this is a closed feasibility finding. If yfinance's statement mapping for Indian filings changes to expose SG&A more completely in the future, this file's numbers are the baseline to re-check against.
