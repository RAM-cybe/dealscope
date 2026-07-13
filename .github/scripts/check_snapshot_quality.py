"""Quarterly-refresh helper: run src/data/quality_checks.py against a new
snapshot and produce (a) the same flagged-rows report every manual run
produces, and (b) a PR-description fragment + GitHub Actions outputs the
workflow uses to decide how to label the PR.

Never merges or blanks anything itself -- purely read-only reporting, same
"a human reviews and decides" rule as running the checker by hand. See
src/data/quality_checks.py for the actual check definitions/thresholds.

Usage: python .github/scripts/check_snapshot_quality.py <snapshot_csv_path>
"""

import os
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from src.data.loaders import load_companies  # noqa: E402
from src.data.quality_checks import run_all_checks  # noqa: E402

# Only these are genuinely impossible-for-a-real-company range violations,
# zero-tolerance by construction. extreme_ebitda_margin/extreme_roce are
# deliberately excluded -- they can be mathematically real (see
# quality_checks.py's own docstring), so they don't block a snapshot on
# their own; a human still sees them in the full report either way.
CRITICAL_CHECKS = {
    "negative_revenue",
    "negative_total_debt",
    "negative_market_cap",
    "negative_current_ratio",
    "negative_quick_ratio",
}


def main():
    if len(sys.argv) < 2:
        print("Usage: check_snapshot_quality.py <snapshot_csv_path>")
        sys.exit(2)

    snapshot_path = Path(sys.argv[1])
    companies = load_companies(snapshot_path)
    report = run_all_checks(companies)

    critical = report[report["check"].isin(CRITICAL_CHECKS)] if not report.empty else report
    critical_count = len(critical)
    total_count = len(report)

    # Named after the snapshot itself, not just today's date -- a manual
    # quality_checks.py run and this workflow can both produce a report on
    # the same calendar date (e.g. someone spot-checks the live data the
    # same day a scheduled refresh runs), and a shared date-only filename
    # would silently overwrite one with the other.
    out_dir = REPO_ROOT / "data" / "quality_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"flagged_rows_for_{snapshot_path.stem}.csv"
    report.to_csv(report_path, index=False)

    # PR description fragment.
    lines = [f"**Snapshot:** `{snapshot_path.name}` ({len(companies)} companies)", ""]
    if critical_count == 0:
        lines.append(f"No critical range-violation flags. ({total_count} total flag(s), "
                      f"see `{report_path.relative_to(REPO_ROOT)}` -- all either already-reviewed "
                      f"real edge cases or the lower-confidence partial_pull_suspected signal.)")
    else:
        lines.append(f"**NEEDS MANUAL REVIEW BEFORE MERGE -- {critical_count} critical "
                      f"range-violation flag(s) found:**")
        lines.append("")
        for _, row in critical.iterrows():
            lines.append(f"- `{row['symbol']}` ({row['name']}) -- {row['check']}: {row['detail']}")
        lines.append("")
        lines.append(f"Full report ({total_count} flags total): "
                      f"`{report_path.relative_to(REPO_ROOT)}`")

    fragment_path = REPO_ROOT / ".github" / "scripts" / "pr_body_fragment.md"
    fragment_path.write_text("\n".join(lines))

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"critical_count={critical_count}\n")
            f.write(f"total_count={total_count}\n")
            f.write(f"needs_review={'true' if critical_count else 'false'}\n")

    print(f"critical_count={critical_count} total_count={total_count}")
    print(f"Report: {report_path}")
    print(f"PR fragment: {fragment_path}")


if __name__ == "__main__":
    main()
