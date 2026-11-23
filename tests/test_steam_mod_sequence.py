"""Verify that cached combat choices stop at effects that need a new decision."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import steam_mod_agent as agent
from steam_mod_sequence import MAX_CHOICES, CombatSequence, can_plan


def card(key, description="Gain 5 Block.", *, cost=1, stars=-1, x_cost=False):
    return {"id": key, "instance_id": f"card:{key}", "description": description, "energy_cost": cost,
            "energy_x": x_cost, "star_cost": stars, "star_x": False, "upgrade": 0, "target_type": "Self"}


def snapshot(cards, *, energy=3, stars=0, revision=5, discard=0, draw=3, intent="Attack", enemy_hp=20):
    hand = [{**item, "index": position, "energy_cost": energy if item["energy_x"] else item["energy_cost"]}
            for position, item in enumerate(cards)]
    actions = [{"id": f"play:{item['index']}", "kind": "play_card",
                "detail": {"card_index": item["index"], "card_id": item["id"],
                           "card_instance_id": item["instance_id"], "description": item["description"]}}
               for item in hand]
    return {
        "screen": "combat", "state_id": f"session:{revision}:snapshot",
        "run": {"profile": 2, "seed": "FIXTURE", "character": "CHARACTER.DEFECT", "act": 1, "floor": 4},
        "state": {
            "phase": "Play", "energy": energy, "stars": stars, "encounter": "TEST",
            "turn": 1, "round": 1, "hand": hand, "player": {"hp": 50, "max_hp": 75},
            "enemies": [{"index": 0, "instance_id": "enemy:1", "id": "TEST", "hp": enemy_hp,
                         "intents": [{"type": intent, "hits": 1}]}],
            "draw_pile_count": draw, "discard_pile_count": discard, "exhaust_pile_count": 0,
            "draw_pile": [{"id": "PILE_CARD", "upgrade": 0, "count": draw}],
            "potions": [],
        },
        "actions": actions,
    }


def test_draw_or_selection_can_end_a_plan_and_cannot_extend_it():
    first = card("BLOCK")
    last = card("FREE", cost=0)
    for description in ("Draw 2 cards.", "Deal 5 damage to a random enemy.",
                        "Discard 1 card.", "抽2张牌。"):
        draw = card("EFFECT", description)
        before = snapshot([first, draw, last])
        after = snapshot([draw, last], energy=2, revision=6, discard=1)
        assert can_plan(snapshot([first, draw]))
        plan = CombatSequence()
        assert plan.offer(before, 1, [1, 2, 3]) == 1
        plan.advance(before, before["actions"][0], after)
        assert plan.take(after) == 1
        assert not plan.has_pending
        assert plan.offer(before, 2, [2, 1]) == 0


def test_sequence_checks_combined_energy_and_stars():
    costly = snapshot([card("A", cost=2), card("B", cost=2)], energy=3)
    star_costs = snapshot([card("A", stars=2), card("B", stars=2)], stars=3)
    for state in (costly, star_costs):
        assert not can_plan(state)
        assert CombatSequence().offer(state, 1, [1, 2]) == 0


def test_cached_x_cost_requires_the_planned_remaining_energy():
    first = card("BLOCK")
    x = card("X", "Gain X Block.", x_cost=True)
    before = snapshot([first, x])
    for energy, expected in ((2, 1), (3, None), (1, None)):
        after = snapshot([x], energy=energy, revision=6, discard=1)
        plan = CombatSequence()
        assert plan.offer(before, 1, [1, 2]) == 1
        plan.advance(before, before["actions"][0], after)
        assert plan.take(after) == expected


def test_new_draw_or_enemy_change_cancels_cached_follow_up():
    first, second = card("FIRST"), card("SECOND")
    before = snapshot([first, second])
    for override in ({"draw": 2}, {"enemy_hp": 0}, {"intent": "Debuff"}):
        after = snapshot([second], energy=2, revision=6, discard=1, **override)
        plan = CombatSequence()
        assert plan.offer(before, 1, [1, 2]) == 1
        plan.advance(before, before["actions"][0], after)
        assert plan.take(after) is None


def test_sequence_is_bounded_and_matches_shifted_native_card_indices():
    cards = [card(str(index), cost=0) for index in range(MAX_CHOICES + 1)]
    before = snapshot(cards)
    plan = CombatSequence()
    assert plan.offer(before, 1, list(range(1, len(cards) + 1))) == MAX_CHOICES - 1
    after = snapshot([cards[2], cards[1], *cards[3:]], revision=6, discard=1)
    plan.advance(before, before["actions"][0], after)
    assert plan.take(after) == 2



def test_agent_reuses_the_final_draw_without_a_second_model_request():
    block, draw = card("BLOCK"), card("DRAW", "Draw 2 cards.")
    before = snapshot([block, draw], energy=2)
    after = snapshot([draw], energy=1, revision=6, discard=1)
    plan = CombatSequence()
    reply = SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content='{"choice":1,"sequence":[1,2]}'),
    )], usage=None)
    with patch.object(agent, "request_choice", return_value=reply) as request:
        chosen, _, usage = agent.choose(None, before, [], "", allow_review=False, turn_sequence=plan)
        assert chosen == before["actions"][0]["id"]
        assert usage["turn_plan_queued"] == 1
        plan.advance(before, before["actions"][0], after)
        chosen, _, usage = agent.choose(None, after, [], "", allow_review=False, turn_sequence=plan)
    assert chosen == after["actions"][0]["id"]
    assert usage["reused_turn_plan"] == 1
    request.assert_called_once()
