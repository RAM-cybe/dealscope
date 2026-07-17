# Regulation 30 tagging — manual review of high-stakes categories (2026-07-17)

Per the explicit instruction for this round: mislabeling a real company's filing as "fraud" or "insolvency" is a genuine reputational/legal risk on a publicly visible tool, so every instance of the high-stakes categories (Fraud, Insolvency, Litigation / regulatory action, Auditor resignation, Credit rating action, Order win / contract) was manually reviewed before shipping, not sampled.

## Method

Two passes, both required because a live feed can't be reviewed item-by-item forever (see below for why):

1. **Real-data pass.** Fetched all 12 NSE feeds live (`src/data/filings.py:fetch_all_nse_filings()`), 289 real items after the mutual-fund NAV noise filter. Every item in every high-stakes category was read individually.
2. **Synthetic sensitivity pass.** Since a live feed on any given day may genuinely contain zero instances of a rare category (fraud disclosures are, correctly, rare), a real-data pass alone can't prove the classifier actually *works* -- only that it isn't firing falsely today. Ran 8 synthetic test cases modeled on realistic Reg 30 subject-line phrasing (not real company data) through `classify_announcement()` to confirm true positives are still caught.

## Real-data pass: a genuine bug found and fixed, not a clean pass on the first try

The first version of `CATEGORY_KEYWORDS` for "Credit rating action" included bare rating-agency names (`crisil`, `icra`, `care ratings`, `india ratings`). Against real live data, this produced **3 false positives**: mutual-fund NAV-declaration items whose *scheme name* happens to contain "CRISIL" (e.g. "Aditya Birla Sun Life CRISIL Broad Based Gilt ETF" — CRISIL is used here as an index/benchmark name in the product name, not a credit-rating-agency reference). These are not fraud/litigation-tier misses, but they demonstrate exactly the failure mode the task warned about: a keyword that looks safe in isolation can fire on unrelated real content.

Fixed two ways:
- Bare agency names removed from `CATEGORY_KEYWORDS`; only phrases describing an actual rating *action* remain (`"credit rating"`, `"rating upgrad"`, `"rating downgrad"`, `"rating reaffirm"`, `"rating withdraw"`, `"rating agency"`, `"rating action taken"`).
- Mutual-fund NAV declarations (routine daily pricing notices, ~55% of the general Announcements feed by volume, and not corporate disclosures at all) are now filtered out entirely before classification (`_is_mf_nav_noise()`), which also reduces false-positive surface area for every other category, not just credit rating.

Also dropped bare `"liquidation"` from the Insolvency keyword list for the same reason (mutual-fund scheme wind-downs use identical wording to corporate liquidation) -- kept the more specific `"winding up"` / `"winding-up"` / `"cirp"` / `"nclt"` / `"bifr"` / `"insolvency resolution"` / `"corporate insolvency"`.

## Real-data pass results (post-fix)

289 items across 12 feeds, 0 fetch errors. High-stakes category counts on this real batch:

| Category | Count | Reviewed |
|---|---|---|
| Fraud | 0 | n/a -- none present today |
| Insolvency | 0 | n/a -- none present today |
| Litigation / regulatory action | 0 | n/a -- none present today |
| Auditor resignation | 0 | n/a -- none present today |
| Credit rating action | 0 | n/a -- none present today (3 false positives from the pre-fix version, above, were the only hits; all 3 individually confirmed as false and traced to the CRISIL-as-fund-name issue) |
| Order win / contract | 0 | n/a -- none present today |

Zero high-stakes hits on this particular day is expected, not a sign the classifier is broken -- these are genuinely rare events (a company issuing a fraud disclosure or CIRP update happens on the order of once per quarter across the whole exchange, not daily). Feed-sourced categories (Related-party transaction, Corporate action, Voting results, etc.) all populated normally and correctly, since those require no keyword judgment at all -- the category comes from which NSE feed the item was published under.

## Synthetic sensitivity pass (all 8 passed)

Constructed 8 test items with realistic Reg 30 subject-line phrasing (not real company filings) covering all 6 high-stakes categories plus 2 negative controls (a NAV-noise item and a routine AGM-notice item). All 8 classified correctly -- see the test block in this file's git history / session log for the exact cases. This confirms the classifier isn't just silent because it never fires; it correctly identifies genuine phrasing for each category while still declining to fire on adjacent-but-different text (routine AGM notice correctly stayed "General announcement", not "Litigation").

## Ongoing discipline (why this isn't a one-time check)

This module runs on live traffic, re-fetching (on a 30-minute cache) for as long as the app is up -- a human can't review every future item forever. The mitigation is that the classifier is **deterministic and keyword-based, not an AI judgment call**: the same logic verified here today applies unchanged to every future fetch. If NSE's phrasing conventions drift or a new false-positive pattern turns up, it needs the same fix-and-re-verify treatment as the CRISIL issue above, not a one-time sign-off. Any future session touching `src/data/filings.py`'s `CATEGORY_KEYWORDS` should re-run both passes in this file before considering the change safe to ship.
