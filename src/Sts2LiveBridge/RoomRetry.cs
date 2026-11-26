using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using Godot;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Events;
using MegaCrit.Sts2.Core.Map;
using MegaCrit.Sts2.Core.Multiplayer.Game;
using MegaCrit.Sts2.Core.Nodes;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Debug;
using MegaCrit.Sts2.Core.Nodes.GodotExtensions;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens;
using MegaCrit.Sts2.Core.Nodes.Screens.MainMenu;
using MegaCrit.Sts2.Core.Nodes.Screens.PauseMenu;
using MegaCrit.Sts2.Core.Nodes.Screens.ScreenContext;
using MegaCrit.Sts2.Core.Platform;
using MegaCrit.Sts2.Core.Rooms;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Saves;

namespace Sts2LiveBridge;

internal static class RoomRetry
{
    private enum Phase { Pause, Menu, Room }
    private enum Kind { Combat, Event }
    // The run start timestamp identifies the live run but has no public getter.
    private static readonly FieldInfo? RunStartTime = typeof(RunManager).GetField("_startTime",
        BindingFlags.Instance | BindingFlags.NonPublic);

    private sealed record Request(RunState Original, int Profile, string Seed, int Act, int Floor,
        string Character, int Ascension, MapCoord Coord, Kind Kind, string RoomId, long StartTime,
        int PriorCount, long Started, Phase Phase, string CheckpointHash, bool Resume = true);
    private sealed record FailedAttempt(RunState? Run, AbstractRoom? Room, int? Floor, int? Profile, string Reason);

    private static Request? _pending;
    private static RunState? _completedRun;
    private static int _completedFloor;
    private static int _completedCount;
    private static Kind _completedKind;
    private static FailedAttempt? _failure;

    internal static bool IsPending => _pending != null;

    internal static int CombatCount(RunState run) => Count(run, Kind.Combat);
    internal static int EventCount(RunState run) => Count(run, Kind.Event);

    private static int Count(RunState run, Kind kind) =>
        ReferenceEquals(run, _completedRun) && run.TotalFloor == _completedFloor && _completedKind == kind
        ? _completedCount : 0;

    internal static string? Failure(RunState? run)
    {
        if (_failure is not { } failure)
            return null;
        if (!ReferenceEquals(run, failure.Run) || !ReferenceEquals(run?.CurrentRoom, failure.Room) ||
            run?.TotalFloor != failure.Floor || CurrentProfile() != failure.Profile)
        {
            _failure = null;
            return null;
        }
        return failure.Reason;
    }

    private static bool Available(RunState run) => _pending is null && run.GameMode == GameMode.Standard &&
        run.Players is [{ Creature.CurrentHp: > 0 }] && run.CurrentMapCoord is not null &&
        run.CurrentRoomCount == 1 && Failure(run) is null &&
        RunManager.Instance is { ShouldSave: true, IsChangingRooms: false, NetService.Type: NetGameType.Singleplayer } &&
        SaveManager.Instance is { IsProfileInitialized: true, HasRunSave: true } &&
        NRun.Instance?.GlobalUi?.TopBar?.Pause is { } pause && Usable(pause);

    internal static bool CombatAvailable(RunState run) => Available(run) &&
        run.CurrentRoom is CombatRoom { IsPreFinished: false, ParentEventId: null };

    internal static bool BeginCombat(RunState run, string encounter, bool resume = true)
    {
        if (!CombatAvailable(run) || ReadPrimaryCheckpoint() is not { } saved)
            return false;

        var request = Prepare(run, Kind.Combat, encounter, saved);
        return request is not null && Begin(request with { Resume = resume });
    }

    internal static LiveAction? EventAction(RunState run, NEventRoom screen, string eventId)
    {
        if (!Available(run) || EventCount(run) != 0 ||
            run.CurrentRoom is not EventRoom { IsPreFinished: false } room ||
            room.CanonicalEvent.LayoutType != EventLayoutType.Default ||
            room.CanonicalEvent.Id.Entry != eventId || !room.LocalMutableEvent.IsFinished ||
            ReadPrimaryCheckpoint() is not { } saved)
            return null;

        var request = Prepare(run, Kind.Event, eventId, saved);
        if (request is null)
            return null;

        return new LiveAction("retry_current_event", "retry_current_event", new
        {
            act = run.CurrentActIndex + 1,
            floor = run.TotalFloor,
            event_id = eventId,
            description = "Save and Quit, then Continue from the checkpoint at the start of this event.",
        }, () => Available(run) && EventCount(run) == 0 &&
            ReferenceEquals(RunManager.Instance.DebugOnlyGetState(), run) &&
            ReferenceEquals(run.CurrentRoom, room) && ActiveScreenContext.Instance.IsCurrent(screen) &&
            room.LocalMutableEvent.IsFinished && Begin(request));
    }

    private static Request? Prepare(RunState run, Kind kind, string roomId, (SerializableRun Save, string Hash) saved)
    {
        var checkpoint = saved.Save;
        if (run.CurrentMapCoord is not { } coord || checkpoint.StartTime <= 0 ||
            !MatchesLiveStart(checkpoint.StartTime))
            return null;

        var request = new Request(run, SaveManager.Instance.CurrentProfileId, run.Rng.StringSeed,
            run.CurrentActIndex, run.TotalFloor, run.Players[0].Character.Id.ToString(), run.AscensionLevel,
            coord, kind, roomId, checkpoint.StartTime, Count(run, kind), Stopwatch.GetTimestamp(), Phase.Pause,
            saved.Hash);
        return MatchesCheckpoint(checkpoint, request) ? request : null;
    }

    private static bool Begin(Request request)
    {
        if (NRun.Instance?.GlobalUi?.TopBar?.Pause is not { } pause || !Usable(pause))
            return false;

        _pending = request;
        try
        {
            pause.ForceClick();
            return true;
        }
        catch (Exception)
        {
            Fail("The native pause menu could not be opened for room retry.");
            return false;
        }
    }

    // Keep every continuation on the Godot thread and dispatch only visible native controls.
    internal static void Advance()
    {
        if (_pending is not { } request)
            return;
        try
        {
            if (PlatformUtil.IsPlatformOverlayOpen() || NDevConsole.IsConsoleVisible ||
                NModalContainer.Instance?.OpenModal is not null ||
                SaveManager.Instance is not { IsProfileInitialized: true } saves || saves.CurrentProfileId != request.Profile)
            {
                Fail("An overlay or profile change interrupted room retry.");
                return;
            }
            if (Stopwatch.GetElapsedTime(request.Started) > TimeSpan.FromSeconds(40))
            {
                Fail("The native game did not return to the original room in time.");
                return;
            }
            if (NGame.Instance is not { Transition.InTransition: false } game)
                return;

            switch (request.Phase)
            {
                case Phase.Pause:
                    if (ReferenceEquals(RunManager.Instance.DebugOnlyGetState(), request.Original) &&
                        ActiveScreenContext.Instance.GetCurrentScreen() is NCapstoneSubmenuStack
                            { Type: CapstoneSubmenuType.PauseMenu } capstone && capstone.Stack.Peek() is NPauseMenu pause &&
                        pause.GetNodeOrNull<NPauseMenuButton>("%ButtonContainer/SaveAndQuit") is { } quit && Usable(quit))
                    {
                        if (!CheckpointStillMatches(request))
                        {
                            Fail("The native checkpoint changed before Save and Quit.");
                            return;
                        }
                        _pending = request with { Phase = Phase.Menu };
                        quit.ForceClick();
                    }
                    break;
                case Phase.Menu:
                    if (game.MainMenu is not { } menu || !ActiveScreenContext.Instance.IsCurrent(menu))
                        break;
                    if (!CheckpointStillMatches(request))
                    {
                        Fail("The native checkpoint changed after Save and Quit.");
                        return;
                    }
                    if (!request.Resume)
                    {
                        _pending = null;
                        return;
                    }
                    if (menu.GetNodeOrNull<NMainMenuTextButton>("MainMenuTextButtons/ContinueButton") is { } resume && Usable(resume))
                    {
                        _pending = request with { Phase = Phase.Room };
                        resume.ForceClick();
                    }
                    break;
                case Phase.Room:
                    VerifyLoadedRoom(request);
                    break;
            }
        }
        catch (Exception)
        {
            Fail("The native game could not complete the room retry.");
        }
    }

    private static void VerifyLoadedRoom(Request request)
    {
        if (RunManager.Instance is not
                { IsInProgress: true, IsChangingRooms: false, NetService.Type: NetGameType.Singleplayer } manager ||
            manager.DebugOnlyGetState() is not { } loaded || ReferenceEquals(loaded, request.Original))
            return;

        if (!MatchesLiveStart(request.StartTime) || loaded.GameMode != GameMode.Standard ||
            loaded.CurrentActIndex != request.Act ||
            loaded.TotalFloor != request.Floor || loaded.CurrentMapCoord != request.Coord ||
            loaded.Rng.StringSeed != request.Seed || loaded.AscensionLevel != request.Ascension ||
            loaded.Players is not [{ Creature.CurrentHp: > 0 } player] ||
            player.Character.Id.ToString() != request.Character)
        {
            Fail("The loaded run did not match the original room checkpoint.");
            return;
        }

        var screen = ActiveScreenContext.Instance.GetCurrentScreen();
        if (request.Kind == Kind.Combat)
        {
            if (screen is not NCombatRoom { Mode: CombatRoomMode.ActiveCombat } ||
                CombatManager.Instance.DebugOnlyGetState() is not { } combat)
                return;
            if (combat.Encounter?.Id.Entry != request.RoomId || combat.RoundNumber != 1)
            {
                Fail("The loaded combat did not match the original checkpoint.");
                return;
            }
        }
        else
        {
            if (loaded.CurrentRoom is not EventRoom { IsPreFinished: false } room ||
                room.CanonicalEvent.Id.Entry != request.RoomId || room.LocalMutableEvent.IsFinished)
            {
                Fail("The loaded event did not match the original checkpoint.");
                return;
            }
            if (screen is not NEventRoom eventScreen || !RoomBridge.HasFreshEventOption(eventScreen, request.RoomId))
                return;
        }

        _completedRun = loaded;
        _completedFloor = request.Floor;
        _completedCount = request.PriorCount + 1;
        _completedKind = request.Kind;
        _pending = null;
    }

    private static bool CheckpointStillMatches(Request request) =>
        ReadPrimaryCheckpoint() is { } saved && saved.Hash == request.CheckpointHash &&
        MatchesCheckpoint(saved.Save, request);

    private static int? CurrentProfile() => SaveManager.Instance is { IsProfileInitialized: true } saves
        ? saves.CurrentProfileId : null;

    internal static long? LiveStartTime() =>
        RunStartTime?.GetValue(RunManager.Instance) is long startTime && startTime > 0 ? startTime : null;

    private static bool MatchesLiveStart(long startTime) => LiveStartTime() == startTime;

    // Inspect the primary save without invoking the game's recovery or repair machinery.
    private static (SerializableRun Save, string Hash)? ReadPrimaryCheckpoint()
    {
        var saves = SaveManager.Instance;
        if (saves.CurrentRunSaveTask is { IsCompleted: false })
            return null;

        var path = saves.GetProfileScopedPath("saves/current_run.save");
        using var file = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Read);
        if (file is null)
            return null;

        var length = checked((long)file.GetLength());
        var bytes = file.GetBuffer(length);
        if (bytes.LongLength != length)
            return null;
        var text = Encoding.UTF8.GetString(bytes).TrimStart('\uFEFF');
        var parsed = SaveManager.FromJson<SerializableRun>(text);
        return parsed.Success && parsed.SaveData is { } save &&
            save.SchemaVersion == saves.GetLatestSchemaVersion<SerializableRun>()
            ? (save, Convert.ToHexString(SHA256.HashData(bytes))) : null;
    }

    // The native room-entry save is written before the game appends this room to map history.
    private static bool MatchesCheckpoint(SerializableRun save, Request request) =>
        save.StartTime == request.StartTime && save.GameMode == GameMode.Standard && save.PreFinishedRoom is null &&
        save.CurrentActIndex == request.Act && save.FloorReached + 1 == request.Floor &&
        save.VisitedMapCoords.Count > 0 && save.VisitedMapCoords[^1] == request.Coord &&
        save.SerializableRng?.Seed == request.Seed && save.Ascension == request.Ascension &&
        save.Players is [var player] && player.CharacterId?.ToString() == request.Character;

    private static bool Usable(NClickableControl button) => GodotObject.IsInstanceValid(button) &&
        button.IsInsideTree() && button.IsVisibleInTree() && !button.IsQueuedForDeletion() && button.IsEnabled;

    private static void Fail(string reason)
    {
        _pending = null;
        var manager = RunManager.Instance;
        var run = manager.IsInProgress ? manager.DebugOnlyGetState() : null;
        _failure = new FailedAttempt(run, run?.CurrentRoom, run?.TotalFloor, CurrentProfile(), reason);
        GD.PushWarning($"[Sts2LiveBridge] {reason}");
    }
}
