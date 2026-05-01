# ATG AI Chatbot — Setup Completion Report

This document maps every item from the **External Service Setup Checklist** to what was actually built and verified in this workspace.

- **Workspace:** `D:\AI Trainings\chatbot`
- **Student email (LiteLLM utilization tag):** `ravi.b@amzur.com`
- **Date completed:** April 30, 2026
- **Final state:** ✅ All 7 setup-doc sections complete; NoteTaker foundation runs end-to-end (FastAPI ↔ Supabase ↔ LiteLLM ↔ ChromaDB ↔ Google Sheets ↔ React).

---

## Section 1 — Development Environment ✅

| Tool   | Required | Installed |
|--------|----------|-----------|
| Python | 3.11+    | 3.13.3    |
| Node   | 18+      | 22.13.1   |
| npm    | 9+       | 10.9.2    |
| Git    | recent   | 2.54.0    |

- VS Code + Copilot/Copilot Chat extensions: present.
- Python virtualenv created at [backend/.venv](backend/.venv/) per the document instructions:
  ```powershell
  cd backend
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```

---

## Section 2 — Amzur LiteLLM Virtual Key ✅

- Virtual key from Siva Jamula stored in [backend/.env](backend/.env) under both `LITELLM_API_KEY` and `LITELLM_VIRTUAL_KEY` (the alias the HR test script expects).
- `LITELLM_USER_ID=ravi.b@amzur.com` is sent on every request via:
  - `user=<email>` parameter
  - `extra_body={"metadata": {...}}`
  - `extra_headers={"x-litellm-spend-logs-metadata": <json>}`
- VPN connectivity confirmed: `nslookup litellm.amzur.com` resolves.
- HR's [backend/test_litellm_setup.py](backend/test_litellm_setup.py) — **5/5 PASS**:
  - chat: `gpt-4o`, `gemini/gemini-2.5-flash`
  - streaming: `gpt-4o`
  - embeddings + batch embeddings: `text-embedding-3-large`
- All 4 expected models accessible:
  - `gpt-4o`
  - `gemini/gemini-2.5-flash`
  - `text-embedding-3-large`
  - `gemini/imagen-4.0-fast-generate-001`

> Initial `.env` shipped with `LLM_MODEL=gemini-2.0-flash` (from the doc), which the proxy rejects (`key_model_access_denied`). Corrected to `gemini/gemini-2.5-flash`.

---

## Section 3 — Supabase (PostgreSQL) ✅

- Project: `https://dtzhwbdwrmzyurfifzom.supabase.co`
- `DATABASE_URL` in [backend/.env](backend/.env) uses the `postgresql+asyncpg://` prefix per the doc.
- Password contained `@` → URL-encoded as `%40`.
- Async sync variant `DATABASE_URL_SYNC` (psycopg2) also stored, in case Alembic ever needs sync mode.
- Connection tested via [backend/test_db_connection.py](backend/test_db_connection.py): **PostgreSQL 17.6** ✅.
- `notes` table created via Alembic migration:
  ```
  alembic\versions\0a9236154fc7_create_notes_table.py
  ```
  Verified live on Supabase (`alembic upgrade head` completed without errors).

---

## Section 4 — Google Cloud OAuth 2.0 ✅

- Project: **amzur-chatbot-dev** (project number `696439815704`).
- **Google People API** enabled (originally), plus **Google Sheets API** and **Google Drive API** enabled later when needed for §7.
- OAuth consent screen: External, app `Amzur Chatbot`, in **Testing** mode.
- Test user added: `ravi.b@amzur.com`.
- OAuth client created (`amzur-chatbot-local`, type **Web application**) with:
  - Authorised JavaScript origin: `http://localhost:5173`
  - Authorised redirect URI: `http://localhost:8000/api/auth/google/callback` (character-for-character match with `.env`)
- Stored in [backend/.env](backend/.env):
  - `GOOGLE_CLIENT_ID` ends in `.apps.googleusercontent.com` ✅
  - `GOOGLE_CLIENT_SECRET` starts with `GOCSPX-` ✅
  - `GOOGLE_REDIRECT_URI` exact match ✅

> Login routes (`/api/auth/google/login`, `/api/auth/google/callback`) are not implemented yet — that's a P3 deliverable; only the credentials are required by the setup doc.

---

## Section 5 — ChromaDB ✅

- `chromadb==1.5.8` installed in venv (and pinned in [backend/requirements.txt](backend/requirements.txt)).
- `CHROMA_PERSIST_DIR=./chroma_db` set in [backend/.env](backend/.env).
- `chroma_db/` excluded by [.gitignore](.gitignore).
- Helper module [backend/app/vectorstore.py](backend/app/vectorstore.py):
  - `chromadb.PersistentClient` with the configured directory
  - **Custom `LiteLLMEmbedder`** that calls the LiteLLM proxy with `text-embedding-3-large` (per §6 — *never* call OpenAI directly)
  - Per-user collections named `user_{user_id}` (matches the doc convention)
- Smoke test [backend/test_chroma.py](backend/test_chroma.py): added 4 docs, queried *"What stores embeddings on disk?"* → returned **"ChromaDB is a local vector database that persists to disk."** ✅.

---

## Section 6 — OpenAI Embeddings via LiteLLM ✅

- Single `OpenAI` client wired to `LITELLM_PROXY_URL` lives in [backend/app/llm.py](backend/app/llm.py); reused by the chat, summarize, and Chroma layers.
- `LITELLM_EMBEDDING_MODEL=text-embedding-3-large` returned 3072-dim vectors during the LiteLLM smoke test.
- No direct OpenAI key anywhere in the codebase.

---

## Section 7 — Google Service Account (Sheets) ✅

- Service account `amzur-chatbot-sheets` created in `amzur-chatbot-dev`.
- JSON key saved **outside the repo** at:
  `C:\Users\Ravi Bandaru\Documents\amzur-secrets\amzur-chatbot-sheets.json`
- `GOOGLE_SERVICE_ACCOUNT_JSON` in [backend/.env](backend/.env) set to that file path (Option A — recommended).
- Helper [backend/app/sheets.py](backend/app/sheets.py) supports either a file path **or** an inline JSON string (Options A & B).
- Verifier [backend/test_sheets_credentials.py](backend/test_sheets_credentials.py) prints the email students must Share each sheet with:
  ```
  amzur-chatbot-sheets@amzur-chatbot-dev-494911.iam.gserviceaccount.com
  ```
- Live read confirmed: spreadsheet `1R-7Xw-gcA5bUiBb8hAi3gKFv5dX1b2Ll9qquAEnioCs` → **26 rows**.
- `*.json` excluded by [.gitignore](.gitignore) (with the doc's allow-list for `package.json`, `tsconfig.json`, `*.config.json`).

> 🔐 **Pending action — key rotation.** The original private key was pasted in chat; please delete it under *Service Accounts → Keys* and create a new JSON, then drop it at the same file path.

---

## .env (final shape)

Matches the document's "Quick Reference — All `.env` Variables" block, plus three additions:

| Added var                  | Why |
|----------------------------|-----|
| `DATABASE_URL_SYNC`        | psycopg2 fallback for Alembic if ever needed |
| `LITELLM_VIRTUAL_KEY`      | Alias the HR test script reads |
| `LITELLM_USER_ID`          | Email used for utilization tracking |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | Supabase project metadata |

---

## Foundation built on top (Siva's NoteTaker recommendation)

Refactored on May 1, 2026 to the agreed package layout (`api / services / models / schemas / ai / db / core`).

| Layer    | Files |
|----------|-------|
| Core     | [backend/app/core/config.py](backend/app/core/config.py) — pydantic-settings, loads `.env` |
| DB       | [backend/app/db/session.py](backend/app/db/session.py) — async SQLAlchemy engine + session + `Base` |
| Models   | [backend/app/models/note.py](backend/app/models/note.py) |
| Schemas  | [backend/app/schemas/note.py](backend/app/schemas/note.py), [backend/app/schemas/chat.py](backend/app/schemas/chat.py) |
| AI       | [backend/app/ai/llm.py](backend/app/ai/llm.py) — LiteLLM singleton + tracking helper. Sub-packages: `chains/`, `memory/`, `prompts/`, `rag/` |
| RAG      | [backend/app/ai/rag/vectorstore.py](backend/app/ai/rag/vectorstore.py) — Chroma + LiteLLM embeddings |
| Services | [backend/app/services/notes_service.py](backend/app/services/notes_service.py), [backend/app/services/chat_service.py](backend/app/services/chat_service.py), [backend/app/services/sheets_service.py](backend/app/services/sheets_service.py) — **all business logic** |
| API      | [backend/app/api/notes.py](backend/app/api/notes.py), [backend/app/api/chat.py](backend/app/api/chat.py), [backend/app/api/sheets.py](backend/app/api/sheets.py) — **HTTP only**, delegate to services |
| Entry    | [backend/app/main.py](backend/app/main.py) — FastAPI app, CORS, `/api/health`, includes `api_router` |
| Migration| [backend/alembic.ini](backend/alembic.ini), [backend/alembic/env.py](backend/alembic/env.py), `versions/0a9236154fc7_create_notes_table.py` |
| Frontend | [frontend/src/App.tsx](frontend/src/App.tsx), [frontend/src/lib/api.ts](frontend/src/lib/api.ts), [frontend/src/types/index.ts](frontend/src/types/index.ts), pages in [frontend/src/pages/](frontend/src/pages/), hooks in [frontend/src/hooks/](frontend/src/hooks/), components in [frontend/src/components/](frontend/src/components/) (`chat/`, `attachments/`, `auth/`) |

### HTTP endpoints exposed

| Method | Path                              | Purpose                                |
|--------|-----------------------------------|----------------------------------------|
| GET    | `/api/health`                     | Status + active model                  |
| GET    | `/api/notes`                      | List notes                             |
| POST   | `/api/notes`                      | Create note                            |
| GET    | `/api/notes/{id}`                 | Get one note                           |
| PATCH  | `/api/notes/{id}`                 | Update                                 |
| DELETE | `/api/notes/{id}`                 | Delete                                 |
| POST   | `/api/chat`                       | LiteLLM chat completion                |
| POST   | `/api/summarize`                  | LiteLLM summary, persisted to the note |
| GET    | `/api/sheets/service-account`     | Returns the email to share sheets with |
| GET    | `/api/sheets/{spreadsheet_id}`    | Returns all rows of a worksheet        |

### End-to-end runs verified

- `GET /api/health` → 200, model `gemini/gemini-2.5-flash`
- `POST /api/notes` → 201, row id=1 in Supabase
- `POST /api/summarize {note_id:1}` → 200, AI summary persisted
- `POST /api/chat` → 200, "The chat endpoint is functional." (12 prompt / 30 completion tokens)
- ChromaDB query → returned correct top match
- `GET /api/sheets/<id>?worksheet=0` → 200, 26 rows

---

## Tests / verifiers

| File | What it checks |
|------|----------------|
| [backend/test_setup.py](backend/test_setup.py)             | All 18 setup-checklist gates (env vars, formats, DB ping, model list) |
| [backend/test_litellm_setup.py](backend/test_litellm_setup.py) | HR-supplied LiteLLM smoke test (5/5 pass) |
| [backend/test_db_connection.py](backend/test_db_connection.py) | Single `select version()` against Supabase |
| [backend/test_chroma.py](backend/test_chroma.py)              | Chroma persist + add + query + cleanup |
| [backend/test_sheets_credentials.py](backend/test_sheets_credentials.py) | Loads service account & prints `client_email` |

Run them any time:

```powershell
cd D:\AI Trainings\chatbot\backend
.\.venv\Scripts\Activate.ps1
python test_setup.py
python test_litellm_setup.py
python test_db_connection.py
python test_chroma.py
python test_sheets_credentials.py
```

---

## How to run

```powershell
# Backend
cd D:\AI Trainings\chatbot\backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head            # one-time per migration
uvicorn app.main:app --reload   # http://localhost:8000  (Swagger: /docs)
```

```powershell
# Frontend (separate terminal)
cd D:\AI Trainings\chatbot\frontend
npm run dev                      # http://localhost:5173
```

---

## Issues encountered & resolutions

| Issue | Resolution |
|-------|-----------|
| Doc had `LLM_MODEL=gemini-2.0-flash`; proxy rejected with `key_model_access_denied` | Switched to `gemini/gemini-2.5-flash` (and `gemini/imagen-4.0-fast-generate-001` for images) — names returned by `/v1/models` |
| `Bravi@Amzur` password broke `DATABASE_URL` parsing | URL-encoded `@` as `%40` |
| Alembic crashed: `invalid interpolation syntax in '...%40...'` | Escaped `%` as `%%` when calling `config.set_main_option` in `alembic/env.py` |
| `npm create vite` hung mid-prompt | Used `npx create-vite@latest frontend --template react-ts` instead (per doc's note) |
| `/api/sheets/...` returned 502 | Underlying error: **Google Sheets API not enabled** in the project. Enabled both Sheets API and Drive API; passed |

---

## Deferred / not in scope of the setup doc

- Google OAuth login flow (`/api/auth/google/login`, `/api/auth/google/callback`) — to be wired in **P3**
- Authentication middleware / JWT issuance for users — to be added when the project prompts arrive
- Document upload + embedding pipeline that uses the per-user Chroma collections — **P7** scope
- Service-account key rotation (manual, you)

---

_End of report._
