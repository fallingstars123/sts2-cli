"""Deck evidence and draw probabilities fed to the Steam agent."""

from itertools import combinations
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from steam_mod_strategy import archetype_assessment, card_pick_advice, sealed_draft_action


def snapshot(deck, **fields):
    return {"screen": "card_reward", "run": {"character": "CHARACTER.SILENT", "deck": deck}, **fields}


def test_offered_and_generated_cards_do_not_count_as_deck_evidence():
    state = snapshot(
        [{"id": "STRIKE_SILENT", "count": 5}],
        state={"hand": [{"id": "SHIV"}], "cards": [{"id": "ACCURACY"}]},
        actions=[{"kind": "pick_card_reward", "detail": {"card": {"id": "BLADE_DANCE"}}}],
    )
    assert archetype_assessment(state)["archetypes"] == []
    assert archetype_assessment(snapshot([{"id": "LEADING_STRIKE", "count": 0}])) == {}
    assert archetype_assessment(snapshot([{"id": "LEADING_STRIKE", "count": "2"}])) == {}


def test_copies_contribute_to_draw_odds_without_implying_independent_support():
    state = snapshot([{"id": "CARD.LEADING_STRIKE", "count": 2},
                      {"id": "LEADING_STRIKE", "count": 1, "is_upgraded": True},
                      {"id": "STRIKE_SILENT", "count": 7}])
    result = archetype_assessment(state)
    shivs, = result["archetypes"]
    assert result["deck_size"] == 10
    assert shivs["evidence"] == "limited"
    assert shivs["owned_enablers"] == {"LEADING_STRIKE": 3}
    assert shivs["missing_roles"] == ["payoffs"]
    assert shivs["sample_probability_pct"] == {"enabler": 91.7, "payoff": 0.0, "both_roles": 0.0}


def test_hybrid_deck_keeps_both_directions():
    state = snapshot([{"id": card} for card in
                      ("LEADING_STRIKE", "STORM_OF_STEEL", "ACCURACY",
                       "BOUNCING_FLASK", "NOXIOUS_FUMES", "ACCELERANT")])
    candidates = {entry["name"]: entry for entry in archetype_assessment(state)["archetypes"]}
    for name in ("Shivs", "Poison"):
        assert candidates[name]["evidence"] == "supported"
        assert candidates[name]["missing_roles"] == []


def test_dual_role_card_draw_odds_match_enumeration():
    cards = ["FAN_OF_KNIVES", "LEADING_STRIKE", "ACCURACY", "NEUTRALIZE",
             "STRIKE_SILENT", "STRIKE_SILENT", "STRIKE_SILENT"]
    assessment = archetype_assessment(snapshot([{"id": card} for card in cards]))
    shivs, = assessment["archetypes"]
    samples = list(combinations(cards, assessment["uniform_sample_size"]))
    both = sum(bool({"FAN_OF_KNIVES", "LEADING_STRIKE"}.intersection(hand))
               and bool({"FAN_OF_KNIVES", "ACCURACY"}.intersection(hand)) for hand in samples)
    assert shivs["sample_probability_pct"]["both_roles"] == round(100 * both / len(samples), 1)



def regent_card_reward(*cards):
    visible = [{"id": card, "description": f"Live description for {card}."} for card in cards]
    return {
        "screen": "card_reward",
        "run": {"character": "CHARACTER.REGENT", "act": 1,
                "deck": [{"id": "CARD.PHOTON_CUT", "count": 2}, {"id": "VENERATE"}]},
        "state": {"cards": visible},
        "actions": [{"id": f"pick.{index}", "kind": "pick_card_reward", "detail": card}
                    for index, card in enumerate(visible)] + [
                        {"id": "skip", "kind": "card_reward_alternative", "detail": {"title": "Skip"}},
                    ],
    }


def test_regent_names_and_role_examples_retain_the_live_choice_number():
    advice = card_pick_advice(regent_card_reward("REFINE_BLADE", "PHOTON_CUT", "UNLISTED_CARD"))
    named, = advice["named_picks"]
    assert (named["choice"], named["card_id"], named["owned_copies"]) == (2, "PHOTON_CUT", 2)
    example, = advice["role_matches"]
    assert (example["choice"], example["card_id"]) == (1, "REFINE_BLADE")
    assert {"Star to energy and burst", "Defend and Forge"} <= {
        direction["name"] for direction in advice["build_directions"]
    }
    unmatched = card_pick_advice(regent_card_reward("UNLISTED_CARD"))
    assert unmatched.get("build_directions") and "named_picks" not in unmatched


def test_regent_shop_advice_excludes_unavailable_cards_and_other_screens():
    state = {
        **regent_card_reward("ARSENAL"),
        "screen": "shop",
        "actions": [
            {"kind": "buy_shop_item", "detail": {"type": "card", "affordable": False, "card": {"id": "ARSENAL"}}},
            {"kind": "buy_shop_item", "detail": {"type": "relic", "item": "MOCK"}},
            {"kind": "buy_shop_item", "detail": {"type": "card", "affordable": True, "card": {"id": "REFLECT"}}},
        ],
    }
    advice = card_pick_advice(state)
    named, = advice["named_picks"]
    assert (named["choice"], named["card_id"]) == (3, "REFLECT")
    assert "Card creation" not in {direction["name"] for direction in advice["build_directions"]}
    assert card_pick_advice({**state, "screen": "combat"}) == {}
    assert card_pick_advice({**state, "run": {"character": "CHARACTER.UNKNOWN"}}) == {}


def test_regent_recommendations_share_the_models_numbered_card_choices():
    import steam_mod_agent as agent

    snapshot = regent_card_reward("UNLISTED_CARD", "HIDDEN_CACHE")
    def request(_client, instructions, data, _high_risk, **_options):
        context = json.loads(data)
        named, = context["card_pick_advice"]["named_picks"]
        choice = named["choice"]
        offered = context["actions"][choice - 1]
        assert context["state"]["cards"][offered["detail"]["card_option_index"]]["id"] == "HIDDEN_CACHE"
        assert "Use build_directions for any available card" in instructions
        return SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"choice":2}'))],
            usage=None,
        )
    with patch.object(agent, "request_choice", side_effect=request):
        assert agent.choose(None, snapshot, [], "")[0] == "pick.1"


def test_five_character_recommendations_match_only_live_and_affordable_choices():
    cases = (
        ("IRONCLAD", "POMMEL_STRIKE", "HEMOKINESIS", "Act 1 survival"),
        ("SILENT", "STORM_OF_STEEL", "LEADING_STRIKE", "Shivs"),
        ("DEFECT", "ROCKET_PUNCH", "HOLOGRAM", "Status cards"),
        ("NECROBINDER", "GRAVE_WARDEN", "PULL_AGGRO", "Souls and energy"),
        ("THE_FOOL", "QUICK_SHOT", "ARCHERY", "Arrow shot loop"),
    )
    for character, named_id, example_id, direction in cases:
        reward = regent_card_reward("UNLISTED_CARD", example_id, named_id)
        reward["run"] = {
            "character": f"CHARACTER.{character}",
            "act": 1,
            "deck": [{"id": f"CARD.{named_id}", "count": 2}],
        }
        advice = card_pick_advice(reward)
        named, = advice["named_picks"]
        example, = advice["role_matches"]
        assert (named["choice"], named["card_id"], named["owned_copies"]) == (3, named_id, 2)
        assert (example["choice"], example["card_id"], example["owned_copies"]) == (2, example_id, 0)
        assert direction in {item["name"] for item in advice["build_directions"]}

        shop = {
            **reward,
            "screen": "shop",
            "actions": [
                {"kind": "buy_shop_item",
                 "detail": {"type": "card", "affordable": False, "card": {"id": named_id}}},
                {"kind": "buy_shop_item", "detail": {"type": "relic", "item": "MOCK"}},
                {"kind": "buy_shop_item",
                 "detail": {"type": "card", "affordable": True, "card": {"id": example_id}}},
            ],
        }
        shop_advice = card_pick_advice(shop)
        shop_example, = shop_advice["role_matches"]
        assert shop_example["choice"] == 3
        assert "named_picks" not in shop_advice

        unmatched = card_pick_advice({**reward, "actions": reward["actions"][:1]})
        assert unmatched.get("build_directions")
        assert "named_picks" not in unmatched and "role_matches" not in unmatched


def test_daily_necrobinder_sealed_draft_fills_ten_slots_with_the_doom_deck():
    names = (
        "BLIGHT_STRIKE DEFILE DEFY DRAIN_POWER FEAR FLATTEN GRAVE_WARDEN GRAVEBLAST "
        "INVOKE NEGATIVE_PULSE POKE PULL_AGGRO REAP REAVE SNAP SOW WISP BONE_SHARDS "
        "BORROWED_TIME CLEANSE DEATHS_DOOR DEATHBRINGER ENFEEBLING_TOUCH HIGH_FIVE "
        "LETHALITY PARSE SHROUD SIC_EM SPUR SQUEEZE"
    ).split()
    costs = {"FLATTEN": 2, "POKE": 0, "PULL_AGGRO": 2, "REAP": 3, "WISP": 0,
             "DEATHBRINGER": 2, "HIGH_FIVE": 2, "SQUEEZE": 3}
    rows = [{"card": {"id": card, "cost": costs.get(card, 1)}, "selected": False} for card in names]
    actions = [{"id": f"card_selection.toggle.{i}", "kind": "toggle_card_choice", "detail": row}
               for i, row in enumerate(rows)]
    reward = {
        "screen": "card_selection",
        "run": {"character": "CHARACTER.NECROBINDER", "game_mode": "daily",
                "floor": 1, "modifiers": ["SEALED_DECK", "SPECIALIZED", "MIDAS"], "deck": []},
        "state": {"cards": rows, "min_select": 10, "max_select": 10, "selected_count": 0},
        "actions": actions,
    }
    assert sealed_draft_action({**reward, "run": {**reward["run"], "game_mode": "standard"}}) is None
    for index in range(10):
        action = sealed_draft_action(reward)
        assert action["detail"]["selected"] is False
        action["detail"]["selected"] = True
        reward["state"]["selected_count"] = index + 1
    assert {row["card"]["id"] for row in rows if row["selected"]} == {
        "BLIGHT_STRIKE", "GRAVE_WARDEN", "INVOKE", "NEGATIVE_PULSE", "REAVE",
        "SOW", "WISP", "DEATHS_DOOR", "DEATHBRINGER", "ENFEEBLING_TOUCH",
    }
    assert sealed_draft_action(reward) is None
    confirm = {"id": "card_selection.confirm.0", "kind": "confirm_card_choice", "detail": {}}
    actions.append(confirm)
    assert sealed_draft_action(reward) is confirm


def test_daily_doom_reward_skips_known_off_build_choices_locally():
    import steam_mod_agent as agent

    deck = ("BLIGHT_STRIKE", "NEGATIVE_PULSE", "DEATHBRINGER", "DEATHS_DOOR",
            "GRAVE_WARDEN", "REAVE", "INVOKE", "WISP", "SOW", "ENFEEBLING_TOUCH")
    reward = necrobinder_reward(deck, "REAP", "GRAVEBLAST", "PULL_FROM_BELOW")
    reward["run"].update(game_mode="daily", modifiers=["SEALED_DECK"])
    with patch.object(agent, "request_choice", side_effect=AssertionError("expected local choice")):
        action, _, usage = agent.choose(None, reward, [], "")
    assert (action, usage["local_recipe_pick"]) == ("skip", "skip_outside_recipe")
    reward["run"]["game_mode"] = "standard"
    assert not card_pick_advice(reward)["recipe"].get("prefer_skip")


def test_daily_doom_skips_saturated_offers_even_after_picking_hang():
    deck = ["BLIGHT_STRIKE", "NEGATIVE_PULSE", "DEATHBRINGER", "DEATHS_DOOR",
            "GRAVE_WARDEN", "REAVE", "INVOKE", "DEFY", "SOW", "HANG"]
    reward = necrobinder_reward(deck, "FLATTEN", "DEFY", "GRAVEBLAST")
    reward["run"].update(game_mode="daily", modifiers=["SEALED_DECK"])
    result = card_pick_advice(reward)["recipe"]
    assert result["direction"] == "Hang" and result["prefer_skip"]

    reward["run"]["deck"] = [card for card in reward["run"]["deck"] if card["id"] != "DEFY"]
    result = card_pick_advice(reward)["recipe"]
    assert not result.get("prefer_skip") and result["preferred_choice"] == 2


def test_fool_reward_tags_cover_melody_before_coda_and_allow_overlap():
    import steam_mod_agent as agent

    reward = regent_card_reward("CODA", "FLORESCENCE", "MELODIC_SHOT", "UNLISTED_CARD")
    reward["run"] = {
        "character": "CHARACTER.FOOL", "act": 2,
        "deck": [{"id": card} for card in
                 ("STRIKE_FOOL", "KI_HOP", "KI_CHANT", "WAH_HAMMER", "CHO_BARBS")],
    }

    def request(_client, instructions, data, _high_risk, **_options):
        context = json.loads(data)
        picks = context["card_pick_advice"]["archetype_matches"]
        assert picks[0] == {
            "choice": 1, "card_id": "CODA",
            "matches": [{"name": "Melody", "roles": ["payoffs"],
                         "deck_evidence": "supported", "new_roles": ["payoffs"]}],
        }
        assert picks[1]["matches"][0]["name"] == "Arrow Shots"
        assert picks[1]["matches"][0]["deck_evidence"] == "unstarted"
        assert {m["name"] for m in picks[2]["matches"]} == {"Arrow Shots", "Melody"}
        assert picks[3]["matches"] == []
        melody, = context["archetype_assessment"]["archetypes"]
        assert melody["owned_role_copies"]["ki"] == 2
        assert melody["owned_role_copies"]["wah"] == 1
        assert melody["owned_role_copies"]["cho"] == 1
        assert melody["owned_payoffs"] == {}
        assert "precomputed build tags" in instructions
        return SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"choice":1}'))],
            usage=None,
        )

    with patch.object(agent, "request_choice", side_effect=request):
        assert agent.choose(None, reward, [], "")[0] == "pick.0"


def test_fool_reward_detects_the_missing_melody_without_counting_offers():
    reward = regent_card_reward("CHO_READY", "WAH_SWEEP")
    reward["run"] = {
        "character": "CHARACTER.FOOL", "act": 1,
        "deck": [{"id": card} for card in ("KI_HOP", "WAH_HAMMER", "CODA")],
    }
    melody, = archetype_assessment(reward)["archetypes"]
    assert melody["missing_roles"] == ["cho"]
    assert melody["owned_role_copies"]["cho"] == 0
    cho, wah = card_pick_advice(reward)["archetype_matches"]
    assert cho["matches"][0]["new_roles"] == ["cho"]
    assert wah["matches"][0]["new_roles"] == []


def test_regent_recipe_fills_the_conversion_gap_and_skips_filler():
    import steam_mod_agent as agent

    state = regent_card_reward("CRESCENT_SPEAR", "ALIGNMENT", "GLOW")
    state["run"].update(act=2, deck=[
        {"id": "STRIKE_REGENT", "count": 3}, {"id": "DEFEND_REGENT", "count": 4},
        {"id": "SHINING_STRIKE"}, {"id": "HIDDEN_CACHE"},
        {"id": "PHOTON_CUT", "count": 2}, {"id": "GLIMMER"},
        {"id": "RADIATE"}, {"id": "GATHER_LIGHT"}, {"id": "KNOW_THY_PLACE"},
    ])
    with patch.object(agent, "request_choice", side_effect=AssertionError("recipe is a local choice")):
        advice = card_pick_advice(state)["recipe"]
        assert advice["owned_roles"]["energy_conversion"] == 0
        assert advice["five_card_sample_pct"]["energy_conversion"] == 0.0
        assert advice["preferred_choice"] == 2 and advice["fills"] == "energy_conversion"
        action, _, usage = agent.choose(None, state, [], "")
        assert (action, usage["local_recipe_pick"]) == ("pick.1", "energy_conversion")

        filled = {**state, "run": {**state["run"], "deck": [*state["run"]["deck"], {"id": "ALIGNMENT"}]}}
        action, _, usage = agent.choose(None, filled, [], "")
        assert (action, usage["local_recipe_pick"]) == ("skip", "skip_outside_recipe")


def test_regent_first_act_picks_damage_before_more_setup_when_only_starters_attack():
    state = regent_card_reward("GLIMMER", "ASTRAL_PULSE", "CELESTIAL_MIGHT")
    state["run"]["deck"] = [
        {"id": "STRIKE_REGENT", "count": 2}, {"id": "DEFEND_REGENT", "count": 4},
        *({"id": card} for card in ("VENERATE", "FALLING_STAR", "GATHER_LIGHT", "CLOAK_OF_STARS")),
    ]
    recipe = card_pick_advice(state)["recipe"]
    assert recipe["owned_roles"]["first_act_damage"] == 0
    assert (recipe["preferred_choice"], recipe["fills"]) == (3, "first_act_damage")

    state["run"]["deck"].extend({"id": card} for card in ("CELESTIAL_MIGHT", "STARDUST"))
    recipe = card_pick_advice(state)["recipe"]
    assert recipe["owned_roles"]["first_act_damage"] == 2
    assert (recipe["preferred_choice"], recipe["fills"]) == (1, "draw")


def test_regent_first_act_uses_star_supply_without_requiring_alignment_for_stardust():
    state = regent_card_reward("STARDUST", "GLITTERSTREAM", "CONVERGENCE")
    state["run"]["deck"] = [{"id": card} for card in ("FALLING_STAR", "VENERATE", "GATHER_LIGHT")]
    recipe = card_pick_advice(state)["recipe"]
    assert recipe["owned_roles"]["energy_conversion"] == 0
    assert (recipe["preferred_choice"], recipe["fills"]) == (1, "first_act_damage")
    state["run"]["deck"].pop()
    assert card_pick_advice(state)["recipe"]["prefer_skip"]


def test_regent_first_act_can_take_forge_damage_without_buying_transition_cards():
    state = regent_card_reward("BULWARK", "GLIMMER")
    state["run"]["deck"] = [
        {"id": card} for card in ("VENERATE", "FALLING_STAR", "CELESTIAL_MIGHT", "GATHER_LIGHT", "CLOAK_OF_STARS")
    ]
    recipe = card_pick_advice(state)["recipe"]
    assert recipe["owned_roles"]["efficient_defense"] == 2
    assert (recipe["preferred_choice"], recipe["fills"]) == (1, "first_act_damage")

    state["screen"] = "shop"
    state["actions"] = [
        {"kind": "buy_shop_item", "detail": {"type": "card", "card": card, "affordable": True}}
        for card in state["state"]["cards"]
    ]
    assert card_pick_advice(state)["shop_purchase_choices"] == []


def test_regent_keeps_immediate_draw_separate_from_delayed_or_expensive_cards():
    state = regent_card_reward("GLIMMER", "PARRY", "CHILD_OF_THE_STARS")
    state["run"].update(act=2, deck=[
        {"id": "STRIKE_REGENT", "count": 3}, {"id": "DEFEND_REGENT", "count": 4},
        {"id": "HIDDEN_CACHE"}, {"id": "PHOTON_CUT"}, {"id": "GUIDING_STAR"},
        {"id": "DECISIONS_DECISIONS"}, {"id": "BLACK_HOLE"},
    ])
    advice = card_pick_advice(state)
    assert advice["recipe"]["preferred_choice"] == 1
    assert advice["recipe"]["owned_roles"]["draw"] == 0
    coverage = advice["hand_role_coverage"]
    assert coverage["current_pct"]["cycle"] == 0
    assert coverage["after_picks"][0]["delta_pct_points"]["cycle"] == 38.5

    finisher = regent_card_reward("COLLISION_COURSE", "RADIATE")
    finisher["run"] = {**state["run"], "deck": [*state["run"]["deck"], {"id": "ALIGNMENT"}]}
    recipe = card_pick_advice(finisher)["recipe"]
    assert recipe["owned_roles"]["sustained_damage"] == 1
    assert (recipe["preferred_choice"], recipe["fills"]) == (2, "damage_payoff")


def test_regent_forge_progression_uses_owned_cards_from_the_winning_run():
    deck = [
        {"id": "STRIKE_REGENT", "count": 2}, {"id": "DEFEND_REGENT", "count": 3},
        *({"id": card} for card in ("FALLING_STAR", "VENERATE", "KNOW_THY_PLACE")),
    ]
    cases = [
        (1, ("REFINE_BLADE", "TERRAFORMING", "GLITTERSTREAM"), "REFINE_BLADE"),
        (1, ("GLOW", "GLITTERSTREAM", "CONVERGENCE"), "GLOW"),
        (1, ("PARRY", "BULWARK", "PHOTON_CUT"), "PARRY"),
        (1, ("THE_SMITH", "SWORD_SAGE", "ROYALTIES"), "THE_SMITH"),
        (3, ("CONQUEROR", "CLOAK_OF_STARS", "REFINE_BLADE"), "CONQUEROR"),
        (3, ("CHARGE", "MONARCHS_GAZE", "PHOTON_CUT"), None),
    ]
    for act, offers, expected in cases:
        if expected == "THE_SMITH":
            deck.extend({"id": card} for card in ("SPOILS_OF_BATTLE", "HIDDEN_CACHE"))
        reward = regent_card_reward(*offers)
        reward["run"].update(act=act, deck=deck)
        advice = card_pick_advice(reward)
        recipe = advice["recipe"]
        if expected is None:
            assert recipe["prefer_skip"]
            continue
        assert offers[recipe["preferred_choice"] - 1] == expected
        assert recipe["name"] == ("Regent Forge" if expected in {"PARRY", "THE_SMITH", "CONQUEROR"}
                                  else "Regent Star cycle")
        deck.append({"id": expected})


def test_regent_forge_shop_opens_only_a_needed_card_with_the_removal_budget_reserved():
    from steam_mod_shop import item_actions

    reward = regent_card_reward("FURNACE", "COLLISION_COURSE", "GLIMMER")
    reward.update(screen="shop")
    reward["run"].update(act=2, gold=110, deck=[
        {"id": card} for card in (
            "STRIKE_REGENT", "REFINE_BLADE", "SPOILS_OF_BATTLE", "PARRY", "GLOW",
            "HIDDEN_CACHE", "THE_SMITH", "ROYAL_GAMBLE",
        )
    ])
    reward["actions"] = [
        {"id": card["id"], "kind": "buy_shop_item",
         "detail": {"type": "card", "affordable": True, "cost": 36, "card": card}}
        for card in reward["state"]["cards"]
    ]
    reward["actions"].append({"id": "remove", "kind": "buy_shop_item",
                              "detail": {"type": "card_removal", "cost": 75, "affordable": True}})
    assert [a["id"] for a in item_actions(reward)] == ["remove"]
    reward["run"]["gold"] += 1
    assert [a["id"] for a in item_actions(reward)] == ["FURNACE", "remove"]
    reward["run"]["deck"].append({"id": "FURNACE"})
    assert [a["id"] for a in item_actions(reward)] == ["remove"]


def test_regent_forge_takes_one_alignment_when_star_supply_supports_it():
    reward = regent_card_reward("ALIGNMENT", "FURNACE", "PHOTON_CUT")
    reward["run"].update(act=3, deck=[
        {"id": card} for card in ("REFINE_BLADE", "SPOILS_OF_BATTLE", "PARRY", "GLOW")
    ])
    assert card_pick_advice(reward)["recipe"]["preferred_choice"] == 2
    reward["run"]["deck"].append({"id": "HIDDEN_CACHE"})
    recipe = card_pick_advice(reward)["recipe"]
    assert (recipe["preferred_choice"], recipe["fills"]) == (1, "energy_conversion")
    reward["run"]["deck"].append({"id": "ALIGNMENT"})
    assert card_pick_advice(reward)["recipe"]["preferred_choice"] == 2

    reward["run"]["deck"].pop()
    reward["screen"] = "shop"
    reward["actions"] = [
        {"kind": "buy_shop_item", "detail": {"type": "card", "card": card, "affordable": True}}
        for card in reward["state"]["cards"]
    ]
    assert card_pick_advice(reward)["shop_purchase_choices"] == [1]
    reward["run"]["act"] = 2
    assert card_pick_advice(reward)["shop_purchase_choices"] == [2]


def test_regent_forge_prices_one_swing_and_excludes_one_time_stars():
    reward = regent_card_reward("ALIGNMENT", "GAMMA_BLAST")
    reward["run"].update(act=3, deck=[
        *({"id": card} for card in (
            "VENERATE", "REFINE_BLADE", "SPOILS_OF_BATTLE", "PARRY", "THE_SMITH",
            "ROYAL_GAMBLE", "CONQUEROR", "HIDDEN_CACHE", "SHINING_STRIKE",
        )),
        {"id": "GLOW", "is_upgraded": True},
    ])
    advice = card_pick_advice(reward)
    assert advice["forge_cycle_budget"] == {
        "repeatable_stars_per_deck_pass": 10,
        "core_stars_per_deck_pass": 4,
        "stars_after_core": 6,
        "base_energy_for_one_swing": 3,
        "base_energy_with_same_turn_smith": 4,
    }
    assert advice["recipe"]["preferred_choice"] == 1

    reward["run"]["deck"] = [
        card for card in reward["run"]["deck"] if card["id"] not in {"HIDDEN_CACHE", "SHINING_STRIKE"}
    ]
    advice = card_pick_advice(reward)
    assert advice["forge_cycle_budget"]["stars_after_core"] == 0
    assert advice["recipe"]["prefer_skip"]


def test_regent_keeps_an_established_star_engine_with_only_one_forge_card():
    reward = regent_card_reward("PARRY", "RADIATE")
    reward["run"].update(act=2, deck=[
        {"id": card} for card in ("ALIGNMENT", "GLOW", "BLACK_HOLE", "BULWARK")
    ])
    advice = card_pick_advice(reward)
    assert advice["recipe"]["name"] == "Regent Star cycle"
    assert advice["trap_choices"] == [1]
    assert advice["recipe"]["preferred_choice"] == 2


def test_event_recipe_counts_pending_picks_and_only_selects_additions():
    import steam_mod_agent as agent

    state = regent_card_reward("GUIDING_STAR", "PHOTON_CUT", "HIDDEN_CACHE", "GLOW", "WROUGHT_IN_WAR")
    state["screen"] = "card_selection"
    state["run"].update(room_event_id="ROOM_FULL_OF_CHEESE", deck=[
        {"id": "STRIKE_REGENT", "count": 4}, {"id": "DEFEND_REGENT", "count": 4},
        {"id": "GATHER_LIGHT"}, {"id": "WROUGHT_IN_WAR"}, {"id": "ORBIT"},
        {"id": "DECISIONS_DECISIONS"}, {"id": "FALLING_STAR"},
    ])
    rows = [{"card": card, "selected": False} for card in state["state"]["cards"]]
    state["state"] = {
        "mode": "NSimpleCardSelectScreen", "selected_count": 0, "cards": rows,
        "instructions": "Choose [blue]2[/blue] Common Cards to Add to Your [gold]Deck[/gold].",
    }
    state["actions"] = [{"id": f"toggle.{index}", "kind": "toggle_card_choice", "detail": row.copy()}
                        for index, row in enumerate(rows)]
    with patch.object(agent, "request_choice", side_effect=AssertionError("event picks should be local")):
        assert agent.choose(None, state, [], "")[0] == "toggle.3"
        rows[3]["selected"] = state["actions"][3]["detail"]["selected"] = True
        state["state"]["selected_count"] = 1
        state["state"]["instructions"] = (
            "\u9009\u62e9[blue]2[/blue]\u5f20\u666e\u901a\u724c\u52a0\u5165\u5230\u4f60\u7684[gold]\u724c\u7ec4[/gold]\u3002"
        )
        advice = card_pick_advice(state)
        assert advice["recipe"]["owned_roles"]["star_supply"] == 2
        assert advice["recipe"]["owned_roles"]["draw"] == 1
        assert agent.choose(None, state, [], "")[0] == "toggle.1"
        assert all(card["id"] != "GLOW" for card in state["run"]["deck"])

    state["state"]["mode"] = "NDeckTransformSelectScreen"
    assert card_pick_advice(state) == {}


def test_orbit_is_only_a_persistent_energy_pick_after_the_engine_is_present():
    state = regent_card_reward("ORBIT", "GUIDING_STAR")
    state["run"].update(act=2, deck=[
        {"id": "STRIKE_REGENT", "count": 4}, {"id": "DEFEND_REGENT", "count": 4},
        {"id": "GATHER_LIGHT"},
    ])
    advice = card_pick_advice(state)
    assert advice["recipe"]["fills"] == "next_turn_draw"
    assert advice["hand_role_coverage"]["after_picks"][0]["delta_pct_points"]["cycle"] == 0
    state["run"]["deck"].extend({"id": card} for card in ("GLOW", "ALIGNMENT", "GUIDING_STAR"))
    assert card_pick_advice(state)["recipe"]["fills"] == "persistent_energy"
    state["run"]["deck"].append({"id": "ORBIT"})
    counts = card_pick_advice(state)["recipe"]["owned_roles"]
    assert counts["energy_conversion"] == counts["persistent_energy"] == 1


def test_regent_prefers_forge_draw_and_requires_stars_before_royal_gamble():
    state = regent_card_reward("QUASAR", "SPOILS_OF_BATTLE", "SHINING_STRIKE")
    state["run"].update(act=2, deck=[
        {"id": "DEFEND_REGENT", "count": 3}, {"id": "WROUGHT_IN_WAR", "count": 2},
        {"id": "GATHER_LIGHT"}, {"id": "FALLING_STAR"}, {"id": "GUIDING_STAR"},
        {"id": "VENERATE"}, {"id": "COLLISION_COURSE"}, {"id": "BIG_BANG"}, {"id": "ORBIT"},
    ])
    recipe = card_pick_advice(state)["recipe"]
    assert (recipe["preferred_choice"], recipe["fills"]) == (2, "draw")

    refill = regent_card_reward("ROYAL_GAMBLE")
    refill["run"] = state["run"]
    assert card_pick_advice(refill)["recipe"]["prefer_skip"]
    refill["run"]["deck"].extend([{"id": "HIDDEN_CACHE"}, {"id": "SPOILS_OF_BATTLE"}])
    recipe = card_pick_advice(refill)["recipe"]
    assert (recipe["preferred_choice"], recipe["fills"]) == (1, "star_refill")


def test_regent_recipe_takes_an_explicit_exception_and_keeps_shop_optional():
    state = regent_card_reward("ALIGNMENT", "BIG_BANG")
    state["run"].update(act=2, deck=[{"id": "STRIKE_REGENT", "count": 4}, {"id": "DEFEND_REGENT", "count": 4},
                                     {"id": "SHINING_STRIKE"}, {"id": "HIDDEN_CACHE"}])
    advice = card_pick_advice(state)["recipe"]
    assert (advice["preferred_choice"], advice["fills"]) == (2, "exception")
    state["screen"] = "shop"
    state["actions"] = [
        {"kind": "buy_shop_item", "detail": {"type": "card", "card": {"id": "BIG_BANG"}, "affordable": False}},
        {"kind": "buy_shop_item", "detail": {"type": "card", "card": {"id": "ALIGNMENT"}, "affordable": True}},
        {"kind": "close_shop", "detail": {}},
    ]
    advice = card_pick_advice(state)["recipe"]
    assert (advice["preferred_choice"], advice["fills"]) == (2, "energy_conversion")



def test_poison_cycle_prefers_the_missing_component_from_the_archived_offers():
    base_deck = ["ACCELERANT", "POISONED_STAB", "DAGGER_THROW"]
    cases = [
        (base_deck, ["DEADLY_POISON", "ADRENALINE", "ACROBATICS"], 2),
        (base_deck + ["BACKFLIP", "DEADLY_POISON"], ["OUTBREAK", "CORROSIVE_WAVE", "STORM_OF_STEEL"], 2),
        (base_deck + ["BACKFLIP", "CORROSIVE_WAVE"], ["CALCULATED_GAMBLE", "DAGGER_THROW", "FLECHETTES"], 1),
        (base_deck + ["BACKFLIP", "DEADLY_POISON", "BOUNCING_FLASK"],
         ["DEADLY_POISON", "BOUNCING_FLASK", "DEFLECT"], 3),
    ]
    for owned, offers, expected_choice in cases:
        replay = snapshot([{"id": card} for card in owned], actions=[
            {"kind": "pick_card_reward", "detail": {"id": card}} for card in offers
        ])
        replay["run"]["act"] = 2
        assert card_pick_advice(replay)["recipe"]["preferred_choice"] == expected_choice


def test_shiv_core_keeps_its_build_when_poison_is_only_secondary():
    replay = snapshot([{"id": card} for card in ("LEADING_STRIKE", "ACCURACY", "POISONED_STAB", "ACCELERANT")],
                      actions=[{"kind": "pick_card_reward", "detail": {"id": "CORROSIVE_WAVE"}}])
    replay["run"]["act"] = 2
    assert "recipe" not in card_pick_advice(replay)



def necrobinder_reward(deck, *offers):
    return snapshot([], run={"character": "CHARACTER.NECROBINDER", "act": 2,
                             "deck": [{"id": card} for card in deck]}, state={}, actions=[
        {"id": f"pick.{index}", "kind": "pick_card_reward", "detail": {"id": card}}
        for index, card in enumerate(offers)
    ] + [{"id": "skip", "kind": "card_reward_alternative", "detail": {"title": "Skip"}}])


def test_necrobinder_recipe_recovers_the_two_missed_engine_picks():
    import steam_mod_agent as agent

    deck = ["STRIKE_NECROBINDER"] * 3 + ["DEFEND_NECROBINDER"] * 4 + [
        "BODYGUARD", "UNLEASH", "REAVE", "GRAVE_WARDEN", "DEFY", "FLATTEN", "SNAP",
    ]
    with patch.object(agent, "request_choice", side_effect=AssertionError("clear gaps are picked locally")):
        floor12 = necrobinder_reward(deck, "REAVE", "SNAP", "GRAVE_WARDEN")
        action, _, usage = agent.choose(None, floor12, [], "")
        assert (action, usage["local_recipe_pick"]) == ("pick.2", "efficient_defense")

        floor19 = necrobinder_reward([*deck, "REAVE", "SIC_EM"], "SNAP", "INVOKE", "BLIGHT_STRIKE")
        action, _, usage = agent.choose(None, floor19, [], "")
        assert (action, usage["local_recipe_pick"]) == ("pick.1", "reusable_energy")


def test_necrobinder_counts_branch_evidence_without_grabbing_unfunded_payoffs():
    base = ["GRAVE_WARDEN", "REAVE", "DEFY"]
    unsupported = necrobinder_reward(base, "DEATHS_DOOR", "HAUNT", "BORROWED_TIME")
    advice = card_pick_advice(unsupported)["recipe"]
    assert "preferred_choice" not in advice and "prefer_skip" not in advice
    assert advice["owned_roles"]["reusable_energy"] == 0

    for added, payoff, expected_direction in (
        (["NEGATIVE_PULSE", "DEATHBRINGER", "OBLIVION"], "DEATHS_DOOR", "Doom defense"),
        (["PARSE", "CAPTURE_SPIRIT"], "HAUNT", "Souls"),
        (["PARSE", "VEILPIERCER", "DEFILE"], "PAGESTORM", "Ethereal"),
        (["FLATTEN", "SIC_EM", "SNAP"], "SPUR", "Osty"),
    ):
        supported = necrobinder_reward([*base, *added], payoff)
        advice = card_pick_advice(supported)["recipe"]
        assert (advice["direction"], advice["preferred_choice"]) == (expected_direction, 1)

    hang = necrobinder_reward([*base, "HANG", "PARSE", "CAPTURE_SPIRIT"], "HAUNT")
    advice = card_pick_advice(hang)["recipe"]
    assert advice["direction"] == "Hang" and "preferred_choice" not in advice



def defect_reward(deck, *offers):
    return snapshot([], run={"character": "CHARACTER.DEFECT", "act": 2,
                             "deck": [{"id": card} for card in deck]}, state={}, actions=[
        {"id": f"pick.{index}", "kind": "pick_card_reward", "detail": {"id": card}}
        for index, card in enumerate(offers)
    ])


def test_defect_recipe_fills_the_recorded_orb_engine_gaps():
    import steam_mod_agent as agent

    start = ["ZAP", "COOLHEADED", "GLACIER", "MOMENTUM_STRIKE"]
    deck = start + ["BALL_LIGHTNING", "COMPILE_DRIVER", "COOLHEADED", "BOOT_SEQUENCE"]
    for owned, offers, index, role in (
        (start, ("STORM", "SCRAPE", "TESLA_COIL"), 2, "targeted_lightning"),
        (deck, ("OVERCLOCK", "COMPILE_DRIVER", "HOLOGRAM"), 0, "fast_draw"),
        (deck, ("CHARGE_BATTERY", "TEMPEST", "FTL"), 0, "efficient_defense"),
        (deck, ("CLAW", "ITERATION", "SYNCHRONIZE"), 2, "mixed_focus"),
    ):
        with patch.object(agent, "request_choice", side_effect=AssertionError("clear gaps are picked locally")):
            action, _, usage = agent.choose(None, defect_reward(owned, *offers), [], "")
        assert (action, usage["local_recipe_pick"]) == (f"pick.{index}", role)


def test_defect_recipe_requires_the_actual_triggers_for_payoffs():
    frost = ["GLACIER", "COOLHEADED", "COLD_SNAP"]
    unsupported = defect_reward(frost + ["ZAP", "OVERCLOCK"], "SYNCHRONIZE", "ITERATION", "CLAW")
    advice = card_pick_advice(unsupported)["recipe"]
    assert "preferred_choice" not in advice and "mixed_focus" not in advice["next_missing_roles"]

    status = defect_reward(["OVERCLOCK", "BOOST_AWAY", "TURBO"], "CLAW", "ITERATION")
    advice = card_pick_advice(status)["recipe"]
    assert (advice["direction"], advice["preferred_choice"]) == ("Status cards", 2)

    few_zero_cards = defect_reward(["BEAM_CELL", "ADAPTIVE_STRIKE", "FERAL"], "SCRAPE", "ALL_FOR_ONE")
    assert "preferred_choice" not in card_pick_advice(few_zero_cards)["recipe"]

    zero_cards = defect_reward(["BEAM_CELL", "GO_FOR_THE_EYES", "FTL"], "SCRAPE", "ALL_FOR_ONE")
    advice = card_pick_advice(zero_cards)["recipe"]
    assert (advice["direction"], advice["preferred_choice"]) == ("Zero-cost replay", 2)
