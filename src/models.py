"""
Shared schemas. Every stage of the pipeline passes these objects around
instead of loose dicts, so a typo in a field name fails fast instead of
silently producing an empty Excel column.

Field names match the golden dataset's own columns where possible:
id, query, expected, module.
"""
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional


class TestCase(BaseModel):
    """One row of the golden dataset."""
    id: str
    query: str
    expected: str
    module: Optional[str] = None
    query_audio_path: Optional[str] = None
    is_regression_case: bool = False


class InvocationResult(BaseModel):
    """What the voice bot adapter returns for one test case."""
    test_case_id: str
    response_audio_path: Optional[str] = None
    response_transcript: str
    latency_ms: int
    error: Optional[str] = None     # set if the call failed after retries


class JudgeVote(BaseModel):
    score: int                      # 0-100
    passed: bool
    reason: str


class JudgeResult(BaseModel):
    """Aggregated result after the judge ensemble votes."""
    test_case_id: str
    votes: list[JudgeVote]
    final_score: float              # mean of votes
    final_pass: bool                # majority vote
    reason: str                     # representative reason (first dissenting or majority)


class EvalRow(BaseModel):
    """One fully-scored row for a single test case."""
    id: str
    actual: str
    report: str                     # human-readable verdict: score + pass/fail + reason
    wer: Optional[float] = None
    latency_ms: int
    judge_score: float
    judge_pass: bool
    judge_reason: str
    final_pass: bool
    run_id: str
    timestamp: str
    error: Optional[str] = None
