"""Supabase persistence for room snapshots (server-side secret only).

Prefers PostgREST table `mafi_rooms` when present; otherwise uses Storage
bucket `mafi-rooms` so cloud deploy works without a manual SQL step.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

_TABLE = "mafi_rooms"
_BUCKET = "mafi-rooms"
_mode: Optional[str] = None  # "table" | "storage" | "off" | None
_offline_logged = False


def _base_url() -> str:
    raw = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    if raw.endswith("/rest/v1"):
        return raw[: -len("/rest/v1")]
    return raw


def _secret() -> str:
    return (
        (os.environ.get("SUPABASE_SECRET_KEY") or "").strip()
        or (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    )


def enabled() -> bool:
    return bool(_base_url() and _secret())


def _headers(content_type: Optional[str] = "application/json", extra: Optional[dict] = None) -> dict[str, str]:
    key = _secret()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    if content_type:
        h["Content-Type"] = content_type
        h["Accept"] = "application/json"
    if extra:
        h.update(extra)
    return h


def _request(
    method: str,
    url: str,
    body: Optional[bytes] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 15.0,
) -> tuple[int, Any]:
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw) if raw else None
            return resp.status, data
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(detail) if detail else None
        except Exception:
            parsed = detail
        raise RuntimeError(f"HTTP {e.code}: {parsed}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"network: {getattr(e, 'reason', e)}") from e


def _rest(method: str, path: str, body: Optional[dict | list] = None, prefer: Optional[str] = None) -> Any:
    url = f"{_base_url()}/rest/v1/{path.lstrip('/')}"
    extra = {}
    if prefer:
        extra["Prefer"] = prefer
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    _, parsed = _request(method, url, data, _headers(extra=extra))
    return parsed


def _is_network(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.URLError) and not isinstance(exc, urllib.error.HTTPError):
        return True
    text = str(exc).lower()
    return (
        "getaddrinfo" in text
        or "no such host" in text
        or "name or service" in text
        or "network:" in text
        or "errno 11001" in text
    )


def _note_offline(exc: BaseException) -> None:
    global _mode, _offline_logged
    _mode = "off"
    if _offline_logged:
        return
    _offline_logged = True
    print(
        "[persist] cloud save paused: Supabase host is unreachable. "
        "Rooms stay saved on this PC."
    )


def _ensure_bucket() -> bool:
    url = f"{_base_url()}/storage/v1/bucket"
    payload = json.dumps(
        {"id": _BUCKET, "name": _BUCKET, "public": False, "file_size_limit": 2_000_000}
    ).encode("utf-8")
    try:
        _request("POST", url, payload, _headers())
        return True
    except RuntimeError as e:
        if _is_network(e):
            raise
        msg = str(e).lower()
        if "already" in msg or "409" in msg or "duplicate" in msg:
            return True
        # Bucket may already exist — GET check
        try:
            _request("GET", f"{_base_url()}/storage/v1/bucket/{_BUCKET}", headers=_headers())
            return True
        except Exception:
            print(f"[supabase] bucket ensure failed: {e}")
            return False


def _detect_mode() -> str:
    global _mode
    if _mode:
        return _mode
    if not enabled():
        _mode = "off"
        return _mode
    try:
        _rest("GET", f"{_TABLE}?select=code&limit=1")
        _mode = "table"
        return _mode
    except Exception as e:
        if _is_network(e):
            _note_offline(e)
            return "off"
    try:
        if _ensure_bucket():
            _mode = "storage"
            return _mode
    except Exception as e:
        _note_offline(e)
        return "off"
    _mode = "off"
    return _mode


def save_room_snapshot(code: str, data: dict[str, Any]) -> bool:
    if not enabled():
        return False
    mode = _detect_mode()
    code_u = str(code).upper()
    try:
        if mode == "table":
            payload = {"code": code_u, "data": data, "updated_at": time.time()}
            _rest(
                "POST",
                f"{_TABLE}?on_conflict=code",
                [payload],
                prefer="resolution=merge-duplicates,return=minimal",
            )
            return True
        if mode == "storage":
            body = json.dumps(
                {"code": code_u, "data": data, "updated_at": time.time()},
                ensure_ascii=False,
            ).encode("utf-8")
            path = urllib.parse.quote(f"{code_u}.json")
            url = f"{_base_url()}/storage/v1/object/{_BUCKET}/{path}"
            try:
                _request(
                    "POST",
                    url,
                    body,
                    _headers(
                        "application/json",
                        {"x-upsert": "true"},
                    ),
                )
            except RuntimeError:
                _request(
                    "PUT",
                    url,
                    body,
                    _headers("application/json", {"x-upsert": "true"}),
                )
            return True
    except Exception as e:
        if _is_network(e):
            _note_offline(e)
        else:
            print(f"[supabase] save_room failed: {e}")
            global _mode
            _mode = None
    return False


def load_room_snapshot(code: str) -> Optional[dict[str, Any]]:
    if not enabled():
        return None
    mode = _detect_mode()
    code_u = str(code).upper()
    try:
        if mode == "table":
            rows = _rest(
                "GET",
                f"{_TABLE}?code=eq.{urllib.parse.quote(code_u)}&select=data&limit=1",
            )
            if rows and isinstance(rows[0].get("data"), dict):
                return rows[0]["data"]
            return None
        if mode == "storage":
            path = urllib.parse.quote(f"{code_u}.json")
            url = f"{_base_url()}/storage/v1/object/{_BUCKET}/{path}"
            _, parsed = _request("GET", url, headers=_headers())
            if isinstance(parsed, dict):
                data = parsed.get("data")
                return data if isinstance(data, dict) else parsed
    except Exception as e:
        if "404" not in str(e):
            print(f"[supabase] load_room failed: {e}")
    return None


def delete_room_snapshot(code: str) -> bool:
    if not enabled():
        return False
    mode = _detect_mode()
    code_u = str(code).upper()
    try:
        if mode == "table":
            _rest(
                "DELETE",
                f"{_TABLE}?code=eq.{urllib.parse.quote(code_u)}",
                prefer="return=minimal",
            )
            return True
        if mode == "storage":
            path = urllib.parse.quote(f"{code_u}.json")
            url = f"{_base_url()}/storage/v1/object/{_BUCKET}/{path}"
            _request("DELETE", url, headers=_headers())
            return True
    except Exception as e:
        print(f"[supabase] delete_room failed: {e}")
    return False


def list_room_snapshots() -> list[tuple[str, dict[str, Any]]]:
    if not enabled():
        return []
    mode = _detect_mode()
    out: list[tuple[str, dict[str, Any]]] = []
    try:
        if mode == "table":
            rows = _rest("GET", f"{_TABLE}?select=code,data&order=updated_at.desc&limit=200")
            for row in rows or []:
                code = row.get("code")
                data = row.get("data")
                if code and isinstance(data, dict):
                    out.append((str(code), data))
            return out
        if mode == "storage":
            url = f"{_base_url()}/storage/v1/object/list/{_BUCKET}"
            body = json.dumps({"prefix": "", "limit": 200}).encode("utf-8")
            _, files = _request("POST", url, body, _headers())
            for item in files or []:
                name = str(item.get("name") or "")
                if not name.endswith(".json"):
                    continue
                code = name[: -len(".json")]
                snap = load_room_snapshot(code)
                if snap:
                    out.append((code, snap))
            return out
    except Exception as e:
        print(f"[supabase] list_rooms failed: {e}")
    return out


def ping() -> dict[str, Any]:
    if not enabled():
        return {"ok": False, "enabled": False, "mode": "off"}
    try:
        mode = _detect_mode()
        if mode == "off":
            err = "host unreachable" if _offline_logged else "no table/storage"
            return {"ok": False, "enabled": True, "mode": "off", "error": err}
        if mode == "table":
            _rest("GET", f"{_TABLE}?select=code&limit=1")
        else:
            _ensure_bucket()
        return {"ok": True, "enabled": True, "mode": mode}
    except Exception as e:
        if _is_network(e):
            _note_offline(e)
            return {"ok": False, "enabled": True, "mode": "off", "error": "host unreachable"}
        return {"ok": False, "enabled": True, "error": str(e)[:200]}
