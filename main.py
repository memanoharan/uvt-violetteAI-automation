"""
Entry point.

    python main.py --golden golden_data/sample_golden.xlsx --run-id demo_run_1

Judge selection is automatic: if ANTHROPIC_API_KEY is set in .env, the
real LLM judge is used. If it's missing/placeholder, this falls back to
a rule-based FuzzyJudge so you can still run and verify the full
pipeline while waiting on a real key. Force one explicitly with --judge.
"""
import argparse
from src.data_loader import load_golden_dataset
from src.adapters.mock_adapter import MockVoiceBotAdapter
from src.adapters.dummy_adapter import DummyVoiceBotAdapter
from src.adapters.file_adapter import FileVoiceBotAdapter
from src.adapters.houndify_adapter import HoundifyVoiceBotAdapter
from src.judges.llm_judge import LLMJudge
from src.judges.fuzzy_judge import FuzzyJudge
from src.orchestrator import run_eval
from src.report_writer import write_report
from src.logger import logger
from config.settings import settings


def _pick_adapter(name: str, sdk_output: str | None, request_info: str | None):
    if name == "mock":
        return MockVoiceBotAdapter()   # always echoes expected verbatim -- proves plumbing only
    if name == "file":
        if not sdk_output:
            raise SystemExit("--adapter file requires --sdk-output <path to your SDK responses file>")
        return FileVoiceBotAdapter(sdk_output)   # reads real SDK output from a file while no live SDK is wired up
    if name == "houndify":
        return HoundifyVoiceBotAdapter(request_info_path=request_info)   # calls the real Houndify SDK live, per test case
    return DummyVoiceBotAdapter()      # realistic mix of correct/drifted/wrong -- exercises scoring


def _pick_judge(forced: str | None):
    have_real_key = bool(settings.anthropic_api_key) and settings.anthropic_api_key != "your_key_here"

    if forced == "llm":
        if not have_real_key:
            raise SystemExit("--judge llm was requested but ANTHROPIC_API_KEY is not set in .env")
        return LLMJudge()
    if forced == "fuzzy":
        return FuzzyJudge()

    # auto: prefer the real judge, fall back to fuzzy with a clear warning
    if have_real_key:
        return LLMJudge()
    logger.warning(
        "ANTHROPIC_API_KEY not set -- using FuzzyJudge (text-similarity only, "
        "not real semantic scoring). Set the key in .env to use the real LLM judge."
    )
    return FuzzyJudge()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", required=True, help="Path to golden dataset Excel file")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--adapter", choices=["dummy", "mock", "file", "houndify"], default="dummy",
        help="'dummy' (default) gives a realistic mix of correct/wrong fake answers. "
             "'mock' always echoes back the expected answer exactly (plumbing test only). "
             "'file' reads real SDK responses from --sdk-output (a file standing in for "
             "the SDK). 'houndify' calls the real Houndify SDK live for every test case "
             "(needs HOUNDIFY_CLIENT_ID / HOUNDIFY_CLIENT_KEY set in .env).",
    )
    parser.add_argument(
        "--sdk-output",
        help="Path to an .xlsx/.csv file with columns 'id' + 'actual' (one row per test case) "
             "containing the SDK's response for each query. Required with --adapter file.",
    )
    parser.add_argument(
        "--request-info",
        help="Path to a requestInfo JSON file for --adapter houndify (e.g. "
             "vendor/houndify/requestInfo_X47.json). This carries DeviceInfo.DeviceModel, "
             "which steers which product the bot answers about -- use the file matching "
             "whatever --golden dataset you're running. Defaults to HOUNDIFY_REQUEST_INFO_PATH "
             "in .env if not given.",
    )
    parser.add_argument(
        "--judge", choices=["auto", "llm", "fuzzy"], default="auto",
        help="Which judge to use. 'auto' (default) uses LLM if a real key is set, else fuzzy.",
    )
    args = parser.parse_args()
    forced = None if args.judge == "auto" else args.judge

    test_cases = load_golden_dataset(args.golden)
    logger.info(f"Loaded {len(test_cases)} test cases from {args.golden}")

    adapter = _pick_adapter(args.adapter, args.sdk_output, args.request_info)  # TODO: swap for your real VoiceBotAdapter once SDK is available
    logger.info(f"Using adapter: {adapter.__class__.__name__}")
    judge = _pick_judge(forced)
    logger.info(f"Using judge: {judge.__class__.__name__}")

    results = run_eval(test_cases, adapter, judge, args.run_id)

    output_path = f"outputs/{args.run_id}_results.xlsx"
    pass_rate = write_report(results, args.golden, output_path)

    logger.info(f"Done. Pass rate: {pass_rate:.1f}%. Report: {output_path}")


if __name__ == "__main__":
    main()
