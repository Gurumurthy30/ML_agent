"""
tests/test_streaming.py — Token-level Streaming Tests
"""

import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessageChunk
from agents.utils import call_llm_stream, _invoke_provider_stream


def test_call_llm_stream_dry_run_callbacks():
    """Verify that dry_run mode in call_llm_stream emits start, delta, and end events for both thinking and text."""
    thinking_starts = []
    thinking_deltas = []
    thinking_ends = []
    text_starts = []
    text_deltas = []
    text_ends = []

    resp, has_thinking = call_llm_stream(
        system_prompt="You are a helper.",
        user_prompt="Hello world",
        role="planner_deep",
        dry_run=True,
        on_thinking_start=lambda: thinking_starts.append(True),
        on_thinking_delta=lambda d: thinking_deltas.append(d),
        on_thinking_end=lambda: thinking_ends.append(True),
        on_text_start=lambda: text_starts.append(True),
        on_text_delta=lambda d: text_deltas.append(d),
        on_text_end=lambda: text_ends.append(True),
    )

    assert len(thinking_starts) == 1
    assert len(thinking_ends) == 1
    assert len(thinking_deltas) > 0
    assert len(text_starts) == 1
    assert len(text_ends) == 1
    assert len(text_deltas) > 0
    assert resp.startswith("{") or "{" in resp


def test_invoke_provider_stream_think_tags():
    """Verify that _invoke_provider_stream cleanly separates <think>...</think> into thinking and text callbacks."""
    mock_llm = MagicMock()
    chunks = [
        AIMessageChunk(content="<think>Step 1: check data\n"),
        AIMessageChunk(content="Step 2: build pipeline</think>Here is the final code: print('done')"),
    ]
    mock_llm.stream.return_value = iter(chunks)

    thinking_chunks = []
    text_chunks = []

    text_res, has_thinking = _invoke_provider_stream(
        mock_llm,
        system_prompt="system",
        user_prompt="test",
        on_thinking_delta=lambda d: thinking_chunks.append(d),
        on_text_delta=lambda d: text_chunks.append(d),
    )

    full_thinking = "".join(thinking_chunks)
    full_text = "".join(text_chunks)

    assert has_thinking is True
    assert "Step 1: check data" in full_thinking
    assert "Step 2: build pipeline" in full_thinking
    assert "<think>" not in full_thinking
    assert "</think>" not in full_thinking

    assert "Here is the final code: print('done')" in full_text
    assert "<think>" not in full_text
    assert "</think>" not in full_text
    assert text_res == full_text


def test_invoke_provider_stream_native_reasoning():
    """Verify that _invoke_provider_stream parses native Groq reasoning_content."""
    mock_llm = MagicMock()
    chunks = [
        AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Pondering problem..."}),
        AIMessageChunk(content="", additional_kwargs={"reasoning_content": " Found solution."}),
        AIMessageChunk(content="Here is the solution.", additional_kwargs={}),
    ]
    mock_llm.stream.return_value = iter(chunks)

    thinking_chunks = []
    text_chunks = []

    text_res, has_thinking = _invoke_provider_stream(
        mock_llm,
        system_prompt="system",
        user_prompt="test",
        on_thinking_delta=lambda d: thinking_chunks.append(d),
        on_text_delta=lambda d: text_chunks.append(d),
    )

    full_thinking = "".join(thinking_chunks)
    full_text = "".join(text_chunks)

    assert has_thinking is True
    assert full_thinking == "Pondering problem... Found solution."
    assert full_text == "Here is the solution."
    assert text_res == full_text
