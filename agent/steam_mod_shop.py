"""Add readable offline effects to visible Steam shop choices."""

from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import re

from steam_mod_strategy import card_pick_advice


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


def potion_belt_full(snapshot):
    run = snapshot.get("run") or {}
    capacity, potions = run.get("potion_capacity"), run.get("potions")
    return type(capacity) is int and capacity >= 0 and isinstance(potions, list) and len(potions) >= capacity


POTION_TIERS = (
    {"SPEED_POTION", "FLEX_POTION"},
    {"POTION_SHAPED_ROCK", "FOUL_POTION", "LIQUID_BRONZE"},
    {"BLOCK_POTION", "FIRE_POTION", "EXPLOSIVE_AMPOULE", "WEAK_POTION", "VULNERABLE_POTION",
     "ATTACK_POTION", "SKILL_POTION", "COLORLESS_POTION", "BONE_BREW", "POISON_POTION"},
    {"BLESSING_OF_THE_FORGE", "REGEN_POTION", "BLOOD_POTION", "ENERGY_POTION", "SWIFT_POTION",
     "DEXTERITY_POTION", "POWER_POTION", "DISTILLED_CHAOS", "GAMBLERS_BREW",
     "POTION_OF_DOOM", "SHACKLING_POTION", "BEETLE_JUICE", "SHIP_IN_A_BOTTLE",
     "STABLE_SERUM", "STRENGTH_POTION", "POT_OF_GHOULS", "POWDERED_DEMISE"},
    {"GIGANTIFICATION_POTION", "CURE_ALL", "DUPLICATOR", "ENTROPIC_BREW", "OROBIC_ACID",
     "GHOST_IN_A_JAR", "HEART_OF_IRON", "FAIRY_IN_A_BOTTLE", "POTION_OF_BINDING",
     "DROPLET_OF_PRECOGNITION", "LIQUID_MEMORIES", "LUCKY_TONIC", "AMBERGRIS", "FRUIT_JUICE"},
)
POTION_RANK = {potion: rank for rank, group in enumerate(POTION_TIERS, 1) for potion in group}
CHEAP_BLOCK = {
    "GRAVE_WARDEN", "NEGATIVE_PULSE", "DEATHS_DOOR", "DEFY", "DEFEND_NECROBINDER",
    "CHO_BARBS", "CHO_READY", "WHISTLING_ARROWS", "DEFEND_FOOL",
    "DEFEND_SILENT", "BACKFLIP", "DEFLECT", "DEFEND_IRONCLAD", "SHRUG_IT_OFF",
    "DEFEND_REGENT", "GATHER_LIGHT", "DEFEND_DEFECT", "LEAP",
}
DOOM_SOURCES = {"BLIGHT_STRIKE", "NEGATIVE_PULSE", "DEATHBRINGER", "SCOURGE", "OBLIVION"}


def potion_rank(snapshot, potion_id):
    if potion_id != "FORTIFIER":
        return POTION_RANK.get(potion_id)
    deck = Counter()
    for row in (snapshot.get("run") or {}).get("deck") or ():
        card, count = row.get("id"), row.get("count", 1)
        if isinstance(card, str) and type(count) is int and count > 0:
            deck[card] += count
    block_cards = sum(deck[card] for card in CHEAP_BLOCK)
    doom_block = "DEATHS_DOOR" in deck and len(deck.keys() & DOOM_SOURCES) >= 2
    scales = doom_block or block_cards >= 5 and 4 * block_cards >= deck.total()
    return POTION_RANK["DUPLICATOR"] if scales else POTION_RANK["BLOCK_POTION"]


def potion_reward_action(snapshot):
    """Take a potion or make space for a strictly better known potion."""
    if snapshot["screen"] != "rewards":
        return None
    run = snapshot.get("run") or {}
    if type(run.get("potion_capacity")) is not int or not isinstance(run.get("potions"), list):
        return None
    actions = snapshot["actions"]
    rewards = [action for action in actions
               if action["kind"] == "claim_reward" and action["detail"].get("type") == "potion"]
    if not rewards:
        return None
    reward = max(rewards, key=lambda action: potion_rank(snapshot, action["detail"].get("item")) or 0)
    if not potion_belt_full(snapshot):
        return reward
    rank = potion_rank(snapshot, reward["detail"].get("item"))
    if rank is None:
        return None
    weaker = []
    for action in actions:
        if action["kind"] != "discard_potion":
            continue
        detail = action["detail"]
        held = next((p for p in run["potions"] if p.get("index") == detail.get("potion_index")
                     and p.get("id") == detail.get("potion_id")), None)
        old_rank = potion_rank(snapshot, held["id"]) if held else None
        if old_rank is not None and old_rank < rank:
            weaker.append((old_rank, action))
    return min(weaker, key=lambda entry: entry[0])[1] if weaker else None


class RewardProgress:
    """Remember which still-visible card offers the player has skipped."""

    def __init__(self):
        self.summary = None
        self.opened = None
        self.skipped = set()

    def available(self, snapshot, actions):
        if snapshot["screen"] != "rewards":
            return actions
        run = snapshot.get("run") or {}
        summary = (run.get("act"), run.get("floor"), snapshot["state"].get("rewards"))
        if summary != self.summary:
            self.summary = summary
            self.skipped.clear()
        return [action for action in actions if action["id"] not in self.skipped]

    def advance(self, before, action, after):
        screen, next_screen = before["screen"], after["screen"]
        if (screen == "rewards" and next_screen == "card_reward"
                and action["kind"] == "claim_reward" and action["detail"].get("type") == "cards"):
            self.opened = action["id"]
            return
        if next_screen == "card_reward":
            return
        if next_screen == "rewards":
            if screen == "card_reward" and self.opened is not None:
                if action["kind"] == "card_reward_alternative":
                    self.skipped.add(self.opened)
                self._remove_claim(after, self.opened)
            elif screen == "rewards" and action["kind"] == "claim_reward":
                self._remove_claim(after, action["id"])
        self.opened = None

    def _remove_claim(self, after, claim_id):
        if not self.summary or not self.skipped:
            return
        act, floor, previous = self.summary
        run = after.get("run") or {}
        rewards = after["state"].get("rewards")
        prefix = "reward.claim."
        tail = claim_id.removeprefix(prefix)
        if ((run.get("act"), run.get("floor")) != (act, floor)
                or not isinstance(previous, list) or not isinstance(rewards, list)
                or not claim_id.startswith(prefix) or not tail.isdecimal()):
            return
        index = int(tail)
        if index >= len(previous) or rewards != previous[:index] + previous[index + 1:]:
            return
        # Native reward IDs are positional. Shift an already skipped offer only after
        # the game confirms this exact removal and the surrounding stock is unchanged.
        shifted = set()
        for position in range(len(previous)):
            if position != index and f"{prefix}{position}" in self.skipped:
                new_position = position - 1 if position > index else position
                shifted.add(f"{prefix}{new_position}")
        self.skipped = shifted
        self.summary = (act, floor, rewards)


def _starter_cards(run):
    return any(isinstance(card, dict) and isinstance(card.get("id"), str)
               and card["id"].rsplit(".", 1)[-1].startswith(("STRIKE_", "DEFEND_"))
               and type(card.get("count", 1)) is int and card.get("count", 1) > 0
               for card in (run.get("deck") or ()))


def early_shop_removal(snapshot):
    """Use an affordable early removal while basic Strikes or Defends remain."""
    run = snapshot.get("run") or {}
    if snapshot["screen"] != "shop" or run.get("act") not in (1, 2) or not _starter_cards(run):
        return None
    return next((action for action in snapshot["actions"] if action["kind"] == "buy_shop_item"
                 and action["detail"].get("type") == "card_removal"
                 and action["detail"].get("affordable") is True), None)


def is_reward_skip(action):
    return (action["kind"] == "card_reward_alternative"
            and str(action["detail"].get("title", "")).casefold() in {"skip", "\u8df3\u8fc7", "\u8df3\u904e"})


def item_actions(snapshot):
    """Keep legal offers consistent with the card budget and reward policy."""
    actions = snapshot["actions"]
    screen = snapshot["screen"]
    if screen == "card_reward" and any(is_reward_skip(action) for action in actions):
        traps = set(card_pick_advice(snapshot).get("trap_choices", ()))
        return [action for choice, action in enumerate(actions, 1) if choice not in traps]
    potion_action = {"shop": "buy_shop_item", "rewards": "claim_reward"}.get(screen)
    if potion_action is not None and potion_belt_full(snapshot):
        actions = [action for action in actions if action["kind"] != "discard_potion"
                   and (action["kind"] != potion_action or action["detail"].get("type") != "potion")]
    if screen != "shop":
        return actions

    run = snapshot.get("run") or {}
    act, gold = run.get("act"), run.get("gold")
    if type(act) is not int or act < 1 or type(gold) is not int:
        return actions
    card_ids = {action["id"] for action in actions
                if action["kind"] == "buy_shop_item" and action["detail"].get("type") == "card"}
    if not card_ids:
        return actions

    # The inventory includes the removal price even when the action is unaffordable.
    items = snapshot["state"].get("items") or [action["detail"] for action in actions
                                               if action["kind"] == "buy_shop_item"]
    removal_price = next((item["cost"] for item in items if item.get("type") == "card_removal"
                          and type(item.get("cost")) is int), 0)
    budget = gold - removal_price if _starter_cards(run) else gold
    affordable = [action for action in actions if action["id"] not in card_ids
                  or type(action["detail"].get("cost")) is int and 0 <= action["detail"]["cost"] <= budget]
    advice = card_pick_advice({**snapshot, "actions": affordable})
    eligible = set(advice.get("shop_purchase_choices", ()))
    return [action for choice, action in enumerate(affordable, 1)
            if action["id"] not in card_ids or choice in eligible]


def shop_exit_action(snapshot, recent):
    """Follow a completed inventory close with the merchant's room exit."""
    if (snapshot["screen"] != "shop" or snapshot["state"].get("inventory_open") is not False
            or not recent or recent[-1].partition(" ")[0] != "close_shop"):
        return None
    return next((action for action in snapshot["actions"] if action["kind"] == "proceed"), None)


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
