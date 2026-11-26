using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using Godot;
using MegaCrit.Sts2.Core.Modding;
using MegaCrit.Sts2.Core.Multiplayer.Game;
using MegaCrit.Sts2.Core.Nodes;
using MegaCrit.Sts2.Core.Platform;
using MegaCrit.Sts2.Core.Rooms;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Saves;

namespace Sts2LiveBridge;

internal sealed record LiveAction(string Id, string Kind, object Detail, Func<bool> Execute);
internal sealed record LiveSnapshot(string Screen, object State, IReadOnlyList<LiveAction> Actions);

[ModInitializer(nameof(Initialize))]
public static class LiveMod
{
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
    private static readonly string Session = Guid.NewGuid().ToString("N");
    private static long _revision;
    private static long _acceptedAt;
    private static bool _overlayOpen;
    private static RunState? _lastRun;
    private static string? _runInstance;
    private static PipeBridge? _bridge;

    public static void Initialize()
    {
        if (_bridge != null || !OperatingSystem.IsWindows())
            return;
        if (Engine.GetMainLoop() is not SceneTree tree)
            throw new InvalidOperationException("STS2 Live Bridge requires the running scene tree.");

        _bridge = new PipeBridge(Handle, Json);
        tree.ProcessFrame += ProcessFrame;
        _bridge.Start();
        GD.Print("[Sts2LiveBridge] Local single-player bridge ready (protocol 1).");
    }

    private static void ProcessFrame()
    {
        RoomRetry.Advance();
        var overlayOpen = PlatformUtil.IsPlatformOverlayOpen();
        if (_overlayOpen != overlayOpen)
        {
            _overlayOpen = overlayOpen;
            _revision++;
        }
        _bridge?.ProcessRequest();
    }

    private static object Handle(BridgeRequest request)
    {
        var manager = RunManager.Instance;
        var run = manager.IsInProgress ? manager.DebugOnlyGetState() : null;
        if (!ReferenceEquals(run, _lastRun))
        {
            _lastRun = run;
            _runInstance = run is null ? null : Guid.NewGuid().ToString("N");
            _revision++;
        }

        var retryFailure = RoomRetry.Failure(run);
        if (RoomRetry.IsPending)
            return Unavailable(request, "waiting", "The native game is reloading the current room.", retryFailure);
        if (run == null)
            return Unavailable(request, "idle", "Open a single-player run.", retryFailure);
        if (manager.NetService?.Type != NetGameType.Singleplayer ||
            run.GameMode is not (GameMode.Standard or GameMode.Daily) || run.Players.Count != 1)
            return Unavailable(request, "unavailable", "Only standard and daily single-player runs are supported.", retryFailure);
        if (_overlayOpen || PlatformUtil.IsPlatformOverlayOpen())
            return Unavailable(request, "paused", "Close the Steam overlay to continue.", retryFailure);
        if (_acceptedAt != 0 && Stopwatch.GetElapsedTime(_acceptedAt) < TimeSpan.FromMilliseconds(250))
            return Unavailable(request, "waiting", "The previous action is settling.", retryFailure);

        IReadOnlyList<CombatBridge.PotionView>? combatPotions = null;
        var snapshot = RoomBridge.Read() ?? CombatBridge.Read(out combatPotions);
        if (snapshot == null)
            return Unavailable(request, "unsupported", "The current screen does not expose a supported action.", retryFailure);

        var player = run.Players[0];
        var potionHud = NRun.Instance?.GlobalUi?.TopBar?.PotionContainer;
        var potionHudVisible = potionHud is not null && GodotObject.IsInstanceValid(potionHud) && potionHud.IsVisibleInTree();
        var runContext = new
        {
            Profile = SaveManager.Instance.CurrentProfileId,
            Seed = run.Rng.StringSeed,
            StartTime = RoomRetry.LiveStartTime(),
            RunInstance = _runInstance,
            MapCoord = run.CurrentMapCoord is { } point ? new { Col = point.col, Row = point.row } : null,
            GameMode = run.GameMode.ToString().ToLowerInvariant(),
            Modifiers = run.Modifiers.Select(modifier => modifier.Id.Entry).ToArray(),
            Act = run.CurrentActIndex + 1,
            Floor = run.TotalFloor,
            CombatRetryCount = RoomRetry.CombatCount(run),
            EventRetryCount = RoomRetry.EventCount(run),
            RoomEventId = (run.CurrentRoom as EventRoom)?.CanonicalEvent.Id.Entry,
            Character = player.Character.Id.ToString(),
            Ascension = run.AscensionLevel,
            Hp = player.Creature.CurrentHp,
            MaxHp = player.Creature.MaxHp,
            PotionCapacity = potionHudVisible ? player.PotionSlots.Count : (int?)null,
            Potions = potionHudVisible ? combatPotions ?? CombatBridge.ReadPotions(player) : null,
            player.Gold,
            Deck = player.Deck.Cards.GroupBy(card => new { Id = card.Id.Entry, card.IsUpgraded })
                .Select(group => new { group.Key.Id, group.Key.IsUpgraded, Count = group.Count() }).ToArray(),
            Relics = player.Relics.Select(relic => relic.Id.Entry).ToArray(),
        };
        var actions = snapshot.Actions.Select(action => new { action.Id, action.Kind, action.Detail }).ToArray();
        var content = new { snapshot.Screen, snapshot.State, Run = runContext, Actions = actions, RetryFailure = retryFailure };
        var fingerprint = Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(content, Json)));
        var stateId = $"{Session}:{_revision}:{fingerprint}";

        if (request.Method == "get_state")
            return BridgeReply.Success(new
            {
                Protocol = 1, StateId = stateId, content.Screen, content.State, content.Run, content.Actions,
                content.RetryFailure,
            });
        if (!string.Equals(request.StateId, stateId, StringComparison.Ordinal))
            return BridgeReply.Failure("stale_state");

        var action = snapshot.Actions.SingleOrDefault(candidate => candidate.Id == request.ActionId);
        if (action == null)
            return BridgeReply.Failure("invalid_action");
        if (!request.TryBeginAction())
            return BridgeReply.Failure("request_expired");

        // Invalidate the state even if a game callback rejects the operation after a partial update.
        _revision++;
        if (!action.Execute())
            return BridgeReply.Failure("action_rejected");
        _acceptedAt = Stopwatch.GetTimestamp();
        return BridgeReply.Success(new { Accepted = true, ActionId = action.Id, action.Kind });
    }

    private static BridgeReply Unavailable(BridgeRequest request, string screen, string reason, string? retryFailure)
    {
        if (request.Method != "get_state")
            return BridgeReply.Failure(screen);
        return BridgeReply.Success(new
        {
            Protocol = 1, Screen = screen, State = new { Reason = reason }, Actions = Array.Empty<object>(),
            RetryFailure = retryFailure,
        });
    }
}
