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


def test_constrict_spends_block_before_attacks_and_keeps_end_turn_under_review():
    import steam_mod_agent as agent

    enemy = beast([{"type": "Attack", "damage": 9, "hits": 1, "total_damage": 9}])
    potion = {"id": "potion", "kind": "use_potion", "detail": {"id": "DEXTERITY_POTION"}}
    state = snapshot([], enemy, hp=63, block=5, energy=0, extra_actions=[potion])
    state["state"]["player"].update(max_hp=75, powers=[{"id": "CONSTRICT_POWER", "amount": 3}])
    tactics = combat_tactics(state)
    assert tactics["shown_attack_damage"] == 9
    assert tactics["end_of_turn_constrict_damage"] == 3
    assert tactics["unblocked_now"] == 7
    assert agent._settled_end_turn(state, tactics, turn_opening=False) is None

    hand = [card(0, "DEFEND_REGENT", 1, DEFEND)]
    state = snapshot(hand, enemy, block=9, energy=1)
    state["state"]["player"]["powers"] = [{"id": "CONSTRICT_POWER", "amount": 3}]
    assert end_turn_guard(state)["estimated_hp_saved"] == 3
    state["state"]["player"]["block"] = 12
    assert combat_tactics(state)["unblocked_now"] == 0
    assert end_turn_guard(state) is None


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


def test_visible_lethal_combines_vulnerability_and_separate_hits_within_budget():
    attack = {"type": "Attack", "damage": 19, "hits": 1, "total_damage": 19}
    enemies = [{**beast([attack])[0], "hp": 23, "block": 3}]
    hand = [
        card(0, "TWO_HIT", 1, "Deal 6 damage twice.", "Attack", "AnyEnemy"),
        card(1, "BASH", 1, "Deal 8 damage.\nApply 2 Vulnerable.", "Attack", "AnyEnemy"),
    ]
    state = snapshot(hand, enemies)
    line, = combat_tactics(state)["known_lethal_lines"]
    assert line["choices"] == [2, 1] and line["damage"] == 26
    assert line["hp_plus_block"] == 26 and line["removed_attack"] == 19
    state["state"]["energy"] = 1
    assert "known_lethal_lines" not in combat_tactics(state)
    state["state"]["energy"] = 2
    enemies[0]["powers"] = [{"id": "INTANGIBLE_POWER", "amount": 1}]
    assert "known_lethal_lines" not in combat_tactics(state)


def test_exoskeleton_caps_each_hit_after_vulnerability():
    enemy = beast([{"type": "Attack", "damage": 10, "hits": 1, "total_damage": 10}])[0]
    enemy.update(id="EXOSKELETON", hp=24, powers=[{"id": "HARD_TO_KILL_POWER", "amount": 9}])
    blade = card(0, "SOVEREIGN_BLADE", 2, "Retain.\nDeal 30 damage.", "Attack", "AnyEnemy")
    might = card(1, "CELESTIAL_MIGHT", 2, "Deal 6 damage 4 times.", "Attack", "AnyEnemy")
    state = snapshot([blade, might], [enemy])
    summary = combat_tactics(state)
    line, = summary["known_lethal_lines"]
    assert line["choices"] == [2] and line["damage"] == 24
    assert "shown_kill_choices" not in summary

    falling = {**card(0, "FALLING_STAR", 0, "Deal 8 damage.\nApply 1 Vulnerable.", "Attack", "AnyEnemy"),
               "star_cost": 2}
    wrought = card(1, "WROUGHT_IN_WAR", 1, "Deal 7 damage.\nForge 7.", "Attack", "AnyEnemy")
    strike = card(2, "STRIKE_REGENT", 1, "Deal 6 damage.", "Attack", "AnyEnemy")
    state = snapshot([falling, wrought, strike], [enemy])
    state["state"]["stars"] = 2
    line, = combat_tactics(state)["known_lethal_lines"]
    assert line["choices"] == [1, 2, 3] and line["damage"] == 26
    enemy["hp"] = 27
    assert "known_lethal_lines" not in combat_tactics(state)


def test_corrupted_attack_line_reports_the_health_paid_to_finish():
    enemy = beast([{"type": "Attack", "damage": 11, "hits": 1, "total_damage": 11}])[0]
    enemy.update(id="BOWLBUG_ROCK", hp=46)
    setup = card(0, "KNOW_THY_PLACE", 0, "Apply 1 Weak.\nApply 1 Vulnerable.\nExhaust.", "Skill", "AnyEnemy")
    might = card(1, "CELESTIAL_MIGHT", 2, "Deal 9 damage 4 times.\n[purple]Lose 2 HP.[/purple]", "Attack", "AnyEnemy")
    state = snapshot([setup, might], [enemy], block=5)
    line, = combat_tactics(state)["known_lethal_lines"]
    assert line["choices"] == [1, 2] and line["damage"] == 52
    assert line["self_hp_loss"] == line["hp_loss_with_remaining_block"] == 2

    state["state"]["player"]["hp"] = 2
    assert "known_lethal_lines" not in combat_tactics(state)


def test_block_guard_can_spend_stars_with_zero_energy():
    enemy = beast([{"type": "Attack", "damage": 19, "hits": 1, "total_damage": 19}])[0]
    wall = {**card(0, "PARTICLE_WALL", 0, "Gain 9 Block.\nReturn this card to your Hand."), "star_cost": 2}
    state = snapshot([wall], [enemy], block=14, energy=0)
    state["state"]["stars"] = 3
    guard = end_turn_guard(state)
    assert guard["card_id"] == "PARTICLE_WALL" and guard["estimated_hp_saved"] == 5
    state["state"]["stars"] = 1
    assert end_turn_guard(state) is None


def test_regent_combines_collision_and_blade_to_prevent_the_rock_bowlbug_attack(monkeypatch):
    from unittest.mock import Mock

    import steam_mod_agent as agent

    enemy = beast([{"type": "Attack", "damage": 11, "hits": 1, "total_damage": 11}])[0]
    enemy.update(hp=30, powers=[{"id": "IMBALANCED_POWER", "amount": 1}])
    hand = [
        card(0, "SOVEREIGN_BLADE", 2, "Retain.\nDeal 17 damage.", "Attack", "AnyEnemy"),
        card(1, "COLLISION_COURSE", 0, "Deal 14 damage.\nAdd a Debris into your Hand.", "Attack", "AnyEnemy"),
        card(2, "DEFEND_REGENT", 1, DEFEND),
    ]
    state = snapshot(hand, [enemy], energy=3)
    state["run"] = {"character": "CHARACTER.REGENT"}
    state["state"]["turn"] = 2
    monkeypatch.setattr(agent, "request_choice", Mock(side_effect=AssertionError("local lethal")))
    action, _, usage = agent.choose(None, state, [], "")
    assert action == "play-0-0"
    assert usage["local_attack_kill"]["damage"] == 31
    assert usage["local_attack_kill"]["removed_attack"] == 11


def test_regent_projects_forge_only_before_the_visible_blade():
    enemy = beast([{"type": "Attack", "damage": 18, "hits": 1, "total_damage": 18}])[0]
    enemy["hp"] = 36
    hand = [
        card(0, "SOVEREIGN_BLADE", 2, "Retain.\nDeal 22 damage.", "Attack", "AnyEnemy"),
        card(1, "WROUGHT_IN_WAR", 1, "Deal 9 damage.\nForge 9.", "Attack", "AnyEnemy"),
    ]
    state = snapshot(hand, [enemy], energy=3)
    line, = combat_tactics(state)["known_lethal_lines"]
    assert (line["choices"], line["damage"], line["removed_attack"]) == ([2, 1], 40, 18)
    state["state"]["player"]["powers"] = [{"id": "WEAK_POWER", "amount": 1}]
    assert "known_lethal_lines" not in combat_tactics(state)


def test_regent_reorders_the_same_offensive_plan_before_spending_energy(monkeypatch):
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock

    import steam_mod_agent as agent

    hand = [
        card(0, "WROUGHT_IN_WAR", 1, "Deal 9 damage.\nForge 9.", "Attack", "AnyEnemy"),
        card(1, "SOVEREIGN_BLADE", 2, "Retain.\nDeal 15 damage.", "Attack", "AnyEnemy"),
        card(2, "GUIDING_STAR", 1, "Deal 12 damage.\nNext turn, draw 2 cards.", "Attack", "AnyEnemy", star_cost=1),
        card(3, "FALLING_STAR", 0, "Deal 8 damage.\nApply 1 Weak.\nApply 1 Vulnerable.",
             "Attack", "AnyEnemy", star_cost=2),
    ]
    enemy = beast([{"type": "Attack", "damage": 9, "hits": 1, "total_damage": 9}])[0]
    enemy["hp"] = 87
    state = snapshot(hand, [enemy], energy=4)
    state["state"].update(stars=4, turn=2)
    line, = combat_tactics(state)["ordered_attack_lines"]
    assert (line["damage"], line["choices"]) == (75, [4, 1, 2, 3])
    proposed = SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
        content=json.dumps({"choice": 1, "sequence": [1, 2, 3, 4]})))
    request = Mock(return_value=SimpleNamespace(choices=[proposed], usage=None))
    monkeypatch.setattr(agent, "request_choice", request)
    action, _, usage = agent.choose(None, state, [], "")
    assert action == "play-3-0"
    assert usage["optimized_attack_order"] == [4, 1, 2, 3]
    request.assert_called_once()


def test_killing_one_attacker_can_save_more_hp_than_blocking_everyone():
    import steam_mod_agent as agent

    hits = lambda amount: [{"type": "Attack", "damage": amount, "hits": 1, "total_damage": amount}]
    rock = {**beast(hits(11))[0], "hp": 27}
    egg = {**beast(hits(5))[0], "index": 1, "hp": 21}
    hand = [
        card(0, "GATHER_LIGHT", 1, "Gain 10 Block."),
        card(1, "SOVEREIGN_BLADE", 2, "Deal 28 damage.", "Attack", "AnyEnemy"),
    ]
    state = snapshot(hand, [rock, egg], hp=45, energy=2)
    state["run"] = {"character": "CHARACTER.REGENT"}
    tactics = combat_tactics(state)
    assert tactics["known_defense_line"]["hp_loss"] == 6
    line = agent._regent_kill_preventing_damage(state, tactics)
    assert line["target_index"] == rock["index"]
    assert line["hp_loss_with_remaining_block"] == 5
    assert "followup_block_choices" not in line


def test_duplicator_is_held_for_a_better_copy_than_a_small_defend():
    import steam_mod_agent as agent

    hand = [card(0, "DEFEND_REGENT", 1, DEFEND), card(1, "DEFEND_REGENT", 1, DEFEND)]
    potion = {"id": "potion", "kind": "use_potion", "detail": {"potion_id": "DUPLICATOR"}}
    enemy = beast([{"type": "Attack", "damage": 23, "hits": 1, "total_damage": 23}])
    state = snapshot(hand, enemy, hp=28, energy=3, extra_actions=[potion])
    tactics = combat_tactics(state)
    assert tactics["known_defense_line"]["hp_loss"] == 13
    assert agent._save_duplicator(state["actions"], 3, [3, 1], tactics, 28) == 1
    assert agent._save_duplicator(state["actions"], 3, [3, 1], tactics, 13) is None


def test_regent_defense_line_reserves_stars_and_values_only_potion_block_needed():
    hand = [
        card(0, "GATHER_LIGHT", 1, "Gain 8 Block.\nGain 1 Star."),
        card(1, "PARTICLE_WALL", 0, "Gain 9 Block.\nReturn this card to your Hand."),
    ]
    hand[1]["star_cost"] = 2
    potion = {"kind": "use_potion", "id": "block",
              "detail": {"potion_id": "BLOCK_POTION", "description": "Gain 12 Block."}}
    state = snapshot(hand, beast([{"type": "Attack", "total_damage": 22}]), hp=6,
                     energy=1, extra_actions=[potion])
    state["state"]["stars"] = 2
    tactics = combat_tactics(state)
    assert tactics["known_defense_line"] == {"choices": [1, 2], "energy": 1, "stars": 2, "hp_loss": 5}
    assert tactics["potion_timing"] == [
        {"choice": 3, "saves_after_known_card_defense": 5, "prevents_lethal": False}]
    state["state"]["stars"] = 1
    tactics = combat_tactics(state)
    assert tactics["known_defense_line"]["hp_loss"] == 14
    assert tactics["potion_timing"][0]["prevents_lethal"]



def test_poison_notes_only_remove_the_attacks_of_enemies_it_will_kill():
    enemies = [
        {"index": 0, "hp": 5, "block": 15, "powers": [{"id": "POISON_POWER", "amount": 5}],
         "intents": [{"type": "Attack", "total_damage": 20}]},
        {"index": 1, "hp": 20, "powers": [], "intents": [{"type": "Attack", "total_damage": 10}]},
    ]
    result = combat_tactics(snapshot([], enemies))["poison_before_enemy_actions"]
    assert result["kills_before_acting"] == [{"target_index": 0, "hp": 5, "stacks": 5, "ticks": 1, "damage": 5}]
    assert not result["safe_to_finish"] and result["remaining_shown_attack_damage"] == 10



def test_guard_points_block_and_weak_at_the_attacking_enemy():
    defy = card(0, "DEFY", 1, "[gold]Ethereal[/gold].\nGain 6 [gold]Block[/gold].\nApply 1 [gold]Weak[/gold].",
                target="AnyEnemy")
    enemies = [
        {"index": 0, "hp": 42, "powers": [], "intents": [{"type": "Debuff"}]},
        {"index": 1, "hp": 45, "powers": [], "intents": [
            {"type": "Attack", "damage": 15, "hits": 1, "total_damage": 15}
        ]},
    ]
    state = snapshot([defy], enemies, energy=6, hp=31, block=5, extra_actions=[play(defy, 1)])
    guard = end_turn_guard(state)
    assert guard["choice"] == 2 and guard["block"] == 6
    assert guard["estimated_weak_reduction"] == 4 and guard["estimated_hp_saved"] == 10
    enemies[1]["powers"].append({"id": "ARTIFACT_POWER", "amount": 1})
    guard = end_turn_guard(state)
    assert guard["estimated_hp_saved"] == 6 and "estimated_weak_reduction" not in guard



def test_doom_reaching_hp_keeps_the_attack_until_after_enemy_actions():
    enemy = {"index": 0, "hp": 10, "block": 0, "powers": [{"id": "DOOM_POWER", "amount": 10}],
             "intents": [{"type": "Attack", "damage": 13, "hits": 1, "total_damage": 13}]}
    state = snapshot([card(0, "DEFEND_NECROBINDER", 1, DEFEND)], [enemy], hp=10)
    state["state"]["encounter"] = "SAMPLE_NORMAL"
    summary = combat_tactics(state)
    assert summary["doom_after_enemy_actions"] == [
        {"target_index": 0, "hp": 10, "stacks": 10, "additional_doom_needed": 0, "shown_attack_damage": 13}
    ]
    assert summary["shown_attack_lethal"] and summary["unblocked_now"] == 13
    assert "poison_before_enemy_actions" not in summary
    assert end_turn_guard(state)["estimated_hp_saved"] == 5

    enemy["powers"].append({"id": "POISON_POWER", "amount": 10})
    summary = combat_tactics(state)
    assert summary["poison_before_enemy_actions"]["safe_to_finish"]
    assert summary["poison_before_enemy_actions"]["remaining_shown_attack_damage"] == 0


def test_speed_potion_under_frail_respects_bound():
    hand = [
        card(0, "CHO_READY", 1, "Gain [red]8[/red] Block.\nGain 5 Aim."),
        card(1, "CHO_BARBS", 1, "Gain [red]6[/red] Block.\nGain 4 Thorns."),
        card(2, "DEFEND_FOOL", 1, "Gain [red]6[/red] Block."),
    ]
    for item in hand[:2]:
        item["affliction"] = {"id": "BOUND"}
    speed = {"id": "speed", "kind": "use_potion", "detail": {
        "potion_id": "SPEED_POTION",
        "description": "Gain 5 Dexterity. At the end of your turn, lose 5 Dexterity.",
    }}
    current = snapshot(hand, beast([{"type": "Attack", "total_damage": 24}]), hp=8,
                       energy=3, extra_actions=[speed])
    current["state"]["player"]["powers"] = [
        {"id": "CHAINS_OF_BINDING_POWER", "amount": 3}, {"id": "FRAIL_POWER", "amount": 99},
    ]
    tactics = combat_tactics(current)
    assert tactics["known_defense_line"]["choices"] == [1, 3]
    assert tactics["potion_timing"][0]["saves_after_known_card_defense"] == 6
    assert tactics["potion_timing"][0]["prevents_lethal"]
    assert tactics["defense_buff_combos"][0]["duration"] == "this_turn"


def test_visible_hp_budget_at_full_and_low_health():
    key = "hp_loss_if_turn_ends_now"
    def loss(hp, hit):
        return combat_tactics(snapshot([], beast([{"type": "Attack", "total_damage": hit}]), hp=hp))
    assert key not in loss(85, 5)
    assert loss(85, 10)[key] == "noticeable"
    assert loss(85, 15)[key] == "heavy"
    assert loss(20, 5)[key] == "heavy"
