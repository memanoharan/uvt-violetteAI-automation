"""
Real Houndify SDK adapter. Sends each test case's `query` text through
Houndify's TextHoundClient (vendor/houndify/houndify.py, using the SSL-fixed
copy) and returns the bot's actual response for comparison against the
golden `expected` value -- same interface as every other adapter, so
main.py just swaps `--adapter houndify` in.

Response shape (from a live call):
  response["Status"] == "OK" on success
  response["AllResults"][0]["WrittenResponse"] / ["SpokenResponse"] -- the
  bot's natural-language answer; these are usually identical, WrittenResponse
  is preferred since it's what's meant to be read/compared as text.
"""
import sys
import os
import time
import json

_HOUNDIFY_SDK_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "vendor", "houndify",
)
if _HOUNDIFY_SDK_DIR not in sys.path:
    sys.path.insert(0, _HOUNDIFY_SDK_DIR)

import houndify  # noqa: E402  (must come after sys.path insert)

from src.models import TestCase, InvocationResult  # noqa: E402
from config.settings import settings  # noqa: E402


def _load_request_info(path: str | None) -> dict:
    path = path or settings.houndify_request_info_path
    if path and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    # Fallback placeholder if no requestInfo file is found at all -- swap
    # in a real one (which should include DeviceInfo.DeviceModel so the
    # bot answers about the right product) and pass its path in.
    return {"Latitude": 12.9716, "Longitude": 77.5946}


class HoundifyVoiceBotAdapter:
    def __init__(self, request_info_path: str | None = None):
        if not settings.houndify_client_id or not settings.houndify_client_key:
            raise RuntimeError(
                "HOUNDIFY_CLIENT_ID / HOUNDIFY_CLIENT_KEY are not set in .env"
            )
        self.client_id = settings.houndify_client_id
        self.client_key = settings.houndify_client_key
        self.request_info = _load_request_info(request_info_path)
        # DeviceInfo.DeviceModel (when present) steers which product's
        # knowledge the bot answers from -- surfaced here so a mismatched
        # or missing requestInfo is obvious in the logs, not just in results.
        device_model = (self.request_info.get("DeviceInfo") or {}).get("DeviceModel")
        print(f"[HoundifyVoiceBotAdapter] requestInfo DeviceInfo.DeviceModel = {device_model!r}"
              f" (from {request_info_path or settings.houndify_request_info_path})")

    def invoke(self, test_case: TestCase) -> InvocationResult:
        # The SDK signs the Hound-Request-Authentication header with the
        # userID passed into the constructor, but also sends whatever
        # "UserID" is in requestInfo as part of the request body -- the
        # server rejects the call if those two don't match. So the userID
        # here MUST come from requestInfo itself, not be hardcoded.
        user_id = self.request_info.get("UserID") or "test_user"

        # A fresh client per call -- TextHoundClient.query() opens its own
        # connection locally rather than reusing shared state, so this is
        # safe to call concurrently from the orchestrator's thread pool.
        client = houndify.TextHoundClient(
            self.client_id, self.client_key, user_id, self.request_info,
        )

        start = time.time()
        try:
            response = client.query(test_case.query)
        except Exception as e:
            return InvocationResult(
                test_case_id=test_case.id,
                response_transcript="",
                latency_ms=int((time.time() - start) * 1000),
                error=f"{type(e).__name__}: {e}",
            )
        latency_ms = int((time.time() - start) * 1000)

        if response.get("Status") != "OK":
            return InvocationResult(
                test_case_id=test_case.id,
                response_transcript="",
                latency_ms=latency_ms,
                error=f"Houndify returned Status={response.get('Status')!r}: "
                      f"{json.dumps(response, ensure_ascii=False)[:300]}",
            )

        results = response.get("AllResults") or []
        if not results:
            return InvocationResult(
                test_case_id=test_case.id,
                response_transcript="",
                latency_ms=latency_ms,
                error="Houndify returned no AllResults for this query",
            )

        top = results[0]
        transcript = top.get("WrittenResponse") or top.get("SpokenResponse") or ""

        return InvocationResult(
            test_case_id=test_case.id,
            response_transcript=transcript,
            latency_ms=latency_ms,
        )
