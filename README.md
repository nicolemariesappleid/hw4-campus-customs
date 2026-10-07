# Campus Customs Storefront (HW4)

A React/Vite/TypeScript storefront for Campus Customs with a FastAPI backend and a PydanticAI shop-assistant agent. The backend serves the catalogue, product images, accounts, and chat; the agent answers product, price, and stock questions using read-only lookups against the course SQLite database.

## Project layout

```
hw4/
├── AI_prompts.md          # prompts used for each problem
├── requirements.txt       # Python dependencies for the backend
├── .env.example           # placeholder settings; copy to .env
├── .gitignore
├── README.md
├── frontend/              # Vite React TypeScript app
├── backend/
│   ├── main.py            # FastAPI app — run with: uvicorn main:app --reload --port 8000
│   ├── agent.py           # PydanticAI agent, loop limits, audit trail
│   ├── models.py          # Pydantic types for requests, replies, tool results
│   ├── tools.py           # read-only catalogue/inventory lookups
│   ├── prompts/
│   │   └── prompt.md      # agent voice, safety rules, agent-loop rules
│   └── test_auth.py, test_chat.py   # integration tests (agent is faked)
└── output/
    ├── harness.md         # how the whole system works
    ├── design.md
    ├── usability.md
    ├── app_check.html     # open by double-clicking
    ├── app_check_images/  # screenshots linked from app_check.html
    └── audit_trail.json   # append-only agent-loop log
```

The agent itself is four files under `backend/`: `prompts/prompt.md`, `agent.py`, `tools.py`, and `models.py`. `main.py` is the API that runs it.

## 1. Place the data pack (not in git)

The database and product images are local-only and are ignored by git. Put the course data pack inside `hw4/` like this:

```
hw4/data/
├── campus_customs.db
└── products/              # images referenced by the catalogue
```

The backend reads `hw4/data/campus_customs.db` and serves images from `hw4/data/products/`. Nothing else needs to be configured for the data.

## 2. Add your API key

```sh
cd hw4
cp .env.example .env
```

Open `.env` and set `PORTKEY_API_KEY` to your real key. `PORTKEY_MODEL` (default `gpt-5.6-luna`), `PORTKEY_BASE_URL`, `PORTKEY_VIRTUAL_KEY`, `COOKIE_SECURE`, and `AUDIT_TRAIL_PATH` are optional. The real `.env` is git-ignored; only `.env.example` with placeholders is committed. The site still loads without a key, but the chat will report that it is not configured.

## 3. Run the back end

Requires Python 3.10+. From `hw4/backend`:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r ../requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000
```

On Windows use `.venv\Scripts\python` and `.venv\Scripts\uvicorn`. Check it at `http://localhost:8000/api/health`; the catalogue is at `http://localhost:8000/api/products`.

## 4. Run the front end

Requires Node.js 18+. In a second terminal, from `hw4/frontend`:

```sh
npm install
npm run dev
```

Open `http://localhost:5173`. The front end calls the API at `VITE_API_URL` (default `http://localhost:8000`; see `frontend/.env.example`). `npm run build` creates a production bundle in `frontend/dist/`.

Stop either server with `Ctrl+C`.

## 5. Run the tests (optional)

From `hw4`, after installing the backend requirements (no API key needed):

```sh
backend/.venv/bin/python -m unittest backend.test_auth backend.test_chat
```

## How it works (short version)

- **Accounts:** create account (first name, last name, email, password + confirm) and log in with email/password. Passwords are stored only as salted PBKDF2-HMAC-SHA256 hashes (600,000 iterations). Sessions use a random token in an HttpOnly, SameSite=Lax cookie; only its SHA-256 digest is stored. Set `COOKIE_SECURE=true` behind HTTPS.
- **Chat:** the widget posts to `POST /api/chat`. The agent uses four read-only tools (search, details, price, stock) and returns a reply plus up to three product IDs; FastAPI verifies the IDs in SQLite and rebuilds the product cards from the database. Signed-in shoppers' chats are saved and reloaded; guest chats are not stored. Product pages pass their product ID so "do you have this in yellow?" works.
- **Limits and audit:** each chat message is capped at 6 model requests, 8 tool calls, and 2,000 output tokens, plus 20 chat requests per minute per IP. Every run is appended to `output/audit_trail.json` (run start, each tool call with short args/result, run end with stop reason) and the file is never wiped between runs. It never stores message text or account details.

Full details on models, tools, safety rules, and specs are in `output/harness.md`.
