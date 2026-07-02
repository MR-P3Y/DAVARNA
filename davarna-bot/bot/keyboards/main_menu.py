from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb(
    is_admin: bool = False,
    is_super_admin: bool = False,
    is_game_admin: bool = False,
    is_finance_admin: bool = False,
    is_user_admin: bool = False,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 خرید کارت", callback_data="menu:buy")
    kb.button(text="🎮 بازی‌های فعال", callback_data="menu:games")
    kb.button(text="🃏 کارت‌های من", callback_data="menu:mycards")

    kb.button(text="💰 کیف پول", callback_data="menu:wallet")

    kb.button(text="ℹ️ راهنما", callback_data="menu:help")

    can_finance = bool(is_super_admin or is_finance_admin or is_user_admin or (is_admin and not (is_game_admin or is_finance_admin or is_user_admin)))
    can_games = bool(is_super_admin or is_game_admin or is_user_admin or (is_admin and not (is_game_admin or is_finance_admin or is_user_admin)))
    can_users = bool(is_super_admin or is_user_admin or (is_admin and not (is_game_admin or is_finance_admin)))

    if can_finance:
        kb.button(text="🛠 ادمین مالی", callback_data="admin:finance")
    if can_games:
        kb.button(text="🛠 ادمین بازی", callback_data="admin:games")
    if can_users:
        kb.button(text="🧑‍💼 ادمین کاربران", callback_data="admin:users")
    if can_games:
        kb.button(text="🏆 کارت‌های برنده", callback_data="admin:games:winners:archive:0")
    if can_finance or can_games or can_users or is_super_admin:
        kb.button(text="📡 داشبورد عملیات", callback_data="admin:ops:dashboard")
    if is_super_admin:
        kb.button(text="👑 سوپرادمین", callback_data="super:admin:panel")

    if can_finance or can_games or can_users or is_super_admin:
        if is_super_admin:
            kb.adjust(1, 2, 1, 1, 2, 2, 1, 1, 1)
        else:
            kb.adjust(1, 2, 1, 1, 2, 2, 1, 1)
    else:
        kb.adjust(1, 2, 1, 1)

    return kb.as_markup()
