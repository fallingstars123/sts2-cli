"""Pure tests for the Steam agent's combat tactics (no game process needed).

Cases are taken from archived defeats: the Act 1 Ceremonial Beast fight where turns ended
with energy and Defends in hand, and The Insatiable's Sandpit countdown at floor 33.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

from steam_mod_tactics import combat_tactics, end_turn_guard  # noqa: E402


def card(index, card_id, cost, description, kind="Skill", target="Self", **extra):
    return {"index": index, "id": card_id, "energy_cost": cost, "energy_x": False, "star_cost": -1,
            "star_x": False, "type": kind, "target_type": target, "upgrade": 0, "keywords": [],
            "description": description, **extra}


def play(item, target=None):
    detail = {"card_index": item["index"], "card_id": item["id"], "description": item["description"]}
    if target is not None:
        detail["target_index"] = target
    return {"id": f"play-{item['index']}-{target}", "kind": "play_card", "detail": detail}


def snapshot(hand, enemies, *, hp=77, block=0, energy=2, relics=(), extra_actions=()):
    actions = [play(item, 0 if item["target_type"] == "AnyEnemy" else None) for item in hand]
    actions += list(extra_actions) + [{"id": "end", "kind": "end_turn", "detail": {}}]
    return {"screen": "combat", "actions": actions, "state": {
        "energy": energy, "hand": hand, "enemies": enemies, "draw_pile_count": 5, "discard_pile_count": 3,
        "player": {"hp": hp, "block": block, "powers": [], "relics": [{"id": r} for r in relics]},
    }}


def beast(intents):
    return [{"index": 0, "id": "CEREMONIAL_BEAST", "hp": 160, "block": 0, "powers": [], "intents": intents}]


DEFEND = "Gain 5 [gold]Block[/gold]."


def test_guard_plays_defend_when_turn_would_end_with_energy_and_damage_unblocked():
    hand = [card(0, "DEFEND_IRONCLAD", 1, DEFEND), card(1, "SPOILS_MAP", 0, "Gain 30 Gold."),
            card(2, "DEFEND_IRONCLAD", 1, DEFEND)]
    guard = end_turn_guard(snapshot(hand, beast([{"type": "Attack", "damage": 20, "hits": 1, "total_damage": 20}])))
    assert guard is not None
    assert guard["card_id"] == "DEFEND_IRONCLAD" and guard["block"] == 5
    assert guard["unblocked_before"] == 20 and guard["estimated_hp_saved"] == 5


def test_guard_stays_out_when_nothing_gets_through():
    hand = [card(0, "DEFEND_IRONCLAD", 1, DEFEND)]
    assert end_turn_guard(snapshot(hand, beast([{"type": "Buff"}]))) is None
    hit = beast([{"type": "Attack", "damage": 6, "hits": 1, "total_damage": 6}])
    assert end_turn_guard(snapshot(hand, hit, block=6)) is None


def test_guard_ignores_bound_retain_mixed_and_unaffordable_cards():
    hit = beast([{"type": "Attack", "damage": 20, "hits": 1, "total_damage": 20}])
    bound = card(0, "DEFEND_IRONCLAD", 1, DEFEND + "\n[purple]Bound[/purple]", affliction={"id": "BOUND"})
    retain = card(1, "DEFEND_IRONCLAD", 1, DEFEND, keywords=["Retain"])
    mixed = card(2, "SHRUG_IT_OFF", 1, "Gain 8 Block.\nDraw 1 card.")
    pricey = card(3, "DEFEND_IRONCLAD", 2, DEFEND)
    assert end_turn_guard(snapshot([bound, retain, mixed, pricey], hit, energy=1)) is None


def test_guard_respects_carry_over_relics():
    hit = beast([{"type": "Attack", "damage": 20, "hits": 1, "total_damage": 20}])
    assert end_turn_guard(snapshot([card(0, "DEFEND_IRONCLAD", 1, DEFEND)], hit, relics=("ICE_CREAM",))) is None


def test_guard_prefers_the_bigger_block():
    hit = beast([{"type": "Attack", "damage": 22, "hits": 1, "total_damage": 22}])
    hand = [card(0, "DEFEND_IRONCLAD", 1, DEFEND), card(1, "DEFEND_IRONCLAD", 1, "Gain 8 [gold]Block[/gold].")]
    assert end_turn_guard(snapshot(hand, hit, energy=3))["block"] == 8


SANDPIT = "When [gold]The Insatiable[/gold] takes its turn, you will be eaten and die."


def insatiable(amount, hp=308):
    return [{"index": 0, "id": "THE_INSATIABLE", "hp": hp, "block": 0, "intents": [
        {"type": "Attack", "damage": 16, "hits": 1, "total_damage": 16}],
        "powers": [{"id": "SANDPIT_POWER", "name": "Sandpit", "amount": amount, "display_amount": amount,
                    "description": SANDPIT}]}]


def test_sandpit_countdown_uses_its_stack_and_reports_the_race():
    risks = combat_tactics(snapshot([], insatiable(4), hp=88, energy=3))["forced_defeat_countdowns"]
    assert len(risks) == 1
    risk = risks[0]
    assert risk["turns_remaining"] == 4  # previously always reported as 1
    assert risk["hp_to_remove_before_deadline"] == 308
    assert risk["damage_needed_per_turn"] == 77
    assert risk["kill_target_index"] == 0


def test_sandpit_last_turn_is_imminent():
    risk = combat_tactics(snapshot([], insatiable(1, hp=132), hp=55, energy=3))["forced_defeat_countdowns"][0]
    assert risk["turns_remaining"] == 1 and risk["damage_needed_per_turn"] == 132


def test_unverified_power_with_sandpit_wording_keeps_one_turn_reading():
    power = {"id": "SOME_FUTURE_POWER", "name": "Maw", "amount": 4, "display_amount": 4,
             "description": "When [gold]The Maw[/gold] takes its turn, you will die."}
    enemies = [{"index": 0, "id": "MAW", "hp": 90, "block": 0, "intents": [], "powers": [power]}]
    risk = combat_tactics(snapshot([], enemies))["forced_defeat_countdowns"][0]
    assert risk["turns_remaining"] == 1 and risk["damage_needed_per_turn"] == 90


ENRAGE = {"id": "ENRAGE_POWER", "name": "Enrage", "amount": 2, "display_amount": 2,
          "description": "Whenever you play a Skill, gains [blue]2[/blue] [gold]Strength[/gold]."}


def nob(intents, powers=(ENRAGE,)):
    return [{"index": 0, "id": "GREMLIN_NOB", "hp": 80, "block": 0, "powers": list(powers), "intents": intents}]


def test_guard_stays_out_against_enrage():
    hit = nob([{"type": "Attack", "damage": 14, "hits": 1, "total_damage": 14}])
    assert end_turn_guard(snapshot([card(0, "DEFEND_IRONCLAD", 1, DEFEND)], hit)) is None
    # A dead Enrage enemy no longer punishes Skills.
    dead = nob([], ) + [{"index": 1, "id": "CULTIST", "hp": 40, "block": 0, "powers": [],
                         "intents": [{"type": "Attack", "damage": 14, "hits": 1, "total_damage": 14}]}]
    dead[0]["hp"] = 0
    assert end_turn_guard(snapshot([card(0, "DEFEND_IRONCLAD", 1, DEFEND)], dead)) is not None


def test_block_estimate_counts_enrage_strength_per_hit():
    # 3 hits of 6: a 5-Block Skill adds 2 Strength to each hit, so it saves 5 - 6 = nothing.
    multi = nob([{"type": "Attack", "damage": 6, "hits": 3, "total_damage": 18}])
    summary = combat_tactics(snapshot([card(0, "DEFEND_IRONCLAD", 1, DEFEND)], multi, hp=30, energy=1))
    assert not any(item["kind"] == "block" for item in summary.get("choices_before_end_turn", []))
    # One hit of 14: 5 Block against +2 damage still saves 3, and the cost is reported.
    single = nob([{"type": "Attack", "damage": 14, "hits": 1, "total_damage": 14}])
    summary = combat_tactics(snapshot([card(0, "DEFEND_IRONCLAD", 1, DEFEND)], single, hp=30, energy=1))
    block = next(item for item in summary["choices_before_end_turn"] if item["kind"] == "block")
    assert block["estimated_hp_saved"] == 3 and block["enemy_damage_gain_from_enrage"] == 2


def test_numbered_countdown_text_still_wins_over_stack():
    power = {"id": "DOOM_CLOCK", "name": "Clock", "amount": 9, "description": "In 2 turns, you die."}
    enemies = [{"index": 0, "id": "X", "hp": 50, "block": 5, "intents": [], "powers": [power]}]
    risk = combat_tactics(snapshot([], enemies))["forced_defeat_countdowns"][0]
    assert risk["turns_remaining"] == 2 and risk["damage_needed_per_turn"] == 28
