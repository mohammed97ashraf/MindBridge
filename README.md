# MindBridge 🧠

> **Evaluating the Psychometric Validity and User Engagement of LLM-Driven Adaptive Mental Health Assessments across Generational Cohorts.**

MindBridge is a conversational mental health screening tool that replaces static tick-box forms with a natural, adaptive chat experience. It conducts clinically validated assessments (GAD-7, PHQ-9, PSS-10, TAWS-16) through an AI interviewer that adjusts its tone and questions based on the user's age, profession, and what they share during the session.

> ⚠️ **This is a research / screening tool — not a clinical diagnosis platform.** Always recommend professional consultation for Moderate or above scores.

---

## Features

- **Adaptive intake** — Mira, a warm AI coordinator, asks 5–6 questions before triaging to the right test
- **Smart triage** — LLM selects the most appropriate instrument from intake signals; falls back to keyword heuristics if the model fails
- **5 interview personas** — Child / Teen / GenZ / Adult / Senior — tone and language adapt to age group
- **4 validated instruments** — GAD-7, PHQ-9, PSS-10, TAWS-16 (Indian workforce)
- **Clinical cascade** — after each test, the engine checks whether a second test is warranted (e.g. high TAWS-16 → GAD-7)
- **Safety-first** — every user turn passes through a guardian node; hardcoded keyword scan + LLM safety check
- **Personalised report** — Markdown report with score summary, trend analysis, and profession-tailored recommendations
- **Dual-provider UI** — switch between the deployed Groq endpoint and your own OpenAI key at session start

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit 1.45 (multi-page) |
| AI workflow | LangGraph 0.4 (12-node StateGraph) |
| LLM client | LangChain-OpenAI (ChatOpenAI) |
| State persistence | LangGraph MemorySaver (in-process) |
| Prompt management | Markdown templates in `prompts/` |
| Logging | Python `logging` + `TimedRotatingFileHandler` |
| Retry | Tenacity (3-attempt exponential back-off) |

---

## Project Structure

```
MindBridge/
├── .streamlit/
│   └── config.toml          # Dark theme + server config
├── assets/                  # Drop favicon.ico here
├── backend/
│   ├── __init__.py          # Installs global exception hook
│   ├── logger.py            # get_logger() — daily rotation, 30-day retention
│   ├── database.py          # get_checkpointer() — swap persistence backend here
│   ├── prompt_loader.py     # Loads & caches prompts/*.md templates
│   └── ai_engine.py         # LangGraph workflow + AssessmentSession + configure_llm()
├── pages/
│   ├── 1_Assessment.py      # Chat interface
│   └── 2_History.py         # Session scores & trend view
├── pages_utils/
│   ├── __init__.py
│   └── styling.py           # inject_css(), SEV_CLS, logo_html()
├── prompts/                 # 8 prompt files (XML + CoT structure)
│   ├── intake.md
│   ├── triage.md
│   ├── interviewer.md       # 5 personas in one file (## INTERVIEWER_XXX sections)
│   ├── mapper.md
│   ├── report.md
│   ├── clarify.md
│   ├── guardian.md
│   └── trend.md
├── logs/                    # Auto-created at runtime
├── .env                     # Your secrets (never commit)
├── .env.template            # Copy this to .env
├── app.py                   # Entry point — landing page
└── requirements.txt
```

---

## AI Models

MindBridge supports two provider modes selectable from the sidebar at session start.

### Default — Groq (deployed)

Uses a custom base URL endpoint configured in `.env`. Designed for the deployed version of the app.

```env
BASE_URL=https://your-groq-or-proxy-endpoint/v1
API_KEY=your-api-key
MODEL=openai/gpt-oss-120b
```

The Groq endpoint requires `model_kwargs={"reasoning_effort": "low"}` which is passed automatically in this mode.

### Custom — OpenAI (user key)

Users can enter their own OpenAI API key directly in the sidebar. This path uses **gpt-4o-mini** without `reasoning_effort` (not supported by standard OpenAI).

No `.env` changes needed — the key is entered at runtime.

### Temperature guide (per node)

| Node | Temp | Why |
|---|---|---|
| Intake (Mira) | 0.65 | Warm, natural conversation |
| Interviewer | 0.75 | Most expressive — varies acknowledgments |
| Clarify | 0.50 | Brief, natural follow-up |
| Report generator | 0.40 | Warm but consistent |
| Trend analyzer | 0.30 | Analytical |
| Triage | 0.15 | Near-deterministic selection |
| Mapper / Guardian | default | Low — scoring and safety are precision tasks |

---

## Running Locally

### 1. Clone & create a virtual environment

```bash
git clone https://github.com/your-org/mindbridge.git
cd mindbridge/MindBridge
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.template .env
```

Open `.env` and fill in your values:

```env
# For the default Groq deployment
BASE_URL=https://your-endpoint/v1
API_KEY=your-key
MODEL=openai/gpt-oss-120b

# OR — just use your OpenAI key directly via the UI
# (no .env changes needed; enter the key in the sidebar)
```

### 4. Run the app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

> **Tip:** If you're using only your own OpenAI key, you can leave `.env` empty and enter the key in the sidebar's "Custom OpenAI key" option.

---

## Switching the Persistence Backend

The default `MemorySaver` keeps state in memory — it resets when the server restarts. To persist sessions across restarts, edit only **`backend/database.py`**:

```python
# SQLite (local file)
from langgraph.checkpoint.sqlite import SqliteSaver
return SqliteSaver.from_conn_string("mindbridge_sessions.db")

# Redis (production)
from langgraph.checkpoint.redis import RedisSaver
return RedisSaver.from_conn_string(os.getenv("REDIS_URL"))
```

Nothing else in the codebase needs to change.

---

## Contributing

Contributions are welcome. Please follow the conventions already in the codebase.


### Adding a new assessment instrument

1. Add an entry to `TEST_REGISTRY` in `backend/ai_engine.py` — keys: `name`, `scoring_label`, `reverse_items`, `max_score`, `thresholds`, `questions`
2. Add cascade rules (if any) to `_CASCADE_RULES` in the same file
3. Update the `TriageDecision.start_test` `Literal` type to include the new test ID
4. Update `get_triage_prompt()` context if the triage prompt references specific test names

### Editing prompts

All prompts are plain Markdown in `prompts/`. Edit them directly — no Python changes needed. The loader caches files on first read; call `backend.prompt_loader.reload_all()` to bust the cache during development.

### Changing the interviewer persona

Each persona is a `## INTERVIEWER_XXX` section in `prompts/interviewer.md`. Add a new section and a corresponding entry in `_PERSONA_MAP` inside `backend/prompt_loader.py`.

### Logging

Every module uses `_log = get_logger(__name__)`. Log levels:
- `DEBUG` — node entry/exit, scoring decisions
- `INFO` — phase transitions, test completions, provider config
- `WARNING` — LLM fallbacks, guardian flags, retried calls
- `ERROR` — exhausted retries, unexpected failures

Logs rotate daily and are retained for 30 days in the `logs/` directory.

### Opening a pull request

1. Fork the repo and create a branch: `git checkout -b feat/your-feature`
2. Make your changes and add tests if applicable
3. Ensure the app runs end-to-end: `streamlit run app.py`
4. Open a PR with a clear description of what changed and why

---

## Assessments Reference

| Instrument | Domain | Items | Scale | Reference period |
|---|---|---|---|---|
| GAD-7 | Generalised Anxiety | 7 | 0–3 | Past 2 weeks |
| PHQ-9 | Depression | 9 | 0–3 | Past 2 weeks |
| PSS-10 | Perceived Stress | 10 | 0–4 | Past 30 days |
| TAWS-16 | Work Stress (Indian workforce) | 16 | 0–4 | Past 6 months |

---

## Disclaimer

MindBridge is a **screening tool only**. It is not a substitute for professional clinical diagnosis or treatment. If you or someone you know is in crisis:

- 🇮🇳 **Tele-MANAS (India):** 14416 (24/7, free)
- **iCall (TISS):** 9152987821
- **Crisis Text Line:** Text HOME to 741741
- 🚨 **Emergency:** 112
