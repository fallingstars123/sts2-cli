"""Summarize visible Steam combat risks and native legal alternatives for the model."""

import re


DIRECT_BLOCK_CARDS = frozenset({"ARMAMENTS", "BACKFLIP", "EVIL_EYE", "FLAME_BARRIER", "IRON_WAVE", "SHRUG_IT_OFF", "TAUNT"})
DIRECT_DAMAGE_CARDS = {"BASH": (8, 2), "DISMANTLE": (8, 2), "STRIKE_IRONCLAD": (6, 3)}
PLAYER_DAMAGE_POWERS = frozenset({"DEXTERITY_POWER", "RINGING_POWER", "STRENGTH_POWER", "VULNERABLE_POWER"})
TARGET_DAMAGE_POWERS = frozenset({"PLOW_POWER", "STRENGTH_POWER", "VULNERABLE_POWER", "WEAK_POWER"})
BLOCK_PREVIEW_POWERS = PLAYER_DAMAGE_POWERS | {
    "DEMON_FORM_POWER", "FLAME_BARRIER_POWER", "JUGGLING_POWER", "NO_DRAW_POWER", "VICIOUS_POWER", "WEAK_POWER",
}
BLOCK_TEXT = re.compile(r"^(?:Gain ([0-9]+) Block\.|获得([0-9]+)点格挡。)", re.IGNORECASE)
TEXT_TAG = re.compile(r"\[/?[A-Za-z]+\]")
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


def _block_preview(action, player_powers):
    if player_powers.keys() - BLOCK_PREVIEW_POWERS:
        return 0
    detail = action["detail"]
    if action.get("kind") == "play_card":
        card_id = detail.get("card_id")
        if not isinstance(card_id, str) or not (card_id.startswith("DEFEND_") or card_id in DIRECT_BLOCK_CARDS):
            return 0
    elif action.get("kind") != "use_potion" or detail.get("potion_id") != "BLOCK_POTION":
        return 0
    preview = _plain(detail.get("description"))
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
    skill_penalty = _skill_penalty(enemies)
    candidates = []
    for choice, action in enumerate(actions, 1):
        if not isinstance(action, dict) or not isinstance(action.get("detail"), dict):
            continue
        block = _block_preview(action, player_powers)
        if block > 0:
            played = hand.get(action["detail"].get("card_index"), {}) if action.get("kind") == "play_card" else {}
            penalty = skill_penalty if played.get("type") == "Skill" else 0
            saved = unblocked - max(0, unblocked + penalty - block)
            if saved > 0:
                candidate = {"choice": choice, "kind": "block", "shown_block_gain": block, "estimated_hp_saved": saved}
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
            if match := DEXTERITY_GAIN.fullmatch(_plain(detail.get("description"))):
                buffs.append((choice, int(match.group(1) or match.group(2))))
    combos = []
    for buff_choice, bonus in buffs:
        for block_choice, block in blocks:
            buffed = block + bonus
            saved = min(unblocked, buffed) - min(unblocked, block)
            if saved:
                combos.append({"buff_choice": buff_choice, "block_choice": block_choice, "buff_kind": "dexterity",
                               "buff_amount": bonus, "duration": "rest_of_combat",
                               "baseline_block": block, "buffed_block": buffed,
                               "estimated_hp_saved": saved, "prevents_lethal": complete and unblocked - block >= hp > unblocked - buffed})
    combos.sort(key=lambda combo: (combo["prevents_lethal"], combo["estimated_hp_saved"]), reverse=True)
    return combos[:4]


def _weak_damage_reduction(enemy):
    powers = _powers(enemy)
    if powers.get("WEAK_POWER", 0) > 0 or powers.get("ARTIFACT_POWER", 0) > 0:
        return 0
    reduction = 0
    for intent in _rows(enemy.get("intents")):
        damage, hits = _nonnegative(intent.get("damage")), _nonnegative(intent.get("hits"))
        if (not damage or not hits or intent.get("type") != "Attack"
                or intent.get("total_damage") != damage * hits):
            continue
        # The displayed hit was rounded down already. Use an upper bound after Weak.
        weakened = (3 * (damage + 1) - 1) // 4
        reduction += (damage - weakened) * hits
    return reduction


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
        if weak := WEAK_APPLICATION.search(text):
            affected = enemies if weak.group("all") else (enemy,) if enemy else ()
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
    unblocked = max(0, incoming - block) if block is not None else None
    lethal = unblocked >= hp if unblocked is not None and hp else None
    if missing and lethal is False:
        lethal = None
    result = {"shown_attack_damage": incoming, "unblocked_now": unblocked, "shown_attack_lethal": lethal}
    if missing:
        result["some_intent_damage_unavailable"] = True
    if risks := _timed_defeat_risks(actions, combat, player, enemies):
        result["forced_defeat_countdowns"] = risks
    if combos := _damage_buff_combos(actions, combat, player, enemies, player_powers):
        result["damage_buff_combos"] = [combo for combo in combos if combo["enables_lethal"]]
        result["damage_setup_choices"] = [combo for combo in combos if not combo["enables_lethal"]]
    if defense := _defense_buff_combos(actions, player_powers, hp, unblocked, not missing):
        result["defense_buff_combos"] = defense
    if lethal:
        choices, combos = _survival_setups(actions, combat, player, enemies, player_powers, incoming, unblocked)
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

    severe = unblocked is not None and hp and (lethal or unblocked >= max(8, hp // 4))
    if severe and any(isinstance(action, dict) and action.get("kind") == "end_turn" for action in actions):
        candidates = _before_end_turn(actions, combat, enemies, player_powers, unblocked)
        if candidates:
            result["choices_before_end_turn"] = candidates
    return result


# Relics that make unspent energy or unplayed cards worth something next turn.
CARRY_OVER_RELICS = frozenset({"ICE_CREAM", "RUNIC_PYRAMID"})
PLAIN_BLOCK_TEXT = re.compile(r"(?:Gain ([1-9]\d*) Block\.|获得([1-9]\d*)点格挡。)", re.IGNORECASE)


def end_turn_guard(snapshot):
    """Return a plain block play to make before ending the turn, or None.

    Ending a turn with energy left and an affordable card whose only effect is Block, while
    shown attacks would get through, wastes HP for nothing. This only fires for that case.
    """
    if snapshot.get("screen") != "combat" or not isinstance(snapshot.get("state"), dict):
        return None
    combat = snapshot["state"]
    player = combat.get("player") if isinstance(combat.get("player"), dict) else {}
    actions = snapshot.get("actions") if isinstance(snapshot.get("actions"), list) else []
    if not any(isinstance(action, dict) and action.get("kind") == "end_turn" for action in actions):
        return None
    if any(relic.get("id") in CARRY_OVER_RELICS for relic in _rows(player.get("relics"))):
        return None
    if _skill_punished(_rows(combat.get("enemies"))):
        # Every Skill feeds an Enrage enemy permanent Strength; leave that trade to the model.
        return None
    incoming, _ = _shown_attack(_rows(combat.get("enemies")))
    block = _nonnegative(player.get("block"))
    energy = _nonnegative(combat.get("energy"))
    if block is None or not energy:
        return None
    unblocked = max(0, incoming - block)
    if unblocked <= 0:
        return None
    hand = {card.get("index"): card for card in _rows(combat.get("hand")) if type(card.get("index")) is int}
    best = None
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
        if not (match := PLAIN_BLOCK_TEXT.fullmatch(text)):
            continue
        gain = int(match.group(1) or match.group(2))
        option = {"choice": choice, "card_id": card.get("id"), "block": gain, "energy_cost": cost,
                  "unblocked_before": unblocked, "estimated_hp_saved": min(gain, unblocked)}
        if best is None or (option["estimated_hp_saved"], -cost) > (best["estimated_hp_saved"], -best["energy_cost"]):
            best = option
    return best
