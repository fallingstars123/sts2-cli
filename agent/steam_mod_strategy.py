"""Assess the owned deck and select relevant Steam strategy advice."""

from collections import Counter
from functools import lru_cache
from itertools import combinations
import json
from math import comb
from pathlib import Path
import re

from steam_mod_prompt import plain_text


PLAYBOOK = Path(__file__).with_name("steam_mod_strategy.json")
MAX_TIPS = 4
SAMPLE_CARDS = 5
ROLE_COVERAGE_TARGET = 80
CARD_TEXT = PLAYBOOK.parent.parent / "localization_eng" / "cards.json"
DRAW_NOW = re.compile(r"(?i)(?:^|[.!]\s+)draw (?:\d+|\{[^}]+\}) (?:cards?\b|\{Cards:plural:[^}]+\})")
PUT_BACK = re.compile(r"put (?:one|1|\{[^}]+\}) cards? from your hand on top of your draw pile", re.IGNORECASE)
ROLE_TEXT = {
    "offense": re.compile(r"(?im)(?:^|[.!]\s+)(?:deal .+? damage|apply .+? (?:poison|doom))\b"),
    "defense": re.compile(r"(?im)(?:^|[.!]\s+)(?:gain .+? block|apply .+? weak)\b"),
    "cycle": re.compile(r"(?i)(?:^|[.!]\s+)gain (?:\d+ energy|\{energy:energyIcons\(\)\}|\[img\][^\n]+energy_icon\.png)"),
}
PURCHASE_EXCEPTIONS = {"OFFERING", "ADRENALINE", "DIVINE_SHOT"}
ALIASES = {"THE_FOOL": "FOOL", "THE_SILENT": "SILENT", "THE_DEFECT": "DEFECT",
           "THE_IRONCLAD": "IRONCLAD", "THE_REGENT": "REGENT", "THE_NECROBINDER": "NECROBINDER"}


@lru_cache(maxsize=1)
def _playbook():
    try:
        book = json.loads(PLAYBOOK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return book if isinstance(book, dict) else {}


def _model_id(value):
    return value.rsplit(".", 1)[-1].strip().replace(" ", "_").upper() if isinstance(value, str) else ""


def _character_entry(section, run, state):
    character = _model_id(run.get("character") or state.get("character"))
    data = _playbook().get(section)
    return data.get(ALIASES.get(character, character)) if isinstance(data, dict) else None


def _card_ids(items):
    if not isinstance(items, list):
        return set()
    return {_model_id(item.get("id")) for item in items
            if isinstance(item, dict) and item.get("id") and item.get("count", 1) != 0}


def _owned_counts(cards):
    if not isinstance(cards, list):
        return {}
    counts = Counter()
    for card in cards:
        if not isinstance(card, dict):
            return {}
        identifier = _model_id(card.get("id"))
        count = card.get("count", 1)
        if not identifier or type(count) is not int or count < 0:
            return {}
        if count:
            counts[identifier] += count
    return counts


def _sample_odds(deck_size, sample_size, enablers, payoffs):
    total = comb(deck_size, sample_size)
    no_enabler = comb(deck_size - enablers.total(), sample_size)
    no_payoff = comb(deck_size - payoffs.total(), sample_size)
    # A card may supply both roles. Union counts that copy once.
    no_components = comb(deck_size - (enablers | payoffs).total(), sample_size)
    return {
        "enabler": round(100 * (total - no_enabler) / total, 1),
        "payoff": round(100 * (total - no_payoff) / total, 1),
        "both_roles": round(100 * (total - no_enabler - no_payoff + no_components) / total, 1),
    }


def _archetype_roles(definition):
    enabler_roles = definition.get("enabler_roles", {"enablers": definition.get("enablers", ())})
    return {**enabler_roles, "payoffs": definition["payoffs"]}


def archetype_assessment(snapshot):
    """Report owned archetype evidence and reference draw odds without replacement."""
    run, state = snapshot.get("run") or {}, snapshot.get("state") or {}
    definitions = _character_entry("archetypes", run, state)
    deck = _owned_counts(run.get("deck"))
    if not isinstance(definitions, dict) or not definitions or not deck:
        return {}

    deck_size = sum(deck.values())
    sample_size = min(SAMPLE_CARDS, deck_size)
    tiers = {"limited": 0, "emerging": 1, "supported": 2}
    candidates = []
    for name, definition in definitions.items():
        groups = _archetype_roles(definition)
        owned_roles = {
            role: Counter({card: deck[card] for card in cards if card in deck})
            for role, cards in groups.items()
        }
        payoffs = owned_roles["payoffs"]
        enablers = Counter()
        for role, cards in owned_roles.items():
            if role != "payoffs":
                enablers |= cards
        distinct = len(enablers | payoffs)
        if not distinct:
            continue
        required_roles = definition.get("required_roles", groups)
        missing = [role for role in required_roles if not owned_roles[role]]
        if distinct >= 3 and not missing:
            evidence = "supported"
        elif distinct >= 2:
            evidence = "emerging"
        else:
            evidence = "limited"
        odds = _sample_odds(deck_size, sample_size, enablers, payoffs)
        candidate = {"name": name, "evidence": evidence,
                     "owned_enablers": dict(enablers), "owned_payoffs": dict(payoffs),
                     "missing_roles": missing, "sample_probability_pct": odds}
        if "enabler_roles" in definition:
            candidate["owned_role_copies"] = {role: cards.total() for role, cards in owned_roles.items()}
        candidates.append((tiers[evidence], distinct, odds["both_roles"], candidate))

    candidates.sort(key=lambda row: row[:3], reverse=True)
    return {"deck_size": deck_size, "uniform_sample_size": sample_size,
            "archetypes": [candidate for _, _, _, candidate in candidates]}


def _available_cards(snapshot, state):
    ids = _card_ids(state.get("hand")) | _card_ids(state.get("cards"))
    for action in snapshot.get("actions") or []:
        if not isinstance(action, dict):
            continue
        detail = action.get("detail", {})
        if not isinstance(detail, dict):
            continue
        if isinstance(card := detail.get("card"), dict):
            ids.add(_model_id(card.get("id")))
        if detail.get("card_id"):
            ids.add(_model_id(detail["card_id"]))
    return ids



def _recipe_branch(branches, owned):
    locked = next((branch for branch in branches if branch.get("locked_by") in owned), None)
    if locked:
        return locked
    scored = [(len(owned.keys() & branch["anchors"]), branch) for branch in branches if "anchors" in branch]
    ranked = sorted((row for row in scored if row[0] >= row[1]["minimum"]),
                    key=lambda row: row[0], reverse=True)
    if ranked and (len(ranked) == 1 or ranked[0][0] > ranked[1][0]):
        return ranked[0][1]
    return None


def _recipe_advice(recipe, owned, offers, act, *, reward_offers=()):
    """Rank known options against the missing steps of the planned build."""
    branch = _recipe_branch(recipe.get("branches", ()), owned)
    stages = recipe["stages"] + (branch["stages"] if branch else [])
    copy_limits = recipe.get("copy_limits", {})
    counts = {stage["role"]: sum(owned.get(card, 0) for card in stage["cards"]) for stage in stages}
    shortages = [stage for stage in stages if counts[stage["role"]] < stage["target"]
                 and all(counts.get(role, 0) >= minimum for role, minimum in stage.get("requires", {}).items())]
    opening = recipe.get("opening", ()) if act == 1 and sum(owned.values()) < 13 else ()
    candidates = []
    missing_roles = [stage["role"] for stage in shortages]
    if act == 1 and reward_offers and (damage := recipe.get("first_act_damage")):
        damage_cards = damage["cards"]
        if counts.get("star_supply", 0):
            damage_cards = [*damage_cards, *damage["star_cards"]]
        counts["first_act_damage"] = sum(owned[card] for card in damage_cards)
        if counts["first_act_damage"] < damage["target"]:
            missing_roles.insert(0, "first_act_damage")
            candidates.extend((1, damage_cards.index(card), choice, "first_act_damage")
                              for choice, card in reward_offers if card in damage_cards and not owned[card])
    for choice, card in offers:
        copies = owned.get(card, 0)
        if card in recipe["exception_cards"] and not copies:
            candidates.append((0, recipe["exception_cards"].index(card), choice, "exception"))
        if card in opening and not copies:
            candidates.append((2, opening.index(card), choice, "opening"))
        for i, stage in enumerate(shortages, 3):
            picks = stage.get("picks", stage["cards"])
            max_copies = copy_limits.get(card, 2 if stage["role"] == "draw" else 1)
            if card in picks and copies < max_copies:
                candidates.append((i, picks.index(card), choice, stage["role"]))
    size = sum(owned.values())
    sample = min(SAMPLE_CARDS, size)
    draw_chances = {role: round(100 * (1 - comb(size - count, sample) / comb(size, sample)), 1)
                    for role, count in counts.items()}
    result = {"name": recipe["name"], "owned_roles": counts, "five_card_sample_pct": draw_chances,
              "next_missing_roles": missing_roles}
    if branch:
        result["direction"] = branch["name"]
    if candidates:
        _, _, choice, reason = min(candidates)
        result.update(preferred_choice=choice, fills=reason)
    return result


def _archetype_matches(definitions, offers, owned, assessment):
    groups = {name: _archetype_roles(definition) for name, definition in definitions.items()}
    evidence = {row["name"]: row["evidence"] for row in assessment.get("archetypes", ())}
    result = []
    for choice, card_id in offers:
        matches = []
        for name, roles in groups.items():
            matching_roles = [role for role, cards in roles.items() if card_id in cards]
            if not matching_roles:
                continue
            match = {"name": name, "roles": matching_roles}
            if owned:
                match["deck_evidence"] = evidence.get(name, "unstarted")
                match["new_roles"] = [
                    role for role in matching_roles if not owned.keys() & roles[role]
                ]
            matches.append(match)
        result.append({"choice": choice, "card_id": card_id, "matches": matches})
    return result


def sealed_draft_action(snapshot):
    """Select an affordable opening deck from a fully exposed daily sealed pool."""
    run, state = snapshot.get("run") or {}, snapshot.get("state") or {}
    if (snapshot["screen"] != "card_selection" or run.get("game_mode") != "daily"
            or "SEALED_DECK" not in (run.get("modifiers") or ())
            or run.get("floor") not in (0, 1) or run.get("deck") != []):
        return None
    rows = state.get("cards") or ()
    count = state.get("max_select")
    if count != 10 or state.get("min_select") != count or len(rows) != 30:
        return None
    if any(not isinstance(row, dict) or type(row.get("selected")) is not bool
           or not isinstance(row.get("card"), dict) for row in rows):
        return None
    selected = [i for i, row in enumerate(rows) if row["selected"]]
    if len(selected) != state.get("selected_count") or len(selected) > count:
        return None
    if len(selected) == count:
        return next((a for a in snapshot["actions"] if a["kind"] == "confirm_card_choice"), None)
    guide = _character_entry("card_recommendations", run, state) or {}
    if not (draft := guide.get("sealed_draft")):
        return None

    cards = [row["card"] for row in rows]
    ids = [_model_id(card.get("id")) for card in cards]
    priorities = {card: i for i, card in enumerate(reversed(draft["priority"]), 1)}
    remaining = count - len(selected)
    options = [i for i, card in enumerate(ids) if card in priorities and i not in selected]
    options.sort(key=lambda i: priorities[ids[i]], reverse=True)
    if len(options) < remaining:
        return None

    # Compare only the leading supported cards. Score group coverage separately from individual power.
    groups = [(set(group["cards"]), group["target"]) for group in draft["groups"]]

    def score(extra):
        deck = [*selected, *extra]
        coverage = sum(min(target, sum(ids[i] in group for i in deck)) for group, target in groups)
        expensive = sum((cards[i].get("cost") or 0) >= 2 for i in deck)
        return sum(priorities.get(ids[i], 0) for i in deck) + 4 * coverage - 3 * max(0, expensive - 1)

    plan = max(combinations(options[:remaining + 5], remaining), key=score)
    chosen = {f"card_selection.toggle.{i}" for i in plan}
    return next((a for a in snapshot["actions"] if a["kind"] == "toggle_card_choice"
                 and a["id"] in chosen and a["detail"].get("selected") is False), None)


@lru_cache(maxsize=1)
def _card_text():
    try:
        table = json.loads(CARD_TEXT.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return table if isinstance(table, dict) else {}


def _coverage_roles(card, named):
    identifier = _model_id(card.get("id"))
    if identifier.startswith(("STRIKE_", "DEFEND_")) or named.get(identifier, ("", ""))[0] == "usually_skip":
        return set()
    # Use the catalog for consistent English semantics across bridge locales.
    text = _card_text().get(identifier + ".description") or card.get("description") or ""
    text = re.sub(r"\[/?(?:gold|blue|green|red|purple)\]", "", text, flags=re.IGNORECASE)
    roles = {role for role, pattern in ROLE_TEXT.items() if pattern.search(text)}
    if identifier != "DECISIONS_DECISIONS" and DRAW_NOW.search(text):
        # A base Photon Cut draws one and parks one. Its upgrade sees an extra card.
        upgraded = card.get("upgraded") or card.get("is_upgraded")
        if not PUT_BACK.search(text) or identifier == "GLIMMER" or identifier == "PHOTON_CUT" and upgraded:
            roles.add("cycle")
    return roles


def _hand_role_coverage(deck, size, offers, named):
    counts = Counter()
    for card in deck:
        for role in _coverage_roles(card, named):
            counts[role] += card.get("count", 1)

    def odds(deck_size, role_count):
        sample = min(deck_size, SAMPLE_CARDS)
        return round(100 * (1 - comb(deck_size - role_count, sample) / comb(deck_size, sample)), 1)

    current = {role: odds(size, counts[role]) for role in ROLE_TEXT}
    deltas = []
    for choice, card in offers.items():
        roles = _coverage_roles(card, named)
        deltas.append({"choice": choice, "delta_pct_points": {
            role: round(odds(size + 1, counts[role] + (role in roles)) - current[role], 1) for role in ROLE_TEXT
        }})
    return {"sample_size": min(size, SAMPLE_CARDS), "current_pct": current, "after_picks": deltas}


def _role_gap_choices(coverage):
    return {row["choice"] for row in coverage["after_picks"]
            if any(delta > 0 and coverage["current_pct"][role] < ROLE_COVERAGE_TARGET
                   for role, delta in row["delta_pct_points"].items())}


def _shop_purchase_choices(act, owned, offers, named, recipe, role_gaps, archetype_matches):
    """Paid candidates are stricter than ordinary reward recommendations."""
    eligible = {choice for choice, card in offers if card in PURCHASE_EXCEPTIONS and not owned[card]}
    if recipe:
        eligible.update(choice for choice, card in offers if card in recipe["exception_cards"] and not owned[card])
        if shop_cards := recipe.get("shop_cards"):
            planned_offers = [(choice, card) for choice, card in offers
                              if card in shop_cards and act >= shop_cards[card] and not owned[card]]
            advice = _recipe_advice(recipe, owned, planned_offers, act)
            if "preferred_choice" in advice:
                eligible.add(advice["preferred_choice"])
            return sorted(eligible)
    if act < 3:
        return sorted(eligible)

    supported = {row["choice"] for row in archetype_matches
                 if any(match.get("deck_evidence") == "supported" for match in row["matches"])}
    eligible.update(choice for choice, card in offers if choice in supported | role_gaps
                    and named.get(card, ("", ""))[0] == "high" and not owned[card])
    if recipe:
        # A conditional card can be a good purchase once its recipe prerequisites
        # work. Free transition cards and listed traps are out of the paid pool.
        working_offers = [(choice, card) for choice, card in offers
                          if named.get(card, ("", ""))[0] not in {"bridge", "usually_skip"}]
        advice = _recipe_advice(recipe, owned, working_offers, act)
        if "preferred_choice" in advice:
            eligible.add(advice["preferred_choice"])
    return sorted(eligible)


def is_event_deck_choice(snapshot):
    """Identify an event selection whose chosen cards are added to the deck."""
    run, state = snapshot.get("run") or {}, snapshot.get("state") or {}
    if (snapshot.get("screen") != "card_selection" or not run.get("room_event_id")
            or snapshot.get("combat_selection") or state.get("location") == "combat_hand"
            or state.get("mode") != "NSimpleCardSelectScreen"):
        return False
    instructions = " ".join(plain_text(state.get("instructions") or "").split())
    return bool(re.search(
        r"^choose\b.+\badd to your deck\b|^\u9009\u62e9.+\u52a0\u5165(?:\u5230)?\u4f60\u7684\u724c\u7ec4",
        instructions, re.IGNORECASE,
    ))


def _regent_forge_recipe(guide, owned):
    forge = guide.get("forge_recipe")
    if not forge:
        return None
    activation = forge["activation"]
    sources = owned.keys() & activation["forge_cards"]
    support = owned.keys() & activation["access_cards"]
    has_early_engine = bool(support and sources.intersection(activation["early_anchors"]))
    if not sources or (len(sources) < 2 and not (has_early_engine or owned["PARRY"])):
        return None
    star_engine = owned["ALIGNMENT"] and owned.keys() & activation["star_payoffs"]
    if star_engine and not owned.keys() & activation["blade_payoffs"]:
        return None
    return forge


def _forge_cycle_budget(forge, deck, owned):
    """Price one Blade swing and one play of each known producer per deck pass."""
    cycle = forge["cycle"]
    sources = cycle["star_sources"]
    production = 0
    for card in deck:
        gain = sources.get(_model_id(card.get("id")))
        if gain:
            upgraded = bool(card.get("is_upgraded") or card.get("upgraded")
                            or card.get("current_upgrade_level"))
            production += gain[upgraded] * card.get("count", 1)
    core_cost = sum(cost for card, cost in cycle["core_star_costs"].items() if owned[card])
    energy = cycle["energy"]
    swing_cost = energy["SOVEREIGN_BLADE"] + (energy["CONQUEROR"] if owned["CONQUEROR"] else 0)
    return {
        "repeatable_stars_per_deck_pass": production,
        "core_stars_per_deck_pass": core_cost,
        "stars_after_core": production - core_cost,
        "base_energy_for_one_swing": swing_cost,
        "base_energy_with_same_turn_smith": swing_cost + (energy["THE_SMITH"] if owned["THE_SMITH"] else 0),
    }


def card_pick_advice(snapshot, assessment=None):
    """Classify legal offers and attach the applicable strategy advice."""
    screen = snapshot.get("screen")
    event_pick = is_event_deck_choice(snapshot)
    if screen not in {"card_reward", "shop"} and not event_pick:
        return {}
    run, state = snapshot.get("run") or {}, snapshot.get("state") or {}
    if event_pick:
        # The bridge reports pending selections separately until the event confirms them.
        pending = [row.get("card") for row in state.get("cards", []) if row.get("selected") is True]
        if state.get("selected_count") != len(pending) or not isinstance(run.get("deck"), list):
            return {}
        if pending:
            run = {**run, "deck": [*run["deck"], *pending]}
            assessment = archetype_assessment({**snapshot, "run": run})
    guide = _character_entry("card_recommendations", run, state)
    if not guide:
        return {}

    offers = []
    card_rows = {}
    for choice, action in enumerate(snapshot.get("actions") or [], 1):
        kind, detail = action["kind"], action["detail"]
        if screen == "card_reward" and kind == "pick_card_reward":
            card = detail.get("card", detail)
        elif event_pick and kind == "toggle_card_choice" and detail.get("selected") is False:
            card = detail.get("card")
        elif (screen == "shop" and kind == "buy_shop_item"
              and detail.get("type") == "card" and detail.get("affordable") is not False):
            card = detail.get("card")
        else:
            continue
        if isinstance(card, dict) and (card_id := _model_id(card.get("id"))):
            offers.append((choice, card_id))
            card_rows[choice] = card
    if not offers:
        return {}

    owned = _owned_counts(run.get("deck"))
    known_cards = set(owned) | {card_id for _, card_id in offers}
    named = {card_id: (row["priority"], row["when"]) for row in guide["named"] for card_id in row["cards"]}
    forge = _regent_forge_recipe(guide, owned)
    if forge:
        named.update({card: ("conditional", when) for card, when in forge["unlocked_picks"].items()})
    examples = {card_id: row["role"] for row in guide["functional_examples"] for card_id in row["cards"]}
    result = {"build_directions": [
        {"name": row["name"], "seek": row["seek"]}
        for row in guide["build_directions"] if not row.get("anchors") or known_cards.intersection(row["anchors"])
    ]}
    if definitions := _character_entry("archetypes", run, state):
        if assessment is None:
            assessment = archetype_assessment(snapshot)
        result["archetype_matches"] = _archetype_matches(definitions, offers, owned, assessment)
    named_picks, role_matches = [], []
    for choice, card_id in offers:
        offer = {"choice": choice, "card_id": card_id}
        if owned:
            offer["owned_copies"] = owned.get(card_id, 0)
        if card_id in named:
            priority, when = named[card_id]
            named_picks.append({**offer, "priority": priority, "when": when})
        if card_id in examples:
            role_matches.append({**offer, "role": examples[card_id]})
    if named_picks:
        result["named_picks"] = named_picks
    if role_matches:
        result["role_matches"] = role_matches
    trap_choices = {choice for choice, card in offers if named.get(card, ("", ""))[0] == "usually_skip"}
    if trap_choices:
        result["trap_choices"] = sorted(trap_choices)
    if owned:
        result["hand_role_coverage"] = _hand_role_coverage(run["deck"], owned.total(), card_rows, named)
    if owned and type(run.get("act")) is int:
        recipe = forge or guide.get("recipe")
        if poison_recipe := guide.get("poison_recipe"):
            archetypes = _character_entry("archetypes", run, state)
            poison = archetypes["Poison"]
            poison_sources = set(owned).intersection(poison["enablers"])
            poison_support = poison_sources | set(owned).intersection(poison["payoffs"])
            shivs = archetypes["Shivs"]
            shiv_core = (set(owned).intersection(shivs["enablers"])
                         and set(owned).intersection(shivs["payoffs"]))
            if "CORROSIVE_WAVE" in owned or (poison_sources and len(poison_support) >= 2 and not shiv_core):
                recipe = poison_recipe
        role_gaps = _role_gap_choices(result["hand_role_coverage"])
        safe_offers = [(choice, card) for choice, card in offers if choice not in trap_choices
                       and (named.get(card, ("", ""))[0] != "bridge" or choice in role_gaps)]
        if forge:
            budget = _forge_cycle_budget(forge, run["deck"], owned)
            result["forge_cycle_budget"] = budget
            costs = {**forge["cycle"]["core_star_costs"], **forge["cycle"]["optional_star_costs"]}
            safe_offers = [(choice, card) for choice, card in safe_offers
                           if card not in costs or costs[card] <= budget["stars_after_core"]]
        if screen == "shop":
            result["shop_purchase_choices"] = _shop_purchase_choices(
                run["act"], owned, safe_offers, named, recipe, role_gaps,
                result.get("archetype_matches", ()))
        if recipe:
            reward_offers = [(choice, card) for choice, card in offers if choice not in trap_choices]
            result["recipe"] = _recipe_advice(
                recipe, owned, safe_offers, run["act"],
                reward_offers=reward_offers if screen == "card_reward" else (),
            )
            pick = result["recipe"]
            if screen == "card_reward" and "preferred_choice" not in pick:
                if recipe.get("skip_unmatched"):
                    pick["prefer_skip"] = True
                elif run.get("game_mode") == "daily" and "SEALED_DECK" in (run.get("modifiers") or ()):
                    rules = guide.get("sealed_draft", {}).get("skip_for_direction", {})
                    active_builds = {
                        row["name"] for row in (assessment or {}).get("archetypes", ())
                        if row["evidence"] == "supported"
                    }
                    missing = pick["next_missing_roles"]
                    for rule in rules.values():
                        if active_builds != {rule["archetype"]}:
                            continue
                        covered_roles = rule.get("covered_roles", {})
                        copy_limits = rule.get("copy_limits", {})
                        compatible = {
                            offer["card_id"] for offer in result.get("archetype_matches", ())
                            if any(match["name"] == rule["archetype"] for match in offer["matches"])
                        }
                        if all(
                            (card in rule["cards"] and card not in compatible)
                            or (card in covered_roles and covered_roles[card] not in missing)
                            or (card in copy_limits and owned[card] >= copy_limits[card])
                            for _, card in offers
                        ):
                            pick["prefer_skip"] = True
                            break
    return result


def community_guidance(snapshot):
    """Use the character, current screen, verified deck, and shown options only."""
    run, state = snapshot.get("run") or {}, snapshot.get("state") or {}
    profile = _character_entry("profiles", run, state)
    if not isinstance(profile, dict):
        return []
    screen = snapshot.get("screen")
    deck = _card_ids(run.get("deck"))
    visible = _available_cards(snapshot, state)
    relevant_cards = visible if screen == "combat" else deck | visible
    act = run.get("act")
    specific, general = [], []
    archetypes = _character_entry("archetypes", run, state) or {}
    for rule in profile["rules"]:
        if screen not in rule["screens"]:
            continue
        limit = rule.get("through_act")
        if limit is not None and (type(act) is not int or act > limit):
            continue
        anchors = rule.get("deck_any", [])
        if archetype := rule.get("archetype_enablers"):
            anchors = archetypes.get(archetype, {}).get("enablers", [])
            if not anchors:
                continue
        offers = rule.get("seen_any", [])
        if anchors and len(deck.intersection(anchors)) < rule.get("min_deck_matches", 1):
            continue
        if offers and relevant_cards.isdisjoint(offers):
            continue
        if anchors or offers:
            relevant = set(anchors) | set(offers)
            specific.append((len(visible & relevant), len(deck & relevant), rule["tip"]))
        else:
            general.append(rule["tip"])
    specific.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return (general[:1] + [row[2] for row in specific] + general[1:])[:MAX_TIPS]
