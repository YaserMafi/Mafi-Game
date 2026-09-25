"""سرور بازی مافیای کلاسیک فارسی — FastAPI + Socket.IO"""
from __future__ import annotations

import asyncio
import json
import os
import random
import socket
import time
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Optional

import socketio
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import persist
import mafi_extras
import mafi_pro
import telegram_auth
import telegram_bot
import telegram_notify
import tts_engine
from game_logic import AVATARS, GameManager, Phase, Role, is_mafia_role

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
PROJECT_ROOT = ROOT.parent
APK_WWW = PROJECT_ROOT / "Mobile APP" / "www"


def _load_dotenv_files() -> None:
    """Load project .env / cloud.env without overriding existing process env."""
    candidates = [
        ROOT.parent / ".env",
        ROOT / ".env",
        Path(__file__).resolve().parent / ".env",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv_files()
telegram_auth.load_env_file()

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
)
app = FastAPI(title="مافیا | MAFI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")
app.mount("/css", StaticFiles(directory=FRONTEND / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND / "js"), name="js")
app.mount("/tts", StaticFiles(directory=tts_engine.CACHE_DIR), name="tts")


@app.middleware("http")
async def pro_http_middleware(request: Request, call_next):
    ip = request.client.host if request.client else "?"
    if not mafi_pro.rate_allow(f"http:{ip}", 120, 60.0):
        return JSONResponse({"ok": False, "error": "rate limit"}, status_code=429)
    mafi_pro.metric_inc("http_requests")
    response = await call_next(request)
    return response


@app.middleware("http")
async def fresh_frontend_assets(request, call_next):
    """Prevent stale CSS/JS on phones after layout updates."""
    response = await call_next(request)
    path = request.url.path
    if (
        path.startswith("/css/")
        or path.startswith("/js/")
        or path in ("/", "/index.html", "/sw.js")
        or path.endswith(".webmanifest")
    ):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


socket_app = socketio.ASGIApp(sio, other_asgi_app=app)
manager = GameManager()
phase_tasks: dict[str, asyncio.Task] = {}
_autosave_task: Optional[asyncio.Task] = None

# بازیابی اتاق‌ها از SQLite
for _code, _snap in persist.list_room_snapshots():
    manager.restore_from_snapshot(_snap)


NARRATOR = {
    "deal": [
        "نقش‌ها در حال توزیع‌اند. سرنوشت شما رقم می‌خورد.",
        "کارت‌ها روی میز می‌لغزند... هویت‌ها پنهان می‌مانند.",
    ],
    "night_start": [
        "شب شد. همه چشم‌ها بسته. شهر در سکوت فرو رفت.",
        "تاریکی شهر را بلعید. نفس‌ها آرام شد.",
    ],
    "night_tense": [
        "شب سنگین است. فقط چند نفر از مافیا مانده‌اند...",
        "سکوت خطرناک است. هر صدایی ممکن است آخرین باشد.",
    ],
    "mafia": [
        "مافیاها بیدار شوید و قربانی خود را انتخاب کنید.",
        "سایه مافیا بلند شد. قربانی امشب کیست؟",
    ],
    "doctor": ["دکتر، کسی را که می‌خواهی از مرگ نجات دهی انتخاب کن."],
    "detective": ["کارآگاه، استعلام بگیر. حقیقت را کشف کن."],
    "sniper": ["اِسنایپر، اگر شلیک می‌کنی، هدف را با دقت انتخاب کن. اشتباه یعنی مرگ."],
    "silencer": ["سای‌لنسر، کسی را که می‌خواهی فردا ساکت بماند انتخاب کن."],
    "bodyguard": ["بادی‌گارد، از چه کسی محافظت می‌کنی؟ اگر حمله شود، تو جان خود را فدا می‌کنی."],
    "psych": ["روان‌پزشک، نقش چه کسی را امشب بلاک می‌کنی؟"],
    "killer": ["جانی بیدار شو. قربانی خودت را انتخاب کن."],
    "natasha": ["ناتاشا، کسی را که می‌خواهی مجذوب کنی انتخاب کن."],
    "day_saved": ["صبح شد. معجزه! امشب کسی کشته نشد. کسی جان دیگری را نجات داد."],
    "day_kill": ["صبح شد. متأسفانه امشب {name} به طرز فجیعی به قتل رسید."],
    "day_none": ["صبح شد. شب آرامی بود. کسی کشته نشد."],
    "day_guard": ["صبح شد. بادی‌گارد جان خود را فدا کرد تا {name} زنده بماند. {guard} کشته شد."],
    "silenced": ["امروز {name} ساکت شده و نمی‌تواند حرف بزند."],
    "discuss": ["وقت دفاع و اتهام است. هر بازیکن به نوبت فرصت حرف زدن دارد."],
    "speak_turn": ["نوبت {name}. صحبت کن."],
    "speak_end": ["زمان {name} تمام شد."],
    "challenge_ask": ["{name} چالش کرده. {sec} ثانیه {when}."],
    "challenge_accept": ["چالش پذیرفته شد. {name}، {sec} ثانیه فرصت داری."],
    "challenge_auto": ["چالش به‌صورت خودکار پذیرفته شد. {name} بعد از این نوبت {sec} ثانیه حرف می‌زند."],
    "challenge_reject": ["چالش رد شد."],
    "challenge_grant": ["چالش! نوبت کوتاه {name}. {sec} ثانیه صحبت کن."],
    "trust": ["رأی اعتماد! چه کسی مشکوک است؟"],
    "defense": ["{name} فرصت دفاع نهایی دارد."],
    "vote": ["رأی‌گیری اعدام آغاز شد. سرنوشت را رقم بزنید."],
    "exec": ["{name} با اکثریت آرا اعدام شد."],
    "tie": ["رأی‌ها مساوی شد. کسی اعدام نمی‌شود."],
    "no_exec": ["کسی اعدام نشد. شب دیگری در راه است."],
    "veto": ["شهردار رأی را وتو کرد!"],
    "town_win": ["شهروندان پیروز شدند. مافیا نابود شد. عدالت برقرار گشت."],
    "mafia_win": ["مافیا پیروز شد. تاریکی شهر را فرا گرفت. هیچ‌کس در امان نیست."],
    "killer_win": ["جانی پیروز شد. تنها بازمانده تاریکی اوست."],
}


def pick_narrator(key: str, room=None, **fmt) -> str:
    opts = NARRATOR.get(key, [key])
    if isinstance(opts, str):
        text = opts
    else:
        text = random.choice(opts)
    # تنش اگر مافیا کم مانده
    if key == "night_start" and room:
        m = len(room.mafia_players())
        if 0 < m <= 2 and room.night_number >= 2:
            text = random.choice(NARRATOR["night_tense"])
    if fmt:
        try:
            text = text.format(**fmt)
        except Exception:
            pass
    return text


RATE_MAP = {"slow": "-12%", "normal": None, "fast": "+4%"}


async def persist_room(room) -> None:
    try:
        persist.save_room_snapshot(room.code, manager.snapshot(room))
    except Exception as e:
        print(f"[persist] save error: {e}")


async def autosave_loop():
    while True:
        await asyncio.sleep(8)
        for room in list(manager.rooms.values()):
            await persist_room(room)


@app.on_event("startup")
async def on_startup():
    global _autosave_task
    _autosave_task = asyncio.create_task(autosave_loop())
    if not os.environ.get("MAFI_ANDROID"):
        telegram_bot.start_background()


def _telegram_from_payload(data: dict) -> tuple[Optional[int], Optional[str], Optional[str], bool]:
    """Return (telegram_id, token, display_name, is_telegram_client)."""
    is_tg = bool(
        data.get("telegram")
        or data.get("telegram_init_data")
        or data.get("initData")
    )
    init = str(data.get("telegram_init_data") or data.get("initData") or "").strip()
    if not init:
        return None, None, None, is_tg
    resolved = telegram_auth.resolve_session(init)
    if not resolved:
        return None, None, None, is_tg
    return resolved[0], resolved[1], resolved[2], True


def _attach_telegram_player(player, telegram_id: Optional[int]) -> None:
    if player and telegram_id:
        player.telegram_id = int(telegram_id)
        if player.token:
            try:
                persist.link_telegram(player.token, int(telegram_id), player.name)
            except Exception:
                pass


async def emit_room_state(room, extra: Optional[dict] = None):
    delay = getattr(room.settings, "spectator_delay", 30)
    for sid in list(room.players.keys()):
        p = room.players[sid]
        if not p.connected and not p.is_bot:
            continue
        if p.is_bot:
            continue
        payload = room.public_state(sid)
        if extra:
            payload.update(extra)
        payload = mafi_pro.spectator_state(payload, room, delay)
        await sio.emit("game_state", payload, to=sid)


async def afk_sweep(room) -> None:
    for sid in mafi_pro.check_afk_players(room):
        p = room.players.get(sid)
        if not p:
            continue
        await sio.emit("kicked", {"reason": "AFK — عدم فعالیت"}, to=sid)
        manager.leave(sid)
        await sio.emit(
            "toast",
            {"message": f"{p.name} به دلیل AFK اخراج شد", "type": "warn"},
            room=room.code,
        )


async def emit_narrator(room, text: str, mood: str = "normal", wait: bool = True):
    audio_url = None
    rate = RATE_MAP.get(getattr(room.settings, "narrator_rate", "normal"))
    voice = getattr(room.settings, "narrator_voice", "farid")
    path, duration = await tts_engine.get_audio(text, voice=voice, rate_override=rate)
    if path:
        audio_url = f"/tts/{path.name}"

    await sio.emit(
        "narrator",
        {"text": text, "mood": mood, "audio": audio_url},
        room=room.code,
    )
    if telegram_auth.is_enabled():
        asyncio.create_task(
            telegram_notify.notify_narrator(room, text, path if path else None)
        )
    if wait:
        await asyncio.sleep(duration or tts_engine.estimate_duration(text))


async def emit_voice_policy(room):
    await sio.emit(
        "voice_policy",
        {
            "mode": room.voice_mode,
            "speaker": room.current_speaker,
            "phase": room.phase.value,
        },
        room=room.code,
    )


async def cancel_phase_timer(code: str):
    task = phase_tasks.pop(code, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def start_phase_timer(room, seconds: int, callback):
    await cancel_phase_timer(room.code)
    room.phase_ends_at = time.time() + seconds

    async def runner():
        try:
            await asyncio.sleep(seconds)
            await callback(room.code)
        except asyncio.CancelledError:
            pass

    phase_tasks[room.code] = asyncio.create_task(runner())


async def advance_after_deal(code: str):
    room = manager.rooms.get(code)
    if not room or room.phase != Phase.DEALING:
        return
    await begin_night(room)


async def begin_night(room):
    from game_logic import NightActions

    room.night_number += 1
    room.night_actions = NightActions(sniper_used=room.sniper_used)
    room.votes = {}
    room.trust_votes = {}
    room.defense_target = None
    room.current_speaker = None
    room.speak_queue = []
    room.voice_mode = "mute" if room.settings.game_mode == "text_only" else "mafia"
    room.phase = Phase.NIGHT_MAFIA
    times = room.effective_times()

    await sio.emit("atmosphere", {"mode": "night"}, room=room.code)
    await emit_voice_policy(room)
    await emit_narrator(room, pick_narrator("night_start", room), "dark")
    await emit_narrator(room, pick_narrator("mafia", room), "danger")
    manager.bot_night_actions(room)
    await emit_room_state(room)
    await persist_room(room)
    await start_phase_timer(room, times["night_time"], night_phase_timeout)


async def night_phase_timeout(code: str):
    room = manager.rooms.get(code)
    if not room:
        return
    await afk_sweep(room)
    manager.bot_night_actions(room)
    await advance_night(room)


def _night_seconds(room) -> int:
    return room.effective_times()["night_time"]


async def _goto_night_role(room, phase: Phase, key: str, mood: str):
    room.phase = phase
    await emit_narrator(room, pick_narrator(key, room), mood)
    manager.bot_night_actions(room)
    await emit_room_state(room)
    await start_phase_timer(room, _night_seconds(room), night_phase_timeout)


async def advance_night(room):
    phase = room.phase
    s = room.settings

    async def has_role(role: Role) -> bool:
        return any(p.role == role and p.alive for p in room.players.values())

    if phase == Phase.NIGHT_MAFIA:
        if s.silencer and await has_role(Role.SILENCER):
            await _goto_night_role(room, Phase.NIGHT_SILENCER, "silencer", "danger")
            return
        room.phase = Phase.NIGHT_SILENCER
        await advance_night(room)
        return

    if phase == Phase.NIGHT_SILENCER:
        if s.natasha and await has_role(Role.NATASHA):
            await _goto_night_role(room, Phase.NIGHT_NATASHA, "natasha", "danger")
            return
        room.phase = Phase.NIGHT_NATASHA
        await advance_night(room)
        return

    if phase == Phase.NIGHT_NATASHA:
        if s.doctor and await has_role(Role.DOCTOR):
            await _goto_night_role(room, Phase.NIGHT_DOCTOR, "doctor", "hope")
            return
        room.phase = Phase.NIGHT_DOCTOR
        await advance_night(room)
        return

    if phase == Phase.NIGHT_DOCTOR:
        if s.bodyguard and await has_role(Role.BODYGUARD):
            await _goto_night_role(room, Phase.NIGHT_BODYGUARD, "bodyguard", "hope")
            return
        room.phase = Phase.NIGHT_BODYGUARD
        await advance_night(room)
        return

    if phase == Phase.NIGHT_BODYGUARD:
        if s.detective and await has_role(Role.DETECTIVE):
            await _goto_night_role(room, Phase.NIGHT_DETECTIVE, "detective", "mystery")
            return
        room.phase = Phase.NIGHT_DETECTIVE
        await advance_night(room)
        return

    if phase == Phase.NIGHT_DETECTIVE:
        if s.psychiatrist and await has_role(Role.PSYCHIATRIST):
            psych = next(p for p in room.players.values() if p.role == Role.PSYCHIATRIST and p.alive)
            if not psych.psych_used:
                await _goto_night_role(room, Phase.NIGHT_PSYCH, "psych", "mystery")
                return
        room.phase = Phase.NIGHT_PSYCH
        await advance_night(room)
        return

    if phase == Phase.NIGHT_PSYCH:
        if s.serial_killer and await has_role(Role.SERIAL_KILLER):
            await _goto_night_role(room, Phase.NIGHT_KILLER, "killer", "danger")
            return
        room.phase = Phase.NIGHT_KILLER
        await advance_night(room)
        return

    if phase == Phase.NIGHT_KILLER:
        needs_sniper = (
            s.sniper
            and not room.sniper_used
            and await has_role(Role.SNIPER)
        )
        needs_vigilante = (
            s.vigilante
            and not room.vigilante_used
            and await has_role(Role.VIGILANTE)
        )
        if needs_sniper or needs_vigilante:
            await _goto_night_role(room, Phase.NIGHT_SNIPER, "sniper", "tension")
            return
        await finish_night(room)
        return

    if phase == Phase.NIGHT_SNIPER:
        na = room.night_actions
        needs_sniper = (
            s.sniper
            and not room.sniper_used
            and await has_role(Role.SNIPER)
            and not na.sniper_acted_tonight
        )
        needs_vigilante = (
            s.vigilante
            and not room.vigilante_used
            and await has_role(Role.VIGILANTE)
            and not na.vigilante_acted_tonight
        )
        if needs_sniper or needs_vigilante:
            label = "sniper" if needs_sniper else "vigilante"
            await _goto_night_role(room, Phase.NIGHT_SNIPER, label, "tension")
            return
        await finish_night(room)
        return


async def finish_night(room):
    result = manager.resolve_night(room)
    # مرده‌ها تماشاگر دید تایم‌لاین می‌گیرند (بدون تغییر is_spectator تا نقش در آخر بازی بماند)
    room.phase = Phase.DAY_ANNOUNCE
    room.voice_mode = "mute"
    await sio.emit("atmosphere", {"mode": "day"}, room=room.code)
    await emit_voice_policy(room)

    if result.get("guard_died_name") and result.get("saved"):
        text = f"صبح شد. بادیگارد {result['guard_died_name']} جان خود را فدا کرد و شهر نفس کشید."
        mood = "hope"
        await sio.emit(
            "death_effect",
            {"name": result["guard_died_name"], "cinematic": True},
            room=room.code,
        )
    elif result["saved"]:
        text = pick_narrator("day_saved", room)
        mood = "hope"
    elif result["killed_name"]:
        text = pick_narrator("day_kill", room, name=result["killed_name"])
        mood = "death"
        await sio.emit(
            "death_effect",
            {"name": result["killed_name"], "cinematic": True},
            room=room.code,
        )
    else:
        text = pick_narrator("day_none", room)
        mood = "calm"

    await emit_narrator(room, text, mood)
    if result.get("silenced_name"):
        await emit_narrator(
            room,
            pick_narrator("silenced", room, name=result["silenced_name"]),
            "tension",
            wait=True,
        )
    if result.get("reporter_hint"):
        await emit_narrator(room, result["reporter_hint"], "mystery", wait=True)

    await emit_room_state(room, {"night_result": result})
    await persist_room(room)

    winner = manager.check_winner(room)
    if winner:
        await end_game(room, winner)
        return

    await asyncio.sleep(1.0)
    room.day_number += 1
    # رأی اعتماد قبل از بحث در حالت تورنمنت
    if room.settings.tournament:
        await begin_trust_vote(room)
    else:
        await start_speak_round(room)


async def begin_trust_vote(room):
    room.phase = Phase.DAY_TRUST
    room.trust_votes = {}
    room.voice_mode = "mute"
    times = room.effective_times()
    await emit_narrator(room, pick_narrator("trust", room), "tension")
    await emit_room_state(room)
    await start_phase_timer(room, times["vote_time"], trust_timeout)


async def trust_timeout(code: str):
    room = manager.rooms.get(code)
    if not room or room.phase != Phase.DAY_TRUST:
        return
    accused = manager.resolve_trust(room)
    if accused and accused in room.players:
        room.defense_target = accused
        await begin_defense(room)
    else:
        await start_speak_round(room)


async def begin_defense(room):
    room.phase = Phase.DAY_DEFENSE
    times = room.effective_times()
    target = room.players.get(room.defense_target)
    name = target.name if target else "متهم"
    room.current_speaker = room.defense_target
    room.voice_mode = "speaker" if room.settings.game_mode != "text_only" else "mute"
    await emit_narrator(room, pick_narrator("defense", room, name=name), "tension")
    await emit_voice_policy(room)
    await emit_room_state(room)
    await start_phase_timer(room, times["defense_time"], defense_timeout)


async def defense_timeout(code: str):
    room = manager.rooms.get(code)
    if not room:
        return
    await begin_vote(room)


async def start_speak_round(room):
    alive = [p for p in room.alive_players() if p.connected or p.is_bot]
    room.speak_queue = [p.sid for p in alive]
    room.speak_index = 0
    room.phase = Phase.DAY_DISCUSS
    room.voice_mode = "mute" if room.settings.game_mode == "text_only" else "speaker"
    room.current_speaker = None
    room.challenge_pending = None
    room.challenge_queue = []
    room.speak_stack = None
    room.is_challenge_turn = False
    room.challenges_used = {}

    await emit_narrator(room, pick_narrator("discuss", room), "talk")
    await emit_room_state(room)
    await next_speak_turn(room)


async def next_speak_turn(room):
    if room.phase != Phase.DAY_DISCUSS:
        return

    # اول صف چالش‌های «بعد از نوبت»
    if room.challenge_queue and not room.speak_stack:
        item = room.challenge_queue.pop(0)
        await start_bonus_speak(room, item["sid"], item["seconds"], challenge=True)
        return

    # رد کردن بازیکن مرده/قطع/ساکت‌شده
    while room.speak_index < len(room.speak_queue):
        sid = room.speak_queue[room.speak_index]
        p = room.players.get(sid)
        if (
            p
            and p.alive
            and p.connected
            and not p.is_spectator
            and sid != room.silenced_sid
        ):
            break
        # اگر ساکت شده، اعلام و رد شو
        if p and sid == room.silenced_sid and p.alive:
            await emit_narrator(
                room,
                f"{p.name} امروز ساکت است و نوبت صحبت ندارد.",
                "calm",
                wait=False,
            )
        room.speak_index += 1
    else:
        room.current_speaker = None
        room.is_challenge_turn = False
        await begin_vote(room)
        return

    sid = room.speak_queue[room.speak_index]
    player = room.players[sid]
    room.current_speaker = sid
    room.voice_mode = "speaker"
    room.is_challenge_turn = False
    speak_sec = room.effective_times()["speak_time"]
    if player.is_bot:
        speak_sec = min(speak_sec, 3)

    await emit_voice_policy(room)
    await emit_narrator(
        room,
        pick_narrator("speak_turn", room, name=player.name),
        "talk",
        wait=True,
    )
    room.phase_ends_at = time.time() + speak_sec
    await emit_room_state(room)
    if telegram_auth.is_enabled() and not player.is_bot:
        asyncio.create_task(telegram_notify.notify_your_turn(player, room.code))
    await sio.emit(
        "speak_turn",
        {
            "sid": sid,
            "name": player.name,
            "avatar": player.avatar,
            "index": room.speak_index + 1,
            "total": len(room.speak_queue),
            "seconds": speak_sec,
            "ends_at": room.phase_ends_at,
            "challenge": False,
        },
        room=room.code,
    )
    await start_phase_timer(room, speak_sec, speak_turn_timeout)


async def start_bonus_speak(room, sid: str, seconds: int, challenge: bool = True):
    player = room.players.get(sid)
    if not player or not player.alive or not player.connected:
        await next_speak_turn(room)
        return

    room.current_speaker = sid
    room.voice_mode = "speaker"
    room.is_challenge_turn = challenge
    room.challenge_pending = None

    await emit_voice_policy(room)
    await emit_narrator(
        room,
        pick_narrator("challenge_grant", room, name=player.name, sec=seconds),
        "talk",
        wait=True,
    )
    room.phase_ends_at = time.time() + seconds
    await emit_room_state(room)
    await sio.emit(
        "speak_turn",
        {
            "sid": sid,
            "name": player.name,
            "avatar": player.avatar,
            "index": room.speak_index + 1,
            "total": len(room.speak_queue),
            "seconds": seconds,
            "ends_at": room.phase_ends_at,
            "challenge": True,
        },
        room=room.code,
    )
    await start_phase_timer(room, seconds, challenge_turn_timeout)


async def speak_turn_timeout(code: str):
    room = manager.rooms.get(code)
    if not room or room.phase != Phase.DAY_DISCUSS:
        return
    await afk_sweep(room)
    prev = room.players.get(room.current_speaker) if room.current_speaker else None
    if prev and not room.is_challenge_turn:
        await emit_narrator(
            room,
            pick_narrator("speak_end", room, name=prev.name),
            "calm",
            wait=False,
        )
    room.challenge_pending = None
    await _clear_challenge_auto(room)

    # بعد از نوبت اصلی: اول چالش‌های صف، بعد نفر بعدی
    if room.challenge_queue:
        room.is_challenge_turn = False
        await next_speak_turn(room)
        return

    room.speak_index += 1
    room.is_challenge_turn = False
    await next_speak_turn(room)


async def challenge_turn_timeout(code: str):
    room = manager.rooms.get(code)
    if not room or room.phase != Phase.DAY_DISCUSS:
        return

    stack = room.speak_stack
    room.speak_stack = None
    room.is_challenge_turn = False
    room.challenge_pending = None

    # چالش «قبل» — برگشت به نوبت اصلی
    if stack and stack.get("sid") in room.players:
        p = room.players[stack["sid"]]
        if p.alive and p.connected:
            remaining = max(5, int(stack.get("remaining", 10)))
            room.current_speaker = stack["sid"]
            room.voice_mode = "speaker"
            await emit_voice_policy(room)
            await emit_narrator(
                room,
                f"ادامه نوبت {p.name}. {remaining} ثانیه باقی مانده.",
                "talk",
                wait=True,
            )
            room.phase_ends_at = time.time() + remaining
            await emit_room_state(room)
            await sio.emit(
                "speak_turn",
                {
                    "sid": p.sid,
                    "name": p.name,
                    "avatar": p.avatar,
                    "index": room.speak_index + 1,
                    "total": len(room.speak_queue),
                    "seconds": remaining,
                    "ends_at": room.phase_ends_at,
                    "challenge": False,
                    "resumed": True,
                },
                room=room.code,
            )
            await start_phase_timer(room, remaining, speak_turn_timeout)
            return

    # چالش‌های «بعد» مانده
    if room.challenge_queue:
        await next_speak_turn(room)
        return

    # صف چالش خالی → نفر بعدی صف اصلی
    room.speak_index += 1
    await next_speak_turn(room)


async def _clear_challenge_auto(room):
    task = getattr(room, "_challenge_auto_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    room._challenge_auto_task = None


async def _schedule_challenge_auto(room):
    await _clear_challenge_auto(room)

    async def auto():
        try:
            await asyncio.sleep(8)
            if not room.challenge_pending:
                return
            # پذیرش خودکار: بعد از نوبت، ۱۰ ثانیه (امن و عادلانه)
            pending = room.challenge_pending
            pending["seconds"] = min(int(pending.get("seconds", 10)), 20)
            pending["position"] = "after"
            pending["auto"] = True
            await _accept_challenge(room, auto=True)
        except asyncio.CancelledError:
            pass

    room._challenge_auto_task = asyncio.create_task(auto())


async def _accept_challenge(room, auto: bool = False):
    pending = room.challenge_pending
    if not pending:
        return
    await _clear_challenge_auto(room)

    from_sid = pending["from_sid"]
    seconds = int(pending.get("seconds", 10))
    seconds = 20 if seconds >= 20 else 10
    position = pending.get("position", "after")
    challenger = room.players.get(from_sid)
    if not challenger or not challenger.alive:
        room.challenge_pending = None
        await emit_room_state(room)
        return

    room.challenges_used[from_sid] = room.challenges_used.get(from_sid, 0) + 1
    room.challenge_pending = None

    # اگر کمتر از ۶ ثانیه از نوبت مانده، «قبل» را به «بعد» تبدیل کن
    left = 0
    if room.phase_ends_at:
        left = room.phase_ends_at - time.time()
    if position == "before" and left < 6:
        position = "after"

    if auto or position == "after":
        room.challenge_queue.append({"sid": from_sid, "seconds": seconds})
        text = (
            pick_narrator("challenge_auto", room, name=challenger.name, sec=seconds)
            if auto
            else pick_narrator("challenge_accept", room, name=challenger.name, sec=seconds)
            + " بعد از این نوبت."
        )
        await emit_narrator(room, text, "talk", wait=False)
        await sio.emit(
            "toast",
            {
                "message": f"چالش {challenger.name}: {seconds}ث بعد از نوبت",
                "type": "success",
            },
            room=room.code,
        )
        await emit_room_state(room)
        return

    # قبل از ادامه نوبت فعلی — pause
    if not room.current_speaker or room.is_challenge_turn:
        room.challenge_queue.append({"sid": from_sid, "seconds": seconds})
        await emit_room_state(room)
        return

    remaining = max(5, int(left)) if left > 0 else room.settings.speak_time
    room.speak_stack = {"sid": room.current_speaker, "remaining": remaining}
    await cancel_phase_timer(room.code)
    await emit_narrator(
        room,
        pick_narrator("challenge_accept", room, name=challenger.name, sec=seconds),
        "talk",
        wait=False,
    )
    await sio.emit(
        "toast",
        {"message": f"چالش فوری {challenger.name}", "type": "warn"},
        room=room.code,
    )
    await start_bonus_speak(room, from_sid, seconds, challenge=True)


async def begin_vote(room):
    room.phase = Phase.DAY_VOTE
    room.votes = {}
    room.current_speaker = None
    room.voice_mode = "mute" if room.settings.game_mode == "text_only" else "all"
    room.challenge_pending = None
    room.challenge_queue = []
    room.speak_stack = None
    room.is_challenge_turn = False
    await _clear_challenge_auto(room)
    manager.bot_votes(room)
    await emit_voice_policy(room)
    await emit_narrator(room, pick_narrator("vote", room), "tension")
    await emit_room_state(room)
    await start_phase_timer(room, room.effective_times()["vote_time"], vote_timeout)
    await maybe_auto_finish_vote(room)


async def discuss_timeout(code: str):
    room = manager.rooms.get(code)
    if not room or room.phase != Phase.DAY_DISCUSS:
        return
    room.current_speaker = None
    await begin_vote(room)


async def vote_timeout(code: str):
    room = manager.rooms.get(code)
    if not room or room.phase != Phase.DAY_VOTE:
        return
    await finish_vote(room)


async def finish_vote(room):
    result = manager.resolve_vote(room)
    room.phase = Phase.DAY_RESULT
    room.voice_mode = "mute"
    await emit_voice_policy(room)

    if result.get("tie"):
        text = pick_narrator("tie", room)
        mood = "calm"
    elif result.get("name"):
        text = pick_narrator("exec", room, name=result["name"])
        mood = "death"
        await sio.emit("death_effect", {"name": result["name"]}, room=room.code)
    else:
        text = pick_narrator("no_exec", room)
        mood = "calm"

    await emit_narrator(room, text, mood)
    await emit_room_state(room, {"vote_result": result})

    if result.get("executed"):
        ex = room.players.get(result["executed"])
        if ex and ex.role == Role.JOKER:
            await asyncio.sleep(2)
            await end_game(room, "joker")
            return

    winner = manager.check_winner(room)
    if winner:
        await asyncio.sleep(2)
        await end_game(room, winner)
        return

    await asyncio.sleep(2.5)
    await begin_night(room)


async def end_game(room, winner: str):
    await cancel_phase_timer(room.code)
    room.phase = Phase.GAME_OVER
    room.winner = winner
    room.voice_mode = "all"
    room.current_speaker = None
    room.add_timeline("game_over", f"پایان — برنده: {winner}", winner=winner)
    if winner == "town":
        text = pick_narrator("town_win", room)
    elif winner == "killer":
        text = pick_narrator("killer_win", room)
    elif winner == "joker":
        text = "جوکر با اعدام شهر برنده شد! 🃏"
    else:
        text = pick_narrator("mafia_win", room)
    mood = "victory" if winner in ("town", "joker") else "defeat"
    await emit_narrator(room, text, mood)
    await sio.emit("atmosphere", {"mode": "end", "winner": winner}, room=room.code)
    await emit_voice_policy(room)
    await emit_room_state(room, {"timeline": room.timeline})

    # آمار پروفایل / رنک
    for p in room.players.values():
        if p.is_bot or not p.token or p.is_spectator:
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
        badge = None
        if won and p.role == Role.DETECTIVE:
            badge = "first_correct_detect"
        ranked_delta = 0
        if room.settings.ranked:
            ranked_delta = 25 if won else -10
        try:
            hosts_delta = 1 if p.is_host else 0
            persist.upsert_profile(
                p.token,
                name=p.name,
                avatar=p.avatar,
                wins_delta=1 if won else 0,
                losses_delta=0 if won else 1,
                badge=badge,
                ranked_delta=ranked_delta,
                season=mafi_extras.CURRENT_SEASON,
                hosts_delta=hosts_delta,
            )
            mafi_extras.check_achievements(room, p, winner)
        except Exception as e:
            print("[profile]", e)
    try:
        mafi_extras.save_match(room, winner)
        mafi_pro.metric_inc("games_finished")
    except Exception as e:
        print("[match]", e)
    if room.settings.ranked:
        try:
            mafi_pro.update_ranked_mmr(
                list(room.players.values()), winner, mafi_extras.CURRENT_SEASON
            )
        except Exception as e:
            print("[mmr]", e)
    for p in room.players.values():
        if p.is_bot or not p.token or p.is_spectator:
            continue
        try:
            xp = 50 if room.settings.ranked else 25
            mafi_pro.season_pass_add_xp(p.token, mafi_extras.CURRENT_SEASON, xp)
        except Exception:
            pass
    if telegram_auth.is_enabled():
        asyncio.create_task(telegram_notify.notify_game_over(room, winner))
    await persist_room(room)


async def maybe_auto_advance_night(room):
    actions = room.night_actions
    if room.phase == Phase.NIGHT_MAFIA:
        mafias = room.mafia_players()
        if mafias and len(actions.mafia_votes) >= len(mafias):
            await cancel_phase_timer(room.code)
            await advance_night(room)
    elif room.phase == Phase.NIGHT_SILENCER:
        if actions.silence_target is not None:
            await cancel_phase_timer(room.code)
            await advance_night(room)
    elif room.phase == Phase.NIGHT_DOCTOR:
        if actions.doctor_save is not None:
            await cancel_phase_timer(room.code)
            await advance_night(room)
    elif room.phase == Phase.NIGHT_BODYGUARD:
        if actions.bodyguard_protect is not None:
            await cancel_phase_timer(room.code)
            await advance_night(room)
    elif room.phase == Phase.NIGHT_DETECTIVE:
        if actions.detective_check is not None:
            await cancel_phase_timer(room.code)
            await advance_night(room)
    elif room.phase == Phase.NIGHT_NATASHA:
        if actions.natasha_target is not None:
            await cancel_phase_timer(room.code)
            await advance_night(room)
    elif room.phase == Phase.NIGHT_PSYCH:
        if actions.psych_block is not None:
            await cancel_phase_timer(room.code)
            await advance_night(room)
    elif room.phase == Phase.NIGHT_KILLER:
        if actions.killer_target is not None:
            await cancel_phase_timer(room.code)
            await advance_night(room)
    elif room.phase == Phase.NIGHT_SNIPER:
        s = room.settings
        sniper_done = (
            not s.sniper
            or room.sniper_used
            or actions.sniper_acted_tonight
            or not any(p.role == Role.SNIPER and p.alive for p in room.players.values())
        )
        vig_done = (
            not s.vigilante
            or room.vigilante_used
            or actions.vigilante_acted_tonight
            or not any(p.role == Role.VIGILANTE and p.alive for p in room.players.values())
        )
        if sniper_done and vig_done:
            await cancel_phase_timer(room.code)
            await advance_night(room)


async def maybe_auto_finish_vote(room):
    alive = room.alive_players()
    if alive and len(room.votes) >= len(alive):
        await cancel_phase_timer(room.code)
        await finish_vote(room)


@app.get("/")
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/preview")
@app.get("/preview/")
async def mobile_preview():
    return FileResponse(FRONTEND / "preview-phone.html")


@app.get("/apk-boot")
@app.get("/apk-boot/")
async def apk_boot_index():
    boot = APK_WWW / "index.html"
    if not boot.is_file():
        return JSONResponse({"ok": False, "error": "Mobile APP/www missing"}, status_code=404)
    return FileResponse(boot)


@app.get("/apk-boot/{asset_path:path}")
async def apk_boot_assets(asset_path: str):
    base = APK_WWW.resolve()
    target = (APK_WWW / asset_path).resolve()
    if not str(target).startswith(str(base)) or not target.is_file():
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    return FileResponse(target)


@app.get("/health")
async def health():
    extra = mafi_extras.validate_cloud_env()
    sb = {"enabled": False, "ok": False}
    try:
        import supabase_persist

        sb = supabase_persist.ping()
    except Exception as e:
        sb = {"enabled": False, "ok": False, "error": str(e)[:120]}
    public = _public_https()
    return {
        "ok": True,
        "rooms": len(manager.rooms),
        "tts": True,
        "telegram": telegram_auth.is_enabled(),
        "season": mafi_extras.CURRENT_SEASON,
        "version": 29,
        "public_url": public,
        "supabase": sb,
        **extra,
    }


@app.get("/metrics")
async def metrics():
    return mafi_pro.metrics_snapshot(len(manager.rooms))


@app.get("/api/ice")
async def ice_config():
    return {"iceServers": mafi_pro.ice_servers()}


def _server_port() -> int:
    for key in ("MAFI_PORT", "PORT"):
        raw = os.environ.get(key, "").strip()
        if raw.isdigit():
            return int(raw)
    return 8000


def _is_placeholder_public_url(url: str) -> bool:
    u = (url or "").strip().lower()
    if not u:
        return True
    bad = (
        "your-service",
        "your-cloud",
        "your-domain",
        "example.com",
        "localhost",
        "127.0.0.1",
        "changeme",
        "placeholder",
    )
    return any(b in u for b in bad)


def _lan_ipv4() -> list[str]:
    found: list[str] = []

    def add(ip: Optional[str]) -> None:
        if not ip or ip.startswith("127.") or ip in found:
            return
        # Skip link-local / bogus
        if ip.startswith("169.254."):
            return
        found.append(ip)

    # Android (Chaquopy): only Wi-Fi / hotspot, not mobile data
    if os.environ.get("MAFI_ANDROID"):
        try:
            from java.net import Inet4Address, NetworkInterface  # type: ignore

            skip = ("rmnet", "ccmni", "pdp", "dummy", "tun", "sit", "ipsec", "lo")
            wifi_names = ("wlan", "ap", "swlan", "softap", "wifi")
            ifaces = NetworkInterface.getNetworkInterfaces()
            while ifaces.hasMoreElements():
                ni = ifaces.nextElement()
                name = str(ni.getName() or "").lower()
                if any(name.startswith(s) for s in skip):
                    continue
                if not any(w in name for w in wifi_names):
                    continue
                try:
                    if ni.isLoopback() or not ni.isUp():
                        continue
                except Exception:
                    pass
                addrs = ni.getInetAddresses()
                while addrs.hasMoreElements():
                    addr = addrs.nextElement()
                    if isinstance(addr, Inet4Address) and not addr.isLoopbackAddress():
                        add(str(addr.getHostAddress()).split("%", 1)[0])
        except Exception:
            pass
    else:
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                add(info[4][0])
        except OSError:
            pass
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("8.8.8.8", 80))
            add(probe.getsockname()[0])
            probe.close()
        except OSError:
            pass

    def score(ip: str) -> int:
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172."):
            return 2
        return 3

    found.sort(key=score)
    return found


def _ngrok_https() -> Optional[str]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1.2) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        for tunnel in data.get("tunnels") or []:
            url = str(tunnel.get("public_url") or "")
            if url.startswith("https://") and not _is_placeholder_public_url(url):
                return url.rstrip("/")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        pass
    return None


def _public_https() -> Optional[str]:
    """Cloud URL (Render/VPS) preferred over ephemeral ngrok for QR invites."""
    for key in ("MAFI_PUBLIC_URL", "MAFI_WEBAPP_URL", "RENDER_EXTERNAL_URL"):
        raw = (os.environ.get(key) or "").strip().rstrip("/")
        if not raw:
            continue
        if _is_placeholder_public_url(raw):
            continue
        if raw.startswith("https://") or raw.startswith("http://"):
            return raw
    host = (os.environ.get("RENDER_EXTERNAL_HOSTNAME") or "").strip().rstrip("/")
    if host and not _is_placeholder_public_url(host):
        return "https://" + host
    return _ngrok_https()


@app.get("/api/network")
async def network_info():
    port = _server_port()
    lans = _lan_ipv4()
    online = _public_https()
    return {
        "port": port,
        "local": f"http://127.0.0.1:{port}",
        "lan_ips": lans,
        "lan": [f"http://{ip}:{port}" for ip in lans],
        "online": online,
        "public_url": online,
    }


@app.get("/api/qr")
async def qr_code(data: str = Query(..., min_length=4, max_length=500)):
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError:
        return Response("qrcode package missing — pip install qrcode", status_code=500)
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(image_factory=SvgPathImage)
        buf = BytesIO()
        img.save(buf)
        return Response(content=buf.getvalue(), media_type="image/svg+xml")
    except Exception as e:
        return Response(f"qr failed: {e}", status_code=400)


@sio.event
async def connect(sid, environ):
    mafi_pro.metric_inc("socket_events")
    mafi_pro.touch_activity(sid)
    await sio.emit("connected", {"sid": sid, "version": 29}, to=sid)


@sio.event
async def disconnect(sid):
    room = manager.leave(sid)
    if room:
        await sio.leave_room(sid, room.code)
        await sio.emit("voice_peer_left", {"sid": sid}, room=room.code)
        await emit_room_state(room)
        await sio.emit(
            "toast",
            {"message": "یک بازیکن قطع شد", "type": "warn"},
            room=room.code,
        )


@sio.event
async def join_room(sid, data):
    if not mafi_pro.socket_rate(sid, "join_room", 8, 30.0):
        await sio.emit("error", {"message": "درخواست زیاد — کمی صبر کن"}, to=sid)
        return
    mafi_pro.touch_activity(sid)
    data = data or {}
    name = str(data.get("name", "")).strip()
    code = str(data.get("code", "")).strip().upper()
    spectator = bool(data.get("spectator", False))
    token = str(data.get("token", "")).strip()
    password = str(data.get("password", ""))
    avatar = str(data.get("avatar", ""))
    tg_id, tg_token, tg_name, is_tg = _telegram_from_payload(data)
    if tg_token:
        token = tg_token
    if tg_name and (not name or is_tg):
        name = tg_name
    if not name or len(name) > 20:
        await sio.emit("error", {"message": "نام نامعتبر است"}, to=sid)
        return
    if token:
        ban_reason = mafi_pro.is_banned(token)
        if ban_reason:
            await sio.emit("error", {"message": f"مسدود: {ban_reason}"}, to=sid)
            return
    fp = str(data.get("fingerprint", "")).strip()
    if fp:
        mafi_pro.set_fingerprint(sid, fp)
    room, err = manager.join_room(
        code, sid, name, spectator, token=token, password=password, avatar=avatar
    )
    if err:
        await sio.emit("error", {"message": err}, to=sid)
        return
    await sio.enter_room(sid, room.code)
    manager.apply_auto_roles(room)
    me = room.players.get(sid)
    _attach_telegram_player(me, tg_id)
    if me and me.token:
        await sio.emit("session", {"token": me.token, "code": room.code}, to=sid)
        try:
            persist.upsert_profile(me.token, name=me.name, avatar=me.avatar)
        except Exception:
            pass
    await emit_room_state(room)
    await emit_voice_policy(room)
    await persist_room(room)
    await sio.emit(
        "toast",
        {"message": f"{name} وارد شد", "type": "info"},
        room=room.code,
    )
    await sio.emit("voice_peer_joined", {"sid": sid, "name": name}, room=room.code)
    if is_tg and telegram_auth.is_enabled() and me and not me.is_host:
        asyncio.create_task(telegram_notify.notify_player_joined(room, me))


@sio.event
async def rejoin(sid, data):
    data = data or {}
    token = str(data.get("token", "")).strip()
    code = str(data.get("code", "")).strip().upper()
    tg_id, tg_token, tg_name, is_tg = _telegram_from_payload(data)
    if tg_token:
        token = tg_token
    room, err = manager.rejoin(sid, token, code)
    if err:
        await sio.emit("error", {"message": err}, to=sid)
        return
    await sio.enter_room(sid, room.code)
    me = room.players.get(sid)
    _attach_telegram_player(me, tg_id)
    if me:
        await sio.emit("session", {"token": me.token, "code": room.code}, to=sid)
    await emit_room_state(room)
    await emit_voice_policy(room)
    await sio.emit("toast", {"message": f"{me.name if me else 'بازیکن'} برگشت", "type": "success"}, room=room.code)


@sio.event
async def create_room(sid, data):
    data = data or {}
    name = str(data.get("name", "")).strip()
    token = str(data.get("token", "")).strip()
    avatar = str(data.get("avatar", ""))
    tg_id, tg_token, tg_name, is_tg = _telegram_from_payload(data)
    if tg_token:
        token = tg_token
    if tg_name and (not name or is_tg):
        name = tg_name
    if not name or len(name) > 20:
        await sio.emit("error", {"message": "نام نامعتبر است"}, to=sid)
        return
    old = manager.leave(sid)
    if old:
        await emit_room_state(old)
    room = manager.create_room(sid, name, token=token, avatar=avatar)
    if is_tg:
        room.settings.game_mode = "text_only"
        room.voice_mode = "mute"
    else:
        room.voice_mode = "all"
    await sio.enter_room(sid, room.code)
    me = room.players[sid]
    _attach_telegram_player(me, tg_id)
    await sio.emit("room_created", {"code": room.code}, to=sid)
    await sio.emit("session", {"token": me.token, "code": room.code}, to=sid)
    try:
        persist.upsert_profile(me.token, name=me.name, avatar=me.avatar)
    except Exception:
        pass
    await emit_room_state(room)
    await emit_voice_policy(room)
    await persist_room(room)
    await sio.emit(
        "toast", {"message": f"اتاق {room.code} ساخته شد", "type": "success"}, to=sid
    )
    if is_tg and telegram_auth.is_enabled():
        asyncio.create_task(telegram_notify.notify_room_created_host(room, me))


@sio.event
async def claim_host(sid, data=None):
    room, err = manager.claim_host(sid)
    if err:
        await sio.emit("error", {"message": err}, to=sid)
        return
    await emit_room_state(room)
    await sio.emit(
        "toast",
        {"message": f"{room.players[sid].name} سازنده اتاق شد", "type": "info"},
        room=room.code,
    )


@sio.event
async def update_settings(sid, data):
    room, err = manager.update_settings(sid, data or {})
    if err:
        await sio.emit("error", {"message": err}, to=sid)
        return
    await emit_room_state(room)


@sio.event
async def start_game(sid, data=None):
    room = manager.get_room_by_sid(sid)
    if not room:
        await sio.emit("error", {"message": "اتاق پیدا نشد"}, to=sid)
        return
    if room.phase != Phase.LOBBY:
        await sio.emit("error", {"message": "بازی در جریان است"}, to=sid)
        return
    player = room.players.get(sid)
    if not player or player.is_spectator:
        await sio.emit("error", {"message": "تماشاگر نمی‌تواند شروع کند"}, to=sid)
        return

    ready = [p for p in room.players.values() if not p.is_spectator and p.connected]
    if len(ready) < 6:
        await sio.emit(
            "error",
            {"message": f"حداقل ۶ بازیکن وصل لازم است ({len(ready)}/۶)"},
            to=sid,
        )
        return

    manager.ensure_host(room)
    err = manager.assign_roles(room)
    if err:
        await sio.emit("error", {"message": err}, to=sid)
        return

    room.phase = Phase.DEALING
    room.voice_mode = "mute"
    await emit_voice_policy(room)
    await emit_narrator(room, pick_narrator("deal", room), "mystery")
    await emit_room_state(room)

    for psid, pl in room.players.items():
        if pl.is_spectator:
            continue
        await sio.emit("role_reveal", pl.private(), to=psid)

    if telegram_auth.is_enabled():
        asyncio.create_task(telegram_notify.notify_game_start(room))

    await start_phase_timer(room, 8, advance_after_deal)


@sio.event
async def night_action(sid, data):
    room = manager.get_room_by_sid(sid)
    if not room:
        return
    player = room.players.get(sid)
    if not player or not player.alive or player.is_spectator:
        return

    data = data or {}
    target = data.get("target")
    action = data.get("action")

    if room.phase == Phase.NIGHT_MAFIA and is_mafia_role(player.role):
        # همه مافیا (شامل رئیس و سایلنسر) در قتل شب شرکت می‌کنند
        if target and target in room.players and room.players[target].alive:
            room.night_actions.mafia_votes[sid] = target
            await sio.emit(
                "toast", {"message": "انتخاب ثبت شد", "type": "success"}, to=sid
            )
            await emit_room_state(room)
            await maybe_auto_advance_night(room)

    elif room.phase == Phase.NIGHT_SILENCER and player.role == Role.SILENCER:
        if target and target in room.players and room.players[target].alive:
            room.night_actions.silence_target = target
            await sio.emit(
                "toast", {"message": "ساکت‌سازی ثبت شد", "type": "success"}, to=sid
            )
            await emit_room_state(room)
            await maybe_auto_advance_night(room)

    elif room.phase == Phase.NIGHT_DOCTOR and player.role == Role.DOCTOR:
        if target and target in room.players and room.players[target].alive:
            room.night_actions.doctor_save = target
            await sio.emit(
                "toast", {"message": "محافظت ثبت شد", "type": "success"}, to=sid
            )
            await emit_room_state(room)
            await maybe_auto_advance_night(room)

    elif room.phase == Phase.NIGHT_BODYGUARD and player.role == Role.BODYGUARD:
        if target and target in room.players and room.players[target].alive:
            room.night_actions.bodyguard_protect = target
            await sio.emit(
                "toast", {"message": "محافظت بادیگارد ثبت شد", "type": "success"}, to=sid
            )
            await emit_room_state(room)
            await maybe_auto_advance_night(room)

    elif room.phase == Phase.NIGHT_DETECTIVE and player.role == Role.DETECTIVE:
        if target and target in room.players and room.players[target].alive:
            room.night_actions.detective_check = target
            await sio.emit(
                "toast", {"message": "استعلام ثبت شد", "type": "success"}, to=sid
            )
            await emit_room_state(room)
            await maybe_auto_advance_night(room)

    elif room.phase == Phase.NIGHT_SNIPER and player.role in (Role.SNIPER, Role.VIGILANTE):
        na = room.night_actions
        if player.role == Role.SNIPER:
            if room.sniper_used or na.sniper_acted_tonight:
                return
        elif player.role == Role.VIGILANTE:
            if room.vigilante_used or na.vigilante_acted_tonight:
                return
        if action == "skip":
            if player.role == Role.SNIPER:
                na.sniper_shot = None
                na.sniper_acted_tonight = True
            else:
                na.vigilante_shot = None
                na.vigilante_acted_tonight = True
            await cancel_phase_timer(room.code)
            await advance_night(room)
            return
        if target and target in room.players and room.players[target].alive:
            if player.role == Role.SNIPER:
                na.sniper_shot = target
                na.sniper_acted_tonight = True
            else:
                na.vigilante_shot = target
                na.vigilante_acted_tonight = True
            await sio.emit(
                "toast", {"message": "شلیک ثبت شد", "type": "warn"}, to=sid
            )
            await cancel_phase_timer(room.code)
            await advance_night(room)

    elif room.phase == Phase.NIGHT_PSYCH and player.role == Role.PSYCHIATRIST:
        if player.psych_used:
            await sio.emit("toast", {"message": "قبلاً استفاده کردی", "type": "warn"}, to=sid)
            return
        if target and target in room.players and room.players[target].alive:
            room.night_actions.psych_block = target
            await sio.emit("toast", {"message": "بلاک ثبت شد", "type": "success"}, to=sid)
            await emit_room_state(room)
            await maybe_auto_advance_night(room)

    elif room.phase == Phase.NIGHT_KILLER and player.role == Role.SERIAL_KILLER:
        if target and target in room.players and room.players[target].alive:
            room.night_actions.killer_target = target
            await sio.emit("toast", {"message": "قتل جانی ثبت شد", "type": "warn"}, to=sid)
            await emit_room_state(room)
            await maybe_auto_advance_night(room)

    elif room.phase == Phase.NIGHT_NATASHA and player.role == Role.NATASHA:
        if target and target in room.players and room.players[target].alive:
            room.night_actions.natasha_target = target
            await sio.emit("toast", {"message": "جذب ناتاشا ثبت شد", "type": "success"}, to=sid)
            await emit_room_state(room)
            await maybe_auto_advance_night(room)

    elif action == "sacrifice" and player.role == Role.SACRIFICE and not player.sacrifice_used:
        if target and target in room.players and room.players[target].alive:
            room.night_actions.sacrifice_for = target
            await sio.emit("toast", {"message": "فداکاری ثبت شد", "type": "info"}, to=sid)
            await emit_room_state(room)


@sio.event
async def cast_vote(sid, data):
    room = manager.get_room_by_sid(sid)
    if not room:
        return
    player = room.players.get(sid)
    if not player or not player.alive or player.is_spectator:
        return
    target = (data or {}).get("target")

    if room.phase == Phase.DAY_TRUST:
        if target == "skip":
            room.trust_votes[sid] = "skip"
        elif target and target in room.players and room.players[target].alive and target != sid:
            room.trust_votes[sid] = target
        else:
            return
        await emit_room_state(room)
        alive = room.alive_players()
        if alive and len(room.trust_votes) >= len(alive):
            await cancel_phase_timer(room.code)
            await trust_timeout(room.code)
        return

    if room.phase != Phase.DAY_VOTE:
        return
    if target == "skip":
        room.votes[sid] = "skip"
    elif (
        target
        and target in room.players
        and room.players[target].alive
        and target != sid
    ):
        room.votes[sid] = target
    else:
        return
    await emit_room_state(room)
    await maybe_auto_finish_vote(room)


@sio.event
async def chat_message(sid, data):
    room = manager.get_room_by_sid(sid)
    if not room:
        return
    player = room.players.get(sid)
    if not player:
        return
    text = str((data or {}).get("text", "")).strip()[:200]
    if not text:
        return

    if not player.alive and not player.is_spectator:
        await sio.emit(
            "toast", {"message": "مرده‌ها نمی‌توانند حرف بزنند", "type": "warn"}, to=sid
        )
        return

    is_mafia_chat = bool((data or {}).get("mafia"))
    msg = {
        "name": player.name,
        "avatar": player.avatar,
        "text": text,
        "time": time.time(),
        "sid": sid,
    }

    if is_mafia_chat:
        if not is_mafia_role(player.role) or not player.alive:
            return
        # فقط فاز شب مافیا/سایلنسر/ناتاشا
        if room.phase not in (
            Phase.NIGHT_MAFIA,
            Phase.NIGHT_SILENCER,
            Phase.NIGHT_NATASHA,
        ):
            room.add_suspicion(player.name, "mafia_chat_day", "چت مافیا خارج شب", player.token)
            persist.log_suspicion(room.code, player.token, player.name, "mafia_chat_day", "خارج شب")
            await sio.emit(
                "toast",
                {"message": "چت مافیا فقط شب مجاز است", "type": "warn"},
                to=sid,
            )
            return
        room.mafia_chat.append(msg)
        for p in room.mafia_players():
            if not p.is_bot:
                await sio.emit("mafia_chat", msg, to=p.sid)
    else:
        if room.silenced_sid == sid and room.phase in (
            Phase.DAY_DISCUSS,
            Phase.DAY_DEFENSE,
            Phase.DAY_VOTE,
        ):
            await sio.emit(
                "toast",
                {"message": "تو ساکت شده‌ای", "type": "warn"},
                to=sid,
            )
            return
        if room.phase not in (
            Phase.DAY_DISCUSS,
            Phase.DAY_VOTE,
            Phase.DAY_TRUST,
            Phase.DAY_DEFENSE,
            Phase.LOBBY,
            Phase.GAME_OVER,
        ):
            await sio.emit(
                "toast",
                {"message": "الان زمان چت عمومی نیست", "type": "warn"},
                to=sid,
            )
            return
        # ضد اسپم ساده
        recent = [m for m in room.chat[-5:] if m.get("sid") == sid]
        if len(recent) >= 4 and time.time() - recent[0]["time"] < 8:
            room.add_suspicion(player.name, "spam", "اسپم چت", player.token)
            persist.log_suspicion(room.code, player.token, player.name, "spam", text[:40])
            await sio.emit("toast", {"message": "کمی آرام‌تر چت کن", "type": "warn"}, to=sid)
            return
        room.chat.append(msg)
        await sio.emit("chat", msg, room=room.code)


@sio.event
async def rematch(sid, data=None):
    room = manager.get_room_by_sid(sid)
    if not room or sid != room.host_sid:
        return
    if room.phase != Phase.GAME_OVER:
        return
    for p in room.players.values():
        p.role = None
        p.alive = True
    room.phase = Phase.LOBBY
    room.winner = None
    room.chat = []
    room.mafia_chat = []
    room.day_number = 0
    room.night_number = 0
    room.current_speaker = None
    room.speak_queue = []
    room.voice_mode = "all"
    await sio.emit("atmosphere", {"mode": "lobby"}, room=room.code)
    await emit_voice_policy(room)
    await emit_room_state(room)


@sio.event
async def leave_game(sid, data=None):
    """خروج قطعی بازیکن از اتاق/بازی و بازگشت به صفحه اصلی"""
    room, name, where = manager.leave_completely(sid)
    if not room:
        await sio.emit("left_game", {"ok": True}, to=sid)
        return
    try:
        await sio.leave_room(sid, room.code)
    except Exception:
        pass
    await sio.emit("voice_peer_left", {"sid": sid}, room=room.code)
    await sio.emit(
        "toast",
        {
            "message": f"{name or 'یک بازیکن'} از بازی خارج شد",
            "type": "warn",
        },
        room=room.code,
    )
    await emit_room_state(room)
    await persist_room(room)
    await sio.emit("left_game", {"ok": True, "where": where}, to=sid)

    # اگر وسط بازی کسی خارج شد و هنوز بازیکن مانده و برنده مشخص شد
    if where == "playing" and room.players:
        winner = manager.check_winner(room)
        if winner:
            await end_game(room, winner)


@sio.event
async def skip_phase(sid, data=None):
    room = manager.get_room_by_sid(sid)
    if not room or sid != room.host_sid:
        return
    await cancel_phase_timer(room.code)
    if room.phase in (
        Phase.NIGHT_MAFIA,
        Phase.NIGHT_SILENCER,
        Phase.NIGHT_NATASHA,
        Phase.NIGHT_DOCTOR,
        Phase.NIGHT_BODYGUARD,
        Phase.NIGHT_DETECTIVE,
        Phase.NIGHT_PSYCH,
        Phase.NIGHT_KILLER,
        Phase.NIGHT_SNIPER,
    ):
        await advance_night(room)
    elif room.phase == Phase.DAY_DISCUSS:
        action = (data or {}).get("action", "turn")
        if action == "all":
            await discuss_timeout(room.code)
        else:
            room.speak_index += 1
            await next_speak_turn(room)
    elif room.phase == Phase.DAY_VOTE:
        await vote_timeout(room.code)
    elif room.phase == Phase.DAY_TRUST:
        await trust_timeout(room.code)
    elif room.phase == Phase.DAY_DEFENSE:
        await defense_timeout(room.code)
    elif room.phase == Phase.DEALING:
        await advance_after_deal(room.code)


@sio.event
async def skip_speak(sid, data=None):
    room = manager.get_room_by_sid(sid)
    if not room or room.phase != Phase.DAY_DISCUSS:
        return
    if room.current_speaker != sid and sid != room.host_sid:
        return
    await cancel_phase_timer(room.code)
    if room.is_challenge_turn or room.speak_stack:
        await challenge_turn_timeout(room.code)
    else:
        await speak_turn_timeout(room.code)


@sio.event
async def challenge_request(sid, data):
    """درخواست چالش از هر بازیکن زنده در فاز بحث"""
    room = manager.get_room_by_sid(sid)
    if not room or room.phase != Phase.DAY_DISCUSS:
        return
    player = room.players.get(sid)
    if not player or not player.alive or player.is_spectator:
        return
    if not room.current_speaker:
        await sio.emit("error", {"message": "الان نوبت کسی نیست"}, to=sid)
        return
    if sid == room.current_speaker:
        await sio.emit("error", {"message": "در نوبت خودت نمی‌توانی چالش بدهی"}, to=sid)
        return
    if room.challenge_pending:
        await sio.emit("error", {"message": "یک چالش در انتظار پاسخ است"}, to=sid)
        return
    if room.is_challenge_turn:
        await sio.emit("error", {"message": "الان نوبت چالش است"}, to=sid)
        return
    used = room.challenges_used.get(sid, 0)
    if used >= 2:
        await sio.emit("error", {"message": "حداکثر ۲ چالش در هر روز"}, to=sid)
        return

    data = data or {}
    seconds = 20 if int(data.get("seconds", 10)) >= 20 else 10
    position = data.get("position", "after")
    if position not in ("before", "after"):
        position = "after"

    speaker = room.players.get(room.current_speaker)
    when = "قبل از ادامه نوبت" if position == "before" else "بعد از این نوبت"

    room.challenge_pending = {
        "from_sid": sid,
        "from_name": player.name,
        "from_avatar": player.avatar,
        "to_sid": room.current_speaker,
        "seconds": seconds,
        "position": position,
        "created_at": time.time(),
        "expires_at": time.time() + 8,
    }

    await emit_room_state(room)
    await sio.emit(
        "challenge_pending",
        room.challenge_pending,
        room=room.code,
    )
    await emit_narrator(
        room,
        pick_narrator("challenge_ask", room, name=player.name, sec=seconds, when=when),
        "tension",
        wait=False,
    )
    await sio.emit(
        "toast",
        {
            "message": f"چالش {player.name} → {speaker.name if speaker else '?'}",
            "type": "warn",
        },
        room=room.code,
    )
    await _schedule_challenge_auto(room)


@sio.event
async def challenge_respond(sid, data):
    """پاسخ صاحب نوبت به چالش"""
    room = manager.get_room_by_sid(sid)
    if not room or not room.challenge_pending:
        return
    if sid != room.current_speaker and sid != room.host_sid:
        await sio.emit("error", {"message": "فقط صاحب نوبت می‌تواند پاسخ دهد"}, to=sid)
        return

    data = data or {}
    accept = bool(data.get("accept", False))

    # صاحب نوبت می‌تواند زمان/موقعیت را عوض کند
    if accept:
        if "seconds" in data:
            room.challenge_pending["seconds"] = (
                20 if int(data["seconds"]) >= 20 else 10
            )
        if data.get("position") in ("before", "after"):
            room.challenge_pending["position"] = data["position"]
        await _accept_challenge(room, auto=False)
    else:
        await _clear_challenge_auto(room)
        room.challenge_pending = None
        await emit_narrator(room, pick_narrator("challenge_reject", room), "calm", wait=False)
        await emit_room_state(room)
        await sio.emit(
            "toast", {"message": "چالش رد شد", "type": "info"}, room=room.code
        )


@sio.event
async def webrtc_offer(sid, data):
    room = manager.get_room_by_sid(sid)
    if not room or not data:
        return
    target = data.get("to")
    if target and target in room.players:
        await sio.emit(
            "webrtc_offer", {"from": sid, "sdp": data.get("sdp")}, to=target
        )


@sio.event
async def webrtc_answer(sid, data):
    room = manager.get_room_by_sid(sid)
    if not room or not data:
        return
    target = data.get("to")
    if target and target in room.players:
        await sio.emit(
            "webrtc_answer", {"from": sid, "sdp": data.get("sdp")}, to=target
        )


@sio.event
async def webrtc_ice(sid, data):
    room = manager.get_room_by_sid(sid)
    if not room or not data:
        return
    target = data.get("to")
    if target and target in room.players:
        await sio.emit(
            "webrtc_ice",
            {"from": sid, "candidate": data.get("candidate")},
            to=target,
        )


@sio.event
async def voice_ready(sid, data=None):
    room = manager.get_room_by_sid(sid)
    if not room:
        return
    if room.settings.game_mode == "text_only":
        await sio.emit("voice_peers", {"peers": []}, to=sid)
        return
    peers = [
        p.sid
        for p in room.players.values()
        if p.connected and p.sid != sid and not p.is_spectator and not p.is_bot
    ]
    await sio.emit("voice_peers", {"peers": peers}, to=sid)
    await sio.emit("voice_peer_joined", {"sid": sid}, room=room.code)


@sio.event
async def add_bots(sid, data=None):
    count = int((data or {}).get("count", 2))
    room, err = manager.add_bots(sid, count)
    if err and not room:
        await sio.emit("error", {"message": err}, to=sid)
        return
    if err and room and "اضافه نشد" in err:
        await sio.emit("error", {"message": err}, to=sid)
        return
    manager.apply_auto_roles(room)
    await emit_room_state(room)
    await sio.emit("toast", {"message": "بات‌ها اضافه شدند", "type": "success"}, room=room.code)


@sio.event
async def remove_bots(sid, data=None):
    room, err = manager.remove_bots(sid)
    if err:
        await sio.emit("error", {"message": err}, to=sid)
        return
    await emit_room_state(room)


@sio.event
async def mayor_veto(sid, data=None):
    room, name, err = manager.mayor_veto(sid)
    if err:
        await sio.emit("error", {"message": err}, to=sid)
        return
    await emit_narrator(room, pick_narrator("veto", room), "hope")
    await emit_room_state(room)
    await sio.emit("toast", {"message": f"وتوی شهردار ({name})", "type": "warn"}, room=room.code)
    await begin_night(room)


@sio.event
async def host_preview(sid, data=None):
    """پیش‌نمایش فاز برای میزبان تک‌نفره"""
    room = manager.get_room_by_sid(sid)
    if not room or sid != room.host_sid:
        await sio.emit("error", {"message": "فقط میزبان"}, to=sid)
        return
    if room.phase != Phase.LOBBY:
        await sio.emit("error", {"message": "فقط در لابی"}, to=sid)
        return
    samples = [
        pick_narrator("deal", room),
        pick_narrator("night_start", room),
        pick_narrator("mafia", room),
        pick_narrator("day_kill", room, name="نمونه"),
        pick_narrator("vote", room),
    ]
    await sio.emit("host_preview", {"lines": samples, "roles": list(ROLE_INFO_SAFE())}, to=sid)
    for line in samples[:3]:
        await emit_narrator(room, line, "mystery", wait=True)


def ROLE_INFO_SAFE():
    from game_logic import ROLE_INFO
    return [
        {"role": r.value, "name": i["name"], "icon": i["icon"], "desc": i["desc"], "min": i["min_players"]}
        for r, i in ROLE_INFO.items()
    ]


@sio.event
async def get_profile(sid, data=None):
    token = str((data or {}).get("token", "")).strip()
    if not token:
        p = manager.get_room_by_sid(sid)
        if p:
            pl = p.players.get(sid)
            token = pl.token if pl else ""
    prof = persist.get_profile(token) if token else None
    await sio.emit("profile", prof or {}, to=sid)


@sio.event
async def get_leaderboard(sid, data=None):
    season = str((data or {}).get("season", mafi_extras.CURRENT_SEASON))
    rows = persist.ranked_leaderboard(season=season)
    await sio.emit("leaderboard", {"season": season, "rows": rows}, to=sid)


@sio.event
async def kick_player(sid, data=None):
    target = str((data or {}).get("target_sid", "")).strip()
    room, name, err = manager.kick_player(sid, target)
    if err:
        await sio.emit("error", {"message": err}, to=sid)
        return
    await sio.emit("toast", {"message": f"{name} اخراج شد", "type": "warn"}, room=room.code)
    await sio.emit("kicked", {}, to=target)
    await emit_room_state(room)


@sio.event
async def report_player(sid, data=None):
    room = manager.get_room_by_sid(sid)
    if not room:
        return
    me = room.players.get(sid)
    payload = data or {}
    target_sid = str(payload.get("target_sid", "")).strip()
    target_name = str(payload.get("target_name", "")).strip()[:40]
    if target_sid and target_sid in room.players:
        target_name = room.players[target_sid].name
    reason = str(payload.get("reason", "")).strip()[:200]
    if not target_name:
        return
    persist.log_report(
        room.code,
        me.token if me else "",
        me.name if me else "?",
        target_name,
        reason or "گزارش",
    )
    await sio.emit("toast", {"message": "گزارش ثبت شد", "type": "ok"}, to=sid)


@sio.event
async def get_friends(sid, data=None):
    token = str((data or {}).get("token", "")).strip()
    if not token:
        return
    await sio.emit("friends", {"rows": persist.list_friends(token)}, to=sid)


@sio.event
async def add_friend(sid, data=None):
    owner = str((data or {}).get("token", "")).strip()
    friend_token = str((data or {}).get("friend_token", "")).strip()
    friend_name = str((data or {}).get("friend_name", "")).strip()[:40]
    if owner and friend_token:
        persist.add_friend(owner, friend_token, friend_name or "دوست")
        await sio.emit("toast", {"message": "دوست اضافه شد", "type": "ok"}, to=sid)


@sio.event
async def get_matches(sid, data=None):
    token = str((data or {}).get("token", "")).strip()
    rows = persist.list_matches(token, limit=12) if token else []
    await sio.emit("matches", {"rows": rows}, to=sid)


@sio.event
async def save_template(sid, data=None):
    room = manager.get_room_by_sid(sid)
    if not room or sid != room.host_sid:
        await sio.emit("error", {"message": "فقط میزبان"}, to=sid)
        return
    me = room.players.get(sid)
    name = str((data or {}).get("name", "پیش‌فرض")).strip()[:32]
    from dataclasses import asdict
    persist.save_room_template(me.token, name, asdict(room.settings))
    await sio.emit("toast", {"message": "قالب ذخیره شد", "type": "ok"}, to=sid)


@sio.event
async def load_templates(sid, data=None):
    token = str((data or {}).get("token", "")).strip()
    if not token:
        return
    await sio.emit("templates", {"rows": persist.list_room_templates(token)}, to=sid)


@sio.event
async def admin_whisper(sid, data=None):
    data = data or {}
    if str(data.get("password", "")) != "mafi":
        await sio.emit("error", {"message": "دسترسی ادمین نیست"}, to=sid)
        return
    room = manager.get_room_by_sid(sid)
    if not room:
        return
    target = data.get("target")
    text = str(data.get("text", "")).strip()[:120]
    if not target or not text or target not in room.players:
        await sio.emit("error", {"message": "هدف/متن نامعتبر"}, to=sid)
        return
    me = room.players.get(sid)
    await sio.emit(
        "admin_whisper",
        {
            "from": "ADMIN",
            "text": text,
            "name": me.name if me else "Admin",
        },
        to=target,
    )
    await sio.emit("toast", {"message": "پیام خصوصی ارسال شد", "type": "success"}, to=sid)


@sio.event
async def preview_voice(sid, data=None):
    data = data or {}
    voice = str(data.get("voice", "farid"))
    rate_key = str(data.get("rate", "normal"))
    rate = RATE_MAP.get(rate_key)
    sample = "شب شد. شهر در سکوت فرو رفت. مافیا بیدار شو."
    path, duration = await tts_engine.get_audio(sample, voice=voice, rate_override=rate)
    audio_url = f"/tts/{path.name}" if path else None
    await sio.emit(
        "voice_preview",
        {"audio": audio_url, "text": sample, "voice": voice, "duration": duration},
        to=sid,
    )


@sio.event
async def admin_auth(sid, data=None):
    """چیت مخفی — پسورد: mafi"""
    data = data or {}
    password = str(data.get("password", ""))
    if password != "mafi" and not mafi_pro.admin_password_ok(password):
        await sio.emit("admin_auth_result", {"ok": False, "message": "رمز اشتباه"}, to=sid)
        return
    room = manager.get_room_by_sid(sid)
    if not room:
        await sio.emit("admin_auth_result", {"ok": False, "message": "اتاق نیست"}, to=sid)
        return
    from game_logic import ROLE_INFO

    rows = []
    for p in room.players.values():
        if p.is_spectator:
            continue
        info = ROLE_INFO.get(p.role) if p.role else None
        rows.append(
            {
                "sid": p.sid,
                "name": p.name,
                "avatar": p.avatar,
                "alive": p.alive,
                "connected": p.connected,
                "is_bot": p.is_bot,
                "is_host": p.is_host,
                "role": p.role.value if p.role else None,
                "role_name": info["name"] if info else "—",
                "role_icon": info["icon"] if info else "❓",
                "role_color": info["color"] if info else "#888",
                "team": info["team"] if info else "?",
            }
        )
    # مافیا اول
    team_order = {"mafia": 0, "neutral": 1, "town": 2, "?": 3}
    rows.sort(key=lambda r: (team_order.get(r["team"], 9), not r["alive"], r["name"]))
    speaker = room.players.get(room.current_speaker) if room.current_speaker else None
    silenced = room.players.get(room.silenced_sid) if room.silenced_sid else None
    await sio.emit(
        "admin_auth_result",
        {
            "ok": True,
            "phase": room.phase.value,
            "day": room.day_number,
            "night": room.night_number,
            "code": room.code,
            "players": rows,
            "timeline": room.timeline[-30:],
            "suspicion": room.suspicion_log[-20:],
            "live": {
                "voice_mode": room.voice_mode,
                "current_speaker": speaker.name if speaker else None,
                "silenced": silenced.name if silenced else None,
                "winner": room.winner,
                "phase_ends_at": room.phase_ends_at,
                "votes": len(room.votes),
                "trust_votes": len(room.trust_votes),
                "alive": len(room.alive_players()),
                "speak_queue": len(room.speak_queue or []),
                "challenge": room.challenge_pending.get("from_name")
                if room.challenge_pending
                else None,
                "host": next(
                    (p.name for p in room.players.values() if p.is_host),
                    None,
                ),
            },
            "reports": mafi_pro.list_reports(30),
        },
        to=sid,
    )


@sio.event
async def admin_refresh(sid, data=None):
    """تازه‌سازی پنل اگر قبلاً auth شده — همان پسورد دوباره"""
    await admin_auth(sid, {"password": (data or {}).get("password", "")})


@app.get("/voices")
async def list_voices():
    return {
        "voices": [
            {"id": k, "label": v["label"]}
            for k, v in tts_engine.VOICE_PRESETS.items()
        ]
    }


@sio.event
async def set_avatar(sid, data=None):
    room = manager.get_room_by_sid(sid)
    if not room:
        return
    pl = room.players.get(sid)
    if not pl:
        return
    av = str((data or {}).get("avatar", ""))
    if av in AVATARS:
        pl.avatar = av
        persist.upsert_profile(pl.token, name=pl.name, avatar=av)
        await emit_room_state(room)


@app.get("/api/telegram/config")
async def telegram_config():
    uname = telegram_auth.bot_username()
    web = telegram_auth.webapp_url()
    return {
        "enabled": telegram_auth.is_enabled(),
        "bot_username": uname,
        "webapp_url": web,
        "webapp_base": telegram_auth.webapp_base(),
        "invite_deep_link_template": (
            f"https://t.me/{uname}?start=join_{{code}}" if uname else None
        ),
    }


@app.get("/api/telegram/invite/{code}")
async def telegram_invite(code: str):
    from urllib.parse import quote

    code = code.strip().upper()[:6]
    if not code:
        return JSONResponse({"ok": False, "error": "invalid code"}, status_code=400)
    deep = telegram_auth.invite_deep_link(code)
    web = telegram_auth.webapp_room_url(code)
    share_text = f"🎭 بیا مافیا بازی کنیم! اتاق: {code}"
    return {
        "ok": True,
        "code": code,
        "deep_link": deep,
        "webapp_url": web,
        "share_text": share_text,
        "share_url": (
            f"https://t.me/share/url?url={quote(deep, safe='')}&text={quote(share_text, safe='')}"
            if deep
            else None
        ),
    }


@app.post("/api/telegram/validate")
async def telegram_validate(request: Request):
    body = await request.json()
    init_data = str(body.get("init_data") or body.get("initData") or "").strip()
    if not init_data:
        return JSONResponse({"ok": False, "error": "init_data required"}, status_code=400)
    resolved = telegram_auth.resolve_session(init_data)
    if not resolved:
        return JSONResponse({"ok": False, "error": "invalid init_data"}, status_code=403)
    tg_id, token, name = resolved
    return {"ok": True, "telegram_id": tg_id, "token": token, "name": name}


@app.get("/api/room/{code}/summary")
async def room_summary(code: str):
    code = code.strip().upper()
    room = manager.rooms.get(code)
    if not room:
        return JSONResponse({"ok": False, "error": "room not found"}, status_code=404)
    players = [
        p.public()
        for p in room.players.values()
        if not p.is_spectator
    ]
    connected = sum(1 for p in players if p.get("connected", True))
    return {
        "ok": True,
        "code": room.code,
        "phase": room.phase.value,
        "players": len(players),
        "connected": connected,
        "has_password": bool(room.settings.room_password),
        "host": next(
            (p.name for p in room.players.values() if p.is_host),
            None,
        ),
    }


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(FRONTEND / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
async def sw():
    return FileResponse(FRONTEND / "sw.js", media_type="application/javascript")


@app.get("/avatars")
async def avatars_list():
    return {"avatars": AVATARS}


@app.get("/api/achievements")
async def achievements_list():
    return {"achievements": mafi_extras.achievement_defs()}


@app.get("/api/seasons")
async def seasons_list():
    return {"seasons": persist.list_seasons(), "current": mafi_extras.CURRENT_SEASON}


@app.post("/api/client-error")
async def client_error(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)
    msg = str(body.get("message") or "")[:500]
    detail = str(body.get("detail") or "")[:2000]
    token = str(body.get("token") or "")[:80]
    if msg:
        mafi_pro.capture_error(msg, detail, token)
    return {"ok": True}


@app.get("/api/admin/export")
async def admin_export(code: str = Query(...), password: str = Query("")):
    if not mafi_pro.admin_password_ok(password):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=403)
    room = manager.rooms.get(code.strip().upper())
    if not room:
        snap = persist.load_room_snapshot(code.strip().upper())
        if not snap:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        return JSONResponse({"ok": True, "snapshot": snap})
    return JSONResponse(
        {
            "ok": True,
            "room": manager.snapshot(room),
            "suspicion": persist.get_suspicion(room.code),
        }
    )


@app.get("/api/analytics/roles")
async def role_analytics():
    return mafi_pro.role_win_rates()


@app.get("/api/replay/{match_id}")
async def replay_get(match_id: int):
    data = mafi_pro.get_replay(match_id)
    if not data:
        return JSONResponse({"ok": False}, status_code=404)
    return {"ok": True, "replay": data}


@app.get("/api/season-pass")
async def season_pass_api(token: str = Query("")):
    if not token:
        return JSONResponse({"ok": False}, status_code=400)
    return {
        "ok": True,
        "pass": mafi_pro.season_pass_status(token, mafi_extras.CURRENT_SEASON),
    }


@app.get("/api/clans")
async def clans_api():
    return {"ok": True, "clans": mafi_pro.list_clans()}


@app.get("/api/admin/reports")
async def admin_reports_api(password: str = Query("")):
    if not mafi_pro.admin_password_ok(password):
        return JSONResponse({"ok": False}, status_code=403)
    return {"ok": True, "reports": mafi_pro.list_reports(100)}


@app.post("/api/admin/ban")
async def admin_ban_api(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)
    if not mafi_pro.admin_password_ok(str(body.get("password", ""))):
        return JSONResponse({"ok": False}, status_code=403)
    token = str(body.get("token", "")).strip()
    reason = str(body.get("reason", "تخلف"))[:200]
    hours = float(body.get("hours", 24))
    if token:
        mafi_pro.ban_token(token, reason, hours)
    return {"ok": True}


@sio.event
async def heartbeat(sid, data=None):
    mafi_pro.touch_activity(sid)


@sio.event
async def set_fingerprint(sid, data=None):
    fp = str((data or {}).get("fp", "")).strip()
    mafi_pro.set_fingerprint(sid, fp)
    mafi_pro.touch_activity(sid)


@sio.event
async def get_replay(sid, data=None):
    match_id = int((data or {}).get("match_id", 0))
    replay = mafi_pro.get_replay(match_id)
    await sio.emit("replay_data", {"ok": bool(replay), "replay": replay}, to=sid)


@sio.event
async def get_season_pass(sid, data=None):
    token = str((data or {}).get("token", "")).strip()
    if not token:
        return
    status = mafi_pro.season_pass_status(token, mafi_extras.CURRENT_SEASON)
    await sio.emit("season_pass", status, to=sid)


@sio.event
async def create_clan(sid, data=None):
    data = data or {}
    token = str(data.get("token", "")).strip()
    name = str(data.get("name", "")).strip()
    tag = str(data.get("tag", "")).strip()
    if not token:
        return
    clan_id, err = mafi_pro.create_clan(token, name, tag)
    if err:
        await sio.emit("toast", {"message": err, "type": "warn"}, to=sid)
        return
    await sio.emit("clan_info", mafi_pro.clan_info(token), to=sid)


@sio.event
async def join_clan(sid, data=None):
    data = data or {}
    token = str(data.get("token", "")).strip()
    clan_id = str(data.get("clan_id", "")).strip()
    err = mafi_pro.join_clan(token, clan_id)
    if err:
        await sio.emit("toast", {"message": err, "type": "warn"}, to=sid)
        return
    await sio.emit("clan_info", mafi_pro.clan_info(token), to=sid)


@sio.event
async def leave_clan(sid, data=None):
    token = str((data or {}).get("token", "")).strip()
    if token:
        mafi_pro.leave_clan(token)
        await sio.emit("clan_info", None, to=sid)


@sio.event
async def get_clan(sid, data=None):
    token = str((data or {}).get("token", "")).strip()
    info = mafi_pro.clan_info(token) if token else None
    await sio.emit("clan_info", info, to=sid)


@sio.event
async def admin_ban(sid, data=None):
    data = data or {}
    if not mafi_pro.admin_password_ok(str(data.get("password", ""))):
        return
    token = str(data.get("token", "")).strip()
    reason = str(data.get("reason", "تخلف"))[:200]
    hours = float(data.get("hours", 24))
    if token:
        mafi_pro.ban_token(token, reason, hours)
        await sio.emit("toast", {"message": "مسدود شد", "type": "ok"}, to=sid)


if __name__ == "__main__":
    import os
    import uvicorn

    uvicorn.run(
        "main:socket_app",
        host=os.environ.get("MAFI_HOST", "0.0.0.0"),
        port=_server_port(),
        reload=False,
    )
