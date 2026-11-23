"""Score archived Steam Mod combats per room checkpoint, to compare agent versions.

Attempts that start a combat from the same room checkpoint (same run seed, floor, encounter,
HP, potions and opening hand) are grouped, so repeated attempts of one fight are compared like
for like. Restore a checkpoint and play it a few times with each agent version, then compare
the two time windows:

  python agent/steam_mod_benchmark.py --until 2026-11-23T00:00 --label before
  python agent/steam_mod_benchmark.py --since 2026-11-23T00:00 --label after
  python agent/steam_mod_benchmark.py --only-repeated --json report.json

Per attempt it records: result, HP lost, turns, preventable HP (turns ended with energy and
an affordable plain Block card while shown attacks got through, which the end-turn guard now
plays), potions used, potions still held at a defeat, and the countdown race requirement.
Draws diverge once actions differ, so play each checkpoint several times and compare averages.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from steam_mod_tactics import combat_tactics, end_turn_guard  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _rows(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _when(value):
    """Parse an ISO time as an aware UTC datetime; a time without a zone is local time."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(timezone.utc)


def _cli_time(value):
    parsed = _when(value)
    if parsed is None:
        raise argparse.ArgumentTypeError(f"not an ISO date/time: {value!r}")
    return parsed


def snapshot(state):
    """Rebuild a native-shaped combat snapshot from an archived combat_play state."""
    energy = state.get("energy") or 0
    hand = [card for card in state.get("hand") or [] if isinstance(card, dict)]
    enemies = [enemy for enemy in state.get("enemies") or [] if isinstance(enemy, dict)]
    alive = [enemy for enemy in enemies if (enemy.get("hp") or 0) > 0]
    actions = []
    for card in hand:
        cost = card.get("energy_cost")
        if card.get("affliction") or not isinstance(cost, int) or cost > energy:
            continue
        detail = {"card_index": card.get("index"), "card_id": card.get("id"), "description": card.get("description")}
        targets = [enemy.get("index") for enemy in alive] if card.get("target_type") == "AnyEnemy" else [None]
        for target in targets:
            actions.append({"kind": "play_card", "detail": {**detail, **({"target_index": target} if target is not None else {})}})
    actions.append({"kind": "end_turn", "detail": {}})
    player = state.get("player") or {}
    return {"screen": "combat", "actions": actions, "state": {
        "energy": energy, "hand": hand, "enemies": alive,
        "draw_pile_count": state.get("draw_pile_count") or 0, "discard_pile_count": state.get("discard_pile_count") or 0,
        "player": {"hp": player.get("hp"), "block": player.get("block") or 0,
                   "powers": player.get("powers") or [], "relics": player.get("relics") or []},
    }}


def preventable(state):
    """HP the end-turn guard would have saved at this end of turn, applying it repeatedly."""
    view = snapshot(state)
    saved = 0
    for _ in range(10):
        guard = end_turn_guard(view)
        if guard is None:
            return saved
        saved += guard["estimated_hp_saved"]
        combat = view["state"]
        played = view["actions"][guard["choice"] - 1]["detail"]["card_index"]
        combat["energy"] -= guard["energy_cost"]
        combat["player"]["block"] += guard["block"]
        combat["hand"] = [card for card in combat["hand"] if card.get("index") != played]
        view = snapshot({**state, "energy": combat["energy"], "hand": combat["hand"],
                         "player": {**(state.get("player") or {}), "block": combat["player"]["block"]}})
    return saved


def split_attempts(rows):
    """Split one room's rows into combat attempts.

    A retry inside the room (the agent's retry_current_combat, or a manual Save and Quit then
    Continue with a new session) restarts the fight in the same room folder. The turn number
    going backwards marks the start of the next attempt.
    """
    segments, current, last_turn = [], [], None
    for row in rows:
        data = row.get("data") or {}
        if row.get("type") == "state" and data.get("decision") == "combat_play" and type(data.get("turn")) is int:
            if last_turn is not None and data["turn"] < last_turn and current:
                segments.append(current)
                current = []
            last_turn = data["turn"]
        current.append(row)
    if current:
        segments.append(current)
    return segments


def attempt(room_dir, rows, *, last_room, run_status, retried=False):
    states, decisions = [], []
    current = None
    for row in rows:
        if row.get("type") == "state":
            current = row.get("data") or {}
            if current.get("decision") == "combat_play":
                states.append(current)
        elif row.get("type") == "action" and current is not None and current.get("decision") == "combat_play":
            decisions.append((current, row.get("data") or {}))
    if not states:
        return None
    first, last = states[0], states[-1]
    player = first.get("player") or {}
    opening = {
        "character": player.get("character_id"), "act": (first.get("context") or {}).get("act"),
        "floor": (first.get("context") or {}).get("floor"), "encounter": first.get("encounter"),
        "hp": player.get("hp"), "potions": [p.get("id") for p in player.get("potions") or [] if p],
        "hand": [c.get("id") for c in first.get("hand") or []],
    }
    lost = not retried and last_room and run_status == "defeat"
    # An attempt followed by another attempt in the same room was abandoned, not won or lost.
    result = "retried" if retried else "lost" if lost else "won" if not last_room else "unfinished"
    end_hp = 0 if lost else (last.get("player") or {}).get("hp")
    end_turns = [(state, action) for state, action in decisions if action.get("action") == "end_turn"]
    races = []
    for state in states:
        for risk in combat_tactics(snapshot(state)).get("forced_defeat_countdowns", []):
            races.append({"turn": state.get("turn"), "turns_remaining": risk["turns_remaining"],
                          "damage_needed_per_turn": risk.get("damage_needed_per_turn")})
    held = [p.get("id") for p in (last.get("player") or {}).get("potions") or [] if p]
    return {
        "room": room_dir.name, "run": room_dir.parent.name, "opening": opening,
        "checkpoint": sha256(json.dumps(opening, sort_keys=True).encode()).hexdigest()[:10],
        "result": result, "turns": max((s.get("turn") or 0) for s in states),
        "hp_start": opening["hp"], "hp_lost": (opening["hp"] or 0) - (end_hp or 0) if end_hp is not None else None,
        "preventable_hp": sum(preventable(state) for state, _ in end_turns),
        "turns_ended_with_preventable_damage": sum(1 for state, _ in end_turns if preventable(state)),
        "potions_used": [a.get("args", {}).get("potion_id") for _, a in decisions if a.get("action") == "use_potion"],
        "potions_held_at_defeat": held if lost else [],
        "race": races[:1] + races[-1:] if races else [],
    }


def attempt_time(rows):
    """When this combat attempt was played: the first timestamp recorded in the room.

    A retry from an old save keeps the original run's start time in run.json, so filtering on
    that would drop fresh attempts; the room's own rows carry the time it was actually played.
    """
    stamps = [stamp for row in rows if (stamp := _when(row.get("ts")))]
    return min(stamps) if stamps else None


def collect(runs_dir, since=None, until=None):
    attempts = []
    for run_file in sorted(runs_dir.glob("*/run.json")):
        info = json.loads(run_file.read_text(encoding="utf-8"))
        rooms = sorted(path.parent for path in run_file.parent.glob("*/states.jsonl"))
        for position, room in enumerate(rooms):
            segments = split_attempts(_rows(room / "states.jsonl"))
            for number, rows in enumerate(segments, 1):
                played = attempt_time(rows)
                if (since or until) and played is None:
                    continue
                if (since and played < since) or (until and played >= until):
                    continue
                item = attempt(room, rows, last_room=position == len(rooms) - 1, run_status=info.get("status"),
                               retried=number < len(segments))
                if item:
                    item["run_started"] = info.get("started")
                    item["attempt_started"] = played.isoformat() if played else None
                    item["attempt_in_room"] = f"{number}/{len(segments)}"
                    attempts.append(item)
    return attempts


def summarize(attempts):
    groups = defaultdict(list)
    for item in attempts:
        groups[item["checkpoint"]].append(item)
    summary = []
    for key, items in groups.items():
        done = [item for item in items if item["result"] in ("won", "lost")]
        opening = items[0]["opening"]
        summary.append({
            "checkpoint": key, "label": f"A{opening['act']:02d} F{opening['floor']:03d} {opening['encounter']}",
            "attempts": len(items), "wins": sum(item["result"] == "won" for item in done), "decided": len(done),
            "retried": sum(item["result"] == "retried" for item in items),
            "avg_hp_lost": round(sum(item["hp_lost"] or 0 for item in done) / len(done), 1) if done else None,
            "avg_preventable_hp": round(sum(item["preventable_hp"] for item in items) / len(items), 1),
            "defeats_holding_potions": sum(1 for item in items if item["potions_held_at_defeat"]),
        })
    summary.sort(key=lambda row: (-row["attempts"], row["label"]))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "STS2 Runs")
    parser.add_argument("--since", type=_cli_time, help="only combat attempts played at or after this time (ISO; no zone = local time)")
    parser.add_argument("--until", type=_cli_time, help="only combat attempts played before this time (ISO; no zone = local time)")
    parser.add_argument("--only-repeated", action="store_true", help="only checkpoints with 2+ attempts")
    parser.add_argument("--label", default="", help="name printed with the report, e.g. before/after")
    parser.add_argument("--json", type=Path, help="also write every attempt and the summary to this file")
    options = parser.parse_args(argv)
    attempts = collect(options.runs_dir, options.since, options.until)
    summary = summarize(attempts)
    if options.only_repeated:
        summary = [row for row in summary if row["attempts"] >= 2]
    print(f"Checkpoint benchmark {options.label}".strip() + f": {len(attempts)} combats, {len(summary)} checkpoints")
    print(f"{'checkpoint':<44}{'tries':>6}{'wins':>8}{'retried':>9}{'HP lost':>9}{'prevent.':>10}{'died w/ pots':>14}")
    for row in summary:
        wins = f"{row['wins']}/{row['decided']}"
        lost = "-" if row["avg_hp_lost"] is None else row["avg_hp_lost"]
        print(f"{row['label'][:43]:<44}{row['attempts']:>6}{wins:>8}{row['retried']:>9}{lost:>9}"
              f"{row['avg_preventable_hp']:>10}{row['defeats_holding_potions']:>14}")
    total = [item for item in attempts if item["result"] in ("won", "lost")]
    if total:
        print(f"\nAll decided combats: {sum(i['result'] == 'won' for i in total)}/{len(total)} won, "
              f"avg HP lost {sum(i['hp_lost'] or 0 for i in total) / len(total):.1f}, "
              f"preventable HP {sum(i['preventable_hp'] for i in attempts)}, "
              f"defeats holding potions {sum(1 for i in attempts if i['potions_held_at_defeat'])}")
    if options.json:
        options.json.write_text(json.dumps({"summary": summary, "attempts": attempts}, indent=1, ensure_ascii=False),
                                encoding="utf-8")
        print(f"Wrote {options.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
