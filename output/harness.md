# Campus Customs Harness

This file explains how the Campus Customs storefront and its shop-assistant agent fit together: the database, the front end, the FastAPI backend, the PydanticAI agent loop, its typed models, tools, safety rules, limits, and audit trail.

## System at a glance

```
Browser (React/Vite, frontend/src/App.tsx)
   │  fetch JSON, session cookie (HttpOnly) on /api routes
   ▼
FastAPI (backend/main.py)  ──►  SQLite (data/campus_customs.db)
   │  POST /api/chat                 catalogue · inventory · users · auth_sessions · chat_messages
   ▼
PydanticAI agent loop (backend/agent.py)
   │  instructions: backend/prompts/prompt.md + verified runtime context
   │  model: gpt-5.6-luna via Portkey (OpenAI-compatible)
   │  tools: backend/tools.py (4 read-only catalogue/inventory lookups)
   │  types:  backend/models.py (ChatReply output, typed lookup results)
   ▼
Audit trail (append_audit in backend/agent.py → output/audit_trail.json, append-only)
```

One chat message is one **agent run**:

1. The chat widget posts `{message, history, page_context_product_id}` to `POST /api/chat`.
2. FastAPI rate-limits the IP, resolves the shopper from the session cookie (if any), verifies the page product against SQLite, assigns a `run_id`, and writes a `run_start` audit entry.
3. The agent loop runs: the model reads the instructions and history, may call up to 8 read-only tools (each logged as a `tool_call`), and must finish with a `ChatReply` (reply text + up to 3 product IDs) within 6 model requests.
4. FastAPI validates every returned product ID against SQLite and rebuilds the product cards from the database, saves the turn for signed-in shoppers, writes a `run_end` entry with the stop reason, and returns `ChatResponse` to the browser.

## How to run it

First place the local data pack so that `hw4/data/campus_customs.db` and `hw4/data/products/` exist (they are not in git), and copy `.env.example` to `.env` in `hw4/` with your real `PORTKEY_API_KEY`.

**Back end** (FastAPI + agent), from `hw4/backend`:

```sh
python3 -m venv .venv                      # first time only
.venv/bin/python -m pip install -r ../requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000
```

`hw4/.env` holds `PORTKEY_API_KEY=...`. Optional: `PORTKEY_MODEL`, `PORTKEY_BASE_URL`, `PORTKEY_VIRTUAL_KEY`, `COOKIE_SECURE=true` (HTTPS only), `AUDIT_TRAIL_PATH` (moves the audit file; tests use this). Check it is up at `http://localhost:8000/api/health`; products are at `http://localhost:8000/api/products`.

**Front end** (React/Vite/TypeScript), in a second terminal from `hw4/frontend`:

```sh
npm install                                # first time only
npm run dev
```

Open `http://localhost:5173`. The front end calls the API at `VITE_API_URL` (default `http://localhost:8000`, see `frontend/.env.example`). `npm run build` makes a production bundle in `frontend/dist/`.

**Tests**, from `hw4` (no model key needed; the agent is faked):

```sh
backend/.venv/bin/python -m unittest backend.test_auth backend.test_chat
```

To stop either server press `Ctrl+C` in its terminal.

## Database tables and fields

Database: `hw4/data/campus_customs.db` (local data pack, not committed)

Each field below is listed with why it matters to the shop or chatbot.

## `catalogue`
Product descriptions and searchable product details. The `product_id` connects each catalogue entry to its inventory rows.

- `product_id` (TEXT, primary key): Identifies a product and links its sizes and stock in `inventory`.
- `name` (TEXT): Gives the chatbot the product name to show in recommendations and answers.
- `garment_type` (TEXT): Lets the chatbot filter and recommend by clothing type.
- `description` (TEXT): Provides product details for accurate customer answers.
- `colors` (TEXT): Helps shoppers find products in their preferred colors.
- `search_tags` (TEXT): Supports matching informal or alternate search terms to products.
- `image_file_path` (TEXT): Points to the product image the chatbot or shop interface can display.
- `price` (REAL): Lets the shop show prices and the chatbot answer cost questions or compare products.

## `inventory`
Stock quantities by product and size. Each product-size pair is unique.

- `id` (INTEGER, primary key): Identifies an inventory row for database updates.
- `product_id` (TEXT, foreign key to `catalogue.product_id`): Ties stock to the product shoppers recognize.
- `size` (TEXT): Identifies which size the quantity applies to, so availability answers are specific.
- `quantity` (INTEGER): Shows how many units are in stock and whether a size can be ordered.

## `users`
Shopper account records. The schema stores password hashes rather than plaintext passwords.

- `id` (INTEGER, primary key): Identifies a user and links their chat messages.
- `name` (TEXT): Stores the account's display name for personalized shop interactions.
- `email` (TEXT, unique): Identifies the account for sign-in and account-related communication.
- `password_hash` (TEXT): Supports password verification without storing the original password; it must remain private.
- `created_at` (TEXT): Records when the account was created, useful for account history and support.
- `first_name` (TEXT): Provides a first-name value for greetings or account display when available.
- `last_name` (TEXT): Provides a last-name value for account display or support when available.

## `chat_messages`
Conversation history, associated with a user through `user_id`.

- `id` (INTEGER, primary key): Identifies a message row for retrieving or managing chat history.
- `user_id` (INTEGER, foreign key to `users.id`): Associates a message with its account's conversation history.
- `role` (TEXT): Distinguishes who sent the message, such as the user or chatbot, so the conversation is interpreted in order.
- `content` (TEXT): Stores the message text that the chatbot uses as conversation context.
- `products_json` (TEXT, nullable): Can store product data associated with a message, supporting product recommendations or references.
- `created_at` (TEXT): Records when a message was sent, allowing chat history to be ordered by time.

## SQLite bookkeeping: `sqlite_sequence`
SQLite maintains this internal table because the database uses `AUTOINCREMENT`. It tracks the latest generated integer IDs; it is database bookkeeping, not shop or chatbot content.

- `name` (TEXT): Names the table whose generated ID is being tracked.
- `seq` (INTEGER): Stores the last generated ID value for that table.

## Authentication

The React account forms send registration and login requests to the FastAPI backend. Registration requires first name, last name, email, password, and matching password confirmation; confirmation is checked in the browser and is never sent or stored. New passwords must be at least 12 characters. Login accepts email and password. Email addresses are trimmed and lowercased before lookup. Invalid login attempts receive the same generic error whether the email or password was wrong.

The `users` table stores `first_name`, `last_name`, a combined display `name`, normalized unique `email`, `created_at`, and `password_hash`. It never stores the original password. New passwords are hashed with PBKDF2-HMAC-SHA256 using a fresh random salt and 600,000 iterations. The test account's older three-part PBKDF2 hash is verified using its legacy 120,000-iteration format, then upgraded to the 600,000-iteration format after a successful login. Password comparisons use constant-time comparison.

Successful registration and login issue a cryptographically random 30-day session token in an HttpOnly, SameSite=Lax cookie scoped to `/api/auth`. JavaScript, including the chat widget, cannot read this cookie. The `auth_sessions` table stores only a SHA-256 digest of the token, its user ID, and creation/expiration timestamps; logout deletes the server-side session and clears the cookie. Session records are linked to users and expired records are cleaned up during new sign-ins. The API returns only public account fields and never returns `password_hash`.

`COOKIE_SECURE` is disabled for local HTTP development and must be set to `true` when deploying over HTTPS. Production must use HTTPS for both the storefront and API. The database file still contains sensitive account data and must be access-controlled, backed up securely, and never exposed as a downloadable static asset. Password hashing and HttpOnly cookies reduce risk but do not make an application immune to compromise; production also needs HTTPS, secret and database access controls, rate limiting, monitoring, and routine dependency updates.

## Chatbot, Frontend, and FastAPI

The floating React chat widget in `frontend/src/App.tsx` sends `POST http://localhost:8000/api/chat` with JSON shaped as `{ "message": "shopper question", "history": [{ "role": "user" | "assistant", "content": "prior turn" }] }`. It sends at most eight prior turns. Each message and history content is limited to 1,200 characters by Pydantic request models. The request does not include the auth cookie or account information. For a category question such as "what hoodies do you have?", the agent uses `search_shop_catalogue` and returns structured `ChatProductMatch` entries (`product_id`, `match_reason`) in `ChatReply.product_matches`, up to three matches. These are only the agent's selection signals, not display data. The API validates each ID against SQLite, hydrates each exact record into the typed `ProductCard` using the current catalogue and inventory values, and sends those cards in `ChatResponse.products`. The frontend appends the cards beneath the reply using the same `ProductCard` component used by the main catalogue. Each card links to `/products/{product_id}`, the existing single-item detail route; the detail page then shows the large image, full description, price, colors, and live size/quantity records. Product images load from `/images/{image_name}`.

The API route is implemented in `backend/main.py` as an asynchronous `POST /api/chat` handler. It limits requests to 20 per minute per client IP in the current single-process development server. It calls the agent asynchronously and responds with the typed `ChatResponse`: a reply string and up to three product cards. The route accepts only IDs in the agent's structured `product_matches`, checks each ID against the SQLite `catalogue`, and rebuilds card name, price, description, image URL, color, and size/quantity data from the database. Unknown or invented IDs are omitted. Authenticated user/assistant turns are persisted to `chat_messages`; guest chat remains in widget memory only. See **User Chat History and Runtime Context** for the full behavior.

The agent is in `backend/agent.py`. On import it reads the complete system instructions from `backend/prompts/prompt.md`; the prompt contains Campus Customs voice, product-use guidance, privacy rules, prompt-injection defenses, prohibited data handling, and operational/safety boundaries. Agent construction is lazy on the first chat request. It uses PydanticAI's `Agent` with structured `ChatReply` output and an OpenAI-compatible `OpenAIChatModel` routed through Portkey at `https://api.portkey.ai/v1` by default. The model defaults to `gpt-5.6-luna` and can be overridden with `PORTKEY_MODEL`; `PORTKEY_BASE_URL` can override the gateway URL. The key is read only from `PORTKEY_API_KEY` after loading `hw4/.env`; it is never returned to the browser. An optional `PORTKEY_VIRTUAL_KEY` is forwarded to the gateway as `x-portkey-virtual-key`.

### User Chat History and Runtime Context

The session cookie is HttpOnly, SameSite=Lax, and scoped to `/api`, so the browser sends the same credential to login/session and chat/history routes without exposing it to React. The chat frontend never sends a user ID, name, or email as an identity claim. FastAPI hashes the cookie token, validates it against `auth_sessions`, and joins to `users` to determine whether a request belongs to a logged-in shopper.

For an authenticated shopper, FastAPI stores each submitted user message and corresponding assistant reply in the existing `chat_messages` table, keyed by the verified `user_id`. The assistant row's `products_json` stores the API-validated product-card snapshot associated with that reply, so previous result cards can be rendered when history is reopened. Only the newest 30 exchanges (up to 60 message rows) are retained per user; older rows are pruned after a new turn is saved. `GET /api/chat/history` returns the newest saved rows in chronological order, only for the user resolved from the current valid session. After logout or for any guest, it returns `authenticated: false` and no history. Guest conversations stay in widget memory for the current page session only and are never inserted into `chat_messages`.

The PydanticAI dependency object `ShopDependencies` in `backend/agent.py` carries three explicit run-scoped values: `database_path` (the fixed server-side SQLite path), optional `customer`, and optional `current_product`. For authenticated runs, `customer` contains only `name` and `email` read from the verified `users` row; guests receive `customer=None`. The system instructs the agent to use a verified name sparingly and never disclose the email unless the shopper asks about their own account. No password hash, session token, or user-supplied identity is put in agent dependencies.

On a product detail route, the chat widget reads the `/products/{product_id}` slug from React Router and sends it as `page_context_product_id` with `POST /api/chat`. This string is an untrusted lookup hint, not product data. FastAPI queries `catalogue` (and inventory through the existing loader) for the exact ID; only a found SQLite product is passed as `current_product`. The agent can then resolve references such as "this" or "it" to the verified product ID and must still call the specific details, price, or stock tool for facts. An invalid ID yields no current-product context. On non-product pages, the field is omitted and the agent receives `current_product=None`.

For authenticated chats, prior conversation messages sent to PydanticAI are loaded from `chat_messages` using the server-verified user ID, not trusted from browser-supplied history. For guest chats, the widget sends its bounded in-memory transcript for the current session. In both cases the current message and selected conversational context are sent to Portkey for inference, while the local database persistence rule remains authenticated-users-only.

`backend/tools.py` exposes four model-callable, read-only tools for authoritative product information. All lookups query the attached `campus_customs.db`; the model is instructed to use tools instead of trusting its training knowledge, browser conversation history, or values mentioned by a shopper.

### Agent tools and return fields

1. `search_shop_catalogue(query, garment_type?)` searches `catalogue` fields `name`, `garment_type`, `description`, `colors`, `search_tags`, and `product_id`, returning up to four matches as `ProductCard` records. Search weights product name and ID above incidental description matches, so a specific item outranks a generic match. `product_id` identifies the exact row and is required for subsequent lookups; `name` is the readable product identity for the shopper; `garment_type` supports filtering and helps distinguish similarly named merchandise; `description` and `colors` let the agent answer discovery questions from the actual catalogue; `price` gives a useful initial snapshot but is not sufficient for a price answer without the dedicated price lookup; `image_url` connects a recommendation to its shop image; `sizes` carries current inventory records for display and establishes which sizes have data. The search tool uses bounded query terms and parameterized SQL.
2. `get_shop_product_details(product_id)` retrieves one exact `catalogue` record and returns `ProductDetailsLookup`: `product_id`, `name`, `garment_type`, `description`, and `colors`. The ID anchors an exact lookup and prevents ambiguous names from selecting an unrelated product; name/type identify it in the reply; the full description is the authoritative text for construction/features; colors support exact variant questions. Missing IDs return no product, never a guessed substitute.
3. `get_shop_product_price(product_id)` retrieves the exact current `catalogue.price` and returns `ProductPriceLookup`: `product_id`, `name`, `price`, and `currency` (fixed to `USD` because catalogue prices are dollar amounts). The exact ID binds price to the requested item, name labels the amount clearly, numeric `price` prevents free-form generation from changing it, and `currency` makes the denomination explicit. The prompt requires calling this tool for every price question/comparison and forbids estimating, rounding, or reusing a prior conversation value.
4. `get_shop_product_stock(product_id, size?)` reads `inventory` joined logically to the exact `catalogue` product and returns `ProductStockLookup`: `product_id`, `name`, `requested_size`, `size_records`, `availability`, and `message`. The ID/name identify which item the result is about; `requested_size` records the normalized requested size (or null for an all-sizes question); each `size_records` item is `ProductSizeStock(size, quantity, in_stock)`, where size maps the row to the shopper’s requested variant, exact integer quantity answers “how many,” and `in_stock` is derived only as `quantity > 0`. `availability` explicitly distinguishes `in_stock`, `out_of_stock`, and `unknown`, while `message` provides a directly accurate status sentence. A database row with quantity zero is explicitly out of stock; no matching size row is unknown and must not be described as available or sold out. With no requested size, the tool returns every recorded size ordered XS-to-XXL (and uncommon sizes afterward), including zero-quantity rows.

### Data grounding and answer behavior

The agent must call `search_shop_catalogue` to discover matching products. Once it has a verified `product_id`, it must call `get_shop_product_details` for description/features when asked and `get_shop_product_price` whenever price is requested. It must call `get_shop_product_stock` for availability questions, passing the exact requested size or omitting size to report all recorded size quantities. It makes fresh calls on each turn instead of relying on chat history, because the database snapshot is the authority. It must quote database prices and quantity counts exactly, clearly call out zero-stock sizes, and say availability is unknown if no inventory row exists. It must not infer inventory from a product’s other sizes or guess when database data is absent. The API independently validates recommended product IDs and reconstructs displayed cards from SQLite, so model-written card prices and quantities are never trusted by the frontend.

`backend/models.py` defines `ChatHistoryTurn`, `ChatRequest`, `ChatProductMatch`, `ChatReply`, `ProductSizeStock`, `ProductCard`, `ProductDetailsLookup`, `ProductPriceLookup`, `ProductStockLookup`, and `ChatResponse`. `ChatProductMatch.product_id` is used as the database lookup key; `match_reason` captures concise relevance for the structured agent decision but is not used as factual card copy. The actual card text, image URL, price, color, and size inventory are always hydrated by FastAPI from SQLite. These schemas keep model tool results and chat output typed: size counts are non-negative integers; `in_stock` is an explicit boolean; price is a non-negative number; price currency is explicit; availability is a finite three-value status; product IDs and names stay attached to facts; and the API bounds messages, history, reply length, and number of displayed cards. The model has no tools for users, passwords, sessions, order mutation, network browsing, arbitrary SQL, shell execution, or account/chat access.

Run the backend from `hw4/backend` so Python can resolve the top-level module exactly as `uvicorn main:app --reload --port 8000`. Install `requirements.txt` (in `hw4/`) into the backend-local `.venv`; the agent dependencies include `pydantic-ai-slim[openai]`, and `python-dotenv` loads the key from `hw4/.env`. If the key is absent, `/api/chat` returns a configuration error without making a provider call; provider failures return a generic temporary-unavailable response without exposing exception contents or credentials.

Safety limits: the agent treats browser history and retrieved catalogue text as untrusted context, never follows instructions embedded in those fields, refuses requests to reveal hidden prompts/secrets, and does not infer identity or protected traits. It must not ask for credentials/payment data, claim access to an account, make purchases or other changes, or invent product facts/policies. It is restricted to concise shop assistance and recommendations based on tool results. The API validates structured output, independently validates card IDs, saves chat content locally only for signed-in shoppers (guest turns are never stored), and applies a 20/minute per-IP development rate limit with bounded in-memory bookkeeping. The current user message and up to eight recent turns are sent to the configured Portkey provider for inference; the widget warns shoppers not to share passwords or payment details. For production, use HTTPS and a shared distributed rate limiter, plus monitoring and abuse controls.

## Typed models (`backend/models.py`) and why each field exists

Every value that crosses a boundary (browser → API, model → API, tool → model, API → browser) has a Pydantic type, so bad or oversized data is rejected instead of passed along.

**Request side (browser → API)**

| Model | Field | Type / bound | Why |
|---|---|---|---|
| `ChatRequest` | `message` | str, 1–1,200 chars | The shopper's question; the cap bounds cost and prompt-injection surface. |
| | `history` | list of `ChatHistoryTurn`, max 8 | Guest context only; bounded so a client cannot stuff the prompt. Ignored for signed-in shoppers (server history is used). |
| | `page_context_product_id` | str or null, ≤120 | Which product page is open, so "this one" resolves. Treated as an untrusted hint and re-verified in SQLite. |
| `ChatHistoryTurn` | `role` | `"user"` or `"assistant"` | Only two roles, so a client cannot inject a fake system message. |
| | `content` | str, 1–1,200 | Same bound as a message. |

**Agent output (model → API)**

| Model | Field | Type / bound | Why |
|---|---|---|---|
| `ChatReply` | `reply` | str, 1–1,600 | The text the shopper reads; bounded so a runaway answer fails validation. |
| | `product_matches` | list of `ChatProductMatch`, max 3 | The agent only *chooses* products; it never supplies display data. |
| `ChatProductMatch` | `product_id` | str, 1–120 | The key FastAPI looks up in SQLite; invented IDs are dropped. |
| | `match_reason` | str, 1–240 | Short reason for the choice; useful for review and the audit, never shown as product fact. |

**Tool results (tool → model)**

| Model | Fields | Why |
|---|---|---|
| `ProductCard` | `product_id`, `name`, `garment_type`, `description`, `price` (≥0), `image_url`, `colors`, `sizes` | One search hit with everything needed to pick a product and to render a card. Also the API's card format, so chat cards and catalogue cards are identical. |
| `ProductDetailsLookup` | `product_id`, `name`, `garment_type`, `description`, `colors` | The authoritative text for "what is it / what's it made of" questions, without price or stock so the agent cannot reuse a stale value. |
| `ProductPriceLookup` | `product_id`, `name`, `price` (≥0), `currency` (`USD`) | A number, not prose, so the price cannot be rewritten; the currency is explicit. |
| `ProductStockLookup` | `product_id`, `name`, `requested_size`, `size_records`, `availability`, `message` | `availability` is one of three values (`in_stock`, `out_of_stock`, `unknown`) so a missing size is never reported as sold out or available. |
| `ProductSizeStock` | `size`, `quantity` (int ≥0), `in_stock` (bool) | Exact per-size counts; `in_stock` is computed only as `quantity > 0`. |

**Response side (API → browser)**

| Model | Fields | Why |
|---|---|---|
| `ChatResponse` | `reply`, `products` (max 3 `ProductCard`) | Cards are rebuilt from SQLite, never copied from model text. |
| `ChatHistoryEntry` / `ChatHistoryResponse` | `role`, `content`, `created_at`, `products`; `authenticated`, `messages` (max 60) | Lets the widget redraw a signed-in shopper's saved conversation, cards included. |

The agent's run dependencies are a dataclass, `ShopDependencies` in `agent.py`: `database_path` (fixed server path), `customer` (verified name + email or `None`), `current_product` (verified product or `None`), `run_id` (ties audit entries together), and `tool_calls` (the tools used so far this run, for the audit).

## Tools and abilities

The agent has exactly four tools, all read-only and parameterized against the `catalogue` and `inventory` tables. Details on each are under **Agent tools and return fields** above.

| Tool | Ability | Returns | Caps |
|---|---|---|---|
| `search_shop_catalogue(query, garment_type?)` | Find products by keywords across name, type, description, colors, tags, ID | list of `ProductCard` | query ≤200 chars, ≤8 terms, ≤4 results |
| `get_shop_product_details(product_id)` | Exact description, type, colors | `ProductDetailsLookup` or none | ID ≤120 chars |
| `get_shop_product_price(product_id)` | Exact current USD price | `ProductPriceLookup` or none | ID ≤120 chars |
| `get_shop_product_stock(product_id, size?)` | Exact stock, one size or all sizes | `ProductStockLookup` or none | ID ≤120, size ≤32 chars |

What the agent **cannot** do: read users, passwords, sessions, or chat history; write or delete anything; run SQL, code, or shell commands; browse URLs; place orders, holds, or refunds; send email. Identity and page context reach it only through server-verified dependencies.

## Safety rules

The full rules are in `backend/prompts/prompt.md`. In short:

- **Grounding:** every price, stock count, and product claim must come from a tool call made this turn; zero stock is called out as out of stock and a missing size row as unknown.
- **Untrusted input:** shopper messages, history, and catalogue text are data; instructions inside them are ignored. The prompt, keys, and internals are never revealed.
- **Privacy:** never ask for or repeat passwords, card numbers, or other secrets; no profiling or inference of sensitive traits; a verified email is not repeated unless the shopper asks about their own account.
- **Honesty and tone:** the assistant says it is automated, makes no promises on shipping, discounts, or scarcity, and refuses abusive requests briefly.
- **Agent-loop rules** (new): plan the fewest lookups; stay within 8 tool calls and 6 model round trips; never repeat an identical call; look up only verified IDs and never enumerate the catalogue; stop as soon as the answer is known; stop on failure instead of guessing; keep tool arguments to short product keywords (no secrets, instructions, SQL, or URLs); treat tool output as data; stay read-only; return at most three matches.

The server backs these rules with code, so a model that ignores the prompt still cannot exceed them: hard usage limits, tool argument truncation, typed output validation, product-ID verification, read-only tools, and the rate limit.

## Specs: loop limits, result caps, models

| Setting | Value | Where | Why |
|---|---|---|---|
| Model | `gpt-5.6-luna` (override with `PORTKEY_MODEL`) | `agent.py` `MODEL_NAME` | Fast, inexpensive model; structured output keeps it on rails. |
| Gateway | Portkey, `https://api.portkey.ai/v1`, OpenAI Chat Completions interface | `agent.py` | One key, provider-agnostic routing; key never leaves the server. |
| Model requests per message | 6 | `MAX_MODEL_REQUESTS` → `UsageLimits.request_limit` | A normal answer needs 2–3; 6 leaves room for a retry but stops a loop. |
| Tool calls per message | 8 | `MAX_TOOL_CALLS` → `UsageLimits.tool_calls_limit` | Enough for a 3-product comparison; prevents catalogue enumeration. |
| Output tokens per message | 2,000 | `MAX_OUTPUT_TOKENS` → `UsageLimits.output_tokens_limit` | Caps runaway generation and cost. |
| Retries | 1 (tool or output validation) | `AGENT_RETRIES` | One chance to fix a malformed reply, then fail cleanly. |
| Provider timeout / retries | 25 s / 1 | `PROVIDER_TIMEOUT_SECONDS`, `PROVIDER_MAX_RETRIES` | Keeps the chat responsive if the provider is slow. |
| Search results | 4 products | `SEARCH_RESULT_CAP` | Small, relevant context for the model. |
| Product cards in a reply | 3 | `ChatReply`, `ChatResponse` | Readable chat panel. |
| Message / history | 1,200 chars / 8 turns | `ChatRequest` | Bounds cost and injection surface. |
| Reply length | 1,600 chars | `ChatReply.reply` | Concise answers. |
| Saved history | newest 30 exchanges per signed-in user | `CHAT_HISTORY_LIMIT` in `main.py` | Useful memory without unbounded growth. |
| Rate limit | 20 chat requests / minute / IP | `chat_rate_limit` in `main.py` | Abuse and cost control (single-process dev server). |
| Audit entry caps | args ≤120 chars each, result summary ≤200 chars | `agent.py` (`MAX_ARG_CHARS`, `MAX_RESULT_CHARS`) | Keeps the trail readable and small. |

When a limit is hit, PydanticAI raises `UsageLimitExceeded`; FastAPI stops the run, returns HTTP 503 with "That question needed more lookups than the assistant is allowed per message. Try asking about one item at a time.", and logs `stop_reason: "loop_limit_reached"`.

## Audit trail (`output/audit_trail.json`)

`append_audit` in `backend/agent.py` appends a record of every agent run to `output/audit_trail.json`, a JSON array. It is **append-only**: each write reads the existing entries, adds the new one, and atomically replaces the file (temp file + `os.replace`, guarded by a lock), so restarts and repeated runs never wipe earlier entries. If the file is ever unreadable it is renamed to `audit_trail.unreadable-<timestamp>.json` rather than deleted. Audit writes are best-effort: a disk error never breaks a shopper's chat.

Each run produces entries sharing one `run_id`:

| `event` | Fields |
|---|---|
| `run_start` | `time`, `run_id`, `model`, `shopper` (`guest`/`authenticated`), `message_chars`, `history_turns`, `page_product_id`, `limits` |
| `tool_call` | `time`, `run_id`, `step`, `tool`, `args` (truncated), `result` (one-line summary, e.g. `4 match(es): ...`, `basic-hoodie-big-yale: 48.0 USD`, `...: out_of_stock (S=0, M=3)`) |
| `run_end` | `time`, `run_id`, `stop_reason`, `tool_calls`, `tools_used`, `duration_ms`, plus `model_requests`, `output_tokens`, `reply_chars`, `product_cards`, `dropped_product_ids` on success, or `detail` on a limit stop |

Stop reasons: `final_reply` (normal finish), `loop_limit_reached` (a usage limit stopped the loop), or `error:<ExceptionType>` (provider or validation failure).

**Privacy:** the trail never stores the shopper's message text, name, email, session token, password, or API key; it records only the message length, whether the shopper was signed in, tool arguments (product keywords and IDs), and short result summaries. The file is a local development log; keep it out of public hosting like the database.

Example (one run):

```json
[
  {"time": "2026-10-07T20:17:22.051+00:00", "run_id": "703a31b7e7e1", "event": "run_start", "model": "gpt-5.6-luna", "shopper": "guest", "message_chars": 25, "history_turns": 0, "page_product_id": null, "limits": {"request_limit": 6, "tool_calls_limit": 8, "output_tokens_limit": 2000}},
  {"time": "2026-10-07T20:17:22.060+00:00", "run_id": "703a31b7e7e1", "event": "tool_call", "step": 1, "tool": "search_shop_catalogue", "args": {"query": "hoodie"}, "result": "4 match(es): champion-reverse-weave-hoodie-1, yale-grandpa-hoodie, yale-sports-hoodie-baseball, yale-sports-hoodie-hockey"},
  {"time": "2026-10-07T20:17:22.066+00:00", "run_id": "703a31b7e7e1", "event": "run_end", "stop_reason": "final_reply", "tool_calls": 1, "tools_used": ["search_shop_catalogue"], "duration_ms": 15, "model_requests": 2, "output_tokens": 180, "reply_chars": 240, "product_cards": ["champion-reverse-weave-hoodie-1", "yale-grandpa-hoodie"], "dropped_product_ids": []}
]
```

Tests in `backend/test_chat.py` check that runs append without wiping earlier entries, that message text is not logged, that tool calls are logged with capped arguments, and that a loop-limit stop is recorded.

