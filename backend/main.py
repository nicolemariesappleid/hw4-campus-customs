import json
import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Cookie, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pydantic_ai.exceptions import UsageLimitExceeded

try:
    from .agent import (
        CHAT_USAGE_LIMITS,
        MODEL_NAME,
        ShopDependencies,
        append_audit,
        build_agent,
        history_to_messages,
        short,
    )
    from .models import ChatHistoryEntry, ChatHistoryResponse, ChatRequest, ChatResponse, ProductCard
except ImportError:
    from agent import (
        CHAT_USAGE_LIMITS,
        MODEL_NAME,
        ShopDependencies,
        append_audit,
        build_agent,
        history_to_messages,
        short,
    )
    from models import ChatHistoryEntry, ChatHistoryResponse, ChatRequest, ChatResponse, ProductCard

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "campus_customs.db"
PRODUCT_IMAGE_DIR = BASE_DIR / "data" / "products"
PASSWORD_ITERATIONS = 600_000
SESSION_COOKIE = "campus_customs_session"
SESSION_DURATION = timedelta(days=30)
CHAT_HISTORY_LIMIT = 30
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

app = FastAPI(title="Campus Customs Store API", version="0.1.0")
_chat_agent = None
_chat_requests: dict[str, deque[float]] = defaultdict(deque)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_methods=["GET", "POST"],
    allow_credentials=True,
    allow_headers=["*"],
)


class AccountCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)


class AccountLogin(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return normalized


def hash_password(password: str) -> str:
    salt = secrets.token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS
    )
    encoded_digest = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${encoded_digest}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        parts = encoded_hash.split("$")
        if len(parts) == 3:
            algorithm, salt, expected_digest = parts
            iterations = 120_000
            digest_format = "hex"
        elif len(parts) == 4:
            algorithm, iterations_text, salt, expected_digest = parts
            iterations = int(iterations_text)
            digest_format = "base64"
        else:
            return False
        if algorithm != "pbkdf2_sha256" or not 1 <= iterations <= 2_000_000:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
        )
        actual_digest = (
            digest.hex()
            if digest_format == "hex"
            else base64.b64encode(digest).decode("ascii")
        )
        return hmac.compare_digest(actual_digest, expected_digest)
    except (ValueError, TypeError):
        return False


def ensure_auth_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )"""
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)"
    )


def public_user(row: sqlite3.Row) -> dict[str, Any]:
    first_name = row["first_name"] or row["name"].split(" ", 1)[0]
    last_name = row["last_name"] or ""
    return {
        "id": row["id"],
        "first_name": first_name,
        "last_name": last_name,
        "name": row["name"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


def create_session(connection: sqlite3.Connection, user_id: int, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    expires_at = datetime.now(timezone.utc) + SESSION_DURATION
    connection.execute(
        "DELETE FROM auth_sessions WHERE expires_at <= datetime('now')"
    )
    connection.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (token_hash, user_id, expires_at.strftime("%Y-%m-%d %H:%M:%S")),
    )
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(SESSION_DURATION.total_seconds()),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/api",
    )


def get_session_user(connection: sqlite3.Connection, token: str | None) -> sqlite3.Row:
    if not token:
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    ensure_auth_schema(connection)
    token_hash = hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()
    row = connection.execute(
        "SELECT users.* FROM auth_sessions "
        "JOIN users ON users.id = auth_sessions.user_id "
        "WHERE auth_sessions.token_hash = ? "
        "AND auth_sessions.expires_at > datetime('now')",
        (token_hash,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    return row


def decode_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def get_connection() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise HTTPException(status_code=503, detail="Product database is unavailable.")
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def serialize_product(row: sqlite3.Row, inventory: list[sqlite3.Row]) -> dict[str, Any]:
    image_name = Path(row["image_file_path"]).name
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "garment_type": row["garment_type"],
        "description": row["description"],
        "colors": decode_json_list(row["colors"]),
        "search_tags": decode_json_list(row["search_tags"]),
        "image_url": f"/images/{image_name}",
        "price": row["price"],
        "sizes": [
            {
                "size": stock["size"],
                "quantity": stock["quantity"],
                "in_stock": stock["quantity"] > 0,
            }
            for stock in inventory
        ],
    }


def load_products(product_id: str | None = None) -> list[dict[str, Any]]:
    with closing(get_connection()) as connection:
        if product_id is None:
            rows = connection.execute(
                "SELECT * FROM catalogue ORDER BY name COLLATE NOCASE"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM catalogue WHERE product_id = ?", (product_id,)
            ).fetchall()
        products = []
        for row in rows:
            inventory = connection.execute(
                "SELECT size, quantity FROM inventory WHERE product_id = ? "
                "ORDER BY CASE size "
                "WHEN 'XS' THEN 1 WHEN 'S' THEN 2 WHEN 'M' THEN 3 "
                "WHEN 'L' THEN 4 WHEN 'XL' THEN 5 WHEN 'XXL' THEN 6 "
                "ELSE 7 END, size",
                (row["product_id"],),
            ).fetchall()
            products.append(serialize_product(row, inventory))
        return products


def persist_chat_turn(
    user_id: int,
    user_message: str,
    assistant_message: str,
    products: list[ProductCard],
) -> None:
    products_json = json.dumps(
        [product.model_dump() for product in products],
        separators=(",", ":"),
    )
    with closing(get_connection()) as connection:
        connection.execute(
            "INSERT INTO chat_messages (user_id, role, content) VALUES (?, 'user', ?)",
            (user_id, user_message),
        )
        connection.execute(
            "INSERT INTO chat_messages (user_id, role, content, products_json) "
            "VALUES (?, 'assistant', ?, ?)",
            (user_id, assistant_message, products_json),
        )
        connection.execute(
            "DELETE FROM chat_messages WHERE user_id = ? AND id NOT IN ("
            "SELECT id FROM chat_messages WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?)",
            (user_id, user_id, CHAT_HISTORY_LIMIT * 2),
        )
        connection.commit()


def load_chat_history(user_id: int) -> list[ChatHistoryEntry]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT role, content, products_json, created_at FROM ("
            "SELECT id, role, content, products_json, created_at FROM chat_messages "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?) ORDER BY id",
            (user_id, CHAT_HISTORY_LIMIT * 2),
        ).fetchall()

    history = []
    for row in rows:
        raw_products = decode_json_list(row["products_json"])
        products = []
        for product_data in raw_products[:3]:
            try:
                products.append(ProductCard.model_validate(product_data))
            except Exception:
                continue
        history.append(
            ChatHistoryEntry(
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
                products=products,
            )
        )
    return history


def chat_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    if client_ip not in _chat_requests and len(_chat_requests) >= 2048:
        oldest_address = min(
            _chat_requests,
            key=lambda address: _chat_requests[address][-1]
            if _chat_requests[address]
            else float("-inf"),
        )
        _chat_requests.pop(oldest_address, None)
    if len(_chat_requests) > 2048:
        for address, requests in list(_chat_requests.items()):
            while requests and now - requests[0] > 60:
                requests.popleft()
            if not requests:
                _chat_requests.pop(address, None)
    recent_requests = _chat_requests[client_ip]
    while recent_requests and now - recent_requests[0] > 60:
        recent_requests.popleft()
    if len(recent_requests) >= 20:
        raise HTTPException(status_code=429, detail="Please pause briefly before sending another message.")
    recent_requests.append(now)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/chat/history", response_model=ChatHistoryResponse)
def chat_history(
    campus_customs_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> ChatHistoryResponse:
    if not campus_customs_session:
        return ChatHistoryResponse(authenticated=False)
    try:
        with closing(get_connection()) as connection:
            user = get_session_user(connection, campus_customs_session)
    except HTTPException as error:
        if error.status_code == 401:
            return ChatHistoryResponse(authenticated=False, messages=[])
        raise
    return ChatHistoryResponse(
        authenticated=True,
        messages=load_chat_history(user["id"]),
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    body: ChatRequest,
    campus_customs_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> ChatResponse:
    global _chat_agent
    client_ip = request.client.host if request.client else "unknown"
    chat_rate_limit(client_ip)
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Enter a message for the shop assistant.")
    if _chat_agent is None:
        try:
            _chat_agent = build_agent()
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    customer_context = None
    user_id = None
    saved_history: list[ChatHistoryEntry] = []
    if campus_customs_session:
        try:
            with closing(get_connection()) as connection:
                user = get_session_user(connection, campus_customs_session)
            user_id = user["id"]
            customer_context = {"name": user["name"], "email": user["email"]}
            saved_history = load_chat_history(user_id)
        except HTTPException as error:
            if error.status_code != 401:
                raise

    current_product = None
    if body.page_context_product_id:
        page_products = load_products(body.page_context_product_id)
        if page_products:
            current_product = page_products[0]

    run_id = secrets.token_hex(6)
    started = time.monotonic()
    deps = ShopDependencies(
        database_path=DB_PATH,
        customer=customer_context,
        current_product=current_product,
        run_id=run_id,
    )
    # Logged without message text or identity: only shape and context flags.
    append_audit(
        {
            "run_id": run_id,
            "event": "run_start",
            "model": MODEL_NAME,
            "shopper": "authenticated" if user_id is not None else "guest",
            "message_chars": len(message),
            "history_turns": min(len(saved_history) if user_id is not None else len(body.history), 8),
            "page_product_id": current_product["product_id"] if current_product else None,
            "limits": {
                "request_limit": CHAT_USAGE_LIMITS.request_limit,
                "tool_calls_limit": CHAT_USAGE_LIMITS.tool_calls_limit,
                "output_tokens_limit": CHAT_USAGE_LIMITS.output_tokens_limit,
            },
        }
    )

    def audit_run_end(stop_reason: str, **extra: Any) -> None:
        append_audit(
            {
                "run_id": run_id,
                "event": "run_end",
                "stop_reason": stop_reason,
                "tool_calls": len(deps.tool_calls),
                "tools_used": deps.tool_calls,
                "duration_ms": round((time.monotonic() - started) * 1000),
                **extra,
            }
        )

    try:
        result = await _chat_agent.run(
            message,
            deps=deps,
            usage_limits=CHAT_USAGE_LIMITS,
            message_history=history_to_messages(
                [
                    {"role": turn.role, "content": turn.content}
                    for turn in saved_history
                ][-8:]
                if user_id is not None
                else [turn.model_dump() for turn in body.history]
            ),
        )
    except UsageLimitExceeded as error:
        audit_run_end("loop_limit_reached", detail=short(str(error), 160))
        raise HTTPException(
            status_code=503,
            detail="That question needed more lookups than the assistant is allowed per message. Try asking about one item at a time.",
        ) from error
    except Exception as error:
        audit_run_end(f"error:{type(error).__name__}")
        raise HTTPException(
            status_code=502,
            detail="The shop assistant is temporarily unavailable. Please try again.",
        ) from error

    product_cards = []
    seen_ids = set()
    for match in result.output.product_matches[:3]:
        product_id = match.product_id
        if product_id in seen_ids:
            continue
        seen_ids.add(product_id)
        product_rows = load_products(product_id)
        if product_rows:
            product_cards.append(ProductCard.model_validate(product_rows[0]))

    response = ChatResponse(reply=result.output.reply, products=product_cards)
    usage = getattr(result, "usage", None)  # RunUsage: model requests and token counts
    audit_run_end(
        "final_reply",
        model_requests=getattr(usage, "requests", None),
        output_tokens=getattr(usage, "output_tokens", None),
        reply_chars=len(response.reply),
        product_cards=[card.product_id for card in response.products],
        dropped_product_ids=[
            short(match.product_id, 60)
            for match in result.output.product_matches
            if match.product_id not in {card.product_id for card in response.products}
        ],
    )
    if user_id is not None:
        persist_chat_turn(user_id, message, response.reply, response.products)
    return response


@app.post("/api/auth/register", status_code=201)
def register_account(account: AccountCreate, response: Response) -> dict[str, Any]:
    first_name = account.first_name.strip()
    last_name = account.last_name.strip()
    if not first_name or not last_name:
        raise HTTPException(status_code=422, detail="First and last name are required.")
    email = normalize_email(account.email)
    display_name = f"{first_name} {last_name}"
    password_hash = hash_password(account.password)

    with closing(get_connection()) as connection:
        ensure_auth_schema(connection)
        try:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash, first_name, last_name) "
                "VALUES (?, ?, ?, ?, ?)",
                (display_name, email, password_hash, first_name, last_name),
            )
            user_id = cursor.lastrowid
            connection.commit()
        except sqlite3.IntegrityError as error:
            connection.rollback()
            if "users.email" in str(error):
                raise HTTPException(status_code=409, detail="An account with this email already exists.") from error
            raise

        user = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        create_session(connection, user_id, response)
        connection.commit()
        return public_user(user)


@app.post("/api/auth/login")
def login_account(account: AccountLogin, response: Response) -> dict[str, Any]:
    email = normalize_email(account.email)
    with closing(get_connection()) as connection:
        ensure_auth_schema(connection)
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        if user is None or not verify_password(account.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Email or password is incorrect.")
        if len(user["password_hash"].split("$")) == 3:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(account.password), user["id"]),
            )
        create_session(connection, user["id"], response)
        connection.commit()
        return public_user(user)


@app.get("/api/auth/me")
def current_account(
    campus_customs_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, Any]:
    with closing(get_connection()) as connection:
        user = get_session_user(connection, campus_customs_session)
        return public_user(user)


@app.post("/api/auth/logout")
def logout_account(
    response: Response,
    campus_customs_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, str]:
    if campus_customs_session:
        token_hash = hashlib.sha256(
            campus_customs_session.encode("ascii", errors="ignore")
        ).hexdigest()
        with closing(get_connection()) as connection:
            ensure_auth_schema(connection)
            connection.execute(
                "DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,)
            )
            connection.commit()
    response.delete_cookie(key=SESSION_COOKIE, path="/api", samesite="lax")
    return {"status": "signed out"}


@app.get("/api/products")
def list_products() -> list[dict[str, Any]]:
    return load_products()


@app.get("/api/products/{product_id}")
def get_product(product_id: str) -> dict[str, Any]:
    products = load_products(product_id)
    if not products:
        raise HTTPException(status_code=404, detail="Product not found.")
    return products[0]


@app.get("/images/{image_name}")
def product_image(image_name: str) -> FileResponse:
    image_path = (PRODUCT_IMAGE_DIR / image_name).resolve()
    if image_path.parent != PRODUCT_IMAGE_DIR.resolve() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Product image not found.")
    return FileResponse(image_path)
