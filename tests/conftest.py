"""
Shared fixtures for the MindBridge test suite.
"""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage


# ── Message fixtures ─────────────────────────────────────────────────────────

@pytest.fixture()
def human_msg():
    """Factory that creates a HumanMessage."""
    def _make(text: str) -> HumanMessage:
        return HumanMessage(content=text)
    return _make


@pytest.fixture()
def ai_msg():
    """Factory that creates an AIMessage."""
    def _make(text: str) -> AIMessage:
        return AIMessage(content=text)
    return _make


@pytest.fixture()
def mixed_messages():
    """Alternating AI / Human messages for conversation-window tests."""
    return [
        AIMessage(content="Hi, I'm Mira. What's your name?"),
        HumanMessage(content="I'm Priya."),
        AIMessage(content="Nice to meet you, Priya. How old are you?"),
        HumanMessage(content="I'm 29."),
        AIMessage(content="What do you do for work?"),
        HumanMessage(content="I'm a software engineer."),
        AIMessage(content="Thanks. What brought you here today?"),
        HumanMessage(content="Feeling overwhelmed with deadlines."),
        AIMessage(content="I understand. How's your sleep been?"),
        HumanMessage(content="Not great, maybe 5 hours most nights."),
    ]


# ── Score / registry fixtures ────────────────────────────────────────────────

@pytest.fixture()
def gad7_scores():
    """All-2 scores for GAD-7 (7 items × 2 = 14 → Moderate)."""
    return {i: 2 for i in range(1, 8)}


@pytest.fixture()
def pss10_scores():
    """
    PSS-10 scores with reverse items [4, 5, 7, 8].
    All raw scores = 3.  Forward items contribute 3 each (6 × 3 = 18).
    Reverse items contribute (4 - 3) = 1 each (4 × 1 = 4).  Total = 22.
    """
    return {i: 3 for i in range(1, 11)}
