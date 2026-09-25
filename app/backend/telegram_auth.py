"""Telegram Mini App initData validation (WebApp HMAC)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl


def load_env_file() -> None:
    """Load app/backend/telegram.env into os.environ (does not override existing)."""
    path = Path(__file__).resolve().parent / "telegram.env"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if key and key not in os.environ:
            os.environ[key] = val


load_env_file()


def bot_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def is_enabled() -> bool:
    return bool(bot_token())


def webapp_url() -> str:
    return os.environ.get("MAFI_WEBAPP_URL", "").strip().rstrip("/")


def bot_username() -> str:
    return os.environ.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")


def webapp_base() -> str:
    """Public HTTPS base for Mini App (falls back to localhost for dev)."""
    url = webapp_url()
    if url:
        return url.rstrip("/")
    return "http://127.0.0.1:8000"


def webapp_room_url(room: str = "", action: str = "") -> str:
    base = webapp_base()
    if room:
        return f"{base}/?room={room.upper()}&tg=1"
    if action == "create":
        return f"{base}/?tg=1&action=create"
    return f"{base}/?tg=1"


def invite_deep_link(room: str) -> Optional[str]:
    """t.me deep link — opens bot then Mini App with room code."""
    uname = bot_username()
    code = str(room or "").strip().upper().replace(" ", "")[:6]
    if not uname or not code:
        return None
    return f"https://t.me/{uname}?start=join_{code}"


def owner_telegram_id() -> Optional[int]:
    raw = os.environ.get("TELEGRAM_OWNER_ID", "").strip()
    if not raw.isdigit():
        return None
    return int(raw)


def validate_init_data(init_data: str, max_age_sec: int = 86400) -> Optional[dict[str, Any]]:
    """Return parsed init-data dict if HMAC valid, else None."""
    token = bot_token()
    raw = str(init_data or "").strip()
    if not token or not raw:
        return None

    parsed = dict(parse_qsl(raw, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    auth_date = int(parsed.get("auth_date") or 0)
    if auth_date and max_age_sec > 0:
        if time.time() - auth_date > max_age_sec:
            return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        return None
    return parsed


def parse_user(init_data: str) -> Optional[dict[str, Any]]:
    parsed = validate_init_data(init_data)
    if not parsed:
        return None
    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        user = json.loads(user_raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(user, dict) or not user.get("id"):
        return None
    return user


def display_name(user: dict[str, Any]) -> str:
    parts = [str(user.get("first_name") or "").strip(), str(user.get("last_name") or "").strip()]
    name = " ".join(p for p in parts if p).strip()
    if not name and user.get("username"):
        name = str(user["username"])
    return name[:20] if name else "بازیکن"


def resolve_session(init_data: str) -> Optional[tuple[int, str, str]]:
    """Validate initData → (telegram_id, player_token, display_name)."""
    user = parse_user(init_data)
    if not user:
        return None
    import persist

    tg_id = int(user["id"])
    token = persist.ensure_telegram_token(tg_id, display_name(user))
    return tg_id, token, display_name(user)
