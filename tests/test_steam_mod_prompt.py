"""Protect local decisions and the compact model-facing representation."""

from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import steam_mod_agent as agent
from steam_mod_prompt import decision_context


def action(kind, **detail):
    return {"kind": kind, "id": f"native.{kind}", "detail": detail}


def test_local_path_requires_one_safe_choice():
    proceed = action("proceed", may_skip=False)
    snapshot = {"screen": "rewards", "state": {"rewards": []}, "actions": [proceed]}
    assert agent._forced_action(snapshot) == proceed
    assert agent._forced_action({**snapshot, "actions": [action("proceed", may_skip=True)]}) is None
    assert agent._forced_action({**snapshot, "state": {"rewards": [{"type": "cards"}]}}) is None
    map_choice = action("select_map_node", col=2, row=5)
    assert agent._forced_action({"screen": "map", "actions": [map_choice]}) == map_choice
    assert agent._forced_action({"screen": "map", "actions": [map_choice, action("select_map_node", col=3)]}) is None
    assert agent._forced_action({"screen": "combat", "actions": [action("end_turn")]}) is None
    assert agent._forced_action({"screen": "card_selection", "actions": [action("confirm_card_choice")]}) is None


def test_compact_combat_keeps_target_specific_text_and_unordered_piles():
    strike = {"index": 3, "id": "STRIKE_SILENT", "name": "Strike", "description": "Deal 6 damage."}
    deck = [{"id": "STRIKE_SILENT", "count": 4}]
    combat = {
        "screen": "combat",
        "state": {
            "hand": [strike],
            "draw_pile": [{"id": "STRIKE_SILENT", "name": "Strike", "count": 2, "description": strike["description"]}],
            "discard_pile": [{"id": "STRIKE_SILENT", "name": "Strike", "count": 1, "description": strike["description"]}],
            "enemies": [{"index": 2, "name": "Beetle"}, {"index": 4, "name": "Beetle"}],
        },
        "run": {"deck": deck, "seed": "PRIVATE"},
        "actions": [
            action("play_card", card_index=3, card_id=strike["id"], card="Strike", target_index=2,
                   target="Beetle", description=strike["description"]),
            action("play_card", card_index=3, card_id=strike["id"], card="Strike", target_index=4,
                   target="Beetle", description="Deal 9 damage to this enemy."),
        ],
    }
    original = deepcopy(combat)
    context = decision_context(combat, include_deck=False)
    assert combat == original
    assert "seed" not in context["run"] and "deck" not in context["run"]
    assert decision_context(combat, include_deck=True)["run"]["deck"] == deck
    assert [row["choice"] for row in context["actions"]] == [1, 2]
    assert context["actions"][0]["detail"] == {"card_index": 3, "target_index": 2}
    assert context["actions"][1]["detail"] == {
        "card_index": 3, "target_index": 4, "description": "Deal 9 damage to this enemy.",
    }
    state = context["state"]
    assert state["card_text"] == {"Strike": "Deal 6 damage."}
    assert state["hand"][0]["name"] == "Strike" and "description" not in state["hand"][0]
    assert state["draw_pile"] == ["Strike x2"] and state["discard_pile"] == ["Strike"]


def test_reward_choice_references_visible_card_and_preserves_skip():
    card = {"id": "HEADBUTT", "title": "Headbutt", "description": "Deal 9 damage."}
    snapshot = {
        "screen": "card_reward", "run": {},
        "state": {"cards": [card]},
        "actions": [action("pick_card_reward", **card), action("card_reward_alternative", title="Skip")],
    }
    compact = decision_context(snapshot, include_deck=True)
    assert compact["state"]["cards"] == [card]
    assert [row["detail"] for row in compact["actions"]] == [{"card_option_index": 0}, {"title": "Skip"}]


def test_local_choice_uses_native_validation_without_provider(tmp_path):
    open_box = action("open_chest")
    before = {"screen": "treasure", "state_id": "s:1:a", "state": {"opened": False},
              "run": {"profile": 2, "floor": 9, "act": 1}, "actions": [open_box]}
    done = {**before, "screen": "settlement", "state": {"outcome": "victory", "native_history": True},
            "actions": []}
    options = SimpleNamespace(profile=2, checkpoint="run", journal_dir=tmp_path / "journal",
                              archive_dir=tmp_path / "archive", max_actions=1, from_room=False)
    mcp = Mock()
    mcp.tool.return_value = {"accepted": True}
    memo = Mock(identity=None)
    memo.context.return_value = {}
    with patch.object(agent, "read_ready", side_effect=[before, done]), patch.object(
        agent, "SteamModMemory", return_value=memo
    ), patch.object(agent, "choose") as choose:
        assert agent.play(mcp, None, options) == 0
    choose.assert_not_called()
    mcp.tool.assert_called_once_with("perform_action", state_id=before["state_id"], action_id=open_box["id"])
