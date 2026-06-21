from __future__ import annotations

import asyncio
import time

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject


REDIRECT_COOLDOWN_SEC = 45.0
REDIRECT_DELETE_AFTER_SEC = 18.0


def _deep_link(username: str | None) -> str | None:
    clean = str(username or "").strip().lstrip("@")
    if not clean:
        return None
    return f"https://t.me/{clean}"


def _extract_chat_id(event: TelegramObject, data: dict) -> int | None:
    chat = data.get("event_chat")
    if chat is not None:
        try:
            return int(chat.id)
        except Exception:
            pass

    direct_chat = getattr(event, "chat", None)
    if direct_chat is not None:
        try:
            return int(direct_chat.id)
        except Exception:
            pass

    message = getattr(event, "message", None)
    if message is not None and getattr(message, "chat", None) is not None:
        try:
            return int(message.chat.id)
        except Exception:
            pass

    for attr in ("edited_message", "channel_post", "edited_channel_post"):
        msg = getattr(event, attr, None)
        if msg is None or getattr(msg, "chat", None) is None:
            continue
        try:
            return int(msg.chat.id)
        except Exception:
            continue

    callback_query = getattr(event, "callback_query", None)
    if callback_query is not None:
        cb_message = getattr(callback_query, "message", None)
        if cb_message is not None and getattr(cb_message, "chat", None) is not None:
            try:
                return int(cb_message.chat.id)
            except Exception:
                pass

    return None


class UserForumIsolationMiddleware(BaseMiddleware):
    """
    Keeps the public user forum broadcast-first.

    Normal user chat stays untouched, but attempts to use the bot inside the
    public group are redirected to private chat so wallet/cards/receipts never
    leak into forum topics.
    """

    def __init__(self, isolated_chat_id: int | None):
        self._isolated_chat_id = int(isolated_chat_id) if isolated_chat_id is not None else None
        self._last_redirect_by_user: dict[int, float] = {}
        self._bot_username: str | None = None

    async def _bot_link(self, bot) -> str | None:
        if self._bot_username:
            return _deep_link(self._bot_username)
        try:
            me = await bot.get_me()
            self._bot_username = getattr(me, "username", None)
        except Exception:
            return None
        return _deep_link(self._bot_username)

    def _should_prompt_user(self, message: Message, bot_id: int | None) -> bool:
        text = str(message.text or message.caption or "").strip()
        if text.startswith("/"):
            return True

        username = str(self._bot_username or "").strip().lstrip("@").lower()
        if username and f"@{username}" in text.lower():
            return True

        reply = getattr(message, "reply_to_message", None)
        reply_from = getattr(reply, "from_user", None)
        if bot_id is not None and reply_from is not None:
            try:
                if int(reply_from.id) == int(bot_id):
                    return True
            except Exception:
                pass

        return False

    def _can_redirect_now(self, user_id: int | None) -> bool:
        if user_id is None:
            return True
        now = time.monotonic()
        prev = float(self._last_redirect_by_user.get(int(user_id), 0.0))
        if now - prev < REDIRECT_COOLDOWN_SEC:
            return False
        self._last_redirect_by_user[int(user_id)] = now
        return True

    async def _delete_later(self, message: Message, delay_sec: float) -> None:
        await asyncio.sleep(max(1.0, float(delay_sec)))
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError):
            return
        except Exception:
            return

    async def _delete_message_quietly(self, message: Message) -> None:
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError):
            return
        except Exception:
            return

    async def _send_redirect(self, message: Message, bot) -> None:
        user_id = None
        if message.from_user is not None:
            try:
                user_id = int(message.from_user.id)
            except Exception:
                user_id = None

        if not self._can_redirect_now(user_id):
            return

        link = await self._bot_link(bot)
        markup = None
        if link:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="ورود به پی وی ربات", url=link)]]
            )

        text = (
            "برای حفظ حریم خصوصی، خرید کارت، کیف پول، کارت‌های من و رسیدها فقط در پی‌وی ربات انجام می‌شود.\n\n"
            "از دکمه زیر وارد ربات شو."
        )

        try:
            sent = await message.answer(text, reply_markup=markup, parse_mode="HTML", disable_notification=True)
        except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError):
            return
        except Exception:
            return

        if sent is not None:
            asyncio.create_task(self._delete_later(sent, REDIRECT_DELETE_AFTER_SEC))

    async def _handle_message(self, message: Message, data: dict) -> None:
        bot = data.get("bot")
        bot_id = None
        if bot is not None:
            try:
                me = await bot.get_me()
                bot_id = int(me.id)
                self._bot_username = getattr(me, "username", None) or self._bot_username
            except Exception:
                pass

        if self._should_prompt_user(message, bot_id):
            await self._send_redirect(message, bot)
            await self._delete_message_quietly(message)

    async def _handle_callback(self, callback_query: CallbackQuery) -> None:
        try:
            await callback_query.answer(
                "برای حفظ حریم خصوصی، این بخش فقط در پی‌وی ربات قابل استفاده است.",
                show_alert=True,
            )
        except Exception:
            return

    async def __call__(self, handler, event: TelegramObject, data: dict):
        if self._isolated_chat_id is None:
            return await handler(event, data)

        chat_id = _extract_chat_id(event, data)
        if chat_id is not None and int(chat_id) == self._isolated_chat_id:
            message = getattr(event, "message", None)
            if isinstance(message, Message):
                await self._handle_message(message, data)
                return None

            callback_query = getattr(event, "callback_query", None)
            if isinstance(callback_query, CallbackQuery):
                await self._handle_callback(callback_query)
                return None

            return None

        return await handler(event, data)
