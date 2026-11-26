using System.Reflection;
using System.Runtime.CompilerServices;
using Godot;
using MegaCrit.Sts2.addons.mega_text;
using MegaCrit.Sts2.Core.CardSelection;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.ControllerInput;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Potions;
using MegaCrit.Sts2.Core.HoverTips;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Afflictions;
using MegaCrit.Sts2.Core.Models.Powers;
using MegaCrit.Sts2.Core.MonsterMoves.Intents;
using MegaCrit.Sts2.Core.Multiplayer.Game;
using MegaCrit.Sts2.Core.Nodes;
using MegaCrit.Sts2.Core.Nodes.Cards;
using MegaCrit.Sts2.Core.Nodes.Cards.Holders;
using MegaCrit.Sts2.Core.Nodes.Combat;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Debug;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens.ScreenContext;
using MegaCrit.Sts2.Core.Platform;
using MegaCrit.Sts2.Core.Rooms;
using MegaCrit.Sts2.Core.Runs;

namespace Sts2LiveBridge;

internal static class CombatBridge
{
    // The hand exposes its controls but keeps confirmation limits and the pending choice private.
    private const BindingFlags HandFields = BindingFlags.Instance | BindingFlags.NonPublic;
    private static readonly FieldInfo? SelectionPrefsField = typeof(NPlayerHand).GetField("_prefs", HandFields);
    private static readonly FieldInfo? SelectionTaskField = typeof(NPlayerHand).GetField("_selectionCompletionSource", HandFields);
    private static readonly ConditionalWeakTable<CombatState, CombatIdentities> InstanceIds = new();
    private static long _nextCombatId;

    // Both snapshot creation and action execution run on the Godot thread.
    internal static LiveSnapshot? Read(out IReadOnlyList<PotionView>? potionInventory)
    {
        potionInventory = null;
        if (NCombatRoom.Instance is not { Mode: CombatRoomMode.ActiveCombat } room ||
            !room.IsVisibleInTree() || !ActiveScreenContext.Instance.IsCurrent(room))
            return null;

        var run = RunManager.Instance;
        var manager = CombatManager.Instance;
        if (run.NetService?.Type != NetGameType.Singleplayer ||
            run.DebugOnlyGetState() is not { Players.Count: 1 } runState ||
            !manager.IsInProgress || manager.DebugOnlyGetState() is not { } combat)
            return null;

        var player = runState.Players[0];
        if (player.PlayerCombatState is not { } playerCombat)
            return null;

        var instanceIds = InstanceIds.GetValue(combat, _ => new CombatIdentities(++_nextCombatId));
        if (room.Ui.Hand.IsInCardSelection)
            return ReadHandChoice(room, combat, runState, playerCombat, instanceIds);

        var turn = playerCombat.TurnNumber;
        var targets = combat.Enemies.Where(enemy => IsVisibleEnemy(room, enemy)).ToArray();
        var targetInstanceIds = targets.Select(instanceIds.Enemy).ToArray();
        var canAct = CanAct(room, combat, player, turn);
        var actions = new List<LiveAction>();
        var legalCardIndices = new SortedSet<int>();
        var hand = playerCombat.Hand.Cards.Select((card, index) => new
        {
            index,
            id = card.Id.Entry,
            instance_id = instanceIds.Card(card),
            name = card.Title,
            description = card.GetDescriptionForPile(PileType.Hand),
            energy_cost = card.EnergyCost.CostsX ? playerCombat.Energy : card.EnergyCost.GetResolved(),
            energy_x = card.EnergyCost.CostsX,
            star_cost = card.HasStarCostX ? playerCombat.Stars : card.CurrentStarCost,
            star_x = card.HasStarCostX,
            type = card.Type.ToString(),
            upgrade = card.CurrentUpgradeLevel,
            target_type = card.TargetType.ToString(),
            keywords = card.Keywords.Select(keyword => keyword.ToString()).ToArray(),
            affliction = ReadAffliction(card),
        }).ToArray();

        if (canAct)
        {
            foreach (var slot in hand)
            {
                var card = playerCombat.Hand.Cards[slot.index];
                foreach (var (target, index) in Targets(card.TargetType, targets, player.Creature, false))
                {
                    if (!card.CanPlayTargeting(target) || (target is not null && !IsSelectableEnemy(room, target)))
                        continue;
                    legalCardIndices.Add(slot.index);
                    actions.Add(new LiveAction($"play:{slot.index}:{index}", "play_card", new
                    {
                        card_index = slot.index, card_id = slot.id, card = slot.name,
                        card_instance_id = slot.instance_id,
                        description = target is null ? slot.description : card.GetDescriptionForPile(PileType.Hand, target),
                        target_index = index, target = target?.Name,
                        target_instance_id = index is int enemyIndex ? targetInstanceIds[enemyIndex] : null,
                    }, () => TryPlay(room, combat, player, turn, card, target)));
                }
            }

            if (room.Ui.EndTurnButton is { IsEnabled: true } endTurn && endTurn.IsVisibleInTree())
            {
                actions.Add(new LiveAction("end_turn", "end_turn", new { turn }, () =>
                {
                    if (!CanAct(room, combat, player, turn) || !endTurn.IsEnabled || !endTurn.IsVisibleInTree())
                        return false;
                    endTurn.CallReleaseLogic();
                    return true;
                }));
            }
        }

        var potions = ReadPotions(player);
        potionInventory = potions;
        foreach (var item in potions)
        {
            var slot = item.Index;
            if (!canAct || player.GetPotionAtSlotIndex(slot) is not { } potion || !CanUsePotion(player, potion, slot))
                continue;

            foreach (var (target, targetIndex) in Targets(potion.TargetType, targets, player.Creature, true))
            {
                if (!potion.IsValidTarget(target) || (targetIndex is not null && !IsSelectableEnemy(room, target!)))
                    continue;
                actions.Add(new LiveAction($"potion:{slot}:{targetIndex}", "use_potion", new
                {
                    potion_index = slot, potion_id = item.Id, potion = item.Name, description = item.Description,
                    target_index = targetIndex, target = target?.Name,
                    target_instance_id = targetIndex is int enemyIndex ? targetInstanceIds[enemyIndex] : null,
                }, () =>
                {
                    if (!CanAct(room, combat, player, turn) || !CanUsePotion(player, potion, slot) ||
                        !potion.IsValidTarget(target) || (targetIndex is not null && !IsSelectableEnemy(room, target!)))
                        return false;
                    potion.EnqueueManualUse(target);
                    return true;
                }));
            }
        }

        if (canAct && combat.Encounter?.Id.Entry is { } encounter && RoomRetry.CombatAvailable(runState))
        {
            actions.Add(new LiveAction("retry_current_combat", "retry_current_combat", new
            {
                act = runState.CurrentActIndex + 1, floor = runState.TotalFloor, encounter, turn,
                description = "Save and Quit, then Continue from the native checkpoint at the start of this fight.",
            }, () => CanAct(room, combat, player, turn) && RoomRetry.BeginCombat(runState, encounter)));
            actions.Add(new LiveAction("save_and_quit_combat", "save_and_quit_combat", new
            {
                description = "Use Save and Quit and leave the game at the main menu.",
            }, () => CanAct(room, combat, player, turn) && RoomRetry.BeginCombat(runState, encounter, resume: false)));
        }

        var enemies = targets.Select((enemy, index) => new
        {
            index,
            id = enemy.ModelId.Entry,
            instance_id = targetInstanceIds[index],
            name = enemy.Name,
            hp = VisibleHp(enemy, enemy.CurrentHp),
            max_hp = VisibleHp(enemy, enemy.MaxHp),
            block = enemy.Block,
            powers = Powers(enemy),
            intents = ReadIntents(room, combat, enemy),
        }).ToArray();

        return new LiveSnapshot("combat", new
        {
            act = runState.CurrentActIndex + 1,
            floor = runState.TotalFloor,
            act_floor = runState.ActFloor,
            ascension = runState.AscensionLevel,
            seed = runState.Rng.StringSeed,
            encounter = combat.Encounter?.Id.Entry,
            round = combat.RoundNumber,
            turn,
            phase = playerCombat.Phase.ToString(),
            energy = playerCombat.Energy,
            max_energy = playerCombat.MaxEnergy,
            stars = playerCombat.Stars,
            draw_pile_count = playerCombat.DrawPile.Cards.Count,
            discard_pile_count = playerCombat.DiscardPile.Cards.Count,
            exhaust_pile_count = playerCombat.ExhaustPile.Cards.Count,
            draw_pile = ReadVisiblePile(room.Ui.DrawPile, playerCombat.DrawPile),
            discard_pile = ReadVisiblePile(room.Ui.DiscardPile, playerCombat.DiscardPile),
            hand,
            legal_card_indices = legalCardIndices.ToArray(),
            ringing = ReadRinging(player, combat),
            arrows_available = ReadArrows(player, targets),
            active_melodies = ReadMelodies(player),
            enemies,
            potions,
            player = new
            {
                character = player.Character.Id.Entry,
                hp = player.Creature.CurrentHp,
                max_hp = player.Creature.MaxHp,
                block = player.Creature.Block,
                gold = player.Gold,
                powers = Powers(player.Creature),
                relics = player.Relics.Select(relic => new
                {
                    id = relic.Id.Entry,
                    name = relic.Title.GetFormattedText(),
                    description = relic.DynamicDescription.GetFormattedText(),
                    counter = relic.ShowCounter ? relic.DisplayAmount : (int?)null,
                }).ToArray(),
            },
            orb_slots = playerCombat.OrbQueue.Capacity,
            orbs = playerCombat.OrbQueue.Orbs.Select(orb => new
            {
                id = orb.Id.Entry,
                name = orb.Title.GetFormattedText(),
                passive = orb.PassiveVal,
                evoke = orb.EvokeVal,
            }).ToArray(),
        }, actions);
    }

    private static object? ReadVisiblePile(NCombatCardPile button, CardPile pile)
    {
        if (!button.IsEnabled || !button.IsVisibleInTree())
            return null;

        // Match the native pile preview, then sort each group independently of the pile's sequence.
        return pile.Cards.GroupBy(card => new
        {
            id = card.Id.Entry,
            name = card.Title,
            type = card.Type.ToString(),
            upgrade = card.CurrentUpgradeLevel,
            description = card.GetDescriptionForPile(pile.Type),
            energy_cost = card.EnergyCost.CostsX ? (int?)null : card.EnergyCost.GetWithModifiers(CostModifiers.All),
            energy_x = card.EnergyCost.CostsX,
            star_cost = card.HasStarCostX ? (int?)null : card.GetStarCostWithModifiers(),
            star_x = card.HasStarCostX,
        }).OrderBy(group => group.Key.id, StringComparer.Ordinal)
          .ThenBy(group => group.Key.upgrade)
          .ThenBy(group => group.Key.name, StringComparer.Ordinal)
          .ThenBy(group => group.Key.type, StringComparer.Ordinal)
          .ThenBy(group => group.Key.description, StringComparer.Ordinal)
          .ThenBy(group => group.Key.energy_cost)
          .ThenBy(group => group.Key.energy_x)
          .ThenBy(group => group.Key.star_cost)
          .ThenBy(group => group.Key.star_x)
          .Select(group => new
          {
              group.Key.id,
              group.Key.name,
              group.Key.type,
              group.Key.upgrade,
              group.Key.description,
              group.Key.energy_cost,
              group.Key.energy_x,
              group.Key.star_cost,
              group.Key.star_x,
              count = group.Count(),
          }).ToArray();
    }

    private sealed class CombatIdentities(long combatId)
    {
        // Allocate tokens only when the corresponding entity is visible in the hand or combat room.
        private readonly ConditionalWeakTable<CardModel, string> _cards = new();
        private readonly ConditionalWeakTable<Creature, string> _enemies = new();
        private long _nextCard;
        private long _nextEnemy;

        internal string Card(CardModel card) => _cards.GetValue(card, _ => $"{combatId}:card:{++_nextCard}");
        internal string Enemy(Creature enemy) => _enemies.GetValue(enemy, _ => $"{combatId}:enemy:{++_nextEnemy}");
    }

    internal static PotionView[] ReadPotions(Player player) => player.PotionSlots
        .Select((potion, index) => potion is null ? null : new PotionView(index, potion.Id.Entry,
            potion.Title.GetFormattedText(), potion.DynamicDescription.GetFormattedText(), potion.Usage.ToString()))
        .OfType<PotionView>().ToArray();

    internal sealed record PotionView(int Index, string Id, string Name, string Description, string Usage);

    private static LiveSnapshot ReadHandChoice(NCombatRoom room, CombatState combat, RunState run,
        PlayerCombatState playerCombat, CombatIdentities instanceIds)
    {
        var hand = room.Ui.Hand;
        var mode = hand.CurrentMode;
        var turn = playerCombat.TurnNumber;
        var buttons = new List<LiveAction>();
        var cards = new List<object>();
        var header = hand.GetNodeOrNull<MegaRichTextLabel>("%SelectionHeader");
        var confirm = hand.GetNodeOrNull<NConfirmButton>("%SelectModeConfirmButton");
        var prefsValue = SelectionPrefsField?.GetValue(hand);
        var prefs = prefsValue is CardSelectorPrefs value ? value : (CardSelectorPrefs?)null;
        var minSelect = prefs?.MinSelect ?? 0;
        var maxSelect = prefs?.MaxSelect ?? 0;
        var selectionTask = PendingHandChoice(hand);

        // Selected cards move out of the regular holders, while remaining in the real hand pile.
        // Upgrade selection has a clickable original card in the native before/after preview.
        var selectedContainer = mode == NPlayerHand.Mode.SimpleSelect
            ? hand.GetNodeOrNull<NSelectedHandCardContainer>("%SelectedHandCardContainer") : null;
        var preview = mode == NPlayerHand.Mode.UpgradeSelect
            ? hand.GetNodeOrNull<NUpgradePreview>("%UpgradePreview") : null;
        var before = preview?.GetNodeOrNull<Control>("%Before");
        var selectedHolders = VisibleSelectedHolders().ToHashSet();

        var canChoose = maxSelect > 0 && CanChoose();
        var visibleHolders = hand.ActiveHolders.Where(IsVisibleChoice);
        foreach (var holder in visibleHolders.Cast<NCardHolder>().Concat(selectedHolders))
        {
            if (holder.CardModel is not { } card)
                continue;
            var position = IndexOfHandCard(playerCombat.Hand.Cards, card);
            if (position < 0)
                continue;

            var selected = selectedHolders.Contains(holder);
            var detail = new
            {
                index = position,
                id = card.Id.Entry,
                instance_id = instanceIds.Card(card),
                name = card.Title,
                description = card.GetDescriptionForPile(PileType.Hand),
                type = card.Type.ToString(),
                upgrade = card.CurrentUpgradeLevel,
                affliction = ReadAffliction(card),
                selected,
            };
            cards.Add(detail);

            if (!canChoose || (!selected && selectedHolders.Count >= maxSelect))
                continue;

            var operation = selected ? "deselect" : "select";
            buttons.Add(new LiveAction($"hand_card.{operation}.{position}", "toggle_card_choice", detail, () =>
            {
                if (!CanChoose() || !IsVisibleChoice(holder) || !ReferenceEquals(holder.CardModel, card) ||
                    IndexOfHandCard(playerCombat.Hand.Cards, card) != position ||
                    !selectedHolders.SetEquals(VisibleSelectedHolders()))
                    return false;

                using var input = new InputEventAction { Action = MegaInput.select, Pressed = true };
                holder._GuiInput(input);
                return true;
            }));
        }

        if (canChoose && confirm is { IsEnabled: true } && confirm.IsVisibleInTree() &&
            selectedHolders.Count >= minSelect && selectedHolders.Count <= maxSelect)
        {
            buttons.Add(new LiveAction("hand_card.confirm", "confirm_card_choice", new { count = selectedHolders.Count }, () =>
            {
                if (!CanChoose() || !confirm.IsEnabled || !confirm.IsVisibleInTree() ||
                    !selectedHolders.SetEquals(VisibleSelectedHolders()))
                    return false;
                confirm.ForceClick();
                return true;
            }));
        }

        var upgrade = preview?.GetNodeOrNull<Control>("%After")?.GetChildren().OfType<NPreviewCardHolder>()
            .FirstOrDefault(IsVisibleChoice)?.CardModel;
        return new LiveSnapshot("card_selection", new
        {
            location = "combat_hand",
            mode = mode.ToString(),
            prompt = header is not null && header.IsVisibleInTree() ? header.Text : null,
            min_select = prefs?.MinSelect,
            max_select = prefs?.MaxSelect,
            selected_count = selectedHolders.Count,
            cards,
            upgrade_preview = upgrade is null ? null : new { name = upgrade.Title, description = upgrade.GetDescriptionForUpgradePreview() },
            floor = run.TotalFloor,
            act = run.CurrentActIndex + 1,
            seed = run.Rng.StringSeed,
            round = combat.RoundNumber,
            turn,
        }, buttons);

        bool CanChoose() => HasControl(room, combat) && ReferenceEquals(room.Ui.Hand, hand) &&
            hand.IsInCardSelection && hand.CurrentMode == mode && !hand.PeekButton.IsPeeking &&
            playerCombat.TurnNumber == turn && selectionTask is { IsCompleted: false } &&
            ReferenceEquals(PendingHandChoice(hand), selectionTask);

        IEnumerable<NCardHolder> VisibleSelectedHolders()
        {
            if (selectedContainer is not null)
                return selectedContainer.Holders.Where(IsVisibleChoice);
            if (before is not null)
                return before.GetChildren().OfType<NPreviewCardHolder>().Where(IsVisibleChoice);
            return [];
        }
    }

    private static Task? PendingHandChoice(NPlayerHand hand) =>
        (SelectionTaskField?.GetValue(hand) as TaskCompletionSource<IEnumerable<CardModel>>)?.Task;

    private static bool IsVisibleChoice(NCardHolder holder) => GodotObject.IsInstanceValid(holder) &&
        !holder.IsQueuedForDeletion() && holder.IsVisibleInTree() && holder.CardNode is { } card && card.IsVisibleInTree();

    private static int IndexOfHandCard(IReadOnlyList<CardModel> cards, CardModel card)
    {
        for (var index = 0; index < cards.Count; index++)
            if (ReferenceEquals(cards[index], card))
                return index;
        return -1;
    }

    private static bool HasControl(NCombatRoom room, CombatState combat)
    {
        var run = RunManager.Instance;
        var manager = CombatManager.Instance;
        return NGame.Instance is { Transition.InTransition: false } &&
            !NDevConsole.IsConsoleVisible && NModalContainer.Instance?.OpenModal is null &&
            run.NetService?.Type == NetGameType.Singleplayer && !run.IsPaused &&
            ReferenceEquals(NCombatRoom.Instance, room) && ActiveScreenContext.Instance.IsCurrent(room) &&
            !manager.IsOverOrEnding && !manager.IsPaused && ReferenceEquals(manager.DebugOnlyGetState(), combat) &&
            NTargetManager.Instance?.IsInSelection != true;
    }

    private static bool CanAct(NCombatRoom room, CombatState combat, Player player, int turn)
    {
        var run = RunManager.Instance;
        var manager = CombatManager.Instance;
        return HasControl(room, combat) && !manager.PlayerActionsDisabled && combat.CurrentSide == CombatSide.Player &&
            player.Creature.IsAlive && player.PlayerCombatState is { Phase: PlayerTurnPhase.Play } playerCombat &&
            playerCombat.TurnNumber == turn && !manager.IsPlayerReadyToEndTurn(player) &&
            !manager.IsExecutingCardOrPotionEffect(player) && !run.ActionExecutor.IsRunning && run.ActionQueueSet.IsEmpty &&
            room.Ui.Hand is { CurrentMode: NPlayerHand.Mode.Play, InCardPlay: false, PeekButton.IsPeeking: false };
    }

    private static bool TryPlay(NCombatRoom room, CombatState combat, Player player, int turn,
        CardModel card, Creature? target)
    {
        if (!CanAct(room, combat, player, turn) || player.PlayerCombatState?.Hand.Cards.Contains(card) != true ||
            (target is not null && !IsSelectableEnemy(room, target)) || !card.TryManualPlay(target))
            return false;

        if (card.TargetType is TargetType.AnyEnemy or TargetType.AllEnemies or TargetType.AllAllies)
            room.LastTargetedCreature = target;
        return true;
    }

    private static bool CanUsePotion(Player player, PotionModel potion, int slot) =>
        player.CanUseOrRemovePotions && ReferenceEquals(player.GetPotionAtSlotIndex(slot), potion) &&
        !potion.IsQueued && !potion.HasBeenRemovedFromState &&
        potion.Usage is PotionUsage.CombatOnly or PotionUsage.AnyTime;

    private static bool IsVisibleEnemy(NCombatRoom room, Creature enemy) =>
        enemy.IsAlive && room.GetCreatureNode(enemy) is { } node && node.IsVisibleInTree();

    private static bool IsSelectableEnemy(NCombatRoom room, Creature? enemy) =>
        enemy is { IsAlive: true } && room.GetCreatureNode(enemy) is { IsInteractable: true } node &&
        node.IsVisibleInTree();

    private static IEnumerable<(Creature? Creature, int? Index)> Targets(TargetType targetType,
        IReadOnlyList<Creature> enemies, Creature player, bool potion)
    {
        if (targetType == TargetType.AnyEnemy)
        {
            for (var index = 0; index < enemies.Count; index++)
                yield return (enemies[index], index);
        }
        else if (targetType != TargetType.AnyAlly)
        {
            var target = potion && targetType is TargetType.AnyPlayer or TargetType.Self ? player : null;
            yield return (target, null);
        }
    }

    private static int? VisibleHp(Creature enemy, int hp) =>
        enemy.HpDisplay == HpDisplay.InfiniteWithoutNumbers ? null : hp;

    private static object[] Powers(Creature creature) => creature.Powers.Where(power => power.IsVisible)
        .Select(power =>
        {
            // The hover tip binds Amount, OwnerName and DynamicVars before formatting the localization string.
            var tip = power.HoverTips.OfType<HoverTip>().FirstOrDefault();
            return (object)new
            {
                id = power.Id.Entry,
                name = tip.Title ?? power.Title.GetFormattedText(),
                amount = power.Amount,
                display_amount = power.DisplayAmount,
                description = ReadPowerDescription(power, tip),
                mechanic = ReadPowerMechanic(power, creature),
            };
        }).ToArray();

    private static string ReadPowerDescription(PowerModel power, HoverTip tip)
    {
        var text = tip.Description ?? power.GetDumbHoverTip(power.Amount).Description;
        var player = power.Applier?.Player ?? power.Target?.Player;
        if (player is null || RunManager.Instance.NetService is not { } network)
            return text;

        var format = (power.HasSmartDescription ? power.SmartDescription : power.Description).GetRawText();
        if (!format.Contains("{ApplierName", StringComparison.Ordinal) &&
            !format.Contains("{TargetName", StringComparison.Ordinal))
            return text;

        // Keep the native tooltip wording without including the player's Steam display name.
        var accountName = PlatformUtil.GetPlayerName(network.Platform, player.NetId);
        return string.IsNullOrEmpty(accountName) ? text :
            text.Replace(accountName, player.Character.Title.GetFormattedText(), StringComparison.Ordinal);
    }

    private static object? ReadPowerMechanic(PowerModel power, Creature owner) => power switch
    {
        SlipperyPower => new { hp_loss_cap_per_trigger = 1, triggers_remaining = power.Amount },
        PlowPower => new
        {
            stun_at_hp_or_lower = power.Amount,
            hp_until_stun_threshold = owner.HpDisplay == HpDisplay.InfiniteWithoutNumbers
                ? (int?)null : Math.Max(0, owner.CurrentHp - power.Amount),
            loses_all_strength = true,
        },
        _ => null,
    };

    private static object? ReadAffliction(CardModel card)
    {
        if (card.Affliction is not { } affliction)
            return null;
        var tip = affliction.HoverTip;
        return new { id = affliction.Id.Entry, name = tip.Title, affliction.Amount, description = tip.Description };
    }

    // The Fool's Shoot cards need an available Arrow; an Arrow impaled in an enemy returns only
    // after enough hits (IMPALED_POWER.display_amount). Null when no Arrows are in play.
    private static int? ReadArrows(Player player, IEnumerable<Creature> enemies)
    {
        var available = ArrowCmd.GetAvailableArrowCount(player);
        return available > 0 || ArrowCmd.PlayerHasAnyArrows(player)
            || enemies.Any(enemy => ArrowCmd.CreatureIsImpaledByPlayersArrow(enemy, player))
            ? available : null;
    }

    private static string[]? ReadMelodies(Player player)
    {
        if (player.Character.Id.Entry != "FOOL")
            return null;

        var melodies = new List<string>(3);
        if (MelodyCmd.PlayedKiThisTurn(player)) melodies.Add("Ki");
        if (MelodyCmd.PlayedChoThisTurn(player)) melodies.Add("Cho");
        if (MelodyCmd.PlayedWahThisTurn(player)) melodies.Add("Wah");
        return melodies.ToArray();
    }

    private static object? ReadRinging(Player player, CombatState combat)
    {
        if (!player.Creature.Powers.OfType<RingingPower>().Any(power => power.IsVisible))
            return null;

        // In the game, an afflicted card can be the first play. A prior unafflicted card also uses that opportunity.
        var hasPlayed = CombatManager.Instance.History.CardPlaysStarted.Any(entry =>
            entry.HappenedThisTurn(combat) && ReferenceEquals(entry.CardPlay.Player, player));
        return new
        {
            max_ringed_cards = 1,
            ringed_plays_remaining = hasPlayed ? 0 : 1,
            affected_card_indices = player.PlayerCombatState?.Hand.Cards.Select((card, index) => (card, index))
                .Where(entry => entry.card.Affliction is Ringing).Select(entry => entry.index).ToArray(),
        };
    }

    private static IntentView[] ReadIntents(NCombatRoom room, CombatState combat, Creature enemy)
    {
        if (NCombatUi.IsDebugHidingIntent || room.GetCreatureNode(enemy)?.IntentContainer.IsVisibleInTree() != true ||
            enemy.Monster?.NextMove is not { } nextMove)
            return [];

        return nextMove.Intents.Select(intent => intent is AttackIntent attack
            ? new IntentView(intent.IntentType.ToString(), attack.GetSingleDamage(combat.PlayerCreatures, enemy),
                attack.Repeats, attack.GetTotalDamage(combat.PlayerCreatures, enemy))
            : new IntentView(intent.IntentType.ToString(), null, null, null)).ToArray();
    }

    private sealed record IntentView(string type, int? damage, int? hits, int? total_damage);
}
