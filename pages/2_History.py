"""
MindBridge — Longitudinal history page (placeholder).

Shows completed test scores for the current session.
Full multi-session trending requires a persistent checkpointer
(swap MemorySaver → SqliteSaver in backend/database.py).
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="MindBridge · History",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from backend.ai_engine import TEST_REGISTRY, get_severity_label
from pages_utils.styling import inject_css, SEV_CLS

inject_css()

st.markdown("## 📈 Your Assessment History")
st.markdown("---")

session = st.session_state.get("session")
if session is None:
    st.info("No active session. Start a check-in from the home page to see your results here.")
    if st.button("← Go to Home"):
        st.switch_page("app.py")
else:
    prog = session.get_progress()
    completed = prog.get("completed_tests", {})

    if not completed:
        st.markdown(
            '<div style="color:#6b7280;font-size:.9rem">No completed assessments yet.</div>',
            unsafe_allow_html=True,
        )
    else:
        cols = st.columns(min(len(completed), 4))
        for i, (tid, sc) in enumerate(completed.items()):
            sev  = get_severity_label(tid, sc)
            nm   = TEST_REGISTRY.get(tid, {}).get("name", tid)
            maxs = TEST_REGISTRY.get(tid, {}).get("max_score", "?")
            cls  = SEV_CLS.get(sev, "")
            with cols[i % 4]:
                st.markdown(f"""
                <div class="sc-card">
                    <div class="sc-name">{nm}</div>
                    <div class="sc-val">{sc}<span style="font-size:.85rem;color:#374151;
                    font-family:'Inter',sans-serif;font-weight:400">/{maxs}</span></div>
                    <span class="sc-sev {cls}">{sev}</span>
                </div>""", unsafe_allow_html=True)

    st.markdown("")
    trend = session.get_state_values().get("trend_analysis", "")
    if trend:
        st.markdown("### Trend Analysis")
        st.markdown(
            f'<div style="background:rgba(124,58,237,0.05);border:1px solid rgba(124,58,237,0.12);'
            f'border-radius:12px;padding:18px 22px;color:#ede9fe;font-size:.88rem;line-height:1.9">'
            f"{trend}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("")
    st.info(
        "Multi-session longitudinal tracking is available by swapping to a persistent "
        "checkpointer in `backend/database.py` (e.g. SqliteSaver or RedisSaver).",
        icon="ℹ️",
    )
