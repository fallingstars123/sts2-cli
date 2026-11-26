"""End-of-turn damage from cards in hand (Toxic, Burn) and the low-HP rest recheck."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import steam_mod_agent as agent
from steam_mod_tactics import combat_tactics, end_turn_guard

TOXIC = "At the end of your turn, if this is in your [gold]Hand[/gold], take 5 damage.\n[gold]Exhaust[/gold]."
TOXIC_ZH = "在你的回合结束时，如果这张牌在你的[gold]手牌[/gold]中，你受到5点伤害。"


def card(index, key, description, *, kind="Skill", cost=1):
    return {"index": index, "id": key, "name": key.title(), "description": description, "energy_cost": cost,
            "energy_x": False, "star_cost": -1, "star_x": False, "type": kind, "target_type": "Self",
            "upgrade": 0, "keywords": []}


def fight(hand, *, block=14, attack=13, energy=3, hp=41):
    actions = [{"id": f"card-{c['index']}", "kind": "play_card",
                "detail": {"card_index": c["index"], "card_id": c["id"], "description": c["description"]}}
               for c in hand]
    actions.append({"id": "end", "kind": "end_turn", "detail": {}})
    return {"screen": "combat", "state_id": "s:3:x", "actions": actions,
            "run": {"act": 2, "floor": 30, "hp": hp, "max_hp": 80},
            "state": {"turn": 2, "phase": "Play", "encounter": "MYTES_NORMAL", "energy": energy, "stars": 0,
                      "hand": hand, "draw_pile_count": 5, "discard_pile_count": 3, "exhaust_pile_count": 0,
                      "player": {"hp": hp, "max_hp": 80, "block": block, "powers": [], "relics": []},
                      "enemies": [{"index": 0, "id": "MYTE", "hp": 64, "block": 0, "powers": [],
                                   "intents": [{"type": "Attack", "damage": attack, "hits": 1,
                                                "total_damage": attack}]}]}}


def test_toxic_in_hand_counts_as_damage_that_block_must_cover():
    # Mytes turn 2 of the lost Regent run: 14 Block, a 13 attack and two Toxics lost 9 HP.
    state = fight([card(0, "TOXIC", TOXIC, kind="Status"), card(1, "TOXIC", TOXIC_ZH, kind="Status")])
    tactics = combat_tactics(state)
    assert tactics["end_of_turn_hand_damage"] == 10 and tactics["unblocked_now"] == 9
    assert [item["choice"] for item in tactics["hand_damage_choices"]] == [1, 2]
    assert combat_tactics(fight([]))["unblocked_now"] == 0


def test_the_guard_plays_toxic_or_the_better_block_before_ending_the_turn():
    toxic_only = fight([card(0, "TOXIC", TOXIC, kind="Status")], block=14, attack=13)
    guard = end_turn_guard(toxic_only)
    assert guard["card_id"] == "TOXIC" and guard["removes_hand_damage"] == 5 and guard["estimated_hp_saved"] == 4
    both = fight([card(0, "TOXIC", TOXIC, kind="Status"), card(1, "TOXIC", TOXIC, kind="Status"),
                  card(2, "ULTIMATE_DEFEND", "Gain 11 [gold]Block[/gold].")], block=14, attack=13)
    assert end_turn_guard(both)["card_id"] == "ULTIMATE_DEFEND"          # saves all 9
    assert end_turn_guard(fight([card(0, "TOXIC", TOXIC, kind="Status")], energy=0)) is None


def test_beckon_loses_hp_through_block_and_is_a_playable_defense():
    beckon = card(0, "BECKON", "At the end of your turn, if this is in your [gold]Hand[/gold],\n lose 6 HP.",
                  kind="Status")
    defend = card(1, "DEFEND_REGENT", "Gain 5 Block.")
    state = fight([beckon, defend], block=20, attack=12, energy=1)
    tactics = combat_tactics(state)
    assert tactics["unblocked_now"] == tactics["end_of_turn_hand_hp_loss_ignoring_block"] == 6
    assert tactics["known_defense_line"]["choices"] == [1]
    assert tactics["known_defense_line"]["hp_loss"] == 0
    assert end_turn_guard(state)["card_id"] == "BECKON"

    state = fight([beckon, defend], block=0, attack=12, energy=1)
    tactics = combat_tactics(state)
    assert tactics["unblocked_now"] == 18
    assert tactics["known_defense_line"]["choices"] == [1]
    assert tactics["known_defense_line"]["hp_loss"] == 12

    state["actions"].pop(0)  # The status cannot be played in this state.
    state["state"]["player"]["block"] = 12
    assert end_turn_guard(state) is None
    assert "known_defense_line" not in combat_tactics(state)


def map_state(hp, *, rest=True):
    nodes = [{"id": "shop", "kind": "select_map_node", "detail": {"col": 5, "row": 11, "type": "Shop"}}]
    if rest:
        nodes.append({"id": "rest", "kind": "select_map_node", "detail": {"col": 4, "row": 11, "type": "RestSite"}})
    return {"screen": "map", "state_id": "s:1:m", "state": {}, "actions": nodes,
            "run": {"act": 2, "floor": 28, "hp": hp, "max_hp": 80, "gold": 371}}


def test_skipping_a_rest_at_low_hp_is_rechecked_once():
    assert agent._skips_rest_at_low_hp(map_state(45), map_state(45)["actions"][0])
    assert not agent._skips_rest_at_low_hp(map_state(60), map_state(60)["actions"][0])
    assert not agent._skips_rest_at_low_hp(map_state(45, rest=False), map_state(45)["actions"][0])
    assert not agent._skips_rest_at_low_hp(map_state(45), map_state(45)["actions"][1])

    calls = []

    def request(_client, _instructions, _data, high_risk, followup=None, **_stable):
        calls.append(followup)
        choice = 2 if followup else 1
        message = SimpleNamespace(content=json.dumps({"choice": choice}))
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=message)], usage=None)

    original = agent.request_choice
    agent.request_choice = request
    try:
        chosen, _, usage = agent.choose(None, map_state(45), [], "", {})
        assert chosen == "rest" and usage["rechecked_rest"] == 1
        assert "skips a reachable rest site (choice 2) at 45/80 HP" in calls[1][1]
        calls.clear()
        chosen, _, _ = agent.choose(None, map_state(45), [], "", {}, reviewed_hazards=frozenset({"rechecked_rest"}))
        assert chosen == "shop" and calls == [None]
    finally:
        agent.request_choice = original
