"""گویندگی فارسی AI — Farid Neural (بهترین صدای مردانه فارسی رایگان)"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path

def _tts_cache_dir() -> Path:
    data = os.environ.get("MAFI_DATA_DIR", "").strip()
    base = Path(data) if data else Path(__file__).resolve().parent
    path = base / "tts_cache"
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        fallback = Path(os.environ.get("TMPDIR") or os.environ.get("TMP") or ".") / "mafi_tts"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


CACHE_DIR = _tts_cache_dir()

# پروفایل‌های گوینده فارسی (Edge Neural)
VOICE_PRESETS = {
    "farid": {
        "id": "fa-IR-FaridNeural",
        "label": "فرید — مردانه واضح",
        "rate": "-6%",
        "pitch": "-1Hz",
        "volume": "+5%",
    },
    "farid_deep": {
        "id": "fa-IR-FaridNeural",
        "label": "فرید — بم و سنگین",
        "rate": "-10%",
        "pitch": "-4Hz",
        "volume": "+8%",
    },
    "farid_cinema": {
        "id": "fa-IR-FaridNeural",
        "label": "فرید — سینمایی دراماتیک",
        "rate": "-8%",
        "pitch": "-3Hz",
        "volume": "+10%",
    },
    "dilara": {
        "id": "fa-IR-DilaraNeural",
        "label": "دلارا — زنانه واضح",
        "rate": "-5%",
        "pitch": "+0Hz",
        "volume": "+5%",
    },
    "dilara_soft": {
        "id": "fa-IR-DilaraNeural",
        "label": "دلارا — نرم و آرام",
        "rate": "-9%",
        "pitch": "-2Hz",
        "volume": "+3%",
    },
}

DEFAULT_PRESET = "farid"
VOICE_VER = "v8-multi-voice"


def apply_preset(name: str | None = None) -> dict:
    global VOICE, RATE, PITCH, VOLUME
    preset = VOICE_PRESETS.get(name or DEFAULT_PRESET, VOICE_PRESETS[DEFAULT_PRESET])
    VOICE = preset["id"]
    RATE = preset["rate"]
    PITCH = preset["pitch"]
    VOLUME = preset["volume"]
    return preset


# مقادیر پیش‌فرض
_p0 = apply_preset(DEFAULT_PRESET)
VOICE = _p0["id"]
RATE = _p0["rate"]
PITCH = _p0["pitch"]
VOLUME = _p0["volume"]

# اعداد فارسی / عربی → واژه‌های قابل تلفظ
_DIGIT_FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NUM_WORDS = {
    0: "صفر",
    1: "یک",
    2: "دو",
    3: "سه",
    4: "چهار",
    5: "پنج",
    6: "شش",
    7: "هفت",
    8: "هشت",
    9: "نه",
    10: "ده",
    11: "یازده",
    12: "دوازده",
    13: "سیزده",
    14: "چهارده",
    15: "پانزده",
    16: "شانزده",
    17: "هفده",
    18: "هجده",
    19: "نوزده",
    20: "بیست",
    30: "سی",
    40: "چهل",
    50: "پنجاه",
    60: "شصت",
    70: "هفتاد",
    80: "هشتاد",
    90: "نود",
    100: "صد",
}

# نرمال‌سازی رایج برای تلفظ بهتر در بازی مافیا
_PRONOUNCE = (
    (r"گادفادر", "پدرخوانده"),
    (r"گاد‌?فادر", "پدرخوانده"),
    (r"\bGodfather\b", "پدرخوانده"),
    (r"بادیگارد", "بادی‌گارد"),
    (r"سایلنسر", "سای‌لنسر"),
    (r"اسنایپر", "اِسنایپر"),
    (r"\bmafia\b", "مافیا"),
    (r"\bAI\b", "ای آی"),
    (r"\bVIP\b", "وی آی پی"),
    (r"\bOK\b", "اوکی"),
)


def _key(text: str, engine: str) -> str:
    raw = f"{VOICE_VER}|{engine}|{VOICE}|{RATE}|{PITCH}|{VOLUME}|{text.strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _num_to_fa(n: int) -> str:
    if n in _NUM_WORDS:
        return _NUM_WORDS[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        if ones == 0:
            return _NUM_WORDS[tens * 10]
        return f"{_NUM_WORDS[tens * 10]} و {_NUM_WORDS[ones]}"
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        head = "صد" if hundreds == 1 else f"{_NUM_WORDS[hundreds]}‌صد"
        if rest == 0:
            return head
        return f"{head} و {_num_to_fa(rest)}"
    return str(n)


def _expand_numbers(text: str) -> str:
    def repl(m: re.Match) -> str:
        try:
            n = int(m.group(0))
            if 0 <= n <= 999:
                return _num_to_fa(n)
        except ValueError:
            pass
        return m.group(0)

    return re.sub(r"\d{1,3}", repl, text)


def clean_text(text: str) -> str:
    t = (text or "").strip()
    # ی و ک عربی → فارسی
    t = t.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    t = t.translate(_DIGIT_FA)
    t = re.sub(r"[\u200c\u200f\u200e]+", "\u200c", t)
    t = re.sub(r"\s+", " ", t)
    for pat, rep in _PRONOUNCE:
        t = re.sub(pat, rep, t, flags=re.IGNORECASE)
    t = _expand_numbers(t)
    t = t.replace("...", "…").replace("..", "…")
    t = re.sub(r"\s*،\s*", "، ", t)
    t = re.sub(r"\s*\.\s*", ". ", t)
    t = re.sub(r"\s*!\s*", "! ", t)
    t = re.sub(r"\s*\?\s*", "؟ ", t)
    t = re.sub(r"\s*؟\s*", "؟ ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t[:480]


def estimate_duration(text: str) -> float:
    n = len(clean_text(text))
    # با rate=-6% حدوداً کمی آهسته‌تر از حالت عادی
    return max(2.8, min(28.0, 1.4 + n * 0.085))


def _meta_path(audio: Path) -> Path:
    return audio.with_suffix(".json")


def _save_meta(audio: Path, duration: float, engine: str) -> None:
    try:
        _meta_path(audio).write_text(
            json.dumps({"duration": duration, "engine": engine, "voice": VOICE}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _load_duration(audio: Path) -> float | None:
    meta = _meta_path(audio)
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        d = float(data.get("duration") or 0)
        return d if d > 0.5 else None
    except Exception:
        return None


def get_duration(path: Path | None, text: str = "") -> float:
    if path:
        d = _load_duration(path)
        if d:
            return d + 0.35
        # تقریبی از حجم mp3 (~48kbps edge)
        try:
            size = path.stat().st_size
            if size > 400:
                return max(2.5, min(28.0, size / 6000 + 0.4))
        except Exception:
            pass
    return estimate_duration(text)


_locks: dict[str, asyncio.Lock] = {}


async def _edge(text: str, out: Path) -> tuple[bool, float]:
    """Synthesize with Farid Neural — plain text + prosody params (not double SSML)."""
    try:
        import edge_tts

        tmp = out.with_suffix(".tmp.mp3")
        if tmp.exists():
            tmp.unlink(missing_ok=True)

        communicate = edge_tts.Communicate(
            text, VOICE, rate=RATE, pitch=PITCH, volume=VOLUME
        )
        duration = 0.0
        with open(tmp, "wb") as f:
            async for chunk in communicate.stream():
                kind = chunk.get("type")
                if kind == "audio":
                    f.write(chunk["data"])
                elif kind in ("WordBoundary", "SentenceBoundary"):
                    # offset/duration are in 100-nanosecond units
                    off = float(chunk.get("offset") or 0) / 10_000_000
                    dur = float(chunk.get("duration") or 0) / 10_000_000
                    duration = max(duration, off + dur)

        if tmp.exists() and tmp.stat().st_size > 400:
            tmp.replace(out)
            if duration < 0.5:
                duration = get_duration(out, text)
            _save_meta(out, duration, "edge")
            return True, duration
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    except Exception as e:
        print(f"[TTS] edge failed: {e}")
    return False, 0.0


def _gtts(text: str, out: Path) -> tuple[bool, float]:
    try:
        from gtts import gTTS

        tmp = out.with_suffix(".tmp.mp3")
        gTTS(text=text, lang="fa", slow=False, tld="com").save(str(tmp))
        if tmp.exists() and tmp.stat().st_size > 200:
            tmp.replace(out)
            duration = get_duration(out, text)
            _save_meta(out, duration, "gtts")
            return True, duration
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    except Exception as e:
        print(f"[TTS] gtts failed: {e}")
    return False, 0.0


# Offline narrator phrases (bundled fallback when network TTS unavailable)
OFFLINE_PHRASES = {
    "night_start": "شب شد. همه چشم‌ها بسته.",
    "day_start": "روز شد. بحث آغاز شد.",
    "vote": "رأی‌گیری آغاز شد.",
    "town_win": "شهروندان برنده شدند.",
    "mafia_win": "مافیا برنده شد.",
}


async def synthesize(text: str) -> tuple[Path | None, float]:
    text = clean_text(text)
    if not text:
        return None, 0.0

    for key, phrase in OFFLINE_PHRASES.items():
        if phrase in text or text in phrase:
            bundled = Path(__file__).resolve().parent.parent / "frontend" / "assets" / "tts_offline" / f"{key}.mp3"
            if bundled.exists():
                return bundled, get_duration(bundled, text)

    engines = ("gtts",) if os.environ.get("MAFI_ANDROID") else ("edge", "gtts")
    for engine in engines:
        path = CACHE_DIR / f"{_key(text, engine)}.mp3"
        if path.exists() and path.stat().st_size > 200:
            return path, get_duration(path, text)

    edge_path = CACHE_DIR / f"{_key(text, 'edge')}.mp3"
    ok, dur = await _edge(text, edge_path)
    if ok:
        return edge_path, dur or get_duration(edge_path, text)

    gtts_path = CACHE_DIR / f"{_key(text, 'gtts')}.mp3"
    ok, dur = await asyncio.to_thread(_gtts, text, gtts_path)
    if ok:
        return gtts_path, dur or get_duration(gtts_path, text)
    return None, 0.0


async def get_audio(text: str, voice: str | None = None, rate_override: str | None = None) -> tuple[Path | None, float]:
    global VOICE, RATE, PITCH, VOLUME
    text = clean_text(text)
    if not text:
        return None, 0.0
    old = (VOICE, RATE, PITCH, VOLUME)
    try:
        apply_preset(voice or DEFAULT_PRESET)
        if rate_override:
            RATE = rate_override
        key = _key(text, "any")
        lock = _locks.setdefault(key, asyncio.Lock())
        async with lock:
            return await synthesize(text)
    finally:
        VOICE, RATE, PITCH, VOLUME = old


async def get_audio_path(text: str) -> Path | None:
    path, _ = await get_audio(text)
    return path
