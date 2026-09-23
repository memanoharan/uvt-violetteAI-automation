"""
Adapter that reads a pre-generated file of "SDK responses" instead of
calling a live voice bot SDK. Use this while the real SDK integration
isn't available yet: hand it a file with one row per test case (matched
by `id`) containing whatever the SDK returned for that query, and the
rest of the pipeline (exact-match check, judge, scorer, report writer)
runs completely unchanged.

Expected columns (case-insensitive; only one of the response aliases is
required):
  - id                                                       (required)
    Must match the golden dataset's `id` column exactly.
  - actual / response / transcript / actual_transcript / sdk_response
    (required, first match wins) -- the SDK's response text to compare
    against the golden `expected` value.
  - latency_ms                                               (optional)
    Defaults to 0 if the column is missing.
  - error                                                     (optional)
    If non-empty for a row, that row is recorded as a failed invocation
    instead of being scored.

Accepts .xlsx or .csv. Rows in the file whose id has no match in the
golden dataset are simply ignored; golden rows with no matching id in
this file come back as an explicit "no SDK output found" error so a
missing row is loud instead of silently skipped.
"""
import pandas as pd
from src.models import TestCase, InvocationResult

ACTUAL_COLUMN_ALIASES = ["actual", "response", "transcript", "actual_transcript", "sdk_response"]


class FileVoiceBotAdapter:
    def __init__(self, path: str):
        self.path = path
        self._by_id = self._load(path)

    def _load(self, path: str) -> dict:
        if path.lower().endswith(".csv"):
            df = pd.read_csv(path, dtype=str)
        else:
            df = pd.read_excel(path, dtype=str)
        df = df.fillna("")
        df.columns = [str(c).strip().lower() for c in df.columns]

        if "id" not in df.columns:
            raise ValueError(f"SDK output file {path} has no 'id' column to match against the golden dataset")

        actual_col = next((c for c in ACTUAL_COLUMN_ALIASES if c in df.columns), None)
        if actual_col is None:
            raise ValueError(
                f"SDK output file {path} needs one of these columns for the response text: "
                f"{ACTUAL_COLUMN_ALIASES}"
            )

        by_id = {}
        for _, row in df.iterrows():
            latency = 0
            if "latency_ms" in df.columns and str(row["latency_ms"]).strip():
                try:
                    latency = int(float(row["latency_ms"]))
                except ValueError:
                    latency = 0
            by_id[str(row["id"])] = {
                "actual": row[actual_col],
                "latency_ms": latency,
                "error": (row.get("error") or None) if "error" in df.columns else None,
            }
        return by_id

    def invoke(self, test_case: TestCase) -> InvocationResult:
        row = self._by_id.get(test_case.id)
        if row is None:
            return InvocationResult(
                test_case_id=test_case.id,
                response_transcript="",
                latency_ms=0,
                error=f"No row with id={test_case.id!r} found in SDK output file {self.path}",
            )
        return InvocationResult(
            test_case_id=test_case.id,
            response_transcript=row["actual"],
            latency_ms=row["latency_ms"],
            error=row["error"] or None,
        )
