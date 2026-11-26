"""Token-saving request layout: cached stable prefixes, compact text, and validated local decisions."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import steam_mod_agent as agent
from steam_mod_prompt import FightReference, decision_context, plain_text
from steam_mod_sequence import CombatSequence
from steam_mod_token_replay import CacheModel, FakeAnthropic
from test_steam_mod_sequence import card, snapshot

STAR = "[img]res://images/packed/sprite_fonts/star_icon.png[/img]"
ENERGY = "[img]res://images/packed/sprite_fonts/regent_energy_icon.png[/img]"


def test_plain_text_keeps_values_and_counts_icons():
    assert plain_text(f"Gain {STAR}{STAR}{STAR}.") == "Gain 3 Stars."
    assert plain_text(f"Gain {ENERGY}. Deal 4 damage for each {STAR} gained.") == (
        "Gain Energy. Deal 4 damage for each Star gained.")
    assert plain_text("Gain [blue]12[/blue] [gold]Block[/gold].") == "Gain 12 Block."
    assert plain_text("Deal [green]9[/green] damage.") == "Deal 9 damage."


def combat(hand, *, encounter="TEST", floor=4, relic_text="Gain 6 Block if you end without Block."):
    state = snapshot(hand)
    state["run"] = {**state["run"], "floor": floor}
    state["state"] = {**state["state"], "encounter": encounter,
                      "player": {**state["state"]["player"],
                                 "relics": [{"id": "ORICHALCUM", "name": "Orichalcum", "description": relic_text}]}}
    for item in state["state"]["hand"]:
        item["name"] = item["id"].title()
    return state


def split(reference, state):
    context = decision_context(state, include_deck=False)
    return reference.split(state, context), context["state"]


def test_fight_reference_is_frozen_for_the_fight_and_live_text_still_reaches_the_model():
    reference = FightReference()
    first = combat([card("STRIKE", "Deal 6 damage.")])
    text, state = split(reference, first)
    assert "Deal 6 damage." in text and "Orichalcum" in text
    assert "card_text" not in state and "description" not in state["hand"][0]

    # Same fight: a changed description and a newly generated card stay in the state only.
    later = combat([card("STRIKE", "Deal 9 damage."), card("SHIV", "Deal 4 damage.")])
    again, state = split(reference, later)
    assert again == text
    assert state["card_text"] == {"Strike": "Deal 9 damage.", "Shiv": "Deal 4 damage."}

    # A new fight starts a new reference.
    other, _ = split(reference, combat([card("SHIV", "Deal 4 damage.")], floor=5))
    assert other != text and "Shiv" in other


class Recorder(FakeAnthropic):
    def answer(self, _request):
        return {"choice": self.script}


def test_claude_requests_cache_the_stable_prefix_and_recheck_as_a_second_turn():
    fake = Recorder()
    fake.script = 2                                     # end turn into 20 damage, then keep it
    client = agent.ClaudeDecisions(fake, "claude-sonnet-5-5")
    hand = [{"index": 0, "id": "DEFEND_IRONCLAD", "name": "Defend", "energy_cost": 1, "energy_x": False,
             "star_cost": -1, "star_x": False, "type": "Skill", "target_type": "Self", "upgrade": 0,
             "keywords": [], "description": "Gain 5 [gold]Block[/gold]."}]
    state = combat([])
    state["state"]["player"].update(block=0, powers=[])
    state["state"].update(hand=hand, energy=2, turn=3,
                          enemies=[{"index": 0, "id": "TEST", "name": "Test", "hp": 90, "block": 0, "powers": [],
                                    "intents": [{"type": "Attack", "damage": 20, "hits": 1, "total_damage": 20}]}])
    state["actions"] = [{"id": "defend", "kind": "play_card",
                         "detail": {"card_index": 0, "card_id": "DEFEND_IRONCLAD", "description": hand[0]["description"]}},
                        {"id": "end", "kind": "end_turn", "detail": {}}]
    reference = FightReference()
    agent.choose(client, state, ["play_card DEFEND"], "", {}, reference=reference)
    first, recheck = fake.requests
    assert first["system"][0]["cache_control"] and first["system"] == recheck["system"]
    stable, volatile = first["messages"][0]["content"]
    assert stable["cache_control"] and "Gain 5 Block." in stable["text"]
    assert "cache_control" not in volatile
    assert recheck["messages"][0] == first["messages"][0]
    assert [message["role"] for message in recheck["messages"]] == ["user", "assistant", "user"]
    assert "Your initial choice 2" in recheck["messages"][2]["content"]


def test_the_combat_system_prompt_does_not_change_between_decisions():
    fake = Recorder()
    fake.script = 1
    client = agent.ClaudeDecisions(fake, "claude-sonnet-5-5")
    plannable = combat([card("A", cost=0), card("B", cost=0)])
    single = combat([card("A", cost=0)])
    agent.choose(client, plannable, ["play_card X"], "", {}, turn_sequence=CombatSequence())
    agent.choose(client, single, ["play_card X"], "", {"encounter_experience": {"past_attempts": 2}})
    systems = {json.dumps(request["system"]) for request in fake.requests}
    assert len(systems) == 1
    notes = [request["messages"][0]["content"][-1]["text"] for request in fake.requests]
    assert not notes[0].startswith("Return no sequence") and notes[1].startswith("Return no sequence")


def potion_turn(incoming, *, block=0):
    state = combat([])
    state["state"].update(turn=2, energy=0, hand=[],
                          player={"hp": 60, "max_hp": 80, "block": block},
                          potions=[{"index": 0, "id": "FIRE_POTION", "name": "Fire Potion"}],
                          enemies=[{"index": 0, "id": "TEST", "name": "Test", "hp": 40, "block": 0,
                                    "intents": [{"type": "Attack", "damage": incoming, "hits": 1,
                                                 "total_damage": incoming}]}])
    state["actions"] = [{"id": "end", "kind": "end_turn", "detail": {}},
                        {"id": "fire", "kind": "use_potion", "detail": {"potion_index": 0, "target_index": 0}}]
    return state


def test_a_potion_only_end_of_turn_is_local_only_when_nothing_is_at_stake():
    tactics = agent.combat_tactics(potion_turn(4, block=0))
    assert agent._settled_end_turn(potion_turn(4), tactics, turn_opening=False) == 1
    assert agent._settled_end_turn(potion_turn(4), tactics, turn_opening=True) is None
    heavy = potion_turn(25)
    assert agent._settled_end_turn(heavy, agent.combat_tactics(heavy), turn_opening=False) is None


def test_a_filled_hand_selection_is_confirmed_locally():
    selection = {"screen": "card_selection", "state": {
        "location": "combat_hand", "mode": "SimpleSelect", "min_select": 1, "max_select": 1, "selected_count": 1},
        "actions": [{"id": "toggle", "kind": "toggle_card_choice", "detail": {}},
                    {"id": "ok", "kind": "confirm_card_choice", "detail": {"count": 1}}]}
    assert agent._completed_hand_selection(selection, ["toggle_card_choice hand_card.select.1"])["id"] == "ok"
    assert agent._completed_hand_selection(selection, ["play_card GLIMMER"]) is None
    deck = {**selection, "state": {**selection["state"], "location": "deck"}}
    assert agent._completed_hand_selection(deck, ["toggle_card_choice x"]) is None
    partial = {**selection, "state": {**selection["state"], "max_select": 2}}
    assert agent._completed_hand_selection(partial, ["toggle_card_choice x"]) is None


def test_optional_hand_replacement_can_finish_without_reversing_its_own_picks():
    confirm = {"id": "hand_card.confirm", "kind": "confirm_card_choice", "detail": {}}
    select = {"id": "hand_card.select.0", "kind": "toggle_card_choice", "detail": {"selected": False}}
    deselect = {"id": "hand_card.deselect.1", "kind": "toggle_card_choice", "detail": {"selected": True}}
    actions = [select, deselect, confirm]
    state = {"screen": "card_selection", "state": {
        "location": "combat_hand", "mode": "SimpleSelect", "min_select": 0, "max_select": 999999999,
        "selected_count": 1, "prompt": "[center]Choose any number of cards to replace.[/center]",
    }}
    assert agent._hand_replacement_actions(state, actions, []) == actions
    recent = ["use_potion GAMBLERS_BREW", "toggle_card_choice hand_card.select.1"]
    assert agent._hand_replacement_actions(state, actions, recent) == [select, confirm]
    assert agent._completed_hand_selection({**state, "actions": [select, confirm]}, recent) is None
    assert agent._completed_hand_selection({**state, "actions": [confirm]}, recent) == confirm

    state["state"]["prompt"] = "Choose any number of cards to retain."
    assert agent._hand_replacement_actions(state, actions, recent) == actions


def with_end_turn(state):
    return {**state, "actions": [*state["actions"], {"id": "end", "kind": "end_turn", "detail": {}}]}


def test_a_plan_may_end_the_turn_after_every_play_resolved_as_planned():
    block, other = card("BLOCK"), card("OTHER")
    before = with_end_turn(snapshot([block, other], energy=2))
    after = with_end_turn(snapshot([other], energy=1, revision=6, discard=1))
    plan = CombatSequence()
    assert plan.offer(before, 1, [1, 3]) == 1            # the end turn is choice 3 before the play
    plan.advance(before, before["actions"][0], after)
    assert plan.take(after) == 2                         # end turn is choice 2 afterwards
    # End turn in the middle of a plan is not accepted.
    assert CombatSequence().offer(before, 1, [1, 3, 2]) == 0


def test_cache_model_reads_a_repeated_prefix_and_writes_only_up_to_the_breakpoint():
    cache = CacheModel()
    request = {"system": [{"type": "text", "text": "S" * 100, "cache_control": {"type": "ephemeral"}}],
               "messages": [{"role": "user", "content": [{"type": "text", "text": "volatile"}]}]}
    assert cache.measure(request, 0) == {"chars": 108, "read_chars": 0, "write_chars": 100, "uncached_chars": 8}
    assert cache.measure(request, 60)["read_chars"] == 100
    assert cache.measure(request, 60 + 301)["read_chars"] == 0      # expired after five idle minutes
