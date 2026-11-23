"""Estimate what known direct draws can find in the visible unordered piles."""

from fractions import Fraction
from math import comb
import re


FIXED_DRAW_CARDS = frozenset({
    "ACROBATICS", "BACKFLIP", "BATTLE_TRANCE", "DAGGER_THROW",
    "POMMEL_STRIKE", "QUICK_SLASH", "SHRUG_IT_OFF",
})
CATEGORIES = ("block", "damage", "mitigation", "any")
MAX_HAND = 10
MAX_PILE = 2048
TAGS = re.compile(r"\[[^\[\]\r\n]{1,80}\]")
DRAW = re.compile(r"^(?:Draw ([1-9][0-9]?) cards?\.|抽([1-9][0-9]?)张牌。)$", re.IGNORECASE | re.MULTILINE)
BLOCK = re.compile(r"^(?:Gain [1-9][0-9]* Block\.|获得[1-9][0-9]*点格挡。)$", re.IGNORECASE | re.MULTILINE)
DAMAGE = re.compile(r"^(?:Deal [1-9][0-9]* damage(?: to (?:all enemies|a random enemy))?(?: [1-9][0-9]* times)?\."
                    r"|造成[1-9][0-9]*点伤害。)$", re.IGNORECASE | re.MULTILINE)
MITIGATION = re.compile(r"^(?:Apply [1-9][0-9]* Weak(?: to all enemies)?\.|"
                        r"Enemy loses [1-9][0-9]* Strength this turn\.|Gain [1-9][0-9]* Intangible\.|"
                        r"给予[1-9][0-9]*层虚弱。)$", re.IGNORECASE | re.MULTILINE)


def hand_capacity(combat):
    """Report the remaining hand slots in the current native combat snapshot."""
    hand = combat.get("hand")
    if not isinstance(hand, list):
        return {}
    return {"limit": MAX_HAND, "cards_in_hand": len(hand), "free_slots": max(0, MAX_HAND - len(hand))}


def _description(value):
    if not isinstance(value, str):
        return ""
    return "\n".join(line.strip() for line in TAGS.sub("", value).splitlines())


def _cost(card):
    energy, stars = card.get("energy_cost"), card.get("star_cost")
    if (card.get("energy_x") is not False or card.get("star_x") is not False
            or type(energy) is not int or energy < 0 or type(stars) is not int or stars < -1):
        return None
    return energy, max(0, stars)


def _pile(combat, name):
    count, groups = combat.get(f"{name}_count"), combat.get(name)
    if type(count) is not int or not 0 <= count <= MAX_PILE:
        return None
    if count == 0 and groups is None:
        return []
    if not isinstance(groups, list) or len(groups) > count:
        return None
    if any(not isinstance(card, dict) or type(card.get("count")) is not int
           or not 1 <= card["count"] <= count for card in groups):
        return None
    return groups if sum(card["count"] for card in groups) == count else None


def _outcomes(groups, energy, stars):
    hits = dict.fromkeys(CATEGORIES, 0)
    for card in groups:
        cost = _cost(card)
        if (not isinstance(card.get("id"), str) or not card["id"] or cost is None or cost[0] > energy
                or (cost[1] > 0 and (stars is None or cost[1] > stars))
                or card.get("type") not in ("Attack", "Skill", "Power")):
            continue
        text = _description(card.get("description"))
        if re.search(r"\b(?:Unplayable|Ringing)\b", text, re.IGNORECASE):
            continue
        matches = [name for name, expression in (("block", BLOCK), ("damage", DAMAGE), ("mitigation", MITIGATION))
                   if expression.search(text)]
        if matches:
            hits["any"] += card["count"]
            for name in matches:
                hits[name] += card["count"]
    return hits


def _chance_no_hit(size, useful, draws):
    if draws == 0 or useful == 0:
        return Fraction(1)
    if draws > size - useful:
        return Fraction(0)
    return Fraction(comb(size - useful, draws), comb(size, draws))


def _draw_choices(actions, hand, energy, stars):
    by_index = {card["index"]: card for card in hand if type(card.get("index")) is int}
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or not isinstance(detail := action.get("detail"), dict):
            continue
        description = _description(detail.get("description"))
        kind = action.get("kind")
        if kind == "play_card":
            index = detail.get("card_index")
            card = by_index.get(index, {}) if type(index) is int else {}
            card_id = card.get("id")
            if (not isinstance(card_id, str) or detail.get("card_id") != card_id
                    or (card_id not in FIXED_DRAW_CARDS and not DRAW.fullmatch(description))):
                continue
            cost = _cost(card)
            if cost is None or cost[0] > energy or (cost[1] > 0 and (stars is None or cost[1] > stars)):
                continue
            hand_room = MAX_HAND - len(hand) + 1
        elif kind == "use_potion" and detail.get("potion_id") == "SWIFT_POTION":
            cost = (0, 0)
            hand_room = MAX_HAND - len(hand)
        else:
            continue
        match = DRAW.search(description)
        if match:
            yield choice, min(int(match.group(1) or match.group(2)), max(0, hand_room)), cost


def draw_estimates(snapshot):
    """Return percentages for inspectable fixed draws, never a hidden draw order or chosen action."""
    if not isinstance(snapshot, dict) or snapshot.get("screen") != "combat":
        return {}
    combat, actions = snapshot.get("state"), snapshot.get("actions")
    if not isinstance(combat, dict) or not isinstance(actions, list):
        return {}
    hand, energy, stars = combat.get("hand"), combat.get("energy"), combat.get("stars")
    if (not isinstance(hand, list) or not all(isinstance(card, dict) for card in hand)
            or type(energy) is not int or energy < 0):
        return {}
    if type(stars) is not int or stars < 0:
        stars = None
    sources = list(_draw_choices(actions, hand, energy, stars))
    if not sources:
        return {}
    player = combat.get("player")
    powers = player.get("powers") if isinstance(player, dict) else None
    power_ids = {power["id"] for power in powers
                 if isinstance(power, dict) and isinstance(power.get("id"), str)} if isinstance(powers, list) else set()
    if "NO_DRAW_POWER" in power_ids:
        return {"reason": "No Draw is active. Card and potion effects cannot draw additional cards this turn."}
    if "RINGING_POWER" in power_ids or isinstance(combat.get("ringing"), dict):
        return {"reason": "Ringing can prevent newly drawn cards from being played. Immediate useful-draw odds are unavailable."}

    draw = _pile(combat, "draw_pile")
    if draw is None:
        return {"reason": "The unordered draw pile is incomplete or unavailable."}
    discard = _pile(combat, "discard_pile")
    draw_size, discard_size = combat["draw_pile_count"], combat.get("discard_pile_count", 0)
    choices = {}
    for choice, requested, cost in sources:
        from_draw = min(requested, draw_size)
        if requested > from_draw and discard is None:
            continue
        # The native game only shuffles when the draw pile is empty.
        from_discard = min(requested - from_draw, discard_size) if discard is not None else 0
        after_energy = energy - cost[0]
        after_stars = stars - cost[1] if stars is not None else None
        draws = _outcomes(draw, after_energy, after_stars)
        reshuffle = _outcomes(discard, after_energy, after_stars) if from_discard else {}
        odds = {}
        for name in CATEGORIES:
            misses = _chance_no_hit(draw_size, draws[name], from_draw)
            if from_discard:
                misses *= _chance_no_hit(discard_size, reshuffle[name], from_discard)
            odds[name] = round(float(1 - misses) * 100, 1)
        choices[str(choice)] = {"draws": from_draw + from_discard, "redraw_from_discard": from_discard,
                                "energy_after": after_energy, "at_least_one_pct": odds}
    if not choices:
        return {"reason": "This draw would require a reshuffle, but the complete discard pile is unavailable."}
    return {"basis": "Uniform unordered sampling. Odds describe at least one recognized card affordable with remaining "
                     "resources, if combat continues and the draw resolves normally. Unclassified effects are omitted.",
            "choices": choices}
