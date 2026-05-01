# Amzur AI Chatbot — NoteTaker Foundation

Foundation built per the ATG AI Chatbot training setup checklist + Siva's NoteTaker recommendation.
Stack: **FastAPI · SQLAlchemy (async) · Alembic · Supabase Postgres · LiteLLM proxy · React (Vite + TS)**.

## Repo layout

```
chatbot/
├─ backend/
│  ├─ .venv/                      Python virtualenv (gitignored)
│  ├─ .env / .env.example         Secrets / template
│  ├─ requirements.txt
│  ├─ alembic.ini  alembic/        Migrations (env.py loads URL from settings)
│  └─ app/
│     ├─ main.py                  FastAPI entry (CORS, /api/health, includes api_router)
│     ├─ core/                    Settings, logging, config
│     ├─ db/                      Async SQLAlchemy session factory + Base
│     ├─ models/                  SQLAlchemy ORM models (one file per resource)
│     ├─ schemas/                 Pydantic request/response (note.py, chat.py)
│     ├─ ai/
│     │  ├─ llm.py                LiteLLM client singleton + tracking helper
│     │  ├─ chains/               LCEL chains (one file per feature)
│     │  ├─ memory/               Conversation memory utilities
│     │  ├─ rag/                  ChromaDB client + ingestion / retrieval
│     │  └─ prompts/              Prompt templates (.txt / .yaml)
│     ├─ services/                Business logic (notes_service, chat_service, sheets_service)
│     └─ api/                     HTTP routers — thin, no business logic
└─ frontend/
   └─ src/
      ├─ App.tsx  main.tsx  App.css
      ├─ components/
      │  ├─ chat/                  MessageList, InputBar, ThreadSidebar
      │  ├─ attachments/           File / image / video upload components
      │  └─ auth/                  Login button, OAuth callback
      ├─ pages/                    NotesPage, ChatPage
      ├─ hooks/                    useChat, etc.
      ├─ lib/                      API client, auth helpers, utilities
      └─ types/                    Shared TypeScript interfaces
```

## One-time
1. Confirm `backend/.env` has all required keys (run `python backend/test_setup.py`).
2. VPN must be on for LiteLLM calls.

## Run backend
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head            # apply migrations to Supabase
uvicorn app.main:app --reload   # http://localhost:8000
```

Open Swagger UI at http://localhost:8000/docs.

## Run frontend (separate terminal)
```powershell
cd frontend
npm install                     # only first time
npm run dev                     # http://localhost:5173
```

The frontend calls the backend at `VITE_API_BASE` (defaults to `http://localhost:8000`, set in `frontend/.env.local`).

## Endpoints
| Method | Path                              | Purpose                                |
|--------|-----------------------------------|----------------------------------------|
| GET    | `/api/health`                     | Sanity / model info                    |
| GET    | `/api/notes`                      | List notes                             |
| POST   | `/api/notes`                      | Create note                            |
| GET    | `/api/notes/{id}`                 | Get note                               |
| PATCH  | `/api/notes/{id}`                 | Update note                            |
| DELETE | `/api/notes/{id}`                 | Delete note                            |
| POST   | `/api/chat`                       | LLM chat (LiteLLM)                     |
| POST   | `/api/summarize`                  | Summarize a stored note                |
| GET    | `/api/sheets/service-account`     | Email to Share each Google Sheet with  |
| GET    | `/api/sheets/{spreadsheet_id}`    | Read a worksheet via service account   |

## Tests
- `backend/test_setup.py` — full setup checklist validator (18 checks)
- `backend/test_litellm_setup.py` — HR's LiteLLM smoke test (5/5)
- `backend/test_db_connection.py` — DB ping
- `backend/test_chroma.py` — ChromaDB persist + LiteLLM embeddings
- `backend/test_sheets_credentials.py` — service account loader

## Architectural rules (per agreed structure)
- `app/api/` routers are HTTP-only — they call `app/services/`.
- Business logic lives in `app/services/`.
- LiteLLM is imported from `app/ai/llm.py` only — do not instantiate `OpenAI(...)` elsewhere.
- ChromaDB / RAG lives under `app/ai/rag/`. Embeddings always route through the LiteLLM proxy.
- Pydantic schemas live in `app/schemas/`, never mixed with ORM.
- Frontend HTTP lives in `src/lib/api.ts`. Components/pages must not call `fetch` directly.
- Shared TS types live in `src/types/`.

## Deferred (per setup doc)
- ChromaDB: required before P7 — `pip install chromadb` + `CHROMA_PERSIST_DIR=./chroma_db` (already in `.env`)
- Google service account JSON: required before P9
