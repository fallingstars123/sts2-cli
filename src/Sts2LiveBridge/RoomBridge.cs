using System.Reflection;
using Godot;
using MegaCrit.Sts2.Core.CardSelection;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.ControllerInput;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Merchant;
using MegaCrit.Sts2.Core.Map;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Nodes.Cards;
using MegaCrit.Sts2.Core.Nodes.Cards.Holders;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Events;
using MegaCrit.Sts2.Core.Nodes.Ftue;
using MegaCrit.Sts2.Core.Nodes.GodotExtensions;
using MegaCrit.Sts2.Core.Nodes.RestSite;
using MegaCrit.Sts2.Core.Nodes.Rewards;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens;
using MegaCrit.Sts2.Core.Nodes.Screens.CardSelection;
using MegaCrit.Sts2.Core.Nodes.Screens.GameOverScreen;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Screens.ScreenContext;
using MegaCrit.Sts2.Core.Nodes.Screens.Shops;
using MegaCrit.Sts2.Core.Nodes.Screens.TreasureRoomRelic;
using MegaCrit.Sts2.Core.Rewards;
using MegaCrit.Sts2.Core.Rooms;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Saves;

namespace Sts2LiveBridge;

internal static class RoomBridge
{
    private const BindingFlags GridSelectionFields = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;

    internal static LiveSnapshot? Read()
    {
        var run = RunManager.Instance.DebugOnlyGetState();
        if (run?.Players.Count != 1)
            return null;

        var screen = ActiveScreenContext.Instance.GetCurrentScreen();
        return screen switch
        {
            NMapScreen map when IsShown(map) => Map(map, run),
            NRewardsScreen rewards when IsShown(rewards) => Rewards(rewards),
            NCardRewardSelectionScreen cardReward when IsShown(cardReward) => CardRewardChoices(cardReward),
            NCardGridSelectionScreen cardGrid when IsShown(cardGrid) => CardGrid(cardGrid),
            NChooseACardSelectionScreen cardChoice when IsShown(cardChoice) => SingleCardChoice(cardChoice),
            NChooseABundleSelectionScreen bundleChoice when IsShown(bundleChoice) => BundleChoice(bundleChoice),
            NEventRoom eventRoom when IsShown(eventRoom) => EventRoom(eventRoom, run),
            NRestSiteRoom restSite when IsShown(restSite) => RestSite(restSite),
            NTreasureRoom treasure when IsShown(treasure) => Treasure(treasure),
            NMerchantRoom merchant when IsShown(merchant) => MerchantRoom(merchant),
            NMerchantInventory inventory when IsShown(inventory) => ShopInventory(inventory),
            NFtue tutorial when IsShown(tutorial) => Tutorial(tutorial),
            NCombatRoom combat when IsShown(combat) && !CombatManager.Instance.IsInProgress &&
                Usable(combat.ProceedButton) => ProceedRoom("post_combat", combat, combat.ProceedButton),
            NGameOverScreen settlement when IsShown(settlement) && run.IsGameOver => Settlement(run),
            _ => null,
        };
    }

    private static LiveSnapshot Settlement(RunState run)
    {
        var manager = RunManager.Instance;
        var history = manager.History;
        if (history is not null && (history.StartTime <= 0 || history.Seed != run.Rng.StringSeed ||
            history.Ascension != run.AscensionLevel || history.GameMode != run.GameMode ||
            history.Players.Count != 1 || history.Players[0].Character != run.Players[0].Character.Id ||
            history.WasAbandoned != manager.IsAbandoned || (history.Win && history.WasAbandoned)))
        {
            history = null;
        }

        string outcome = "defeat";
        if (manager.IsAbandoned)
            outcome = "abandoned";
        else if (history?.Win == true)
            outcome = "victory";
        else if (history is null && run.CurrentRoom?.IsVictoryRoom == true)
            outcome = "unverified";

        return new LiveSnapshot("settlement", new
        {
            outcome,
            act = run.CurrentActIndex + 1,
            floor = run.TotalFloor,
            start_time = history?.StartTime,
            build = history?.BuildId,
            act_points = history?.MapPointHistory.Select(points => points.Count).ToArray(),
            native_history = history is not null,
        }, []);
    }

    private static LiveSnapshot Map(NMapScreen map, RunState run)
    {
        var points = Descendants<NMapPoint>(map).Where(IsShown)
            .OrderBy(point => point.Point.coord.row).ThenBy(point => point.Point.coord.col).ToArray();
        var actions = new List<LiveAction>();
        foreach (var point in points.Where(point => CanTravel(map, point)))
        {
            var coord = point.Point.coord;
            actions.Add(Click(map, point, $"map.{coord.col}.{coord.row}", "select_map_node",
                new { col = coord.col, row = coord.row, type = point.Point.PointType.ToString() },
                () => CanTravel(map, point)));
        }

        return new LiveSnapshot("map", new
        {
            act = run.CurrentActIndex + 1,
            floor = run.TotalFloor,
            act_floor = run.ActFloor,
            current = run.CurrentMapCoord is { } current ? new { col = current.col, row = current.row } : null,
            nodes = points.Select(point => new
            {
                col = point.Point.coord.col,
                row = point.Point.coord.row,
                type = point.Point.PointType.ToString(),
                state = point.State.ToString(),
                children = point.Point.Children.OrderBy(child => child.coord.col)
                    .Select(child => new { col = child.coord.col, row = child.coord.row }).ToArray(),
            }).ToArray(),
        }, actions);
    }

    private static bool CanTravel(NMapScreen map, NMapPoint point) =>
        map.IsOpen && map.IsTravelEnabled && !map.IsTraveling && !map.IsDebugTravelEnabled &&
        map.Drawings.GetLocalDrawingMode() == DrawingMode.None && Usable(point) &&
        point.State == MapPointState.Travelable && map.IsNodeOnScreen(point) &&
        (point.Point.coord.row != 0 || SaveManager.Instance.SeenFtue("map_select_ftue"));

    private static LiveSnapshot Rewards(NRewardsScreen screen)
    {
        var rewards = Descendants<NRewardButton>(screen)
            .Where(button => IsShown(button) && button.Reward is { IsPopulated: true }).ToArray();
        var details = rewards.Select(button => DescribeReward(button.Reward!)).ToArray();
        var actions = new List<LiveAction>();
        for (int index = 0; index < rewards.Length; index++)
        {
            var button = rewards[index];
            if (Usable(button))
                actions.Add(Click(screen, button, $"reward.claim.{index}", "claim_reward", details[index]));
        }
        var proceed = screen.GetNodeOrNull<NProceedButton>("ProceedButton");
        if (proceed is not null && Usable(proceed))
            actions.Add(Click(screen, proceed, "reward.proceed", "proceed", new { may_skip = proceed.IsSkip }));
        return new LiveSnapshot("rewards", new { rewards = details }, actions);
    }

    private static object DescribeReward(Reward reward) => new
    {
        type = reward switch
        {
            CardReward => "cards", GoldReward => "gold", PotionReward => "potion", RelicReward => "relic",
            _ => reward.GetType().Name,
        },
        title = reward.Description.GetFormattedText(),
        gold = (reward as GoldReward)?.Amount,
        item = ((AbstractModel?)(reward as PotionReward)?.Potion ?? (reward as RelicReward)?.Relic)?.Id.Entry,
    };

    private static LiveSnapshot CardRewardChoices(NCardRewardSelectionScreen screen)
    {
        var holders = Descendants<NGridCardHolder>(screen)
            .Where(holder => IsShown(holder) && holder.CardModel != null)
            .OrderBy(holder => holder.GetInstanceId()).ToArray();
        var cards = holders.Select(holder => DescribeCard(holder.CardModel!)).ToArray();
        var actions = new List<LiveAction>();
        for (int index = 0; index < holders.Length; index++)
        {
            var holder = holders[index];
            if (CanSelectCard(holder))
                actions.Add(SelectCard(screen, holder, $"card_reward.pick.{index}", "pick_card_reward", cards[index]));
        }
        foreach (var (button, index) in Descendants<NCardRewardAlternativeButton>(screen).Select((b, i) => (b, i)))
        {
            if (Usable(button))
            {
                var label = button.GetNodeOrNull<Label>("Label")?.Text;
                actions.Add(Click(screen, button, $"card_reward.alternative.{index}", "card_reward_alternative",
                    new { title = label }));
            }
        }
        return new LiveSnapshot("card_reward", new { cards }, actions);
    }

    private static bool CanSelectCard(NCardHolder holder) => IsShown(holder) &&
        Usable(holder.Hitbox) && holder.Get(NCardHolder.PropertyName._isClickable).AsBool();

    private static LiveAction SelectCard(IScreenContext owner, NCardHolder holder, string id, string kind,
        object detail, Func<bool>? available = null)
    {
        var card = holder.CardModel;
        return new LiveAction(id, kind, detail, () =>
        {
            if (!IsCurrent(owner) || !CanSelectCard(holder) || holder.CardModel != card || available?.Invoke() == false)
                return false;
            return holder.EmitSignal(NCardHolder.SignalName.Pressed, holder) == Error.Ok;
        });
    }

    private static LiveSnapshot CardGrid(NCardGridSelectionScreen screen)
    {
        var grid = screen.GetNodeOrNull<NCardGrid>("%CardGrid");
        var screenType = screen.GetType();
        // The highlight node stays visible while its shader fades to zero. Read the same choice set as Confirm.
        var selectedCards = screenType.GetField("_selectedCards", GridSelectionFields)?.GetValue(screen)
            as IReadOnlySet<CardModel>;
        var prefs = screenType.GetField("_prefs", GridSelectionFields)?.GetValue(screen) as CardSelectorPrefs?;
        var actions = new List<LiveAction>();
        var cards = new List<object>();
        if (grid is not null && CanUseGrid(grid))
        {
            var holders = Descendants<NGridCardHolder>(grid).Where(holder => IsShown(holder) && holder.CardModel != null)
                .OrderBy(holder => holder.GetInstanceId()).ToArray();
            for (int index = 0; index < holders.Length; index++)
            {
                var holder = holders[index];
                var card = holder.CardModel!;
                var selected = selectedCards?.Contains(card);
                var details = new
                {
                    card = DescribeCard(card),
                    selected,
                };
                cards.Add(details);
                if (CanSelectCard(holder) && CanToggle())
                    actions.Add(SelectCard(screen, holder, $"card_selection.toggle.{index}", "toggle_card_choice",
                        details, CanToggle));

                bool CanToggle() => CanUseGrid(grid) && selectedCards?.Contains(card) == selected &&
                    (screen is not (NSimpleCardSelectScreen or NCombatPileCardSelectScreen) ||
                        selected != false || prefs is null || selectedCards!.Count < prefs.Value.MaxSelect);
            }
        }

        AddSelectionConfirmation(screen, screen, actions);
        var enchantment = screen.GetNodeOrNull<RichTextLabel>("%EnchantmentDescription");
        return new LiveSnapshot("card_selection", new
        {
            mode = screen.GetType().Name,
            instructions = screen.GetNodeOrNull<RichTextLabel>("%BottomLabel")?.Text,
            enchantment = enchantment is not null && IsShown(enchantment) ? enchantment.Text : null,
            selected_count = selectedCards?.Count,
            min_select = prefs?.MinSelect,
            max_select = prefs?.MaxSelect,
            manual_confirmation = prefs?.RequireManualConfirmation,
            cards,
            preview = VisiblePreview(screen),
        }, actions);
    }

    private static bool CanUseGrid(NCardGrid grid) => IsShown(grid) &&
        grid.FocusBehaviorRecursive != Control.FocusBehaviorRecursiveEnum.Disabled;

    private static LiveSnapshot SingleCardChoice(NChooseACardSelectionScreen screen)
    {
        var holders = Descendants<NGridCardHolder>(screen).Where(holder => IsShown(holder) && holder.CardModel != null)
            .OrderBy(holder => holder.GetInstanceId()).ToArray();
        var cards = holders.Select(holder => DescribeCard(holder.CardModel!)).ToArray();
        var actions = new List<LiveAction>();
        if (CanPickSingleCard(screen))
        {
            for (int index = 0; index < holders.Length; index++)
            {
                var holder = holders[index];
                if (CanSelectCard(holder))
                    actions.Add(SelectCard(screen, holder, $"card_selection.pick.{index}", "pick_card_choice",
                        cards[index], () => CanPickSingleCard(screen)));
            }
            var skip = screen.GetNodeOrNull<NChoiceSelectionSkipButton>("SkipButton");
            if (skip is not null && Usable(skip))
                actions.Add(Click(screen, skip, "card_selection.skip", "skip_card_choice", new { }));
        }
        return new LiveSnapshot("card_selection", new { mode = screen.GetType().Name, cards }, actions);
    }

    private static bool CanPickSingleCard(NChooseACardSelectionScreen screen)
    {
        ulong opened = screen.Get(NChooseACardSelectionScreen.PropertyName._openedTicks).As<ulong>();
        return opened > 0 && Time.GetTicksMsec() - opened > 350 &&
            !screen.Get(NChooseACardSelectionScreen.PropertyName._screenComplete).AsBool();
    }

    private static LiveSnapshot BundleChoice(NChooseABundleSelectionScreen screen)
    {
        var bundles = Descendants<NCardBundle>(screen).Where(IsShown).ToArray();
        var details = bundles.Select(bundle => new { cards = bundle.Bundle.Select(DescribeCard).ToArray() }).ToArray();
        var actions = new List<LiveAction>();
        for (int index = 0; index < bundles.Length; index++)
        {
            var bundle = bundles[index];
            if (Usable(bundle.Hitbox))
                actions.Add(Click(screen, bundle.Hitbox, $"bundle.choose.{index}", "choose_card_bundle", details[index]));
        }
        AddSelectionConfirmation(screen, screen, actions);
        return new LiveSnapshot("card_selection", new
        {
            mode = screen.GetType().Name,
            bundles = details,
            preview = VisiblePreview(screen),
        }, actions);
    }

    private static object[] VisiblePreview(Control screen) => Descendants<NPreviewCardHolder>(screen)
        .Where(holder => IsShown(holder) && holder.CardModel != null)
        .Select(holder => DescribeCard(holder.CardModel!)).ToArray();

    private static void AddSelectionConfirmation(IScreenContext owner, Control screen, List<LiveAction> actions)
    {
        foreach (var (button, index) in Descendants<NConfirmButton>(screen).Where(Usable).Select((b, i) => (b, i)))
            actions.Add(Click(owner, button, $"card_selection.confirm.{index}", "confirm_card_choice", new { }));
        foreach (var (button, index) in Descendants<NBackButton>(screen).Where(Usable).Select((b, i) => (b, i)))
            actions.Add(Click(owner, button, $"card_selection.back.{index}", "undo_or_cancel_card_choice", new { }));
    }

    private static object DescribeCard(CardModel card) => new
    {
        id = card.Id.Entry,
        title = card.Title,
        description = card.GetDescriptionForPile(PileType.None),
        cost = card.EnergyCost.GetResolved(),
        type = card.Type.ToString(),
        rarity = card.Rarity.ToString(),
        upgraded = card.IsUpgraded,
    };

    private static LiveSnapshot EventRoom(NEventRoom room, RunState run)
    {
        var buttons = Descendants<NEventOptionButton>(room).Where(IsShown).ToArray();
        var eventId = (run.CurrentRoom as EventRoom)?.CanonicalEvent.Id.Entry ?? buttons.FirstOrDefault()?.Event.Id.Entry;
        var actions = new List<LiveAction>();
        int? ancientDialogueLine = null;
        if (room.Layout is NAncientEventLayout ancient)
        {
            var line = ancient.Get(NAncientEventLayout.PropertyName._currentDialogueLine).AsInt32();
            ancientDialogueLine = line;
            var hitbox = ancient.GetNodeOrNull<NAncientDialogueHitbox>("%DialogueHitbox");
            var next = ancient.GetNodeOrNull<Control>("%FakeNextButtonContainer");
            if (IsShown(next))
            {
                buttons = [];
                if (hitbox is not null && Usable(hitbox))
                {
                    actions.Add(Click(room, hitbox, "event.advance_dialogue", "proceed", new { dialogue_line = line },
                        () => IsShown(next) && ReferenceEquals(room.Layout, ancient) &&
                            ancient.Get(NAncientEventLayout.PropertyName._currentDialogueLine).AsInt32() == line));
                }
            }
        }
        var options = buttons.Select(button => new
        {
            title = button.Option.Title.GetFormattedText(),
            description = button.Option.Description.GetFormattedText(),
            locked = button.Option.IsLocked,
            proceed = button.Option.IsProceed,
        }).ToArray();
        for (int index = 0; index < buttons.Length; index++)
        {
            var button = buttons[index];
            if (CanChooseEvent(button))
                actions.Add(Click(room, button, $"event.choose.{index}", "choose_event_option", options[index],
                    () => CanChooseEvent(button)));
        }
        var resolved = buttons is [var proceed] && proceed.Option.IsProceed && proceed.Event.IsFinished;
        if (resolved && actions.Count == 1 && eventId is not null &&
            RoomRetry.EventAction(run, room, eventId) is { } retry)
            actions.Add(retry);
        return new LiveSnapshot("event", new
        {
            event_id = eventId,
            resolved,
            dialogue_line = ancientDialogueLine,
            options,
        }, actions);
    }

    private static bool CanChooseEvent(NEventOptionButton button) => Usable(button) &&
        button.MouseFilter == Control.MouseFilterEnum.Stop && !button.Option.IsLocked;

    internal static bool HasFreshEventOption(NEventRoom room, string eventId) => IsShown(room) &&
        Descendants<NEventOptionButton>(room).Any(button => button.Event.Id.Entry == eventId &&
            !button.Event.IsFinished && !button.Option.IsProceed && CanChooseEvent(button));

    private static LiveSnapshot RestSite(NRestSiteRoom room)
    {
        var actions = new List<LiveAction>();
        foreach (var (option, index) in room.Options.Select((option, index) => (option, index)))
        {
            var button = room.GetButtonForOption(option);
            if (button is not null && option.IsEnabled && Usable(button))
            {
                actions.Add(Click(room, button, $"rest.choose.{index}", "choose_rest_option", new
                {
                    id = option.OptionId,
                    title = option.Title.GetFormattedText(),
                    description = option.Description.GetFormattedText(),
                }, () => option.IsEnabled));
            }
        }
        AddProceed(actions, room, room.ProceedButton);
        return new LiveSnapshot("rest", new { }, actions);
    }

    private static LiveSnapshot Treasure(NTreasureRoom room)
    {
        var actions = new List<LiveAction>();
        var chest = room.GetNodeOrNull<NClickableControl>("%Chest") ?? room.GetNodeOrNull<NClickableControl>("Chest");
        // The native chest button is disabled as soon as opening begins.
        bool opened = chest is not null && !chest.IsEnabled;
        if (chest is not null && Usable(chest))
            actions.Add(Click(room, chest, "treasure.open", "open_chest", new { }));

        foreach (var holder in Descendants<NTreasureRoomRelicHolder>(room))
        {
            if (Usable(holder) && holder.Relic?.Model is { } relic)
            {
                actions.Add(Click(room, holder, $"treasure.pick.{holder.Index}", "pick_treasure_relic", new
                {
                    id = relic.Id.Entry,
                    title = relic.Title.GetFormattedText(),
                }));
            }
        }
        AddProceed(actions, room, room.ProceedButton);
        return new LiveSnapshot("treasure", new { opened }, actions);
    }

    private static LiveSnapshot MerchantRoom(NMerchantRoom room)
    {
        var actions = new List<LiveAction>();
        if (Usable(room.MerchantButton))
            actions.Add(Click(room, room.MerchantButton, "shop.open", "open_shop", new { }));
        AddProceed(actions, room, room.ProceedButton);
        return new LiveSnapshot("shop", new { inventory_open = false }, actions);
    }

    private static LiveSnapshot ShopInventory(NMerchantInventory inventory)
    {
        var slots = inventory.GetAllSlots().Where(slot => IsShown(slot) && slot.Entry?.IsStocked == true).ToArray();
        var details = slots.Select(slot => DescribeShopItem(slot.Entry)).ToArray();
        var actions = new List<LiveAction>();
        var back = inventory.GetNodeOrNull<NBackButton>("%BackButton");
        if (back is not null && Usable(back))
        {
            for (int index = 0; index < slots.Length; index++)
            {
                var slot = slots[index];
                var entry = slot.Entry;
                if (CanBuy(slot))
                {
                    actions.Add(new LiveAction($"shop.buy.{index}", "buy_shop_item", details[index], () =>
                    {
                        if (!IsCurrent(inventory) || !Usable(back) || !CanBuy(slot) || slot.Entry != entry)
                            return false;
                        using var select = new InputEventAction { Action = MegaInput.select, Pressed = true };
                        slot._GuiInput(select);
                        return true;
                    }));
                }
            }
            actions.Add(Click(inventory, back, "shop.close", "close_shop", new { }));
        }
        return new LiveSnapshot("shop", new { inventory_open = true, items = details }, actions);
    }

    private static bool CanBuy(NMerchantSlot slot) => IsShown(slot) && Usable(slot.Hitbox) &&
        slot.Entry is { IsStocked: true, EnoughGold: true };

    private static object DescribeShopItem(MerchantEntry entry) => new
    {
        type = entry switch
        {
            MerchantCardEntry => "card", MerchantRelicEntry => "relic", MerchantPotionEntry => "potion",
            MerchantCardRemovalEntry => "card_removal", _ => entry.GetType().Name,
        },
        cost = entry.Cost,
        affordable = entry.EnoughGold,
        card = (entry as MerchantCardEntry)?.CreationResult?.Card is { } card ? DescribeCard(card) : null,
        item = ((AbstractModel?)(entry as MerchantRelicEntry)?.Model ?? (entry as MerchantPotionEntry)?.Model)?.Id.Entry,
        title = (entry as MerchantRelicEntry)?.Model?.Title.GetFormattedText() ??
            (entry as MerchantPotionEntry)?.Model?.Title.GetFormattedText(),
    };

    private static LiveSnapshot? Tutorial(NFtue screen)
    {
        if (screen is not (NMapSelectFtue or NCombatRewardFtue or NRelicRewardFtue or NObtainPotionFtue or
            NPowerCardFtue or NRestSiteFtue or NMerchantFtue or NCombatRulesFtue or NShuffleFtue or
            NCanPlayCardsFtue or NCannotPlayCardFtue))
            return null;

        var buttons = Descendants<NFtueConfirmButton>(screen).Where(Usable).Take(2).ToArray();
        var detail = new { tutorial = screen.GetType().Name };
        IReadOnlyList<LiveAction> actions = buttons.Length == 1
            ? [Click(screen, buttons[0], "tutorial.acknowledge", "acknowledge_tutorial", detail)] : [];
        return new LiveSnapshot("tutorial", detail, actions);
    }

    private static LiveSnapshot ProceedRoom(string screen, IScreenContext room, NProceedButton proceed)
    {
        var actions = new List<LiveAction>();
        AddProceed(actions, room, proceed);
        return new LiveSnapshot(screen, new { }, actions);
    }

    private static void AddProceed(List<LiveAction> actions, IScreenContext owner, NProceedButton proceed)
    {
        if (Usable(proceed))
            actions.Add(Click(owner, proceed, "room.proceed", "proceed", new { may_skip = proceed.IsSkip }));
    }

    private static bool IsCurrent(IScreenContext screen) => ActiveScreenContext.Instance.IsCurrent(screen);

    private static bool IsShown(Control? control) => control is not null && GodotObject.IsInstanceValid(control) &&
        control.IsInsideTree() && !control.IsQueuedForDeletion() && control.IsVisibleInTree();

    private static bool Usable(NClickableControl? button) => IsShown(button) && button!.IsEnabled &&
        !button.GetTree().Paused;

    private static LiveAction Click(IScreenContext owner, NClickableControl button, string id, string kind,
        object detail, Func<bool>? available = null) => new(id, kind, detail, () =>
        {
            if (!IsCurrent(owner) || !Usable(button) || available?.Invoke() == false)
                return false;
            // Dispatch the game's regular release handler only after checking the live UI context.
            button.ForceClick();
            return true;
        });

    private static IEnumerable<T> Descendants<T>(Node node) where T : Node
    {
        foreach (var child in node.GetChildren())
        {
            if (child is T match)
                yield return match;
            foreach (var descendant in Descendants<T>(child))
                yield return descendant;
        }
    }
}
