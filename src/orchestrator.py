"""
Ties data_loader -> adapter -> scorer -> judge together. Uses a thread
pool for concurrency (voice bot + judge calls are I/O bound) and writes
each row's result to SQLite the moment it completes, so a crashed run
resumes instead of restarting from zero.
"""
import sqlite3
import json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import TestCase, EvalRow, JudgeResult
from src.scorer import compute_wer, final_pass, is_exact_match
from src.logger import logger
from config.settings import settings

CHECKPOINT_DB = "outputs/checkpoints.db"


def _init_checkpoint_db():
    conn = sqlite3.connect(CHECKPOINT_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS results (
            run_id TEXT, test_case_id TEXT, payload TEXT,
            PRIMARY KEY (run_id, test_case_id)
        )
    """)
    conn.commit()
    return conn


def _already_done(conn, run_id: str, test_case_id: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM results WHERE run_id=? AND test_case_id=?", (run_id, test_case_id)
    )
    return cur.fetchone() is not None


def _save_checkpoint(conn, run_id: str, row: EvalRow):
    conn.execute(
        "INSERT OR REPLACE INTO results VALUES (?, ?, ?)",
        (run_id, row.id, row.model_dump_json()),
    )
    conn.commit()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _invoke_with_retry(adapter, test_case: TestCase):
    return adapter.invoke(test_case)


def _process_one(test_case: TestCase, adapter, judge, run_id: str) -> EvalRow:
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        invocation = _invoke_with_retry(adapter, test_case)
        if invocation.error:
            raise RuntimeError(invocation.error)

        if is_exact_match(test_case.expected, invocation.response_transcript):
            # Already agrees with the golden data verbatim (ignoring case/
            # whitespace) -- no need to spend a judge call on it.
            judge_result = JudgeResult(
                test_case_id=test_case.id,
                votes=[],
                final_score=100.0,
                final_pass=True,
                reason="Exact match with golden 'expected' value -- judge not called.",
            )
        else:
            judge_result = judge.evaluate(
                query=test_case.query,
                expected=test_case.expected,
                actual=invocation.response_transcript,
            )
        wer_score = compute_wer(test_case.expected, invocation.response_transcript)
        passed = final_pass(judge_result.final_score, judge_result.final_pass, invocation.latency_ms)
        verdict = "PASS" if passed else "FAIL"
        report = f"{verdict} ({judge_result.final_score:.0f}/100) - {judge_result.reason}"

        return EvalRow(
            id=test_case.id,
            actual=invocation.response_transcript,
            report=report,
            wer=wer_score,
            latency_ms=invocation.latency_ms,
            judge_score=judge_result.final_score,
            judge_pass=judge_result.final_pass,
            judge_reason=judge_result.reason,
            final_pass=passed,
            run_id=run_id,
            timestamp=timestamp,
        )
    except Exception as e:
        logger.error(f"Row {test_case.id} failed: {e}")
        return EvalRow(
            id=test_case.id,
            actual="",
            report=f"ERROR - {e}",
            latency_ms=0,
            judge_score=0,
            judge_pass=False,
            judge_reason="",
            final_pass=False,
            run_id=run_id,
            timestamp=timestamp,
            error=str(e),
        )


def run_eval(test_cases: list[TestCase], adapter, judge, run_id: str) -> list[EvalRow]:
    conn = _init_checkpoint_db()
    results: list[EvalRow] = []
    pending = [tc for tc in test_cases if not _already_done(conn, run_id, tc.id)]
    logger.info(f"Run {run_id}: {len(pending)} pending, {len(test_cases) - len(pending)} resumed from checkpoint")

    with ThreadPoolExecutor(max_workers=settings.max_concurrent_workers) as pool:
        futures = {pool.submit(_process_one, tc, adapter, judge, run_id): tc for tc in pending}
        for future in as_completed(futures):
            row = future.result()
            tc = futures[future]
            _save_checkpoint(conn, run_id, row)
            results.append(row)
            q_short = (tc.query[:70] + "...") if len(tc.query) > 70 else tc.query
            a_short = (row.actual[:90] + "...") if len(row.actual) > 90 else row.actual
            logger.info(
                f"[{row.id}] pass={row.final_pass} score={row.judge_score} "
                f"| Q: {q_short!r} | A: {a_short!r}"
            )

    # merge in previously-completed rows from checkpoint for a full report
    for tc in test_cases:
        if tc.id not in {r.id for r in results}:
            cur = conn.execute(
                "SELECT payload FROM results WHERE run_id=? AND test_case_id=?", (run_id, tc.id)
            )
            row = cur.fetchone()
            if row:
                results.append(EvalRow(**json.loads(row[0])))

    conn.close()
    return results
