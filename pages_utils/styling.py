"""
Reusable CSS, severity helpers, and layout constants for MindBridge pages.

All pages call inject_css() at the top (after set_page_config) to apply
the dark theme. SEV_CLS maps severity labels to CSS class names used in
score cards.
"""
from __future__ import annotations

import streamlit as st

# ── Severity label → CSS badge class ────────────────────────────────────────
SEV_CLS: dict[str, str] = {
    "Minimal":           "sv-Minimal",
    "Low":               "sv-Low",
    "Mild":              "sv-Mild",
    "Moderate":          "sv-Moderate",
    "Moderately Severe": "sv-High",
    "High":              "sv-High",
    "Severe":            "sv-Severe",
}

# ── Full application CSS ─────────────────────────────────────────────────────
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fraunces:opsz,wght@9..144,400;9..144,600&display=swap');

*, html, body { font-family: 'Inter', sans-serif; box-sizing: border-box; }

/* ── App background ── */
.stApp { background: #080c14; min-height: 100vh; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1220 0%, #0a0f1a 100%) !important;
    border-right: 1px solid rgba(255,255,255,0.05) !important;
}
section[data-testid="stSidebar"] * { color: #8b949e !important; }
section[data-testid="stSidebar"] strong { color: #c9d1d9 !important; }
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color: #e6edf3 !important; font-weight: 600 !important; }

/* ── Main column centering ── */
.main .block-container { max-width: 840px; padding: 1.5rem 1.5rem 0; }

/* ── Logo ── */
.mb-logo {
    font-family: 'Fraunces', serif;
    font-size: 2.4rem;
    font-weight: 600;
    background: linear-gradient(135deg, #a78bfa 0%, #38bdf8 60%, #34d399 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    line-height: 1.1;
}
.mb-sub { color: #4b5563; font-size: 0.82rem; margin-top: 3px; letter-spacing: .03em; }

/* ── Phase strip ── */
.phase-strip {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 14px;
    padding: 10px 18px;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    backdrop-filter: blur(8px);
}
.phase-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-intake  { background: #38bdf8; box-shadow: 0 0 8px rgba(56,189,248,0.6); }
.dot-assess  { background: #a78bfa; box-shadow: 0 0 8px rgba(167,139,250,0.6); }
.dot-done    { background: #34d399; box-shadow: 0 0 8px rgba(52,211,153,0.6); }
.phase-label { font-size: 0.75rem; color: #4b5563; }
.phase-name  { font-size: 0.75rem; font-weight: 600; color: #c9d1d9; }
.prog-bar-wrap { margin: 0 0 0 auto; flex: 1; max-width: 200px; }
.prog-bar-outer { background: rgba(255,255,255,0.07); border-radius: 8px; height: 3px; }
.prog-bar-inner { height: 3px; border-radius: 8px; transition: width 0.5s ease; }
.bar-intake { background: linear-gradient(90deg,#38bdf8,#0ea5e9); }
.bar-assess { background: linear-gradient(90deg,#7c3aed,#a78bfa); }
.prog-label { font-size: 0.68rem; color: #4b5563; text-align: right; margin-top: 4px; }

/* ── Chat area ── */
.chat-outer {
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 18px;
    background: rgba(255,255,255,0.015);
    padding: 22px 18px 14px;
    margin-bottom: 6px;
    max-height: 56vh;
    overflow-y: auto;
    scroll-behavior: smooth;
}
.chat-outer::-webkit-scrollbar { width: 3px; }
.chat-outer::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }

/* ── Bubbles ── */
.bubble-row-user  { display:flex; justify-content:flex-end; margin: 8px 0; }
.bubble-row-agent { display:flex; justify-content:flex-start; margin: 8px 0; align-items: flex-end; gap: 8px; }

.bbl {
    max-width: 74%;
    padding: 12px 18px;
    font-size: 0.88rem;
    line-height: 1.75;
    word-wrap: break-word;
    animation: fadeInUp 0.25s ease;
}
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
}
.bbl-user {
    background: linear-gradient(135deg, #7c3aed 0%, #5b21b6 100%);
    color: #fff;
    border-radius: 20px 20px 4px 20px;
    box-shadow: 0 3px 16px rgba(124,58,237,0.35);
}
.bbl-intake {
    background: rgba(56,189,248,0.07);
    border: 1px solid rgba(56,189,248,0.15);
    color: #e0f2fe;
    border-radius: 4px 20px 20px 20px;
}
.bbl-triage {
    background: rgba(52,211,153,0.07);
    border: 1px solid rgba(52,211,153,0.18);
    color: #d1fae5;
    border-radius: 4px 20px 20px 20px;
}
.bbl-agent {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.09);
    color: #e6edf3;
    border-radius: 4px 20px 20px 20px;
}
.bbl-crisis {
    background: rgba(239,68,68,0.08);
    border: 1px solid rgba(239,68,68,0.25);
    color: #fca5a5;
    border-radius: 14px;
    max-width: 92%;
}
.bbl-report {
    background: linear-gradient(135deg, rgba(124,58,237,0.06), rgba(56,189,248,0.04));
    border: 1px solid rgba(124,58,237,0.18);
    color: #ede9fe;
    border-radius: 14px;
    font-size: 0.86rem;
    line-height: 1.9;
    max-width: 96%;
    padding: 20px 24px;
}

/* ── Avatars ── */
.avatar {
    width: 30px; height: 30px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.72rem; font-weight: 700; flex-shrink: 0;
}
.av-agent  { background: rgba(124,58,237,0.2); color: #a78bfa; border: 1px solid rgba(124,58,237,0.25); }
.av-intake { background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.2); }
.av-triage { background: rgba(52,211,153,0.15); color: #34d399; border: 1px solid rgba(52,211,153,0.2); }

/* ── Typing indicator ── */
.typing-indicator {
    display: flex; align-items: center; gap: 4px;
    padding: 12px 16px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 4px 20px 20px 20px;
    width: fit-content;
}
.typing-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #a78bfa;
    animation: typingPulse 1.4s infinite ease-in-out;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; background: #7c3aed; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; background: #38bdf8; }
@keyframes typingPulse {
    0%, 60%, 100% { opacity: 0.2; transform: scale(0.8); }
    30% { opacity: 1; transform: scale(1.1); }
}

/* ── Disclaimer / crisis banner ── */
.disclaimer {
    background: rgba(245,158,11,0.06);
    border: 1px solid rgba(245,158,11,0.18);
    border-radius: 12px;
    padding: 14px 18px;
    color: #fde68a;
    font-size: 0.79rem;
    line-height: 1.9;
    margin-bottom: 20px;
}
.crisis-banner {
    background: rgba(239,68,68,0.07);
    border: 1px solid rgba(239,68,68,0.22);
    border-radius: 12px;
    padding: 12px 18px;
    color: #fca5a5;
    font-size: 0.81rem;
    margin-bottom: 14px;
}

/* ── Score cards ── */
.sc-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    padding: 13px 15px;
    margin: 7px 0;
    text-align: center;
}
.sc-val  { font-size: 1.8rem; font-weight: 700; font-family: 'Fraunces', serif; color: #e6edf3; line-height: 1.1; }
.sc-name { font-size: 0.66rem; color: #4b5563; text-transform: uppercase; letter-spacing: .07em; margin-bottom: 4px; }
.sc-sev  { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.66rem; font-weight: 600; margin-top: 5px; letter-spacing: .04em; }
.sv-Minimal, .sv-Low { background: #064e3b; color: #6ee7b7; }
.sv-Mild              { background: #78350f; color: #fcd34d; }
.sv-Moderate          { background: #7c2d12; color: #fdba74; }
.sv-High, .sv-Moderately-Severe { background: #831843; color: #f9a8d4; }
.sv-Severe            { background: #7f1d1d; color: #fca5a5; }

/* ── Profile chip ── */
.profile-chip {
    background: rgba(124,58,237,0.07);
    border: 1px solid rgba(124,58,237,0.16);
    border-radius: 10px;
    padding: 11px 14px;
    font-size: 0.76rem;
    color: #c4b5fd;
    line-height: 2;
    margin: 8px 0;
}

/* ── Inputs ── */
.stTextInput>div>div>input {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: #e6edf3 !important; border-radius: 10px !important;
}
.stChatInputContainer {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 16px !important;
}
.stChatInputContainer textarea { color: #e6edf3 !important; background: transparent !important; }

/* ── Buttons ── */
.stButton>button {
    background: linear-gradient(135deg, #7c3aed, #5b21b6) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important; font-weight: 500 !important;
    transition: all .2s !important; letter-spacing: .02em !important;
}
.stButton>button:hover { opacity: .88 !important; transform: translateY(-1px) !important; }
.stDownloadButton>button {
    background: rgba(255,255,255,0.06) !important;
    color: #c9d1d9 !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important; transition: all .2s !important;
}
.stDownloadButton>button:hover { background: rgba(255,255,255,0.1) !important; }

/* ── Dialog override ── */
div[data-testid="stDialog"] > div {
    background: #0d1220 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 20px !important; padding: 8px !important;
}

/* ── Misc ── */
h1, h2, h3 { color: #e6edf3 !important; }
label, .stMarkdown p { color: #6b7280 !important; }
hr { border-color: rgba(255,255,255,0.06) !important; }
.stCheckbox label { color: #8b949e !important; }

/* ── Markdown inside bubbles ── */
.bbl p  { margin: 0 0 0.65em 0; }
.bbl p:last-child { margin-bottom: 0; }
.bbl strong { color: inherit; font-weight: 600; }
.bbl ul, .bbl ol { margin: 0.4em 0 0.7em 0; padding-left: 1.3em; }
.bbl li { margin: 0.25em 0; line-height: 1.65; }
.bbl hr { border: none; border-top: 1px solid rgba(255,255,255,0.1); margin: 12px 0; }
.bbl-report strong { color: #c4b5fd; font-weight: 600; }
.bbl-report ul li::marker { color: #7c3aed; }
.bbl-report p + ul { margin-top: -0.2em; }
</style>
"""


def inject_css() -> None:
    """Inject the MindBridge dark-theme CSS into the current Streamlit page."""
    st.markdown(_CSS, unsafe_allow_html=True)


def logo_html(font_size: str = "2.4rem") -> str:
    """Return the MindBridge logo + tagline as an HTML string."""
    return (
        f'<div class="mb-logo" style="font-size:{font_size}">MindBridge</div>'
        '<div class="mb-sub">Evaluating the Psychometric Validity and User Engagement of '
        "LLM-Driven Adaptive Mental Health Assessments across Generational Cohorts.</div>"
    )
