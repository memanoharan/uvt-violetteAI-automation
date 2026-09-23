from src.scorer import compute_wer, final_pass, is_exact_match


def test_wer_identical_strings_is_zero():
    assert compute_wer("hello world", "hello world") == 0.0


def test_wer_detects_difference():
    assert compute_wer("hello world", "hello there") > 0.0


def test_final_pass_requires_all_conditions():
    assert final_pass(judge_score=90, judge_pass=True, latency_ms=1000) is True
    assert final_pass(judge_score=50, judge_pass=True, latency_ms=1000) is False
    assert final_pass(judge_score=90, judge_pass=False, latency_ms=1000) is False
    assert final_pass(judge_score=90, judge_pass=True, latency_ms=99999) is False

def test_is_exact_match_ignores_case_and_whitespace():
    assert is_exact_match("Hello  World", "hello world") is True
    assert is_exact_match("  Hello World  ", "Hello World") is True


def test_is_exact_match_detects_real_difference():
    assert is_exact_match("Hello World", "Goodbye World") is False

