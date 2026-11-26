"""Fool Arrows in queued sequences, and end-turn reviews that meet a stale action."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import steam_mod_agent as agent
from steam_mod_sequence import CombatSequence
from steam_mod_tactics import arrow_ready_actions, arrow_state, combat_tactics

SHOT = "[gold]Shoot[/gold] an [gold]Arrow[/gold] to deal 10 damage."
STRIKE = "Deal 6 damage."


def fool_card(index, key, description, *, cost=1, kind="Attack"):
    return {"index": index, "id": key, "instance_id": f"c:{key}", "name": key.title(),
            "description": description, "energy_cost": cost, "energy_x": False, "star_cost": -1,
            "star_x": False, "type": kind, "upgrade": 0, "target_type": "AnyEnemy", "keywords": []}


def fool_turn(hand, *, revision=5, energy=2, hits=2, arrows=None, priest_hp=132):
    priest = {"index": 0, "id": "KIN_PRIEST", "instance_id": "e:priest", "name": "Kin Priest",
              "hp": priest_hp, "max_hp": 190, "block": 0,
              "powers": [{"id": "IMPALED_POWER", "name": "Impaled", "amount": 1, "display_amount": hits}] if hits else [],
              "intents": [{"type": "Attack", "damage": 9, "hits": 1, "total_damage": 9}]}
    state = {"phase": "Play", "encounter": "THE_KIN_BOSS", "turn": 2, "round": 2, "energy": energy, "stars": 0,
             "hand": hand, "enemies": [priest], "player": {"hp": 50, "max_hp": 70, "block": 0, "powers": []},
             "draw_pile_count": 5, "discard_pile_count": 3, "exhaust_pile_count": 0, "potions": []}
    if arrows is not None:
        state["arrows_available"] = arrows
    actions = [{"id": f"play:{card['index']}", "kind": "play_card",
                "detail": {"card_index": card["index"], "card_id": card["id"], "card_instance_id": card["instance_id"],
                           "description": card["description"], "target_index": 0, "target_instance_id": "e:priest"}}
               for card in hand]
    actions.append({"id": "end", "kind": "end_turn", "detail": {}})
    return {"screen": "combat", "state_id": f"fool:{revision}:x", "actions": actions, "state": state,
            "run": {"profile": 3, "seed": "S", "character": "CHARACTER.FOOL", "act": 1, "floor": 17}}


def test_arrow_count_comes_from_the_bridge_or_is_inferred_from_an_impaled_enemy():
    assert arrow_state(fool_turn([], arrows=1, hits=0)["state"]) == {"available": 1, "impaled": []}
    inferred = arrow_state(fool_turn([], hits=2)["state"])
    assert inferred["available"] == 0 and inferred["impaled"] == [{"target_index": 0, "hits_to_dislodge": 2}]
    assert arrow_state(fool_turn([], hits=0)["state"]) is None


def test_combat_summary_marks_shots_without_an_arrow_and_the_hits_that_dislodge_it():
    hand = [fool_card(0, "STRIKE_FOOL", STRIKE), fool_card(1, "STRIKE_FOOL", STRIKE), fool_card(2, "QUICK_SHOT", SHOT, cost=0)]
    arrows = combat_tactics(fool_turn(hand, arrows=0))["arrows"]
    assert arrows["shots_without_arrow"] == [3] and arrows["dislodge_hit_choices"] == [1, 2]


def test_arrowless_hobbling_shot_is_hidden_but_whistling_arrows_can_block():
    hand = [
        fool_card(0, "HOBBLING_SHOT", SHOT, cost=0),
        fool_card(1, "WHISTLING_ARROWS",
                  "Gain 4 Block. Whenever you Shoot an Arrow, return this to your Hand.",
                  cost=0, kind="Skill"),
        fool_card(2, "STRIKE_FOOL", STRIKE),
    ]
    no_arrow = fool_turn(hand, arrows=0)
    assert combat_tactics(no_arrow)["arrows"]["shots_without_arrow"] == [1]
    assert [a["id"] for a in arrow_ready_actions(no_arrow)] == ["play:1", "play:2", "end"]
    with_arrow = fool_turn(hand, arrows=1, hits=0)
    assert arrow_ready_actions(with_arrow) == with_arrow["actions"]


def test_a_queued_plan_never_spends_more_arrows_than_are_available():
    hand = [fool_card(0, "QUICK_SHOT", SHOT, cost=0), fool_card(1, "QUICK_SHOT_B", SHOT, cost=0),
            fool_card(2, "STRIKE_FOOL", STRIKE)]
    one_arrow = fool_turn(hand, arrows=1, hits=0)
    plan = CombatSequence()
    assert plan.offer(one_arrow, 1, [1, 2, 3]) == 0              # the second shot has no Arrow left
    plan = CombatSequence()
    assert plan.offer(one_arrow, 3, [3, 1]) == 1                  # strike, then the one shot


def test_a_queued_shot_is_dropped_when_the_live_arrow_is_still_impaled():
    # Two strikes are queued before the shot; the first strike leaves the Arrow impaled.
    strike_a, strike_b = fool_card(0, "STRIKE_FOOL", STRIKE), fool_card(1, "STRIKE_FOOL_B", STRIKE)
    shot = fool_card(2, "QUICK_SHOT", SHOT, cost=0)
    before = fool_turn([strike_a, strike_b, shot], energy=2, arrows=1, hits=0)
    plan = CombatSequence()
    assert plan.offer(before, 1, [1, 2, 3]) == 2
    after_a = fool_turn([fool_card(0, "STRIKE_FOOL_B", STRIKE), fool_card(1, "QUICK_SHOT", SHOT, cost=0)],
                        revision=6, energy=1, arrows=1, hits=0)
    after_a["state"]["discard_pile_count"] = 4
    plan.advance(before, before["actions"][0], after_a)
    assert plan.take(after_a) == 1                                 # the second strike
    # The live state now says the Arrow is out (the earlier shot impaled it): drop the shot.
    after_b = fool_turn([fool_card(0, "QUICK_SHOT", SHOT, cost=0)], revision=7, energy=0, arrows=0, hits=1)
    after_b["state"]["discard_pile_count"] = 5
    plan.advance(after_a, after_a["actions"][0], after_b)
    assert plan.take(after_b) is None and not plan.has_pending


def reply(choice):
    message = SimpleNamespace(content=json.dumps({"choice": choice}))
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=message)], usage=None)


def test_a_shot_without_an_arrow_is_rechecked_and_the_strike_is_played_first():
    # Turn 2 of the floor-17 Kin fight: after Ki Hop the Arrow needs two more hits.
    hand = [fool_card(0, "STRIKE_FOOL", STRIKE), fool_card(1, "STRIKE_FOOL_B", STRIKE),
            fool_card(2, "QUICK_SHOT", SHOT, cost=0)]
    questions = []

    def request(_client, _instructions, _data, _high_risk, followup=None, **_stable):
        questions.append(followup)
        return reply(1 if followup else 3)

    with patch.object(agent, "request_choice", side_effect=request):
        chosen, _, usage = agent.choose(None, fool_turn(hand, arrows=0), ["play_card KI_HOP"], "", {})
    assert chosen == "play:0" and usage["rechecked_arrow"] == 3
    assert "no available Arrow" in questions[1][1] and "enemy 0 after 2 more hits" in questions[1][1]


# --- end-turn review and stale actions --------------------------------------------------------

def necro_card(index, key, description, cost=1, *, kind="Skill", target="Self"):
    return {"index": index, "id": key, "instance_id": f"n:{key}", "name": key.title(), "description": description,
            "energy_cost": cost, "energy_x": False, "star_cost": -1, "star_x": False, "type": kind,
            "target_type": target, "upgrade": 0, "keywords": []}


def necro_turn(revision, hand, energy, block):
    enemies = [{"index": 0, "id": "PARAFRIGHT", "instance_id": "e:p", "name": "Parafright", "hp": 21, "max_hp": 21,
                "block": 0, "powers": [{"id": "ILLUSION_POWER", "amount": 1}, {"id": "MINION_POWER", "amount": 1}],
                "intents": [{"type": "Attack", "damage": 16, "hits": 1, "total_damage": 16}]},
               {"index": 1, "id": "THE_OBSCURA", "instance_id": "e:o", "name": "The Obscura", "hp": 120,
                "max_hp": 150, "block": 6, "powers": [], "intents": [{"type": "Buff"}]}]
    actions = []
    for card in hand:
        targets = [0, 1] if card["target_type"] == "AnyEnemy" else [None]
        for target in targets:
            detail = {"card_index": card["index"], "card_id": card["id"], "description": card["description"]}
            if target is not None:
                detail["target_index"] = target
            actions.append({"id": f"play:{card['id']}:{target}", "kind": "play_card", "detail": detail})
    actions.append({"id": "end", "kind": "end_turn", "detail": {}})
    return {"screen": "combat", "state_id": f"necro:{revision}:x", "actions": actions,
            "run": {"profile": 3, "seed": "S", "character": "CHARACTER.NECROBINDER", "act": 2, "floor": 28,
                    "hp": 46, "max_hp": 80},
            "state": {"phase": "Play", "encounter": "THE_OBSCURA_NORMAL", "turn": 3, "round": 3, "energy": energy,
                      "stars": 0, "hand": hand, "enemies": enemies, "potions": [],
                      "player": {"hp": 46, "max_hp": 80, "block": block, "powers": [], "relics": []},
                      "draw_pile_count": 6, "discard_pile_count": 6, "exhaust_pile_count": 0}}


UNLEASH = necro_card(1, "UNLEASH", "[gold]Osty[/gold] deals [green]23[/green] damage.", kind="Attack", target="AnyEnemy")
REAVE = necro_card(2, "REAVE", "Deal 13 damage.", kind="Attack", target="AnyEnemy")
LETHALITY = necro_card(3, "LETHALITY", "The first Attack each turn deals 50% additional damage.", kind="Power")
WARDEN = necro_card(0, "GRAVE_WARDEN", "Gain 8 [gold]Block[/gold].\nAdd a Soul into your Draw Pile.")


def renumber(cards):
    return [{**card, "index": index} for index, card in enumerate(cards)]


def test_a_stale_action_does_not_use_up_the_end_turn_review(tmp_path):
    opening = necro_turn(1, renumber([WARDEN, UNLEASH, REAVE, LETHALITY]), energy=5, block=0)
    replanned = {**opening, "state_id": "necro:1:y"}   # same epoch, new hash
    after_warden = necro_turn(3, renumber([UNLEASH, REAVE, LETHALITY]), energy=4, block=8)
    done = {"screen": "settlement", "state_id": "necro:4:x", "actions": [],
            "state": {"outcome": "defeat", "native_history": True}, "run": opening["run"]}
    asked = []

    def request(_client, _instructions, data, _high_risk, followup=None, **_stable):
        state = json.loads(data)
        actions = state["actions"]
        end = next(row["choice"] for row in actions if row["kind"] == "end_turn")
        asked.append((state["state"]["energy"], bool(followup), followup[1] if followup else ""))
        if followup:                      # the review recommends playing on
            return reply(next(row["choice"] for row in actions if row["kind"] == "play_card"))
        if state["state"]["energy"] == 5 and len(asked) == 3:
            return reply(1)               # after the stale rejection: Grave Warden
        return reply(end)                 # otherwise propose ending the turn

    responses = iter([agent.SessionError("stale_state"), {"accepted": True}, {"accepted": True}])

    def tool(name, **_arguments):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    mcp = Mock()
    mcp.tool.side_effect = tool
    memo = Mock(identity=None)
    memo.context.return_value = {}
    options = SimpleNamespace(profile=None, checkpoint="run", journal_dir=tmp_path / "journal",
                              archive_dir=tmp_path / "archive", max_actions=6, from_room=False,
                              experience=tmp_path / "experience.json", no_review=True)
    with patch.object(agent, "read_ready", side_effect=[opening, replanned, after_warden, done]), \
            patch.object(agent, "SteamModMemory", return_value=memo), \
            patch.object(agent, "request_choice", side_effect=request), patch.object(agent, "sleep"):
        agent.play(mcp, None, options)

    # 1-2: end turn at 5 energy, review -> play on (rejected as stale).
    # 3: same state replanned -> Grave Warden. 4-5: end turn at 4 energy with four affordable
    # plays is reviewed again, because the hand and energy changed after the rejected review.
    assert [(energy, follow) for energy, follow, _ in asked] == [(5, False), (5, True), (5, False), (4, False), (4, True)]
    assert "changed since" in asked[4][2] and "shown_kill_choices" in asked[4][2]


def test_end_turn_reviews_stay_bounded_within_a_turn():
    state = necro_turn(5, renumber([UNLEASH, REAVE, LETHALITY]), energy=4, block=8)
    turn_state = agent._turn_state_key(state["state"])
    calls = []

    def request(_client, _instructions, _data, _high_risk, followup=None, **_stable):
        calls.append(followup)
        return reply(len(state["actions"]))

    used = frozenset({"rechecked_end_turn", "end_turn_reviewed:other"})
    with patch.object(agent, "request_choice", side_effect=request):
        agent.choose(None, state, ["play_card GRAVE_WARDEN"], "", {}, reviewed_hazards=used)
        assert calls[-1] is not None                               # changed state: one follow-up
        calls.clear()
        agent.choose(None, state, ["play_card GRAVE_WARDEN"], "", {},
                     reviewed_hazards=used | {"end_turn_reviewed:" + turn_state})
        assert calls == [None]                                     # bound reached


def test_lethal_multihit_uses_cho_before_wah_blast_and_then_follows_through():
    cho = fool_card(0, "CHO_BARBS", "Gain 6 Block.\nGain 4 Thorns.", kind="Skill")
    cho["affliction"] = {"id": "BOUND"}
    blast = fool_card(1, "WAH_BLAST", "Deal 27 damage to ALL enemies.\n"
                     "If you have a Cho Melody or Ki Melody, hits twice.", cost=2)
    before = fool_turn([cho, blast], energy=3, arrows=0, priest_hp=44)
    before["state"]["player"]["hp"] = 7
    before["state"]["enemies"][0]["intents"] = [
        {"type": "Attack", "damage": 16, "hits": 3, "total_damage": 48}
    ]
    for action in before["actions"][:2]:
        action["detail"]["target_index"] = None

    action_id, _, usage = agent.choose(None, before, [], "")
    assert action_id == "play:0"
    assert usage["local_melody_survival"] == {"choices": [1, 2], "damage": 54, "target_index": 0}
    assert combat_tactics(before)["incoming_by_target"][0]["weak_saves_at_least"] == 12

    after = {**before, "actions": before["actions"][1:],
             "state": {**before["state"], "energy": 2, "hand": [blast]}}
    action_id, _, usage = agent.choose(None, after, ["play_card CHO_BARBS"], "")
    assert action_id == "play:1"
    assert usage["local_melody_survival"]["choices"] == [1]

    after["state"]["active_melodies"] = ["Ki"]
    after["state"]["player"]["relics"] = [{"id": "PEN_NIB", "counter": 9}]
    action_id, _, usage = agent.choose(None, after, ["use_potion SPEED_POTION"], "")
    assert action_id == "play:1"
    assert usage["local_melody_survival"]["damage"] == 54
    assert combat_tactics(after)["pen_nib_doubles_attack_number_from_now"] == 1
