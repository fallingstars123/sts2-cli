"""Observed outcomes and progress estimates from the launcher's run archive."""

from collections import Counter
from datetime import datetime
import json
from pathlib import Path


FINISHED = {"victory", "defeat"}
AI_PROVIDERS = ("DeepSeek", "Claude")
POTION_SLOT_RELICS = {"ALCHEMICAL_COFFER": 4, "PHIAL_HOLSTER": 1, "POTION_BELT": 2}


def json_dict(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def json_lines(paths):
    for path in paths:
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    try:
                        value = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(value, dict):
                        yield value
        except OSError:
            continue


def stage(data):
    if isinstance(data, dict):
        act, floor = data.get("act"), data.get("floor")
        if type(act) is int and type(floor) is int and act > 0 and floor >= 0:
            return act, floor
    return None


def game_records(folder):
    files = sorted(p for p in folder.glob("*.jsonl") if not p.name.endswith(".plan.jsonl"))
    return json_lines(files)


def fill_legacy_progress(folder, info):
    if stage(info.get("last_stage")) and type(info.get("ascension")) is int:
        return
    furthest = stage(info.get("last_stage"))
    for record in game_records(folder):
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        if data.get("cmd") == "start_run" and type(data.get("ascension")) is int:
            info["ascension"] = data["ascension"]
        position = stage(data.get("context"))
        if position and (not furthest or position > furthest):
            furthest = position
    if furthest:
        info["last_stage"] = dict(zip(("act", "floor"), furthest))


def completed_runs(root):
    result = []
    for path in sorted(Path(root).glob("*/run.json")):
        info = json_dict(path)
        if info.get("status") in ("victory", "defeat"):
            fill_legacy_progress(path.parent, info)
            result.append(info)
    return result


def win_counts(runs):
    statuses = [run.get("status") for run in runs if run.get("status") in ("victory", "defeat")]
    return statuses.count("victory"), len(statuses)


def timestamp(value):
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).timestamp()
        except (ValueError, OSError, OverflowError):
            pass
    return None


def recent_average_floor(runs, limit=10):
    """Average the reached floor of the latest completed AI runs with recorded progress."""
    eligible = []
    for run in runs:
        if run.get("status") not in FINISHED or run.get("provider") not in AI_PROVIDERS:
            continue
        position = stage(run.get("last_stage"))
        finished = next((value for key in ("ended", "last_updated", "started")
                         if (value := timestamp(run.get(key))) is not None), None)
        if position is not None and finished is not None:
            eligible.append((finished, position[1]))
    recent = sorted(eligible, reverse=True)[:limit]
    count = len(recent)
    return (sum(floor for _, floor in recent) / count if count else None), count


def similar_runs(runs, target):
    keys = ("provider", "model", "character", "ascension")
    start = timestamp(target.get("started"))
    if start is None or type(target.get("ascension")) is not int:
        return []
    return [run for run in runs
            if all(run.get(key) == target.get(key) for key in keys)
            and (finished := timestamp(run.get("ended"))) is not None and finished < start]


def estimated_wins(runs, position):
    if not position:
        return 0, 0
    return win_counts(run for run in runs if (reached := stage(run.get("last_stage"))) and reached >= position)


def run_timeline(folder):
    return run_progress(folder)[0]


def run_progress(folder):
    """Align health and progress snapshots to issued gameplay actions."""
    info = json_dict(folder / "run.json")
    steam_victory = info.get("source") == "steam_mod" and info.get("native_outcome") == "victory"
    points = {}
    latest = {}
    previous_relics = Counter()
    potion_slots_added = 0
    known_potion_capacity = None
    additions_at_capture = 0
    step = 0
    for record in game_records(folder):
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        if record.get("type") == "action" and data.get("cmd") == "action":
            step += 1
        if record.get("type") != "state" or not data.get("decision"):
            continue
        player = data.get("player")
        position = stage(data.get("context"))
        if not isinstance(player, dict) or not position:
            continue
        if steam_victory and data["decision"] == "settlement" and player.get("hp") == 0:
            # The victory screen clears the live creature HP after the final event.
            player = {key: value for key, value in player.items() if key not in {"hp", "max_hp"}}
        latest = {**latest, **player, "act": position[0], "floor": position[1]}
        relics = player.get("relics")
        if isinstance(relics, list):
            owned = Counter(relic["id"].rsplit(".", 1)[-1].upper() for relic in relics
                            if isinstance(relic, dict) and isinstance(relic.get("id"), str))
            # These relics grant capacity on pickup. Losing one does not remove the slots.
            potion_slots_added += sum(added * (owned[key] - previous_relics[key])
                                      for key, added in POTION_SLOT_RELICS.items()
                                      if owned[key] > previous_relics[key])
            previous_relics = owned
        capacity = player.get("potion_capacity")
        if type(capacity) is int and capacity >= 0:
            known_potion_capacity = capacity
            additions_at_capture = potion_slots_added
        for field in ("energy", "max_energy"):
            value = data.get(field)
            if data.get("decision") == "combat_play" and type(value) is int:
                latest[field] = value
            else:
                latest.pop(field, None)
        hp, maximum = player.get("hp"), player.get("max_hp")
        if type(hp) is int and type(maximum) is int and maximum > 0:
            points[step] = (step, max(0, min(100, 100 * hp / maximum)), position)
    if potion_slots_added:
        latest["potion_slots_added"] = potion_slots_added
    if known_potion_capacity is not None:
        latest["potion_capacity"] = known_potion_capacity + potion_slots_added - additions_at_capture
    return list(points.values()), latest
