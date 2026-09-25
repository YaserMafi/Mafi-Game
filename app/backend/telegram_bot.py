"""Telegram bot — invites, Mini App launcher, smart narrator companion."""
from __future__ import annotations

import asyncio
import re
from typing import Optional

import telegram_auth
import telegram_notify

_dp: Optional[object] = None
_task: Optional[asyncio.Task] = None


def _webapp_url(room: str = "", action: str = "") -> str:
    return telegram_auth.webapp_room_url(room, action)


def _mini_app_kb(url: str, label: str = "🎭 باز کردن بازی"):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]]
    )


def _parse_room(text: str) -> Optional[str]:
    m = re.search(r"[A-Z0-9]{4,6}", (text or "").upper())
    return m.group(0)[:6] if m else None


async def _cmd_start(message, bot):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    args = (message.text or "").split(maxsplit=1)
    payload = args[1].strip() if len(args) > 1 else ""
    room = None
    if payload.lower().startswith("join_"):
        room = _parse_room(payload[5:])
    elif payload.lower().startswith("room_"):
        room = _parse_room(payload[5:])
    else:
        room = _parse_room(payload)

    uname = telegram_auth.bot_username()
    intro = (
        "🎭 **MAFI — مافیا ابری**\n\n"
        "بازی گروهی فارسی با گرداننده هوشمند، دعوت QR، و Mini App.\n"
        "لپ‌تاپ لازم نیست — سرور همیشه آنلاین است.\n\n"
    )
    if uname:
        intro += f"بات: @{uname}\n\n"

    if room:
        url = _webapp_url(room)
        await message.answer(
            f"{intro}دعوت به اتاق `{room}`\nروی دکمه بزنید و نام یکتا وارد کنید.",
            reply_markup=_mini_app_kb(url, f"ورود به اتاق {room}"),
            parse_mode="Markdown",
        )
        return

    rows = [
        [InlineKeyboardButton(text="➕ ساخت اتاق", web_app=WebAppInfo(url=_webapp_url(action="create")))],
        [InlineKeyboardButton(text="🎮 ورود به بازی", web_app=WebAppInfo(url=_webapp_url()))],
    ]
    await message.answer(
        intro + "یک گزینه را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="Markdown",
    )


async def _cmd_create(message):
    url = _webapp_url(action="create")
    await message.answer(
        "➕ **ساخت اتاق جدید**\nMini App را باز کنید، نام بزنید و «ساخت اتاق» را بزنید.",
        reply_markup=_mini_app_kb(url, "ساخت اتاق"),
        parse_mode="Markdown",
    )


async def _cmd_join(message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("فرمت: `/join ABCDE`", parse_mode="Markdown")
        return
    room = _parse_room(parts[1])
    if not room:
        await message.answer("کد اتاق نامعتبر است.")
        return
    url = _webapp_url(room)
    await message.answer(
        f"ورود به اتاق `{room}`:",
        reply_markup=_mini_app_kb(url, f"ورود {room}"),
        parse_mode="Markdown",
    )


async def _cmd_help(message):
    await message.answer(
        "🎭 **راهنمای MAFI Bot**\n\n"
        "/start — منوی اصلی\n"
        "/create — ساخت اتاق (Mini App)\n"
        "/join CODE — ورود با کد\n"
        "/help — این پیام\n\n"
        "گرداننده هوشمند: صدای فارسی + اعلان فازها در تلگرام.\n"
        "برای بازی کامل Mini App را باز کنید (HTTPS لازم است).",
        parse_mode="Markdown",
    )


def build_dispatcher(bot):
    from aiogram import Dispatcher, Router
    from aiogram.filters import Command, CommandStart

    router = Router()

    @router.message(CommandStart())
    async def start_handler(message):
        await _cmd_start(message, bot)

    @router.message(Command("create"))
    async def create_handler(message):
        await _cmd_create(message)

    @router.message(Command("join"))
    async def join_handler(message):
        await _cmd_join(message)

    @router.message(Command("help"))
    async def help_handler(message):
        await _cmd_help(message)

    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def setup_bot_ui(bot) -> None:
    """Register commands + menu button (Mini App launcher)."""
    from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="منوی اصلی — ساخت یا ورود"),
            BotCommand(command="create", description="ساخت اتاق جدید"),
            BotCommand(command="join", description="ورود — مثال: /join ABCDE"),
            BotCommand(command="help", description="راهنمای بازی"),
        ]
    )
    web = telegram_auth.webapp_url()
    if web and web.startswith("https://"):
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="🎭 بازی مافیا",
                    web_app=WebAppInfo(url=_webapp_url()),
                )
            )
            print("[telegram] menu button → Mini App")
        except Exception as e:
            print("[telegram] menu button setup failed:", e)


async def run_bot() -> None:
    token = telegram_auth.bot_token()
    if not token:
        print("[telegram] TELEGRAM_BOT_TOKEN not set — bot disabled")
        return

    from aiogram import Bot

    bot = Bot(token=token)
    telegram_notify.set_bot(bot)
    dp = build_dispatcher(bot)
    global _dp
    _dp = dp

    web = telegram_auth.webapp_url()
    if not web or web.startswith("http://127.0.0.1") or web.startswith("http://localhost"):
        print("[telegram] WARNING: MAFI_WEBAPP_URL should be public HTTPS for Mini App")
    else:
        await setup_bot_ui(bot)

    print("[telegram] bot polling started")
    await dp.start_polling(bot, allowed_updates=["message"])


def start_background() -> Optional[asyncio.Task]:
    global _task
    if not telegram_auth.is_enabled():
        return None
    if _task and not _task.done():
        return _task
    _task = asyncio.create_task(run_bot())
    return _task


async def stop_bot() -> None:
    global _task, _dp
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    _dp = None
