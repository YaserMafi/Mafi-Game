"""SQLite persistence — rooms snapshot, profiles, ranked, suspicion log"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

_DATA_ROOT = Path(
    os.environ.get("MAFI_DATA_DIR", "").strip() or Path(__file__).resolve().parent
)
_DATA_ROOT.mkdir(parents=True, exist_ok=True)
DB_PATH = _DATA_ROOT / "mafi_data.sqlite3"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                code TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profiles (
                token TEXT PRIMARY KEY,
                name TEXT,
                avatar TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                badges TEXT DEFAULT '[]',
                ranked_points INTEGER DEFAULT 0,
                season TEXT DEFAULT '2026-S1',
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS suspicion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room TEXT,
                token TEXT,
                name TEXT,
                kind TEXT,
                detail TEXT,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS friends (
                owner_token TEXT,
                friend_token TEXT,
                friend_name TEXT,
                PRIMARY KEY (owner_token, friend_token)
            );
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT,
                winner TEXT,
                mode TEXT,
                ranked INTEGER DEFAULT 0,
                day_count INTEGER DEFAULT 0,
                night_count INTEGER DEFAULT 0,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room TEXT,
                reporter_token TEXT,
                reporter_name TEXT,
                target_name TEXT,
                reason TEXT,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS room_templates (
                owner_token TEXT,
                name TEXT,
                data TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (owner_token, name)
            );
            CREATE TABLE IF NOT EXISTS client_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT,
                message TEXT,
                detail TEXT,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS season_archive (
                season TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                archived_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bans (
                token TEXT PRIMARY KEY,
                reason TEXT,
                until REAL DEFAULT 0,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS clans (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                tag TEXT NOT NULL,
                owner_token TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS clan_members (
                clan_id TEXT NOT NULL,
                token TEXT NOT NULL,
                role TEXT DEFAULT 'member',
                joined_at REAL NOT NULL,
                PRIMARY KEY (clan_id, token)
            );
            CREATE TABLE IF NOT EXISTS season_pass (
                token TEXT NOT NULL,
                season TEXT NOT NULL,
                xp INTEGER DEFAULT 0,
                claimed TEXT DEFAULT '[]',
                updated_at REAL,
                PRIMARY KEY (token, season)
            );
            """
        )
        try:
            c.execute("ALTER TABLE profiles ADD COLUMN telegram_id INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE profiles ADD COLUMN games_hosted INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE profiles ADD COLUMN mmr INTEGER DEFAULT 1000")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE profiles ADD COLUMN cosmetics TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE profiles ADD COLUMN clan_id TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_telegram ON profiles(telegram_id) WHERE telegram_id IS NOT NULL"
            )
        except sqlite3.OperationalError:
            pass


_cloud_warned = False


def _cloud_skip(action: str, exc: Exception) -> None:
    global _cloud_warned
    text = str(exc).lower()
    if "getaddrinfo" in text or "no such host" in text or "urlopen error" in text or "network:" in text:
        if _cloud_warned:
            return
        _cloud_warned = True
        print("[persist] cloud save paused: Supabase host is unreachable. Local save continues.")
        return
    print(f"[persist] supabase {action} skipped: {exc}")


def save_room_snapshot(code: str, data: dict[str, Any]) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO rooms(code, data, updated_at) VALUES(?,?,?)",
            (code, json.dumps(data, ensure_ascii=False), time.time()),
        )
    try:
        import supabase_persist

        supabase_persist.save_room_snapshot(code, data)
    except Exception as e:
        _cloud_skip("save", e)


def load_room_snapshot(code: str) -> Optional[dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT data FROM rooms WHERE code=?", (code,)).fetchone()
    if row:
        try:
            return json.loads(row["data"])
        except Exception:
            pass
    try:
        import supabase_persist

        remote = supabase_persist.load_room_snapshot(code)
        if remote:
            # warm local cache
            try:
                with _conn() as c:
                    c.execute(
                        "INSERT OR REPLACE INTO rooms(code, data, updated_at) VALUES(?,?,?)",
                        (code, json.dumps(remote, ensure_ascii=False), time.time()),
                    )
            except Exception:
                pass
            return remote
    except Exception as e:
        _cloud_skip("load", e)
    return None


def delete_room_snapshot(code: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM rooms WHERE code=?", (code,))
    try:
        import supabase_persist

        supabase_persist.delete_room_snapshot(code)
    except Exception as e:
        _cloud_skip("delete", e)


def list_room_snapshots() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    with _conn() as c:
        rows = c.execute("SELECT code, data FROM rooms").fetchall()
    for row in rows:
        try:
            code = row["code"]
            out.append((code, json.loads(row["data"])))
            seen.add(str(code).upper())
        except Exception:
            continue
    try:
        import supabase_persist

        for code, data in supabase_persist.list_room_snapshots():
            key = str(code).upper()
            if key in seen:
                continue
            out.append((code, data))
            seen.add(key)
            try:
                with _conn() as c:
                    c.execute(
                        "INSERT OR REPLACE INTO rooms(code, data, updated_at) VALUES(?,?,?)",
                        (code, json.dumps(data, ensure_ascii=False), time.time()),
                    )
            except Exception:
                pass
    except Exception as e:
        _cloud_skip("list", e)
    return out


def upsert_profile(
    token: str,
    name: str = "",
    avatar: str = "",
    wins_delta: int = 0,
    losses_delta: int = 0,
    badge: Optional[str] = None,
    ranked_delta: int = 0,
    season: str = "2026-S1",
    hosts_delta: int = 0,
    mmr_delta: int = 0,
    cosmetic: Optional[str] = None,
) -> dict[str, Any]:
    with _conn() as c:
        row = c.execute("SELECT * FROM profiles WHERE token=?", (token,)).fetchone()
        if not row:
            badges = [badge] if badge else []
            cosmetics = [cosmetic] if cosmetic else []
            c.execute(
                """INSERT INTO profiles(token,name,avatar,wins,losses,badges,ranked_points,season,games_hosted,mmr,cosmetics,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    token,
                    name,
                    avatar,
                    max(0, wins_delta),
                    max(0, losses_delta),
                    json.dumps(badges, ensure_ascii=False),
                    max(0, ranked_delta),
                    season,
                    max(0, hosts_delta),
                    1000 + mmr_delta if mmr_delta else 1000,
                    json.dumps(cosmetics, ensure_ascii=False),
                    time.time(),
                ),
            )
        else:
            badges = json.loads(row["badges"] or "[]")
            if badge and badge not in badges:
                badges.append(badge)
            cosmetics = json.loads(row["cosmetics"] or "[]") if "cosmetics" in row.keys() else []
            if cosmetic and cosmetic not in cosmetics:
                cosmetics.append(cosmetic)
            mmr_val = int(row["mmr"] if "mmr" in row.keys() and row["mmr"] is not None else 1000)
            c.execute(
                """UPDATE profiles SET name=?, avatar=?, wins=wins+?, losses=losses+?,
                   badges=?, ranked_points=ranked_points+?, season=?, games_hosted=games_hosted+?,
                   mmr=?, cosmetics=?, updated_at=? WHERE token=?""",
                (
                    name or row["name"],
                    avatar or row["avatar"],
                    wins_delta,
                    losses_delta,
                    json.dumps(badges, ensure_ascii=False),
                    ranked_delta,
                    season,
                    hosts_delta,
                    max(0, mmr_val + mmr_delta),
                    json.dumps(cosmetics, ensure_ascii=False),
                    time.time(),
                    token,
                ),
            )
        row = c.execute("SELECT * FROM profiles WHERE token=?", (token,)).fetchone()
    return _profile_row(row)


def get_profile(token: str) -> Optional[dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM profiles WHERE token=?", (token,)).fetchone()
    return _profile_row(row) if row else None


def get_token_by_telegram_id(telegram_id: int) -> Optional[str]:
    with _conn() as c:
        row = c.execute(
            "SELECT token FROM profiles WHERE telegram_id=?", (int(telegram_id),)
        ).fetchone()
    return row["token"] if row else None


def get_telegram_id_by_token(token: str) -> Optional[int]:
    with _conn() as c:
        row = c.execute(
            "SELECT telegram_id FROM profiles WHERE token=?", (token,)
        ).fetchone()
    if not row or row["telegram_id"] is None:
        return None
    return int(row["telegram_id"])


def ensure_telegram_token(telegram_id: int, name: str = "") -> str:
    tg_id = int(telegram_id)
    existing = get_token_by_telegram_id(tg_id)
    if existing:
        if name:
            upsert_profile(existing, name=name)
        link_telegram(existing, tg_id)
        return existing
    token = f"tg-{tg_id}-{secrets.token_hex(10)}"
    link_telegram(token, tg_id, name=name)
    return token


def link_telegram(token: str, telegram_id: int, name: str = "") -> None:
    with _conn() as c:
        row = c.execute("SELECT token FROM profiles WHERE token=?", (token,)).fetchone()
        if row:
            c.execute(
                "UPDATE profiles SET telegram_id=?, name=COALESCE(NULLIF(?, ''), name), updated_at=? WHERE token=?",
                (int(telegram_id), name, time.time(), token),
            )
        else:
            c.execute(
                """INSERT INTO profiles(token, name, telegram_id, updated_at)
                   VALUES(?,?,?,?)""",
                (token, name, int(telegram_id), time.time()),
            )


def _profile_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "token": row["token"],
        "name": row["name"],
        "avatar": row["avatar"],
        "wins": row["wins"],
        "losses": row["losses"],
        "badges": json.loads(row["badges"] or "[]"),
        "ranked_points": row["ranked_points"],
        "season": row["season"],
        "games_hosted": row["games_hosted"] if "games_hosted" in row.keys() else 0,
        "mmr": row["mmr"] if "mmr" in row.keys() and row["mmr"] is not None else 1000,
        "cosmetics": json.loads(row["cosmetics"] or "[]") if "cosmetics" in row.keys() else [],
        "clan_id": row["clan_id"] if "clan_id" in row.keys() else None,
    }


def ranked_leaderboard(season: str = "2026-S1", limit: int = 20) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            """SELECT name, avatar, ranked_points, mmr, wins, losses, badges FROM profiles
               WHERE season=? ORDER BY mmr DESC, ranked_points DESC, wins DESC LIMIT ?""",
            (season, limit),
        ).fetchall()
    return [
        {
            "name": r["name"],
            "avatar": r["avatar"],
            "ranked_points": r["ranked_points"],
            "mmr": r["mmr"] if "mmr" in r.keys() and r["mmr"] is not None else 1000,
            "wins": r["wins"],
            "losses": r["losses"],
            "badges": json.loads(r["badges"] or "[]"),
        }
        for r in rows
    ]


def log_suspicion(room: str, token: str, name: str, kind: str, detail: str) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO suspicion(room,token,name,kind,detail,created_at)
               VALUES(?,?,?,?,?,?)""",
            (room, token, name, kind, detail, time.time()),
        )


def get_suspicion(room: str, limit: int = 40) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            """SELECT name, kind, detail, created_at FROM suspicion
               WHERE room=? ORDER BY id DESC LIMIT ?""",
            (room, limit),
        ).fetchall()
    return [
        {
            "name": r["name"],
            "kind": r["kind"],
            "detail": r["detail"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def add_friend(owner_token: str, friend_token: str, friend_name: str) -> None:
    with _conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO friends(owner_token, friend_token, friend_name)
               VALUES(?,?,?)""",
            (owner_token, friend_token, friend_name),
        )


def list_friends(owner_token: str) -> list[dict[str, str]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT friend_token, friend_name FROM friends WHERE owner_token=?",
            (owner_token,),
        ).fetchall()
    return [{"token": r["friend_token"], "name": r["friend_name"]} for r in rows]


def save_match(
    room_code: str,
    winner: str,
    mode: str,
    ranked: bool,
    day_count: int,
    night_count: int,
    timeline: list,
    players: list,
) -> None:
    payload = {
        "room_code": room_code,
        "winner": winner,
        "mode": mode,
        "ranked": ranked,
        "day_count": day_count,
        "night_count": night_count,
        "timeline": timeline,
        "players": players,
    }
    with _conn() as c:
        c.execute(
            """INSERT INTO matches(room_code,winner,mode,ranked,day_count,night_count,data,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                room_code,
                winner,
                mode,
                1 if ranked else 0,
                day_count,
                night_count,
                json.dumps(payload, ensure_ascii=False),
                time.time(),
            ),
        )


def list_matches(token: str, limit: int = 15) -> list[dict[str, Any]]:
    if not token:
        return []
    fetch_limit = max(limit * 10, 80)
    with _conn() as c:
        rows = c.execute(
            """SELECT id, data, created_at FROM matches ORDER BY id DESC LIMIT ?""",
            (fetch_limit,),
        ).fetchall()
    out = []
    for r in rows:
        try:
            d = json.loads(r["data"])
            d["id"] = r["id"]
            d["created_at"] = r["created_at"]
            players = d.get("players", [])
            if not any(p.get("token") == token for p in players):
                continue
            out.append(d)
            if len(out) >= limit:
                break
        except Exception:
            continue
    return out


def get_match_by_id(match_id: int) -> Optional[dict[str, Any]]:
    with _conn() as c:
        row = c.execute(
            "SELECT id, data, created_at FROM matches WHERE id=?", (match_id,)
        ).fetchone()
    if not row:
        return None
    try:
        d = json.loads(row["data"])
        d["id"] = row["id"]
        d["created_at"] = row["created_at"]
        return d
    except Exception:
        return None


def list_reports(limit: int = 50) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            """SELECT id, room, reporter_name, target_name, reason, created_at
               FROM reports ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "room": r["room"],
            "reporter": r["reporter_name"],
            "target": r["target_name"],
            "reason": r["reason"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def set_ban(token: str, reason: str, until: float) -> None:
    with _conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO bans(token, reason, until, created_at) VALUES(?,?,?,?)""",
            (token, reason[:200], until, time.time()),
        )


def get_ban(token: str) -> Optional[dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM bans WHERE token=?", (token,)).fetchone()
    if not row:
        return None
    return {"reason": row["reason"], "until": row["until"]}


def remove_ban(token: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM bans WHERE token=?", (token,))


def create_clan(clan_id: str, name: str, tag: str, owner_token: str) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO clans(id, name, tag, owner_token, created_at) VALUES(?,?,?,?,?)""",
            (clan_id, name, tag, owner_token, time.time()),
        )
        c.execute(
            """INSERT INTO clan_members(clan_id, token, role, joined_at) VALUES(?,?,?,?)""",
            (clan_id, owner_token, "owner", time.time()),
        )
        c.execute("UPDATE profiles SET clan_id=? WHERE token=?", (clan_id, owner_token))


def get_clan(clan_id: str) -> Optional[dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM clans WHERE id=?", (clan_id,)).fetchone()
    if not row:
        return None
    members = list_clan_members(clan_id)
    return {
        "id": row["id"],
        "name": row["name"],
        "tag": row["tag"],
        "owner": row["owner_token"],
        "members": members,
        "member_count": len(members),
    }


def list_clan_members(clan_id: str) -> list[dict[str, str]]:
    with _conn() as c:
        rows = c.execute(
            """SELECT cm.token, cm.role, p.name FROM clan_members cm
               LEFT JOIN profiles p ON p.token=cm.token WHERE cm.clan_id=?""",
            (clan_id,),
        ).fetchall()
    return [{"token": r["token"], "role": r["role"], "name": r["name"] or "?"} for r in rows]


def get_clan_by_member(token: str) -> Optional[dict[str, Any]]:
    with _conn() as c:
        row = c.execute(
            "SELECT clan_id FROM clan_members WHERE token=?", (token,)
        ).fetchone()
    if not row:
        return None
    return get_clan(row["clan_id"])


def add_clan_member(clan_id: str, token: str, role: str = "member") -> None:
    with _conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO clan_members(clan_id, token, role, joined_at) VALUES(?,?,?,?)""",
            (clan_id, token, role, time.time()),
        )
        c.execute("UPDATE profiles SET clan_id=? WHERE token=?", (clan_id, token))


def remove_clan_member(token: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM clan_members WHERE token=?", (token,))
        c.execute("UPDATE profiles SET clan_id=NULL WHERE token=?", (token,))


def list_clans(limit: int = 30) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            """SELECT c.id, c.name, c.tag,
                      (SELECT COUNT(*) FROM clan_members m WHERE m.clan_id=c.id) AS cnt
               FROM clans c ORDER BY cnt DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [{"id": r["id"], "name": r["name"], "tag": r["tag"], "members": r["cnt"]} for r in rows]


def season_pass_get(token: str, season: str) -> dict[str, Any]:
    with _conn() as c:
        row = c.execute(
            "SELECT xp, claimed FROM season_pass WHERE token=? AND season=?",
            (token, season),
        ).fetchone()
    if not row:
        return {"xp": 0, "claimed": []}
    return {"xp": row["xp"], "claimed": json.loads(row["claimed"] or "[]")}


def season_pass_upsert(token: str, season: str, xp_delta: int) -> dict[str, Any]:
    with _conn() as c:
        row = c.execute(
            "SELECT xp, claimed FROM season_pass WHERE token=? AND season=?",
            (token, season),
        ).fetchone()
        if row:
            new_xp = row["xp"] + xp_delta
            claimed = json.loads(row["claimed"] or "[]")
            c.execute(
                "UPDATE season_pass SET xp=?, updated_at=? WHERE token=? AND season=?",
                (new_xp, time.time(), token, season),
            )
        else:
            new_xp = max(0, xp_delta)
            claimed = []
            c.execute(
                """INSERT INTO season_pass(token, season, xp, claimed, updated_at) VALUES(?,?,?,?,?)""",
                (token, season, new_xp, "[]", time.time()),
            )
    return {"xp": new_xp, "claimed": claimed}


def season_pass_set_claimed(token: str, season: str, claimed: list[str]) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE season_pass SET claimed=?, updated_at=? WHERE token=? AND season=?",
            (json.dumps(claimed, ensure_ascii=False), time.time(), token, season),
        )


def role_analytics(limit: int = 500) -> dict[str, Any]:
    with _conn() as c:
        rows = c.execute(
            "SELECT data FROM matches ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    stats: dict[str, dict[str, int]] = {}
    for r in rows:
        try:
            d = json.loads(r["data"])
            winner = d.get("winner", "")
            for p in d.get("players", []):
                role = p.get("role")
                if not role or p.get("bot"):
                    continue
                if role not in stats:
                    stats[role] = {"games": 0, "wins": 0}
                stats[role]["games"] += 1
                if p.get("won"):
                    stats[role]["wins"] += 1
        except Exception:
            continue
    out = {}
    for role, s in stats.items():
        g = s["games"]
        out[role] = {
            "games": g,
            "wins": s["wins"],
            "win_rate": round(100 * s["wins"] / g, 1) if g else 0,
        }
    return {"roles": out, "sample_size": limit}


def log_report(room: str, reporter_token: str, reporter_name: str, target_name: str, reason: str) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO reports(room,reporter_token,reporter_name,target_name,reason,created_at)
               VALUES(?,?,?,?,?,?)""",
            (room, reporter_token, reporter_name, target_name, reason, time.time()),
        )


def log_client_error(message: str, detail: str = "", token: str = "") -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO client_errors(token,message,detail,created_at) VALUES(?,?,?,?)""",
            (token, message[:500], detail[:2000], time.time()),
        )


def save_room_template(owner_token: str, name: str, data: dict[str, Any]) -> None:
    with _conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO room_templates(owner_token,name,data,updated_at)
               VALUES(?,?,?,?)""",
            (owner_token, name, json.dumps(data, ensure_ascii=False), time.time()),
        )


def list_room_templates(owner_token: str) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT name, data, updated_at FROM room_templates WHERE owner_token=? ORDER BY updated_at DESC",
            (owner_token,),
        ).fetchall()
    out = []
    for r in rows:
        try:
            out.append({"name": r["name"], "settings": json.loads(r["data"]), "updated_at": r["updated_at"]})
        except Exception:
            continue
    return out


def archive_season(season: str) -> dict[str, Any]:
    board = ranked_leaderboard(season=season, limit=100)
    payload = {"season": season, "rows": board, "archived_at": time.time()}
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO season_archive(season,data,archived_at) VALUES(?,?,?)",
            (season, json.dumps(payload, ensure_ascii=False), time.time()),
        )
    return payload


def list_seasons() -> list[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT season FROM profiles UNION SELECT season FROM season_archive"
        ).fetchall()
    return sorted({r[0] for r in rows if r[0]}, reverse=True)


init_db()
