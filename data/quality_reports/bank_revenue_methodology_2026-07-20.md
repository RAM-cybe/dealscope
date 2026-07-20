# Bank/NBFC revenue definition — investigation and decision (2026-07-20)

Investigated per this session's Part 3 enrichment task, before touching any bank/NBFC
`revenue` values. **Decision: leave as-is, document the caveat, do not source a different
field or scraper.** Reasoning and evidence below.

## The question

The 2026-07 data quality audit found large-cap banks showing a real gap between our
stored `revenue` (yfinance-sourced) and public "revenue" figures for the same company
(HDFCBANK -19.5%, SBIN -26.8%, BAJFINANCE -46.5%, AXISBANK -45.1%, ICICIBANK/KOTAKBANK
within ~10%). The working theory going in was "net vs. gross interest income."

## What the data actually shows

Pulled each bank's raw yfinance income-statement (`Ticker.financials`) directly, rather
than comparing black-box "revenue" numbers from two different vendors:

| Bank | Interest Income (gross) | Interest Expense | Net Interest Income | yfinance "Total Revenue" |
|---|---:|---:|---:|---:|
| HDFCBANK (FY25) | ₹322,796 Cr | ₹182,348 Cr | ₹140,449 Cr | ₹237,151 Cr |
| SBIN (FY26) | ₹514,933 Cr | ₹315,005 Cr | ₹199,928 Cr | ₹381,709 Cr |
| AXISBANK (FY26) | ₹132,538 Cr | ₹74,075 Cr | ₹58,463 Cr | ₹88,067 Cr |

The pattern is consistent and not a coincidence: **yfinance's own `totalRevenue` sits
between Net Interest Income and gross Interest Income for every bank checked** — roughly
NII + a further ~₹40-100K Cr, most plausibly Net Interest Income + non-interest ("other")
income, a legitimate concept equity analysts sometimes call "Net Total Income" or "Total
Operating Income" for a bank. It is not random noise and it is not obviously broken.

Separately, cross-referencing screener.in's own "Revenue"/"Sales" line for banks against
the same yfinance Interest Income figures shows screener's number lands very close to
**gross Interest Income alone** (SBIN screener ₹514,933 Cr = yfinance Interest Income
₹514,933 Cr, to the crore; AXISBANK screener ₹135,732 Cr ≈ yfinance Interest Income
₹132,538 Cr). And HDFC Bank's own screener "Other Income" line (₹134,548 Cr, FY25) is
implausible as a match to either NII or gross Interest Income alone — it's a genuinely
separate third figure.

**Conclusion: there are at least three different, each internally-consistent, "bank
revenue" conventions in circulation** — our pipeline's (≈ NII + Other Income), screener.in's
(≈ gross Interest Income), and the bank's own headline "Total Income" press-release figure
(= gross Interest Income + Other Income, the largest of the three). None of the three is
"the" correct one; they're just different, non-standardized ways different providers handle
a business model (banking) where "revenue" isn't the unambiguous single number it is for a
normal company. This is a **methodology/definitional difference, not a data quality bug.**

## Decision

**Leave `revenue` as-is for Financial Services companies (banks/NBFCs). Do not swap in a
different yfinance field or build a bank-specific scraper.** Reasons:

1. yfinance itself doesn't expose a clean "Total Income" (Interest + Other Income) field to
   substitute in — only Interest Income, Interest Expense, Net Interest Income, and its own
   already-in-use "Total Revenue," which (per above) is a real, defensible figure, just not
   the same one press releases/screener use.
2. Every bank publishes its "Total Income" in its own PDF format with no uniform API — a
   scraper covering this properly would need per-bank maintenance disproportionate to the
   handful of large banks actually affected, relative to the 2,046-company universe.
3. The definitional gap is bank-specific in *size* (KOTAKBANK/ICICIBANK showed only ~5-10%
   gaps in the original audit, HDFCBANK/SBIN/AXISBANK showed 19-45%) because each bank's
   NII-to-Other-Income mix differs — there's no single correction factor to apply uniformly
   even if a fix were attempted.
4. The 2026-07-20 targeted backfill (see `backfill_log_2026-07-20.csv`) fills *missing*
   revenue values (including for Financial Services companies) using this exact same,
   already-established field and formula — consistent with every already-populated bank
   revenue value in the dataset. A newly-filled value carries the identical caveat as its
   peers; nothing is silently overwritten or guessed.

## What this means practically

- `ebitda_margin_pct` for banks is denominated against this same "Total Revenue" figure, so
  it inherits the same definitional caveat — a bank's margin isn't directly comparable to a
  non-financial company's margin on the same 0-100 scale in the way it would be for two
  industrial companies. This was already true before today; not a new issue introduced here.
- Do not directly compare this dataset's bank `revenue` figures against screener.in,
  macrotrends, or a bank's own press release without accounting for the definitional gap
  described above — they are measuring different things, not disagreeing about the same
  thing.
- If a future contributor wants Financial Services companies to be screened on a figure
  closer to headline "Total Income," that would need a dedicated, documented follow-up
  project (likely a bank-specific data source), not a quick field swap.
