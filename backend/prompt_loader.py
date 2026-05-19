"""
Prompt loader — loads, caches, and fills markdown templates from /prompts/.

All LLM-facing prompts live in *.md files so they can be edited without
touching Python. Templates use {{key}} placeholders filled by _fill().

Public API
----------
get_prompt(prompt_id, **kwargs)   — render any named template
get_<name>_prompt(...)            — convenience wrappers
list_prompts()                    — list available IDs
reload_all()                      — bust cache (dev / hot-reload)
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet

from backend.logger import get_logger

_log = get_logger(__name__)

_HERE: Path = Path(__file__).parent          # backend/
_PROMPTS_DIR: Path = _HERE.parent / "prompts"  # MindBridge/prompts/

_PROMPT_FILE_MAP: Dict[str, str] = {
    "GUARDIAN_SEMANTIC": "guardian.md",
    "INTAKE_QUESTIONS":  "intake.md",
    "TRIAGE_DECISION":   "triage.md",
    "MAPPER_SCORE":      "mapper.md",
    "TREND_ANALYSIS":    "trend.md",
    "REPORT_FULL":       "report.md",
    "CLARIFY_AMBIGUOUS": "clarify.md",
}
_PERSONAS: FrozenSet[str] = frozenset({"CHILD", "TEEN", "GENZ", "ADULT", "SENIOR"})
_PERSONA_MAP: Dict[str, str] = {
    "Child":  "CHILD",
    "Teen":   "TEEN",
    "GenZ":   "GENZ",
    "Adult":  "ADULT",
    "Senior": "SENIOR",
}


# ── Internal helpers ─────────────────────────────────────────────────────────

def _fill(template: str, **kwargs: object) -> str:
    """Replace every {{key}} placeholder in *template* with str(*value*)."""
    for key, value in kwargs.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


@lru_cache(maxsize=32)
def _load_file(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if not path.exists():
        available = [f.name for f in _PROMPTS_DIR.glob("*.md")]
        raise FileNotFoundError(
            f"Prompt file not found: {path}\nAvailable files: {available}"
        )
    _log.debug("Loading prompt file: %s", filename)
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=5)
def _load_interviewer_section(persona: str) -> str:
    """Extract one persona section from interviewer.md by its ## header."""
    raw = _load_file("interviewer.md")
    marker = f"INTERVIEWER_{persona}"

    # Primary: ## INTERVIEWER_XXX markdown headers
    pattern = re.compile(r"^## (INTERVIEWER_\w+)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(raw))
    sections: Dict[str, str] = {
        match.group(1): raw[match.end(): matches[i + 1].start() if i + 1 < len(matches) else len(raw)].strip()
        for i, match in enumerate(matches)
    }

    # Legacy fallback: old # ═══ separator format
    if not sections:
        legacy = re.compile(r"# ═+\n# (INTERVIEWER_\w+)\n# ═+", re.MULTILINE)
        lmatches = list(legacy.finditer(raw))
        sections = {
            m.group(1): raw[m.end(): lmatches[i + 1].start() if i + 1 < len(lmatches) else len(raw)].strip()
            for i, m in enumerate(lmatches)
        }

    if marker not in sections:
        _log.warning("Persona '%s' not found in interviewer.md — returning full file", persona)
        return raw

    return sections[marker]


# ── Public API ───────────────────────────────────────────────────────────────

def reload_all() -> None:
    """Bust the in-process prompt cache (useful in development / hot-reload)."""
    _load_file.cache_clear()
    _load_interviewer_section.cache_clear()
    _log.info("Prompt cache cleared")


def get_prompt(prompt_id: str, **kwargs: object) -> str:
    """
    Render a named prompt template with the supplied keyword arguments.

    Parameters
    ----------
    prompt_id:
        One of the keys in _PROMPT_FILE_MAP, or 'INTERVIEWER_<PERSONA>'.
    **kwargs:
        Values substituted for {{key}} placeholders in the template.
    """
    if prompt_id.startswith("INTERVIEWER_"):
        persona = prompt_id.removeprefix("INTERVIEWER_")
        if persona not in _PERSONAS:
            raise KeyError(
                f"Unknown interviewer persona: '{persona}'. Valid: {sorted(_PERSONAS)}"
            )
        return _fill(_load_interviewer_section(persona), **kwargs)

    if prompt_id not in _PROMPT_FILE_MAP:
        raise KeyError(
            f"Unknown prompt ID: '{prompt_id}'.\n"
            f"Available: {list(_PROMPT_FILE_MAP) + ['INTERVIEWER_' + p for p in sorted(_PERSONAS)]}"
        )
    return _fill(_load_file(_PROMPT_FILE_MAP[prompt_id]), **kwargs)


def list_prompts() -> list[str]:
    """Return all valid prompt IDs."""
    return list(_PROMPT_FILE_MAP) + [f"INTERVIEWER_{p}" for p in sorted(_PERSONAS)]


# ── Convenience wrappers ─────────────────────────────────────────────────────

def get_guardian_prompt() -> str:
    return get_prompt("GUARDIAN_SEMANTIC")


def get_intake_prompt(conversation_so_far: str, question_number: int) -> str:
    return get_prompt(
        "INTAKE_QUESTIONS",
        conversation_so_far=conversation_so_far,
        question_number=str(question_number),
    )


def get_triage_prompt(user_profile: str, conversation: str) -> str:
    return get_prompt(
        "TRIAGE_DECISION",
        user_profile=user_profile,
        conversation=conversation,
    )


def get_interviewer_prompt(
    age_group: str,
    symptom: str,
    progress: str,
    prev_response: str = "None",
    user_name: str = "there",
    profession: str = "not specified",
    user_context: str = "No additional context available.",
    conversation_window: str = "No conversation yet.",
    answered_summary: str = "None yet.",
) -> str:
    persona = _PERSONA_MAP.get(age_group, "ADULT")
    return get_prompt(
        f"INTERVIEWER_{persona}",
        symptom=symptom,
        progress=progress,
        prev_response=prev_response,
        user_name=user_name,
        profession=profession,
        user_context=user_context,
        conversation_window=conversation_window,
        answered_summary=answered_summary,
    )


def get_mapper_prompt(
    instrument_name: str,
    symptom: str,
    scoring_label: str,
    is_reverse: bool,
    user_response: str,
    user_name: str = "the user",
    profession: str = "not specified",
    conversation_window: str = "No conversation yet.",
    clarify_attempt: int = 0,
) -> str:
    return get_prompt(
        "MAPPER_SCORE",
        instrument_name=instrument_name,
        symptom=symptom,
        scoring_label=scoring_label,
        is_reverse="YES — higher reported wellbeing = LOWER distress score" if is_reverse else "NO",
        user_response=user_response,
        user_name=user_name,
        profession=profession,
        conversation_window=conversation_window,
        clarify_attempt=str(clarify_attempt),
    )


def get_trend_prompt(
    history_text: str,
    user_name: str = "the user",
    profession: str = "not specified",
) -> str:
    return get_prompt(
        "TREND_ANALYSIS",
        history=history_text,
        user_name=user_name,
        profession=profession,
    )


def get_report_prompt(
    user_name: str,
    age_group: str,
    profession: str,
    user_context: str,
    score_summary: str,
    trend: str,
) -> str:
    return get_prompt(
        "REPORT_FULL",
        user_name=user_name,
        age_group=age_group,
        profession=profession,
        user_context=user_context,
        score_summary=score_summary,
        trend=trend,
    )


def get_clarify_prompt(
    symptom: str,
    user_name: str = "there",
    prev_response: str = "",
) -> str:
    return get_prompt(
        "CLARIFY_AMBIGUOUS",
        symptom=symptom,
        user_name=user_name,
        prev_response=prev_response,
    )
