"""
Abstract interface for a voice bot integration. Implement this once per
bot/provider. The orchestrator only ever talks to this interface, so
swapping bots or testing two versions side-by-side means swapping the
adapter, not touching the pipeline.
"""
from abc import ABC, abstractmethod
from src.models import TestCase, InvocationResult


class VoiceBotAdapter(ABC):
    @abstractmethod
    def invoke(self, test_case: TestCase) -> InvocationResult:
        """
        Send the test case's query (audio or synthesized from query_text)
        to the voice bot and return its spoken response transcript + timing.
        Must not raise on ordinary API failures — catch them and set
        InvocationResult.error instead, so one bad row doesn't kill a run.
        """
        raise NotImplementedError
