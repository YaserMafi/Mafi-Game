"""منطق بازی مافیای کلاسیک فارسی"""
from __future__ import annotations

import random
import string
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class Role(str, Enum):
    CITIZEN = "citizen"
    MAFIA = "mafia"
    DOCTOR = "doctor"
    DETECTIVE = "detective"
    SNIPER = "sniper"
    GODFATHER = "godfather"
    MAYOR = "mayor"
    BODYGUARD = "bodyguard"
    SILENCER = "silencer"
    PSYCHIATRIST = "psychiatrist"  # ۸+ — یک‌بار نقش را بلاک کند
    SERIAL_KILLER = "serial_killer"  # ۹+ — مستقل
    SACRIFICE = "sacrifice"  # ۸+ — فداکار
    REPORTER = "reporter"  # ۱۰+ — خبرنگار
    NATASHA = "natasha"  # ۱۱+ — مافیا
    JOKER = "joker"  # ۱۰+ — خنثی؛ با رأی اعدام برنده
    VIGILANTE = "vigilante"  # ۹+ — یک‌بار شب می‌کشد


class Phase(str, Enum):
    LOBBY = "lobby"
    DEALING = "dealing"
    NIGHT_MAFIA = "night_mafia"
    NIGHT_SILENCER = "night_silencer"
    NIGHT_NATASHA = "night_natasha"
    NIGHT_DOCTOR = "night_doctor"
    NIGHT_BODYGUARD = "night_bodyguard"
    NIGHT_DETECTIVE = "night_detective"
    NIGHT_SNIPER = "night_sniper"
    NIGHT_PSYCH = "night_psych"
    NIGHT_KILLER = "night_killer"
    DAY_ANNOUNCE = "day_announce"
    DAY_DISCUSS = "day_discuss"
    DAY_DEFENSE = "day_defense"
    DAY_TRUST = "day_trust"
    DAY_VOTE = "day_vote"
    DAY_RESULT = "day_result"
    GAME_OVER = "game_over"


ROLE_INFO = {
    Role.CITIZEN: {
        "name": "شهروند",
        "team": "town",
        "color": "#c9a84c",
        "icon": "👤",
        "desc": "شهروند معمولی. با رأی‌گیری مافیا را پیدا کن.",
        "min_players": 6,
    },
    Role.MAFIA: {
        "name": "مافیا",
        "team": "mafia",
        "color": "#b91c1c",
        "icon": "🎭",
        "desc": "شب‌ها قربانی انتخاب می‌کنی. هویتت را پنهان کن.",
        "min_players": 6,
    },
    Role.DOCTOR: {
        "name": "دکتر",
        "team": "town",
        "color": "#22c55e",
        "icon": "💉",
        "desc": "هر شب یک نفر را از مرگ نجات بده.",
        "min_players": 6,
    },
    Role.DETECTIVE: {
        "name": "کارآگاه",
        "team": "town",
        "color": "#3b82f6",
        "icon": "🔍",
        "desc": "هر شب هویت یک نفر را استعلام بگیر.",
        "min_players": 6,
    },
    Role.SNIPER: {
        "name": "اسنایپر",
        "team": "town",
        "color": "#a855f7",
        "icon": "🎯",
        "desc": "یک بار در طول بازی می‌توانی شلیک کنی. اگر اشتباه بزنی می‌میری.",
        "min_players": 8,
    },
    Role.GODFATHER: {
        "name": "رئیس مافیا",
        "team": "mafia",
        "color": "#7f1d1d",
        "icon": "👑",
        "desc": "مافیایی هستی که کارآگاه تو را شهروند می‌بیند.",
        "min_players": 10,
    },
    Role.MAYOR: {
        "name": "شهردار",
        "team": "town",
        "color": "#eab308",
        "icon": "🏛️",
        "desc": "رأی تو دو برابر حساب می‌شود.",
        "min_players": 10,
    },
    Role.BODYGUARD: {
        "name": "بادیگارد",
        "team": "town",
        "color": "#14b8a6",
        "icon": "🛡️",
        "desc": "هر شب از یک نفر محافظت کن. اگر به او حمله شود، تو می‌میری نه او.",
        "min_players": 11,
    },
    Role.SILENCER: {
        "name": "سایلنسر",
        "team": "mafia",
        "color": "#64748b",
        "icon": "🔇",
        "desc": "مافیایی هستی که هر شب یک نفر را برای روز بعد ساکت می‌کنی.",
        "min_players": 13,
    },
    Role.PSYCHIATRIST: {
        "name": "روان‌پزشک",
        "team": "town",
        "color": "#ec4899",
        "icon": "🧠",
        "desc": "یک‌بار در بازی نقش شب یک نفر را بلاک می‌کنی.",
        "min_players": 8,
    },
    Role.SERIAL_KILLER: {
        "name": "جانی",
        "team": "neutral",
        "color": "#f97316",
        "icon": "🔪",
        "desc": "مستقلی. هر شب می‌کشی. اگر تنها بمانی برنده‌ای.",
        "min_players": 9,
    },
    Role.SACRIFICE: {
        "name": "فداکار",
        "team": "town",
        "color": "#f43f5e",
        "icon": "💝",
        "desc": "یک‌بار می‌توانی به‌جای هدف مافیا بمیری.",
        "min_players": 8,
    },
    Role.REPORTER: {
        "name": "خبرنگار",
        "team": "town",
        "color": "#06b6d4",
        "icon": "📰",
        "desc": "هر صبح یک سرنخ عمومی از نقش‌ها می‌دهی.",
        "min_players": 10,
    },
    Role.NATASHA: {
        "name": "ناتاشا",
        "team": "mafia",
        "color": "#db2777",
        "icon": "💋",
        "desc": "مافیایی؛ شب یک نفر را مجذوب/ساکت اثرگذار می‌کنی.",
        "min_players": 11,
    },
    Role.JOKER: {
        "name": "جوکر",
        "team": "neutral",
        "color": "#a855f7",
        "icon": "🃏",
        "desc": "خنثی؛ اگر با رأی شهر اعدام شوی برنده‌ای.",
        "min_players": 10,
    },
    Role.VIGILANTE: {
        "name": "شبه‌نظامی",
        "team": "town",
        "color": "#475569",
        "icon": "⚔️",
        "desc": "یک‌بار در شب می‌توانی یک نفر را بکشی.",
        "min_players": 9,
    },
}


def recommended_setup(n: int) -> dict:
    """نقش‌ها و تعداد مافیا بر اساس تعداد بازیکن"""
    n = max(6, min(15, n))
    mafia = 2 if n < 10 else (3 if n < 14 else 4)
    return {
        "mafia_count": mafia,
        "doctor": True,
        "detective": True,
        "sniper": n >= 8,
        "godfather": n >= 10,
        "mayor": n >= 10,
        "bodyguard": n >= 11,
        "silencer": n >= 13,
        "psychiatrist": n >= 8,
        "serial_killer": n >= 9,
        "sacrifice": n >= 8,
        "reporter": n >= 10,
        "natasha": n >= 11,
        "joker": n >= 10,
        "vigilante": n >= 9,
        "auto_roles": True,
    }


def unlocked_roles(n: int) -> list[dict]:
    """لیست نقش‌های بازشده برای نمایش در لابی"""
    out = []
    for role, info in ROLE_INFO.items():
        if role == Role.CITIZEN:
            continue
        unlocked = n >= info.get("min_players", 6)
        # مافیا همیشه از ۶
        if role == Role.MAFIA:
            unlocked = n >= 6
        out.append(
            {
                "role": role.value,
                "name": info["name"],
                "icon": info["icon"],
                "color": info["color"],
                "desc": info["desc"],
                "min_players": info.get("min_players", 6),
                "unlocked": unlocked,
                "team": info["team"],
            }
        )
    # مرتب بر اساس حداقل بازیکن
    out.sort(key=lambda x: (x["min_players"], x["name"]))
    return out


def is_mafia_role(role: Optional[Role]) -> bool:
    if not role:
        return False
    return ROLE_INFO[role]["team"] == "mafia"


def detective_sees_mafia(role: Optional[Role]) -> bool:
    """رئیس مافیا برای کارآگاه منفی است؛ ناتاشا دیده می‌شود"""
    if not role:
        return False
    return role in (Role.MAFIA, Role.SILENCER, Role.NATASHA)


AVATARS = [
    "🦁", "🐺", "🦅", "🦊", "🦉", "🐉", "🦂", "🦇",
    "🐯", "🐆", "🦈", "🐍", "🕷️", "🖤", "⚔️", "🔥",
    "🎭", "🎩", "💎", "🌙", "🕯️", "🃏", "🧿", "💀",
]

BOT_NAMES = [
    "آریا", "نیما", "سارا", "کیمیا", "رضا", "مهسا", "پویا", "نازنین", "کیان", "هستی"
]


def generate_code(length: int = 5) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def new_token() -> str:
    return uuid.uuid4().hex


def norm_player_name(name: str) -> str:
    """Normalize display names for duplicate checks (case/space insensitive)."""
    return " ".join(str(name or "").strip().split()).casefold()


@dataclass
class Player:
    sid: str
    name: str
    avatar: str
    token: str = ""
    is_host: bool = False
    is_spectator: bool = False
    is_bot: bool = False
    telegram_id: Optional[int] = None
    role: Optional[Role] = None
    alive: bool = True
    connected: bool = True
    disconnected_at: Optional[float] = None
    psych_used: bool = False
    sacrifice_used: bool = False
    mayor_veto_used: bool = False

    def public(self) -> dict[str, Any]:
        return {
            "sid": self.sid,
            "name": self.name,
            "avatar": self.avatar,
            "is_host": self.is_host,
            "is_spectator": self.is_spectator,
            "is_bot": self.is_bot,
            "alive": self.alive,
            "connected": self.connected,
        }

    def private(self) -> dict[str, Any]:
        data = self.public()
        data["token"] = self.token
        if self.role:
            info = ROLE_INFO[self.role]
            data["role"] = self.role.value
            data["role_name"] = info["name"]
            data["role_color"] = info["color"]
            data["role_icon"] = info["icon"]
            data["role_desc"] = info["desc"]
            data["team"] = info["team"]
            data["psych_used"] = self.psych_used
            data["sacrifice_used"] = self.sacrifice_used
            data["mayor_veto_used"] = self.mayor_veto_used
        return data


@dataclass
class RoomSettings:
    mafia_count: int = 2
    doctor: bool = True
    detective: bool = True
    sniper: bool = False
    godfather: bool = False
    mayor: bool = False
    bodyguard: bool = False
    silencer: bool = False
    psychiatrist: bool = False
    serial_killer: bool = False
    sacrifice: bool = False
    reporter: bool = False
    natasha: bool = False
    joker: bool = False
    vigilante: bool = False
    auto_roles: bool = True
    bot_difficulty: str = "normal"  # easy | normal | hard
    tournament_round: int = 0
    custom_role_pack: str = ""  # creator mode preset name
    night_time: int = 30
    discuss_time: int = 90
    vote_time: int = 45
    speak_time: int = 30
    defense_time: int = 30
    music: bool = True
    narrator_rate: str = "normal"  # slow | normal | fast
    narrator_voice: str = "farid"  # farid | dilara | farid_deep | farid_cinema | dilara_soft
    game_mode: str = "classic"  # classic | fast | last_stand | text_only | ranked | tournament
    tournament: bool = False
    ranked: bool = False
    room_password: str = ""
    room_password_hash: str = ""
    spectator_delay: int = 30


@dataclass
class NightActions:
    mafia_votes: dict[str, str] = field(default_factory=dict)
    doctor_save: Optional[str] = None
    detective_check: Optional[str] = None
    sniper_shot: Optional[str] = None
    vigilante_shot: Optional[str] = None
    sniper_acted_tonight: bool = False
    vigilante_acted_tonight: bool = False
    sniper_used: bool = False
    bodyguard_protect: Optional[str] = None
    silence_target: Optional[str] = None
    psych_block: Optional[str] = None
    killer_target: Optional[str] = None
    natasha_target: Optional[str] = None
    sacrifice_for: Optional[str] = None


@dataclass
class Room:
    code: str
    host_sid: str
    players: dict[str, Player] = field(default_factory=dict)
    settings: RoomSettings = field(default_factory=RoomSettings)
    phase: Phase = Phase.LOBBY
    night_actions: NightActions = field(default_factory=NightActions)
    votes: dict[str, str] = field(default_factory=dict)
    trust_votes: dict[str, str] = field(default_factory=dict)
    day_number: int = 0
    night_number: int = 0
    last_killed: Optional[str] = None
    last_killed_name: Optional[str] = None
    last_saved: bool = False
    winner: Optional[str] = None
    phase_ends_at: Optional[float] = None
    chat: list[dict] = field(default_factory=list)
    mafia_chat: list[dict] = field(default_factory=list)
    sniper_used: bool = False
    vigilante_used: bool = False
    detective_results: dict[str, dict] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    speak_queue: list[str] = field(default_factory=list)
    speak_index: int = 0
    current_speaker: Optional[str] = None
    voice_mode: str = "all"  # all | speaker | mafia | mute
    challenge_pending: Optional[dict] = None
    challenge_queue: list[dict] = field(default_factory=list)
    speak_stack: Optional[dict] = None
    is_challenge_turn: bool = False
    challenges_used: dict[str, int] = field(default_factory=dict)
    silenced_sid: Optional[str] = None
    natasha_charm: Optional[str] = None
    defense_target: Optional[str] = None
    reporter_hint: Optional[str] = None
    suspicion_log: list[dict] = field(default_factory=list)
    blocked_roles_tonight: set = field(default_factory=set)

    def add_timeline(self, kind: str, text: str, **extra: Any) -> None:
        ev = {
            "t": time.time(),
            "day": self.day_number,
            "night": self.night_number,
            "phase": self.phase.value,
            "kind": kind,
            "text": text,
        }
        ev.update(extra)
        self.timeline.append(ev)
        self.history.append(text)

    def add_suspicion(self, name: str, kind: str, detail: str, token: str = "") -> None:
        self.suspicion_log.append(
            {"t": time.time(), "name": name, "kind": kind, "detail": detail, "token": token}
        )
        if len(self.suspicion_log) > 80:
            self.suspicion_log = self.suspicion_log[-80:]

    def effective_times(self) -> dict[str, int]:
        s = self.settings
        mul = 0.5 if s.game_mode == "fast" else 1.0
        return {
            "night_time": max(12, int(s.night_time * mul)),
            "discuss_time": max(20, int(s.discuss_time * mul)),
            "vote_time": max(15, int(s.vote_time * mul)),
            "speak_time": max(10, int(s.speak_time * mul)),
            "defense_time": max(15, int(s.defense_time * mul)),
        }

    def alive_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.alive and not p.is_spectator]

    def mafia_players(self) -> list[Player]:
        return [p for p in self.alive_players() if is_mafia_role(p.role)]

    def town_players(self) -> list[Player]:
        return [
            p
            for p in self.alive_players()
            if p.role and ROLE_INFO[p.role]["team"] == "town"
        ]

    def neutral_players(self) -> list[Player]:
        return [
            p
            for p in self.alive_players()
            if p.role and ROLE_INFO[p.role]["team"] == "neutral"
        ]

    def player_count(self) -> int:
        return len([p for p in self.players.values() if not p.is_spectator])

    def settings_public(self) -> dict[str, Any]:
        s = self.settings
        return {
            "mafia_count": s.mafia_count,
            "doctor": s.doctor,
            "detective": s.detective,
            "sniper": s.sniper,
            "godfather": s.godfather,
            "mayor": s.mayor,
            "bodyguard": s.bodyguard,
            "silencer": s.silencer,
            "psychiatrist": s.psychiatrist,
            "serial_killer": s.serial_killer,
            "sacrifice": s.sacrifice,
            "reporter": s.reporter,
            "natasha": s.natasha,
            "joker": s.joker,
            "vigilante": s.vigilante,
            "bot_difficulty": s.bot_difficulty,
            "auto_roles": s.auto_roles,
            "night_time": s.night_time,
            "discuss_time": s.discuss_time,
            "vote_time": s.vote_time,
            "speak_time": s.speak_time,
            "defense_time": s.defense_time,
            "music": s.music,
            "narrator_rate": s.narrator_rate,
            "narrator_voice": s.narrator_voice,
            "game_mode": s.game_mode,
            "tournament": s.tournament,
            "ranked": s.ranked,
            "has_password": bool(s.room_password or s.room_password_hash),
            "spectator_delay": s.spectator_delay,
        }

    def public_state(self, for_sid: Optional[str] = None) -> dict[str, Any]:
        me = self.players.get(for_sid) if for_sid else None
        players_list = []
        for p in self.players.values():
            info = p.public()
            if self.phase == Phase.GAME_OVER and p.role:
                info["role"] = p.role.value
                info["role_name"] = ROLE_INFO[p.role]["name"]
                info["role_icon"] = ROLE_INFO[p.role]["icon"]
                info["role_color"] = ROLE_INFO[p.role]["color"]
            if (
                me
                and is_mafia_role(me.role)
                and is_mafia_role(p.role)
                and self.phase not in (Phase.LOBBY, Phase.DEALING)
            ):
                info["known_mafia"] = True
            # مرده / تماشاگر می‌تواند بعد از مرگ تایم‌لاین ببیند
            players_list.append(info)

        connected_n = len(
            [p for p in self.players.values() if not p.is_spectator and p.connected]
        )

        state: dict[str, Any] = {
            "code": self.code,
            "phase": self.phase.value,
            "day_number": self.day_number,
            "night_number": self.night_number,
            "players": players_list,
            "settings": self.settings_public(),
            "unlocked_roles": unlocked_roles(connected_n),
            "recommended": recommended_setup(connected_n),
            "host_sid": self.host_sid,
            "last_killed": self.last_killed,
            "last_killed_name": self.last_killed_name,
            "last_saved": self.last_saved,
            "winner": self.winner,
            "phase_ends_at": self.phase_ends_at,
            "vote_count": len(self.votes),
            "alive_count": len(self.alive_players()),
            "current_speaker": self.current_speaker,
            "speak_index": self.speak_index,
            "speak_total": len(self.speak_queue),
            "voice_mode": self.voice_mode,
            "is_challenge_turn": self.is_challenge_turn,
            "challenge_pending": self.challenge_pending,
            "challenge_queue_len": len(self.challenge_queue),
            "silenced_sid": self.silenced_sid,
            "defense_target": self.defense_target,
            "reporter_hint": self.reporter_hint,
            "timeline": self.timeline[-60:],
            "text_only": self.settings.game_mode == "text_only" or self.settings.tournament,
        }

        if self.current_speaker and self.current_speaker in self.players:
            sp = self.players[self.current_speaker]
            state["speaker_name"] = sp.name
            state["speaker_avatar"] = sp.avatar

        if me:
            state["me"] = me.private()
            state["my_challenges_left"] = max(0, 2 - self.challenges_used.get(me.sid, 0))
            if me.role == Role.DETECTIVE and me.sid in self.detective_results:
                state["detective_result"] = self.detective_results[me.sid]
            if is_mafia_role(me.role):
                state["mafia_chat"] = self.mafia_chat[-50:]
            if self.phase == Phase.DAY_VOTE:
                state["my_vote"] = self.votes.get(me.sid)
                state["votes_cast"] = len(self.votes)
            if self.phase == Phase.DAY_TRUST:
                state["my_trust_vote"] = self.trust_votes.get(me.sid)
            if self.silenced_sid == me.sid or self.natasha_charm == me.sid:
                state["am_silenced"] = True
            # میزبان لاگ مشکوک می‌بیند
            if me.is_host:
                state["suspicion_log"] = self.suspicion_log[-30:]
            # مرده یا تماشاگر: تایم‌لاین کامل‌تر
            if me.is_spectator or not me.alive:
                state["spectator_view"] = True
                state["timeline"] = self.timeline[-100:]

        state["chat"] = self.chat[-80:]
        return state


class GameManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.sid_to_room: dict[str, str] = {}
        self.token_index: dict[str, tuple[str, str]] = {}  # token -> (code, sid)

    def create_room(
        self, sid: str, name: str, token: str = "", avatar: str = ""
    ) -> Room:
        code = generate_code()
        while code in self.rooms:
            code = generate_code()
        token = token or new_token()
        avatar = avatar if avatar in AVATARS else random.choice(AVATARS)
        player = Player(
            sid=sid, name=name.strip()[:20], avatar=avatar, token=token, is_host=True
        )
        room = Room(code=code, host_sid=sid, players={sid: player})
        self.rooms[code] = room
        self.sid_to_room[sid] = code
        self.token_index[token] = (code, sid)
        return room

    def _remap_player(self, room: Room, existing: Player, sid: str) -> Room:
        old_sid = existing.sid
        if old_sid in room.players and old_sid != sid:
            del room.players[old_sid]
        self.sid_to_room.pop(old_sid, None)
        existing.sid = sid
        existing.connected = True
        existing.disconnected_at = None
        room.players[sid] = existing
        self.sid_to_room[sid] = room.code
        if existing.token:
            self.token_index[existing.token] = (room.code, sid)
        # remap references
        if room.host_sid == old_sid or existing.is_host:
            room.host_sid = sid
            existing.is_host = True
        if room.current_speaker == old_sid:
            room.current_speaker = sid
        if room.silenced_sid == old_sid:
            room.silenced_sid = sid
        if room.natasha_charm == old_sid:
            room.natasha_charm = sid
        if room.defense_target == old_sid:
            room.defense_target = sid
        room.speak_queue = [sid if x == old_sid else x for x in room.speak_queue]
        if old_sid in room.votes:
            room.votes[sid] = room.votes.pop(old_sid)
        if old_sid in room.challenges_used:
            room.challenges_used[sid] = room.challenges_used.pop(old_sid)
        if old_sid in room.detective_results:
            room.detective_results[sid] = room.detective_results.pop(old_sid)
        na = room.night_actions
        if old_sid in na.mafia_votes:
            na.mafia_votes[sid] = na.mafia_votes.pop(old_sid)
        for field_name in (
            "doctor_save",
            "detective_check",
            "sniper_shot",
            "bodyguard_protect",
            "silence_target",
            "psych_block",
            "killer_target",
            "natasha_target",
            "sacrifice_for",
        ):
            if getattr(na, field_name) == old_sid:
                setattr(na, field_name, sid)
        for k, v in list(na.mafia_votes.items()):
            if v == old_sid:
                na.mafia_votes[k] = sid
        self.ensure_host(room)
        return room

    def join_room(
        self,
        code: str,
        sid: str,
        name: str,
        spectator: bool = False,
        token: str = "",
        password: str = "",
        avatar: str = "",
    ) -> tuple[Optional[Room], Optional[str]]:
        code = code.upper().strip()
        room = self.rooms.get(code)
        if not room:
            return None, "اتاق پیدا نشد"
        name = (name or "").strip()[:20]
        if not name:
            return None, "نام لازم است"
        name_key = norm_player_name(name)

        # رمز اتاق
        pwd_hash = getattr(room.settings, "room_password_hash", "") or ""
        pwd_plain = room.settings.room_password or ""
        if pwd_hash or pwd_plain:
            tok_ok = False
            if token:
                for p in room.players.values():
                    if p.token == token:
                        tok_ok = True
                        break
            if not tok_ok:
                ok_pwd = False
                if pwd_hash:
                    try:
                        import mafi_pro

                        ok_pwd = mafi_pro.verify_password(password, pwd_hash)
                    except Exception:
                        ok_pwd = False
                elif pwd_plain:
                    ok_pwd = password == pwd_plain
                if not ok_pwd:
                    return None, "رمز اتاق اشتباه است"

        # reconnect با token
        if token:
            by_token = next((p for p in room.players.values() if p.token == token), None)
            if by_token:
                if by_token.connected and by_token.sid != sid:
                    room.add_suspicion(by_token.name, "takeover", "ورود دوم با همان توکن", token)
                return self._remap_player(room, by_token, sid), None

        # reconnect / duplicate با نام (بدون حساسیت به حروف بزرگ/فاصله)
        existing = next(
            (p for p in room.players.values() if norm_player_name(p.name) == name_key),
            None,
        )
        if existing:
            if existing.connected and existing.sid != sid:
                if existing.token and token and existing.token == token:
                    return self._remap_player(room, existing, sid), None
                room.add_suspicion(name, "dup_name", "تلاش ورود با نام تکراری", token)
                return None, "این نام قبلاً گرفته شده — نام دیگری انتخاب کنید"
            if token and not existing.token:
                existing.token = token
            return self._remap_player(room, existing, sid), None

        if room.phase != Phase.LOBBY and not spectator:
            return None, "بازی شروع شده — فقط تماشاگر می‌توانی وارد شوی"

        if not spectator and room.player_count() >= 15:
            return None, "اتاق پر است"

        # نام تکراری بازیکن وصل
        if any(norm_player_name(p.name) == name_key and p.connected for p in room.players.values()):
            return None, "این نام قبلاً گرفته شده — نام دیگری انتخاب کنید"

        token = token or new_token()
        avatar = avatar if avatar in AVATARS else random.choice(AVATARS)
        player = Player(
            sid=sid,
            name=name,
            avatar=avatar,
            token=token,
            is_spectator=spectator,
        )
        room.players[sid] = player
        self.sid_to_room[sid] = code
        self.token_index[token] = (code, sid)
        self.ensure_host(room)
        return room, None

    def rejoin(self, sid: str, token: str, code: str = "") -> tuple[Optional[Room], Optional[str]]:
        token = (token or "").strip()
        if not token:
            return None, "توکن نامعتبر"
        # جستجو در ایندکس
        hit = self.token_index.get(token)
        if hit:
            rcode, _ = hit
            room = self.rooms.get(rcode)
            if room:
                pl = next((p for p in room.players.values() if p.token == token), None)
                if pl:
                    return self._remap_player(room, pl, sid), None
        # جستجو در همه اتاق‌ها
        for room in self.rooms.values():
            if code and room.code != code.upper():
                continue
            pl = next((p for p in room.players.values() if p.token == token), None)
            if pl:
                return self._remap_player(room, pl, sid), None
        return None, "نشست پیدا نشد — دوباره وارد شو"

    def ensure_host(self, room: Room) -> None:
        host = room.players.get(room.host_sid)
        if host and host.connected and not host.is_spectator:
            host.is_host = True
            return
        for p in room.players.values():
            p.is_host = False
        for p in room.players.values():
            if p.connected and not p.is_spectator and not p.is_bot:
                p.is_host = True
                room.host_sid = p.sid
                return
        for p in room.players.values():
            if p.connected and not p.is_spectator:
                p.is_host = True
                room.host_sid = p.sid
                return
        if room.players:
            first = next(iter(room.players.values()))
            first.is_host = True
            room.host_sid = first.sid

    def leave(self, sid: str, grace: bool = True) -> Optional[Room]:
        code = self.sid_to_room.get(sid)
        if not code:
            return None
        room = self.rooms.get(code)
        if not room:
            self.sid_to_room.pop(sid, None)
            return None
        player = room.players.get(sid)
        if not player:
            self.sid_to_room.pop(sid, None)
            return room

        player.connected = False
        player.disconnected_at = time.time()

        if room.phase == Phase.LOBBY and player.is_bot:
            del room.players[sid]
            self.sid_to_room.pop(sid, None)
            self.ensure_host(room)
            return room

        if room.phase == Phase.LOBBY and not grace:
            del room.players[sid]
            self.sid_to_room.pop(sid, None)
            if player.token:
                self.token_index.pop(player.token, None)

        if not any(p.connected for p in room.players.values()):
            # اتاق را نگه دار برای restore کوتاه؛ پاکسازی با autosave/TTL
            self.ensure_host(room)
            return room

        self.ensure_host(room)
        return room

    def leave_completely(self, sid: str) -> tuple[Optional[Room], Optional[str], Optional[str]]:
        """خروج قطعی بازیکن (لابی یا وسط بازی) تا بتواند دوباره از خانه شروع کند."""
        code = self.sid_to_room.get(sid)
        if not code:
            return None, None, None
        room = self.rooms.get(code)
        if not room:
            self.sid_to_room.pop(sid, None)
            return None, None, None
        player = room.players.get(sid)
        if not player:
            self.sid_to_room.pop(sid, None)
            return room, None, None

        name = player.name
        was_alive = bool(player.alive and not player.is_spectator)
        in_game = room.phase not in (Phase.LOBBY, Phase.GAME_OVER)

        # پاک کردن ارجاعات SID
        room.votes.pop(sid, None)
        for k, v in list(room.votes.items()):
            if v == sid:
                room.votes.pop(k, None)
        room.trust_votes.pop(sid, None)
        for k, v in list(room.trust_votes.items()):
            if v == sid:
                room.trust_votes.pop(k, None)
        room.challenges_used.pop(sid, None)
        room.detective_results.pop(sid, None)
        room.speak_queue = [x for x in room.speak_queue if x != sid]
        if room.current_speaker == sid:
            room.current_speaker = None
        if room.defense_target == sid:
            room.defense_target = None
        if room.silenced_sid == sid:
            room.silenced_sid = None
        if room.natasha_charm == sid:
            room.natasha_charm = None
        if room.challenge_pending and (
            room.challenge_pending.get("from_sid") == sid
            or room.challenge_pending.get("to_sid") == sid
        ):
            room.challenge_pending = None
        if room.challenge_queue:
            room.challenge_queue = [
                x for x in room.challenge_queue if not (isinstance(x, dict) and x.get("sid") == sid)
            ]
        if isinstance(room.speak_stack, dict) and room.speak_stack.get("sid") == sid:
            room.speak_stack = None

        na = room.night_actions
        if na:
            na.mafia_votes.pop(sid, None)
            for field_name in (
                "doctor_save",
                "detective_check",
                "sniper_shot",
                "bodyguard_protect",
                "silence_target",
                "psych_block",
                "killer_target",
                "natasha_target",
                "sacrifice_for",
            ):
                if getattr(na, field_name, None) == sid:
                    setattr(na, field_name, None)
            for k, v in list(na.mafia_votes.items()):
                if v == sid:
                    na.mafia_votes.pop(k, None)

        if player.token:
            self.token_index.pop(player.token, None)
        del room.players[sid]
        self.sid_to_room.pop(sid, None)

        if in_game and was_alive:
            room.add_timeline("leave", f"{name} از بازی خارج شد")

        self.ensure_host(room)
        return room, name, ("playing" if in_game else "lobby")

    def claim_host(self, sid: str) -> tuple[Optional[Room], Optional[str]]:
        room = self.get_room_by_sid(sid)
        if not room:
            return None, "اتاق پیدا نشد"
        if room.phase != Phase.LOBBY:
            return None, "بازی شروع شده"
        player = room.players.get(sid)
        if not player or player.is_spectator:
            return None, "مجاز نیست"
        for p in room.players.values():
            p.is_host = False
        player.is_host = True
        room.host_sid = sid
        return room, None

    def kick_player(self, host_sid: str, target_sid: str) -> tuple[Optional[Room], Optional[str], Optional[str]]:
        room = self.get_room_by_sid(host_sid)
        if not room:
            return None, "اتاق پیدا نشد", None
        if host_sid != room.host_sid:
            return None, "فقط میزبان", None
        if room.phase != Phase.LOBBY:
            return None, "فقط در لابی", None
        target = room.players.get(target_sid)
        if not target:
            return None, "بازیکن نیست", None
        if target.is_host:
            return None, "نمی‌توان میزبان را اخراج کرد", None
        name = target.name
        if target.token:
            self.token_index.pop(target.token, None)
        del room.players[target_sid]
        self.sid_to_room.pop(target_sid, None)
        return room, name, None

    def get_room_by_sid(self, sid: str) -> Optional[Room]:
        code = self.sid_to_room.get(sid)
        return self.rooms.get(code) if code else None

    def update_settings(self, sid: str, settings: dict) -> tuple[Optional[Room], Optional[str]]:
        room = self.get_room_by_sid(sid)
        if not room:
            return None, "اتاق پیدا نشد"
        if sid != room.host_sid:
            return None, "فقط سازنده اتاق می‌تواند تنظیمات را تغییر دهد"
        if room.phase != Phase.LOBBY:
            return None, "بازی شروع شده"
        s = room.settings
        bool_keys = [
            "doctor", "detective", "sniper", "godfather", "mayor", "bodyguard",
            "silencer", "psychiatrist", "serial_killer", "sacrifice", "reporter",
            "natasha", "joker", "vigilante", "auto_roles", "music", "tournament", "ranked",
        ]
        for k in bool_keys:
            if k in settings:
                setattr(s, k, bool(settings[k]))
        if "mafia_count" in settings:
            s.mafia_count = max(1, min(5, int(settings["mafia_count"])))
        if "night_time" in settings:
            s.night_time = max(15, min(120, int(settings["night_time"])))
        if "discuss_time" in settings:
            s.discuss_time = max(30, min(300, int(settings["discuss_time"])))
        if "vote_time" in settings:
            s.vote_time = max(20, min(120, int(settings["vote_time"])))
        if "speak_time" in settings:
            s.speak_time = max(15, min(90, int(settings["speak_time"])))
        if "defense_time" in settings:
            s.defense_time = max(15, min(60, int(settings["defense_time"])))
        if "narrator_rate" in settings and settings["narrator_rate"] in ("slow", "normal", "fast"):
            s.narrator_rate = settings["narrator_rate"]
        if "narrator_voice" in settings and settings["narrator_voice"] in (
            "farid", "dilara", "farid_deep", "farid_cinema", "dilara_soft"
        ):
            s.narrator_voice = settings["narrator_voice"]
        if "game_mode" in settings and settings["game_mode"] in (
            "classic", "fast", "last_stand", "text_only", "ranked", "tournament"
        ):
            s.game_mode = settings["game_mode"]
            if s.game_mode == "ranked":
                s.ranked = True
            if s.game_mode == "tournament":
                s.tournament = True
            self.apply_game_mode(room)
        if "bot_difficulty" in settings and settings["bot_difficulty"] in ("easy", "normal", "hard"):
            s.bot_difficulty = settings["bot_difficulty"]
        if "custom_role_pack" in settings:
            s.custom_role_pack = str(settings["custom_role_pack"] or "")[:64]
        if "room_password" in settings:
            plain = str(settings["room_password"] or "")[:32]
            if plain:
                try:
                    import mafi_pro

                    s.room_password_hash = mafi_pro.hash_password(plain)
                    s.room_password = ""
                except Exception:
                    s.room_password = plain
                    s.room_password_hash = ""
            else:
                s.room_password = ""
                s.room_password_hash = ""
        if "spectator_delay" in settings:
            s.spectator_delay = max(0, min(120, int(settings["spectator_delay"])))
        return room, None

    def apply_game_mode(self, room: Room) -> None:
        s = room.settings
        if s.game_mode == "last_stand":
            s.doctor = False
            s.bodyguard = False
            s.sacrifice = False
        if s.game_mode == "fast":
            s.night_time = min(s.night_time, 20)
            s.speak_time = min(s.speak_time, 20)
            s.discuss_time = min(s.discuss_time, 45)
            s.vote_time = min(s.vote_time, 30)

    def apply_auto_roles(self, room: Room) -> None:
        if not room.settings.auto_roles:
            return
        n = len(
            [p for p in room.players.values() if not p.is_spectator and p.connected]
        )
        if n < 6:
            return
        rec = recommended_setup(n)
        s = room.settings
        for k, v in rec.items():
            if hasattr(s, k):
                setattr(s, k, v)
        if s.game_mode == "last_stand":
            s.doctor = False
            s.bodyguard = False
            s.sacrifice = False

    def add_bots(self, sid: str, count: int = 2) -> tuple[Optional[Room], Optional[str]]:
        room = self.get_room_by_sid(sid)
        if not room:
            return None, "اتاق پیدا نشد"
        if sid != room.host_sid:
            return None, "فقط میزبان"
        if room.phase != Phase.LOBBY:
            return None, "فقط در لابی"
        count = max(1, min(3, int(count)))
        existing_names = {p.name for p in room.players.values()}
        added = 0
        for name in BOT_NAMES:
            if room.player_count() >= 15:
                break
            if added >= count:
                break
            if name in existing_names:
                continue
            bot_sid = f"bot-{uuid.uuid4().hex[:8]}"
            room.players[bot_sid] = Player(
                sid=bot_sid,
                name=name,
                avatar=random.choice(AVATARS),
                token=new_token(),
                is_bot=True,
                connected=True,
            )
            self.sid_to_room[bot_sid] = room.code
            added += 1
        if added == 0:
            return room, "باتی اضافه نشد"
        return room, None

    def remove_bots(self, sid: str) -> tuple[Optional[Room], Optional[str]]:
        room = self.get_room_by_sid(sid)
        if not room or sid != room.host_sid or room.phase != Phase.LOBBY:
            return None, "مجاز نیست"
        for psid, p in list(room.players.items()):
            if p.is_bot:
                del room.players[psid]
                self.sid_to_room.pop(psid, None)
        return room, None

    def assign_roles(self, room: Room) -> Optional[str]:
        for sid, p in list(room.players.items()):
            if not p.connected and not p.is_bot and room.phase == Phase.LOBBY:
                # grace: فقط خیلی قدیمی‌ها را پاک کن
                if p.disconnected_at and time.time() - p.disconnected_at > 120:
                    del room.players[sid]
                    self.sid_to_room.pop(sid, None)

        players = [
            p
            for p in room.players.values()
            if not p.is_spectator and (p.connected or p.is_bot)
        ]
        n = len(players)
        if n < 6:
            return "حداقل ۶ بازیکن وصل لازم است"
        if n > 15:
            return "حداکثر ۱۵ بازیکن"

        self.apply_auto_roles(room)
        s = room.settings

        roles: list[Role] = []
        special_mafia = 0
        if s.godfather and n >= 10:
            roles.append(Role.GODFATHER)
            special_mafia += 1
        if s.silencer and n >= 13:
            roles.append(Role.SILENCER)
            special_mafia += 1
        if s.natasha and n >= 11:
            roles.append(Role.NATASHA)
            special_mafia += 1

        mafia_count = min(s.mafia_count, max(1, n // 3))
        regular_mafia = max(0, mafia_count - special_mafia)
        if regular_mafia == 0 and special_mafia == 0:
            regular_mafia = 1
        roles.extend([Role.MAFIA] * regular_mafia)

        if s.doctor:
            roles.append(Role.DOCTOR)
        if s.detective:
            roles.append(Role.DETECTIVE)
        if s.sniper and n >= 8:
            roles.append(Role.SNIPER)
        if s.mayor and n >= 10:
            roles.append(Role.MAYOR)
        if s.bodyguard and n >= 11:
            roles.append(Role.BODYGUARD)
        if s.psychiatrist and n >= 8:
            roles.append(Role.PSYCHIATRIST)
        if s.serial_killer and n >= 9:
            roles.append(Role.SERIAL_KILLER)
        if s.sacrifice and n >= 8:
            roles.append(Role.SACRIFICE)
        if s.reporter and n >= 10:
            roles.append(Role.REPORTER)
        if s.joker and n >= 10:
            roles.append(Role.JOKER)
        if s.vigilante and n >= 9:
            roles.append(Role.VIGILANTE)

        remaining = n - len(roles)
        if remaining < 0:
            trim = -remaining
            removable = [
                Role.NATASHA, Role.SILENCER, Role.REPORTER, Role.SACRIFICE,
                Role.PSYCHIATRIST, Role.SERIAL_KILLER, Role.BODYGUARD,
                Role.MAYOR, Role.SNIPER,
            ]
            for r in removable:
                while trim > 0 and r in roles:
                    roles.remove(r)
                    trim -= 1
            remaining = n - len(roles)
            if remaining < 0:
                return "تعداد نقش‌ها بیشتر از بازیکنان است"

        roles.extend([Role.CITIZEN] * remaining)
        random.shuffle(roles)
        random.shuffle(players)
        for player, role in zip(players, roles):
            player.role = role
            player.alive = True
            player.psych_used = False
            player.sacrifice_used = False
            player.mayor_veto_used = False

        room.sniper_used = False
        room.vigilante_used = False
        room.night_actions = NightActions()
        room.votes = {}
        room.trust_votes = {}
        room.day_number = 0
        room.night_number = 0
        room.winner = None
        room.last_killed = None
        room.last_killed_name = None
        room.detective_results = {}
        room.history = []
        room.timeline = []
        room.silenced_sid = None
        room.natasha_charm = None
        room.reporter_hint = None
        room.blocked_roles_tonight = set()
        room.add_timeline("deal", "نقش‌ها توزیع شد")
        return None

    def resolve_night(self, room: Room) -> dict[str, Any]:
        actions = room.night_actions
        # بلاک روان‌پزشک
        blocked = set()
        if actions.psych_block and actions.psych_block in room.players:
            target_p = room.players[actions.psych_block]
            if target_p.alive and target_p.role:
                blocked.add(target_p.role)
                psych = next(
                    (p for p in room.players.values() if p.role == Role.PSYCHIATRIST and p.alive),
                    None,
                )
                if psych:
                    psych.psych_used = True
        room.blocked_roles_tonight = blocked

        target = None
        if Role.MAFIA not in blocked and Role.GODFATHER not in blocked and actions.mafia_votes:
            counts: dict[str, int] = {}
            for t in actions.mafia_votes.values():
                counts[t] = counts.get(t, 0) + 1
            target = max(counts, key=counts.get)  # type: ignore

        # فداکار
        if target and actions.sacrifice_for == target:
            sacr = next(
                (p for p in room.players.values() if p.role == Role.SACRIFICE and p.alive and not p.sacrifice_used),
                None,
            )
            if sacr:
                sacr.sacrifice_used = True
                target = sacr.sid

        saved = False
        killed_sid = None
        killed_name = None
        guard_died_name = None
        kills: list[tuple[str, str]] = []

        def kill(sid: str, name: str) -> None:
            nonlocal killed_sid, killed_name
            p = room.players.get(sid)
            if p and p.alive:
                p.alive = False
                kills.append((sid, name))
                if not killed_sid:
                    killed_sid = sid
                    killed_name = name

        if target and target in room.players and Role.DOCTOR not in blocked:
            victim = room.players[target]
            if actions.doctor_save == target:
                saved = True
            elif actions.bodyguard_protect == target and Role.BODYGUARD not in blocked:
                guard = next(
                    (p for p in room.players.values() if p.role == Role.BODYGUARD and p.alive),
                    None,
                )
                if guard and guard.alive:
                    kill(guard.sid, guard.name)
                    guard_died_name = guard.name
                    saved = True
                elif victim.alive:
                    kill(target, victim.name)
            elif victim.alive:
                kill(target, victim.name)
        elif target and target in room.players:
            victim = room.players[target]
            if actions.doctor_save == target and Role.DOCTOR not in blocked:
                saved = True
            elif victim.alive:
                kill(target, victim.name)

        # جانی
        if actions.killer_target and Role.SERIAL_KILLER not in blocked:
            kt = room.players.get(actions.killer_target)
            if kt and kt.alive:
                kill(kt.sid, kt.name)

        # سایلنسر / ناتاشا
        room.silenced_sid = None
        room.natasha_charm = None
        if actions.silence_target and Role.SILENCER not in blocked:
            silenced = room.players.get(actions.silence_target)
            if silenced and silenced.alive:
                room.silenced_sid = actions.silence_target
        if actions.natasha_target and Role.NATASHA not in blocked:
            charm = room.players.get(actions.natasha_target)
            if charm and charm.alive:
                room.natasha_charm = actions.natasha_target
                if not room.silenced_sid:
                    room.silenced_sid = actions.natasha_target

        sniper_died = False
        sniper_kill_name = None
        vigilante_kill_name = None
        if actions.sniper_shot:
            shot = room.players.get(actions.sniper_shot)
            sniper = next(
                (p for p in room.players.values() if p.role == Role.SNIPER and p.alive),
                None,
            )
            if sniper and shot and not room.sniper_used and Role.SNIPER not in blocked:
                room.sniper_used = True
                if is_mafia_role(shot.role) and shot.alive:
                    kill(shot.sid, shot.name)
                    sniper_kill_name = shot.name
                else:
                    kill(sniper.sid, sniper.name)
                    sniper_died = True
        if actions.vigilante_shot:
            shot = room.players.get(actions.vigilante_shot)
            vigilante = next(
                (p for p in room.players.values() if p.role == Role.VIGILANTE and p.alive),
                None,
            )
            if (
                vigilante
                and shot
                and shot.alive
                and not room.vigilante_used
                and Role.VIGILANTE not in blocked
            ):
                room.vigilante_used = True
                kill(shot.sid, shot.name)
                vigilante_kill_name = shot.name

        room.last_killed = killed_sid
        room.last_killed_name = killed_name
        room.last_saved = saved and target is not None

        if actions.detective_check and Role.DETECTIVE not in blocked:
            detective = next(
                (p for p in room.players.values() if p.role == Role.DETECTIVE and p.alive),
                None,
            )
            checked = room.players.get(actions.detective_check)
            if detective and checked:
                is_mafia = detective_sees_mafia(checked.role)
                room.detective_results[detective.sid] = {
                    "target": checked.name,
                    "is_mafia": is_mafia,
                    "message": (
                        f"«{checked.name}» مافیاست!"
                        if is_mafia
                        else f"«{checked.name}» مافیا نیست."
                    ),
                }

        # خبرنگار
        room.reporter_hint = None
        reporter = next(
            (p for p in room.players.values() if p.role == Role.REPORTER and p.alive),
            None,
        )
        if reporter and room.settings.reporter:
            alive_roles = [ROLE_INFO[p.role]["name"] for p in room.alive_players() if p.role]
            if alive_roles:
                pick = random.choice(alive_roles)
                room.reporter_hint = f"خبرنگار فاش کرد: هنوز نقش «{pick}» در شهر زنده است."

        room.add_timeline(
            "night_resolve",
            f"شب {room.night_number}: کشته={killed_name or 'هیچ‌کس'} نجات={saved}",
            killed=killed_name,
            saved=saved,
            kills=[{"sid": a, "name": b} for a, b in kills],
        )

        return {
            "killed_sid": killed_sid,
            "killed_name": killed_name,
            "saved": room.last_saved,
            "sniper_died": sniper_died,
            "sniper_kill_name": sniper_kill_name,
            "vigilante_kill_name": vigilante_kill_name,
            "guard_died_name": guard_died_name,
            "silenced_name": (
                room.players[room.silenced_sid].name if room.silenced_sid else None
            ),
            "reporter_hint": room.reporter_hint,
            "kills": kills,
        }

    def resolve_vote(self, room: Room) -> dict[str, Any]:
        if not room.votes:
            return {"executed": None, "name": None, "counts": {}}

        counts: dict[str, int] = {}
        for voter_sid, t in room.votes.items():
            if t == "skip":
                continue
            weight = 1
            voter = room.players.get(voter_sid)
            if voter and voter.role == Role.MAYOR and voter.alive:
                weight = 2
            counts[t] = counts.get(t, 0) + weight

        if not counts:
            return {"executed": None, "name": None, "counts": {}}

        max_votes = max(counts.values())
        top = [sid for sid, c in counts.items() if c == max_votes]
        if len(top) > 1:
            room.add_timeline("vote", "رأی‌ها مساوی شد", counts=counts)
            return {"executed": None, "name": None, "counts": counts, "tie": True}

        executed_sid = top[0]
        player = room.players.get(executed_sid)
        if player and player.alive:
            player.alive = False
            room.add_timeline(
                "exec",
                f"{player.name} اعدام شد",
                executed=player.name,
                counts=counts,
            )
            return {
                "executed": executed_sid,
                "name": player.name,
                "counts": counts,
                "tie": False,
            }
        return {"executed": None, "name": None, "counts": counts}

    def resolve_trust(self, room: Room) -> Optional[str]:
        """رأی اعتماد: برمی‌گرداند sid متهم با بیشترین بی‌اعتمادی یا None"""
        if not room.trust_votes:
            return None
        counts: dict[str, int] = {}
        for t in room.trust_votes.values():
            if t == "skip":
                continue
            counts[t] = counts.get(t, 0) + 1
        if not counts:
            return None
        max_v = max(counts.values())
        top = [s for s, c in counts.items() if c == max_v]
        if len(top) != 1:
            return None
        return top[0]

    def mayor_veto(self, sid: str) -> tuple[Optional[Room], Optional[str], Optional[str]]:
        room = self.get_room_by_sid(sid)
        if not room:
            return None, None, "اتاق نیست"
        p = room.players.get(sid)
        if not p or p.role != Role.MAYOR or not p.alive:
            return room, None, "فقط شهردار زنده"
        if p.mayor_veto_used:
            return room, None, "وتو قبلاً استفاده شده"
        if room.phase not in (Phase.DAY_VOTE, Phase.DAY_DEFENSE, Phase.DAY_RESULT):
            return room, None, "الان نمی‌شود وتو کرد"
        p.mayor_veto_used = True
        room.votes = {}
        room.defense_target = None
        room.add_timeline("veto", f"شهردار ({p.name}) رأی را وتو کرد")
        return room, p.name, None

    def check_winner(self, room: Room) -> Optional[str]:
        mafia = room.mafia_players()
        town = room.town_players()
        neutrals = room.neutral_players()
        alive = room.alive_players()

        # جانی تنها → برد جانی
        if len(alive) == 1 and alive[0].role == Role.SERIAL_KILLER:
            room.winner = "killer"
            return "killer"
        if len(alive) == 2 and any(p.role == Role.SERIAL_KILLER for p in alive):
            # جانی در ۱v1 معمولاً می‌برد اگر مافیا/شهر یکی مانده
            sk = next(p for p in alive if p.role == Role.SERIAL_KILLER)
            other = next(p for p in alive if p.sid != sk.sid)
            if not is_mafia_role(other.role):
                room.winner = "killer"
                return "killer"

        if not mafia and not any(p.role == Role.SERIAL_KILLER for p in alive):
            room.winner = "town"
            return "town"
        if not mafia and neutrals and all(p.role == Role.SERIAL_KILLER for p in neutrals):
            # فقط جانی و شهر — ادامه تا جانی یا شهر ببازد
            pass
        if mafia and len(mafia) >= len([p for p in alive if not is_mafia_role(p.role)]):
            room.winner = "mafia"
            return "mafia"
        return None

    def bot_night_actions(self, room: Room) -> None:
        """اکشن بات‌ها — با AI ساده در حالت normal/hard"""
        try:
            import mafi_extras
        except ImportError:
            mafi_extras = None
        phase = room.phase
        alive = [p for p in room.alive_players() if p.sid != room.silenced_sid]
        if not alive:
            return
        smart = room.settings.bot_difficulty in ("normal", "hard")
        bots = [p for p in room.alive_players() if p.is_bot]
        for bot in bots:
            others = [p for p in alive if p.sid != bot.sid]
            if not others:
                continue
            if smart and mafi_extras:
                pick = mafi_extras.smart_bot_night_pick(bot, room, phase)
            else:
                pick = random.choice(others).sid
            if not pick:
                continue
            na = room.night_actions
            if phase == Phase.NIGHT_MAFIA and is_mafia_role(bot.role):
                na.mafia_votes[bot.sid] = pick
            elif phase == Phase.NIGHT_DOCTOR and bot.role == Role.DOCTOR:
                na.doctor_save = pick
            elif phase == Phase.NIGHT_DETECTIVE and bot.role == Role.DETECTIVE:
                na.detective_check = pick
            elif phase == Phase.NIGHT_BODYGUARD and bot.role == Role.BODYGUARD:
                na.bodyguard_protect = pick
            elif phase == Phase.NIGHT_SILENCER and bot.role == Role.SILENCER:
                na.silence_target = pick
            elif phase == Phase.NIGHT_NATASHA and bot.role == Role.NATASHA:
                na.natasha_target = pick
            elif phase == Phase.NIGHT_KILLER and bot.role == Role.SERIAL_KILLER:
                na.killer_target = pick
            elif phase == Phase.NIGHT_PSYCH and bot.role == Role.PSYCHIATRIST and not bot.psych_used:
                na.psych_block = pick
            elif phase == Phase.NIGHT_SNIPER and bot.role == Role.SNIPER:
                na.sniper_shot = pick
                na.sniper_acted_tonight = True
            elif phase == Phase.NIGHT_SNIPER and bot.role == Role.VIGILANTE:
                na.vigilante_shot = pick
                na.vigilante_acted_tonight = True

    def bot_votes(self, room: Room) -> None:
        try:
            import mafi_extras
        except ImportError:
            mafi_extras = None
        alive = room.alive_players()
        smart = room.settings.bot_difficulty in ("normal", "hard")
        for bot in alive:
            if not bot.is_bot:
                continue
            if bot.sid in room.votes:
                continue
            if smart and mafi_extras:
                room.votes[bot.sid] = mafi_extras.smart_bot_vote(bot, room)
            else:
                others = [p for p in alive if p.sid != bot.sid]
                if not others:
                    room.votes[bot.sid] = "skip"
                else:
                    room.votes[bot.sid] = random.choice(others).sid

    def snapshot(self, room: Room) -> dict[str, Any]:
        players = {}
        for sid, p in room.players.items():
            players[sid] = {
                "sid": p.sid,
                "name": p.name,
                "avatar": p.avatar,
                "token": p.token,
                "is_host": p.is_host,
                "is_spectator": p.is_spectator,
                "is_bot": p.is_bot,
                "telegram_id": p.telegram_id,
                "role": p.role.value if p.role else None,
                "alive": p.alive,
                "connected": p.connected,
                "psych_used": p.psych_used,
                "sacrifice_used": p.sacrifice_used,
                "mayor_veto_used": p.mayor_veto_used,
            }
        return {
            "code": room.code,
            "host_sid": room.host_sid,
            "phase": room.phase.value,
            "settings": asdict(room.settings),
            "players": players,
            "day_number": room.day_number,
            "night_number": room.night_number,
            "timeline": room.timeline[-100:],
            "history": room.history[-50:],
            "winner": room.winner,
            "sniper_used": room.sniper_used,
            "vigilante_used": room.vigilante_used,
            "silenced_sid": room.silenced_sid,
            "suspicion_log": room.suspicion_log[-40:],
            "chat": room.chat[-40:],
        }

    def restore_from_snapshot(self, data: dict[str, Any]) -> Optional[Room]:
        try:
            code = data["code"]
            settings = RoomSettings(**{
                k: v for k, v in data.get("settings", {}).items()
                if k in RoomSettings.__dataclass_fields__
            })
            room = Room(code=code, host_sid=data.get("host_sid", ""), settings=settings)
            room.phase = Phase(data.get("phase", "lobby"))
            room.day_number = data.get("day_number", 0)
            room.night_number = data.get("night_number", 0)
            room.timeline = data.get("timeline", [])
            room.history = data.get("history", [])
            room.winner = data.get("winner")
            room.sniper_used = data.get("sniper_used", False)
            room.vigilante_used = data.get("vigilante_used", False)
            room.silenced_sid = data.get("silenced_sid")
            room.suspicion_log = data.get("suspicion_log", [])
            room.chat = data.get("chat", [])
            for sid, pd in data.get("players", {}).items():
                role = Role(pd["role"]) if pd.get("role") else None
                pl = Player(
                    sid=pd["sid"],
                    name=pd["name"],
                    avatar=pd.get("avatar") or random.choice(AVATARS),
                    token=pd.get("token") or new_token(),
                    is_host=pd.get("is_host", False),
                    is_spectator=pd.get("is_spectator", False),
                    is_bot=pd.get("is_bot", False),
                    telegram_id=pd.get("telegram_id"),
                    role=role,
                    alive=pd.get("alive", True),
                    connected=False,
                    psych_used=pd.get("psych_used", False),
                    sacrifice_used=pd.get("sacrifice_used", False),
                    mayor_veto_used=pd.get("mayor_veto_used", False),
                )
                room.players[sid] = pl
                self.token_index[pl.token] = (code, sid)
            self.rooms[code] = room
            return room
        except Exception as e:
            print(f"[persist] restore failed: {e}")
            return None

    def next_night_phase(self, room: Room) -> Phase:
        if room.phase == Phase.DEALING or room.phase in (
            Phase.DAY_RESULT,
            Phase.LOBBY,
        ):
            room.night_number += 1
            room.night_actions = NightActions(sniper_used=room.sniper_used)
            room.votes = {}
            if room.mafia_players():
                return Phase.NIGHT_MAFIA

        if room.phase == Phase.NIGHT_MAFIA:
            if room.settings.doctor and any(
                p.role == Role.DOCTOR and p.alive for p in room.players.values()
            ):
                return Phase.NIGHT_DOCTOR
            room.phase = Phase.NIGHT_DOCTOR

        if room.phase == Phase.NIGHT_DOCTOR:
            if room.settings.detective and any(
                p.role == Role.DETECTIVE and p.alive for p in room.players.values()
            ):
                return Phase.NIGHT_DETECTIVE
            room.phase = Phase.NIGHT_DETECTIVE

        if room.phase == Phase.NIGHT_DETECTIVE:
            if (
                room.settings.sniper
                and not room.sniper_used
                and any(p.role == Role.SNIPER and p.alive for p in room.players.values())
            ):
                return Phase.NIGHT_SNIPER
            if (
                room.settings.vigilante
                and not room.vigilante_used
                and any(p.role == Role.VIGILANTE and p.alive for p in room.players.values())
            ):
                return Phase.NIGHT_SNIPER
            return Phase.DAY_ANNOUNCE

        if room.phase == Phase.NIGHT_SNIPER:
            return Phase.DAY_ANNOUNCE

        return Phase.NIGHT_MAFIA
