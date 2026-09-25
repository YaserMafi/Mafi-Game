"""Push game events to Telegram DMs (narrator voice, roles, alerts)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

import telegram_auth

_bot: Any = None
_lock = asyncio.Lock()


def set_bot(bot: Any) -> None:
    global _bot
    _bot = bot


def _enabled() -> bool:
    return _bot is not None and telegram_auth.is_enabled()


async def _send_text(chat_id: int, text: str, web_app_url: Optional[str] = None) -> None:
    if not _enabled() or not chat_id:
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    kb = None
    if web_app_url:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎭 بازگشت به بازی",
                        web_app=WebAppInfo(url=web_app_url),
                    )
                ]
            ]
        )
    try:
        async with _lock:
            await _bot.send_message(chat_id, text, reply_markup=kb)
    except Exception as e:
        print("[telegram notify]", e)


async def _send_voice(chat_id: int, audio_path: Path, caption: str = "") -> None:
    if not _enabled() or not chat_id or not audio_path.exists():
        return
    from aiogram.types import FSInputFile

    try:
        async with _lock:
            await _bot.send_voice(
                chat_id,
                FSInputFile(str(audio_path)),
                caption=(caption or "")[:1024] or None,
            )
    except Exception as e:
        print("[telegram voice]", e)


def _play_url(room_code: str) -> str:
    return telegram_auth.webapp_room_url(room_code)


async def notify_text(telegram_id: int, text: str, room_code: Optional[str] = None) -> None:
    url = _play_url(room_code) if room_code else None
    await _send_text(int(telegram_id), text, url)


async def notify_narrator(
    room,
    text: str,
    audio_path: Optional[Path] = None,
    *,
    dm: bool = True,
) -> None:
    """Send narrator line to Telegram players (voice if file exists)."""
    if not _enabled() or not dm:
        return
    import persist

    seen: set[int] = set()
    for p in room.players.values():
        if p.is_bot or p.is_spectator:
            continue
        tg_id = p.telegram_id or persist.get_telegram_id_by_token(p.token or "")
        if not tg_id or tg_id in seen:
            continue
        seen.add(tg_id)
        if audio_path and audio_path.exists():
            await _send_voice(tg_id, audio_path, text[:200])
        else:
            await notify_text(tg_id, f"🎙 {text}", room.code)


async def notify_private_role(player, room_code: str) -> None:
    if not _enabled() or not player.role:
        return
    import persist

    tg_id = player.telegram_id or persist.get_telegram_id_by_token(player.token or "")
    if not tg_id:
        return
    info = player.private()
    msg = (
        f"🃏 نقش شما: {info.get('role_icon', '')} {info.get('role_name', '')}\n"
        f"{info.get('role_desc', '')}\n\n"
        f"اتاق: {room_code}"
    )
    await notify_text(tg_id, msg, room_code)


async def notify_game_start(room) -> None:
    if not _enabled():
        return
    for p in room.players.values():
        if p.is_bot or p.is_spectator or not p.role:
            continue
        await notify_private_role(p, room.code)
    await notify_text_broadcast(
        room,
        f"🎮 بازی در اتاق {room.code} شروع شد!\nگرداننده هوشمند MAFI در حال اجراست.",
    )


async def notify_text_broadcast(room, text: str) -> None:
    if not _enabled():
        return
    import persist

    seen: set[int] = set()
    for p in room.players.values():
        if p.is_bot or p.is_spectator:
            continue
        tg_id = p.telegram_id or persist.get_telegram_id_by_token(p.token or "")
        if not tg_id or tg_id in seen:
            continue
        seen.add(tg_id)
        await notify_text(tg_id, text, room.code)


async def notify_game_over(room, winner: str) -> None:
    labels = {"town": "شهروندان", "mafia": "مافیا", "killer": "جانی"}
    label = labels.get(winner, winner)
    await notify_text_broadcast(room, f"🏁 بازی تمام شد — برنده: {label}")


async def notify_your_turn(player, room_code: str) -> None:
    import persist

    tg_id = player.telegram_id or persist.get_telegram_id_by_token(player.token or "")
    if not tg_id:
        return
    await notify_text(tg_id, f"🎤 نوبت صحبت شماست — {player.name}", room_code)


async def notify_room_created_host(room, host_player) -> None:
    """Send host invite links after creating a room in Telegram."""
    if not _enabled():
        return
    import persist

    tg_id = host_player.telegram_id or persist.get_telegram_id_by_token(
        host_player.token or ""
    )
    if not tg_id:
        return
    deep = telegram_auth.invite_deep_link(room.code)
    web = telegram_auth.webapp_room_url(room.code)
    lines = [
        f"✅ اتاق {room.code} ساخته شد!",
        f"👥 بازیکنان: {len([p for p in room.players.values() if not p.is_spectator])}",
        "",
        "لینک دعوت تلگرام:",
        deep or web,
        "",
        "این لینک را برای دوستان بفرستید تا از Mini App وارد شوند.",
    ]
    await notify_text(tg_id, "\n".join(lines), room.code)


async def notify_player_joined(room, joined_player) -> None:
    """Tell host a new player joined via Telegram."""
    if not _enabled():
        return
    import persist

    host = next((p for p in room.players.values() if p.is_host), None)
    if not host or host.sid == joined_player.sid:
        return
    tg_id = host.telegram_id or persist.get_telegram_id_by_token(host.token or "")
    if not tg_id:
        return
    count = len([p for p in room.players.values() if not p.is_spectator and p.connected])
    await notify_text(
        tg_id,
        f"➕ {joined_player.name} به اتاق {room.code} پیوست ({count} نفر)",
        room.code,
    )
