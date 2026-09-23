"""
Rule-based judge used to test the FULL pipeline before an Anthropic API
key is available. Same evaluate() interface as LLMJudge (src/judges/llm_judge.py),
so orchestrator.py, main.py and report_writer.py don't need to know or
care which judge is plugged in.

This is NOT a real evaluator -- it only measures raw text similarity, so
it can't tell "correct but differently worded" apart from "wrong". It's
strictly for verifying the pipeline (loading, invoking, scoring, writing
the report) works end to end while you wait on the real key. Swap to
LLMJudge in main.py the moment you have one.
"""
import difflib
from src.models import JudgeResult, JudgeVote
from config.settings import settings


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


class FuzzyJudge:
    def evaluate(self, query: str, expected: str, actual: str) -> JudgeResult:
        ratio = difflib.SequenceMatcher(None, _normalize(expected), _normalize(actual)).ratio()
        score = round(ratio * 100)
        passed = score >= settings.pass_score_threshold

        reason = (
            f"[FUZZY JUDGE - not the real judge] text similarity {score}/100 "
            f"(pass threshold {settings.pass_score_threshold}). Re-run with the LLM "
            f"judge once ANTHROPIC_API_KEY is set for real semantic scoring."
        )

        vote = JudgeVote(score=score, passed=passed, reason=reason)
        return JudgeResult(
            test_case_id="",
            votes=[vote],
            final_score=score,
            final_pass=passed,
            reason=reason,
        )
