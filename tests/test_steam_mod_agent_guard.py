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


def test_early_regent_reviews_nonlethal_strike_that_crowds_out_block():
    strike = {**defend(0), "id": "STRIKE_REGENT", "description": "Deal 6 damage.", "type": "Attack"}
    block = {**defend(1), "id": "DEFEND_REGENT"}
    snapshot = state([strike, block], energy=1, incoming=8, hp=62)
    snapshot["run"]["character"] = "CHARACTER.REGENT"
    snapshot["state"].update(act=1, encounter="SEAPUNK_WEAK")
    snapshot["state"]["enemies"][0].update(id="SEAPUNK", hp=13)
    snapshot["actions"][0]["detail"]["target_index"] = 0
    model = FakeModel(choice=1)

    _, _, usage = agent.choose(model, snapshot, [], "")

    assert usage["rechecked_defense"] == 1
    assert "leave only 3 HP loss" in asked(model.calls[-1])
    assert "compare the two lines through the next hand" in asked(model.calls[-1]).lower()

    snapshot["state"]["enemies"][0]["hp"] = 6
    action, _, usage = agent.choose(FakeModel(choice=1), snapshot, [], "")
    assert action == "card-0" and "rechecked_defense" not in usage


def test_next_draw_lethal_includes_retained_blade_after_guiding_star():
    strike = {**defend(0), "id": "STRIKE_REGENT", "description": "Deal 6 damage.", "type": "Attack"}
    block = {**defend(1), "id": "DEFEND_REGENT"}
    blade = {**strike, "index": 2, "id": "SOVEREIGN_BLADE", "energy_cost": 2,
             "description": "Retain.\nDeal 17 damage.", "keywords": ["Retain"]}
    snapshot = state([strike, block, blade], energy=1, incoming=8, hp=74)
    snapshot["run"]["character"] = "CHARACTER.REGENT"
    combat = snapshot["state"]
    combat.update(act=1, encounter="SEAPUNK_WEAK", max_energy=3, draw_pile_count=1,
                  draw_pile=[{**strike, "count": 1}])
    combat["player"]["powers"] = [{"id": "DRAW_CARDS_NEXT_TURN_POWER", "amount": 2}]
    combat["enemies"][0].update(id="SEAPUNK", hp=20)
    snapshot["actions"][0]["detail"]["target_index"] = 0
    del snapshot["actions"][2]  # The blade is too expensive to play this turn.
    model = FakeModel(choice=1)

    action, _, usage = agent.choose(model, snapshot, [], "")

    assert action == "card-1"
    assert usage["local_block_for_next_lethal"]["damage_before_vulnerable"] == 23
    assert len(model.calls) == 1

    blade["keywords"] = []
    action, _, usage = agent.choose(FakeModel(choice=1), snapshot, [], "")
    assert action == "card-0" and "local_block_for_next_lethal" not in usage


def test_regent_queued_strike_keeps_last_energy_for_full_block_against_shrinker():
    strike = {**defend(0), "id": "STRIKE_REGENT", "description": "Deal [red]4[/red] damage.", "type": "Attack"}
    block = {**defend(1), "id": "DEFEND_REGENT"}
    snapshot = state([strike, block], energy=1, incoming=5, hp=57)
    snapshot["run"]["character"] = "CHARACTER.REGENT"
    snapshot["state"].update(act=1, encounter="SHRINKER_BEETLE_WEAK")
    snapshot["state"]["enemies"][0].update(id="SHRINKER_BEETLE", hp=14)
    snapshot["state"]["player"]["powers"] = [{"id": "SHRINK_POWER", "amount": -1}]
    snapshot["actions"][0]["detail"]["target_index"] = 0
    cleared = []
    sequence = SimpleNamespace(take=lambda _: 1, clear=lambda: cleared.append(True))
    model = FakeModel(choice=1)
    action, _, usage = agent.choose(model, snapshot, [], "", turn_sequence=sequence)
    assert action == "card-1"
    assert usage["local_preserve_hp"]["hp_loss"] == 0
    assert cleared and not model.calls


def test_regent_keeps_stars_on_the_ceremonial_beast_opening():
    cloak = {**defend(0, "Gain 7 Block."), "id": "CLOAK_OF_STARS", "energy_cost": 0, "star_cost": 1}
    strike = {**defend(1, "Deal 6 damage."), "id": "STRIKE_REGENT", "type": "Attack"}
    snapshot = state([cloak, strike], incoming=0)
    snapshot["state"].update(turn=1, stars=1)
    enemy = snapshot["state"]["enemies"][0]
    enemy["intents"] = [{"type": "Buff"}]
    assert agent.choose(FakeModel(choice=1), snapshot, [], "")[0] == "card-1"

    snapshot["state"]["player"]["relics"] = [{"id": "CALIPERS"}]
    assert agent.choose(FakeModel(choice=1), snapshot, [], "")[0] == "card-0"


def test_cloak_is_held_when_all_exoskeletons_are_buffing():
    cloak = {**defend(0, "Gain 7 Block."), "id": "CLOAK_OF_STARS", "energy_cost": 0, "star_cost": 1}
    snapshot = state([cloak], incoming=0)
    combat = snapshot["state"]
    combat.update(encounter="EXOSKELETONS_WEAK", stars=1)
    combat["player"]["relics"] = [{"id": "GLASS_EYE"}]
    enemy = combat["enemies"][0]
    enemy.update(id="EXOSKELETON", intents=[{"type": "Buff"}],
                 powers=[{"id": "HARD_TO_KILL_POWER", "amount": 9}])
    assert agent.choose(FakeModel(choice=1), snapshot, [], "")[0] == "end"

    enemy["intents"] = [{"type": "Attack", "damage": 7, "hits": 1, "total_damage": 7}]
    assert agent.choose(FakeModel(choice=1), snapshot, [], "")[0] == "card-0"
    enemy["intents"] = [{"type": "Buff"}]
    combat["hand"].append({"id": "BURN", "index": 1,
                           "description": "At the end of your turn, if this is in your Hand, take 2 damage."})
    assert agent.choose(FakeModel(choice=1), snapshot, [], "")[0] == "card-0"


def test_regent_blocks_when_next_draw_already_guarantees_ceremonial_stun():
    strike = {**defend(0, "Deal 11 damage."), "id": "STRIKE_REGENT", "type": "Attack"}
    block = {**defend(1), "id": "DEFEND_REGENT"}
    blade = {**strike, "id": "SOVEREIGN_BLADE", "index": 2, "energy_cost": 2,
             "keywords": ["Retain"], "description": "Retain.\nDeal 22 damage."}
    snapshot = state([strike, block, blade], energy=1, incoming=18, hp=61)
    del snapshot["actions"][2]
    snapshot["actions"][0]["detail"]["target_index"] = 0
    snapshot["run"]["character"] = "CHARACTER.REGENT"
    combat = snapshot["state"]
    combat.update(act=1, turn=2, stars=6, max_energy=3, draw_pile_count=4, draw_pile=[
        {**strike, "id": "FALLING_STAR", "energy_cost": 0, "star_cost": 2, "count": 1,
         "description": "Deal 8 damage.\nApply 1 Weak.\nApply 1 Vulnerable."},
        {**strike, "id": "PHOTON_CUT", "count": 1, "description": "Deal 13 damage.\nDraw 2 cards."},
        {**block, "count": 2},
    ])
    combat["player"]["powers"] = [
        {"id": "STRENGTH_POWER", "amount": 5}, {"id": "FLEX_POTION_POWER", "amount": 5},
    ]
    enemy = combat["enemies"][0]
    enemy.update(hp=201, powers=[{"id": "PLOW_POWER", "amount": 150}])
    enemy["intents"].append({"type": "Buff"})
    action, _, usage = agent.choose(FakeModel(choice=1), snapshot, [], "")
    assert action == "card-1"
    assert usage["local_block_for_next_stun"]["damage"] == 52

    combat["draw_pile"][2]["count"] = 4
    combat["draw_pile_count"] = 6
    assert "ceremonial_stun_from_next_draw" not in agent.combat_tactics(snapshot)


def test_keeps_deck_search_potion_when_every_draw_pile_card_is_unplayable():
    snapshot = state([], incoming=13, hp=37)
    snapshot["state"].update(ringing={"ringed_plays_remaining": 0}, draw_pile_count=1,
                             draw_pile=[{"id": "FALLING_STAR", "count": 1,
                                         "description": "Deal 8 damage.\n[purple]Ringing.[/purple]"}])
    snapshot["actions"].insert(0, {"id": "search", "kind": "use_potion",
                                    "detail": {"potion_id": "DROPLET_OF_PRECOGNITION"}})
    assert agent.choose(FakeModel(choice=1), snapshot, [], "", allow_review=False)[0] == "end"

    snapshot["state"]["draw_pile"][0]["description"] += "\nRetain."
    assert agent.choose(FakeModel(choice=1), snapshot, [], "", allow_review=False)[0] == "search"


def test_reserves_flex_when_shambler_is_guaranteed_to_die_after_full_block():
    skill = {**defend(0, "Gain 7 Block."), "id": "CLOAK_OF_STARS", "energy_cost": 0, "star_cost": 1}
    strike = {**defend(1, "Deal 6 damage."), "id": "STRIKE_REGENT", "type": "Attack"}
    might = {**strike, "index": 2, "id": "CELESTIAL_MIGHT", "energy_cost": 2,
             "description": "Deal 6 damage 4 times."}
    snapshot = state([skill, strike, might], energy=3, incoming=6, hp=61)
    snapshot["run"]["character"] = "CHARACTER.REGENT"
    combat = snapshot["state"]
    combat.update(encounter="VINE_SHAMBLER_NORMAL", max_energy=3, stars=1, draw_pile_count=2,
                  draw_pile=[{**strike, "id": "WROUGHT_IN_WAR", "count": 1,
                              "description": "Deal 7 damage.\nForge 7."}, {**defend(0), "count": 1}])
    enemy = combat["enemies"][0]
    enemy.update(id="VINE_SHAMBLER", hp=35)
    enemy["intents"].append({"type": "CardDebuff"})
    for action in snapshot["actions"][1:3]:
        action["detail"]["target_index"] = 0
    snapshot["actions"].append({"id": "flex", "kind": "use_potion", "detail": {
        "potion_id": "FLEX_POTION",
        "description": "Gain 5 Strength. At the end of your turn, lose 5 Strength.",
    }})

    action, _, usage = agent.choose(FakeModel(choice=5), snapshot, [], "")
    assert action == "card-0"
    assert usage["local_save_flex_potion"]["drawn_card"] == "WROUGHT_IN_WAR"
    assert usage["local_save_flex_potion"]["next_turn_energy"] == 2

    # The cheaper strike is sufficient after blocking and doing 24 damage.
    # Lethal review must not steer that strike back to the potion.
    enemy["hp"] = 11
    combat.update(energy=1, stars=0, hand=[strike])
    combat["player"]["block"] = 7
    snapshot["actions"] = [snapshot["actions"][index] for index in (1, 3, 4)]
    model = FakeModel(choice=1)
    action, _, usage = agent.choose(model, snapshot, [], "")
    assert action == "card-1" and "rechecked_lethal_combo" not in usage and len(model.calls) == 1

    combat["draw_pile"][1]["count"] = 5
    combat["draw_pile_count"] = 6
    assert "safe_finish_without_flex" not in agent.combat_tactics(snapshot)


def test_attack_stuns_terror_eel_before_spending_block_potion():
    strike = {**defend(0), "id": "STRIKE_REGENT", "description": "Deal 10 damage.", "type": "Attack"}
    potion = {"id": "potion", "kind": "use_potion", "detail": {"potion_id": "BLOCK_POTION"}}
    snapshot = state([strike], energy=1, incoming=22)
    snapshot["run"]["character"] = "CHARACTER.REGENT"
    snapshot["actions"][0]["detail"]["target_index"] = 0
    snapshot["actions"].insert(1, potion)
    enemy = snapshot["state"]["enemies"][0]
    enemy.update(id="TERROR_EEL", hp=77, max_hp=140, powers=[
        {"id": "SHRIEK_POWER", "amount": 70}, {"id": "VIGOR_POWER", "amount": 6},
    ])
    model = FakeModel(choice=2)

    action, _, usage = agent.choose(model, snapshot, [], "")

    assert action == "card-0"
    assert usage["local_attack_stun"]["stun_hp"] == 70
    assert not model.calls

    enemy["block"] = 4
    assert "known_stun_lines" not in agent.combat_tactics(snapshot)
    enemy["block"] = 0
    enemy["powers"].pop(0)
    assert "known_stun_lines" not in agent.combat_tactics(snapshot)


def test_holds_regen_potion_at_full_health():
    snapshot = state([defend(0)], hp=90)
    potion = {"id": "regen", "kind": "use_potion", "detail": {
        "potion_id": "REGEN_POTION", "description": "Gain 5 Regen.",
    }}
    snapshot["actions"].insert(0, potion)

    action, _, _ = agent.choose(FakeModel(choice=1), snapshot, [], "")
    assert action == "card-0"

    snapshot["state"]["player"]["hp"] = snapshot["run"]["hp"] = 75
    action, _, _ = agent.choose(FakeModel(choice=1), snapshot, [], "")
    assert action == "regen"


def test_holds_potions_that_only_draw_or_add_cards_while_hand_is_full():
    snapshot = state([defend(index) for index in range(10)], incoming=0)
    potion = {"id": "attack_potion", "kind": "use_potion", "detail": {"potion_id": "ATTACK_POTION"}}
    defensive_potion = {"id": "block_potion", "kind": "use_potion", "detail": {"potion_id": "BLOCK_POTION"}}
    snapshot["actions"][:0] = [potion, defensive_potion]

    action, _, _ = agent.choose(FakeModel(choice=1), snapshot, [], "")
    assert action == "block_potion"

    snapshot["state"]["hand"].pop()
    snapshot["actions"].pop(-2)
    action, _, _ = agent.choose(FakeModel(choice=1), snapshot, [], "")
    assert action == "attack_potion"


def test_no_guard_when_block_already_covers_the_hit():
    snapshot = state([defend(0)], incoming=0)
    model = FakeModel(choice=2)
    action_id, _, usage = agent.choose(model, snapshot, [], "", {})
    assert action_id == "end" and "end_turn_guard" not in usage



def test_poison_lethal_saves_the_potion_without_a_provider_call():
    snapshot = state([], energy=0, incoming=15, hp=15)
    combat = snapshot["state"]
    combat["encounter"] = "SLUMBERING_BEETLE_NORMAL"
    combat["player"]["powers"] = [{"id": "ACCELERANT_POWER", "amount": 1}]
    combat["enemies"][0].update(hp=27, block=30, powers=[{"id": "POISON_POWER", "amount": 14}])
    snapshot["actions"][:0] = [
        {"id": "potion", "kind": "use_potion", "detail": {"potion_id": "COLORLESS_POTION"}},
        {"id": "retry", "kind": "retry_current_combat", "detail": {}},
    ]
    model = FakeModel(choice=1)
    action_id, _, usage = agent.choose(model, snapshot, [], "")
    assert action_id == "end"
    assert usage["local_poison_finish"] == [{"target_index": 0, "hp": 27, "stacks": 14, "ticks": 2, "damage": 27}]
    assert model.calls == []

    combat["enemies"][0]["hp"] = 28
    action_id, _, usage = agent.choose(model, snapshot, [], "")
    assert action_id == "potion" and "local_poison_finish" not in usage

    combat["enemies"][0]["hp"] = 27
    combat["enemies"][0]["powers"].append({"id": "SLIPPERY_POWER", "amount": 2})
    action_id, _, usage = agent.choose(model, snapshot, [], "")
    assert action_id == "potion" and "local_poison_finish" not in usage



def test_local_doom_finish_requires_safe_intents_and_simple_plays():
    snapshot = state([defend(0)], energy=1, hp=6)
    combat = snapshot["state"]
    combat["encounter"] = "SLUMBERING_BEETLE_NORMAL"
    enemy = combat["enemies"][0]
    enemy.update(hp=10, powers=[{"id": "DOOM_POWER", "amount": 10}],
                 intents=[{"type": "StatusCard", "total_damage": None}])
    model = FakeModel(choice=2)
    assert agent.choose(model, snapshot, [], "")[2]["local_doom_finish"]
    assert model.calls == []

    combat["encounter"] = "TEST_SUBJECT_BOSS"
    result = agent.choose(model, snapshot, [], "")
    assert result[0] == "end" and "local_doom_finish" not in result[2]
    assert len(model.calls) == 1  # no generic spare-energy review after the Doom calculation

    combat["encounter"] = "SLUMBERING_BEETLE_NORMAL"
    enemy["intents"] = [{"type": "Attack", "damage": 9, "hits": 1, "total_damage": 9}]
    assert "local_doom_finish" not in agent.choose(FakeModel(choice=1), snapshot, [], "")[2]

    enemy["intents"] = [{"type": "StatusCard"}]
    snapshot["actions"][0]["detail"]["description"] = DEFEND + " Draw 1 card."
    assert "local_doom_finish" not in agent.choose(FakeModel(choice=2), snapshot, [], "")[2]


def test_spare_energy_review_includes_attacks_when_no_block_is_needed():
    strike = {**defend(0), "id": "STRIKE_IRONCLAD", "description": "Deal 6 damage.", "type": "Attack"}
    snapshot = state([strike], energy=1, incoming=0)
    model = FakeModel(choice=2)
    action_id, _, usage = agent.choose(model, snapshot, [], "")
    assert action_id == "end" and usage["rechecked_end_turn"] == 2
    assert any("1 energy and legal card choices [1]" in asked(call) for call in model.calls)

    snapshot["state"]["player"]["relics"] = [{"id": "ICE_CREAM"}]
    action_id, _, usage = agent.choose(FakeModel(choice=2), snapshot, [], "")
    assert action_id == "end" and "rechecked_end_turn" not in usage


def test_exhausted_lethal_saves_before_end_turn(monkeypatch):
    snapshot = state([], energy=0, incoming=35, hp=20)
    snapshot["state"]["player"]["block"] = 6
    snapshot["actions"].append({"id": "save", "kind": agent.COMBAT_SAVE_AND_QUIT, "detail": {}})
    reason = agent.exhausted_lethal(snapshot)
    assert reason == "29 projected unblocked damage at 20 HP"

    calls, events = [], []
    responses = iter([{"screen": "waiting"}, {"screen": "idle"}])
    monkeypatch.setattr(agent, "sleep", lambda _: None)

    def tool(name, **arguments):
        calls.append((name, arguments))
        return {"accepted": True} if name == "perform_action" else next(responses)

    result = agent.save_before_lethal(
        SimpleNamespace(tool=tool), snapshot, lambda kind, **_: events.append(kind), reason
    )
    assert result == 0
    assert calls == [
        ("perform_action", {"state_id": snapshot["state_id"], "action_id": "save"}),
        ("get_state", {}),
        ("get_state", {}),
    ]
    assert events == ["lethal_stop", "lethal_stop_saved"]


def test_exhausted_lethal_waits_if_a_card_or_potion_is_available():
    snapshot = state([], energy=0, incoming=35, hp=20)
    snapshot["actions"].append({"id": "potion", "kind": "use_potion", "detail": {}})
    assert agent.exhausted_lethal(snapshot) is None
    assert agent.exhausted_lethal(state([defend(0)], incoming=35, hp=20)) is None


def test_lethal_end_turn_is_not_sent_while_only_debris_remains(tmp_path, monkeypatch):
    debris = {**defend(0), "id": "DEBRIS", "type": "Status", "description": "Exhaust."}
    snapshot = state([debris], energy=2, incoming=36, hp=2)
    snapshot["state"]["player"]["block"] = 10
    snapshot["actions"].append({"id": "save", "kind": agent.COMBAT_SAVE_AND_QUIT, "detail": {}})
    options = SimpleNamespace(profile=None, checkpoint="run", max_actions=1, no_review=True,
                              journal_dir=tmp_path / "journal", archive_dir=tmp_path / "archive")
    actions_sent = []

    def tool(name, **arguments):
        if name == "perform_action":
            actions_sent.append(arguments["action_id"])
            return {"accepted": True}
        return {"screen": "idle"}

    assert agent.exhausted_lethal(snapshot) is None
    monkeypatch.setattr(agent, "choose", lambda *_args, **_kwargs: ("end", "", {}))
    assert agent.play(SimpleNamespace(tool=tool), None, options, initial_state=snapshot) == 0
    assert actions_sent == ["save"]

    snapshot["state"]["player"]["powers"] = [{"id": "BUFFER_POWER", "amount": 1}]
    assert agent._end_turn_defeat(snapshot) is None


def test_combat_pick_prompt_carries_the_energy_after_the_trigger():
    chant = {**defend(0), "id": "KI_CHANT", "name": "Ki Chant+"}
    before = state([chant, {**defend(1), "name": "Defend+"}], energy=2, incoming=24)
    before["state"]["encounter"] = "QUEEN_BOSS"
    origin = agent.combat_selection_origin(before, before["actions"][0])
    assert origin["energy_after_trigger"] == 1
    assert origin["prior_hand"] == [{"card": "Defend+", "cost": 1, "affliction": None}]
    assert origin["enemy_intents"][0]["intents"][0]["total_damage"] == 24

    snapshot = {"screen": "card_selection", "state": {"mode": "choose"}, "run": before["run"],
                "actions": [{"id": "take", "kind": "toggle_card_choice", "detail": {}}],
                "combat_selection": origin}
    model = FakeModel(choice=1)
    assert agent.choose(model, snapshot, [], "")[0] == "take"
    prompt = asked(model.calls[0])
    assert '"energy_after_trigger":1' in prompt
    assert "Ki Chant can add the Ki Melody" in prompt
