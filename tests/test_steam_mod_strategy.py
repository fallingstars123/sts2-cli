"""Deck evidence and draw probabilities fed to the Steam agent."""

from itertools import combinations
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from steam_mod_strategy import archetype_assessment, card_pick_advice


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
