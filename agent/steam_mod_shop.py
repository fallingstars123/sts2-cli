"""Add readable offline effects to visible Steam shop choices."""

from functools import lru_cache
import json
from pathlib import Path
import re


TABLES = {"relic": "relics.json", "potion": "potions.json"}
ITEM_ID = re.compile(r"[A-Z0-9_]{1,96}")
MARKUP = re.compile(r"\[/?(?:b|i|u|color|gold|blue|green|purple|red|orange|gray|white|yellow|rainbow|center)"
                    r"(?:=[^\]\n]*)?\]", re.IGNORECASE)
IMAGES = re.compile(r"\[img\].*?\[/img\]", re.IGNORECASE | re.DOTALL)
FIELD = re.compile(r"\{([^{}]*)\}")


@lru_cache(maxsize=8)
def _read_table(path):
    try:
        table = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, RecursionError):
        return {}
    return table if isinstance(table, dict) else {}


def _clean(value):
    if not isinstance(value, str):
        return ""
    return " ".join(MARKUP.sub("", IMAGES.sub("", value)).split())


def _template(text, values):
    numbers = {key.casefold(): value for key, value in values.items()
               if isinstance(key, str) and type(value) is int} if isinstance(values, dict) else {}
    missing = False

    def replace(match):
        nonlocal missing
        key, _, operation = match.group(1).partition(":")
        amount = numbers.get(key.casefold())
        if operation.startswith("plural:"):
            forms = operation.removeprefix("plural:").split("|", 1)
            if len(forms) == 2:
                return forms[0] if amount == 1 else forms[1]
        if key.casefold() == "incombat" and "|" in operation:
            return operation.rsplit("|", 1)[1]
        if operation.startswith(("energyIcons(", "starIcons(")):
            resource = " Energy" if operation.startswith("energy") else " Stars"
            missing |= amount is None
            return f"{amount if amount is not None else '?'}{resource}"
        if amount is not None and operation in ("", "diff()", "abs()"):
            return str(abs(amount) if operation == "abs()" else amount)
        missing = True
        return "?"

    while FIELD.search(text):
        text = FIELD.sub(replace, text)
    if "{" in text or "}" in text:
        missing = True
        text = text.replace("{", "?").replace("}", "")
    return _clean(text), missing


def shop_actions(state):
    """Hide potion purchases when the bridge reports a full potion belt."""
    actions = state["actions"]
    if state["screen"] != "shop":
        return actions
    run = state.get("run") or {}
    capacity, potions = run.get("potion_capacity"), run.get("potions")
    if type(capacity) is not int or capacity < 0 or not isinstance(potions, list) or len(potions) < capacity:
        return actions
    return [action for action in actions
            if action["kind"] != "buy_shop_item" or action["detail"].get("type") != "potion"]


def shop_item_context(actions, localization_dir):
    """Describe legal relic and potion purchases without changing the action list."""
    directory = Path(localization_dir)
    items = []
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or action.get("kind") != "buy_shop_item":
            continue
        detail = action.get("detail")
        if not isinstance(detail, dict):
            continue
        kind, identifier = detail.get("type"), detail.get("item")
        if not isinstance(kind, str) or kind not in TABLES or not isinstance(identifier, str):
            continue
        identifier = identifier.strip().upper().removeprefix(kind.upper() + ".")
        if not ITEM_ID.fullmatch(identifier):
            continue
        local = _read_table(directory / TABLES[kind])
        name = _clean(detail.get("title")) or _clean(local.get(identifier + ".title")) or identifier
        text = _clean(detail.get("description")) or _clean(local.get(identifier + ".description"))
        description, missing = _template(text, detail.get("vars"))
        item = {"choice": choice, "type": kind, "item": identifier, "name": name,
                "cost": detail.get("cost"), "affordable": detail.get("affordable"), "description": description or None}
        if missing:
            item["amounts_unavailable"] = True
        items.append(item)
    return items
