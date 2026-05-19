"""
Tests for backend.ai_engine — pure-logic functions + LLM-mocked paths.

Pure functions (no mocking needed):
  get_severity_label, compute_total, get_remaining, last_human,
  build_intake_transcript, build_conversation_window,
  build_answered_summary, _fallback_test, _merge_dicts, configure_llm

LLM-mocked:
  _get_llm (kwargs verification), AssessmentSession construction
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from backend.ai_engine import (
    INTAKE_TOTAL,
    TEST_REGISTRY,
    _fallback_test,
    _merge_dicts,
    build_answered_summary,
    build_conversation_window,
    build_intake_transcript,
    compute_total,
    configure_llm,
    get_remaining,
    get_severity_label,
    last_human,
)


# ── TEST_REGISTRY structure ──────────────────────────────────────────────────

class TestTestRegistry:
    REQUIRED_KEYS = {"name", "scoring_label", "reverse_items", "max_score", "thresholds", "questions"}

    @pytest.mark.parametrize("test_id", ["GAD-7", "PHQ-9", "PSS-10", "TAWS-16"])
    def test_all_instruments_present(self, test_id):
        assert test_id in TEST_REGISTRY

    @pytest.mark.parametrize("test_id", ["GAD-7", "PHQ-9", "PSS-10", "TAWS-16"])
    def test_required_keys_present(self, test_id):
        assert self.REQUIRED_KEYS.issubset(TEST_REGISTRY[test_id].keys())

    def test_gad7_has_7_questions(self):
        assert len(TEST_REGISTRY["GAD-7"]["questions"]) == 7

    def test_phq9_has_9_questions(self):
        assert len(TEST_REGISTRY["PHQ-9"]["questions"]) == 9

    def test_pss10_has_10_questions(self):
        assert len(TEST_REGISTRY["PSS-10"]["questions"]) == 10

    def test_taws16_has_16_questions(self):
        assert len(TEST_REGISTRY["TAWS-16"]["questions"]) == 16

    def test_pss10_reverse_items(self):
        assert sorted(TEST_REGISTRY["PSS-10"]["reverse_items"]) == [4, 5, 7, 8]

    def test_gad7_no_reverse_items(self):
        assert TEST_REGISTRY["GAD-7"]["reverse_items"] == []

    def test_max_scores(self):
        assert TEST_REGISTRY["GAD-7"]["max_score"]   == 21
        assert TEST_REGISTRY["PHQ-9"]["max_score"]   == 27
        assert TEST_REGISTRY["PSS-10"]["max_score"]  == 40
        assert TEST_REGISTRY["TAWS-16"]["max_score"] == 64

    def test_intake_total_is_6(self):
        assert INTAKE_TOTAL == 6


# ── get_severity_label ───────────────────────────────────────────────────────

class TestGetSeverityLabel:
    @pytest.mark.parametrize("score,expected", [
        (0, "Minimal"), (4, "Minimal"),
        (5, "Mild"),    (9, "Mild"),
        (10, "Moderate"), (14, "Moderate"),
        (15, "Severe"), (21, "Severe"),
    ])
    def test_gad7_thresholds(self, score, expected):
        assert get_severity_label("GAD-7", score) == expected

    @pytest.mark.parametrize("score,expected", [
        (0, "Minimal"), (4, "Minimal"),
        (5, "Mild"),    (9, "Mild"),
        (10, "Moderate"), (14, "Moderate"),
        (15, "Moderately Severe"), (19, "Moderately Severe"),
        (20, "Severe"), (27, "Severe"),
    ])
    def test_phq9_thresholds(self, score, expected):
        assert get_severity_label("PHQ-9", score) == expected

    @pytest.mark.parametrize("score,expected", [
        (0, "Low"), (13, "Low"),
        (14, "Moderate"), (26, "Moderate"),
        (27, "High"), (40, "High"),
    ])
    def test_pss10_thresholds(self, score, expected):
        assert get_severity_label("PSS-10", score) == expected

    @pytest.mark.parametrize("score,expected", [
        (0, "Low"),  (16, "Low"),
        (17, "Mild"), (32, "Mild"),
        (33, "Moderate"), (48, "Moderate"),
        (49, "High"), (64, "High"),
    ])
    def test_taws16_thresholds(self, score, expected):
        assert get_severity_label("TAWS-16", score) == expected


# ── compute_total ────────────────────────────────────────────────────────────

class TestComputeTotal:
    def test_gad7_no_reverse(self, gad7_scores):
        # 7 items × 2 = 14
        assert compute_total("GAD-7", gad7_scores) == 14

    def test_gad7_all_zero(self):
        scores = {i: 0 for i in range(1, 8)}
        assert compute_total("GAD-7", scores) == 0

    def test_gad7_all_max(self):
        scores = {i: 3 for i in range(1, 8)}
        assert compute_total("GAD-7", scores) == 21

    def test_phq9_max_score(self):
        scores = {i: 3 for i in range(1, 10)}
        assert compute_total("PHQ-9", scores) == 27

    def test_pss10_reverse_items_contribute_correctly(self, pss10_scores):
        # Forward items (1,2,3,6,9,10): 6 × 3 = 18
        # Reverse items (4,5,7,8):       4 × (4-3) = 4
        # Total = 22
        assert compute_total("PSS-10", pss10_scores) == 22

    def test_pss10_all_zero_gives_max_for_reverse(self):
        # Forward: 6 × 0 = 0 ; Reverse: 4 × (4-0) = 16
        scores = {i: 0 for i in range(1, 11)}
        assert compute_total("PSS-10", scores) == 16

    def test_taws16_no_reverse(self):
        scores = {i: 4 for i in range(1, 17)}
        assert compute_total("TAWS-16", scores) == 64

    def test_empty_scores_returns_zero(self):
        assert compute_total("GAD-7", {}) == 0


# ── get_remaining ────────────────────────────────────────────────────────────

class TestGetRemaining:
    def test_nothing_answered_returns_all(self):
        remaining = get_remaining("GAD-7", {})
        assert sorted(remaining) == list(range(1, 8))

    def test_all_answered_returns_empty(self):
        answered = {i for i in range(1, 8)}
        remaining = get_remaining("GAD-7", {"GAD-7": list(answered)})
        assert remaining == []

    def test_partial_answer(self):
        remaining = get_remaining("GAD-7", {"GAD-7": [1, 2, 3]})
        assert sorted(remaining) == [4, 5, 6, 7]

    def test_different_test_key_not_counted(self):
        # Answered in PHQ-9 should not affect GAD-7
        remaining = get_remaining("GAD-7", {"PHQ-9": [1, 2, 3]})
        assert sorted(remaining) == list(range(1, 8))


# ── last_human ───────────────────────────────────────────────────────────────

class TestLastHuman:
    def test_returns_last_human_message(self, mixed_messages):
        result = last_human(mixed_messages)
        assert result == "Not great, maybe 5 hours most nights."

    def test_returns_empty_string_when_no_human_messages(self):
        msgs = [AIMessage(content="Hello"), AIMessage(content="How are you?")]
        assert last_human(msgs) == ""

    def test_returns_empty_string_for_empty_list(self):
        assert last_human([]) == ""

    def test_skips_ai_messages_at_end(self):
        msgs = [
            HumanMessage(content="I feel anxious."),
            AIMessage(content="I hear you. Let me ask the next question."),
        ]
        assert last_human(msgs) == "I feel anxious."


# ── build_intake_transcript ──────────────────────────────────────────────────

class TestBuildIntakeTranscript:
    def test_labels_human_as_user(self):
        msgs = [HumanMessage(content="I'm Priya.")]
        transcript = build_intake_transcript(msgs)
        assert transcript == "User: I'm Priya."

    def test_labels_ai_as_mira(self):
        msgs = [AIMessage(content="Hi! I'm Mira.")]
        transcript = build_intake_transcript(msgs)
        assert transcript == "Mira: Hi! I'm Mira."

    def test_alternating_messages(self):
        msgs = [
            AIMessage(content="What's your name?"),
            HumanMessage(content="Priya"),
        ]
        transcript = build_intake_transcript(msgs)
        assert transcript == "Mira: What's your name?\nUser: Priya"

    def test_empty_list_returns_empty_string(self):
        assert build_intake_transcript([]) == ""


# ── build_conversation_window ────────────────────────────────────────────────

class TestBuildConversationWindow:
    def test_empty_list_returns_placeholder(self):
        result = build_conversation_window([])
        assert result == "No conversation yet."

    def test_truncates_to_n_most_recent(self, mixed_messages):
        result = build_conversation_window(mixed_messages, n=4)
        lines = result.strip().split("\n")
        assert len(lines) == 4

    def test_no_truncation_when_fewer_than_n(self):
        msgs = [HumanMessage(content="hello")]
        result = build_conversation_window(msgs, n=8)
        assert "hello" in result

    def test_labels_correctly(self):
        msgs = [
            AIMessage(content="Q"),
            HumanMessage(content="A"),
        ]
        result = build_conversation_window(msgs)
        assert "Assistant: Q" in result
        assert "User: A" in result

    def test_uses_last_n_not_first_n(self, mixed_messages):
        result = build_conversation_window(mixed_messages, n=2)
        assert "5 hours" in result          # last human msg
        assert "Priya" not in result        # early message should be gone


# ── build_answered_summary ───────────────────────────────────────────────────

class TestBuildAnsweredSummary:
    def test_no_answered_returns_none_message(self):
        result = build_answered_summary("GAD-7", {}, {})
        assert "None yet" in result

    def test_answered_items_appear_in_output(self):
        answered = {"GAD-7": [1, 2]}
        result = build_answered_summary("GAD-7", answered, {})
        q1 = TEST_REGISTRY["GAD-7"]["questions"][1]
        q2 = TEST_REGISTRY["GAD-7"]["questions"][2]
        assert q1 in result
        assert q2 in result

    def test_bullet_format(self):
        answered = {"GAD-7": [1]}
        result = build_answered_summary("GAD-7", answered, {})
        assert result.startswith("•")


# ── _fallback_test ───────────────────────────────────────────────────────────

class TestFallbackTest:
    def test_work_keywords_return_taws16(self):
        transcript = "I've been struggling with work deadlines and my boss is very demanding."
        assert _fallback_test(transcript) == "TAWS-16"

    def test_anxiety_keywords_return_gad7(self):
        transcript = "I feel really anxious and nervous all the time, panic attacks."
        assert _fallback_test(transcript) == "GAD-7"

    def test_depression_keywords_return_phq9(self):
        transcript = "I feel so hopeless and empty. Lost interest in everything."
        assert _fallback_test(transcript) == "PHQ-9"

    def test_student_keyword_returns_gad7(self):
        transcript = "I'm a student preparing for college exams."
        assert _fallback_test(transcript) == "GAD-7"

    def test_unemployed_keyword_returns_phq9(self):
        transcript = "I've been unemployed for three months and it's really hard."
        assert _fallback_test(transcript) == "PHQ-9"

    def test_homemaker_keyword_returns_pss10(self):
        transcript = "I'm a homemaker taking care of my family."
        assert _fallback_test(transcript) == "PSS-10"

    def test_default_returns_gad7(self):
        assert _fallback_test("nothing specific here") == "GAD-7"

    def test_case_insensitive(self):
        # Keywords are lowercased before matching
        assert _fallback_test("WORK DEADLINE JOB BOSS OFFICE MANAGER CAREER") == "TAWS-16"


# ── _merge_dicts ─────────────────────────────────────────────────────────────

class TestMergeDicts:
    def test_non_overlapping_keys(self):
        result = _merge_dicts({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_scalar_value_overwritten_by_second(self):
        result = _merge_dicts({"a": 1}, {"a": 2})
        assert result["a"] == 2

    def test_list_values_concatenated_without_duplicates(self):
        result = _merge_dicts({"ids": [1, 2]}, {"ids": [2, 3]})
        assert result["ids"] == [1, 2, 3]

    def test_empty_first_dict(self):
        result = _merge_dicts({}, {"a": [1]})
        assert result == {"a": [1]}

    def test_empty_second_dict(self):
        result = _merge_dicts({"a": [1]}, {})
        assert result == {"a": [1]}

    def test_does_not_mutate_original(self):
        original = {"a": [1]}
        _merge_dicts(original, {"a": [2]})
        assert original == {"a": [1]}


# ── configure_llm ────────────────────────────────────────────────────────────

class TestConfigureLlm:
    def test_sets_provider_to_openai(self):
        from backend.ai_engine import _llm_cfg
        configure_llm("openai", "sk-test-key")
        assert _llm_cfg.provider == "openai"
        assert _llm_cfg.openai_key == "sk-test-key"

    def test_sets_provider_to_default(self):
        from backend.ai_engine import _llm_cfg
        configure_llm("default")
        assert _llm_cfg.provider == "default"

    def test_resets_key_when_switching_to_default(self):
        from backend.ai_engine import _llm_cfg
        configure_llm("openai", "sk-old-key")
        configure_llm("default", "")
        assert _llm_cfg.provider == "default"


# ── _get_llm — LLM factory kwargs (ChatOpenAI is mocked) ────────────────────

class TestGetLlm:
    def test_default_mode_includes_model_kwargs_reasoning_effort(self, monkeypatch):
        from backend import ai_engine
        monkeypatch.setattr(ai_engine, "_BASE_URL", "https://groq-url/v1")
        monkeypatch.setattr(ai_engine, "_API_KEY",  "groq-key")
        configure_llm("default")

        with patch("backend.ai_engine.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            ai_engine._get_llm()
            kwargs = mock_cls.call_args.kwargs
            assert kwargs.get("model_kwargs") == {"reasoning_effort": "low"}
            assert kwargs.get("base_url") == "https://groq-url/v1"
            assert kwargs.get("api_key") == "groq-key"

    def test_default_mode_omits_base_url_when_not_set(self, monkeypatch):
        from backend import ai_engine
        monkeypatch.setattr(ai_engine, "_BASE_URL", "")
        monkeypatch.setattr(ai_engine, "_API_KEY",  "")
        configure_llm("default")

        with patch("backend.ai_engine.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            ai_engine._get_llm()
            kwargs = mock_cls.call_args.kwargs
            assert "base_url" not in kwargs

    def test_openai_mode_uses_gpt4o_mini(self):
        configure_llm("openai", "sk-user-key")

        with patch("backend.ai_engine.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            from backend.ai_engine import _get_llm
            _get_llm()
            kwargs = mock_cls.call_args.kwargs
            assert kwargs["model"] == "gpt-4o-mini"
            assert kwargs["api_key"] == "sk-user-key"

    def test_openai_mode_has_no_model_kwargs(self):
        configure_llm("openai", "sk-user-key")

        with patch("backend.ai_engine.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            from backend.ai_engine import _get_llm
            _get_llm()
            kwargs = mock_cls.call_args.kwargs
            assert "model_kwargs" not in kwargs

    def test_structured_output_called_when_schema_provided(self):
        from pydantic import BaseModel
        from backend.ai_engine import _get_llm

        class _Schema(BaseModel):
            value: int

        configure_llm("openai", "sk-test")
        with patch("backend.ai_engine.ChatOpenAI") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.with_structured_output.return_value = MagicMock()
            mock_cls.return_value = mock_instance
            _get_llm(structured=_Schema)
            mock_instance.with_structured_output.assert_called_once_with(_Schema)

    def test_temperature_is_passed_through(self):
        configure_llm("openai", "sk-test")
        with patch("backend.ai_engine.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            from backend.ai_engine import _get_llm
            _get_llm(temperature=0.75)
            assert mock_cls.call_args.kwargs["temperature"] == 0.75


# ── AssessmentSession construction ───────────────────────────────────────────

class TestAssessmentSession:
    """
    Smoke tests for session creation.  The compiled graph is never invoked —
    we only verify that __init__ sets attributes correctly and calls configure_llm.
    """

    def _make_session(self, provider="default", key=""):
        with patch("backend.ai_engine.build_graph") as mock_graph:
            mock_graph.return_value = MagicMock()
            from backend.ai_engine import AssessmentSession
            return AssessmentSession("user_001", provider=provider, openai_key=key)

    def test_user_id_stored(self):
        s = self._make_session()
        assert s.user_id == "user_001"

    def test_provider_stored(self):
        s = self._make_session(provider="openai", key="sk-x")
        assert s.provider == "openai"

    def test_starts_not_done(self):
        s = self._make_session()
        assert s.is_done is False

    def test_starts_not_crisis(self):
        s = self._make_session()
        assert s.is_crisis is False

    def test_configure_llm_called_with_correct_provider(self):
        from backend.ai_engine import _llm_cfg
        with patch("backend.ai_engine.build_graph", return_value=MagicMock()):
            from backend.ai_engine import AssessmentSession
            AssessmentSession("u2", provider="openai", openai_key="sk-abc")
        assert _llm_cfg.provider == "openai"
        assert _llm_cfg.openai_key == "sk-abc"

    def test_thread_id_matches_user_id(self):
        s = self._make_session()
        assert s.config["configurable"]["thread_id"] == "user_001"

    def test_reply_when_done_returns_complete_message(self):
        s = self._make_session()
        s.is_done = True
        result = s.reply("hello")
        assert "complete" in result.lower()
