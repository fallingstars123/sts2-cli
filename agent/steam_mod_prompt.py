"""Build a compact, self-contained copy of the visible game state for the model."""

import json
import re


ACTION_REFERENCES = {
    "card_reward": ("cards", "pick_card_reward", "card_option_index"),
    "card_selection": ("cards", "toggle_card_choice", "card_option_index"),
    "event": ("options", "choose_event_option", "option_index"),
    "rewards": ("rewards", "claim_reward", "reward_index"),
    "shop": ("items", "buy_shop_item", "item_index"),
}
CARD_FIELDS = {"card_id": "id", "card": "name", "card_instance_id": "instance_id", "description": "description"}
TARGET_FIELDS = {"target": "name", "target_instance_id": "instance_id"}
POTION_FIELDS = {"potion_id": "id", "potion": "name", "description": "description", "usage": "usage"}


def _without_duplicate_fields(detail, source, aliases):
    return {key: value for key, value in detail.items()
            if key not in aliases or aliases[key] not in source or value != source[aliases[key]]}


def _index_rows(rows):
    return {row["index"]: row for row in (rows or []) if isinstance(row, dict) and type(row.get("index")) is int}


def _combat_action_details(actions, state):
    hand = _index_rows(state.get("hand"))
    potions = _index_rows(state.get("potions"))
    enemies = _index_rows(state.get("enemies"))
    for action in actions:
        detail = action["detail"]
        if action["kind"] == "play_card":
            detail = _without_duplicate_fields(detail, hand.get(detail.get("card_index"), {}), CARD_FIELDS)
        elif action["kind"] == "use_potion":
            detail = _without_duplicate_fields(detail, potions.get(detail.get("potion_index"), {}), POTION_FIELDS)
        if action["kind"] in {"play_card", "use_potion"}:
            detail = _without_duplicate_fields(detail, enemies.get(detail.get("target_index"), {}), TARGET_FIELDS)
        detail = {key: value for key, value in detail.items() if value is not None}
        if action["kind"] == "end_turn" and detail.get("turn") == state.get("turn"):
            detail.pop("turn")
        yield detail


def _reference_details(actions, state, reference):
    list_name, kind, index_key = reference
    entries = state.get(list_name) or []
    for action in actions:
        detail = action["detail"]
        if action["kind"] == kind:
            match = next((i for i, entry in enumerate(entries) if detail == entry), None)
            if match is not None:
                detail = {index_key: match}
        yield detail


ICONS = re.compile(r"(?:\[img\]res://images/packed/sprite_fonts/(\w+?)_icon\.png\[/img\])+")
ICON = re.compile(r"\[img\]res://images/packed/sprite_fonts/(\w+?)_icon\.png\[/img\]")
MARKUP = re.compile(r"\[/?[a-z]+(?:=[^\]\n]*)?\]", re.IGNORECASE)
CARD_DEFAULTS = {"energy_x": False, "star_x": False, "star_cost": -1, "keywords": [], "affliction": None}
PILE_ONLY = ("id", "upgrade")
PILE_FIELDS = {"name", "type", "energy_cost", "star_cost", "count"}


def _pile_entry(row):
    """A plain pile card reads as 'Name (Type, 1 energy, 2 stars) x2'."""
    if not isinstance(row, dict) or not set(row) <= PILE_FIELDS or not isinstance(row.get("name"), str):
        return row
    costs = [row.get("type")] if isinstance(row.get("type"), str) else []
    if type(row.get("energy_cost")) is int:
        costs.append(f"{row['energy_cost']} energy")
    if type(row.get("star_cost")) is int:
        costs.append(f"{row['star_cost']} stars")
    count = row.get("count")
    return row["name"] + (f" ({', '.join(costs)})" if costs else "") + (f" x{count}" if type(count) is int and count > 1 else "")
COMPACT_NOTE = """State text is plain: an icon run reads as a count, for example "2 Stars"
or "3 Energy". Card, power and intent fields that are left out are empty or default:
no star cost, not X-cost, no keywords, affliction or amount. A pile entry reads
"Name (Type, energy cost, star cost) xN" and has one copy without xN. Card, relic, potion and power text is listed once by name in card_text,
relic_text, potion_text and power_text. The fight reference holds those tables for the whole fight; an entry of the
same name in state replaces it, and a row with its own description uses that text."""


def _icon_name(name):
    name = name.lower()
    return "Energy" if "energy" in name else "Star" if name == "star" else name.replace("_", " ").title()


def plain_text(text):
    """Drop BBCode colour tags and spell out icon runs, which carry the values themselves."""
    if "[" not in text:
        return text

    def icons(match):
        names = ICON.findall(match.group(0))
        label = _icon_name(names[0])
        if len(set(names)) != 1:
            return " ".join(_icon_name(name) for name in names)
        if len(names) == 1:
            return label
        return f"{len(names)} {label}" + ("s" if label == "Star" else "")

    return MARKUP.sub("", ICONS.sub(icons, text))


def compact_text(value):
    if isinstance(value, str):
        return plain_text(value)
    if isinstance(value, list):
        return [compact_text(item) for item in value]
    if isinstance(value, dict):
        return {key: compact_text(item) for key, item in value.items()}
    return value


def _without_defaults(row, defaults=CARD_DEFAULTS):
    return {key: value for key, value in row.items()
            if value is not None and not (key in defaults and value == defaults[key])}


def _compact_power(power):
    if not isinstance(power, dict):
        return power
    row = {key: value for key, value in power.items() if value is not None}
    if row.get("display_amount") == row.get("amount"):
        row.pop("display_amount", None)
    if isinstance(row.get("name"), str):
        row.pop("id", None)
    return row


def _compact_creature(creature):
    if not isinstance(creature, dict):
        return creature
    row = {key: value for key, value in creature.items() if value is not None and value != []}
    if isinstance(row.get("powers"), list):
        row["powers"] = [_compact_power(power) for power in row["powers"]]
    if isinstance(row.get("intents"), list):
        row["intents"] = [{key: value for key, value in intent.items() if value is not None}
                          if isinstance(intent, dict) else intent for intent in row["intents"]]
    return row


def _named_row(row):
    """A relic or potion row is identified by its name; its id and empty fields add nothing."""
    if not isinstance(row, dict):
        return row
    return {key: value for key, value in row.items()
            if value is not None and not (key == "id" and isinstance(row.get("name"), str))}


def _named_text(rows, table, key="name", text="description"):
    """Move each row's text into table[name]; keep it inline when that name already has other text."""
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str) or not isinstance(row.get(text), str):
            result.append(row)
            continue
        name, description = row[key], row[text]
        if table.setdefault(name, description) == description:
            row = {field: value for field, value in row.items() if field != text}
        result.append(row)
    return result


def _fold_combat_text(state):
    """List each distinct card, relic and potion text once instead of on every row and pile."""
    card_text = {}
    for zone in ("hand", "draw_pile", "discard_pile", "exhaust_pile"):
        cards = state.get(zone)
        if not isinstance(cards, list):
            continue
        rows = []
        for card in cards:
            if isinstance(card, dict):
                card = _without_defaults(card)
                if zone != "hand" and isinstance(card.get("name"), str):
                    card = {key: value for key, value in card.items() if key not in PILE_ONLY}
                    if card.get("count") == 1:
                        card.pop("count")
                elif zone == "hand":
                    card.pop("instance_id", None)
                    if isinstance(card.get("name"), str):
                        card.pop("upgrade", None)    # the name already ends in + when upgraded
            rows.append(card)
        rows = _named_text(rows, card_text)
        state[zone] = rows if zone == "hand" else [_pile_entry(row) for row in rows]
    if card_text:
        state["card_text"] = card_text
    power_text = {}

    def creature(row):
        row = _compact_creature(row)
        if isinstance(row, dict) and isinstance(row.get("powers"), list):
            row["powers"] = _named_text(row["powers"], power_text)
        return row

    if isinstance(state.get("enemies"), list):
        state["enemies"] = [creature(enemy) for enemy in state["enemies"]]
    if isinstance(state.get("potions"), list):
        potion_text = {}
        state["potions"] = _named_text([_named_row(potion) for potion in state["potions"]], potion_text)
        if potion_text:
            state["potion_text"] = potion_text
    if isinstance(player := state.get("player"), dict):
        player = creature(player)
        if isinstance(player.get("relics"), list):
            relic_text = {}
            player["relics"] = _named_text([_named_row(relic) for relic in player["relics"]], relic_text)
            if relic_text:
                state["relic_text"] = relic_text
        state["player"] = player
    if power_text:
        state["power_text"] = power_text
    for key in [key for key, value in state.items() if value is None or value == []]:
        state.pop(key)


class FightReference:
    """Per-fight card, relic and potion text, kept byte-stable so the provider can cache it.

    The tables are taken from the first decision of each fight and then frozen: a later name,
    or a name whose text has changed, is sent in the state's own table instead, so the model
    always sees the live text while the cached block never changes mid-fight.
    """

    TABLES = ("card_text", "relic_text", "potion_text", "power_text")

    def __init__(self):
        self.key = None
        self.tables = {}

    def split(self, snapshot, context):
        """Move reference tables out of context; return the stable JSON text, or None."""
        state = context.get("state")
        run = snapshot.get("run") or {}
        live = snapshot.get("state") or {}
        if snapshot.get("screen") != "combat" or not isinstance(state, dict):
            return None
        key = tuple(run.get(name) for name in ("profile", "seed", "start_time", "act", "floor")) + (
            live.get("encounter"), run.get("combat_retry_count"))
        fresh = key != self.key
        if fresh:
            self.key, self.tables = key, {}
        for name in self.TABLES:
            current = state.pop(name, None)
            if not isinstance(current, dict):
                continue
            if fresh:
                self.tables[name] = dict(current)
            table = self.tables.get(name, {})
            overrides = {label: text for label, text in current.items() if table.get(label) != text}
            if overrides:
                state[name] = overrides
        if not self.tables:
            return None
        return "Fight reference (unchanged entries stay valid all fight): " + json.dumps(
            self.tables, ensure_ascii=False, separators=(",", ":"))


def decision_context(snapshot, *, include_deck):
    """Leave the source snapshot untouched for local tactics, action validation, and archives."""
    context = {key: value for key, value in snapshot.items() if key not in {"state_id", "protocol", "retry_failure"}}
    for section in ("state", "run"):
        if isinstance(context.get(section), dict):
            context[section] = {key: value for key, value in context[section].items()
                                if key not in {"profile", "seed", "start_time", "run_instance"}}
    state = context.get("state") or {}
    run = context.get("run") or {}
    if not include_deck:
        run.pop("deck", None)
    for key in [key for key, value in run.items() if value is None]:
        run.pop(key)

    actions = snapshot["actions"]
    screen = snapshot["screen"]
    if screen == "combat":
        details = list(_combat_action_details(actions, state))
        for key in ("act", "floor", "ascension"):
            if key in state and key in run and state[key] == run[key]:
                state.pop(key)
        if state.get("potions") is not None and state["potions"] == run.get("potions"):
            run.pop("potions")
        if isinstance(player := state.get("player"), dict):
            state["player"] = _without_duplicate_fields(
                player, run, {key: key for key in ("hp", "max_hp", "gold", "character")}
            )
            role = state["player"].get("character")
            if isinstance(role, str) and isinstance(run.get("character"), str) and run["character"].endswith("." + role):
                state["player"].pop("character")
            relics = player.get("relics")
            if isinstance(relics, list) and all(isinstance(relic, dict) for relic in relics):
                if [relic.get("id") for relic in relics] == run.get("relics"):
                    run.pop("relics")
        _fold_combat_text(state)
    elif reference := ACTION_REFERENCES.get(screen):
        details = _reference_details(actions, state, reference)
    else:
        details = (action["detail"] for action in actions)
    context["actions"] = [{"choice": i, "kind": action["kind"], "detail": detail}
                          for i, (action, detail) in enumerate(zip(actions, details), 1)]
    return context
