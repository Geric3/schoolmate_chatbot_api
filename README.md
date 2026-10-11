# Schoolmate Chatbot API (FastAPI)

Replaces the old logic embedded in `chatbot.php`. This service is stateless,
multi-tenant aware, and never talks to the browser directly — see
`php_updates/README_INTEGRATION.md` for the PHP side.

## How a question is answered

```
message
  │
  ├─ 1. moderation.py   -> refuse instantly: password requests, or a
  │                          student asking about another student
  ├─ 2. intent_service   -> regex match: grades / payment / courses /
  │       + context_builder    semester validation / teacher lookup /
  │                            announcements / teacher hours ... pulled
  │                            LIVE from the tenant's MySQL DB, scoped to
  │                            the caller's own id from the JWT
  ├─ 3. faq_service      -> chatbot_faqs table (admin-managed)
  ├─ 4. rag_service      -> chatbot_documents / chatbot_document_chunks
  │                          (reglement interieur, admin-uploaded PDFs...)
  └─ 5. llm_service      -> Groq or OpenAI, general-knowledge fallback
```

Every DB-backed answer is optionally "polished" by the LLM for tone, but the
LLM is explicitly instructed to use ONLY the numbers it's given — it never
invents a grade or a balance.

## Setup

```bash
cd schoolmate_chatbot_api
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in DB creds, JWT_SECRET, GROQ/OPENAI keys
uvicorn main:app --reload
```

`JWT_SECRET` **must** be identical to the one set in `chatbot_client.php` on
the PHP side — it's how the two services trust each other.

## Database changes

Run `migrations/001_chatbot_tables.sql` on **every tenant database**
(`universities.db_name`), and fold it into whatever script creates a new
university's database, so new tenants get the chatbot tables automatically.

## Container and continuous deployment

Run the API locally with Docker Compose:

```bash
cp .env.example .env
# Fill in the values in .env, then:
docker compose up --build
```

The container listens on port `8000` by default. Compose publishes it on
`PORT` (or `8000` if `PORT` is unset). Never commit `.env`; configure production
values as environment variables in Render.

Every push to GitHub and every pull request targeting `master` runs the
validation: GitHub Actions builds the Docker image and starts it with a test
`JWT_SECRET`, then checks `GET /health`. Only a push to `master` triggers
Render, and only after the checks pass.

To enable gated deployment:

1. Configure the Render web service to use the repository's **Docker** runtime
   and its `Dockerfile`. If the current Render service uses a different
   runtime, create a Docker web service for this repository.
2. Turn off Render's automatic deploy-on-push setting so it cannot deploy
   before GitHub Actions has validated the changes.
3. Create a Render deploy hook for the service. Add its URL in the GitHub
   repository under **Settings → Secrets and variables → Actions** as the
   `RENDER_DEPLOY_HOOK` secret.
4. Add the API's production environment variables (including `JWT_SECRET`) to
   the Render service, and make sure GitHub Actions is enabled for the repo.

After that, merges or pushes to `master` validate first, then ask Render to
deploy. A pull request never triggers the deploy hook.

## Deploying

- **Render without GitHub Actions deployment gating**: use the Docker runtime
  described above, or configure the Python build command
  `pip install -r requirements.txt` and start command
  `uvicorn main:app --host 0.0.0.0 --port $PORT`. Add the environment variables
  in the dashboard. Make sure the MySQL host's remote-access rules allow
  Render to connect.
- **PythonAnywhere**: upload the folder, create a virtualenv, install
  `requirements.txt`, and point the WSGI file at `main:app` via
  `a2wsgi`/`asgiref` (PythonAnywhere's free tier serves WSGI; wrap the ASGI
  app with `from a2wsgi import ASGIMiddleware` and expose that as
  `application`, or use their "Always-on task" + `uvicorn` on a paid plan
  which supports ASGI directly).

## Security notes baked into the code

- `db.py` only ever connects to the `db_name` found inside a **signed** JWT
  — a tampered or user-supplied db name is rejected before it reaches MySQL.
- No query in `context_builder.py` ever selects a password/secret column.
- `moderation.py` blocks password questions and cross-student lookups
  before any DB call is made, for every role.
- Admin/teacher-only endpoints (`routers/admin.py`) require `role in
  {admin, university}` from the JWT — never from a request field.
