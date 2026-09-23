"""
Reads a golden dataset Excel file into a list of TestCase objects.

Real golden sheets don't all use the same column names (a hand-built demo
sheet uses id/query/expected/module; a real question bank exported from a
product team might use ID/Question/"Answer (voice-ready)"/Category instead)
and may have extra sheets (a "Category Index" summary tab alongside the
actual Q&A data). This loader copes with both:

  - Column names are matched case-insensitively against a small alias list
    per field, so "Question" and "query" both work.
  - If the workbook has multiple sheets, each is checked in order and the
    first one containing recognizable id/query/expected columns is used
    (a metadata-only sheet like "Category Index" is skipped automatically).

Kept strict on the things that matter: fails loudly if no sheet has the
required columns, rather than silently producing NaNs that surface as bugs
three stages later.
"""
import pandas as pd
from src.models import TestCase

ID_ALIASES = ["id"]
QUERY_ALIASES = ["query", "question"]
EXPECTED_ALIASES = ["expected", "answer (voice-ready)", "answer"]
MODULE_ALIASES = ["module", "category"]


def _find_column(columns: list[str], aliases: list[str]) -> str | None:
    lower_to_actual = {str(c).strip().lower(): c for c in columns}
    for alias in aliases:
        if alias in lower_to_actual:
            return lower_to_actual[alias]
    return None


def _load_matching_sheet(path: str) -> tuple[pd.DataFrame, str, str, str, str | None]:
    xls = pd.ExcelFile(path)
    checked = []
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet_name, dtype=str)
        id_col = _find_column(df.columns, ID_ALIASES)
        query_col = _find_column(df.columns, QUERY_ALIASES)
        expected_col = _find_column(df.columns, EXPECTED_ALIASES)
        if id_col and query_col and expected_col:
            module_col = _find_column(df.columns, MODULE_ALIASES)
            return df, id_col, query_col, expected_col, module_col
        checked.append(sheet_name)

    raise ValueError(
        f"Golden dataset {path} has no sheet with recognizable id/query/expected "
        f"columns (checked sheet(s): {checked}). Expected column names like "
        f"id/ID, query/Question, expected/'Answer (voice-ready)'/Answer."
    )


def load_golden_dataset(path: str) -> list[TestCase]:
    df, id_col, query_col, expected_col, module_col = _load_matching_sheet(path)
    df = df.fillna("")

    cases = []
    for _, row in df.iterrows():
        row_id = str(row[id_col]).strip()
        if not row_id:
            continue  # skip blank/spacer rows
        cases.append(
            TestCase(
                id=row_id,
                query=row[query_col],
                expected=row[expected_col],
                module=(row[module_col] if module_col else "") or None,
                query_audio_path=row.get("query_audio_path") or None,
                is_regression_case=str(row.get("is_regression_case", "")).lower() == "true",
            )
        )
    return cases
