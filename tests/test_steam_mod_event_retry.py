"""Event checkpoint helpers in the Steam agent, with snapshots shaped like Sts2LiveBridge output."""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

import steam_mod_agent as agent  # noqa: E402

RUN = {"profile": 3, "seed": "SEED", "character": "CHARACTER.SILENT", "act": 2, "floor": 22,
       "room_event_id": "SLIPPERY_BRIDGE", "event_retry_count": 0, "hp": 50, "max_hp": 70, "gold": 100}
IDENTITY = SimpleNamespace(profile=3, seed="SEED", character="CHARACTER.SILENT", start_time=1795404849)


def event(resolved, *, retry_count=0, options=(), actions=()):
    return {"screen": "event", "run": {**RUN, "event_retry_count": retry_count},
            "state": {"event_id": "SLIPPERY_BRIDGE", "resolved": resolved, "options": list(options)},
            "actions": list(actions)}


PROCEED = {"id": "event.choose.0", "kind": "choose_event_option", "detail": {"title": "Proceed", "proceed": True}}
RETRY = {"id": "retry_current_event", "kind": "retry_current_event", "detail": {"event_id": "SLIPPERY_BRIDGE"}}
OPTION = {"id": "event.choose.1", "kind": "choose_event_option", "detail": {"title": "Hold On", "proceed": False}}


def test_event_room_reads_the_bridge_run_context_on_any_event_screen():
    room = agent._event_room(event(True))
    assert room == (3, "SEED", "CHARACTER.SILENT", 2, 22, "SLIPPERY_BRIDGE")
    reward = {"screen": "card_reward", "run": RUN, "state": {}, "actions": []}
    assert agent._event_room(reward) == room


def test_retry_marker_needs_a_resolved_event_and_an_unused_retry(tmp_path):
    resolved = event(True, actions=[PROCEED, RETRY])
    assert agent._event_retry_marker(resolved, IDENTITY, tmp_path) is not None
    assert agent._event_retry_marker(event(False, actions=[OPTION, RETRY]), IDENTITY, tmp_path) is None
    assert agent._event_retry_marker(event(True, retry_count=1, actions=[PROCEED, RETRY]), IDENTITY, tmp_path) is None
    assert agent._event_retry_marker(resolved, None, tmp_path) is None


def test_same_retried_event_confirms_a_fresh_unresolved_event():
    before = event(True, actions=[PROCEED, RETRY])
    after = event(False, retry_count=1, actions=[OPTION])
    assert agent._same_retried_event(before, after)
    assert not agent._same_retried_event(before, event(False, retry_count=0, actions=[OPTION]))
    assert not agent._same_retried_event(before, event(True, retry_count=1, actions=[PROCEED]))


def test_event_outcome_records_the_choice_and_resource_changes():
    before = event(False, actions=[OPTION])
    after = {**event(True), "run": {**RUN, "hp": 44, "gold": 130}}
    note = agent._event_outcome(before, {**OPTION, "detail": {**OPTION["detail"], "description": "Lose 6 HP."}}, after)
    assert note == {"choice": "Hold On", "effect": "Lose 6 HP.", "hp_change": -6, "gold_change": 30}


def test_enchantment_review_distinguishes_generated_shivs_from_direct_damage():
    card = {"id": "LEADING_STRIKE", "title": "Leading Strike",
            "description": "Deal 3 damage.\nAdd 2 [gold]Shivs[/gold] into your [gold]Hand[/gold]."}
    enchanted = {**card, "description": card["description"].replace("3", "[green]4[/green]", 1)
                 + "\n[purple]Lose 2 HP.[/purple]"}
    state = {
        "screen": "card_selection",
        "run": {**RUN, "deck": [{"id": "LEADING_STRIKE", "count": 2}, {"id": "STORM_OF_STEEL"}]},
        "state": {"mode": "NDeckEnchantSelectScreen", "preview": [card, enchanted]},
        "actions": [
            {"id": "confirm", "kind": "confirm_card_choice", "detail": {}},
            {"id": "undo", "kind": "undo_or_cancel_card_choice", "detail": {}},
        ],
    }

    def request(_client, _instructions, data, high_risk, **_stable):
        context = json.loads(data)
        assert high_risk
        assert any("multiple ways to produce Shivs" in tip for tip in context["community_guidance"])
        assert context["archetype_assessment"]["archetypes"][0]["name"] == "Shivs"
        assert context["enchantment_changes"] == {
            "card": "Leading Strike",
            "removed_text": ["Deal 3 damage."],
            "added_text": ["Deal 4 damage.", "Lose 2 HP."],
            "unchanged_text": ["Add 2 Shivs into your Hand."],
        }
        message = SimpleNamespace(content='{"choice":2}')
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=message)], usage=None)

    with patch.object(agent, "request_choice", side_effect=request):
        chosen, _, _ = agent.choose(None, state, [], "")
    assert chosen == "undo"


def test_retry_failure_only_stops_the_caller_awaiting_that_retry():
    error = "The native checkpoint changed before Continue."
    state = {**event(True, actions=[PROCEED]), "retry_failure": error}
    mcp = SimpleNamespace(tool=lambda _method: state)
    assert agent.read_ready(mcp) == state
    try:
        agent.read_ready(mcp, awaiting_retry=True)
    except agent.SessionError as failure:
        assert str(failure) == error
    else:
        raise AssertionError("The waiting caller did not receive the retry failure")
