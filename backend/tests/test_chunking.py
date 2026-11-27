import re
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.chunking import chunk_text


def _normalize_whitespace(value: str) -> str:
    """Collapse runs of whitespace (spaces, tabs, newlines) into single spaces."""
    return re.sub(r"\s+", " ", value).strip()


def _assert_all_chunks_valid(chunks: list[str], max_chars: int) -> None:
    """Assert every chunk is non-empty and respects max_chars."""
    assert all(isinstance(c, str) and len(c.strip()) > 0 for c in chunks)
    assert all(len(c) <= max_chars for c in chunks)


def test_empty_input_returns_no_chunks():
    assert chunk_text("", max_chars=100) == []


@pytest.mark.parametrize("blank_text", ["   ", "\n\n\t  ", "\r\n\r\n"])
def test_whitespace_only_input_returns_no_chunks(blank_text: str):
    assert chunk_text(blank_text, max_chars=100) == []


def test_input_smaller_than_budget_returns_one_chunk():
    text = "Short note for summarization."
    chunks = chunk_text(text, max_chars=200)

    assert len(chunks) == 1
    assert chunks == [text]
    _assert_all_chunks_valid(chunks, max_chars=200)


def test_input_exactly_at_budget_returns_one_chunk():
    text = "x" * 50
    assert len(text) == 50

    chunks = chunk_text(text, max_chars=50)
    assert len(chunks) == 1
    assert chunks == [text]
    _assert_all_chunks_valid(chunks, max_chars=50)


def test_several_short_paragraphs_combined_when_possible():
    text = "Alpha one.\n\nBeta two.\n\nGamma three."
    # Total length with "\n\n" joiners is 10 + 2 + 9 + 2 + 13 = 36 chars.
    chunks = chunk_text(text, max_chars=50)

    assert len(chunks) == 1
    assert chunks[0] == text
    _assert_all_chunks_valid(chunks, max_chars=50)
    assert _normalize_whitespace(" ".join(chunks)) == _normalize_whitespace(text)


def test_paragraphs_exceeding_combined_budget_produce_multiple_chunks():
    p1 = "First paragraph about async I/O."  # 33 chars
    p2 = "Second paragraph about schema checks."  # 37 chars
    p3 = "Third paragraph about clean error mapping."  # 43 chars
    text = f"{p1}\n\n{p2}\n\n{p3}"

    # p1 + "\n\n" + p2 = 72 chars (> 70), so p1 and p2 split into separate chunks.
    chunks = chunk_text(text, max_chars=70)

    assert len(chunks) >= 2
    _assert_all_chunks_valid(chunks, max_chars=70)
    assert _normalize_whitespace(" ".join(chunks)) == _normalize_whitespace(text)


def test_oversized_paragraph_is_split_into_multiple_chunks():
    oversized = (
        "FastAPI handles async endpoints efficiently while Pydantic v2 validates "
        "request and response models strictly before route handlers execute."
    )
    chunks = chunk_text(oversized, max_chars=55)

    assert len(chunks) > 1
    _assert_all_chunks_valid(chunks, max_chars=55)
    # Verify exact word sequence is preserved without dropping or duplicating words
    assert _normalize_whitespace(" ".join(chunks)).split(" ") == oversized.split(" ")


def test_single_extremely_long_word_respects_hard_limit():
    long_token = "A" * 135
    chunks = chunk_text(long_token, max_chars=40)

    assert len(chunks) == 4  # 40 + 40 + 40 + 15 = 135
    _assert_all_chunks_valid(chunks, max_chars=40)
    assert "".join(chunks) == long_token


def test_content_preservation_across_mixed_paragraphs_and_splits():
    text = (
        "Intro sentence.\n\n"
        + (
            "Detailed middle section with multiple words that will exceed the chunk limit " * 3
        ).strip()
        + "\n\nClosing remark."
    )
    max_chars = 65
    chunks = chunk_text(text, max_chars=max_chars)

    assert len(chunks) >= 3
    _assert_all_chunks_valid(chunks, max_chars=max_chars)

    reconstructed_tokens = _normalize_whitespace(" ".join(chunks)).split(" ")
    original_tokens = _normalize_whitespace(text).split(" ")
    assert reconstructed_tokens == original_tokens


def test_chunk_text_is_deterministic():
    text = (
        "Paragraph one has important details.\n\n"
        "Paragraph two is somewhat longer so it tests boundary splitting behavior across runs.\n\n"
        "Paragraph three wraps up the document."
    )
    first_run = chunk_text(text, max_chars=55)
    second_run = chunk_text(text, max_chars=55)

    assert first_run == second_run
    _assert_all_chunks_valid(first_run, max_chars=55)


@pytest.mark.parametrize("invalid_budget", [0, -1, -100])
def test_invalid_budget_raises_value_error(invalid_budget: int):
    with pytest.raises(ValueError):
        chunk_text("Some non-empty text.", max_chars=invalid_budget)
