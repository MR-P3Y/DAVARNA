from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from bot.services.admin_acl import (
    get_admin_roles,
    is_admin_user,
    is_finance_admin_user,
    is_game_admin_user,
    is_super_admin_user,
    is_user_admin_user,
)

class UserContextMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        u = data.get("event_from_user")
        if u:
            callback_data = str(getattr(event, "data", "") or "")
            is_super = is_super_admin_user(u.id)
            is_game = is_game_admin_user(u.id)
            is_finance = is_finance_admin_user(u.id)
            is_user_admin = is_user_admin_user(u.id)
            is_admin = is_admin_user(u.id)
            if callback_data.startswith(("admin:finance", "admin:deposits", "admin:withdraw", "admin:crypto")):
                is_admin = bool(is_finance)
            elif callback_data.startswith("admin:ops"):
                is_admin = bool(is_super or is_game or is_finance or is_user_admin)
            elif callback_data.startswith("admin:games"):
                is_admin = bool(is_game)
            elif callback_data.startswith("admin:users"):
                is_admin = bool(is_user_admin)
            data["tg_user_id"] = u.id
            data["tg_username"] = u.username
            data["is_super_admin"] = is_super
            data["is_admin"] = is_admin
            data["admin_roles"] = sorted(get_admin_roles(u.id))
            data["is_game_admin"] = is_game
            data["is_finance_admin"] = is_finance
            data["is_user_admin"] = is_user_admin
        return await handler(event, data)
