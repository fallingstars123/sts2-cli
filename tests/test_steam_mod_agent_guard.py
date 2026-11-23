"""The Steam agent's choose(): end-turn guard and per-hazard recheck gating, with a fake model."""
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

import steam_mod_agent as agent  # noqa: E402

DEFEND = "Gain 5 [gold]Block[/gold]."


class FakeModel:
    """Answers every request with a fixed choice and records whether reasoning was requested."""

    def __init__(self, choice):
        self.choice, self.calls = choice, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.calls.append(request)
        message = SimpleNamespace(content=json.dumps({"choice": self.choice}))
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=message)], usage=None)


def asked(call):
    """All prompt text of one request; a recheck is the last user turn."""
    return " ".join(message["content"] for message in call["messages"])


def state(hand, *, energy=2, incoming=20, hp=77):
    actions = [{"id": f"card-{c['index']}", "kind": "play_card",
                "detail": {"card_index": c["index"], "card_id": c["id"], "description": c["description"]}} for c in hand]
    actions.append({"id": "end", "kind": "end_turn", "detail": {}})
    return {
        "state_id": "s:5:x", "screen": "combat", "actions": actions,
        "run": {"act": 1, "floor": 17, "hp": hp, "max_hp": 90, "character": "CHARACTER.IRONCLAD"},
        "state": {"turn": 3, "phase": "Play", "encounter": "CEREMONIAL_BEAST_BOSS", "energy": energy, "stars": 0,
                  "hand": hand, "draw_pile_count": 4, "discard_pile_count": 3, "exhaust_pile_count": 0,
                  "player": {"hp": hp, "max_hp": 90, "block": 0, "powers": [], "relics": []},
                  "enemies": [{"index": 0, "id": "CEREMONIAL_BEAST", "hp": 136, "block": 0, "powers": [],
                               "intents": [{"type": "Attack", "damage": incoming, "hits": 1,
                                            "total_damage": incoming}]}]},
    }


def defend(index, text=DEFEND):
    return {"index": index, "id": "DEFEND_IRONCLAD", "energy_cost": 1, "energy_x": False, "star_cost": -1,
            "star_x": False, "type": "Skill", "target_type": "Self", "upgrade": 0, "keywords": [], "description": text}


def test_end_turn_with_unused_defend_is_replaced_by_the_defend():
    snapshot = state([defend(0), defend(1)])
    model = FakeModel(choice=3)  # end turn
    action_id, _, usage = agent.choose(model, snapshot, [], "", {})
    assert action_id == "card-0"
    assert usage["end_turn_guard"]["block"] == 5


def test_recheck_requests_reasoning():
    snapshot = state([defend(0), defend(1)])
    model = FakeModel(choice=3)
    agent.choose(model, snapshot, [], "", {})
    rechecks = [call for call in model.calls if "Your initial choice" in asked(call)]
    assert rechecks, "ending the turn into 20 unblocked damage should trigger a recheck"
    assert all(call["extra_body"]["thinking"]["type"] == "enabled" for call in rechecks)


def test_end_turn_recheck_still_runs_after_a_defense_recheck_this_turn():
    snapshot = state([defend(0), defend(1)])
    model = FakeModel(choice=3)
    agent.choose(model, snapshot, [], "", {}, reviewed_hazards=frozenset({"rechecked_defense"}))
    assert any("Your initial choice 3" in asked(call) for call in model.calls)


def test_end_turn_recheck_runs_once_per_turn():
    snapshot = state([defend(0), defend(1)])
    model = FakeModel(choice=3)
    agent.choose(model, snapshot, [], "", {}, reviewed_hazards=frozenset({"rechecked_end_turn"}))
    assert not any("Your initial choice" in asked(call) for call in model.calls)


def test_no_guard_when_block_already_covers_the_hit():
    snapshot = state([defend(0)], incoming=0)
    model = FakeModel(choice=2)
    action_id, _, usage = agent.choose(model, snapshot, [], "", {})
    assert action_id == "end" and "end_turn_guard" not in usage
