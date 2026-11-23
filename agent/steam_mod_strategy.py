"""Assess the owned deck and select relevant Steam strategy advice."""

from collections import Counter
from functools import lru_cache
import json
from math import comb
from pathlib import Path


PLAYBOOK = Path(__file__).with_name("steam_mod_strategy.json")
MAX_TIPS = 4
SAMPLE_CARDS = 5
ALIASES = {"THE_FOOL": "FOOL", "THE_SILENT": "SILENT", "THE_DEFECT": "DEFECT",
           "THE_IRONCLAD": "IRONCLAD", "THE_REGENT": "REGENT", "THE_NECROBINDER": "NECROBINDER"}


@lru_cache(maxsize=1)
def _playbook():
    try:
        book = json.loads(PLAYBOOK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return book if isinstance(book, dict) else {}


def _model_id(value):
    return value.rsplit(".", 1)[-1].strip().replace(" ", "_").upper() if isinstance(value, str) else ""


def _character_entry(section, run, state):
    character = _model_id(run.get("character") or state.get("character"))
    data = _playbook().get(section)
    return data.get(ALIASES.get(character, character)) if isinstance(data, dict) else None


def _card_ids(items):
    if not isinstance(items, list):
        return set()
    return {_model_id(item.get("id")) for item in items
            if isinstance(item, dict) and item.get("id") and item.get("count", 1) != 0}


def _owned_counts(cards):
    if not isinstance(cards, list):
        return {}
    counts = Counter()
    for card in cards:
        if not isinstance(card, dict):
            return {}
        identifier = _model_id(card.get("id"))
        count = card.get("count", 1)
        if not identifier or type(count) is not int or count < 0:
            return {}
        if count:
            counts[identifier] += count
    return counts


def _sample_odds(deck_size, sample_size, enablers, payoffs):
    total = comb(deck_size, sample_size)
    no_enabler = comb(deck_size - enablers.total(), sample_size)
    no_payoff = comb(deck_size - payoffs.total(), sample_size)
    # A card may supply both roles. Union counts that copy once.
    no_components = comb(deck_size - (enablers | payoffs).total(), sample_size)
    return {
        "enabler": round(100 * (total - no_enabler) / total, 1),
        "payoff": round(100 * (total - no_payoff) / total, 1),
        "both_roles": round(100 * (total - no_enabler - no_payoff + no_components) / total, 1),
    }


def archetype_assessment(snapshot):
    """Report owned archetype evidence and reference draw odds without replacement."""
    run, state = snapshot.get("run") or {}, snapshot.get("state") or {}
    definitions = _character_entry("archetypes", run, state)
    deck = _owned_counts(run.get("deck"))
    if not isinstance(definitions, dict) or not definitions or not deck:
        return {}

    deck_size = sum(deck.values())
    sample_size = min(SAMPLE_CARDS, deck_size)
    tiers = {"limited": 0, "emerging": 1, "supported": 2}
    candidates = []
    for name, definition in definitions.items():
        enablers = Counter({card: deck[card] for card in definition["enablers"] if card in deck})
        payoffs = Counter({card: deck[card] for card in definition["payoffs"] if card in deck})
        distinct = len(enablers | payoffs)
        if not distinct:
            continue
        missing = [role for role, cards in (("enablers", enablers), ("payoffs", payoffs)) if not cards]
        if distinct >= 3 and not missing:
            evidence = "supported"
        elif distinct >= 2:
            evidence = "emerging"
        else:
            evidence = "limited"
        odds = _sample_odds(deck_size, sample_size, enablers, payoffs)
        candidate = {"name": name, "evidence": evidence,
                     "owned_enablers": dict(enablers), "owned_payoffs": dict(payoffs),
                     "missing_roles": missing, "sample_probability_pct": odds}
        candidates.append((tiers[evidence], distinct, odds["both_roles"], candidate))

    candidates.sort(key=lambda row: row[:3], reverse=True)
    return {"deck_size": deck_size, "uniform_sample_size": sample_size,
            "archetypes": [candidate for _, _, _, candidate in candidates]}


def _available_cards(snapshot, state):
    ids = _card_ids(state.get("hand")) | _card_ids(state.get("cards"))
    for action in snapshot.get("actions") or []:
        if not isinstance(action, dict):
            continue
        detail = action.get("detail", {})
        if not isinstance(detail, dict):
            continue
        if isinstance(card := detail.get("card"), dict):
            ids.add(_model_id(card.get("id")))
        if detail.get("card_id"):
            ids.add(_model_id(detail["card_id"]))
    return ids


def card_pick_advice(snapshot):
    """Match named recommendations to legal offers and keep guidance for other card choices."""
    screen = snapshot.get("screen")
    if screen not in {"card_reward", "shop"}:
        return {}
    run, state = snapshot.get("run") or {}, snapshot.get("state") or {}
    guide = _character_entry("card_recommendations", run, state)
    if not guide:
        return {}

    offers = []
    for choice, action in enumerate(snapshot.get("actions") or [], 1):
        kind, detail = action["kind"], action["detail"]
        if screen == "card_reward" and kind == "pick_card_reward":
            card = detail.get("card", detail)
        elif (screen == "shop" and kind == "buy_shop_item"
              and detail.get("type") == "card" and detail.get("affordable") is not False):
            card = detail.get("card")
        else:
            continue
        if isinstance(card, dict) and (card_id := _model_id(card.get("id"))):
            offers.append((choice, card_id))
    if not offers:
        return {}

    owned = _owned_counts(run.get("deck"))
    known_cards = set(owned) | {card_id for _, card_id in offers}
    named = {card_id: (row["priority"], row["when"]) for row in guide["named"] for card_id in row["cards"]}
    examples = {card_id: row["role"] for row in guide["functional_examples"] for card_id in row["cards"]}
    result = {"build_directions": [
        {"name": row["name"], "seek": row["seek"]}
        for row in guide["build_directions"] if not row.get("anchors") or known_cards.intersection(row["anchors"])
    ]}
    named_picks, role_matches = [], []
    for choice, card_id in offers:
        offer = {"choice": choice, "card_id": card_id}
        if owned:
            offer["owned_copies"] = owned.get(card_id, 0)
        if card_id in named:
            priority, when = named[card_id]
            named_picks.append({**offer, "priority": priority, "when": when})
        if card_id in examples:
            role_matches.append({**offer, "role": examples[card_id]})
    if named_picks:
        result["named_picks"] = named_picks
    if role_matches:
        result["role_matches"] = role_matches
    return result


def community_guidance(snapshot):
    """Use the character, current screen, verified deck, and shown options only."""
    run, state = snapshot.get("run") or {}, snapshot.get("state") or {}
    profile = _character_entry("profiles", run, state)
    if not isinstance(profile, dict):
        return []
    screen = snapshot.get("screen")
    deck = _card_ids(run.get("deck"))
    visible = _available_cards(snapshot, state)
    relevant_cards = visible if screen == "combat" else deck | visible
    act = run.get("act")
    specific, general = [], []
    archetypes = _character_entry("archetypes", run, state) or {}
    for rule in profile["rules"]:
        if screen not in rule["screens"]:
            continue
        limit = rule.get("through_act")
        if limit is not None and (type(act) is not int or act > limit):
            continue
        anchors = rule.get("deck_any", [])
        if archetype := rule.get("archetype_enablers"):
            anchors = archetypes.get(archetype, {}).get("enablers", [])
            if not anchors:
                continue
        offers = rule.get("seen_any", [])
        if anchors and len(deck.intersection(anchors)) < rule.get("min_deck_matches", 1):
            continue
        if offers and relevant_cards.isdisjoint(offers):
            continue
        if anchors or offers:
            relevant = set(anchors) | set(offers)
            specific.append((len(visible & relevant), len(deck & relevant), rule["tip"]))
        else:
            general.append(rule["tip"])
    specific.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return (general[:1] + [row[2] for row in specific] + general[1:])[:MAX_TIPS]
