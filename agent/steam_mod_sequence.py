"""Revalidate short model-suggested combat prefixes against each native state."""

from collections import Counter, deque
from dataclasses import dataclass, replace
import re


MAX_CHOICES = 6
CARD_TARGETS = {"AnyEnemy", "AllEnemies", "Self", "None", "AnyPlayer"}
MARKUP = re.compile(r"\[/?[a-z]+(?:=[^\]\n]*)?\]", re.IGNORECASE)
UNPREDICTABLE = re.compile(
    r"\b(?:random\w*|draws?|shuffle\w*|reveal\w*|choose|select|discover|scry|fetch)\b"
    r"|\bdiscard\s+(?!pile\b)"
    r"|\b(?:add|copy|put|return)\b[^.\n]*\binto your hand\b"
    r"|抽牌|抽\s*\d+\s*[张張]牌|随机|隨機|ランダム|무작위|al[ée]atoire|aleatori[oa]|zufällig|случайн", re.IGNORECASE,
)
PILE_KEYS = ("draw_pile_count", "discard_pile_count", "exhaust_pile_count")


def _object(value):
    return value if isinstance(value, dict) else {}


def _identity(value):
    if (type(value) is int and value >= 0) or (isinstance(value, str) and 0 < len(value) <= 128):
        return value
    return None


def _number(value):
    return type(value) is int and value >= 0


def _indexed(items):
    if not isinstance(items, list):
        return None
    result = {}
    instances = set()
    for position, item in enumerate(items):
        item = _object(item)
        index = item.get("index", position)
        instance = _identity(item.get("instance_id"))
        model = item.get("id")
        if (not _number(index) or index in result or instance is None or instance in instances
                or not isinstance(model, str) or not model):
            return None
        result[index] = item
        instances.add(instance)
    return result


@dataclass(frozen=True)
class View:
    state_id: str
    session: str
    revision: int
    scope: tuple
    state: dict
    hand: dict
    enemies: dict
    actions: list


def _view(snapshot):
    snapshot = _object(snapshot)
    state = _object(snapshot.get("state"))
    run = _object(snapshot.get("run"))
    state_id = snapshot.get("state_id")
    if snapshot.get("screen") != "combat" or state.get("phase") != "Play" or not isinstance(state_id, str):
        return None
    epoch = state_id.rsplit(":", 2)
    if (len(epoch) != 3 or not epoch[0] or len(epoch[1]) > 20 or not epoch[1].isascii()
            or not epoch[1].isdigit() or not epoch[2]):
        return None
    scope = tuple(run.get(key) for key in ("profile", "seed", "character", "start_time", "act", "floor"))
    profile, seed, character, started, act, floor = scope
    encounter, turn, round_number = (state.get(key) for key in ("encounter", "turn", "round"))
    if (not _number(profile) or not isinstance(seed, str) or not seed or not isinstance(character, str) or not character
            or (started is not None and not _number(started)) or not _number(act) or not _number(floor)
            or not isinstance(encounter, str) or not encounter or not _number(turn) or not _number(round_number)):
        return None
    player = _object(state.get("player"))
    hand = _indexed(state.get("hand"))
    enemies = _indexed(state.get("enemies"))
    actions = snapshot.get("actions")
    if (hand is None or enemies is None or not isinstance(actions, list) or not _number(player.get("hp"))
            or player["hp"] == 0 or not _number(state.get("energy")) or not _number(state.get("stars"))
            or any(not _number(state.get(key)) for key in PILE_KEYS)):
        return None
    return View(state_id, epoch[0], int(epoch[1]), scope + (encounter, turn, round_number), state, hand, enemies, actions)


def _needs_replan(*descriptions):
    texts = [description for description in descriptions if isinstance(description, str) and description.strip()]
    if not texts:
        return None
    return any(UNPREDICTABLE.search(MARKUP.sub("", text)) for text in texts)


@dataclass(frozen=True)
class Move:
    kind: str
    instance: str | int
    model: str
    target: str | int | None
    energy: int = 0
    stars: int = 0
    upgrade: int | None = None
    target_type: str | None = None
    x_cost: bool = False
    needs_replan: bool = False

    @property
    def resource(self):
        return self.kind, self.instance

    @property
    def can_continue(self):
        return not self.x_cost and not self.needs_replan

    def affordable(self, energy, stars):
        return stars >= self.stars and energy >= (1 if self.x_cost else self.energy)


# A planned end of turn closes a sequence. It is released only after every planned play was
# observed with an unchanged context, and the agent still runs its end-turn checks on it.
END_TURN = Move("end_turn", "end_turn", "end_turn", None, needs_replan=True)


def _is_end_turn(action):
    return _object(action).get("kind") == "end_turn"


def _reference_matches(action, detail, key, expected):
    for source in (action, detail):
        if key in source:
            value = source[key]
            if (expected is None and value is not None) or (expected is not None and _identity(value) != expected):
                return False
    return True


def _move(view, action):
    action = _object(action)
    kind = action.get("kind")
    if kind not in ("play_card", "use_potion"):
        return None
    detail = _object(action.get("detail"))
    target_index = detail.get("target_index")
    target = None
    if target_index is not None:
        enemy = view.enemies.get(target_index) if _number(target_index) else None
        if enemy is None or enemy.get("hp") == 0:
            return None
        target = enemy["instance_id"]
    if not _reference_matches(action, detail, "target_instance_id", target):
        return None
    if kind == "use_potion":
        slot, model = detail.get("potion_index"), detail.get("potion_id")
        potions = _potion_slots(view.state)
        needs_replan = _needs_replan(detail.get("description"))
        if (_number(slot) and isinstance(model, str) and model and needs_replan is not None
                and (potions is None or potions.get(slot) == model)):
            return Move(kind, slot, model, target, needs_replan=needs_replan)
        return None

    index = detail.get("card_index")
    card = view.hand.get(index) if _number(index) else None
    if card is None or not _reference_matches(action, detail, "card_instance_id", card["instance_id"]):
        return None
    model = card.get("id")
    target_type = card.get("target_type")
    energy, stars = card.get("energy_cost"), card.get("star_cost")
    x_cost = card.get("energy_x")
    needs_replan = _needs_replan(card.get("description"), detail.get("description"))
    if (not isinstance(model, str) or not model or model != detail.get("card_id")
            or not isinstance(target_type, str) or target_type not in CARD_TARGETS
            or (target_type == "AnyEnemy") != (target is not None)
            or type(x_cost) is not bool or card.get("star_x") is not False
            or not _number(energy) or type(stars) is not int or stars < -1 or needs_replan is None):
        return None
    if x_cost and (energy == 0 or energy != view.state["energy"]):
        return None
    return Move(kind, card["instance_id"], model, target, energy, max(0, stars), card.get("upgrade"),
                target_type, x_cost=x_cost, needs_replan=needs_replan)


def can_plan(snapshot):
    """Check that a legal first move can be followed by another distinct, affordable move."""
    view = _view(snapshot)
    if view is None:
        return False
    energy, stars = view.state["energy"], view.state["stars"]
    moves = [move for action in view.actions if (move := _move(view, action)) is not None]
    return any(first.can_continue and first.affordable(energy, stars)
               and any(second.resource != first.resource
                       and second.affordable(energy - first.energy, stars - first.stars) for second in moves)
               for first in moves)


def _choice(view, choice):
    if type(choice) is not int or not 1 <= choice <= len(view.actions):
        return None
    return _move(view, view.actions[choice - 1])


def _hand_ids(view):
    return {(card["instance_id"], card.get("id")) for card in view.hand.values()}


def _roster(view):
    return {(enemy["instance_id"], enemy.get("id"), enemy.get("hp") != 0) for enemy in view.enemies.values()}


def _intent_pattern(view):
    return {
        enemy["instance_id"]: tuple((intent.get("type"), intent.get("hits"))
                                    for intent in (enemy.get("intents") or []) if isinstance(intent, dict))
        for enemy in view.enemies.values()
    }


def _potion_slots(state):
    items = state.get("potions")
    if not isinstance(items, list):
        return None
    slots = {}
    for item in items:
        item = _object(item)
        slot, model = item.get("index"), item.get("id")
        if not _number(slot) or slot in slots or not isinstance(model, str) or not model:
            return None
        slots[slot] = model
    return slots


def _visible_draw_pile(state):
    items = state.get("draw_pile")
    if not isinstance(items, list):
        return None
    counts = Counter()
    for item in items:
        item = _object(item)
        model, upgrade, count = (item.get(key) for key in ("id", "upgrade", "count"))
        if not isinstance(model, str) or not _number(upgrade) or not _number(count):
            return None
        counts[model, upgrade] += count
    return counts


def _unchanged_context(before, after, move):
    if (before.session != after.session or after.revision != before.revision + 1 or before.scope != after.scope
            or _roster(before) != _roster(after) or _intent_pattern(before) != _intent_pattern(after)):
        return False
    previous, current = before.state, after.state
    if any(previous["player"].get(key) != current["player"].get(key) for key in ("hp", "max_hp")):
        return False
    if any(previous.get(key) != current.get(key) for key in ("revealed_cards", "revealed_draw_pile")):
        return False
    if (previous["draw_pile_count"] != current["draw_pile_count"]
            or _visible_draw_pile(previous) != _visible_draw_pile(current)):
        return False
    hand = _hand_ids(before)
    changed_piles = [current[key] - previous[key] for key in PILE_KEYS[1:]]
    if move.kind == "play_card":
        hand.discard((move.instance, move.model))
        if any(delta not in (0, 1) for delta in changed_piles) or sum(changed_piles) > 1:
            return False
    else:
        if changed_piles != [0, 0] or any(
                _object(action).get("kind") == "use_potion"
                and _object(action.get("detail")).get("potion_index") == move.instance
                for action in after.actions):
            return False
    potions_before, potions_after = _potion_slots(previous), _potion_slots(current)
    if potions_before is not None and potions_after is not None:
        if move.kind == "use_potion" and potions_before.pop(move.instance, None) != move.model:
            return False
        if potions_before != potions_after:
            return False
    return hand == _hand_ids(after)


class CombatSequence:
    """Store only a short prefix and release each move after its predecessor is observed."""

    can_plan = staticmethod(can_plan)

    def __init__(self):
        self._pending = deque()
        self._in_flight = None
        self._ready_state = None

    @property
    def has_pending(self):
        return bool(self._pending)

    def clear(self):
        self._pending.clear()
        self._in_flight = self._ready_state = None

    def offer(self, snapshot, primary_choice, choices):
        """Keep supported later choices and return their count."""
        self.clear()
        if (type(primary_choice) is not int or not isinstance(choices, list) or len(choices) < 2
                or type(choices[0]) is not int or choices[0] != primary_choice):
            return 0
        view = _view(snapshot)
        if view is None:
            return 0
        primary = _choice(view, primary_choice)
        energy, stars = view.state["energy"], view.state["stars"]
        if primary is None or not primary.can_continue or not primary.affordable(energy, stars):
            return 0
        energy -= primary.energy
        stars -= primary.stars
        used = {primary.resource}
        later = choices[1:MAX_CHOICES]
        for position, choice in enumerate(later):
            if (position == len(later) - 1 and type(choice) is int and 1 <= choice <= len(view.actions)
                    and _is_end_turn(view.actions[choice - 1])):
                self._pending.append(END_TURN)
                break
            move = _choice(view, choice)
            if move is None or move.resource in used or not move.affordable(energy, stars):
                break
            self._pending.append(replace(move, energy=energy) if move.x_cost else move)
            if not move.can_continue:
                break
            energy -= move.energy
            stars -= move.stars
            used.add(move.resource)
        if self._pending:
            self._in_flight = (view.state_id, primary)
        return len(self._pending)

    def take(self, snapshot):
        """Return the next current choice number, or invalidate the prefix."""
        if not self._pending:
            return None
        view = _view(snapshot)
        if view is not None and self._ready_state == view.state_id:
            expected = self._pending[0]
            if expected is END_TURN:
                matches = [index for index, action in enumerate(view.actions, 1) if _is_end_turn(action)]
            else:
                matches = [index for index, action in enumerate(view.actions, 1) if _move(view, action) == expected]
            if len(matches) == 1 and expected.affordable(view.state["energy"], view.state["stars"]):
                self._pending.popleft()
                self._ready_state = None
                self._in_flight = (view.state_id, expected)
                return matches[0]
        self.clear()
        return None

    def advance(self, before, action, after):
        """Confirm an accepted native action and release the next move if it is still safe."""
        if self._pending and self._in_flight is not None:
            previous, current = _view(before), _view(after)
            state_id, move = self._in_flight
            if (previous is not None and current is not None and state_id == previous.state_id
                    and action in previous.actions and _move(previous, action) == move and move.can_continue
                    and _unchanged_context(previous, current, move)):
                self._in_flight = None
                self._ready_state = current.state_id
                return
        self.clear()
