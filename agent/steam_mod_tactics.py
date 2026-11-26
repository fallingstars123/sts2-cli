"""Summarize visible Steam combat risks and native legal alternatives for the model."""

from itertools import combinations
import re
from typing import NamedTuple


NOTICEABLE_HP_LOSS = 10
HEAVY_HP_LOSS = 15


def heavy_hp_loss(hp, loss):
    """Treat smaller losses as heavy once they consume a large share of current HP."""
    return type(hp) is int and hp > 0 and type(loss) is int and loss >= min(HEAVY_HP_LOSS, max(5, (hp + 3) // 4))


DIRECT_BLOCK_CARDS = frozenset({"ARMAMENTS", "BACKFLIP", "EVIL_EYE", "FLAME_BARRIER", "IRON_WAVE", "SHRUG_IT_OFF", "TAUNT",
                               "BULWARK", "CLOAK_OF_STARS", "GATHER_LIGHT", "PARTICLE_WALL", "REFLECT",
                               "ULTIMATE_DEFEND", "CHO_BARBS", "CHO_READY", "WHISTLING_ARROWS"})
DIRECT_DAMAGE_CARDS = {"BASH": (8, 2), "DISMANTLE": (8, 2), "STRIKE_IRONCLAD": (6, 3)}
PLAYER_DAMAGE_POWERS = frozenset({"DEXTERITY_POWER", "RINGING_POWER", "STRENGTH_POWER", "VULNERABLE_POWER"})
TARGET_DAMAGE_POWERS = frozenset({"DOOM_POWER", "PLOW_POWER", "STRENGTH_POWER", "VULNERABLE_POWER", "WEAK_POWER"})
BLOCK_PREVIEW_POWERS = PLAYER_DAMAGE_POWERS | {
    "DEMON_FORM_POWER", "DRAW_CARDS_NEXT_TURN_POWER", "FASTEN_POWER", "FLAME_BARRIER_POWER", "JUGGLING_POWER",
    "NO_DRAW_POWER", "REGEN_POWER", "SMOGGY_POWER", "SPECTRUM_SHIFT_POWER", "STAR_NEXT_TURN_POWER",
    "BLACK_HOLE_POWER", "FLEX_POTION_POWER", "TYRANNY_POWER", "VICIOUS_POWER", "WEAK_POWER",
    "AIM_POWER", "ARCHERY_POWER", "CHAINS_OF_BINDING_POWER", "CHO_BARBS_POWER", "FRAIL_POWER",
    "HIDDEN_ROOTS_POWER", "MOTIF_POWER", "SHRINK_POWER", "SPEED_POTION_POWER", "THORNS_POWER",
}
BLOCK_TEXT = re.compile(r"^(?:Gain ([0-9]+) Block\.|获得([0-9]+)点格挡。)", re.IGNORECASE)
TEXT_TAG = re.compile(r"\[/?[A-Za-z]+\]")
WEAK_BLOCK_TEXT = re.compile(
    r"(?:Ethereal\.\s*)?Gain ([1-9]\d*) Block\.\s*Apply [1-9]\d* Weak\."
    r"|(?:虚无。\s*)?获得([1-9]\d*)点格挡。\s*给予[1-9]\d*层虚弱。", re.IGNORECASE)
DEADLINE_TEXT = (
    re.compile(r"^(?:in (?P<turns>[1-9]\d*) turns?|(?P<each_turn>when .+ takes? (?:its|their) turn)|"
               r"at the (?:start|end) of .+?next turn),\s*you (?:will )?"
               r"(?:be [^,.]+ and )?(?:die|be killed|lose the fight)[.!]?$", re.IGNORECASE),
    re.compile(r"^在.+的下(?P<turns>[1-9]\d*)个回合(?:开始|结束)时[，,]\s*"
               r"你(?:将(?:会)?)?(?:被[^，。]+并)?(?:立即|直接)?死亡[。.]?$"),
)
DRAW_TEXT = re.compile(r"^(?:Draw [1-9]\d* cards?[.]|抽[1-9]\d*张牌。)", re.IGNORECASE | re.MULTILINE)
DAMAGE_TEXT = re.compile(r"^Deal (?P<damage>[1-9]\d*) damage"
                         r"(?P<untargeted> to (?:all enemies|a random enemy))?"
                         r"(?: (?P<hits>[1-9]\d*|X) times)?[.]", re.IGNORECASE)
DAMAGE_TEXT_ZH = re.compile(r"^(?P<untargeted>对(?:所有敌人|一名随机敌人))?造成(?P<damage>[1-9]\d*)点伤害"
                            r"(?:(?P<hits>[1-9]\d*|X)次)?。", re.IGNORECASE)
DOUBLE_ON_VULNERABLE = {"if the enemy is vulnerable, hits twice.", "如果该敌人有易伤状态，则攻击两次。"}
VULNERABLE_TOOLTIP = re.compile(r"receive ([1-9]\d*)% more damage from attacks|受到的攻击伤害增加([1-9]\d*)%", re.IGNORECASE)
STRENGTH_GAIN = re.compile(r"^(?:gain ([1-9]\d*) strength[.]|获得([1-9]\d*)点力量。)", re.IGNORECASE)
STRENGTH_EXPIRY = re.compile(r"^(?:at the end of (?:your|this) turn, lose ([1-9]\d*) strength[.]|"
                             r"在你的这个回合结束时，失去([1-9]\d*)点力量。)$", re.IGNORECASE)
ENERGY_GAIN = re.compile(r"^(?:gain (?:([1-9]\d*) energy|(⚡+))[.]|获得(?:([1-9]\d*)点能量|(⚡+))。)$", re.IGNORECASE)
ENERGY_ICON = re.compile(r"\[img\]res://images/packed/sprite_fonts/(?:[a-z0-9_]+_)?energy_icon\.png\[/img\]", re.IGNORECASE)
BUFF_DAMAGE_PLAYER_POWERS = PLAYER_DAMAGE_POWERS | {"DEMON_FORM_POWER", "JUGGLING_POWER", "NO_DRAW_POWER", "VICIOUS_POWER"}
BUFF_DAMAGE_RELICS = frozenset({"FAKE_STRIKE_DUMMY", "MINIATURE_CANNON", "MYSTIC_LIGHTER", "PAPER_PHROG",
                                "PEN_NIB", "STRIKE_DUMMY", "UNDYING_SIGIL", "VITRUVIAN_MINION"})
DEXTERITY_GAIN = re.compile(r"^(?:Gain ([1-9]\d*) Dexterity\.|获得([1-9]\d*)点敏捷。)$", re.IGNORECASE)
DIRECT_DRAW = re.compile(r"(?:^|[.!。\n])\s*(?:draw ([1-9]\d*) cards?\.|抽([1-9]\d*)张牌。)", re.IGNORECASE)
HAND_GENERATION = re.compile(r"^(?:choose [1-9]\d* of [1-9]\d* random ([a-z]+) cards? to add into your hand\."
                             r"|从[1-9]\d*张随机([^，。]+)中选择[1-9]\d*张加入你的手牌。)", re.IGNORECASE)
VULNERABLE_DRAW = re.compile(r"^(?:whenever you apply vulnerable, draw ([1-9]\d*) cards?\."
                             r"|每当你给予易伤时[，,]抽([1-9]\d*)张牌。)$", re.IGNORECASE)
WEAK_APPLICATION = re.compile(r"(?:^|[.!。\n])\s*(?:apply [1-9]\d* weak(?: to (?P<all>all enemies))?\."
                              r"|(?:给予|施加)[1-9]\d*层虚弱。)", re.IGNORECASE)
VULNERABLE_APPLICATION = re.compile(r"(?:^|[.!。\n])\s*(?:apply [1-9]\d* vulnerable(?: to all enemies)?\."
                                    r"|(?:给予|施加)[1-9]\d*层易伤。)", re.IGNORECASE)
STRENGTH_LOSS = re.compile(r"^(?:(?:enemy|target) loses ([1-9]\d*) strength(?: this turn)?\."
                           r"|使一名敌人(?:在本回合)?失去([1-9]\d*)点力量。)", re.IGNORECASE)
WEAK_TOOLTIP = re.compile(r"attacks deal ([1-9]\d*)% less damage|造成的攻击伤害减少([1-9]\d*)%", re.IGNORECASE)
WEAK_RELIC_TOOLTIP = re.compile(r"deal ([1-9]\d*)% less damage to you", re.IGNORECASE)
# Countdown powers whose stack is verified as turns remaining (localization_eng/powers.json).
# Toxic, Burn, Decay, Infection and Wither: damage at end of turn while the card stays in hand.
# Block absorbs it before the enemy turn, so it adds to the damage the shown Block must cover.
HAND_DAMAGE_TEXT = re.compile(
    r"At the end of your turn, if this is in your Hand, take ([1-9]\d*) damage\."
    r"|在你的回合结束时，如果这张牌在你的手牌中[,，]\s*你受到([1-9]\d*)点伤害。", re.IGNORECASE)
HAND_HP_LOSS_TEXT = re.compile(
    r"At the end of your turn, if this is in your Hand, lose ([1-9]\d*) HP\."
    r"|在你的回合结束时，如果这张牌在你的手牌中[,，]\s*你失去([1-9]\d*)点生命。", re.IGNORECASE)
# The Fool's Shoot cards need an available Arrow. An Arrow impaled in an enemy (IMPALED_POWER)
# returns only after display_amount more hits on that enemy; until then a Shoot does nothing.
SHOT_TEXT = re.compile(r"(?:^|[.!\n])\s*Shoot an Arrow\b", re.IGNORECASE)
SHOWN_DAMAGE = re.compile(r"\bdeals? ([1-9]\d*) damage\b(?! to ALL)", re.IGNORECASE)
STACK_COUNTDOWN_POWERS = frozenset({"SANDPIT_POWER"})
# Enemy powers that punish playing a Skill (ENRAGE_POWER: "Whenever you play a Skill, gains N Strength").
SKILL_PUNISH_POWERS = frozenset({"ENRAGE_POWER"})
INTENT_STRENGTH_PLAYER_POWERS = BLOCK_PREVIEW_POWERS | {"CHAINS_OF_BINDING_POWER", "FRAIL_POWER"}
INTENT_STRENGTH_ENEMY_POWERS = TARGET_DAMAGE_POWERS | {
    "ARTIFACT_POWER", "DARK_SHACKLES_POWER", "MINION_POWER", "PAPER_CUTS_POWER", "SOAR_POWER",
}


def _rows(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _nonnegative(value):
    return value if type(value) is int and value >= 0 else None


def _plain(value):
    return TEXT_TAG.sub("", value).strip() if isinstance(value, str) else ""


def _powers(creature):
    return {power["id"]: power["amount"] for power in _rows(creature.get("powers"))
            if isinstance(power.get("id"), str) and type(power.get("amount")) is int}


def is_shot(text):
    return bool(SHOT_TEXT.search(_plain(text)))


def arrow_state(combat):
    """Live Arrow availability for Shoot cards, or None when Arrows are not in play.

    The bridge reports arrows_available (ArrowCmd.GetAvailableArrowCount). Older snapshots lack
    it; there an impaled enemy means the Fool's single Arrow is out, so the count is inferred as 0.
    """
    impaled = []
    for enemy in _rows(combat.get("enemies")):
        if not _nonnegative(enemy.get("hp")):
            continue
        for power in _rows(enemy.get("powers")):
            if power.get("id") == "IMPALED_POWER":
                hits = power.get("display_amount")
                hits = hits if type(hits) is int and hits > 0 else power.get("amount")
                impaled.append({"target_index": enemy.get("index"), "hits_to_dislodge": hits})
    available = combat.get("arrows_available")
    if type(available) is int and available >= 0:
        return {"available": available, "impaled": impaled}
    if impaled:
        return {"available": 0, "impaled": impaled, "inferred": True}
    return None


# These cards' damage and on-hit effects require the same successful Arrow shot.
ARROW_REQUIRED_ATTACKS = frozenset({"FOOLISH_SHOT", "SKY_SHOT", "HOBBLING_SHOT", "THE_SHOT"})


def arrow_ready_actions(snapshot):
    """Hide known empty shots, while retaining other cards and native actions."""
    if snapshot.get("screen") != "combat":
        return snapshot["actions"]
    arrows = arrow_state(snapshot["state"])
    if arrows is None or arrows["available"] != 0:
        return snapshot["actions"]
    return [action for action in snapshot["actions"] if not (
        action["kind"] == "play_card" and action["detail"].get("card_id") in ARROW_REQUIRED_ATTACKS
    )]


def _shot_actions(actions, combat):
    hand = {card.get("index"): card for card in _rows(combat.get("hand"))}
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or action.get("kind") != "play_card":
            continue
        detail = action.get("detail") if isinstance(action.get("detail"), dict) else {}
        card = hand.get(detail.get("card_index"), {})
        if is_shot(detail.get("description") or card.get("description")):
            yield choice, detail, card


def _arrow_summary(actions, combat):
    arrows = arrow_state(combat)
    if arrows is None:
        return None
    summary = {key: value for key, value in arrows.items() if key != "inferred" and value != []}
    if arrows["available"] == 0:
        if dead := [choice for choice, _, _ in _shot_actions(actions, combat)]:
            summary["shots_without_arrow"] = dead
        targets = {item["target_index"] for item in arrows["impaled"]}
        hand = {card.get("index"): card for card in _rows(combat.get("hand"))}
        dislodge = []
        for choice, action in enumerate(actions, 1):
            detail = action.get("detail") if isinstance(action, dict) and isinstance(action.get("detail"), dict) else {}
            card = hand.get(detail.get("card_index"), {})
            if (action.get("kind") == "play_card" and detail.get("target_index") in targets
                    and card.get("type") == "Attack" and not is_shot(detail.get("description") or card.get("description"))):
                dislodge.append(choice)
        if dislodge:
            summary["dislodge_hit_choices"] = dislodge
    return summary


def shown_kill_choices(actions, combat):
    """Targeted plays whose shown damage meets an enemy's HP plus Block (modifiers not applied)."""
    enemies = {enemy.get("index"): enemy for enemy in _rows(combat.get("enemies"))}
    energy = _nonnegative(combat.get("energy"))
    hand = {card.get("index"): card for card in _rows(combat.get("hand"))}
    arrows = arrow_state(combat)
    kills = []
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or action.get("kind") != "play_card":
            continue
        detail = action.get("detail") if isinstance(action.get("detail"), dict) else {}
        card = hand.get(detail.get("card_index"), {})
        enemy = enemies.get(detail.get("target_index"))
        text = _plain(detail.get("description") or card.get("description"))
        cost = _nonnegative(card.get("energy_cost"))
        if (not enemy or cost is None or energy is None or cost > energy
                or (is_shot(text) and arrows is not None and arrows["available"] == 0)):
            continue
        hp, block = _nonnegative(enemy.get("hp")), _nonnegative(enemy.get("block")) or 0
        hp_loss_cap = _powers(enemy).get("HARD_TO_KILL_POWER")
        shown = SHOWN_DAMAGE.search(text)
        if hp and shown and int(shown.group(1)) >= hp + block and (hp_loss_cap is None or hp <= hp_loss_cap):
            kills.append({"choice": choice, "card_id": card.get("id"), "target_index": detail.get("target_index"),
                          "shown_damage": int(shown.group(1)), "target_hp": hp, "target_block": block})
    return kills[:4]


def _shown_attack(enemies):
    incoming = 0
    missing = not enemies
    for enemy in enemies:
        intents = _rows(enemy.get("intents"))
        missing |= not intents
        for intent in intents:
            damage = _nonnegative(intent.get("total_damage"))
            if damage is not None:
                incoming += damage
            elif intent.get("type") == "Attack":
                missing = True
    return incoming, missing


# These powers do not change incoming Poison or replace a dead enemy.
POISON_NEUTRAL_ENEMY_POWERS = frozenset({"POISON_POWER", "STRENGTH_POWER", "WEAK_POWER", "VULNERABLE_POWER",
                                       "FRAIL_POWER", "ARTIFACT_POWER", "PLATING_POWER"})
POISON_NEUTRAL_PLAYER_POWERS = POISON_NEUTRAL_ENEMY_POWERS | {
    "ACCELERANT_POWER", "CORROSIVE_WAVE_POWER", "DEXTERITY_POWER", "ENVENOM_POWER", "NOXIOUS_FUMES_POWER",
}


def _poison_outlook(combat, enemies, player_powers, hand_damage):
    """Calculate confirmed Poison ticks before enemy actions, bypassing Block."""
    if player_powers.keys() - POISON_NEUTRAL_PLAYER_POWERS:
        return None
    hits = 1 + max(0, player_powers.get("ACCELERANT_POWER", 0))
    living, kills = [], []
    for enemy in enemies:
        hp, target = _nonnegative(enemy.get("hp")), _nonnegative(enemy.get("index"))
        if hp == 0:
            continue
        living.append(enemy)
        powers = _powers(enemy)
        stacks = powers.get("POISON_POWER", 0)
        # Doom on an enemy checks after Poison and does not change its damage.
        if (hp is None or target is None or stacks <= 0
                or powers.keys() - POISON_NEUTRAL_ENEMY_POWERS - {"DOOM_POWER"}):
            continue
        count = min(stacks, hits)
        damage = count * (2 * stacks - count + 1) // 2
        if damage >= hp:
            kills.append({"target_index": target, "hp": hp, "stacks": stacks, "ticks": count, "damage": damage})
    if not kills:
        return None
    doomed = {kill["target_index"] for kill in kills}
    remaining = [enemy for enemy in living if enemy.get("index") not in doomed]
    encounter = combat.get("encounter") or ""
    ends_combat = not remaining and not hand_damage and encounter.endswith(("_NORMAL", "_WEAK"))
    result = {"kills_before_acting": kills, "safe_to_finish": ends_combat}
    if not remaining:
        result["remaining_shown_attack_damage"] = 0
    else:
        incoming, missing = _shown_attack(remaining)
        if not missing:
            result["remaining_shown_attack_damage"] = incoming
    return result


def _doom_after_enemy_actions(enemies):
    """Show each live target's Doom threshold without cancelling any attack intent."""
    targets = []
    for enemy in enemies:
        hp, index = _nonnegative(enemy.get("hp")), _nonnegative(enemy.get("index"))
        doom = _powers(enemy).get("DOOM_POWER", 0)
        if not hp or index is None or doom <= 0:
            continue
        row = {"target_index": index, "hp": hp, "stacks": doom, "additional_doom_needed": max(0, hp - doom)}
        damage, missing = _shown_attack([enemy])
        if not missing:
            row["shown_attack_damage"] = damage
        targets.append(row)
    return targets


def _doom_covers_living(enemies, doom):
    live = [enemy for enemy in enemies if enemy.get("hp") != 0]
    return bool(live) and len(live) == len(doom) and all(
        row["additional_doom_needed"] == 0 for row in doom
    )


def doom_finish_action(snapshot, tactics):
    """End a routine fight when Doom will resolve safely and the legal plays only add damage or Block."""
    combat = snapshot["state"]
    if (not tactics.get("doom_covers_living")
            or not (combat.get("encounter") or "").endswith(("_NORMAL", "_WEAK"))
            or tactics.get("shown_attack_damage") != 0 or tactics.get("unblocked_now") != 0
            or tactics.get("some_intent_damage_unavailable") or tactics.get("end_of_turn_hand_damage")
            or tactics.get("forced_defeat_countdowns")):
        return None
    player = combat.get("player") or {}
    if (_powers(player).keys() - (POISON_NEUTRAL_PLAYER_POWERS | {
            "DEXTERITY_POWER", "FRIENDSHIP_POWER", "NO_DRAW_POWER", "SHROUD_POWER", "SLEIGHT_OF_FLESH_POWER",
        })):
        return None
    for enemy in _rows(combat.get("enemies")):
        if enemy.get("hp") == 0:
            continue
        if _powers(enemy).keys() - (POISON_NEUTRAL_ENEMY_POWERS | {"DOOM_POWER", "HANG_POWER", "INTANGIBLE_POWER"}):
            return None
        if not all(intent.get("type") == "StatusCard" for intent in _rows(enemy.get("intents"))):
            return None
    end = None
    for action in snapshot["actions"]:
        if action["kind"] == "end_turn":
            end = action
        elif action["kind"] == "play_card":
            text = _plain(action["detail"].get("description"))
            lines = [line.strip() for line in text.splitlines()
                     if line.strip() and line.strip().casefold() not in LINE_RULES]
            if len(lines) != 1 or not (LINE_HIT.fullmatch(lines[0]) or LINE_HIT_ZH.fullmatch(lines[0])
                                       or BLOCK_TEXT.fullmatch(lines[0])):
                return None
        elif action["kind"] != "retry_current_combat":
            return None
    return end


def _block_preview(action, player_powers):
    if player_powers.keys() - BLOCK_PREVIEW_POWERS:
        return 0
    detail = action["detail"]
    preview = _plain(detail.get("description"))
    if action.get("kind") == "play_card":
        if match := WEAK_BLOCK_TEXT.fullmatch(preview):
            return int(match.group(1) or match.group(2))
        card_id = detail.get("card_id")
        if not isinstance(card_id, str) or not (card_id.startswith("DEFEND_") or card_id in DIRECT_BLOCK_CARDS):
            return 0
    elif action.get("kind") != "use_potion" or detail.get("potion_id") != "BLOCK_POTION":
        return 0
    match = BLOCK_TEXT.match(preview)
    return int(match.group(1) or match.group(2)) if match else 0


def _attack_hp_loss(card, enemy, player_powers, enemy_powers):
    """Estimate only fixed direct attacks with understood visible modifiers."""
    card_id, upgrade = card.get("id"), _nonnegative(card.get("upgrade"))
    block = _nonnegative(enemy.get("block"))
    if (not isinstance(card_id, str) or card_id not in DIRECT_DAMAGE_CARDS or upgrade not in (0, 1)
            or block is None or player_powers.keys() - PLAYER_DAMAGE_POWERS
            or enemy_powers.keys() - TARGET_DAMAGE_POWERS):
        return 0
    base, increase = DIRECT_DAMAGE_CARDS[card_id]
    damage = max(0, base + upgrade * increase + min(0, player_powers.get("STRENGTH_POWER", 0)))
    vulnerable = enemy_powers.get("VULNERABLE_POWER", 0) > 0
    if vulnerable:
        damage = damage * 3 // 2
    hits = 2 if card_id == "DISMANTLE" and vulnerable else 1
    return max(0, damage * hits - block)


def _skill_penalty(enemies):
    """Extra attack damage this turn for each Skill played, from enemies with Enrage.

    Enrage: "Whenever you play a Skill, gains N Strength." Strength adds N to every hit of
    that enemy's shown attacks, and it lasts for the rest of combat.
    """
    extra = 0
    for enemy in enemies:
        if (_nonnegative(enemy.get("hp")) or 0) <= 0:
            continue
        gain = sum(amount for power, amount in _powers(enemy).items() if power in SKILL_PUNISH_POWERS and amount > 0)
        if not gain:
            continue
        hits = sum(_nonnegative(intent.get("hits")) or 1 for intent in _rows(enemy.get("intents"))
                   if intent.get("type") == "Attack")
        extra += gain * hits
    return extra


def _skill_punished(enemies):
    return any((_nonnegative(enemy.get("hp")) or 0) > 0
               and any(power in SKILL_PUNISH_POWERS and amount > 0 for power, amount in _powers(enemy).items())
               for enemy in enemies)


def _before_end_turn(actions, combat, enemies, player_powers, unblocked):
    hand = {card["index"]: card for card in _rows(combat.get("hand")) if type(card.get("index")) is int}
    # Quantify attacks only against the sole enemy so saved damage is attributable.
    enemy = enemies[0] if len(enemies) == 1 else {}
    enemy_hp = _nonnegative(enemy.get("hp"))
    enemy_powers = _powers(enemy)
    target_index = _nonnegative(enemy.get("index"))
    by_index = {item.get("index"): item for item in enemies}
    skill_penalty = _skill_penalty(enemies)
    candidates = []
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or not isinstance(action.get("detail"), dict):
            continue
        block = _block_preview(action, player_powers)
        if block > 0:
            played = hand.get(action["detail"].get("card_index"), {}) if action.get("kind") == "play_card" else {}
            penalty = skill_penalty if played.get("type") == "Skill" else 0
            target = by_index.get(action["detail"].get("target_index"))
            weak_reduction = 0 if penalty else _weak_block_reduction(action["detail"], target)
            saved = unblocked - max(0, unblocked + penalty - block - weak_reduction)
            if saved > 0:
                candidate = {"choice": choice, "kind": "block", "shown_block_gain": block, "estimated_hp_saved": saved}
                if weak_reduction:
                    candidate["estimated_weak_reduction"] = weak_reduction
                if penalty:
                    candidate["enemy_damage_gain_from_enrage"] = penalty
                    candidate["note"] = "Playing this Skill gives an Enrage enemy Strength for the rest of combat."
                candidates.append(candidate)
        detail = action["detail"]
        position = _nonnegative(detail.get("card_index"))
        if (action.get("kind") != "play_card" or enemy_hp is None or target_index is None
                or _nonnegative(detail.get("target_index")) != target_index or position not in hand):
            continue
        card = hand[position]
        if card.get("id") != detail.get("card_id"):
            continue
        loss = _attack_hp_loss(card, enemy, player_powers, enemy_powers)
        threshold = enemy_powers.get("PLOW_POWER", 0)
        if loss > 0 and (loss >= enemy_hp or (threshold > 0 and enemy_hp - loss <= threshold)):
            candidates.append({"choice": choice, "kind": "lethal" if loss >= enemy_hp else "plow_stun",
                               "target_index": target_index, "minimum_estimated_hp_loss": loss,
                               "estimated_hp_saved": unblocked})
    candidates.sort(key=lambda item: item["estimated_hp_saved"], reverse=True)
    return candidates[:4]


def _hand_damage(combat):
    """Distinguish damage Block can absorb from direct loss of HP."""
    by_index = {}
    for card in _rows(combat.get("hand")):
        index = card.get("index")
        if type(index) is not int:
            continue
        text = " ".join(_plain(card.get("description")).split())
        if match := HAND_DAMAGE_TEXT.search(text):
            by_index[index] = (int(match.group(1) or match.group(2)), False)
        elif match := HAND_HP_LOSS_TEXT.search(text):
            by_index[index] = (int(match.group(1) or match.group(2)), True)
    blockable = sum(amount for amount, direct in by_index.values() if not direct)
    direct = sum(amount for amount, direct in by_index.values() if direct)
    return blockable, direct, by_index


def hold_cloak_on_idle_turn(combat, player):
    """Save the Star when Block has no known use and the play has no extra effects."""
    enemies = _rows(combat.get("enemies"))
    if not enemies or any(not enemy.get("intents") or
                          any(intent.get("type") != "Buff" for intent in enemy["intents"])
                          for enemy in enemies):
        return False
    if any(_powers(enemy).keys() - {"PLOW_POWER", "HARD_TO_KILL_POWER", "STRENGTH_POWER",
                                   "WEAK_POWER", "VULNERABLE_POWER"} for enemy in enemies):
        return False
    if any(power.get("id") not in {"DRAW_CARDS_NEXT_TURN_POWER", "STAR_NEXT_TURN_POWER"}
           for power in _rows(player.get("powers"))):
        return False
    if any(relic.get("id") not in {"DIVINE_RIGHT", "LARGE_CAPSULE", "RED_MASK", "BOOK_OF_FIVE_RINGS",
                                   "CENTENNIAL_PUZZLE", "GLASS_EYE"} for relic in _rows(player.get("relics"))):
        return False
    return not _hand_damage(combat)[0]


def _slumbering_beetle_at_end_turn(combat):
    enemies = _rows(combat.get("enemies"))
    if combat.get("encounter") != "SLUMBERING_BEETLE_NORMAL" or combat.get("energy") != 0 or len(enemies) != 1:
        return None
    enemy = enemies[0]
    if (enemy.get("id") != "SLUMBERING_BEETLE"
            or _powers(enemy).keys() - {"STRENGTH_POWER", "WEAK_POWER", "VULNERABLE_POWER"}
            or not enemy.get("intents")
            or any(intent.get("type") not in {"Attack", "Buff"} for intent in enemy["intents"])):
        return None
    return enemy


def _obsidian_vice_damage(player, hand):
    return len(hand) if any(relic.get("id") == "OBSIDIAN_VICE" for relic in _rows(player.get("relics"))) else 0


def hold_particle_wall_for_pocketwatch(combat, player):
    """Keep the extra draw when spending Stars for chip damage cannot finish a buffing foe."""
    if combat.get("encounter") != "ENTOMANCER_ELITE" or combat.get("energy") != 0:
        return False
    if not any(relic.get("id") == "POCKETWATCH" and relic.get("counter") == 3
               for relic in _rows(player.get("relics"))):
        return False
    enemies = _rows(combat.get("enemies"))
    if (len(enemies) != 1 or not enemies[0].get("intents")
            or any(intent.get("type") != "Buff" for intent in enemies[0]["intents"])
            or _hand_damage(combat)[0]):
        return False
    pile = _rows(combat.get("draw_pile"))
    count = sum(_nonnegative(card.get("count")) or 0 for card in pile)
    dazed = sum(_nonnegative(card.get("count")) or 0 for card in pile if card.get("id") == "DAZED")
    if count != combat.get("draw_pile_count") or not 5 <= count < 8 or dazed < 4:
        return False
    hand = _rows(combat.get("hand"))
    costs = [card["star_cost"] for card in hand if card.get("id") == "PARTICLE_WALL"
             and (_nonnegative(card.get("star_cost")) or 0) > 0]
    stars = _nonnegative(combat.get("stars")) or 0
    powers = _powers(player)
    if not costs or powers.keys() - {"BLACK_HOLE_POWER", "STAR_NEXT_TURN_POWER", "TYRANNY_POWER"}:
        return False
    wall_damage = (stars // min(costs)) * max(0, powers.get("BLACK_HOLE_POWER", 0))
    return (_nonnegative(enemies[0].get("hp")) or 0) > wall_damage + _obsidian_vice_damage(player, hand)


def hold_star_potion_for_next_turn(combat, player):
    """Keep the option to drink after drawing when the Stars cannot save this turn."""
    if combat.get("energy") != 0:
        return False
    enemy = _slumbering_beetle_at_end_turn(combat)
    targets = [enemy] if enemy else _rows(combat.get("enemies"))
    if not enemy and (combat.get("encounter") != "DECIMILLIPEDE_ELITE" or not targets
                      or any(not str(target.get("id") or "").startswith("DECIMILLIPEDE_SEGMENT_")
                             or _powers(target).keys() - BLACK_HOLE_TARGET_POWERS
                             for target in targets)):
        return False
    hand = _rows(combat.get("hand"))
    if any((not _nonnegative(card.get("energy_cost")) or card.get("energy_x"))
           and "Unplayable" not in (card.get("keywords") or ()) for card in hand):
        return False
    black_hole_damage = max(0, _powers(player).get("BLACK_HOLE_POWER", 0))
    maximum_damage = black_hole_damage + _obsidian_vice_damage(player, hand)
    return all((_nonnegative(target.get("hp")) or 0) > maximum_damage for target in targets)


def star_potion_end_turn_line(actions, combat, unblocked):
    """Check immediate end-turn lethal or repeated Particle Wall with the added Stars."""
    if (type(unblocked) is not int or unblocked < NOTICEABLE_HP_LOSS or combat.get("ringing")
            or not (enemy := _slumbering_beetle_at_end_turn(combat))):
        return None
    potion = next((action for action in actions if action["kind"] == "use_potion"
                   and action["detail"].get("potion_id") == "STAR_POTION"), None)
    if not potion:
        return None
    gained = (potion["detail"].get("description") or "").count("[img]res://images/packed/sprite_fonts/star_icon.png[/img]")
    if gained <= 0:
        return None
    player = combat.get("player") or {}
    powers, hand = _powers(player), _rows(combat.get("hand"))
    vice_damage = _obsidian_vice_damage(player, hand)
    hp, block = _nonnegative(enemy.get("hp")), _nonnegative(enemy.get("block"))
    if hp and block is not None and vice_damage < hp + block <= vice_damage + powers.get("BLACK_HOLE_POWER", 0):
        return {"action_id": potion["id"], "hp_saved": unblocked, "lethal_with_obsidian_vice": True}
    stars = _nonnegative(combat.get("stars"))
    if stars is None:
        return None
    for card in hand:
        cost = _nonnegative(card.get("star_cost"))
        if (card.get("id") != "PARTICLE_WALL" or card.get("energy_cost") != 0 or card.get("affliction")
                or card.get("energy_x") or card.get("star_x") or not cost or not stars < cost <= stars + gained):
            continue
        synthetic_play = {"kind": "play_card", "detail": {
            "card_id": "PARTICLE_WALL", "description": card.get("description")}}
        repeats = (stars + gained) // cost
        saved = min(unblocked, repeats * _block_preview(synthetic_play, powers))
        if saved >= NOTICEABLE_HP_LOSS:
            return {"action_id": potion["id"], "hp_saved": saved, "particle_wall_plays": repeats}
    return None


def _hand_damage_choices(actions, combat, by_index, unblocked):
    """Legal plays that take a hand-damage card out of the hand before the turn ends."""
    hand = {card.get("index"): card for card in _rows(combat.get("hand"))}
    choices = []
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or action.get("kind") != "play_card":
            continue
        detail = action.get("detail") if isinstance(action.get("detail"), dict) else {}
        index = detail.get("card_index")
        card = hand.get(index, {})
        if index not in by_index or card.get("id") != detail.get("card_id"):
            continue
        amount, direct = by_index[index]
        option = {"choice": choice, "kind": "remove_hand_damage", "card_id": card.get("id"),
                  "energy_cost": _nonnegative(card.get("energy_cost")), "removes_damage": amount,
                  "estimated_hp_saved": amount if direct else min(amount, unblocked or 0)}
        if direct:
            option["bypasses_block"] = True
        choices.append(option)
    return choices


def _defeat_deadline(power):
    description = " ".join(_plain(power.get("description")).split())
    for pattern in DEADLINE_TEXT:
        if match := pattern.fullmatch(description):
            groups = match.groupdict()
            if groups.get("turns"):
                turns = int(groups["turns"])
            elif groups.get("each_turn") and power.get("id") in STACK_COUNTDOWN_POWERS:
                # The game text is "{Amount:plural:When X takes its turn|In {} turns}", but the
                # state can carry the singular wording at every stack, so the stack is the
                # countdown (Sandpit 4, 3, 2, 1 kills on the enemy turn after 1). Unverified
                # powers with this wording keep the conservative one-turn reading.
                amount = _nonnegative(power.get("display_amount", power.get("amount")))
                turns = amount if amount else 1
            else:
                turns = 1
            return turns, description
    return None


def _possible_lethal(detail, description, combat, enemy):
    hp, block = _nonnegative(enemy.get("hp")), _nonnegative(enemy.get("block"))
    enemy_index = _nonnegative(enemy.get("index"))
    match = DAMAGE_TEXT.match(description)
    if not match or hp is None or block is None or enemy_index is None:
        return False
    if detail.get("target_index") != enemy_index and not match.group("untargeted"):
        return False
    hits = match.group("hits") or "1"
    if hits.upper() == "X":
        hand = _rows(combat.get("hand"))
        if not any(card.get("index") == detail.get("card_index") and card.get("energy_x") is True for card in hand):
            return False
        hits = _nonnegative(combat.get("energy")) or 0
    return int(match.group("damage")) * int(hits) >= hp + block


def _deadline_choices(actions, combat, enemies, name):
    escaped = re.escape(name)
    change = re.compile(rf"(?:^|[.!。\n])\s*(?:increase {escaped} by [1-9]\d*|remove (?:the )?{escaped}|"
                        rf"将{escaped}的计数加[1-9]\d*|移除{escaped})[.!。]", re.IGNORECASE) if name else None
    can_draw = any((_nonnegative(combat.get(key)) or 0) > 0 for key in ("draw_pile_count", "discard_pile_count"))
    delays, wins, draws = [], [], []
    for index, action in enumerate(actions, 1):
        if not isinstance(action, dict) or action.get("kind") not in {"play_card", "use_potion"}:
            continue
        detail = action.get("detail")
        if not isinstance(detail, dict):
            continue
        description = _plain(detail.get("description"))
        if change and change.search(description):
            delays.append(index)
        if len(enemies) == 1 and _possible_lethal(detail, description, combat, enemies[0]):
            wins.append(index)
        if can_draw and DRAW_TEXT.search(description):
            draws.append(index)
    return {"delay_choices": delays, "possible_win_choices": wins, "draw_choices": draws}


def _timed_defeat_risks(actions, combat, player, enemies):
    risks = []
    for creature in (player, *enemies):
        for power in _rows(creature.get("powers")):
            deadline = _defeat_deadline(power)
            if deadline is None:
                continue
            turns, description = deadline
            name = power.get("name")
            name = name.strip() if isinstance(name, str) else ""
            risk = {"power_id": power.get("id"), "name": name, "turns_remaining": turns,
                    "shown_amount": _nonnegative(power.get("display_amount", power.get("amount"))),
                    "description": description,
                    **_deadline_choices(actions, combat, enemies, name)}
            risk.update(_race(creature, player, enemies, turns))
            risks.append(risk)
    return risks


def _race(owner, player, enemies, turns):
    """HP that must come off before the countdown ends: the owner if an enemy holds it, else every enemy."""
    targets = enemies if owner is player else [owner]
    remaining = [(_nonnegative(enemy.get("hp")), _nonnegative(enemy.get("block"))) for enemy in targets]
    if not remaining or any(hp is None or block is None for hp, block in remaining):
        return {}
    total = sum(hp + block for hp, block in remaining)
    owner_index = _nonnegative(owner.get("index")) if owner is not player else None
    race = {"hp_to_remove_before_deadline": total,
            "damage_needed_per_turn": -(-total // max(1, turns))}
    if owner_index is not None:
        race["kill_target_index"] = owner_index
    return race


def _vulnerable_multiplier(enemy):
    for power in _rows(enemy.get("powers")):
        if power.get("id") != "VULNERABLE_POWER" or not (_nonnegative(power.get("amount")) or 0):
            continue
        match = VULNERABLE_TOOLTIP.search(_plain(power.get("description")))
        return 100 + int(match.group(1) or match.group(2)) if match else None
    return 100


def _visible_buff(description):
    if not isinstance(description, str):
        return None
    text = _plain(ENERGY_ICON.sub("⚡", description))
    if match := STRENGTH_GAIN.match(text):
        amount = int(match.group(1) or match.group(2))
        rest = text[match.end():].strip()
        if not rest:
            return "strength", amount, False
        if (expiry := STRENGTH_EXPIRY.fullmatch(rest)) and int(expiry.group(1) or expiry.group(2)) == amount:
            return "strength", amount, True
    elif match := ENERGY_GAIN.fullmatch(text):
        amount = int(value) if (value := match.group(1) or match.group(3)) else len(match.group(2) or match.group(4))
        return "energy", amount, True
    return None


def _buff_attack(detail, card, energy, target_index, vulnerable):
    if card.get("type") != "Attack" or card.get("affliction"):
        return None
    description = _plain(detail.get("description"))
    match = DAMAGE_TEXT.match(description) or DAMAGE_TEXT_ZH.match(description)
    if not match or (detail.get("target_index") != target_index and not match.group("untargeted")):
        return None
    suffix = description[match.end():].strip().casefold()
    hits = (match.group("hits") or "1").upper()
    if suffix in DOUBLE_ON_VULNERABLE and hits == "1":
        hits = "2" if vulnerable > 100 else "1"
    elif suffix:
        return None
    if hits == "X":
        if card.get("energy_x") is not True or not energy:
            return None
        return int(match.group("damage")), energy, True
    if card.get("energy_x") or card.get("star_x"):
        return None
    return int(match.group("damage")), int(hits), False


def _damage_buff_combos(actions, combat, player, enemies, player_powers):
    if len(enemies) != 1 or player_powers.keys() - BUFF_DAMAGE_PLAYER_POWERS:
        return []
    if any(relic.get("id") in BUFF_DAMAGE_RELICS for relic in _rows(player.get("relics"))):
        return []
    enemy = enemies[0]
    target_index = _nonnegative(enemy.get("index"))
    hp, block = _nonnegative(enemy.get("hp")), _nonnegative(enemy.get("block"))
    energy = _nonnegative(combat.get("energy"))
    if not hp or None in (target_index, block, energy):
        return []
    if any(power.get("id") not in TARGET_DAMAGE_POWERS and _defeat_deadline(power) is None
           for power in _rows(enemy.get("powers"))):
        return []
    vulnerable = _vulnerable_multiplier(enemy)
    if vulnerable is None:
        return []

    hand = {card.get("index"): card for card in _rows(combat.get("hand")) if type(card.get("index")) is int}
    buffs, attacks = [], []
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or not isinstance(detail := action.get("detail"), dict):
            continue
        kind = action.get("kind")
        if kind == "use_potion" and (buff := _visible_buff(detail.get("description"))):
            if detail.get("target_index") is None:
                buffs.append((choice, 0, buff))
        elif kind == "play_card" and type(index := detail.get("card_index")) is int and index in hand:
            card = hand[index]
            cost = _nonnegative(card.get("energy_cost"))
            if cost is None or card.get("id") != detail.get("card_id"):
                continue
            if preview := _buff_attack(detail, card, energy, target_index, vulnerable):
                attacks.append((choice, cost, preview))
            elif (card.get("type") == "Power" and card.get("target_type") == "Self"
                  and not card.get("affliction") and not card.get("energy_x") and not card.get("star_x")
                  and (_nonnegative(card.get("star_cost")) or 0) == 0 and not player_powers.get("RINGING_POWER")
                  and (buff := _visible_buff(detail.get("description")))):
                buffs.append((choice, cost, buff))

    combos = []
    for buff_choice, buff_cost, (buff_kind, buff_amount, temporary) in buffs:
        remaining = energy - buff_cost + (buff_amount if buff_kind == "energy" else 0)
        bonus_per_hit = buff_amount if buff_kind == "strength" else 0
        for attack_choice, attack_cost, (per_hit, hits, variable_hits) in attacks:
            buffed_hits = remaining if variable_hits else hits
            if buffed_hits <= 0 or (not variable_hits and attack_cost > remaining):
                continue
            baseline = max(0, per_hit * vulnerable // 100 * hits - block)
            buffed = max(0, (per_hit + bonus_per_hit) * vulnerable // 100 * buffed_hits - block)
            if buffed > baseline and baseline < hp:
                combos.append({"buff_choice": buff_choice, "attack_choice": attack_choice,
                               "buff_kind": buff_kind, "buff_amount": buff_amount, "temporary": temporary,
                               "target_index": target_index, "baseline_damage": baseline, "buffed_damage": buffed,
                               "target_hp": hp, "enables_lethal": buffed >= hp})
    combos.sort(key=lambda item: (item["enables_lethal"], item["buffed_damage"] - item["baseline_damage"]), reverse=True)
    return combos[:4]


def _dexterity_potion_bonus(detail, player_powers):
    item = detail.get("potion_id")
    if item not in {"SPEED_POTION", "DEXTERITY_POTION"}:
        return 0, 0, None
    effect = re.split(r"(?<=[。.])\s*", _plain(detail.get("description")), maxsplit=1)[0]
    match = DEXTERITY_GAIN.fullmatch(effect)
    if match is None:
        return 0, 0, None
    amount = int(match.group(1) or match.group(2))
    # Frail is already applied to the shown Block. Round the added amount down for a lower bound.
    bonus = amount * 3 // 4 if player_powers.get("FRAIL_POWER", 0) > 0 else amount
    return amount, bonus, "this_turn" if item == "SPEED_POTION" else "rest_of_combat"


def _defense_buff_combos(actions, player_powers, hp, unblocked, complete):
    if not hp or not unblocked:
        return []
    buffs, blocks = [], []
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or not isinstance(detail := action.get("detail"), dict):
            continue
        if action.get("kind") == "play_card" and (block := _block_preview(action, player_powers)):
            blocks.append((choice, block))
        elif action.get("kind") == "use_potion" and detail.get("target_index") is None:
            amount, bonus, duration = _dexterity_potion_bonus(detail, player_powers)
            if bonus:
                buffs.append((choice, amount, bonus, duration))
    combos = []
    for buff_choice, amount, bonus, duration in buffs:
        for block_choice, block in blocks:
            buffed = block + bonus
            saved = min(unblocked, buffed) - min(unblocked, block)
            if saved:
                combos.append({"buff_choice": buff_choice, "block_choice": block_choice, "buff_kind": "dexterity",
                               "buff_amount": amount, "duration": duration,
                               "baseline_block": block, "buffed_block": buffed,
                               "estimated_hp_saved": saved, "prevents_lethal": complete and unblocked - block >= hp > unblocked - buffed})
    combos.sort(key=lambda combo: (combo["prevents_lethal"], combo["estimated_hp_saved"]), reverse=True)
    return combos[:4]


def _attack_hit_profiles(enemy):
    powers = _powers(enemy)
    can_weaken = not (powers.get("WEAK_POWER", 0) > 0 or powers.get("ARTIFACT_POWER", 0) > 0)
    profiles = []
    for intent in _rows(enemy.get("intents")):
        damage, hits = _nonnegative(intent.get("damage")), _nonnegative(intent.get("hits"))
        if (not damage or not hits or intent.get("type") != "Attack"
                or intent.get("total_damage") != damage * hits):
            continue
        profile = {"damage_per_hit": damage, "hits": hits}
        if can_weaken:
            # The displayed hit was rounded down already. Use an upper bound after Weak.
            profile["max_damage_per_hit_after_weak"] = (3 * (damage + 1) - 1) // 4
        profiles.append(profile)
    return profiles


def _weak_damage_reduction(enemy):
    return sum((line["damage_per_hit"] - line["max_damage_per_hit_after_weak"]) * line["hits"]
               for line in _attack_hit_profiles(enemy) if "max_damage_per_hit_after_weak" in line)


def _weak_block_reduction(detail, enemy):
    if enemy and WEAK_BLOCK_TEXT.fullmatch(_plain(detail.get("description"))):
        return _weak_damage_reduction(enemy)
    return 0


def _weak_multiplier(enemy, player):
    for power in _rows(enemy.get("powers")):
        if power.get("id") != "WEAK_POWER" or not (_nonnegative(power.get("amount")) or 0):
            continue
        for relic in _rows(player.get("relics")):
            if relic.get("id") == "PAPER_KRANE":
                match = WEAK_RELIC_TOOLTIP.search(_plain(relic.get("description")))
                return 100 - int(match.group(1)) if match else None
        match = WEAK_TOOLTIP.search(_plain(power.get("description")))
        return 100 - int(match.group(1) or match.group(2)) if match else None
    return 100


def _strength_loss_projection(enemy, player, player_powers, amount):
    powers = _powers(enemy)
    if (powers.get("ARTIFACT_POWER", 0) > 0 or powers.keys() - INTENT_STRENGTH_ENEMY_POWERS
            or player_powers.keys() - INTENT_STRENGTH_PLAYER_POWERS):
        return []
    weak, vulnerable = _weak_multiplier(enemy, player), _vulnerable_multiplier(player)
    if weak is None or vulnerable is None or not 0 < weak <= 100:
        return []
    minimum_reduction, fraction = divmod(amount * weak * vulnerable, 10_000)
    maximum_reduction = minimum_reduction + bool(fraction)
    projections = []
    for intent in _rows(enemy.get("intents")):
        if intent.get("type") != "Attack":
            continue
        damage, hits = _nonnegative(intent.get("damage")), _nonnegative(intent.get("hits"))
        if damage is None or not hits or intent.get("total_damage") != damage * hits:
            return []
        # The intent already rounded down the original hit, so an incremental reduction can round either way.
        projections.append({"hits": hits, "damage_per_hit_before": damage,
                            "damage_per_hit_after_min": max(0, damage - maximum_reduction),
                            "damage_per_hit_after_max": max(0, damage - minimum_reduction)})
    return projections


def _generation_choice(choice, text, energy):
    match = HAND_GENERATION.match(text)
    if not match:
        return None
    card_type = match.group(1) or match.group(2)
    free = "free to play this turn" in text.casefold() or "本回合可以免费打出" in text
    return {"choice": choice, "kind": "generate", "generated_type": card_type, "energy_after": energy,
            "free_this_turn": free, "can_generate_defense": free and card_type.casefold() in {"skill", "技能牌"}}


def _defense_generation_choices(actions, energy):
    if energy is None:
        return []
    choices = []
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or action.get("kind") != "use_potion":
            continue
        detail = action.get("detail")
        if isinstance(detail, dict):
            option = _generation_choice(choice, _plain(detail.get("description")), energy)
            if option and option["can_generate_defense"]:
                choices.append(option)
    return choices[:6]


def _survival_setups(actions, combat, player, enemies, player_powers, incoming, unblocked):
    energy = _nonnegative(combat.get("energy"))
    if energy is None:
        return [], []
    hand = {card.get("index"): card for card in _rows(combat.get("hand")) if type(card.get("index")) is int}
    targets = {enemy.get("index"): enemy for enemy in enemies if type(enemy.get("index")) is int}
    can_draw = not player_powers.get("NO_DRAW_POWER") and any(
        (_nonnegative(combat.get(key)) or 0) > 0 for key in ("draw_pile_count", "discard_pile_count"))
    choices, draw_setups, triggers = [], [], []
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or not isinstance(detail := action.get("detail"), dict):
            continue
        kind = action.get("kind")
        card = {}
        if kind == "play_card":
            index = detail.get("card_index")
            card = hand.get(index, {}) if type(index) is int else {}
            cost = _nonnegative(card.get("energy_cost"))
            if (cost is None or cost > energy or card.get("id") != detail.get("card_id")
                    or card.get("star_x") or (_nonnegative(card.get("star_cost")) or 0) > 0):
                continue
        elif kind == "use_potion":
            cost = 0
        else:
            continue
        text = _plain(detail.get("description"))
        remaining = energy - cost
        target = detail.get("target_index")
        enemy = targets.get(target) if type(target) is int else None
        saved = 0
        weak = WEAK_APPLICATION.search(text)
        hobbling = (card.get("id") == "HOBBLING_SHOT"
                    and (arrow_state(combat) or {}).get("available", 0) > 0)
        if weak or hobbling:
            affected = enemies if weak and weak.group("all") else (enemy,) if enemy else ()
            saved = sum(_weak_damage_reduction(item) for item in affected)
            if saved:
                choices.append({"choice": choice, "kind": "weak", "target_index": target,
                                "baseline_incoming": incoming, "estimated_incoming": incoming - saved,
                                "estimated_hp_saved": min(saved, unblocked), "energy_after": remaining})
        if enemy and (strength := STRENGTH_LOSS.match(text)):
            amount = int(strength.group(1) or strength.group(2))
            hits = _strength_loss_projection(enemy, player, player_powers, amount)
            before = sum(hit["hits"] * hit["damage_per_hit_before"] for hit in hits)
            after = sum(hit["hits"] * hit["damage_per_hit_after_max"] for hit in hits)
            if after < before:
                reduction = before - after
                choices.append({"choice": choice, "kind": "strength_loss", "target_index": target,
                                "strength_loss": amount, "target_attack_hits": hits,
                                "baseline_incoming": incoming, "estimated_incoming": incoming - reduction,
                                "estimated_hp_saved": min(reduction, unblocked), "energy_after": remaining})
        if can_draw and (draw := DIRECT_DRAW.search(text)):
            choices.append({"choice": choice, "kind": "draw", "draw_count": int(draw.group(1) or draw.group(2)),
                            "energy_after": remaining})
        if kind == "use_potion" and (generation := _generation_choice(choice, text, remaining)):
            choices.append(generation)

        # Recheck native actions after setup. A restrictive or damaging affliction can invalidate a two-card estimate.
        if not can_draw or player_powers.get("RINGING_POWER") or card.get("affliction") or card.get("energy_x"):
            continue
        if (card.get("type") == "Power" and card.get("target_type") == "Self"
                and (setup := VULNERABLE_DRAW.fullmatch(text))):
            draw_setups.append((choice, cost, int(setup.group(1) or setup.group(2))))
        if enemy and _powers(enemy).get("ARTIFACT_POWER", 0) <= 0 and VULNERABLE_APPLICATION.search(text):
            triggers.append((choice, cost, target, saved))

    combos = []
    for setup_choice, setup_cost, count in draw_setups:
        for trigger_choice, trigger_cost, target, saved in triggers:
            remaining = energy - setup_cost - trigger_cost
            if setup_choice != trigger_choice and remaining >= 0:
                combos.append({"setup_choice": setup_choice, "trigger_choice": trigger_choice, "trigger": "vulnerable",
                               "draw_count": count, "target_index": target, "energy_after": remaining,
                               "estimated_incoming": incoming - saved, "estimated_hp_saved": min(saved, unblocked)})
    choices.sort(key=lambda item: (item.get("estimated_hp_saved", 0), item["energy_after"]), reverse=True)
    combos.sort(key=lambda item: (item["estimated_hp_saved"], item["energy_after"], item["draw_count"]), reverse=True)
    return choices[:6], combos[:4]



# The native hand tooltip includes player modifiers. Enemy Vulnerable is applied to each
# hit separately. Stop at effects that can change the board, costs, or the hand.
LINE_HIT = re.compile(r"^Deal (?P<damage>\d+) damage(?: (?P<hits>twice|\d+ times))?"
                      r"(?: to (?P<all>all enemies))?\.$", re.IGNORECASE)
LINE_HIT_ZH = re.compile(r"^(?:对(?P<all>所有敌人))?造成\s*(?P<damage>\d+)\s*点伤害"
                         r"(?P<hits>\d+)?(?:次)?。$")
LINE_VULNERABLE = re.compile(r"(?:Apply [1-9]\d* Vulnerable\.|给予[1-9]\d*层易伤。)", re.IGNORECASE)
LINE_WEAK = re.compile(r"(?:Apply [1-9]\d* Weak\.|给予[1-9]\d*层虚弱。)", re.IGNORECASE)
LINE_RULES = {"exhaust.", "retain.", "消耗。", "保留。"}
CORRUPTED_SELF_LOSS = {"lose 2 hp.", "失去2点生命。"}
LINE_PLAYER_POWERS = {"STRENGTH_POWER", "DEXTERITY_POWER", "WEAK_POWER", "FRAIL_POWER",
                      "VULNERABLE_POWER", "NO_DRAW_POWER", "DRAW_CARDS_NEXT_TURN_POWER", "FASTEN_POWER",
                      "REGEN_POWER", "SPECTRUM_SHIFT_POWER", "STAR_NEXT_TURN_POWER", "TYRANNY_POWER"}
# Imbalanced only triggers when the enemy's attack is fully blocked.
LINE_ENEMY_POWERS = {"DOOM_POWER", "STRENGTH_POWER", "WEAK_POWER", "VULNERABLE_POWER",
                     "IMBALANCED_POWER", "PLATING_POWER", "SHRIEK_POWER", "SURPRISE_POWER", "THIEVERY_POWER",
                     "THORNS_POWER", "VIGOR_POWER", "PLOW_POWER", "HARD_TO_KILL_POWER", "REATTACH_POWER",
                     "ILLUSION_POWER", "MINION_POWER"}
BLACK_HOLE_TARGET_POWERS = {"STRENGTH_POWER", "WEAK_POWER", "VULNERABLE_POWER", "REATTACH_POWER",
                           "ILLUSION_POWER", "MINION_POWER"}
SHOCKWAVE_SETUP = re.compile(
    r"Apply [1-9]\d* Weak and Vulnerable to ALL enemies\."
    r"|\u7ed9\u4e88\u6240\u6709\u654c\u4eba[1-9]\d*\u5c42\u865a\u5f31\u548c\u6613\u4f24\u3002",
    re.IGNORECASE,
)
ATTACK_LINE_SUFFIXES = {
    "COLLISION_COURSE": re.compile(
        r"Add a Debris into your Hand\.|\u5c06\u4e00\u5f20\u788e\u5c51\u6dfb\u52a0\u81f3\u4f60\u7684\u624b\u724c\u3002",
        re.IGNORECASE,
    ),
    "GUIDING_STAR": re.compile(
        r"Next turn, draw [1-9]\d* cards?\.|\u5728\u4e0b\u4e2a\u56de\u5408\u62bd[1-9]\d*\u5f20\u724c\u3002",
        re.IGNORECASE,
    ),
    "WROUGHT_IN_WAR": re.compile(r"Forge\s+(\d+)\.|\u94f8\u9020\s*(\d+)\u3002", re.IGNORECASE),
    "PHOTON_CUT": re.compile(
        r"Draw [1-9]\d* cards?\.\nPut 1 card from your Hand on top of your Draw Pile\."
        r"|抽[1-9]\d*张牌。\n将手牌中的一张牌放到抽牌堆顶部。",
        re.IGNORECASE,
    ),
    "NEOWS_FURY": re.compile(
        r"Put up to [1-9]\d* cards? from your Discard Pile into your Hand\."
        r"|将你弃牌堆中的至多[1-9]\d*张牌放入你的手牌。",
        re.IGNORECASE,
    ),
}


class AttackOption(NamedTuple):
    choice: int
    index: int
    energy: int
    stars: int
    damage: int
    hits: int
    target: int | None
    all_enemies: bool
    vulnerable: bool
    forge: int
    card_id: str
    self_hp_loss: int = 0


def _attack_order_damage(order, multiplier, target_hp_with_block, hp_loss_cap=None, black_hole=0):
    damage = forge = landed_hits = 0
    for option in order:
        if option.stars:
            damage += black_hole
        per_hit = option.damage + (forge if option.card_id == "SOVEREIGN_BLADE" else 0)
        per_hit = per_hit * multiplier // 100
        if hp_loss_cap is not None:
            per_hit = min(per_hit, hp_loss_cap)
        if per_hit > 0 and damage < target_hp_with_block:
            hits_to_kill = (target_hp_with_block - damage + per_hit - 1) // per_hit
            landed_hits += min(option.hits, hits_to_kill)
        damage += per_hit * option.hits
        forge += option.forge
        if option.vulnerable and multiplier == 100:
            multiplier = 150
    return damage, landed_hits
PERSISTENT_BUFF_POTIONS = {"DEXTERITY_POTION", "STRENGTH_POTION", "CULTIST_POTION", "REGEN_POTION",
                           "RADIANT_TINCTURE"}


def _line_card_options(actions, combat, *, allow_bound=False):
    energy, stars = _nonnegative(combat.get("energy")), _nonnegative(combat.get("stars"))
    if energy is None:
        return
    hand = {card.get("index"): card for card in _rows(combat.get("hand"))}
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or action.get("kind") != "play_card":
            continue
        detail = action.get("detail")
        if not isinstance(detail, dict):
            continue
        index = detail.get("card_index")
        if type(index) is not int or index not in hand:
            continue
        card = hand[index]
        cost, star_cost = _nonnegative(card.get("energy_cost")), card.get("star_cost", -1)
        affliction = card.get("affliction")
        if (card.get("id") != detail.get("card_id") or cost is None or cost > energy
                or card.get("energy_x") or card.get("star_x")
                or (affliction and (not allow_bound or affliction.get("id") != "BOUND"))
                or type(star_cost) is not int or not -1 <= star_cost <= (stars or 0)):
            continue
        yield choice, index, card, detail, cost, max(0, star_cost)


def wah_blast_survival_line(snapshot, *, melody_active=False):
    """Find a Cho setup and Wah Blast line that removes the current attack."""
    combat = snapshot["state"]
    actions = snapshot["actions"]
    enemies = _rows(combat.get("enemies"))
    attackers = [enemy for enemy in enemies if _shown_attack([enemy])[0]]
    incoming, unknown = _shown_attack(enemies)
    player = combat.get("player") or {}
    hp, block, energy = (_nonnegative(value) for value in
                         (player.get("hp"), player.get("block"), combat.get("energy")))
    if (unknown or hp is None or block is None or energy is None
            or len(attackers) != 1 or _skill_punished(enemies)):
        return None
    loss = incoming - block
    if loss < hp and not heavy_hp_loss(hp, loss):
        return None
    target = attackers[0]
    enemy_hp, enemy_block = _nonnegative(target.get("hp")), _nonnegative(target.get("block"))
    # Only use the shared attack tooltip when nothing on this target changes its damage.
    if (enemy_hp is None or enemy_block is None or any(
        _powers(enemy).keys() - {"MINION_POWER", "STRENGTH_POWER", "WEAK_POWER", "IMPALED_POWER"}
        for enemy in enemies
    )):
        return None
    options = list(_line_card_options(actions, combat, allow_bound=True))
    for blast, _, card, detail, cost, stars in options:
        if card.get("id") != "WAH_BLAST" or stars or detail.get("target_index") is not None:
            continue
        preview = _plain(detail.get("description")).splitlines()
        hit = (LINE_HIT.fullmatch(preview[0]) or LINE_HIT_ZH.fullmatch(preview[0])) if preview else None
        if not hit or not hit.group("all") or hit.group("hits"):
            continue
        damage = int(hit.group("damage")) * 2
        if damage < enemy_hp + enemy_block:
            continue
        if melody_active:
            return {"choices": [blast], "damage": damage, "target_index": target["index"]}
        bound_blast = (card.get("affliction") or {}).get("id") == "BOUND"
        for setup, _, cho, _, setup_cost, setup_stars in options:
            if (cho.get("id") in {"CHO_BARBS", "CHO_READY"} and not setup_stars and setup_cost + cost <= energy
                    and not (bound_blast and (cho.get("affliction") or {}).get("id") == "BOUND")):
                return {"choices": [setup, blast], "damage": damage, "target_index": target["index"]}
    return None


def _direct_attack_lines(actions, combat, player, enemies, player_powers):
    black_hole = player_powers.get("BLACK_HOLE_POWER", 0)
    # A Star payment adds one flat hit to each target before the card resolves.
    # Don't project it when hitting another enemy can trigger a reactive power.
    if (player_powers.keys() - LINE_PLAYER_POWERS - {"BLACK_HOLE_POWER"}
            or black_hole and any(_powers(enemy).keys() - BLACK_HOLE_TARGET_POWERS for enemy in enemies)):
        return [], [], []
    attack_limit = 10
    for relic in _rows(player.get("relics")):
        relic_id = (relic.get("id") or "").split(".")[-1]
        if relic_id not in BUFF_DAMAGE_RELICS:
            continue
        counter = _nonnegative(relic.get("counter"))
        if relic_id != "PEN_NIB" or counter is None or counter >= 9:
            return [], [], []
        # Stay within attacks that will neither trigger nor consume the double hit.
        attack_limit = 9 - counter
    energy, stars = _nonnegative(combat.get("energy")), _nonnegative(combat.get("stars")) or 0
    hand = _rows(combat.get("hand"))
    if energy is None or len(hand) > 10:
        return [], [], []
    # Weak changes the Forge increment before rounding. The live tooltip already includes
    # Weak, so project Forge only when there is one visible Blade and its full gain is known.
    project_forge = (not player_powers.get("WEAK_POWER")
                     and sum(card.get("id") == "SOVEREIGN_BLADE" for card in hand) == 1)
    options = []
    for choice, index, card, detail, cost, star_cost in _line_card_options(actions, combat):
        lines = [line.strip() for line in _plain(detail.get("description")).splitlines()
                 if line.strip() and line.strip().casefold() not in LINE_RULES]
        card_id = card["id"]
        target = detail.get("target_index")
        if card.get("type") == "Skill":
            if _skill_punished(enemies):
                continue
            if card_id == "SHOCKWAVE" and target is None and len(lines) == 1 and SHOCKWAVE_SETUP.fullmatch(lines[0]):
                options.append(AttackOption(choice, index, cost, star_cost, 0, 0, None, True, True, 0, card_id))
            elif (card_id == "KNOW_THY_PLACE" and type(target) is int and len(lines) == 2
                  and LINE_WEAK.fullmatch(lines[0]) and LINE_VULNERABLE.fullmatch(lines[1])):
                options.append(AttackOption(choice, index, cost, star_cost, 0, 0, target, False, True, 0, card_id))
            continue
        if card.get("type") != "Attack" or not lines:
            continue
        if not (hit := LINE_HIT.fullmatch(lines[0]) or LINE_HIT_ZH.fullmatch(lines[0])):
            continue
        suffix = ATTACK_LINE_SUFFIXES.get(card_id)
        followups = [line for line in lines[1:]
                     if not (LINE_VULNERABLE.fullmatch(line) or LINE_WEAK.fullmatch(line))]
        self_hp_loss = 0
        if followups and followups[-1].casefold() in CORRUPTED_SELF_LOSS:
            followups.pop()
            self_hp_loss = 2
        effect = suffix.fullmatch("\n".join(followups)) if suffix and followups else None
        if followups and effect is None:
            continue
        # A different per-target tooltip may already include a modifier. Do not reuse it
        # as the base for a hypothetical Vulnerable calculation.
        if _plain(detail.get("description")) != _plain(card.get("description")):
            continue
        hits = hit.group("hits")
        hits = 2 if hits and hits.casefold() == "twice" else int(hits.split()[0]) if hits else 1
        if not (0 < int(hit.group("damage")) and 1 <= hits <= 30):
            continue
        forge = (int(effect.group(1) or effect.group(2))
                 if project_forge and effect and card_id == "WROUGHT_IN_WAR" else 0)
        options.append(AttackOption(
            choice, index, cost, star_cost, int(hit.group("damage")), hits, detail.get("target_index"),
            bool(hit.group("all")), any(LINE_VULNERABLE.fullmatch(line) for line in lines[1:]),
            forge, card_id, self_hp_loss,
        ))

    lethal_lines, damage_lines, stun_lines = [], [], []
    thorns_in_fight = sum(max(0, _powers(enemy).get("THORNS_POWER", 0)) for enemy in enemies)
    for target in enemies:
        index, hp, block = (target.get("index"), _nonnegative(target.get("hp")), _nonnegative(target.get("block")))
        powers = _powers(target)
        if type(index) is not int or not hp or block is None or powers.keys() - LINE_ENEMY_POWERS:
            continue
        hp_loss_cap = powers.get("HARD_TO_KILL_POWER")
        # The cap is on HP lost, so Block and the cap need separate tracking.
        if hp_loss_cap is not None and (block or hp_loss_cap <= 0):
            continue
        multiplier = _vulnerable_multiplier(target)
        if multiplier is None:
            continue
        # At most one native attack per hand card for this target.
        choices = {item.index: item for item in options if item.target == index or item.all_enemies and item.target is None}
        stun_power = {"TERROR_EEL": "SHRIEK_POWER", "CEREMONIAL_BEAST": "PLOW_POWER"}.get(target.get("id"))
        stun_hp = powers.get(stun_power, 0)
        stun_damage = hp - stun_hp + block if 0 < stun_hp < hp else None
        best_kill, best_damage, best_stun = None, None, None
        for count in range(1, len(choices) + 1):
            for group in combinations(choices.values(), count):
                used_energy = sum(item.energy for item in group)
                used_stars = sum(item.stars for item in group)
                self_hp_loss = sum(item.self_hp_loss for item in group)
                if (used_energy > energy or used_stars > stars
                        or sum(bool(item.hits) for item in group) > attack_limit
                        or self_hp_loss and self_hp_loss >= (_nonnegative(player.get("hp")) or 0)):
                    continue
                # Forge before the Blade. Test each Vulnerable opener, since the opener
                # itself deals damage before applying the debuff.
                has_forge = any(item.forge for item in group)
                # Keep cards that stop the turn queue at the end when they do not set up damage.
                base_order = tuple(sorted(group, key=lambda item: (
                    item.card_id in {"COLLISION_COURSE", "GUIDING_STAR", "NEOWS_FURY", "PHOTON_CUT"},
                    has_forge and item.card_id == "SOVEREIGN_BLADE",
                )))
                orders = [base_order]
                if multiplier == 100:
                    orders += [(item, *(other for other in base_order if other != item))
                               for item in base_order if item.vulnerable]
                (total, landed_hits), order = max(
                    ((_attack_order_damage(order, multiplier, hp + block, hp_loss_cap, black_hole), order)
                     for order in orders),
                    key=lambda projected: (projected[0][0], -projected[0][1]),
                )
                line = {"target_index": index, "choices": [item.choice for item in order],
                        "damage": total, "hp_plus_block": hp + block, "energy": used_energy, "stars": used_stars}
                if self_hp_loss:
                    line["self_hp_loss"] = self_hp_loss
                if total >= hp + block:
                    # Include retaliation on the fatal hit. An area attack may still hit other enemies.
                    thorns = max(0, powers.get("THORNS_POWER", 0))
                    reflected = thorns * landed_hits + sum((thorns_in_fight - thorns) * item.hits
                                                           for item in group if item.all_enemies)
                    score = (reflected + self_hp_loss, used_energy, used_stars, count, -total)
                    if best_kill is None or score < best_kill[0]:
                        best_kill = score, {**line, "removed_attack": _shown_attack([target])[0]}
                        if reflected:
                            best_kill[1]["max_thorns_damage"] = reflected
                elif count > 1 and any(item.card_id in ATTACK_LINE_SUFFIXES or item.vulnerable
                                       for item in group):
                    per_hits = [item.damage * multiplier // 100 for item in group]
                    if hp_loss_cap is not None:
                        per_hits = [min(per_hit, hp_loss_cap) for per_hit in per_hits]
                    without_setup = sum(per_hit * item.hits + (black_hole if item.stars else 0)
                                        for item, per_hit in zip(group, per_hits))
                    if total > without_setup:
                        score = (-total, used_energy, used_stars, count)
                        if best_damage is None or score < best_damage[0]:
                            best_damage = score, {**line, "extra_damage_from_setup": total - without_setup}
                if stun_damage is not None and total >= stun_damage and not (thorns_in_fight or self_hp_loss):
                    score = (used_energy, used_stars, count, -total)
                    if best_stun is None or score < best_stun[0]:
                        best_stun = score, {**line, "stun_hp": stun_hp, "removed_attack": _shown_attack([target])[0]}
        if best_stun:
            stun_lines.append(best_stun[1])
        if best_kill:
            lethal_lines.append(best_kill[1])
        elif best_damage:
            damage_lines.append(best_damage[1])
    return (sorted(lethal_lines, key=lambda line: (-line["removed_attack"], line["energy"]))[:3],
            sorted(damage_lines, key=lambda line: -line["extra_damage_from_setup"])[:3],
            stun_lines)


def _obscura_vice_line(actions, combat, player, enemies, player_powers, unblocked):
    """Price a one-HP Parafright as a chance to stop its hit, without treating it as a kill."""
    if (combat.get("encounter") != "THE_OBSCURA_NORMAL" or len(enemies) != 2
            or type(unblocked) is not int or unblocked < 15 or player_powers.keys() - LINE_PLAYER_POWERS):
        return None
    target = next((enemy for enemy in enemies if enemy.get("id") == "PARAFRIGHT"), None)
    if not target or target.get("block") != 0 or _powers(target).keys() - {
        "ILLUSION_POWER", "MINION_POWER", "STRENGTH_POWER", "WEAK_POWER"
    }:
        return None
    damage, missing = _shown_attack([target])
    hp = _nonnegative(target.get("hp"))
    hand = _rows(combat.get("hand"))
    if not hp or missing or damage < 16 or not _obsidian_vice_damage(player, hand):
        return None
    options = {}
    for choice, _, card, detail, energy, stars in _line_card_options(actions, combat):
        card_id = card.get("id")
        lines = _plain(detail.get("description")).splitlines()
        if (card_id not in {"PHOTON_CUT", "WROUGHT_IN_WAR"} or stars or detail.get("target_index") != target["index"]
                or not lines or _plain(detail.get("description")) != _plain(card.get("description"))):
            continue
        hit = LINE_HIT.fullmatch(lines[0]) or LINE_HIT_ZH.fullmatch(lines[0])
        if hit and not (hit.group("hits") or hit.group("all")):
            options[card_id] = (choice, energy, int(hit.group("damage")))
    # Use the Forge attack first so Photon Cut ends the plan and its draw can be handled live.
    order = [options[card_id] for card_id in ("WROUGHT_IN_WAR", "PHOTON_CUT") if card_id in options]
    for size in range(1, len(order) + 1):
        for line in combinations(order, size):
            if (sum(item[1] for item in line) <= combat["energy"]
                    and sum(item[2] for item in line) == hp - 1 and len(hand) >= size + 2):
                return {"choices": [item[0] for item in line], "target_index": target["index"],
                        "attack_if_vice_hits": damage, "hp_left": 1, "min_chance_to_stop_attack": 0.5}
    return None


def _block_lines(actions, combat, player_powers, enemies, unblocked, removals, *, direct_hp_loss=0):
    energy, stars = _nonnegative(combat.get("energy")), _nonnegative(combat.get("stars")) or 0
    if (unblocked is None or not (unblocked or direct_hp_loss) or energy is None
            or len(_rows(combat.get("hand"))) > 10 or _skill_punished(enemies)):
        return None
    removals_by_choice = {row["choice"]: row for row in removals}
    options = {}
    for choice, index, card, _detail, cost, star_cost in _line_card_options(actions, combat, allow_bound=True):
        # Only trust the defensive effect itself. Skip attacks or cards which draw before
        # blocking, as well as optional selection and reactive Block conditions.
        removal = removals_by_choice.get(choice, {})
        direct = removal.get("removes_damage", 0) if removal.get("bypasses_block") else 0
        block = _block_preview(actions[choice - 1], player_powers) if card.get("type") == "Skill" else 0
        blockable = max(block, removal.get("removes_damage", 0) if not direct else 0)
        if blockable or direct:
            bound = (card.get("affliction") or {}).get("id") == "BOUND"
            options.setdefault(index, (choice, cost, star_cost, blockable, bound, direct))
    best = (0, 0, 0, 0, ())
    best_direct_left = direct_hp_loss
    skill_limit = min(len(options), player_powers.get("SMOGGY_POWER", len(options)))
    for size in range(1, skill_limit + 1):
        for group in combinations(options.values(), size):
            cost, star_cost = sum(item[1] for item in group), sum(item[2] for item in group)
            if cost > energy or star_cost > stars or sum(item[4] for item in group) > 1:
                continue
            direct_saved = min(direct_hp_loss, sum(item[5] for item in group))
            saving = min(unblocked, sum(item[3] for item in group)) + direct_saved
            option = (saving, -cost, -star_cost, -size, tuple(item[0] for item in group))
            if option > best:
                best = option
                best_direct_left = direct_hp_loss - direct_saved
    if best[0]:
        result = {"choices": list(best[4]), "energy": -best[1], "stars": -best[2],
                  "hp_loss": unblocked + direct_hp_loss - best[0]}
        if best_direct_left:
            result["direct_hp_loss"] = best_direct_left
        return result


def black_hole_before_particle_wall(actions, combat, selected, unblocked):
    """Start the power before spending Stars when the same defense stays affordable."""
    if (actions[selected - 1]["detail"].get("card_id") != "PARTICLE_WALL"
            or combat.get("encounter") != "SLUMBERING_BEETLE_NORMAL"
            or not unblocked or combat.get("ringing")):
        return None
    player_powers = _powers(combat.get("player") or {})
    enemies = _rows(combat.get("enemies"))
    if ("BLACK_HOLE_POWER" in player_powers or player_powers.keys() - LINE_PLAYER_POWERS
            or any(_powers(enemy).get("SLUMBER_POWER") and (_nonnegative(enemy.get("block")) or 0) < 6
                   for enemy in enemies)):
        return None
    options = list(_line_card_options(actions, combat))
    wall = next((item for item in options if item[0] == selected), None)
    power = next((item for item in options if item[2].get("id") == "BLACK_HOLE"), None)
    if not wall or not power:
        return None
    wall_energy, wall_stars = wall[-2:]
    power_energy, power_stars = power[-2:]
    energy = combat["energy"] - wall_energy - power_energy
    stars = (combat.get("stars") or 0) - wall_stars - power_stars
    block = _block_preview(actions[selected - 1], player_powers)
    if energy < 0 or stars < wall_stars or not wall_stars or not block:
        return None
    after_wall = {**combat, "energy": energy, "stars": stars}
    damage_left = max(0, unblocked - block)
    followup = _block_lines(actions, after_wall, player_powers, enemies, damage_left, [])
    if not damage_left or followup and followup["hp_loss"] == 0:
        return {"choices": [power[0], selected], "block_after_power_available": unblocked}
    return None


def _reflect_star_setup(actions, combat, player_powers, enemies, unblocked):
    energy, stars = _nonnegative(combat.get("energy")), _nonnegative(combat.get("stars"))
    if (energy is None or stars is None or unblocked is None or unblocked < 5
            or combat.get("ringing") or player_powers.get("SMOGGY_POWER") or _skill_punished(enemies)):
        return None
    for card in _rows(combat.get("hand")):
        cost, star_cost = _nonnegative(card.get("energy_cost")), _nonnegative(card.get("star_cost"))
        if (card.get("id") != "REFLECT" or cost is None or star_cost is None or star_cost <= stars
                or card.get("affliction") or card.get("energy_x") or card.get("star_x")):
            continue
        preview = {"kind": "play_card", "detail": {"card_id": "REFLECT", "description": card.get("description")}}
        block = _block_preview(preview, player_powers)
        if block < unblocked:
            continue
        for choice, _, _, detail, setup_cost, _ in _line_card_options(actions, combat):
            if detail.get("card_id") != "VENERATE" or cost + setup_cost > energy:
                continue
            description = detail.get("description") or ""
            gained = description.count("[img]res://images/packed/sprite_fonts/star_icon.png[/img]")
            if stars + gained >= star_cost:
                return {"choice": choice, "stars_after_setup": stars + gained, "block": block}
    return None


def _regent_next_draw_lethal(combat, player, enemies, player_powers, defense=None):
    """Count fixed attacks already retained or guaranteed to be drawn after defense."""
    if (len(enemies) != 1 or enemies[0].get("id") not in {"CORPSE_SLUG", "SEAPUNK", "SEWER_CLAM"}
            or player_powers.keys() - {"FRAIL_POWER", "DRAW_CARDS_NEXT_TURN_POWER"}
            or any(relic.get("id") not in {"DIVINE_RIGHT", "STONE_HUMIDIFIER", "BLOOD_VIAL", "RED_MASK",
                                          "HAPPY_FLOWER", "LOST_COFFER"}
                   for relic in _rows(player.get("relics")))):
        return None
    enemy = enemies[0]
    clam = enemy.get("id") == "SEWER_CLAM"
    expected_intent = "Buff" if clam else "Attack"
    powers = _powers(enemy)
    allowed_powers = {"STRENGTH_POWER", "WEAK_POWER", "VULNERABLE_POWER"}
    allowed_powers.add("PLATING_POWER" if clam else "RAVENOUS_POWER")
    if (powers.keys() - allowed_powers or not enemy.get("intents")
            or any(intent.get("type") != expected_intent for intent in enemy["intents"])):
        return None
    pile = _rows(combat.get("draw_pile"))
    energy, stars = _nonnegative(combat.get("max_energy")), _nonnegative(combat.get("stars"))
    hp, block = _nonnegative(enemy.get("hp")), _nonnegative(enemy.get("block"))
    counts = [row.get("count") for row in pile]
    retained = [card for card in _rows(combat.get("hand")) if "Retain" in (card.get("keywords") or ())]
    draw = 5 + max(0, player_powers.get("DRAW_CARDS_NEXT_TURN_POWER", 0))
    if (not all(type(count) is int and count > 0 for count in counts)
            or sum(counts) != combat.get("draw_pile_count") or sum(counts) > min(draw, 10 - len(retained))
            or energy is None or stars is None or not hp or block is None
            or any(card.get("affliction") for card in _rows(combat.get("hand")))):
        return None
    guaranteed = [row for row in pile if row.get("id") in {"FALLING_STAR", "STRIKE_REGENT", "COLLISION_COURSE"}]
    guaranteed += [{**row, "count": 1} for row in retained if row.get("id") == "SOVEREIGN_BLADE"]
    attacks = []
    for row in guaranteed:
        if row.get("energy_x") or row.get("star_x"):
            continue
        cost, star_cost = _nonnegative(row.get("energy_cost")), row.get("star_cost")
        if cost is None or type(star_cost) is not int or star_cost < -1:
            continue
        text = _plain(row.get("description")).splitlines()
        if row["id"] == "SOVEREIGN_BLADE":
            text = [line for line in text if line.lower() not in {"retain.", "保留。"}]
        if not text or not (hit := LINE_HIT.fullmatch(text[0]) or LINE_HIT_ZH.fullmatch(text[0])):
            continue
        if hit.group("hits") or hit.group("all"):
            continue
        attacks.extend([(cost, max(0, star_cost), int(hit.group("damage")), row["id"])] * row["count"])
    target = hp + block + max(0, powers.get("PLATING_POWER", 0))
    stars_budget = stars - (defense or {}).get("stars", 0)
    for size in range(1, len(attacks) + 1):
        for line in combinations(attacks, size):
            damage = sum(row[2] for row in line)
            if (damage >= target and sum(row[0] for row in line) <= energy
                    and sum(row[1] for row in line) <= stars_budget):
                return {"damage_before_vulnerable": damage, "target_hp_plus_block": target,
                        "cards": [row[3] for row in line]}
    return None


def _ceremonial_next_stun(combat, enemies, player_powers):
    """Check the deterministic Fallen Star, Photon Cut and retained Blade line."""
    if combat.get("encounter") != "CEREMONIAL_BEAST_BOSS" or len(enemies) != 1:
        return None
    enemy = enemies[0]
    powers = _powers(enemy)
    threshold, hp = powers.get("PLOW_POWER", 0), _nonnegative(enemy.get("hp"))
    if (not hp or not 0 < threshold < hp or enemy.get("block") != 0
            or powers.keys() - {"PLOW_POWER", "STRENGTH_POWER", "WEAK_POWER"}
            or {intent.get("type") for intent in enemy.get("intents", ())} != {"Attack", "Buff"}):
        return None
    flex = player_powers.get("FLEX_POTION_POWER", 0)
    if (player_powers.keys() - {"STRENGTH_POWER", "FLEX_POTION_POWER"}
            or player_powers.get("STRENGTH_POWER", 0) != flex):
        return None
    pile = _rows(combat.get("draw_pile"))
    counts = [card.get("count") for card in pile]
    hand = _rows(combat.get("hand"))
    retained = [card for card in hand if "Retain" in (card.get("keywords") or ())]
    if (not all(type(count) is int and count > 0 for count in counts)
            or sum(counts) != combat.get("draw_pile_count") or sum(counts) > min(5, 10 - len(retained))):
        return None
    cards = {card["id"]: card for card in pile}
    blade = next((card for card in retained if card.get("id") == "SOVEREIGN_BLADE"), None)
    star, photon = cards.get("FALLING_STAR"), cards.get("PHOTON_CUT")
    if not (star and photon and blade):
        return None
    damage, energy, stars = [], 0, 0
    for card in (star, photon, blade):
        cost, star_cost = _nonnegative(card.get("energy_cost")), card.get("star_cost")
        if (cost is None or card.get("affliction") or card.get("energy_x") or card.get("star_x")
                or type(star_cost) is not int or star_cost < -1):
            return None
        lines = [line.strip() for line in _plain(card.get("description") or "").splitlines()
                 if line.strip() and line.strip().casefold() not in LINE_RULES]
        hit = (LINE_HIT.fullmatch(lines[0]) or LINE_HIT_ZH.fullmatch(lines[0])) if lines else None
        if not hit or hit.group("hits") or hit.group("all"):
            return None
        if card is star and not any(LINE_VULNERABLE.fullmatch(line) for line in lines[1:]):
            return None
        damage.append(max(0, int(hit.group("damage")) - (flex if card is blade else 0)))
        energy += cost
        stars += max(0, star_cost)
    total = damage[0] + damage[1] * 3 // 2 + damage[2] * 3 // 2
    if (energy <= (_nonnegative(combat.get("max_energy")) or 0)
            and stars <= (_nonnegative(combat.get("stars")) or 0) and hp - total <= threshold):
        return {"stun_hp": threshold, "damage": total, "energy": energy, "stars": stars}
    return None


def _vine_shambler_finish_next_turn(actions, combat, player, enemies, player_powers, block_line, unblocked):
    """Prove a potion-free finish using a card drawn before the next shuffle."""
    if (combat.get("encounter") != "VINE_SHAMBLER_NORMAL" or len(enemies) != 1 or player_powers
            or not any(action["kind"] == "use_potion" and action["detail"].get("potion_id") == "FLEX_POTION"
                       for action in actions)
            or (unblocked and (not block_line or block_line["hp_loss"] != 0))):
        return None
    enemy = enemies[0]
    hp = _nonnegative(enemy.get("hp"))
    if (not hp or enemy.get("block") != 0 or _powers(enemy).keys() - {"WEAK_POWER"}
            or {intent.get("type") for intent in enemy.get("intents", ())} != {"Attack", "CardDebuff"}):
        return None
    pile = _rows(combat.get("draw_pile"))
    counts = [card.get("count") for card in pile]
    max_energy = _nonnegative(combat.get("max_energy"))
    retained = sum("Retain" in (card.get("keywords") or ()) for card in _rows(combat.get("hand")))
    if (max_energy is None or retained > 4 or not all(type(count) is int and count > 0 for count in counts)
            or sum(counts) != combat.get("draw_pile_count") or sum(counts) > 5):
        return None
    # Grasping Vines adds Tangled (one more Energy for attacks) without changing the draw pile.
    guaranteed = []
    for card in pile:
        cost = _nonnegative(card.get("energy_cost"))
        if (card.get("id") not in {"STRIKE_REGENT", "WROUGHT_IN_WAR"} or cost is None
                or cost + 1 > max_energy or card.get("affliction") or card.get("energy_x") or card.get("star_x")
                or card.get("star_cost") not in (-1, 0)):
            continue
        first_line = _plain(card.get("description") or "").partition("\n")[0]
        hit = LINE_HIT.fullmatch(first_line) or LINE_HIT_ZH.fullmatch(first_line)
        if hit and not (hit.group("hits") or hit.group("all")):
            guaranteed.append((int(hit.group("damage")), -cost - 1, card["id"]))
    if not guaranteed:
        return None
    damage, negative_cost, card_id = max(guaranteed)
    target = hp - damage
    defense = block_line or {"choices": [], "energy": 0, "stars": 0}
    attacks = []
    if target > 0:
        remaining = {**combat, "energy": combat["energy"] - defense["energy"],
                     "stars": (combat.get("stars") or 0) - defense["stars"]}
        finishes, _, _ = _direct_attack_lines(
            actions, remaining, player, [{**enemy, "hp": target}], player_powers,
        )
        if not finishes:
            return None
        attacks = finishes[0]["choices"]
    return {"choices": defense["choices"] + attacks, "drawn_card": card_id,
            "next_turn_damage": damage, "next_turn_energy": -negative_cost}


def _potion_timing(actions, combat, player_powers, without_potion, block_line, hp):
    context = []
    opening = combat.get("turn") == 1 and str(combat.get("encounter") or "").endswith(("_ELITE", "_BOSS"))
    skills = {choice for choice, _, card, _, _, _ in _line_card_options(actions, combat, allow_bound=True)
              if card.get("type") == "Skill" and _block_preview(actions[choice - 1], player_powers)}
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or action.get("kind") != "use_potion":
            continue
        detail = action.get("detail") or {}
        item = detail.get("potion_id")
        block = _block_preview(action, player_powers)
        if block and type(without_potion) is int and without_potion > 0:
            saved = min(block, without_potion)
        elif block_line and without_potion:
            _, bonus, _ = _dexterity_potion_bonus(detail, player_powers)
            saved = min(without_potion, bonus * len(skills.intersection(block_line["choices"])))
        else:
            saved = 0
        if saved:
            context.append({"choice": choice, "saves_after_known_card_defense": saved,
                            "prevents_lethal": bool(hp and without_potion >= hp > without_potion - saved)})
        elif (item == "ATTACK_POTION" and heavy_hp_loss(hp, without_potion)
              and any(line["hits"] > 1 for enemy in _rows(combat.get("enemies"))
                      for line in _attack_hit_profiles(enemy))):
            context.append({"choice": choice, "remaining_hp_loss_after_known_defense": without_potion,
                            "timing": "Consider looking for playable Weak or a free attack that removes the attacker. "
                                      "Read the offered cards before committing the rest of the turn."})
        elif opening and item in PERSISTENT_BUFF_POTIONS:
            context.append({"choice": choice, "timing": "early payoff over several turns"})
    return context


def combat_tactics(snapshot):
    """Use the snapshot and its numbered legal actions only. This never chooses an action."""
    if snapshot.get("screen") != "combat" or not isinstance(snapshot.get("state"), dict):
        return {}
    combat = snapshot["state"]
    player = combat.get("player")
    player = player if isinstance(player, dict) else {}
    enemies = _rows(combat.get("enemies"))
    actions = snapshot.get("actions")
    actions = actions if isinstance(actions, list) else []
    incoming, missing = _shown_attack(enemies)
    hp, block = _nonnegative(player.get("hp")), _nonnegative(player.get("block"))
    player_powers = _powers(player)
    hand_damage, direct_hp_loss, hand_damage_cards = _hand_damage(combat)
    constrict = max(0, player_powers.get("CONSTRICT_POWER", 0))
    total_incoming = incoming + hand_damage + constrict
    blockable_unblocked = max(0, total_incoming - block) if block is not None else None
    unblocked = blockable_unblocked + direct_hp_loss if blockable_unblocked is not None else None
    lethal = unblocked >= hp if unblocked is not None and hp else None
    if missing and lethal is False:
        lethal = None
    result = {"shown_attack_damage": incoming, "unblocked_now": unblocked, "shown_attack_lethal": lethal}
    if not missing and unblocked is not None:
        if heavy_hp_loss(hp, unblocked):
            result["hp_loss_if_turn_ends_now"] = "heavy"
        elif unblocked >= NOTICEABLE_HP_LOSS:
            result["hp_loss_if_turn_ends_now"] = "noticeable"
    attacks = []
    for enemy in enemies:
        damage, unknown = _shown_attack([enemy])
        if not damage:
            continue
        profiles = _attack_hit_profiles(enemy)
        if len(enemies) > 1 or any(line["hits"] > 1 for line in profiles):
            attack = {"target_index": enemy.get("index"), "name": enemy.get("name"),
                      "damage": damage, "hits": profiles}
            if weak_savings := _weak_damage_reduction(enemy):
                attack["weak_saves_at_least"] = weak_savings
            if unknown:
                attack["partial"] = True
            attacks.append(attack)
    if attacks:
        result["incoming_by_target"] = sorted(attacks, key=lambda attack: -attack["damage"])
    if poison := _poison_outlook(combat, enemies, player_powers, hand_damage + direct_hp_loss + constrict):
        result["poison_before_enemy_actions"] = poison
    if doom := _doom_after_enemy_actions(enemies):
        result["doom_after_enemy_actions"] = doom
        if _doom_covers_living(enemies, doom):
            result["doom_covers_living"] = True
    if arrows := _arrow_summary(actions, combat):
        result["arrows"] = arrows
    melodies = combat.get("active_melodies")
    if isinstance(melodies, list):
        result["active_melodies"] = melodies
    pen_nib = next((relic.get("counter") for relic in _rows(player.get("relics"))
                    if (relic.get("id") or "").split(".")[-1] == "PEN_NIB"), None)
    if type(pen_nib) is int and 7 <= pen_nib <= 9:
        result["pen_nib_doubles_attack_number_from_now"] = 10 - pen_nib
    if kills := shown_kill_choices(actions, combat):
        result["shown_kill_choices"] = kills
    if constrict:
        result["end_of_turn_constrict_damage"] = constrict
    if hand_damage or direct_hp_loss:
        result["end_of_turn_hand_damage"] = hand_damage + direct_hp_loss
        if direct_hp_loss:
            result["end_of_turn_hand_hp_loss_ignoring_block"] = direct_hp_loss
        if removals := _hand_damage_choices(actions, combat, hand_damage_cards, blockable_unblocked):
            result["hand_damage_choices"] = [item for item in removals if item["estimated_hp_saved"] > 0] or removals
    if missing:
        result["some_intent_damage_unavailable"] = True
    lethal_lines, damage_lines, stun_lines = _direct_attack_lines(actions, combat, player, enemies, player_powers)
    if stun_lines:
        result["known_stun_lines"] = stun_lines
    if lethal_lines:
        result["known_lethal_lines"] = lethal_lines
    if damage_lines:
        result["ordered_attack_lines"] = damage_lines
    if not missing:
        if near_kill := _obscura_vice_line(actions, combat, player, enemies, player_powers, unblocked):
            result["obsidian_vice_near_kill"] = near_kill
        block_line = _block_lines(actions, combat, player_powers, enemies, blockable_unblocked,
                                  result.get("hand_damage_choices", []), direct_hp_loss=direct_hp_loss)
        if block_line:
            result["known_defense_line"] = block_line
            if (hp and block_line["hp_loss"] < min(hp, unblocked) and not block_line["stars"] and not stun_lines
                    and (next_stun := _ceremonial_next_stun(combat, enemies, player_powers))):
                result["ceremonial_stun_from_next_draw"] = next_stun
            if (len(enemies) == 1 and incoming > 0 and len(block_line["choices"]) == 1
                    and not hand_damage and not direct_hp_loss and not constrict):
                choice = block_line["choices"][0]
                action = actions[choice - 1]
                if action["detail"].get("card_id") == "REFLECT":
                    result["reflect_defense"] = {
                        "choice": choice, "blocked_damage_reflected": min(incoming, block + _block_preview(action, player_powers))}
            if (hp and block_line["hp_loss"] < hp and not lethal_lines
                    and (next_lethal := _regent_next_draw_lethal(combat, player, enemies, player_powers, block_line))):
                result["lethal_from_next_draw"] = next_lethal
        if (not lethal_lines and not hand_damage and not constrict
                and (block_line or {}).get("hp_loss", unblocked) != 0
                and (reflect_setup := _reflect_star_setup(actions, combat, player_powers, enemies, unblocked))):
            result["reflect_star_setup"] = reflect_setup
        if unblocked and lethal_lines:
            for line in lethal_lines:
                if not line["removed_attack"]:
                    continue
                thorns = line.get("max_thorns_damage", 0)
                direct_loss = max(0, thorns - block)
                self_loss = line.get("self_hp_loss", 0)
                damage_left = max(0, total_incoming - line["removed_attack"] - max(0, block - thorns))
                after_kill = {**combat, "energy": combat["energy"] - line["energy"],
                              "stars": (combat.get("stars") or 0) - line["stars"]}
                remaining_enemies = [enemy for enemy in enemies if enemy.get("index") != line["target_index"]]
                if direct_loss and not remaining_enemies and not (hand_damage or direct_hp_loss or constrict):
                    # Block has to be in place before the first counterattack.
                    before_attack = _block_lines(actions, after_kill, player_powers, enemies, direct_loss, [])
                    if before_attack:
                        line["pre_attack_block_choices"] = before_attack["choices"]
                        line["hp_loss_with_remaining_block"] = self_loss + before_attack["hp_loss"]
                        continue
                followup = _block_lines(actions, after_kill, player_powers, remaining_enemies, damage_left,
                                        result.get("hand_damage_choices", []), direct_hp_loss=direct_hp_loss)
                line["hp_loss_with_remaining_block"] = self_loss + direct_loss + (
                    followup["hp_loss"] if followup else damage_left + direct_hp_loss)
                if followup:
                    line["followup_block_choices"] = followup["choices"]
        remaining_direct = block_line.get("direct_hp_loss", 0) if block_line else direct_hp_loss
        remaining_damage = block_line["hp_loss"] - remaining_direct if block_line else blockable_unblocked
        if potion_timing := _potion_timing(
                actions, combat, player_powers, remaining_damage,
                block_line, hp - remaining_direct if hp is not None else None):
            result["potion_timing"] = potion_timing
        if (unblocked == 0 and not incoming and not hand_damage and not direct_hp_loss and not constrict
                and combat.get("encounter") == "SEWER_CLAM_NORMAL"
                and (next_lethal := _regent_next_draw_lethal(combat, player, enemies, player_powers))):
            result["safe_lethal_from_next_draw"] = next_lethal
        if (not lethal_lines and not hand_damage and not direct_hp_loss and not constrict
                and (finish := _vine_shambler_finish_next_turn(
                    actions, combat, player, enemies, player_powers, block_line, unblocked,
                ))):
            result["safe_finish_without_flex"] = finish
    if risks := _timed_defeat_risks(actions, combat, player, enemies):
        result["forced_defeat_countdowns"] = risks
    if combos := _damage_buff_combos(actions, combat, player, enemies, player_powers):
        result["damage_buff_combos"] = [combo for combo in combos if combo["enables_lethal"]]
        result["damage_setup_choices"] = [combo for combo in combos if not combo["enables_lethal"]]
    if defense := _defense_buff_combos(actions, player_powers,
                                       hp - direct_hp_loss if hp is not None else None,
                                       blockable_unblocked, not missing):
        result["defense_buff_combos"] = defense
    if lethal:
        choices, combos = _survival_setups(actions, combat, player, enemies, player_powers, total_incoming, blockable_unblocked)
        if choices:
            result["survival_setup_choices"] = choices
        if combos:
            result["conditional_draw_combos"] = combos
    elif unblocked is not None and unblocked >= 12:
        choices = _defense_generation_choices(actions, _nonnegative(combat.get("energy")))
        if choices:
            result["survival_setup_choices"] = choices

    reminders = []
    ringing = combat.get("ringing")
    if isinstance(ringing, dict):
        remaining = _nonnegative(ringing.get("ringed_plays_remaining"))
        if remaining == 0:
            reminders.append("Ringing: the chance to play an affected card is spent. Use the live legal actions for unaffected cards or potions.")
        elif remaining is not None:
            reminders.append("Ringing: an affected card can only be played first this turn. An unaffected first card uses that chance too. Check survival before the first card; potions are separate.")
    elif player_powers.get("RINGING_POWER", 0) > 0:
        reminders.append("Ringing can block affected cards. Use the live legal actions for playable cards and potions.")
    for enemy in enemies:
        target = _nonnegative(enemy.get("index"))
        if target is None:
            continue
        powers = _powers(enemy)
        slippery, plow = powers.get("SLIPPERY_POWER", 0), powers.get("PLOW_POWER", 0)
        if slippery > 0:
            reminders.append(f"Enemy {target}: the next {slippery} unblocked HP-loss events each remove at most 1 HP. Cheap or multi-hit plays can strip Slippery; fully blocked hits do not.")
        enemy_hp = _nonnegative(enemy.get("hp"))
        if plow > 0 and enemy_hp is not None:
            gap = max(1, enemy_hp - plow)
            reminders.append(f"Enemy {target}: Plow stuns and clears Strength at {plow} HP or below. It needs {gap} more unblocked HP loss; include its Block and compare damage before ending the turn.")
    if reminders:
        result["reminders"] = reminders

    severe = lethal or heavy_hp_loss(hp, unblocked)
    if severe and any(isinstance(action, dict) and action.get("kind") == "end_turn" for action in actions):
        candidates = _before_end_turn(actions, combat, enemies, player_powers, blockable_unblocked)
        candidates += [item for item in result.get("hand_damage_choices", []) if item["estimated_hp_saved"] > 0]
        candidates.sort(key=lambda item: item["estimated_hp_saved"], reverse=True)
        if candidates:
            result["choices_before_end_turn"] = candidates[:4]
    return result


# Relics that make unspent energy or unplayed cards worth something next turn.
CARRY_OVER_RELICS = frozenset({"ICE_CREAM", "RUNIC_PYRAMID"})
PLAIN_BLOCK_TEXT = re.compile(r"(?:Gain ([1-9]\d*) Block\.|获得([1-9]\d*)点格挡。)", re.IGNORECASE)


def end_turn_guard(snapshot):
    """Use affordable immediate mitigation against shown damage before ending the turn."""
    if snapshot.get("screen") != "combat" or not isinstance(snapshot.get("state"), dict):
        return None
    combat = snapshot["state"]
    player = combat.get("player") if isinstance(combat.get("player"), dict) else {}
    actions = snapshot.get("actions") if isinstance(snapshot.get("actions"), list) else []
    if not any(isinstance(action, dict) and action.get("kind") == "end_turn" for action in actions):
        return None
    if any(relic.get("id") in CARRY_OVER_RELICS for relic in _rows(player.get("relics"))):
        return None
    enemies = _rows(combat.get("enemies"))
    if _skill_punished(enemies):
        # Every Skill feeds an Enrage enemy permanent Strength; leave that trade to the model.
        return None
    by_index = {enemy.get("index"): enemy for enemy in enemies}
    incoming, _ = _shown_attack(enemies)
    hand_damage, direct_hp_loss, hand_damage_cards = _hand_damage(combat)
    block = _nonnegative(player.get("block"))
    energy = _nonnegative(combat.get("energy"))
    if block is None or energy is None:
        return None
    constrict = max(0, _powers(player).get("CONSTRICT_POWER", 0))
    blockable_unblocked = max(0, incoming + hand_damage + constrict - block)
    unblocked = blockable_unblocked + direct_hp_loss
    if unblocked <= 0:
        return None
    hand = {card.get("index"): card for card in _rows(combat.get("hand")) if type(card.get("index")) is int}
    best = None

    def consider(option):
        nonlocal best
        if best is None or (option["estimated_hp_saved"], -option["energy_cost"]) > (
                best["estimated_hp_saved"], -best["energy_cost"]):
            best = option

    # Playing a Toxic-like card removes its end-of-turn damage, whatever else it does.
    for removal in _hand_damage_choices(actions, combat, hand_damage_cards, blockable_unblocked):
        cost = removal["energy_cost"]
        if cost is not None and cost <= energy and removal["estimated_hp_saved"] > 0:
            consider({"choice": removal["choice"], "card_id": removal["card_id"], "block": 0,
                      "removes_hand_damage": removal["removes_damage"],
                      "energy_cost": cost, "unblocked_before": unblocked,
                      "estimated_hp_saved": removal["estimated_hp_saved"]})
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or action.get("kind") != "play_card":
            continue
        detail = action.get("detail") if isinstance(action.get("detail"), dict) else {}
        card = hand.get(detail.get("card_index"), {})
        cost = _nonnegative(card.get("energy_cost"))
        keywords = {str(word).casefold() for word in card.get("keywords") or []}
        if (card.get("id") != detail.get("card_id") or cost is None or cost > energy or card.get("energy_x")
                or card.get("affliction") or "retain" in keywords or card.get("type") != "Skill"):
            continue
        text = " ".join(_plain(detail.get("description") or card.get("description")).split())
        if card.get("id") in {"GATHER_LIGHT", "PARTICLE_WALL"}:
            match = BLOCK_TEXT.match(text)  # These cards also give Stars or return to hand.
        else:
            match = PLAIN_BLOCK_TEXT.fullmatch(text) or WEAK_BLOCK_TEXT.fullmatch(text)
        if not match or (_nonnegative(card.get("star_cost")) or 0) > (_nonnegative(combat.get("stars")) or 0):
            continue
        gain = int(match.group(1) or match.group(2))
        target = by_index.get(detail.get("target_index"))
        weak_reduction = _weak_block_reduction(detail, target)
        option = {"choice": choice, "card_id": card.get("id"), "block": gain, "energy_cost": cost,
                  "unblocked_before": unblocked, "estimated_hp_saved": min(gain + weak_reduction, blockable_unblocked)}
        if option["estimated_hp_saved"] == 0:
            continue
        if weak_reduction:
            option["estimated_weak_reduction"] = weak_reduction
        consider(option)
    return best
