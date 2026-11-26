"""Native-run archives keep the active branch across controller sessions."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import steam_mod_agent as agent
from run_stats import recent_average_floor, run_progress
from steam_mod_archive import SteamModArchive

IDENTITY = {"profile": 1, "start_time": 1700000000, "seed": "SAME-SEED",
            "character": "CHARACTER.FOOL", "ascension": 0}


def observed(second, *, kind="observed", screen="combat", floor=8, turn=1, hp=30, index=None,
             instance=None, cards=None, identity=IDENTITY):
    run = {**identity, "act": 1, "floor": floor, "hp": hp, "max_hp": 30,
           "run_instance": instance, "deck": [], "potions": []}
    state = {"turn": turn, "encounter": "SAMPLE_NORMAL", "hand": cards or []} if screen == "combat" else {
        "event_id": "SAMPLE", "options": [{"title": "Proceed"}],
    }
    return {"utc": f"2024-01-01T10:00:{second:02}+00:00", "type": kind, "screen": screen,
            "state": state, "run": run, "index": index}


def play(archive, second, title, **state):
    archive.append({"utc": f"2024-01-01T10:00:{second:02}+00:00", "type": "decision",
                    "index": second, "action": {"id": str(second), "kind": "play_card",
                    "detail": {"title": title}}})
    archive.append(observed(second + 1, index=second, **state))


def lines(folder):
    return [json.loads(line) for line in (folder / "gameplay.jsonl").read_text(encoding="utf-8").splitlines()]


def actions(folder):
    return [entry["data"]["args"]["title"] for entry in lines(folder) if entry["type"] == "action"]


def test_ordinary_resume_keeps_one_run_and_continues_steps(tmp_path):
    first = SteamModArchive(tmp_path)
    first.append(observed(0, kind="start"))
    play(first, 1, "Before disconnect", turn=2)
    second = SteamModArchive(tmp_path)
    second.append(observed(3, kind="start", turn=2))
    play(second, 4, "After reconnect", turn=3)
    assert first.folder == second.folder
    assert first.info["run_id"] == second.info["run_id"]
    assert second.rewinds == 0
    assert actions(second.folder) == ["Before disconnect", "After reconnect"]
    assert [row["step"] for row in lines(second.folder) if row["type"] == "action"] == [1, 2]

    new_run = SteamModArchive(tmp_path)
    new_run.append(observed(6, kind="start", identity={**IDENTITY, "start_time": 1700000100}))
    assert new_run.info["run_id"] != second.info["run_id"]


def test_reloaded_combat_replaces_only_the_abandoned_suffix(tmp_path):
    first = SteamModArchive(tmp_path)
    first.append(observed(0, kind="start", floor=7))
    play(first, 1, "Earlier room", floor=7, turn=2)
    first.append(observed(3, kind="state_changed", floor=8,
                          cards=[{"id": "CARD", "instance_id": "old"}]))
    play(first, 4, "Abandoned combat", floor=8, turn=2, hp=25)
    first.append(observed(6, kind="state_changed", screen="event", floor=9))
    play(first, 7, "Later room", screen="event", floor=9)

    resumed = SteamModArchive(tmp_path)
    resumed.append(observed(9, kind="start", floor=8,
                            cards=[{"id": "CARD", "instance_id": "new"}]))
    play(resumed, 10, "Replacement", floor=8, turn=2)
    assert resumed.rewinds == 1
    assert resumed.info["last_stage"] == {"act": 1, "floor": 8}
    assert actions(resumed.folder) == ["Earlier room", "Replacement"]
    assert {path.parent.name for path in resumed.folder.glob("*/scene.json")} == {
        "A01 F007 - Battle", "A01 F008 - Battle",
    }
    transcript = (resumed.folder / "transcript.txt").read_text(encoding="utf-8")
    assert "Earlier room" in transcript and "Replacement" in transcript and "Abandoned combat" not in transcript


def test_confirmed_same_room_event_retry_replaces_the_old_choices(tmp_path):
    archive = SteamModArchive(tmp_path)
    archive.append(observed(0, kind="start", screen="event"))
    play(archive, 1, "First choice", screen="event")
    archive.append(observed(3, kind="event_retry_completed", screen="event"))
    archive.append(observed(4, screen="event"))
    play(archive, 5, "Changed choice", screen="event")
    assert archive.rewinds == 1
    assert actions(archive.folder) == ["Changed choice"]


def test_full_run_reconnects_from_fresh_state_of_the_same_run(monkeypatch):
    first = observed(0, kind="start")
    resumed = observed(1, kind="start", turn=2)
    contexts = [MagicMock(), MagicMock()]
    monkeypatch.setattr(agent, "McpClient", Mock(side_effect=contexts))
    monkeypatch.setattr(agent, "read_ready", Mock(side_effect=[first, resumed]))
    monkeypatch.setattr(agent, "sleep", lambda _: None)
    loop = Mock(side_effect=[agent.BridgeDisconnected("pipe"), 0])
    monkeypatch.setattr(agent, "play", loop)
    options = SimpleNamespace(checkpoint="run")
    assert agent.play_connected(None, options) == 0
    assert [call.kwargs["initial_state"] for call in loop.call_args_list] == [first, resumed]


def test_full_run_reconnect_does_not_take_over_another_run_with_same_seed(monkeypatch):
    first = observed(0, kind="start")
    other = observed(1, kind="start", identity={**IDENTITY, "start_time": 1700000200})
    monkeypatch.setattr(agent, "McpClient", Mock(side_effect=[MagicMock(), MagicMock()]))
    monkeypatch.setattr(agent, "read_ready", Mock(side_effect=[first, other]))
    monkeypatch.setattr(agent, "sleep", lambda _: None)
    loop = Mock(side_effect=agent.BridgeDisconnected("pipe"))
    monkeypatch.setattr(agent, "play", loop)
    with pytest.raises(agent.SessionError, match="different run"):
        agent.play_connected(None, SimpleNamespace(checkpoint="run"))
    assert loop.call_count == 1


@pytest.mark.parametrize(("outcome", "expected_hp"), [("victory", 6), ("defeat", 0)])
def test_recent_hp_uses_the_last_playable_state_for_victory(tmp_path, outcome, expected_hp):
    archive = SteamModArchive(tmp_path)
    archive.append(observed(0, kind="start", hp=6))
    row = observed(1, kind="settlement", hp=0)
    row["state"] = {"native_history": True, "start_time": IDENTITY["start_time"], "outcome": outcome}
    archive.append(row)
    points, latest = run_progress(archive.folder)
    assert latest["hp"] == expected_hp
    assert points[-1][1] == 100 * expected_hp / 30


def test_average_floor_counts_the_last_ten_completed_ai_runs():
    runs = [{"status": "defeat", "provider": "Claude" if index % 2 else "DeepSeek",
             "ended": f"2024-01-01T10:00:{index:02}+00:00",
             "last_stage": {"act": 1, "floor": index}} for index in range(1, 13)]
    runs += [{**runs[-1], "provider": "manual"}, {**runs[-1], "status": "partial"}]
    assert recent_average_floor(runs) == (7.5, 10)
    assert recent_average_floor(runs[:2]) == (1.5, 2)
    assert recent_average_floor([]) == (None, 0)


def test_native_terminal_row_can_bind_an_older_unidentified_session(tmp_path):
    archive = SteamModArchive(tmp_path)
    old_bridge = {key: value for key, value in IDENTITY.items() if key != "start_time"}
    archive.append(observed(0, kind="start", identity=old_bridge))
    assert archive.folder is None
    row = observed(1, kind="settlement", identity=old_bridge)
    row["state"] = {"native_history": True, "start_time": IDENTITY["start_time"], "outcome": "victory"}
    archive.append(row)
    assert archive.info["native_outcome"] == "victory"
    assert len(lines(archive.folder)) == 2
