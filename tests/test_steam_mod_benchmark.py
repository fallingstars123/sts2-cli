"""The checkpoint benchmark filters by when each combat attempt was played, not when the run began."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

import steam_mod_benchmark as bench  # noqa: E402


def combat_state(hp):
    return {"decision": "combat_play", "context": {"act": 2, "floor": 33}, "encounter": "THE_INSATIABLE_BOSS",
            "turn": 1, "energy": 3, "hand": [], "enemies": [],
            "player": {"hp": hp, "block": 0, "potions": [], "character_id": "CHARACTER.IRONCLAD"}}


def write_run(root, name, started, room_times, status="defeat"):
    run = root / name
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"started": started, "status": status}), encoding="utf-8")
    for position, when in enumerate(room_times):
        room = run / f"A02 F{33 + position:03d} - Boss"
        room.mkdir()
        rows = [{"type": "state", "ts": when, "data": combat_state(90)},
                {"type": "action", "ts": when, "data": {"action": "end_turn"}}]
        (room / "states.jsonl").write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_fresh_retry_of_an_old_save_is_kept_by_since(tmp_path):
    # The run began on 22 Nov (local time, -05:00); this attempt was played on 24 Nov (UTC).
    write_run(tmp_path, "retry", "2026-11-22T17:18:41-05:00", ["2026-11-24T15:00:00+00:00"])
    since = bench._cli_time("2026-11-23T00:00:00+00:00")
    kept = bench.collect(tmp_path, since=since)
    assert len(kept) == 1
    assert kept[0]["attempt_started"] == "2026-11-24T15:00:00+00:00"
    assert kept[0]["run_started"] == "2026-11-22T17:18:41-05:00"


def test_old_attempts_are_dropped_even_in_a_new_run_folder(tmp_path):
    write_run(tmp_path, "old", "2026-11-25T09:00:00-05:00", ["2026-11-22T21:00:00+00:00"])
    assert bench.collect(tmp_path, since=bench._cli_time("2026-11-23T00:00:00+00:00")) == []


def test_until_splits_attempts_inside_one_run(tmp_path):
    write_run(tmp_path, "mixed", "2026-11-22T17:00:00-05:00",
              ["2026-11-22T23:00:00+00:00", "2026-11-24T15:00:00+00:00"])
    cutoff = bench._cli_time("2026-11-23T00:00:00+00:00")
    assert [a["room"] for a in bench.collect(tmp_path, until=cutoff)] == ["A02 F033 - Boss"]
    assert [a["room"] for a in bench.collect(tmp_path, since=cutoff)] == ["A02 F034 - Boss"]


def test_a_retry_inside_one_room_is_two_attempts(tmp_path):
    run = tmp_path / "retried"
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"started": "2026-11-22T16:36:01-05:00", "status": "defeat"}))
    room = run / "A01 F017 - Boss"
    room.mkdir()
    rows = []
    for when, turns in (("2026-11-22T22:00:00+00:00", (1, 2, 3)), ("2026-11-22T22:30:00+00:00", (1, 2))):
        for turn in turns:
            state = combat_state(90)
            state["turn"] = turn
            rows += [{"type": "state", "ts": when, "data": state},
                     {"type": "action", "ts": when, "data": {"action": "end_turn"}}]
    (room / "states.jsonl").write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    attempts = bench.collect(tmp_path)
    assert [(a["attempt_in_room"], a["result"], a["turns"]) for a in attempts] == [("1/2", "retried", 3), ("2/2", "lost", 2)]
    # The time filter applies to each attempt separately.
    later = bench.collect(tmp_path, since=bench._cli_time("2026-11-22T22:15:00+00:00"))
    assert [a["attempt_in_room"] for a in later] == ["2/2"]


def test_time_zones_are_compared_in_utc():
    assert bench._when("2026-11-22T20:00:00-05:00") == bench._when("2026-11-23T01:00:00+00:00")
