"""
Pretty-prints an existing results .xlsx (from main.py / report_writer.py) as
a readable Query -> Expected vs Actual transcript, one block per row --
built for walking stakeholders through what the bot actually said, without
re-running the eval (no extra API calls).

Usage:
    python3 show_qa.py outputs/f77_full2_results.xlsx
    python3 show_qa.py outputs/f77_full2_results.xlsx --only-fail
    python3 show_qa.py outputs/f77_full2_results.xlsx --contains "charge in the rain"
    python3 show_qa.py outputs/f77_full2_results.xlsx --limit 20
"""
import argparse
import sys

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results_path", help="Path to a *_results.xlsx file")
    parser.add_argument("--only-fail", action="store_true",
                         help="Show only rows where final_pass is False")
    parser.add_argument("--contains", default=None,
                         help="Only show rows whose query or expected contains this text (case-insensitive)")
    parser.add_argument("--limit", type=int, default=None,
                         help="Show at most this many rows")
    args = parser.parse_args()

    df = pd.read_excel(args.results_path)

    missing = [c for c in ("query", "expected", "actual") if c not in df.columns]
    if missing:
        print(f"ERROR: {args.results_path} is missing expected column(s): {missing}. "
              f"Columns found: {list(df.columns)}", file=sys.stderr)
        sys.exit(1)

    if args.only_fail and "final_pass" in df.columns:
        df = df[df["final_pass"] == False]  # noqa: E712

    if args.contains:
        needle = args.contains.lower()
        mask = df["query"].astype(str).str.lower().str.contains(needle) | \
               df["expected"].astype(str).str.lower().str.contains(needle)
        df = df[mask]

    if args.limit:
        df = df.head(args.limit)

    print(f"\n{len(df)} row(s) from {args.results_path}\n" + "=" * 70)

    for _, row in df.iterrows():
        rid = row.get("id", "?")
        module = row.get("module", "")
        score = row.get("judge_score", "")
        passed = row.get("final_pass", "")
        print(f"\n[{rid}] {module}  (score={score}, pass={passed})")
        print(f"  Q:        {row['query']}")
        print(f"  Expected: {row['expected']}")
        print(f"  Actual:   {row['actual']}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
