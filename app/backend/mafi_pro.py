"""MAFI Pro — ELO, security, metrics, clans, season pass, AFK, analytics."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from collections import defaultdict
from typing import Any, Optional

import persist

try:
    import bcrypt

    _HAS_BCRYPT = True
except ImportError:
    _HAS_BCRYPT = False

try:
    import sentry_sdk

    _SENTRY = bool(os.environ.get("SENTRY_DSN", "").strip())
    if _SENTRY:
        sentry_sdk.init(
            dsn=os.environ["SENTRY_DSN"],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES", "0.1")),
            environment=os.environ.get("MAFI_ENV", "production"),
        )
except Exception:
    _SENTRY = False

DEFAULT_MMR = 1000
K_FACTOR = 32
AFK_LIMIT_SEC = 90
SPECTATOR_DELAY_DEFAULT = 30

# --- Rate limiting ---
_buckets: dict[str, list[float]] = defaultdict(list)


def rate_allow(key: str, max_calls: int = 20, window: float = 10.0) -> bool:
    now = time.time()
    bucket = _buckets[key]
    _buckets[key] = [t for t in bucket if now - t < window]
    if len(_buckets[key]) >= max_calls:
        return False
    _buckets[key].append(now)
    return True


def socket_rate(sid: str, event: str, limit: int = 15, window: float = 8.0) -> bool:
    return rate_allow(f"sock:{sid}:{event}", limit, window)


# --- Password hashing ---
def hash_password(plain: str) -> str:
    if not plain:
        return ""
    if _HAS_BCRYPT:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()
    return hashlib.sha256(f"mafi:{plain}".encode()).hexdigest()


def verify_password(plain: str, stored: str) -> bool:
    if not stored:
        return not plain
    if not plain:
        return False
    if stored.startswith("$2") and _HAS_BCRYPT:
        try:
            return bcrypt.checkpw(plain.encode(), stored.encode())
        except Exception:
            return False
    if len(stored) == 64 and all(c in "0123456789abcdef" for c in stored):
        return hashlib.sha256(f"mafi:{plain}".encode()).hexdigest() == stored
    return plain == stored


def admin_password_ok(password: str) -> bool:
    expected_hash = os.environ.get("MAFI_ADMIN_HASH", "").strip()
    expected_plain = os.environ.get("MAFI_ADMIN_PASSWORD", "mafi").strip()
    if expected_hash:
        return verify_password(password, expected_hash)
    return password == expected_plain


# --- Metrics ---
_metrics: dict[str, Any] = {
    "started_at": time.time(),
    "socket_events": 0,
    "http_requests": 0,
    "games_finished": 0,
    "errors": 0,
    "active_rooms": 0,
}


def metric_inc(name: str, n: int = 1) -> None:
    _metrics[name] = int(_metrics.get(name, 0)) + n


def metrics_snapshot(room_count: int = 0) -> dict[str, Any]:
    uptime = time.time() - _metrics["started_at"]
    return {
        **{k: v for k, v in _metrics.items() if k != "started_at"},
        "uptime_sec": round(uptime, 1),
        "active_rooms": room_count,
        "sentry": _SENTRY,
    }


def capture_error(message: str, detail: str = "", token: str = "") -> None:
    metric_inc("errors")
    persist.log_client_error(message, detail, token)
    if _SENTRY:
        try:
            sentry_sdk.capture_message(f"{message}: {detail[:500]}")
        except Exception:
            pass


# --- Bans ---
def is_banned(token: str) -> Optional[str]:
    if not token:
        return None
    row = persist.get_ban(token)
    if not row:
        return None
    if row["until"] and row["until"] < time.time():
        persist.remove_ban(token)
        return None
    return row.get("reason") or "مسدود"


def ban_token(token: str, reason: str, hours: float = 24.0) -> None:
    until = time.time() + hours * 3600 if hours > 0 else 0
    persist.set_ban(token, reason, until)


def unban_token(token: str) -> None:
    persist.remove_ban(token)


def list_reports(limit: int = 50) -> list[dict[str, Any]]:
    return persist.list_reports(limit)


# --- ELO / MMR ---
def expected_score(rating: float, opponent: float) -> float:
    return 1.0 / (1.0 + 10 ** ((opponent - rating) / 400.0))


def elo_delta(rating: int, opponent_avg: int, won: bool, k: int = K_FACTOR) -> int:
    exp = expected_score(rating, opponent_avg)
    score = 1.0 if won else 0.0
    return round(k * (score - exp))


def apply_season_decay(mmr: int, current_season: str, profile_season: str) -> int:
    """Pull MMR 10% toward default when entering a new season."""
    if profile_season == current_season:
        return mmr
    return round(mmr * 0.9 + DEFAULT_MMR * 0.1)


def update_ranked_mmr(
    players: list[Any],
    winner: str,
    season: str,
) -> dict[str, int]:
    """Return token -> mmr_delta for ranked games."""
    from game_logic import Role, is_mafia_role

    deltas: dict[str, int] = {}
    alive_ratings: list[int] = []
    token_ratings: dict[str, int] = {}
    for p in players:
        if p.is_bot or p.is_spectator or not p.token:
            continue
        prof = persist.get_profile(p.token) or {}
        mmr = int(prof.get("mmr") or DEFAULT_MMR)
        mmr = apply_season_decay(mmr, season, prof.get("season") or season)
        token_ratings[p.token] = mmr
        alive_ratings.append(mmr)
    if len(alive_ratings) < 2:
        return deltas
    avg_opp = sum(alive_ratings) // len(alive_ratings)
    for p in players:
        if p.is_bot or p.is_spectator or not p.token:
            continue
        won = False
        if winner == "town" and p.role and not is_mafia_role(p.role) and p.role != Role.SERIAL_KILLER:
            won = True
        elif winner == "mafia" and is_mafia_role(p.role):
            won = True
        elif winner == "killer" and p.role == Role.SERIAL_KILLER:
            won = True
        elif winner == "joker" and p.role == Role.JOKER:
            won = True
        rating = token_ratings.get(p.token, DEFAULT_MMR)
        delta = elo_delta(rating, avg_opp, won)
        deltas[p.token] = delta
        persist.upsert_profile(p.token, mmr_delta=delta, season=season)
    return deltas


# --- Role analytics ---
def role_win_rates(limit: int = 500) -> dict[str, Any]:
    return persist.role_analytics(limit)


# --- AFK tracking ---
_last_activity: dict[str, float] = {}
_session_fp: dict[str, str] = {}


def touch_activity(sid: str) -> None:
    _last_activity[sid] = time.time()


def set_fingerprint(sid: str, fp: str) -> None:
    if fp:
        _session_fp[sid] = fp[:64]


def check_afk_players(room) -> list[str]:
    """Return sids to kick for AFK during active phases."""
    from game_logic import Phase

    if room.phase in (Phase.LOBBY, Phase.GAME_OVER, Phase.DEALING):
        return []
    now = time.time()
    kick: list[str] = []
    for p in room.players.values():
        if p.is_bot or p.is_spectator or not p.alive or not p.connected:
            continue
        last = _last_activity.get(p.sid, now)
        if now - last > AFK_LIMIT_SEC:
            if room.current_speaker == p.sid or room.phase.value.startswith("night_"):
                kick.append(p.sid)
    return kick


def duplicate_session_tokens(room) -> dict[str, list[str]]:
    """token -> [sid,...] for multi-tab detection."""
    by_token: dict[str, list[str]] = defaultdict(list)
    for p in room.players.values():
        if p.token and p.connected:
            by_token[p.token].append(p.sid)
    return {t: sids for t, sids in by_token.items() if len(sids) > 1}


# --- Spectator delay ---
def spectator_state(base_state: dict[str, Any], room, delay_sec: int = SPECTATOR_DELAY_DEFAULT) -> dict[str, Any]:
    if not base_state.get("me", {}).get("is_spectator"):
        return base_state
    cutoff = time.time() - max(0, delay_sec)
    state = dict(base_state)
    timeline = [ev for ev in room.timeline if ev.get("t", 0) <= cutoff]
    state["timeline"] = timeline[-60:]
    state["spectator_delay"] = delay_sec
    state["spectator_lag"] = delay_sec
    return state


# --- Clans ---
def create_clan(owner_token: str, name: str, tag: str) -> tuple[Optional[str], Optional[str]]:
    name = name.strip()[:24]
    tag = tag.strip()[:6].upper()
    if len(name) < 2:
        return None, "نام کلن کوتاه است"
    if len(tag) < 2:
        return None, "تگ کلن کوتاه است"
    existing = persist.get_clan_by_member(owner_token)
    if existing:
        return None, "در کلن دیگری هستید"
    clan_id = secrets.token_hex(8)
    persist.create_clan(clan_id, name, tag, owner_token)
    return clan_id, None


def join_clan(token: str, clan_id: str) -> Optional[str]:
    if persist.get_clan_by_member(token):
        return "در کلن دیگری هستید"
    if not persist.get_clan(clan_id):
        return "کلن پیدا نشد"
    persist.add_clan_member(clan_id, token, "member")
    return None


def leave_clan(token: str) -> None:
    persist.remove_clan_member(token)


def clan_info(token: str) -> Optional[dict[str, Any]]:
    return persist.get_clan_by_member(token)


def list_clans(limit: int = 30) -> list[dict[str, Any]]:
    return persist.list_clans(limit)


# --- Season pass ---
SEASON_PASS_TIERS = [
    {"tier": 1, "xp": 100, "reward": "border_bronze", "label": "حاشیه برنزی"},
    {"tier": 2, "xp": 250, "reward": "border_silver", "label": "حاشیه نقره‌ای"},
    {"tier": 3, "xp": 500, "reward": "avatar_crown", "label": "آواتار تاج"},
    {"tier": 4, "xp": 800, "reward": "border_gold", "label": "حاشیه طلایی"},
    {"tier": 5, "xp": 1200, "reward": "title_legend", "label": "لقب افسانه"},
]


def season_pass_add_xp(token: str, season: str, xp: int) -> dict[str, Any]:
    row = persist.season_pass_upsert(token, season, xp)
    claimed = set(row.get("claimed") or [])
    new_rewards = []
    for tier in SEASON_PASS_TIERS:
        if row["xp"] >= tier["xp"] and tier["reward"] not in claimed:
            claimed.add(tier["reward"])
            new_rewards.append(tier)
            persist.upsert_profile(token, cosmetic=tier["reward"])
    if new_rewards:
        persist.season_pass_set_claimed(token, season, list(claimed))
    row["new_rewards"] = new_rewards
    return row


def season_pass_status(token: str, season: str) -> dict[str, Any]:
    row = persist.season_pass_get(token, season)
    return {"xp": row.get("xp", 0), "claimed": row.get("claimed", []), "tiers": SEASON_PASS_TIERS}


# --- TURN / ICE ---
def ice_servers() -> list[dict[str, Any]]:
    servers: list[dict[str, Any]] = [
        {"urls": "stun:stun.l.google.com:19302"},
        {"urls": "stun:stun1.l.google.com:19302"},
    ]
    turn_url = os.environ.get("MAFI_TURN_URL", "").strip()
    turn_user = os.environ.get("MAFI_TURN_USER", "").strip()
    turn_pass = os.environ.get("MAFI_TURN_PASS", "").strip()
    if turn_url:
        entry: dict[str, Any] = {"urls": turn_url}
        if turn_user:
            entry["username"] = turn_user
            entry["credential"] = turn_pass
        servers.append(entry)
    return servers


# --- Replay ---
def get_replay(match_id: int) -> Optional[dict[str, Any]]:
    return persist.get_match_by_id(match_id)


def list_replays(token: str, limit: int = 10) -> list[dict[str, Any]]:
    matches = persist.list_matches(token, limit)
    return [
        {
            "id": m.get("id"),
            "room_code": m.get("room_code"),
            "winner": m.get("winner"),
            "created_at": m.get("created_at"),
            "day_count": m.get("day_count"),
            "night_count": m.get("night_count"),
        }
        for m in matches
    ]
