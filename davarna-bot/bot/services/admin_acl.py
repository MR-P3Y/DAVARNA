from __future__ import annotations

import json
from pathlib import Path

from bot.config import settings

_STORE_PATH = Path("storage/admin_acl.json")
ADMIN_ROLE_NAMES = {"ADMIN", "SUPER_ADMIN", "GAME_OPERATOR", "FINANCE_ADMIN"}


def _normalize_roles(raw: object) -> set[str]:
    if isinstance(raw, str):
        raw_values = [raw]
    elif isinstance(raw, (list, tuple, set)):
        raw_values = list(raw)
    else:
        raw_values = []
    roles = {str(x or "").strip().upper() for x in raw_values if str(x or "").strip()}
    roles = {x for x in roles if x in ADMIN_ROLE_NAMES}
    if "SUPER_ADMIN" in roles:
        roles.add("ADMIN")
    return roles


def _load_acl() -> tuple[set[int], set[int], dict[int, str], dict[int, set[str]]]:
    if not _STORE_PATH.exists():
        return set(), set(), {}, {}
    try:
        data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return set(), set(), {}, {}
        raw_dynamic = data.get("dynamic_admin_ids", [])
        raw_blocked = data.get("blocked_admin_ids", [])
        raw_labels = data.get("admin_labels", {})
        raw_roles = data.get("admin_roles", {})
        if not isinstance(raw_dynamic, list):
            raw_dynamic = []
        if not isinstance(raw_blocked, list):
            raw_blocked = []
        if not isinstance(raw_labels, dict):
            raw_labels = {}
        if not isinstance(raw_roles, dict):
            raw_roles = {}
        dynamic = {int(x) for x in raw_dynamic if str(x).isdigit()}
        blocked = {int(x) for x in raw_blocked if str(x).isdigit()}
        labels: dict[int, str] = {}
        for k, v in raw_labels.items():
            if not str(k).isdigit():
                continue
            val = str(v or "").strip()
            if not val:
                continue
            labels[int(k)] = val
        role_map: dict[int, set[str]] = {}
        for k, v in raw_roles.items():
            if not str(k).isdigit():
                continue
            roles = _normalize_roles(v)
            if roles:
                role_map[int(k)] = roles
        for uid in dynamic:
            role_map.setdefault(int(uid), {"ADMIN"})
        return dynamic, blocked, labels, role_map
    except Exception:
        return set(), set(), {}, {}


def _save_acl(
    dynamic_ids: set[int],
    blocked_ids: set[int],
    labels: dict[int, str],
    role_map: dict[int, set[str]] | None = None,
) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean_roles: dict[str, list[str]] = {}
    for uid, roles in (role_map or {}).items():
        normalized = _normalize_roles(roles)
        if int(uid) > 0 and normalized:
            clean_roles[str(int(uid))] = sorted(normalized)
    payload = {
        "dynamic_admin_ids": sorted(int(x) for x in dynamic_ids if int(x) > 0),
        "blocked_admin_ids": sorted(int(x) for x in blocked_ids if int(x) > 0),
        "admin_labels": {str(int(k)): str(v) for k, v in sorted(labels.items()) if int(k) > 0 and str(v or "").strip()},
        "admin_roles": clean_roles,
    }
    _STORE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_dynamic_admin_ids() -> set[int]:
    dynamic, _, _, _ = _load_acl()
    return dynamic


def get_blocked_admin_ids() -> set[int]:
    _, blocked, _, _ = _load_acl()
    return blocked


def list_all_admin_ids() -> set[int]:
    ids = set(settings.admin_ids)
    ids.update(settings.super_admin_ids)
    ids.update(get_dynamic_admin_ids())
    return ids


def is_admin_user(tg_user_id: int) -> bool:
    uid = int(tg_user_id)
    if uid in settings.super_admin_ids:
        return True
    blocked = get_blocked_admin_ids()
    if uid in blocked:
        return False
    if uid in settings.admin_ids:
        return True
    return uid in get_dynamic_admin_ids()


def is_super_admin_user(tg_user_id: int) -> bool:
    owner_id = settings.owner_super_admin_id
    if owner_id is not None:
        return int(tg_user_id) == int(owner_id)
    return int(tg_user_id) in settings.super_admin_ids


def get_admin_roles(tg_user_id: int) -> set[str]:
    uid = int(tg_user_id)
    roles: set[str] = set()
    if uid in settings.super_admin_ids:
        roles.update({"SUPER_ADMIN", "ADMIN"})
    if uid in settings.admin_ids:
        roles.add("ADMIN")
    _, blocked, _, role_map = _load_acl()
    if uid in blocked and uid not in settings.super_admin_ids:
        return set()
    roles.update(role_map.get(uid, set()))
    if "SUPER_ADMIN" in roles:
        roles.add("ADMIN")
    return {role for role in roles if role in ADMIN_ROLE_NAMES}


def is_game_admin_user(tg_user_id: int) -> bool:
    roles = get_admin_roles(int(tg_user_id))
    return bool(roles.intersection({"SUPER_ADMIN", "ADMIN", "GAME_OPERATOR"}))


def is_finance_admin_user(tg_user_id: int) -> bool:
    roles = get_admin_roles(int(tg_user_id))
    return bool(roles.intersection({"SUPER_ADMIN", "ADMIN", "FINANCE_ADMIN"}))


def is_user_admin_user(tg_user_id: int) -> bool:
    roles = get_admin_roles(int(tg_user_id))
    return bool(roles.intersection({"SUPER_ADMIN", "ADMIN"}))


def grant_dynamic_admin(tg_user_id: int, roles: set[str] | list[str] | tuple[str, ...] | None = None) -> None:
    uid = int(tg_user_id)
    dynamic, blocked, labels, role_map = _load_acl()
    blocked.discard(uid)
    normalized_roles = _normalize_roles(roles or {"ADMIN"}) or {"ADMIN"}
    if uid not in settings.admin_ids and uid not in settings.super_admin_ids:
        dynamic.add(uid)
    role_map[uid] = _normalize_roles(set(role_map.get(uid, set())).union(normalized_roles))
    _save_acl(dynamic, blocked, labels, role_map)


def revoke_dynamic_admin(tg_user_id: int) -> None:
    uid = int(tg_user_id)
    if uid in settings.super_admin_ids:
        return
    dynamic, blocked, labels, role_map = _load_acl()
    dynamic.discard(uid)
    role_map.pop(uid, None)
    if uid in settings.admin_ids:
        blocked.add(uid)
    else:
        blocked.discard(uid)
    labels.pop(uid, None)
    _save_acl(dynamic, blocked, labels, role_map)


def sync_dynamic_admin_ids(tg_user_ids: set[int]) -> None:
    backend_ids = {int(x) for x in tg_user_ids if int(x) > 0}
    static_admins = set(settings.admin_ids)
    super_admins = set(settings.super_admin_ids)

    _, _, labels, old_role_map = _load_acl()
    dynamic = {uid for uid in backend_ids if uid not in static_admins and uid not in super_admins}
    blocked = {uid for uid in static_admins if uid not in backend_ids}
    keep_ids = backend_ids | super_admins
    clean_labels = {uid: val for uid, val in labels.items() if uid in keep_ids and str(val or "").strip()}
    role_map = {uid: old_role_map.get(uid, {"ADMIN"}) for uid in backend_ids}
    _save_acl(dynamic, blocked, clean_labels, role_map)


def sync_dynamic_admin_roles(admin_roles: dict[int, set[str] | list[str] | tuple[str, ...]]) -> None:
    backend_ids = {int(uid) for uid in admin_roles if int(uid) > 0}
    static_admins = set(settings.admin_ids)
    super_admins = set(settings.super_admin_ids)

    _, _, labels, _ = _load_acl()
    dynamic = {uid for uid in backend_ids if uid not in static_admins and uid not in super_admins}
    blocked = {uid for uid in static_admins if uid not in backend_ids}
    keep_ids = backend_ids | super_admins
    clean_labels = {uid: val for uid, val in labels.items() if uid in keep_ids and str(val or "").strip()}
    role_map = {
        int(uid): (_normalize_roles(roles) or {"ADMIN"})
        for uid, roles in admin_roles.items()
        if int(uid) > 0
    }
    for uid in super_admins:
        role_map[uid] = {"SUPER_ADMIN", "ADMIN"}
    for uid in static_admins:
        role_map.setdefault(uid, {"ADMIN"})
    _save_acl(dynamic, blocked, clean_labels, role_map)


def set_admin_label(tg_user_id: int, label: str) -> None:
    uid = int(tg_user_id)
    dynamic, blocked, labels, role_map = _load_acl()
    val = str(label or "").strip()
    if val:
        labels[uid] = val
    else:
        labels.pop(uid, None)
    _save_acl(dynamic, blocked, labels, role_map)


def get_admin_label(tg_user_id: int) -> str:
    _, _, labels, _ = _load_acl()
    return str(labels.get(int(tg_user_id), "") or "")
