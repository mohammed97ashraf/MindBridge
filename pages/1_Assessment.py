"""
MindBridge — Assessment chat page.

Rendered after the user consents on the landing page and an
AssessmentSession is stored in st.session_state.session.
"""
from __future__ import annotations

import time
from datetime import datetime

import markdown as md_lib
import streamlit as st

st.set_page_config(
    page_title="MindBridge · Assessment",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

from backend.ai_engine import AssessmentSession, TEST_REGISTRY, get_severity_label, INTAKE_TOTAL
from pages_utils.styling import inject_css, logo_html, SEV_CLS

inject_css()


# ── Guard: redirect to landing if no active session ─────────────────────────

if not st.session_state.get("started") or st.session_state.get("session") is None:
    st.switch_page("app.py")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_html(text: str) -> str:
    return md_lib.markdown(text, extensions=["sane_lists"])


def _add_msg(role: str, text: str, bubble: str = "agent") -> None:
    st.session_state.chat.append((role, text, bubble))


def _avatar(bubble: str) -> str:
    if bubble == "user":
        return ""
    if bubble == "intake":
        return '<div class="avatar av-intake">M</div>'
    if bubble == "triage":
        return '<div class="avatar av-triage">✦</div>'
    return '<div class="avatar av-agent">🧠</div>'


def _bubble_css(bubble: str) -> str:
    return {
        "intake": "bbl-intake",
        "triage": "bbl-triage",
        "crisis": "bbl-crisis",
        "report": "bbl-report",
    }.get(bubble, "bbl-agent")


# ── Chat rendering ───────────────────────────────────────────────────────────

def render_chat_history() -> None:
    st.markdown('<div class="chat-outer" id="chat-scroll">', unsafe_allow_html=True)
    for role, text, bubble in st.session_state.chat:
        if role == "user":
            st.markdown(
                f'<div class="bubble-row-user">'
                f'<div class="bbl bbl-user">{text}</div></div>',
                unsafe_allow_html=True,
            )
        else:
            av  = _avatar(bubble)
            css = _bubble_css(bubble)
            st.markdown(
                f'<div class="bubble-row-agent">{av}'
                f'<div class="bbl {css}">{_to_html(text)}</div></div>',
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)


def _stream_text(text: str, bubble: str) -> None:
    """Word-by-word streaming effect for AI responses."""
    css = _bubble_css(bubble)
    av  = _avatar(bubble)
    ph  = st.empty()
    buf = ""
    for i, word in enumerate(text.split()):
        buf += word + " "
        if i % 5 == 0:
            ph.markdown(
                f'<div class="bubble-row-agent">{av}'
                f'<div class="bbl {css}">{buf}▌</div></div>',
                unsafe_allow_html=True,
            )
            time.sleep(0.014)
    ph.empty()


# ── Report dialog ────────────────────────────────────────────────────────────

@st.dialog("📊 Your Check-In Results", width="large")
def _show_report_popup() -> None:
    session: AssessmentSession = st.session_state.session
    report = session.get_report()
    if not report:
        st.warning("Report not available yet.")
        return

    st.markdown(
        f'<div style="background:rgba(124,58,237,0.05);border:1px solid rgba(124,58,237,0.15);'
        f'border-radius:14px;padding:24px 28px;color:#ede9fe;font-size:0.87rem;'
        f'line-height:1.9;max-height:65vh;overflow-y:auto;">'
        f"{_to_html(report)}</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "📄 Download Report",
            data=report,
            file_name=f"mindbridge_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with c2:
        if st.button("Close", use_container_width=True):
            st.session_state.show_report_popup = False
            st.rerun()


# ── Sidebar ──────────────────────────────────────────────────────────────────

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(logo_html(), unsafe_allow_html=True)
        st.divider()

        # ── Active provider (read-only during a session) ─────────────────────
        provider = st.session_state.get("provider", "default")
        if provider == "openai":
            model_label = "gpt-4o-mini (OpenAI)"
            badge_color = "#38bdf8"
        else:
            import os as _os
            model_label = _os.getenv("MODEL", "openai/gpt-oss-120b") + " (Groq)"
            badge_color = "#34d399"
        st.markdown(
            f'<div style="font-size:.72rem;color:{badge_color};margin-bottom:4px">'
            f'⚡ {model_label}</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        st.markdown("### 📊 Progress")
        session: AssessmentSession = st.session_state.session
        prog  = session.get_progress()
        phase = prog.get("phase", "intake")

        if phase == "intake":
            iq, it = prog.get("intake_q", 0), prog.get("intake_total", INTAKE_TOTAL)
            pct = int(iq / it * 100) if it else 0
            st.markdown(f"""
            <div style="font-size:.78rem;color:#6b7280;margin-bottom:7px">
                <span style="color:#38bdf8;font-weight:700">●</span>&nbsp; Getting to know you
            </div>
            <div style="font-size:.73rem;color:#4b5563">{iq} of {it} questions</div>
            <div class="prog-bar-outer" style="margin-top:7px">
                <div class="prog-bar-inner bar-intake" style="width:{pct}%"></div>
            </div>""", unsafe_allow_html=True)

        elif phase == "assess":
            tid  = prog.get("test_id", "")
            name = TEST_REGISTRY.get(tid, {}).get("name", tid)
            ans, tot = prog.get("answered", 0), prog.get("total", 0)
            pct = int(ans / tot * 100) if tot else 0
            st.markdown(f"""
            <div style="font-size:.78rem;color:#6b7280;margin-bottom:4px">
                <span style="color:#a78bfa;font-weight:700">●</span>&nbsp; {name}
            </div>
            <div style="font-size:.73rem;color:#4b5563">{ans} of {tot} answered</div>
            <div class="prog-bar-outer" style="margin-top:7px">
                <div class="prog-bar-inner bar-assess" style="width:{pct}%"></div>
            </div>""", unsafe_allow_html=True)

        n = prog.get("user_name", "")
        p = prog.get("profession", "")
        a = prog.get("age_group", "")
        if n or p:
            st.markdown(f"""
            <div class="profile-chip">
                {"👤 <strong style='color:#c4b5fd'>" + n + "</strong><br>" if n else ""}
                {"💼 " + p + "<br>" if p else ""}
                {"👥 " + a if a else ""}
            </div>""", unsafe_allow_html=True)

        completed = prog.get("completed_tests", {})
        if completed:
            st.markdown("**Completed**")
            for tid, sc in completed.items():
                sev  = get_severity_label(tid, sc)
                nm   = TEST_REGISTRY.get(tid, {}).get("name", tid)
                maxs = TEST_REGISTRY.get(tid, {}).get("max_score", "?")
                cls  = SEV_CLS.get(sev, "")
                st.markdown(f"""
                <div class="sc-card">
                    <div class="sc-name">{nm}</div>
                    <div class="sc-val">{sc}<span style="font-size:.85rem;color:#374151;
                    font-family:'Inter',sans-serif;font-weight:400">/{maxs}</span></div>
                    <span class="sc-sev {cls}">{sev}</span>
                </div>""", unsafe_allow_html=True)

        st.divider()
        st.markdown("### 🆘 Crisis Support")
        st.markdown("""
<div style="font-size:.73rem;color:#6b7280;line-height:2.2">

**🇮🇳 India — Free & 24/7**
- Tele-MANAS: **14416**
- iCall (TISS): **9152987821**
- Vandrevala: **1860-2662-345**

**🌍 International**
- Text HOME → **741741**

🚨 Emergency: **112**
</div>""", unsafe_allow_html=True)

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 New Session", use_container_width=True):
                st.session_state.session          = None
                st.session_state.chat             = []
                st.session_state.started          = False
                st.session_state.show_report_popup = False
                st.switch_page("app.py")
        with col2:
            if st.button("🗑️ Clear Chat", use_container_width=True):
                st.session_state.chat = []
                st.rerun()


# ── Main chat view ───────────────────────────────────────────────────────────

def render_chat() -> None:
    session: AssessmentSession = st.session_state.session
    prog  = session.get_progress()
    phase = prog.get("phase", "intake")

    # Crisis banner
    if session.is_crisis:
        st.markdown("""<div class="crisis-banner">
        🆘 <strong>Crisis support active</strong> — Please call <strong>Tele-MANAS: 14416</strong>
        or <strong>Emergency: 112</strong> right now.
        </div>""", unsafe_allow_html=True)

    # Phase strip
    if not session.is_done:
        dot_cls   = "dot-intake" if phase == "intake" else "dot-assess"
        phase_lbl = {
            "intake": "Getting to know you",
            "triage": "Selecting your check-in",
            "assess": "Assessment",
        }.get(phase, "")
        prog_html = ""
        if phase == "intake":
            iq, it = prog.get("intake_q", 0), prog.get("intake_total", INTAKE_TOTAL)
            pct = int(iq / it * 100) if it else 0
            prog_html = (
                f'<div class="prog-bar-wrap">'
                f'<div class="prog-bar-outer"><div class="prog-bar-inner bar-intake" style="width:{pct}%"></div></div>'
                f'<div class="prog-label">{iq}/{it}</div></div>'
            )
        elif phase == "assess":
            ans, tot = prog.get("answered", 0), prog.get("total", 0)
            pct   = int(ans / tot * 100) if tot else 0
            tname = TEST_REGISTRY.get(prog.get("test_id", ""), {}).get("name", "")
            prog_html = (
                f'<div class="prog-bar-wrap">'
                f'<div class="prog-bar-outer"><div class="prog-bar-inner bar-assess" style="width:{pct}%"></div></div>'
                f'<div class="prog-label">{ans}/{tot} · {tname}</div></div>'
            )
        st.markdown(
            f'<div class="phase-strip">'
            f'<div class="phase-dot {dot_cls}"></div>'
            f'<span class="phase-label">Phase:</span>'
            f'<span class="phase-name">{phase_lbl}</span>'
            f"{prog_html}</div>",
            unsafe_allow_html=True,
        )

    render_chat_history()

    # Done state — action buttons
    if session.is_done and not session.is_crisis:
        st.markdown(
            '<div style="text-align:center;padding:12px 0 4px;color:#4b5563;font-size:.85rem">'
            "✅ Check-in complete</div>",
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            report = session.get_report()
            if report:
                st.download_button(
                    "📄 Download",
                    data=report,
                    file_name=f"mindbridge_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
        with c2:
            if st.button("📊 View Full Report", use_container_width=True):
                st.session_state.show_report_popup = True
                st.rerun()
        with c3:
            if st.button("🔄 New Session", use_container_width=True):
                st.session_state.session          = None
                st.session_state.chat             = []
                st.session_state.started          = False
                st.session_state.show_report_popup = False
                st.switch_page("app.py")

        if st.session_state.get("show_report_popup"):
            _show_report_popup()
        return

    if session.is_done:
        return

    # Chat input
    user_input = st.chat_input("Type your response…")
    if user_input:
        _add_msg("user", user_input, "user")

        loading_ph = st.empty()
        loading_ph.markdown(
            '<div class="bubble-row-agent">'
            '<div class="avatar av-agent">🧠</div>'
            '<div class="typing-indicator">'
            '<div class="typing-dot"></div>'
            '<div class="typing-dot"></div>'
            '<div class="typing-dot"></div>'
            "</div></div>",
            unsafe_allow_html=True,
        )

        reply = session.reply(user_input)
        loading_ph.empty()

        new_prog   = session.get_progress()
        new_phase  = new_prog.get("phase", "intake")
        new_intent = session.get_state_values().get("turn_intent", "")

        if session.is_crisis:
            bubble = "crisis"
        elif new_intent == "report_done":
            bubble = "report"
        elif new_phase == "assess" and phase == "intake":
            bubble = "triage"
        elif new_phase == "intake":
            bubble = "intake"
        else:
            bubble = "agent"

        _stream_text(reply, bubble)
        _add_msg("agent", reply, bubble)
        st.rerun()


# ── Page entry point ─────────────────────────────────────────────────────────

render_sidebar()
render_chat()
