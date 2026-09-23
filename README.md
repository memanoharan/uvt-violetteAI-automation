# Voice Bot Eval Platform

Automated evaluation pipeline: golden dataset (Excel) -> voice bot SDK -> judge LLM -> scored report (Excel).

## Folder structure

```
voice_eval/
├── config/
│   └── settings.py          # env-driven config (pydantic-settings)
├── golden_data/
│   └── sample_golden.xlsx   # your query/expected-result test set
├── src/
│   ├── models.py             # TestCase, InvocationResult, JudgeResult, EvalRow schemas
│   ├── data_loader.py        # reads golden Excel -> list[TestCase]
│   ├── adapters/
│   │   ├── base.py           # abstract VoiceBotAdapter interface
│   │   └── mock_adapter.py   # fake adapter for testing the pipeline end-to-end
│   ├── judges/
│   │   ├── base.py           # abstract Judge interface
│   │   └── llm_judge.py      # Claude-based judge, structured JSON output, ensemble voting
│   ├── scorer.py              # WER + latency SLA + judge score -> final pass/fail
│   ├── orchestrator.py        # thread-pool runner, checkpointed to SQLite
│   ├── report_writer.py       # writes results back to Excel
│   └── logger.py              # structured logging setup
├── tests/
│   └── test_scorer.py
├── outputs/                   # generated result Excel files land here
├── logs/                      # run logs
├── .env.example
├── requirements.txt
└── main.py                    # CLI entry point
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in your voice bot SDK creds + judge LLM API key
```

## Run

```bash
python main.py --golden golden_data/sample_golden.xlsx --run-id demo_run_1
```

Golden dataset columns required: `id, query, expected` (`module` is optional but
supported). Any other columns you keep in the golden sheet pass through untouched.

`outputs/demo_run_1_results.xlsx` is created as a **copy of your golden file**
(the master is never opened in write mode) with these columns appended:
`actual_transcript, wer, latency_ms, judge_score, judge_pass, judge_reason,
final_pass, run_id, timestamp, error`.

Checkpoints are written to `outputs/checkpoints.db` (SQLite) as each row completes,
so a crashed run can resume instead of restarting from zero.

## No live SDK yet? Compare a file of SDK output against the golden data

While your real voice bot SDK integration isn't wired up, you don't need to
touch any code to run a comparison: hand the pipeline a file containing
whatever the SDK actually returned for each query, and it gets checked
against the golden `expected` value exactly the same way a live SDK call
would be.

```bash
python main.py --golden golden_data/sample_golden.xlsx \
                --run-id sdk_check_1 \
                --adapter file \
                --sdk-output sdk_output/sample_sdk_output.xlsx
```

Your SDK-output file (`.xlsx` or `.csv`) needs:

- `id` — must match the `id` values in the golden dataset
- one of `actual` / `response` / `transcript` / `actual_transcript` / `sdk_response`
  — the text the SDK returned for that query
- `latency_ms` (optional)
- `error` (optional) — non-empty marks that row as a failed invocation

See `sdk_output/sample_sdk_output.xlsx` for a working example.

**How the comparison works:**

1. Each SDK response is compared to the golden `expected` value, ignoring
   case and extra whitespace.
2. If it's an **exact match**, that row is auto-scored PASS (100/100) and
   the judge is never called — no need to spend an LLM call proving what a
   plain string comparison already proved.
3. If it's **not an exact match**, the judge (LLM judge if `ANTHROPIC_API_KEY`
   is set, otherwise the fallback FuzzyJudge) scores it and decides pass/fail,
   same as any other adapter.

The output report (`outputs/sdk_check_1_results.xlsx`) has one row per test
case with `actual`, `report` (PASS/FAIL + score + reason), `judge_score`,
`judge_pass`, `wer`, and `final_pass` — plus every column from the golden
sheet untouched.

## Real Houndify SDK (live)

The real Houndify SDK is vendored in `vendor/houndify/` (`houndify.py` +
`__init__.py`, patched to use an unverified SSL context -- this environment's
CA bundle fails to validate api.houndify.com's cert chain otherwise) and
wired up as `src/adapters/houndify_adapter.py`. It calls
`houndify.TextHoundClient` once per test case with each golden row's `query`
text, and takes the bot's `WrittenResponse` (falling back to
`SpokenResponse`) as the `actual` value to compare against `expected` --
same exact-match-then-judge flow as every other adapter.

```bash
python main.py --golden golden_data/sample_golden.xlsx --run-id houndify_run_1 --adapter houndify
```

Requires `HOUNDIFY_CLIENT_ID` and `HOUNDIFY_CLIENT_KEY` in `.env` (already
set up). `HOUNDIFY_REQUEST_INFO_PATH` (default
`vendor/houndify/requestInfo.json`) points at the location/context payload
sent with every query; until the real `requestInfo.json` is dropped in there,
the adapter falls back to a placeholder lat/long.

A standalone sanity check that skips the whole pipeline and just prints one
raw response:

```bash
python3 check_houndify_sdk.py "How much does the bike weigh"
```

## Swapping in a different voice bot SDK

For any SDK other than Houndify, implement `src/adapters/base.py::VoiceBotAdapter`
(see `mock_adapter.py` for the shape, or `houndify_adapter.py` for a real
example) and point `main.py` at it via `--adapter`.

## Swapping in your real judge

`src/judges/llm_judge.py` calls the Anthropic API directly. Adjust the model name,
rubric text, and ensemble size (`JUDGE_VOTES` in `.env`) to taste.
