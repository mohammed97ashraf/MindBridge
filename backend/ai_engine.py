"""
MindBridge AI engine — LangGraph adaptive mental-health assessment workflow.

Architecture
------------
A 12-node StateGraph drives the full conversation lifecycle:

    guardian → intake → intake_score → triage → interviewer
                                                     ↑   ↓
                               score_response ← user input
                                    ↓
                          clarify / scoring → trend_analyzer → router
                                                                  ↓
                                                         report_generator

Safety contract: every turn passes through guardian_node first.

Logging
-------
Node entry/exit: DEBUG.  State transitions: INFO.  Errors: WARNING/ERROR.

Retry
-----
Every LLM invoke goes through _invoke(), which retries up to
_MAX_LLM_RETRIES times with exponential back-off via tenacity.
"""
from __future__ import annotations

import operator
import os
from datetime import datetime
from typing import Annotated, Any, Dict, List, Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

import backend  # noqa: F401 — triggers install_exception_hook
from backend.database import get_checkpointer
from backend.logger import get_logger
from backend.prompt_loader import (
    get_clarify_prompt,
    get_guardian_prompt,
    get_intake_prompt,
    get_interviewer_prompt,
    get_mapper_prompt,
    get_report_prompt,
    get_trend_prompt,
    get_triage_prompt,
)

load_dotenv()
_log = get_logger(__name__)

# ── Runtime constants ────────────────────────────────────────────────────────
_MODEL: str = os.getenv("MODEL", "gpt-4o-mini")
_BASE_URL: str = os.getenv("BASE_URL", "")
_API_KEY: str = os.getenv("API_KEY") or os.getenv("OPENAI_API_KEY", "")
_MAX_LLM_RETRIES: int = 3
_CONV_WINDOW_SIZE: int = 8
_MAX_REPORT_ASSESSMENT_MSGS: int = 12

INTAKE_TOTAL: int = 6  # number of intake questions (exported for UI)

# ── Tenacity retry preset ────────────────────────────────────────────────────
_RETRY = retry(
    reraise=True,
    stop=stop_after_attempt(_MAX_LLM_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=8),
)


# ── TEST REGISTRY ────────────────────────────────────────────────────────────

TEST_REGISTRY: Dict[str, Dict] = {
    "GAD-7": {
        "name": "Anxiety (GAD-7)",
        "scoring_label": "0=Not at all, 1=Several days, 2=More than half the days, 3=Nearly every day",
        "reverse_items": [],
        "max_score": 21,
        "thresholds": [(4, "Minimal"), (9, "Mild"), (14, "Moderate"), (21, "Severe")],
        "questions": {
            1: "Feeling nervous, anxious, or on edge",
            2: "Not being able to stop or control worrying",
            3: "Worrying too much about different things",
            4: "Trouble relaxing",
            5: "Being so restless that it is hard to sit still",
            6: "Becoming easily annoyed or irritable",
            7: "Feeling afraid as if something awful might happen",
        },
    },
    "PHQ-9": {
        "name": "Depression (PHQ-9)",
        "scoring_label": "0=Not at all, 1=Several days, 2=More than half the days, 3=Nearly every day",
        "reverse_items": [],
        "max_score": 27,
        "thresholds": [
            (4, "Minimal"), (9, "Mild"), (14, "Moderate"),
            (19, "Moderately Severe"), (27, "Severe"),
        ],
        "questions": {
            1: "Little interest or pleasure in doing things",
            2: "Feeling down, depressed, or hopeless",
            3: "Trouble falling or staying asleep, or sleeping too much",
            4: "Feeling tired or having little energy",
            5: "Poor appetite or overeating",
            6: "Feeling bad about yourself — or that you are a failure",
            7: "Trouble concentrating on things",
            8: "Moving or speaking so slowly others noticed, or being fidgety/restless",
            9: "Thoughts that you would be better off dead, or of hurting yourself",
        },
    },
    "PSS-10": {
        "name": "Perceived Stress (PSS-10)",
        "scoring_label": "0=Never, 1=Almost never, 2=Sometimes, 3=Fairly often, 4=Very often",
        "reverse_items": [4, 5, 7, 8],
        "max_score": 40,
        "thresholds": [(13, "Low"), (26, "Moderate"), (40, "High")],
        "questions": {
            1:  "Been upset because of something that happened unexpectedly",
            2:  "Felt unable to control the important things in your life",
            3:  "Felt nervous and stressed",
            4:  "Felt confident about your ability to handle personal problems",
            5:  "Felt that things were going your way",
            6:  "Been unable to cope with all the things you had to do",
            7:  "Been able to control irritations in your life",
            8:  "Felt that you were on top of things",
            9:  "Been angered because of things that were outside your control",
            10: "Felt difficulties were piling up so high that you could not overcome them",
        },
    },
    "TAWS-16": {
        "name": "Work Stress (TAWS-16)",
        "scoring_label": "0=Never, 1=Rarely, 2=Sometimes, 3=Often, 4=Very Often — reflecting the past 6 months",
        "reverse_items": [],
        "max_score": 64,
        "thresholds": [(16, "Low"), (32, "Mild"), (48, "Moderate"), (64, "High")],
        "questions": {
            1:  "Felt that your workload was too heavy to complete within your working hours",
            2:  "Experienced conflicting demands or expectations from different people at your workplace",
            3:  "Felt uncertain or unclear about what your role actually required of you",
            4:  "Lacked adequate resources — tools, support, or budget — needed to do your job effectively",
            5:  "Felt unable to manage urgent or unexpected tasks that landed on you",
            6:  "Found it difficult to mentally disconnect from work during your personal or family time",
            7:  "Felt unsupported, sidelined, or unheard by your supervisor or management",
            8:  "Experienced tension, friction, or conflict with a colleague or team member",
            9:  "Felt anxious or uncertain about your job security or career stability",
            10: "Struggled to balance your professional responsibilities with personal or family life",
            11: "Felt that your efforts and contributions at work went unrecognised or undervalued",
            12: "Worked outside your official hours — evenings, weekends, or on leave — due to pressure",
            13: "Felt that your organisation's expectations were beyond what was realistically achievable",
            14: "Experienced physical fatigue or exhaustion that you attributed directly to work demands",
            15: "Felt emotionally drained or burnt out by the end of your working day",
            16: "Had trouble concentrating or staying focused because of work-related stress",
        },
    },
}


# ── Pydantic structured-output schemas ──────────────────────────────────────

class SafetyAssessment(BaseModel):
    is_crisis: bool = Field(
        description="True if suicidal ideation, self-harm, or extreme hopelessness."
    )
    risk_level: Literal["Low", "Medium", "High"]
    reasoning: str


class ScoreMapping(BaseModel):
    score: int = Field(ge=0, le=4)
    confidence: Literal["High", "Medium", "Low"]
    reasoning: str
    needs_clarification: bool = Field(default=False)


class TrendAnalysis(BaseModel):
    trajectory: Literal["Improving", "Stable", "Declining", "Insufficient data"]
    summary: str
    recommendation: str


class TriageDecision(BaseModel):
    start_test: Literal["GAD-7", "PHQ-9", "PSS-10", "TAWS-16"] = Field(
        description="Which clinical test to administer first."
    )
    reasoning: str = Field(description="Clinical reasoning for this choice.")
    transition_message: str = Field(
        description="Warm, personalised message to deliver to the user before Q1."
    )
    inferred_name: str = Field(default="", description="User's name from intake.")
    inferred_profession: str = Field(default="Not specified", description="User's profession.")
    inferred_age_group: Literal["Child", "Teen", "GenZ", "Adult", "Senior"] = Field(
        default="Adult"
    )
    user_context_summary: str = Field(
        default="", description="1-2 sentence summary of user's situation."
    )


# ── State reducers ───────────────────────────────────────────────────────────

def _merge_dicts(a: dict, b: dict) -> dict:
    """Deep-merge two dicts; list values are de-duplicated and concatenated."""
    merged = dict(a)
    for k, v in b.items():
        if k in merged and isinstance(merged[k], list) and isinstance(v, list):
            merged[k] = merged[k] + [x for x in v if x not in merged[k]]
        else:
            merged[k] = v
    return merged


# ── Agent state ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    user_id:      str
    user_name:    str
    age_group:    str
    profession:   str
    user_context: str

    intake_question_number: int
    intake_complete:        bool
    intake_conversation:    str

    current_test:        str
    current_question_id: int
    test_answered:   Annotated[Dict[str, List[int]], _merge_dicts]
    test_scores:     Annotated[Dict[str, Dict[int, int]], _merge_dicts]
    completed_tests: Annotated[Dict[str, int], _merge_dicts]
    clarify_attempts: Annotated[Dict[str, int], _merge_dicts]

    historical_scores: Annotated[List[Dict], operator.add]
    messages: Annotated[List[BaseMessage], operator.add]

    trend_analysis: str
    final_report:   str
    is_crisis:      bool

    turn_phase:  str
    turn_intent: str


# ── Provider configuration ───────────────────────────────────────────────────

class _LLMConfig:
    """
    Runtime provider selection shared within a single Streamlit worker.

    "default" → BASE_URL / API_KEY / MODEL from .env, with reasoning_effort
    "openai"  → gpt-4o-mini via a user-supplied key, no reasoning_effort
    """
    provider: str = "default"
    openai_key: str = ""


_llm_cfg = _LLMConfig()


def configure_llm(provider: Literal["default", "openai"], openai_key: str = "") -> None:
    """
    Switch the active LLM provider.  Call once before creating AssessmentSession.

    Parameters
    ----------
    provider:
        "default" uses the deployed Groq endpoint from .env.
        "openai"  uses gpt-4o-mini with the user-supplied *openai_key*.
    openai_key:
        Required when provider == "openai".
    """
    _llm_cfg.provider  = provider
    _llm_cfg.openai_key = openai_key
    _log.info("LLM provider configured: %s", provider)


# ── LLM factory ─────────────────────────────────────────────────────────────

def _get_llm(structured: Any = None, temperature: float = 0.3) -> Any:
    """
    Instantiate a ChatOpenAI client for the active provider.

    Default (Groq/base-URL) path: model_kwargs reasoning_effort is required
    by the remote endpoint and must stay in model_kwargs (not a top-level kwarg).

    OpenAI path: gpt-4o-mini does not accept reasoning_effort at all.
    """
    if _llm_cfg.provider == "openai":
        kwargs: Dict[str, Any] = {
            "model":       "gpt-4o-mini",
            "temperature": temperature,
            "api_key":     _llm_cfg.openai_key or os.getenv("OPENAI_API_KEY", ""),
        }
    else:
        kwargs = {
            "model":        _MODEL,
            "temperature":  temperature,
            "model_kwargs": {"reasoning_effort": "low"},
        }
        if _BASE_URL:
            kwargs["base_url"] = _BASE_URL
        if _API_KEY:
            kwargs["api_key"] = _API_KEY

    llm = ChatOpenAI(**kwargs)
    return llm.with_structured_output(structured) if structured else llm


# ── Retry-aware LLM invoke ───────────────────────────────────────────────────

def _invoke(llm: Any, messages: list[BaseMessage], node: str = "") -> Any:
    """
    Call llm.invoke() with automatic exponential-backoff retry.

    Logs a warning on each transient failure and an error if all attempts
    are exhausted, then re-raises the original exception.
    """
    @_RETRY
    def _call() -> Any:
        return llm.invoke(messages)

    try:
        return _call()
    except Exception as exc:
        _log.error("LLM exhausted %d retries in node '%s': %s", _MAX_LLM_RETRIES, node, exc)
        raise


# ── Domain helpers ───────────────────────────────────────────────────────────

def get_severity_label(test_id: str, score: int) -> str:
    for threshold, label in TEST_REGISTRY[test_id]["thresholds"]:
        if score <= threshold:
            return label
    return TEST_REGISTRY[test_id]["thresholds"][-1][1]


def get_remaining(test_id: str, test_answered: Dict[str, List[int]]) -> List[int]:
    answered = test_answered.get(test_id, [])
    return [q for q in TEST_REGISTRY[test_id]["questions"] if q not in answered]


def compute_total(test_id: str, scores: Dict[int, int]) -> int:
    reverse = TEST_REGISTRY[test_id]["reverse_items"]
    max_item = 4 if test_id in ("PSS-10", "TAWS-16") else 3
    return sum((max_item - v) if q in reverse else v for q, v in scores.items())


def last_human(messages: List[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return m.content
    return ""


def build_intake_transcript(messages: List[BaseMessage]) -> str:
    return "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'Mira'}: {m.content}"
        for m in messages
    )


def build_conversation_window(messages: List[BaseMessage], n: int = _CONV_WINDOW_SIZE) -> str:
    recent = messages[-n:] if len(messages) >= n else messages
    lines = [
        f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}"
        for m in recent
    ]
    return "\n".join(lines) or "No conversation yet."


def build_answered_summary(
    test_id: str,
    test_answered: Dict[str, List[int]],
    test_scores: Dict[str, Dict[int, int]],  # noqa: ARG001 — kept for future use
) -> str:
    answered = test_answered.get(test_id, [])
    if not answered:
        return "None yet — this is the first question."
    items = [
        f"• {TEST_REGISTRY[test_id]['questions'].get(q_id, '')}"
        for q_id in answered
    ]
    return "\n".join(items)


def _fallback_test(transcript: str) -> str:
    """Keyword heuristic triage used when the LLM call fails."""
    t = transcript.lower()
    scores = {
        "TAWS-16": sum(1 for kw in ["work", "job", "office", "deadline", "colleague", "manager", "boss", "career", "workplace", "salary"] if kw in t),
        "PHQ-9":   sum(1 for kw in ["sad", "hopeless", "empty", "lost interest", "worthless", "burden", "numb", "crying"] if kw in t),
        "GAD-7":   sum(1 for kw in ["worry", "anxious", "nervous", "afraid", "panic", "fear", "restless", "racing"] if kw in t),
    }
    if scores["TAWS-16"] >= 2:
        return "TAWS-16"
    if scores["PHQ-9"] > scores["GAD-7"] and scores["PHQ-9"] > 0:
        return "PHQ-9"
    if scores["GAD-7"] > 0:
        return "GAD-7"
    for kw, test in [("student", "GAD-7"), ("unemployed", "PHQ-9"), ("homemaker", "PSS-10"), ("retired", "PSS-10")]:
        if kw in t:
            return test
    return "GAD-7"


# ── Graph nodes ──────────────────────────────────────────────────────────────

def intake_node(state: AgentState) -> dict:
    _log.debug("→ intake_node | user=%s | q=%d", state.get("user_id"), state.get("intake_question_number", 1))
    q_num = state.get("intake_question_number", 1)
    transcript = build_intake_transcript(state.get("messages", []))
    system = get_intake_prompt(
        conversation_so_far=transcript or "No conversation yet.",
        question_number=q_num,
    )
    llm = _get_llm(temperature=0.65)
    resp = _invoke(llm, [SystemMessage(content=system)], node="intake")
    _log.debug("← intake_node | q=%d", q_num)
    return {
        "messages":    [AIMessage(content=resp.content)],
        "turn_phase":  "intake",
        "turn_intent": "waiting",
    }


def intake_score_node(state: AgentState) -> dict:
    q_num = state.get("intake_question_number", 1)
    transcript = build_intake_transcript(state.get("messages", []))
    new_q_num = q_num + 1
    _log.debug("intake_score_node | q %d → %d", q_num, new_q_num)

    if new_q_num > INTAKE_TOTAL:
        _log.info("Intake complete for user=%s", state.get("user_id"))
        return {
            "intake_question_number": new_q_num,
            "intake_complete":        True,
            "intake_conversation":    transcript,
            "turn_phase":             "triage",
            "turn_intent":            "triage",
        }
    return {
        "intake_question_number": new_q_num,
        "intake_conversation":    transcript,
        "turn_phase":             "intake",
        "turn_intent":            "ask_intake",
    }


def triage_node(state: AgentState) -> dict:
    _log.debug("→ triage_node | user=%s", state.get("user_id"))
    transcript = state.get("intake_conversation", "")
    system = get_triage_prompt(
        user_profile=f"Intake conversation:\n{transcript}",
        conversation=transcript,
    )
    llm = _get_llm(structured=TriageDecision, temperature=0.15)
    try:
        decision: TriageDecision = _invoke(llm, [SystemMessage(content=system)], node="triage")
        start_test   = decision.start_test
        transition   = decision.transition_message
        user_name    = decision.inferred_name or state.get("user_id", "there")
        profession   = decision.inferred_profession or "Not specified"
        age_group    = decision.inferred_age_group or "Adult"
        user_context = decision.user_context_summary or transcript[:300]
    except Exception as exc:
        _log.warning("Triage LLM failed — using keyword fallback: %s", exc)
        start_test   = _fallback_test(transcript)
        transition   = (
            "Thank you for sharing that with me. I'd like to ask you a few questions now — "
            "there are no right or wrong answers."
        )
        user_name    = state.get("user_id", "there")
        profession   = "Not specified"
        age_group    = "Adult"
        user_context = transcript[:300]

    _log.info(
        "← triage_node | user=%s | test=%s | age=%s",
        state.get("user_id"), start_test, age_group,
    )
    return {
        "current_test":        start_test,
        "current_question_id": 0,
        "test_answered":       {start_test: []},
        "test_scores":         {start_test: {}},
        "clarify_attempts":    {},
        "user_name":           user_name,
        "profession":          profession,
        "age_group":           age_group,
        "user_context":        user_context,
        "messages":            [AIMessage(content=transition)],
        "turn_phase":          "assess",
        "turn_intent":         "ask",
    }


_CRISIS_KEYWORDS = frozenset({
    "suicide", "suicidal", "kill myself", "end my life", "end it all",
    "harm myself", "self-harm", "want to die", "better off dead",
    "no reason to live", "can't go on", "don't want to be here",
})


def guardian_node(state: AgentState) -> dict:
    intent = state.get("turn_intent", "score")
    if intent in ("ask", "ask_intake", "triage"):
        return {}

    text = last_human(state.get("messages", [])).lower()
    if not text:
        return {}

    if any(kw in text for kw in _CRISIS_KEYWORDS):
        _log.warning("Crisis keyword detected for user=%s", state.get("user_id"))
        return {"is_crisis": True, "turn_intent": "crisis", "turn_phase": "done"}

    try:
        llm = _get_llm(structured=SafetyAssessment)
        result: SafetyAssessment = _invoke(
            llm,
            [SystemMessage(content=get_guardian_prompt()), HumanMessage(content=text)],
            node="guardian",
        )
        if result.is_crisis or result.risk_level == "High":
            _log.warning(
                "Guardian LLM flagged crisis for user=%s | risk=%s",
                state.get("user_id"), result.risk_level,
            )
            return {"is_crisis": True, "turn_intent": "crisis", "turn_phase": "done"}
    except Exception as exc:
        _log.warning("Guardian LLM error (non-fatal): %s", exc)

    return {}


def score_response_node(state: AgentState) -> dict:
    test_id = state["current_test"]
    q_id    = state["current_question_id"]
    symptom = TEST_REGISTRY[test_id]["questions"].get(q_id, "")
    is_rev  = q_id in TEST_REGISTRY[test_id]["reverse_items"]
    user_txt = last_human(state.get("messages", []))

    clarify_key = f"{test_id}:{q_id}"
    attempt     = state.get("clarify_attempts", {}).get(clarify_key, 0)
    conv_window = build_conversation_window(state.get("messages", []))
    _log.debug("→ score_response_node | test=%s | q=%d | attempt=%d", test_id, q_id, attempt)

    score = 1
    needs_clarify = False
    try:
        llm = _get_llm(structured=ScoreMapping)
        m: ScoreMapping = _invoke(
            llm,
            [SystemMessage(content=get_mapper_prompt(
                instrument_name=TEST_REGISTRY[test_id]["name"],
                symptom=symptom,
                scoring_label=TEST_REGISTRY[test_id]["scoring_label"],
                is_reverse=is_rev,
                user_response=user_txt,
                user_name=state.get("user_name", "the user"),
                profession=state.get("profession", "not specified"),
                conversation_window=conv_window,
                clarify_attempt=attempt,
            ))],
            node="score_response",
        )
        max_s = 4 if test_id in ("PSS-10", "TAWS-16") else 3
        score = max(0, min(max_s, m.score))
        needs_clarify = m.needs_clarification and m.confidence == "Low" and attempt == 0
        _log.debug("Scored q%d=%d (conf=%s)", q_id, score, m.confidence)
    except Exception as exc:
        _log.warning("Mapper error — defaulting score to 1: %s", exc)

    current_answered = list(state.get("test_answered", {}).get(test_id, []))
    if q_id not in current_answered:
        current_answered = current_answered + [q_id]

    current_scores = {**state.get("test_scores", {}).get(test_id, {}), q_id: score}
    remaining = [q for q in TEST_REGISTRY[test_id]["questions"] if q not in current_answered]

    if needs_clarify:
        intent = "clarify"
    elif not remaining:
        intent = "finish"
    else:
        intent = "ask_next"

    _log.debug("← score_response_node | intent=%s | remaining=%d", intent, len(remaining))
    return {
        "test_answered": {test_id: current_answered},
        "test_scores":   {test_id: current_scores},
        "turn_intent":   intent,
    }


def interviewer_node(state: AgentState) -> dict:
    test_id = state["current_test"]
    test_answered = state.get("test_answered", {})
    remaining = get_remaining(test_id, test_answered)
    _log.debug("→ interviewer_node | test=%s | remaining=%d", test_id, len(remaining))

    if not remaining:
        return {"turn_intent": "finish"}

    next_q_id = remaining[0]
    answered_count = len(test_answered.get(test_id, []))
    total_qs = len(TEST_REGISTRY[test_id]["questions"])
    system = get_interviewer_prompt(
        age_group=state.get("age_group", "Adult"),
        symptom=TEST_REGISTRY[test_id]["questions"][next_q_id],
        progress=f"Question {answered_count + 1} of {total_qs}",
        prev_response=last_human(state.get("messages", [])) or "None — this is the first question.",
        user_name=state.get("user_name", "there"),
        profession=state.get("profession", "not specified"),
        user_context=state.get("user_context", ""),
        conversation_window=build_conversation_window(state.get("messages", [])),
        answered_summary=build_answered_summary(
            test_id, test_answered, state.get("test_scores", {})
        ),
    )
    llm = _get_llm(temperature=0.75)
    resp = _invoke(llm, [SystemMessage(content=system)], node="interviewer")
    _log.debug("← interviewer_node | q=%d", next_q_id)
    return {
        "current_question_id": next_q_id,
        "messages":    [AIMessage(content=resp.content)],
        "turn_intent": "waiting",
    }


def clarify_node(state: AgentState) -> dict:
    test_id = state["current_test"]
    q_id    = state["current_question_id"]
    symptom = TEST_REGISTRY[test_id]["questions"].get(q_id, "")
    _log.debug("→ clarify_node | test=%s | q=%d", test_id, q_id)

    clarify_key = f"{test_id}:{q_id}"
    new_attempts = {
        **state.get("clarify_attempts", {}),
        clarify_key: state.get("clarify_attempts", {}).get(clarify_key, 0) + 1,
    }
    llm = _get_llm(temperature=0.5)
    resp = _invoke(
        llm,
        [SystemMessage(content=get_clarify_prompt(
            symptom=symptom,
            user_name=state.get("user_name", "there"),
            prev_response=last_human(state.get("messages", [])),
        ))],
        node="clarify",
    )
    return {
        "messages":         [AIMessage(content=resp.content)],
        "clarify_attempts": new_attempts,
        "turn_intent":      "score",
    }


def scoring_node(state: AgentState) -> dict:
    test_id  = state["current_test"]
    scores   = state.get("test_scores", {}).get(test_id, {})
    total    = compute_total(test_id, scores)
    severity = get_severity_label(test_id, total)
    _log.info(
        "scoring_node | user=%s | test=%s | total=%d | severity=%s",
        state.get("user_id"), test_id, total, severity,
    )
    return {
        "completed_tests": {test_id: total},
        "historical_scores": [{
            "date":     datetime.now().isoformat(),
            "test":     test_id,
            "score":    total,
            "severity": severity,
        }],
    }


def trend_analyzer_node(state: AgentState) -> dict:
    _log.debug("→ trend_analyzer_node | user=%s", state.get("user_id"))
    history = state.get("historical_scores", [])
    by_test: Dict[str, list] = {}
    for entry in history:
        by_test.setdefault(entry["test"], []).append(entry)

    if not any(len(v) >= 2 for v in by_test.values()):
        return {
            "trend_analysis": (
                "Initial baseline established. "
                "Longitudinal tracking begins after your next session."
            )
        }

    history_text = "\n".join(
        f"[{e['date'][:10]}] {e['test']}: {e['score']} ({e.get('severity', 'N/A')})"
        for e in history
    )
    try:
        llm = _get_llm(structured=TrendAnalysis, temperature=0.3)
        a: TrendAnalysis = _invoke(
            llm,
            [SystemMessage(content=get_trend_prompt(
                history_text=history_text,
                user_name=state.get("user_name", "the user"),
                profession=state.get("profession", "not specified"),
            ))],
            node="trend_analyzer",
        )
        summary = (
            f"**Trajectory**: {a.trajectory}\n\n"
            f"{a.summary}\n\n"
            f"**Recommendation**: {a.recommendation}"
        )
        _log.info("trend_analyzer_node | trajectory=%s", a.trajectory)
    except Exception as exc:
        _log.warning("Trend analysis failed: %s", exc)
        summary = "Trend analysis temporarily unavailable."

    return {"trend_analysis": summary}


_CASCADE_RULES = [
    # (trigger_test, score_threshold, cascade_to, message)
    (
        "TAWS-16", 32, "GAD-7",
        "Thank you for going through all of that, {name}. "
        "Given what you've shared about work, I'd like to check in on anxiety as well — "
        "the two often travel together. Just a few more questions.",
    ),
    (
        "PSS-10", 20, "GAD-7",
        "Your stress levels appear elevated, {name}. "
        "I'd like to also check in about anxiety — the two often go hand in hand. "
        "Just a few more questions.",
    ),
    (
        "GAD-7", 10, "PHQ-9",
        "Thank you for sharing that. Given your responses, I'd also like to ask "
        "a few questions about your mood overall.",
    ),
    (
        "PHQ-9", 10, "PSS-10",
        "Almost there — a few more questions about stress levels overall, "
        "then I'll put together your full summary.",
    ),
]


def router_node(state: AgentState) -> dict:
    scores = state.get("completed_tests", {})
    name   = state.get("user_name", "there")
    _log.debug("→ router_node | completed=%s", list(scores))

    for trigger, threshold, cascade_to, msg_template in _CASCADE_RULES:
        if trigger in scores and scores[trigger] > threshold and cascade_to not in scores:
            _log.info(
                "router_node | cascade %s→%s | score=%d > %d",
                trigger, cascade_to, scores[trigger], threshold,
            )
            return {
                "current_test":        cascade_to,
                "current_question_id": 0,
                "test_answered":       {cascade_to: []},
                "test_scores":         {cascade_to: {}},
                "messages":            [AIMessage(content=msg_template.format(name=name))],
                "turn_intent":         "ask",
            }

    _log.info("router_node | no cascade — proceeding to report")
    return {"turn_intent": "report"}


def _build_assessment_context(state: AgentState) -> str:
    """Merge intake summary with personal disclosures shared during assessment."""
    intake_ctx = state.get("user_context", "")
    human_msgs = [m.content for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    assessment_answers = human_msgs[INTAKE_TOTAL:]
    if assessment_answers:
        disclosed = " | ".join(assessment_answers[:_MAX_REPORT_ASSESSMENT_MSGS])
        return f"{intake_ctx}\n\nAdditional context shared during assessment:\n{disclosed}"
    return intake_ctx


def report_generator_node(state: AgentState) -> dict:
    _log.debug("→ report_generator_node | user=%s", state.get("user_id"))
    scores = state.get("completed_tests", {})
    trend  = state.get("trend_analysis", "No historical data available.")

    score_lines = [
        f"  • {TEST_REGISTRY.get(tid, {}).get('name', tid)}: "
        f"{sc}/{TEST_REGISTRY.get(tid, {}).get('max_score', '?')} "
        f"({get_severity_label(tid, sc)})"
        for tid, sc in scores.items()
    ]

    system = get_report_prompt(
        user_name=state.get("user_name", state.get("user_id", "there")),
        age_group=state.get("age_group", "Adult"),
        profession=state.get("profession", "Not specified"),
        user_context=_build_assessment_context(state),
        score_summary="\n".join(score_lines),
        trend=trend,
    )
    llm = _get_llm(temperature=0.4)
    report = _invoke(llm, [SystemMessage(content=system)], node="report_generator").content

    # Append crisis resource block if PHQ-9 item 9 (suicidal ideation) scored > 0
    phq_scores = state.get("test_scores", {}).get("PHQ-9", {})
    if "PHQ-9" in scores and phq_scores.get(9, 0) > 0:
        _log.warning(
            "PHQ-9 Q9 > 0 for user=%s — appending crisis resources to report",
            state.get("user_id"),
        )
        report += (
            "\n\n---\n"
            "⚠️ **Important Notice**: Your responses indicated some thoughts about death or self-harm. "
            "Please speak with a mental health professional as soon as possible.\n\n"
            "**Immediate support (India)**:\n"
            "- Tele-MANAS: **14416** (24/7, free)\n"
            "- iCall (TISS): **9152987821**\n"
            "- Vandrevala Foundation: **1860-2662-345**"
        )

    _log.info("← report_generator_node | user=%s | report generated", state.get("user_id"))
    return {
        "final_report": report,
        "messages":     [AIMessage(content=report)],
        "turn_intent":  "report_done",
        "turn_phase":   "done",
    }


def crisis_node(state: AgentState) -> dict:
    name     = state.get("user_name", "")
    greeting = f"{name}, " if name else ""
    _log.warning("crisis_node invoked | user=%s", state.get("user_id"))
    msg = (
        f"💙 {greeting}I hear you, and I'm really glad you're here right now.\n\n"
        "What you're feeling matters deeply. You deserve real, in-person support.\n\n"
        "**Please reach out right now:**\n\n"
        "🇮🇳 **India — Free, 24/7**\n"
        "- **Tele-MANAS** (Govt. of India): **14416**\n"
        "- **iCall** (TISS Mumbai): **9152987821**\n"
        "- **Vandrevala Foundation**: **1860-2662-345**\n"
        "- **NIMHANS**: **080-46110007**\n\n"
        "🌍 **International**\n"
        "- Crisis Text Line: Text **HOME** to **741741** (US/UK/Canada)\n"
        "- Befrienders Worldwide: https://www.befrienders.org\n\n"
        "🚨 **Immediate danger**: Call **112** (India) or your local emergency number.\n\n"
        "You are not alone. Things can get better. 💙"
    )
    return {
        "is_crisis":    True,
        "final_report": msg,
        "messages":     [AIMessage(content=msg)],
        "turn_intent":  "report_done",
        "turn_phase":   "done",
    }


# ── Routing functions ────────────────────────────────────────────────────────

def _route_after_intake_score(state: AgentState) -> str:
    return "triage" if state.get("turn_intent") == "triage" else "intake"


def _route_after_scorer(state: AgentState) -> str:
    intent = state.get("turn_intent", "ask_next")
    if intent == "clarify":
        return "clarify"
    if intent == "finish":
        return "scoring"
    return "interviewer"


def _route_after_router(state: AgentState) -> str:
    return "interviewer" if state.get("turn_intent") == "ask" else "report_generator"


def _route_guardian(state: AgentState) -> str:
    if state.get("is_crisis") or state.get("turn_intent") == "crisis":
        return "crisis_intervention"
    if state.get("turn_phase") == "intake":
        if state.get("turn_intent") not in ("ask", "ask_intake"):
            return "intake_score"
        return "intake"
    if state.get("turn_phase") == "triage":
        return "triage"
    if state.get("turn_intent") == "score":
        return "score_response"
    return "interviewer"


# ── Graph factory ────────────────────────────────────────────────────────────

def build_graph():
    """Compile and return the full LangGraph assessment workflow."""
    wf = StateGraph(AgentState)

    wf.add_node("intake",              intake_node)
    wf.add_node("intake_score",        intake_score_node)
    wf.add_node("triage",              triage_node)
    wf.add_node("guardian",            guardian_node)
    wf.add_node("score_response",      score_response_node)
    wf.add_node("interviewer",         interviewer_node)
    wf.add_node("clarify",             clarify_node)
    wf.add_node("scoring",             scoring_node)
    wf.add_node("trend_analyzer",      trend_analyzer_node)
    wf.add_node("router",              router_node)
    wf.add_node("report_generator",    report_generator_node)
    wf.add_node("crisis_intervention", crisis_node)

    wf.set_entry_point("guardian")

    wf.add_conditional_edges("guardian", _route_guardian, {
        "crisis_intervention": "crisis_intervention",
        "intake_score":        "intake_score",
        "intake":              "intake",
        "triage":              "triage",
        "score_response":      "score_response",
        "interviewer":         "interviewer",
    })
    wf.add_conditional_edges("intake_score", _route_after_intake_score, {
        "triage": "triage",
        "intake": "intake",
    })
    wf.add_conditional_edges("score_response", _route_after_scorer, {
        "clarify":     "clarify",
        "scoring":     "scoring",
        "interviewer": "interviewer",
    })
    wf.add_conditional_edges("router", _route_after_router, {
        "interviewer":      "interviewer",
        "report_generator": "report_generator",
    })

    wf.add_edge("triage",              "interviewer")
    wf.add_edge("intake",              END)
    wf.add_edge("clarify",             END)
    wf.add_edge("interviewer",         END)
    wf.add_edge("scoring",             "trend_analyzer")
    wf.add_edge("trend_analyzer",      "router")
    wf.add_edge("report_generator",    END)
    wf.add_edge("crisis_intervention", END)

    return wf.compile(checkpointer=get_checkpointer())


# ── Session facade ───────────────────────────────────────────────────────────

class AssessmentSession:
    """
    High-level interface consumed by the Streamlit UI.

    One instance per user session; wraps the compiled LangGraph app
    and exposes start(), reply(), get_progress(), and get_report().
    """

    def __init__(
        self,
        user_id: str,
        provider: Literal["default", "openai"] = "default",
        openai_key: str = "",
    ) -> None:
        configure_llm(provider, openai_key)
        self.user_id   = user_id
        self.provider  = provider
        self.config    = {"configurable": {"thread_id": user_id}}
        self.app       = build_graph()
        self.is_done   = False
        self.is_crisis = False
        self.phase     = "intake"
        _log.info("AssessmentSession created | user=%s | provider=%s", user_id, provider)

    # ── Initial state ────────────────────────────────────────────────────────

    def _initial_state(self) -> AgentState:
        return {
            "user_id":               self.user_id,
            "user_name":             "",
            "age_group":             "Adult",
            "profession":            "Not specified",
            "user_context":          "",
            "intake_question_number": 1,
            "intake_complete":       False,
            "intake_conversation":   "",
            "current_test":          "",
            "current_question_id":   0,
            "test_answered":         {},
            "test_scores":           {},
            "completed_tests":       {},
            "clarify_attempts":      {},
            "historical_scores":     [],
            "messages":              [],
            "trend_analysis":        "",
            "final_report":          "",
            "is_crisis":             False,
            "turn_phase":            "intake",
            "turn_intent":           "ask_intake",
        }

    # ── Public methods ───────────────────────────────────────────────────────

    def start(self) -> str:
        """Invoke the graph with the blank initial state; return the opening message."""
        _log.info("Session started | user=%s", self.user_id)
        result = self.app.invoke(self._initial_state(), self.config)
        return self._last_ai(result)

    def reply(self, user_text: str) -> str:
        """Process one user turn; return the AI response text."""
        if self.is_done:
            return "✅ Your assessment is complete. Start a new session to begin again."

        vals = self.get_state_values()
        phase = vals.get("turn_phase", "intake")
        next_intent = "score_intake" if phase == "intake" else "score"

        result = self.app.invoke(
            {"messages": [HumanMessage(content=user_text)], "turn_intent": next_intent},
            self.config,
        )

        new_vals   = self.get_state_values()
        self.phase = new_vals.get("turn_phase", "intake")

        if new_vals.get("turn_intent") == "report_done":
            self.is_done = True
            _log.info("Assessment complete | user=%s", self.user_id)
        if new_vals.get("is_crisis"):
            self.is_crisis = True
            self.is_done   = True

        return self._last_ai(result)

    def get_state_values(self) -> dict:
        try:
            return self.app.get_state(self.config).values
        except Exception as exc:
            _log.warning("get_state_values failed for user=%s: %s", self.user_id, exc)
            return {}

    def get_report(self) -> str:
        return self.get_state_values().get("final_report", "")

    def get_progress(self) -> dict:
        vals          = self.get_state_values()
        phase         = vals.get("turn_phase", "intake")
        test_id       = vals.get("current_test", "")
        test_answered = vals.get("test_answered", {})
        answered_cnt  = len(test_answered.get(test_id, []))
        total         = len(TEST_REGISTRY.get(test_id, {}).get("questions", {})) if test_id else 0
        intake_q      = vals.get("intake_question_number", 1)
        return {
            "phase":           phase,
            "test_id":         test_id,
            "answered":        answered_cnt,
            "total":           total,
            "completed_tests": vals.get("completed_tests", {}),
            "intake_q":        min(intake_q - 1, INTAKE_TOTAL),
            "intake_total":    INTAKE_TOTAL,
            "user_name":       vals.get("user_name", ""),
            "profession":      vals.get("profession", ""),
            "age_group":       vals.get("age_group", ""),
        }

    # ── Internal ─────────────────────────────────────────────────────────────

    @staticmethod
    def _last_ai(result: dict) -> str:
        for m in reversed(result.get("messages", [])):
            if isinstance(m, AIMessage):
                return m.content
        return "Something went wrong. Please try again."
