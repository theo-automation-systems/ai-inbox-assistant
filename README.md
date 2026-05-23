# AI Inbox Assistant

AI-powered inbox assistant that automatically classifies, summarizes, and prioritizes 
emails to reduce daily workload.

Demo “enterprise inbox” assistant: classify, prioritize, summarize, and suggest replies via **Groq** (default, OpenAI-compatible API) or **OpenAI**, with a modular FastAPI backend and a SaaS-style Streamlit UI.

## Features

- **FastAPI backend** with typed endpoints and Pydantic validation.
- **Structured LLM analysis** (JSON schema + validation): category, priority, sentiment, summary, action items, deadlines, entities, suggested reply.
- **Dedicated LLM service** (`app/services/llm_service.py`): external prompts, retries on rate limits, robust parsing.
- **Server-side analysis cache** to avoid redundant calls (`app/services/analysis_cache.py`).
- **Fake dataset**: 30 realistic emails under `emails/` (stored on disk by topic for generation only; the UI does not filter by folder).
- **Streamlit frontend**: dark theme, search, AI-only category filters after analysis, quick stats (`—` until analyzed), JSON export (full analysis + tasks).
- **Heuristic urgency hints** (UX complement, not ML): `app/utils/urgency.py`.

## Architecture

```
project_root/
├── app/
│   ├── api/              # REST routes (/emails, /analyze, /reply)
│   ├── core/             # Configuration (pydantic-settings)
│   ├── services/         # Email repo, LLM, analysis cache
│   ├── models/           # Shared Pydantic schemas
│   ├── prompts/          # Versioned prompts (classification / extraction / reply)
│   ├── utils/            # Parse .txt emails, JSON extraction, heuristics
│   └── main.py           # FastAPI app + CORS + lifespan
├── frontend/streamlit_app.py
├── emails/               # Fake data (.txt)
├── scripts/generate_emails.py  # Regenerate files if needed
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

Main flow:

1. `.txt` files are indexed on startup (`EmailRepository.refresh`).
2. `POST /analyze` loads (or receives) an email, checks the cache, then calls the LLM (Groq or OpenAI) with validated JSON output (`EmailAnalysisResult`).
3. `POST /reply` regenerates only a reply (`reply_prompt.txt`).
4. Streamlit calls the API with `httpx` and keeps a small UI cache in `st.session_state`.

## Prerequisites

- **Python 3.12+**
- **Groq** API key ([console](https://console.groq.com/keys)) with `LLM_PROVIDER=groq`, or **OpenAI** if `LLM_PROVIDER=openai`.

## Setup

```powershell
cd ai-inbox-assistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then set GROQ_API_KEY (or OpenAI if needed)
```

### Environment variables

See `.env.example`. Main settings:

| Variable | Description |
| --- | --- |
| `LLM_PROVIDER` | `groq` (default) or `openai`. |
| `GROQ_API_KEY` | Groq key (**default** for `/analyze` and `/reply`). |
| `GROQ_MODEL` | Groq model (e.g. `llama-3.3-70b-versatile`). |
| `OPENAI_API_KEY` | If `LLM_PROVIDER=openai`. |
| `OPENAI_MODEL` | OpenAI model when used. |
| `EMAILS_DIR` | Fake emails directory (relative to project or absolute). |
| `CORS_ORIGINS` | Allowed origins for Streamlit (CSV list). |
| `STREAMLIT_API_BASE` | Backend URL for Streamlit (`http://127.0.0.1:8000` by default). |

## Run the backend

From the repo root:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Check: `GET http://127.0.0.1:8000/health` should return `{"status":"ok","emails_loaded":30}`.

Interactive docs: `http://127.0.0.1:8000/docs`.

## Run the Streamlit frontend

In a **second** terminal (venv active):

```powershell
streamlit run frontend/streamlit_app.py
```

Browser opens at `http://localhost:8501`. Adjust `STREAMLIT_API_BASE` in `.env` if needed.

Upload a single message via **Analyze upload**: `.txt` (demo `FROM`/`SUBJECT` format) or standard `.eml` exports (Outlook, Thunderbird, etc.).

## Dataset

Files live under `emails/<folder>/email_XX.txt`. To regenerate:

```powershell
python scripts/generate_emails.py
```

Expected format:

```
FROM: Name <email>
TO: recipient
SUBJECT: ...
DATE: ...
THREAD-ID: ...
ATTACHMENTS: file1.pdf, file2.png

Message body...
```

## Tests

```powershell
pytest
```

## Screenshots

Add product-demo screenshots here:

1. **Streamlit inbox** — filtered list + message panel.
2. **AI analysis cards** — priority / sentiment badges + summary.
3. **JSON export** — sample downloaded file.

*(Placeholder: replace with portfolio images when presenting.)*

## Troubleshooting

- **Missing `GROQ_API_KEY` or `OPENAI_API_KEY`** (per `LLM_PROVIDER`): `/analyze` and `/reply` return `503` with a clear message.
- **Quota / rate limit**: the LLM service retries a few times on `429`.
- **Missing `emails` directory**: the backend fails to start (`RuntimeError` on lifespan).
- **Invalid LLM output**: `503` “schema” error — regenerate or try another model.

## Possible extensions

OAuth Gmail, database, async queues, multi-tenant auth, fine-tuning: **out of MVP scope**, but the `services/` vs `api/` split keeps things extensible.

## License

See `LICENSE`.
