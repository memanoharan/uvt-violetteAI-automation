"""
Judge LLM wrapper. Calls the judge N times (JUDGE_VOTES) and takes a
majority vote + mean score, instead of trusting a single call — LLM
judges have real variance and a single call gives false confidence.
"""
import json
from anthropic import Anthropic
from src.models import JudgeVote, JudgeResult
from config.settings import settings

RUBRIC = """You are grading a voice assistant's spoken response.

Query: {query}
Expected result: {expected}
Actual response (transcribed): {actual}

Score 0-100 on how well the actual response satisfies the expected result:
- 90-100: fully correct, natural for speech
- 70-89: correct meaning, minor phrasing/formatting issues
- 40-69: partially correct or missing key information
- 0-39: wrong, off-topic, or unusable as a spoken response

Also flag anything unsuitable for speech (e.g. reads out markdown, numbered
lists, overly long response) as a deduction even if the meaning is right.

Respond ONLY with JSON, no other text:
{{"score": <int 0-100>, "pass": <true|false>, "reason": "<one sentence>"}}
"""


class LLMJudge:
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)

    def _single_vote(self, query: str, expected: str, actual: str) -> JudgeVote:
        prompt = RUBRIC.format(query=query, expected=expected, actual=actual)
        resp = self.client.messages.create(
            model=settings.judge_model,
            max_tokens=300,
            temperature=settings.judge_temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        data = json.loads(raw)
        return JudgeVote(score=data["score"], passed=data["pass"], reason=data["reason"])

    def evaluate(self, query: str, expected: str, actual: str) -> JudgeResult:
        votes = [self._single_vote(query, expected, actual) for _ in range(settings.judge_votes)]

        final_score = sum(v.score for v in votes) / len(votes)
        pass_votes = sum(1 for v in votes if v.passed)
        final_pass = pass_votes > len(votes) / 2

        # surface a dissenting reason if the vote wasn't unanimous, else the first reason
        reasons = [v.reason for v in votes]
        reason = reasons[0] if len(set(v.passed for v in votes)) == 1 else " | ".join(reasons)

        return JudgeResult(
            test_case_id="",  # filled in by caller
            votes=votes,
            final_score=final_score,
            final_pass=final_pass,
            reason=reason,
        )
