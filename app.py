"""
MindBridge — entry point and landing page.

Streamlit multi-page layout:
  app.py          → this file (landing / home)
  pages/1_Assessment.py  → the full chat assessment
  pages/2_History.py     → longitudinal history (future)
"""
from __future__ import annotations

import os
from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="MindBridge",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

from backend.ai_engine import AssessmentSession, TEST_REGISTRY, configure_llm, get_severity_label, INTAKE_TOTAL
from pages_utils.styling import inject_css, logo_html, SEV_CLS

inject_css()


# ── Session state defaults ───────────────────────────────────────────────────

def _init_session_state() -> None:
    defaults: dict = {
        "session":           None,
        "chat":              [],
        "started":           False,
        "api_ok":            False,
        "show_report_popup": False,
        "provider":          "default",   # "default" | "openai"
        "openai_key":        "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ── Sidebar ──────────────────────────────────────────────────────────────────

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(logo_html(), unsafe_allow_html=True)
        st.divider()

        st.markdown("### ⚙️ Setup")

        provider = st.radio(
            "Model provider",
            options=["default", "openai"],
            format_func=lambda x: "Default (Groq — deployed)" if x == "default" else "Custom OpenAI key",
            index=0 if st.session_state.provider == "default" else 1,
            horizontal=True,
        )
        st.session_state.provider = provider

        if provider == "default":
            if os.environ.get("API_KEY") or os.environ.get("BASE_URL"):
                st.session_state.api_ok = True
                st.success("Deployed model ready", icon="✅")
            else:
                st.session_state.api_ok = False
                st.warning("BASE_URL / API_KEY not found in .env")
            model_label = os.getenv("MODEL", "openai/gpt-oss-120b")
        else:
            key = st.text_input(
                "OpenAI API key",
                type="password",
                placeholder="sk-...",
                value=st.session_state.openai_key,
            )
            if key:
                st.session_state.openai_key = key
                st.session_state.api_ok     = True
                st.success("Key set", icon="🔑")
            elif st.session_state.openai_key:
                st.session_state.api_ok = True
                st.success("Key set", icon="🔑")
            else:
                st.session_state.api_ok = False
                st.warning("Enter your OpenAI API key")
            model_label = "gpt-4o-mini"

        st.markdown(
            f'<div style="font-size:.7rem;color:#374151;margin-top:3px">Model: {model_label}</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        # Progress (visible once a session is active)
        st.markdown("### 📊 Progress")
        session: AssessmentSession | None = st.session_state.get("session")
        if session and st.session_state.started:
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
                        <div class="sc-val">{sc}<span style="font-size:.85rem;color:#374151;font-family:'Inter',sans-serif;font-weight:400">/{maxs}</span></div>
                        <span class="sc-sev {cls}">{sev}</span>
                    </div>""", unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="color:#374151;font-size:.78rem">Start a session to track progress.</div>',
                unsafe_allow_html=True,
            )

        st.divider()
        st.markdown("### 🆘 Crisis Support")
        st.markdown("""
<div style="font-size:.73rem;color:#6b7280;line-height:2.2">

**🇮🇳 India — Free & 24/7**
- Tele-MANAS: **14416**
- iCall (TISS): **9152987821**
- Vandrevala: **1860-2662-345**
- NIMHANS: **080-46110007**

**🌍 International**
- Text HOME → **741741**
- [Befrienders.org](https://befrienders.org)

🚨 Emergency: **112**
</div>""", unsafe_allow_html=True)

        st.divider()
        if st.session_state.started:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 New Session", use_container_width=True):
                    st.session_state.session          = None
                    st.session_state.chat             = []
                    st.session_state.started          = False
                    st.session_state.show_report_popup = False
                    st.rerun()
            with col2:
                if st.button("🗑️ Clear Chat", use_container_width=True):
                    st.session_state.chat = []
                    st.rerun()


# ── Landing page ─────────────────────────────────────────────────────────────

def render_landing() -> None:
    st.markdown("""
    <div style="padding:48px 0 24px;text-align:center">
        <div style="font-size:3.8rem;margin-bottom:12px;filter:drop-shadow(0 0 24px rgba(167,139,250,0.4))">🧠</div>
        <div class="mb-logo" style="font-size:3.2rem">MindBridge</div>
        <div style="color:#4b5563;margin-top:10px;font-size:.95rem;max-width:480px;margin-left:auto;margin-right:auto;line-height:1.7">
            A personalised mental health check-in — no forms, just a real conversation.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""<div class="disclaimer">
⚠️ <strong>Please read before starting</strong><br>
• This is a <strong>screening tool only</strong> — not a clinical diagnosis or substitute for professional care.<br>
• If you are in immediate distress, call <strong>Tele-MANAS: 14416</strong> or <strong>Emergency: 112</strong>.<br>
• Your conversation is processed via OpenAI's API. Avoid sharing sensitive personal identifiers.<br>
• Not recommended for children under 13 without parental supervision.
</div>""", unsafe_allow_html=True)

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("#### How it works")
        steps = [
            ("🗣️", "**Chat with Mira** — she asks 5 short questions to understand your situation"),
            ("🎯", "**Smart triage** — AI selects the most relevant check-in for your needs"),
            ("📋", "**Answer at your pace** — natural conversation, no tick-boxes"),
            ("📊", "**Personalised report** — summary with context-aware recommendations"),
        ]
        for icon, step in steps:
            st.markdown(
                f'<div style="display:flex;gap:12px;margin:10px 0;font-size:.87rem;color:#6b7280;align-items:flex-start">'
                f'<span style="font-size:1.1rem">{icon}</span><span>{step}</span></div>',
                unsafe_allow_html=True,
            )

        st.markdown("")
        anon_id = st.text_input("Session ID (optional)", placeholder="Leave blank for anonymous")
        consent = st.checkbox("I understand this is a screening tool and I consent to proceed.")
        if not st.session_state.api_ok:
            st.warning("Add your API key in the sidebar to continue.", icon="🔑")

        st.markdown("")
        if st.button(
            "Begin Check-In →",
            use_container_width=True,
            disabled=not (consent and st.session_state.api_ok),
        ):
            uid = anon_id.strip() or f"anon_{datetime.now().strftime('%H%M%S')}"
            with st.spinner("Starting your session…"):
                session = AssessmentSession(
                    user_id=uid,
                    provider=st.session_state.provider,
                    openai_key=st.session_state.openai_key,
                )
                opening = session.start()
            st.session_state.session          = session
            st.session_state.chat             = []
            st.session_state.show_report_popup = False
            st.session_state.chat.append(("agent", opening, "intake"))
            st.session_state.started = True
            st.switch_page("pages/1_Assessment.py")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    _init_session_state()
    render_sidebar()
    render_landing()


if __name__ == "__main__":
    main()
