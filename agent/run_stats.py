"""Observed outcomes and progress estimates from the launcher's run archive."""

from datetime import datetime
import json
from pathlib import Path


FINISHED = {"victory", "defeat"}
AI_PROVIDERS = ("DeepSeek", "Claude")


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
    """Align health and progress snapshots to issued gameplay actions."""
    points = {}
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
        hp, maximum = player.get("hp"), player.get("max_hp")
        if type(hp) is int and type(maximum) is int and maximum > 0:
            points[step] = (step, max(0, min(100, 100 * hp / maximum)), position)
    return list(points.values())
