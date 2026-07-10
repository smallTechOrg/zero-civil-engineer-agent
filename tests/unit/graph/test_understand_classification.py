"""Deterministic guards for the `understand` component-classification contract.

These pin the CODE-vs-SPEC fixes without hitting the real LLM: the classifier
seam (`graph.nodes.LLMClient`) is patched to return a controlled
`UnderstandResult`, so we assert the *dispatch decision* logic:

- an explicit picker choice ALWAYS wins (bypasses classification);
- a resolved classification is honoured;
- an in-scope request the classifier could NOT resolve (component_type=None) is
  NEVER silently defaulted to the culvert — it fails transparently
  (component-registry.md: classify is "1 retry, then fatal (transparent error)").

The real-LLM discriminator (RW prompt vs culvert prompt) lives in the
integration suite (`tests/integration/test_component_classification.py`).
"""

import time
from uuid import uuid4

import pytest

from graph.nodes import UnderstandResult, understand
from graph.persistence import create_run_row
from graph.steps import initial_steps
from observability import progress


class _FakeResult:
    def __init__(self, parsed):
        self.parsed = parsed
        self.text = ""
        self.prompt_tokens = 10
        self.completion_tokens = 5
        self.latency_ms = 1


class _FakeLLM:
    """Stands in for LLMClient — returns a fixed UnderstandResult, no network."""

    _parsed = None

    def generate(self, *args, **kwargs):
        return _FakeResult(self._parsed)


@pytest.fixture
def base_state():
    session_id = "unit-understand-session"
    run_id = create_run_row(session_id, "some prompt")
    progress.register(run_id)
    return {
        "run_id": run_id,
        "session_id": session_id,
        "user_prompt": "some prompt",
        "component_type": "box_culvert",  # runner-seeded default
        "requested_component": None,
        "messages": [],
        "token_usage": [],
        "steps": initial_steps(),
        "started_monotonic": time.monotonic(),
    }


def _patch_llm(monkeypatch, parsed):
    fake = type("_LLM", (_FakeLLM,), {"_parsed": parsed})
    monkeypatch.setattr("graph.nodes.LLMClient", fake)


def test_unresolved_classification_fails_transparently_not_a_silent_culvert(
    monkeypatch, base_state
):
    """In scope but component_type=None must NOT default to box_culvert."""
    _patch_llm(
        monkeypatch,
        UnderstandResult(in_scope=True, component_type=None, plan="do the thing"),
    )

    updates = understand(base_state)

    # Transparent failure — routed to handle_error, NOT dispatched as a culvert.
    assert updates.get("error")
    assert "component" in updates["error"].lower()
    assert updates.get("component_type") != "box_culvert"
    assert "component_type" not in updates  # never silently resolved
    assert updates.get("in_scope") is not True
    entry = next(s for s in updates["steps"] if s["name"] == "Understand")
    assert entry["status"] == "failed"


def test_resolved_classification_is_honoured(monkeypatch, base_state):
    _patch_llm(
        monkeypatch,
        UnderstandResult(
            in_scope=True,
            component_type="rcc_cantilever_retaining_wall",
            plan="design the wall",
        ),
    )

    updates = understand(base_state)

    assert updates.get("error") is None
    assert updates["in_scope"] is True
    assert updates["component_type"] == "rcc_cantilever_retaining_wall"


def test_explicit_picker_choice_wins_over_null_classification(monkeypatch, base_state):
    """The picker path always resolves — even if the classifier returns null."""
    base_state["requested_component"] = "rcc_cantilever_retaining_wall"
    _patch_llm(
        monkeypatch,
        UnderstandResult(in_scope=True, component_type=None, plan="design the wall"),
    )

    updates = understand(base_state)

    assert updates.get("error") is None
    assert updates["component_type"] == "rcc_cantilever_retaining_wall"
