"""
Generates a realistic MIX of fake voice bot responses -- not just an exact
echo of `expected` like MockVoiceBotAdapter does. Roughly:
  - 50% exact match           (should PASS)
  - 30% minor wording drift    (should mostly PASS, WER > 0)
  - 20% wrong/off-topic        (should FAIL)

Use this instead of MockVoiceBotAdapter when you actually want to see
your scorer/judge correctly catch failures, not just prove the pipeline
runs. Same interface (invoke() -> InvocationResult), so swapping between
adapters in main.py is a one-line change either way.
"""
import random
import time
from src.models import TestCase, InvocationResult

WRONG_ANSWERS = [
    "I'm sorry, I didn't understand that. Could you rephrase?",
    "Let me transfer you to a human agent for that.",
    "I don't have information on that right now.",
    "Sorry, could you say that again?",
]


def _mutate(text: str) -> str:
    """Light wording drift: drop a word, swap two words, or add a filler."""
    words = text.split()
    if len(words) <= 4:
        return text
    action = random.choice(["drop", "swap", "filler"])
    if action == "drop":
        del words[random.randrange(len(words))]
    elif action == "swap":
        i, j = random.sample(range(len(words)), 2)
        words[i], words[j] = words[j], words[i]
    elif action == "filler":
        words.insert(0, random.choice(["Um,", "So,", "Well,"]))
    return " ".join(words)


class DummyVoiceBotAdapter:
    def invoke(self, test_case: TestCase) -> InvocationResult:
        start = time.time()
        time.sleep(random.uniform(0.05, 0.2))  # simulate network latency
        latency_ms = int((time.time() - start) * 1000)

        roll = random.random()
        if roll < 0.5:
            transcript = test_case.expected                     # exact
        elif roll < 0.8:
            transcript = _mutate(test_case.expected)             # slightly off
        else:
            transcript = random.choice(WRONG_ANSWERS)            # wrong

        return InvocationResult(
            test_case_id=test_case.id,
            response_transcript=transcript,
            latency_ms=latency_ms,
        )
