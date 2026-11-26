"""Protect local decisions and the compact model-facing representation."""

from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import steam_mod_agent as agent
from steam_mod_prompt import decision_context
from steam_mod_shop import RewardProgress, item_actions, potion_reward_action, shop_exit_action


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


def test_reward_navigation_collects_gold_and_remembers_card_skip():
    gold = {**action("claim_reward", type="gold"), "id": "reward.claim.1"}
    cards = {**action("claim_reward", type="cards"), "id": "reward.claim.0"}
    leave = action("proceed", may_skip=True)
    initial = {"screen": "rewards", "run": {"act": 1, "floor": 2},
               "state": {"rewards": [cards["detail"], gold["detail"]]}, "actions": [cards, gold, leave]}
    after_gold = {**initial, "state": {"rewards": [cards["detail"]]}, "actions": [cards, leave]}
    assert agent._forced_action(initial) == gold
    assert agent._forced_action(after_gold) == cards

    progress = RewardProgress()
    assert progress.available(after_gold, after_gold["actions"]) == [cards, leave]
    picker = {"screen": "card_reward"}
    progress.advance(after_gold, cards, picker)
    progress.advance(picker, action("card_reward_alternative", title="Skip"), after_gold)
    offered = {**after_gold, "actions": progress.available(after_gold, after_gold["actions"])}
    assert agent._forced_action(offered, skipped_rewards=progress.skipped) == leave

    new_room = {**after_gold, "run": {"act": 1, "floor": 3}}
    assert progress.available(new_room, new_room["actions"]) == [cards, leave]
    unknown = {**offered, "state": {"rewards": [{"type": "relic"}]}}
    assert agent._forced_action(unknown, skipped_rewards={"reward.claim.0"}) is None


def test_reward_skip_survives_another_offer_being_taken():
    first = {**action("claim_reward", type="cards", title="First"), "id": "reward.claim.0"}
    second = {**action("claim_reward", type="cards", title="Second"), "id": "reward.claim.1"}
    leave = action("proceed", may_skip=True)
    both = {"screen": "rewards", "run": {"act": 1, "floor": 2},
            "state": {"rewards": [first["detail"], second["detail"]]}, "actions": [first, second, leave]}
    shifted = {**second, "id": "reward.claim.0"}
    one = {**both, "state": {"rewards": [second["detail"]]}, "actions": [shifted, leave]}
    picker = {"screen": "card_reward"}

    progress = RewardProgress()
    progress.available(both, both["actions"])
    progress.advance(both, second, picker)
    progress.advance(picker, action("card_reward_alternative", title="Skip"), both)
    assert progress.available(both, both["actions"]) == [first, leave]
    progress.advance(both, first, picker)
    progress.advance(picker, action("pick_card_reward"), one)
    assert progress.available(one, one["actions"]) == [leave]
    assert progress.skipped == {"reward.claim.0"}


def test_only_unlocked_rest_option_can_run_locally():
    rest = action("choose_rest_option", locked=False, title="Rest")
    site = {"screen": "rest", "actions": [rest]}
    assert agent._forced_action(site) == rest
    assert agent._forced_action({**site, "actions": [action("choose_rest_option", locked=True)]}) is None
    assert agent._forced_action({**site, "actions": [rest, action("proceed")]}) is None


def test_full_potion_belt_keeps_fixed_block_over_temporary_stats():
    hold = [{"id": "REGEN_POTION", "index": 0}, {"id": "BLOCK_POTION", "index": 1},
            {"id": "BLESSING_OF_THE_FORGE", "index": 2}]
    skip = action("proceed", may_skip=True)
    cards = {**action("claim_reward", type="cards"), "id": "claim.cards"}
    drop = action("discard_potion", potion_index=1, potion_id="BLOCK_POTION")
    for potion in ("SPEED_POTION", "FLEX_POTION"):
        claim = action("claim_reward", type="potion", item=potion)
        snapshot = {"screen": "rewards", "state": {"rewards": [claim["detail"], cards["detail"]]},
                    "actions": [claim, cards, skip, drop],
                    "run": {"potions": hold, "potion_capacity": 3,
                            "deck": [{"id": card} for card in
                                     ("DEATHS_DOOR", "NEGATIVE_PULSE", "DEATHBRINGER", "DEFY")]}}
        assert potion_reward_action(snapshot) is None
        offered = {**snapshot, "actions": item_actions(snapshot)}
        assert offered["actions"] == [cards, skip]
        assert agent._forced_action(offered) == cards
        potion_only = {**offered, "state": {"rewards": [claim["detail"]]}, "actions": [skip]}
        assert agent._forced_action(potion_only) == skip


def test_potion_upgrade_discards_only_a_known_weaker_slot_then_claims_reward():
    held = [{"index": 0, "id": "UNKNOWN_POTION"}, {"index": 1, "id": "FLEX_POTION"}]
    claim = action("claim_reward", type="potion", item="BLOCK_POTION")
    drop = action("discard_potion", potion_index=1, potion_id="FLEX_POTION")
    unknown = {**action("discard_potion", potion_index=0, potion_id="UNKNOWN_POTION"), "id": "discard.0"}
    snapshot = {"screen": "rewards", "state": {"rewards": [claim["detail"]]},
                "actions": [claim, unknown, drop], "run": {"potions": held, "potion_capacity": 2}}
    assert potion_reward_action(snapshot) == drop
    snapshot["run"]["potions"] = held[:1]
    snapshot["actions"] = [claim]
    assert potion_reward_action(snapshot) == claim


def test_shop_prioritizes_removal_and_uses_only_spare_gold_to_fill_late_gaps():
    def purchase(card, price):
        return {**action("buy_shop_item", type="card", cost=price, affordable=True, card={"id": card}),
                "id": card}

    removal = action("buy_shop_item", type="card_removal", cost=75, affordable=True)
    leave = action("close_shop")
    solar, hidden = purchase("SOLAR_STRIKE", 24), purchase("HIDDEN_CACHE", 48)
    conversion = purchase("ALIGNMENT", 50)
    snapshot = {"screen": "shop", "state": {"inventory_open": True},
                "run": {"character": "CHARACTER.REGENT", "act": 1, "gold": 109,
                        "deck": [{"id": "STRIKE_REGENT", "count": 4}, {"id": "COLLISION_COURSE"}]},
                "actions": [solar, hidden, removal, leave]}
    assert item_actions(snapshot) == [removal, leave]
    assert agent._forced_action(snapshot) == removal

    # The same gap is eligible once the deck has money to cover both services.
    snapshot["run"].update(act=3, gold=110, deck=[*snapshot["run"]["deck"], {"id": "HIDDEN_CACHE"}])
    snapshot["actions"] = [solar, conversion, removal, leave]
    assert item_actions(snapshot) == [removal, leave]
    snapshot["run"]["gold"] = 150
    assert item_actions(snapshot) == [conversion, removal, leave]
    assert agent._forced_action(snapshot) is None


def test_trap_reward_is_skipped_without_a_model_call():
    trap = action("pick_card_reward", id="PARRY")
    skip = action("card_reward_alternative", title="Skip")
    snapshot = {"screen": "card_reward", "state": {}, "actions": [trap, skip],
                "run": {"character": "CHARACTER.REGENT", "act": 1, "deck": [{"id": "STRIKE_REGENT"}]}}
    assert item_actions(snapshot) == [skip]
    assert agent._forced_action({**snapshot, "actions": [skip]}) == skip
    assert item_actions({**snapshot, "actions": [trap]}) == [trap]


def test_after_closing_inventory_exit_the_shop_without_reopening():
    close = action("close_shop")
    reopen = action("open_shop")
    proceed = action("proceed")
    inside = {"screen": "shop", "state": {"inventory_open": True}, "actions": [close]}
    closing = {"screen": "shop", "state": {"inventory_open": False}, "actions": [reopen]}
    ready = {**closing, "actions": [reopen, proceed]}
    bridge = Mock()
    bridge.tool.side_effect = [inside, closing, ready]
    with patch.object(agent, "sleep"):
        assert agent.read_ready(bridge, after=inside, leaving_shop=True) == ready
    assert shop_exit_action(ready, ["close_shop shop.close"]) == proceed
    assert shop_exit_action(ready, ["select_map_node"]) is None


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
