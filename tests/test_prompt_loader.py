"""Tests for backend.prompt_loader — template filling, file loading, persona parsing."""
from __future__ import annotations

import pytest

from backend.prompt_loader import (
    _fill,
    get_clarify_prompt,
    get_guardian_prompt,
    get_intake_prompt,
    get_interviewer_prompt,
    get_mapper_prompt,
    get_prompt,
    get_report_prompt,
    get_trend_prompt,
    get_triage_prompt,
    list_prompts,
    reload_all,
)


# ── _fill ────────────────────────────────────────────────────────────────────

class TestFill:
    def test_single_placeholder(self):
        result = _fill("Hello {{name}}!", name="Priya")
        assert result == "Hello Priya!"

    def test_multiple_placeholders(self):
        result = _fill("{{a}} and {{b}}", a="foo", b="bar")
        assert result == "foo and bar"

    def test_missing_placeholder_left_unchanged(self):
        result = _fill("Hello {{name}}", age="29")
        assert "{{name}}" in result

    def test_non_string_value_is_coerced(self):
        result = _fill("Q {{number}} of 7", number=3)
        assert result == "Q 3 of 7"

    def test_empty_template(self):
        assert _fill("", key="val") == ""

    def test_no_placeholders(self):
        assert _fill("no placeholders here") == "no placeholders here"


# ── list_prompts ─────────────────────────────────────────────────────────────

class TestListPrompts:
    EXPECTED_BASE = {
        "GUARDIAN_SEMANTIC", "INTAKE_QUESTIONS", "TRIAGE_DECISION",
        "MAPPER_SCORE", "TREND_ANALYSIS", "REPORT_FULL", "CLARIFY_AMBIGUOUS",
    }
    EXPECTED_PERSONAS = {
        "INTERVIEWER_ADULT", "INTERVIEWER_CHILD", "INTERVIEWER_GENZ",
        "INTERVIEWER_SENIOR", "INTERVIEWER_TEEN",
    }

    def test_contains_all_base_prompts(self):
        prompts = set(list_prompts())
        assert self.EXPECTED_BASE.issubset(prompts)

    def test_contains_all_persona_prompts(self):
        prompts = set(list_prompts())
        assert self.EXPECTED_PERSONAS.issubset(prompts)

    def test_total_count(self):
        assert len(list_prompts()) == 12   # 7 base + 5 personas


# ── get_prompt — unknown IDs ─────────────────────────────────────────────────

class TestGetPromptErrors:
    def test_unknown_prompt_id_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown prompt ID"):
            get_prompt("NONEXISTENT_PROMPT")

    def test_unknown_persona_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown interviewer persona"):
            get_prompt("INTERVIEWER_ALIEN")


# ── Real prompt file loading ─────────────────────────────────────────────────

class TestPromptFileLoading:
    def test_guardian_prompt_is_non_empty(self):
        p = get_guardian_prompt()
        assert len(p) > 100

    def test_guardian_prompt_contains_crisis_indicators(self):
        p = get_guardian_prompt()
        assert "crisis" in p.lower() or "suicid" in p.lower()

    def test_intake_prompt_contains_question_number(self):
        p = get_intake_prompt(conversation_so_far="No conversation yet.", question_number=3)
        assert "3" in p

    def test_intake_prompt_fills_conversation(self):
        marker = "User: hello there"
        p = get_intake_prompt(conversation_so_far=marker, question_number=1)
        assert marker in p

    def test_triage_prompt_fills_profile_and_conversation(self):
        profile = "Name: Test | Age: 30"
        conv    = "I've been really stressed at work."
        p = get_triage_prompt(user_profile=profile, conversation=conv)
        assert profile in p
        assert conv in p

    def test_mapper_prompt_fills_reverse_flag_yes(self):
        p = get_mapper_prompt(
            instrument_name="PSS-10",
            symptom="Felt confident about handling problems",
            scoring_label="0=Never, 4=Very often",
            is_reverse=True,
            user_response="often",
        )
        assert "YES" in p

    def test_mapper_prompt_fills_reverse_flag_no(self):
        p = get_mapper_prompt(
            instrument_name="GAD-7",
            symptom="Feeling nervous",
            scoring_label="0=Not at all, 3=Nearly every day",
            is_reverse=False,
            user_response="sometimes",
        )
        assert "NO" in p

    def test_clarify_prompt_fills_symptom_and_name(self):
        p = get_clarify_prompt(
            symptom="Trouble relaxing",
            user_name="Arjun",
            prev_response="I don't know",
        )
        assert "Trouble relaxing" in p
        assert "Arjun" in p

    @pytest.mark.parametrize("age_group", ["Child", "Teen", "GenZ", "Adult", "Senior"])
    def test_interviewer_prompt_loads_for_every_persona(self, age_group):
        p = get_interviewer_prompt(
            age_group=age_group,
            symptom="Feeling nervous or on edge",
            progress="Q1 of 7",
        )
        assert len(p) > 200

    def test_interviewer_prompt_fills_symptom(self):
        symptom = "Trouble concentrating on things"
        p = get_interviewer_prompt(
            age_group="Adult",
            symptom=symptom,
            progress="Q5 of 9",
            user_name="Meera",
        )
        assert symptom in p

    def test_trend_prompt_fills_history(self):
        history = "[2026-01-01] GAD-7: 12 (Moderate)"
        p = get_trend_prompt(history_text=history, user_name="Raj")
        assert history in p

    def test_report_prompt_fills_all_fields(self):
        p = get_report_prompt(
            user_name="Kavya",
            age_group="Adult",
            profession="Software Engineer",
            user_context="Deadline pressure at work.",
            score_summary="  • GAD-7: 14/21 (Moderate)",
            trend="Initial baseline.",
        )
        assert "Kavya" in p
        assert "Software Engineer" in p
        assert "GAD-7" in p


# ── Cache invalidation ───────────────────────────────────────────────────────

class TestReloadAll:
    def test_reload_does_not_raise(self):
        reload_all()

    def test_prompts_still_load_after_reload(self):
        reload_all()
        p = get_guardian_prompt()
        assert len(p) > 50
