"""Gemini provider retry policy — one retry with backoff on timeout/5xx/429, then a clear error."""

import pytest

import llm.providers.gemini as gemini_module
from llm.providers.gemini import GeminiProvider, _is_retryable


class _FakeStatusError(Exception):
    def __init__(self, code: int):
        super().__init__(f"status {code}")
        self.code = code


class _FakeResponse:
    text = '{"ok": true}'
    parsed = None

    class usage_metadata:
        prompt_token_count = 10
        candidates_token_count = 5
        thoughts_token_count = 0


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(gemini_module.time, "sleep", lambda _s: None)
    return GeminiProvider(api_key="unit-test-key", model="gemini-2.5-pro")


def test_is_retryable_classification():
    assert _is_retryable(_FakeStatusError(429)) is True
    assert _is_retryable(_FakeStatusError(500)) is True
    assert _is_retryable(_FakeStatusError(503)) is True
    assert _is_retryable(TimeoutError("deadline")) is True
    assert _is_retryable(_FakeStatusError(400)) is False
    assert _is_retryable(ValueError("not http at all")) is False


def test_retryable_failure_is_retried_once_then_succeeds(provider, monkeypatch):
    attempts: list[int] = []

    def flaky(prompt, *, system, schema, temperature):
        attempts.append(1)
        if len(attempts) == 1:
            raise _FakeStatusError(503)
        return _FakeResponse()

    monkeypatch.setattr(provider, "_generate_once", flaky)
    result = provider.generate("hello")
    assert len(attempts) == 2
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.latency_ms >= 0


def test_second_retryable_failure_raises_clear_error(provider, monkeypatch):
    def always_down(prompt, *, system, schema, temperature):
        raise _FakeStatusError(500)

    monkeypatch.setattr(provider, "_generate_once", always_down)
    with pytest.raises(RuntimeError, match="failed twice"):
        provider.generate("hello")


def test_non_retryable_failure_raises_immediately(provider, monkeypatch):
    attempts: list[int] = []

    def bad_request(prompt, *, system, schema, temperature):
        attempts.append(1)
        raise _FakeStatusError(400)

    monkeypatch.setattr(provider, "_generate_once", bad_request)
    with pytest.raises(_FakeStatusError):
        provider.generate("hello")
    assert len(attempts) == 1
