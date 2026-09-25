"""MAFI v28 — achievements, smart bots, matches, reports, templates, seasons."""
from __future__ import annotations

import random
import time
from typing import Any, Optional

import persist
from game_logic import Phase, Role, is_mafia_role

CURRENT_SEASON = "2026-S2"

ACHIEVEMENTS: dict[str, dict[str, str]] = {
    "first_win": {"name": "اولین پیروزی", "icon": "🏆"},
    "ten_wins": {"name": "۱۰ برد", "icon": "👑"},
    "mafia_master": {"name": "استاد مافیا", "icon": "🎭"},
    "doctor_hero": {"name": "قهرمان دکتر", "icon": "💉"},
    "detective_eye": {"name": "چشم کارآگاه", "icon": "🔍"},
    "survivor_5": {"name": "۵ شب زنده", "icon": "🌙"},
    "host_10": {"name": "۱۰ بازی میزبانی", "icon": "🎪"},
    "first_correct_detect": {"name": "کارآگاه درست", "icon": "🕵️"},
    "joker_win": {"name": "برد جوکر", "icon": "🃏"},
    "ranked_gold": {"name": "طلایی رنک", "icon": "⭐"},
}


def achievement_defs() -> list[dict[str, str]]:
    return [{"id": k, **v} for k, v in ACHIEVEMENTS.items()]


def _player_won(winner: str, role: Optional[Role]) -> bool:
    if not role:
        return False
    if winner == "town" and not is_mafia_role(role) and role not in (Role.SERIAL_KILLER, Role.JOKER):
        return True
    if winner == "mafia" and is_mafia_role(role):
        return True
    if winner == "killer" and role == Role.SERIAL_KILLER:
        return True
    if winner == "joker" and role == Role.JOKER:
        return True
    return False


def check_achievements(room, player, winner: str) -> list[str]:
    if not player.token or player.is_bot or player.is_spectator:
        return []
    awarded: list[str] = []
    prof = persist.get_profile(player.token) or {}
    wins = int(prof.get("wins") or 0)
    badges = list(prof.get("badges") or [])
    won = _player_won(winner, player.role)

    checks: list[tuple[str, bool]] = [
        ("first_win", won and wins == 0),
        ("ten_wins", won and wins + 1 >= 10),
        ("mafia_master", won and winner == "mafia" and is_mafia_role(player.role)),
        ("doctor_hero", won and player.role == Role.DOCTOR),
        ("detective_eye", won and player.role == Role.DETECTIVE),
        ("survivor_5", won and room.night_number >= 5),
        ("host_10", int(prof.get("games_hosted") or 0) >= 10),
        ("joker_win", winner == "joker"),
        ("ranked_gold", int(prof.get("ranked_points") or 0) >= 500),
    ]
    for badge_id, ok in checks:
        if ok and badge_id not in badges:
            persist.upsert_profile(player.token, badge=badge_id)
            awarded.append(badge_id)
    return awarded


def save_match(room, winner: str) -> None:
    players = []
    for p in room.players.values():
        if p.is_spectator:
            continue
        players.append(
            {
                "name": p.name,
                "token": p.token,
                "role": p.role.value if p.role else None,
                "won": _player_won(winner, p.role),
                "bot": p.is_bot,
            }
        )
    persist.save_match(
        room_code=room.code,
        winner=winner,
        mode=room.settings.game_mode,
        ranked=room.settings.ranked,
        day_count=room.day_number,
        night_count=room.night_number,
        timeline=room.timeline[-80:],
        players=players,
    )


def smart_bot_night_pick(bot, room, phase: Phase) -> Optional[str]:
    alive = [p for p in room.alive_players() if p.sid != bot.sid]
    if not alive:
        return None
    if is_mafia_role(bot.role):
        town = [p for p in alive if not is_mafia_role(p.role) and p.role != Role.SERIAL_KILLER]
        pool = town or alive
        if phase == Phase.NIGHT_MAFIA:
            votes = room.night_actions.mafia_votes
            if votes:
                tally: dict[str, int] = {}
                for t in votes.values():
                    tally[t] = tally.get(t, 0) + 1
                return max(tally, key=tally.get)
        return random.choice(pool).sid
    if bot.role == Role.DOCTOR:
        mafia_targets = list(room.night_actions.mafia_votes.values())
        if mafia_targets and random.random() < 0.55:
            return random.choice(mafia_targets)
        return bot.sid
    if bot.role == Role.DETECTIVE:
        suspects = [p for p in alive if not is_mafia_role(p.role)]
        return random.choice(suspects or alive).sid
    if bot.role in (Role.SNIPER, Role.VIGILANTE):
        mafia = [p for p in alive if is_mafia_role(p.role)]
        if mafia and random.random() < 0.5:
            return random.choice(mafia).sid
        return random.choice(alive).sid
    return random.choice(alive).sid


def smart_bot_vote(bot, room) -> str:
    alive = room.alive_players()
    others = [p for p in alive if p.sid != bot.sid]
    if not others:
        return "skip"
    if is_mafia_role(bot.role):
        town = [p for p in others if not is_mafia_role(p.role)]
        return random.choice(town or others).sid
    if bot.role in (Role.DETECTIVE, Role.MAYOR):
        mafia_sus = [p for p in others if is_mafia_role(p.role)]
        if mafia_sus and random.random() < 0.35:
            return random.choice(mafia_sus).sid
    return random.choice(others).sid


def client_error_log(message: str, detail: str = "", token: str = "") -> None:
    persist.log_client_error(message, detail, token)


def validate_cloud_env() -> dict[str, Any]:
    import os

    hints = []
    if os.environ.get("MAFI_PUBLIC_URL"):
        hints.append("public_url_ok")
    if os.environ.get("RENDER"):
        hints.append("render")
    return {"hints": hints, "season": CURRENT_SEASON}
