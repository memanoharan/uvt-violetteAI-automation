"""
Fake voice bot for exercising the pipeline end-to-end without real
credentials. Swap for a real adapter (e.g. voicebot_adapter.py calling
your actual SDK) once this scaffold runs cleanly.
"""
import random
import time
from src.models import TestCase, InvocationResult


class MockVoiceBotAdapter:
    def invoke(self, test_case: TestCase) -> InvocationResult:
        start = time.time()
        time.sleep(random.uniform(0.05, 0.2))  # simulate network latency
        latency_ms = int((time.time() - start) * 1000)

        # Pretend the bot echoes back a slightly noisy version of expected
        transcript = test_case.expected
        return InvocationResult(
            test_case_id=test_case.id,
            response_transcript=transcript,
            latency_ms=latency_ms,
        )
