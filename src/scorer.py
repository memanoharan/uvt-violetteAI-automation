"""
Deterministic metrics live here, separate from the LLM judge, so a
regression is easy to explain: "WER spiked" is a different bug than
"judge score dropped".
"""
from jiwer import wer
from config.settings import settings


def compute_wer(expected: str, actual: str) -> float:
    if not expected.strip():
        return 0.0
    return round(wer(expected, actual), 4)


def latency_within_sla(latency_ms: int) -> bool:
    return latency_ms <= settings.latency_sla_ms


def final_pass(judge_score: float, judge_pass: bool, latency_ms: int) -> bool:
    """
    Documented combination rule — change this in one place, not scattered
    across the pipeline. Currently: judge must pass AND score above
    threshold AND latency within SLA.
    """
    return (
        judge_pass
        and judge_score >= settings.pass_score_threshold
        and latency_within_sla(latency_ms)
    )

def _normalize_for_match(text: str) -> str:
    return " ".join(text.strip().lower().split())


def is_exact_match(expected: str, actual: str) -> bool:
    """
    True when actual matches the golden 'expected' value once whitespace
    and case differences are ignored. Used to skip the (slower, costlier)
    judge call entirely for rows that already agree with the golden data
    -- only rows that DON'T match exactly need the judge to decide pass/fail.
    """
    return _normalize_for_match(expected) == _normalize_for_match(actual)

