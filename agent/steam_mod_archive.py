"""Convert confirmed Steam Mod journal rows to desktop run archives."""

from collections import defaultdict, deque
from datetime import datetime, timezone
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
from tempfile import NamedTemporaryFile


ROOMS = {"combat": "battle", "event": "event", "rest": "rest", "shop": "shop", "treasure": "chest"}
MAP_ROOMS = {"monster": "battle", "elite": "elite", "boss": "boss", "shop": "shop", "treasure": "chest",
             "restsite": "rest"}
ROOM_NAMES = {"battle": "Battle", "elite": "Elite", "boss": "Boss", "event": "Event", "rest": "Rest Site",
              "shop": "Shop", "chest": "Treasure"}
OVERLAYS = {"rewards", "card_reward", "card_selection", "post_combat", "tutorial", "settlement"}
CHARACTERS = {name.upper(): name for name in ("Ironclad", "Silent", "Regent", "Necrobinder", "Defect", "Fool")}
IDENTITY_FIELDS = ("profile", "start_time", "seed", "character", "ascension")


def _identity(value):
    if isinstance(value, dict):
        data = {field: value.get(field) for field in IDENTITY_FIELDS}
    else:
        data = {field: getattr(value, field, None) for field in IDENTITY_FIELDS}
    profile, start, seed, role, level = data.values()
    if (type(profile) is int and profile in (1, 2, 3) and type(start) is int and 0 < start < 2**40
            and isinstance(seed, str) and 0 < len(seed) <= 80 and seed.isprintable() and seed.strip()
            and isinstance(role, str) and role.startswith("CHARACTER.") and role.isprintable()
            and type(level) is int and level >= 0):
        return data
    return None


def _object(value):
    return value if isinstance(value, dict) else {}


def _read_object(path):
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, RecursionError):
        return {}


def _rows(path):
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def _atomic_json(path, value):
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _atomic_text(path, text):
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _checkpoint(run, state, screen):
    def stable(value):
        if isinstance(value, dict):
            return {key: stable(item) for key, item in value.items()
                    if key not in {"instance_id", "target_instance_id"}}
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value

    # Visual overlays are not checkpoints. Compare room state and inventory without
    # transient battle IDs, so Save and Quit can match a room from an earlier session.
    inventory = {key: run.get(key) for key in ("hp", "max_hp", "gold", "deck", "potions", "relics")}
    payload = stable([screen, inventory, state])
    fingerprint = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"screen": screen, "turn": state.get("turn") if screen == "combat" else None,
            "run_instance": run.get("run_instance"), "fingerprint": fingerprint}


def _timestamp(value):
    if isinstance(value, str):
        try:
            time = datetime.fromisoformat(value)
            if time.tzinfo is not None:
                return time.timestamp()
        except (ValueError, OSError, OverflowError):
            pass
    return None


def _stage(value):
    act, floor = value.get("act"), value.get("floor")
    return (act, floor) if type(act) is int and 1 <= act <= 10 and type(floor) is int and 0 <= floor <= 500 else None


def _coord(value):
    item = _object(value)
    col, row = item.get("col"), item.get("row")
    return (col, row) if type(col) is int and 0 <= col <= 30 and type(row) is int and 0 <= row <= 60 else None


def _position(coord):
    return {"col": coord[0], "row": coord[1]}


def _item_label(value):
    return value.rsplit(".", 1)[-1].replace("_", " ").title()


def _inventory_id(value):
    return isinstance(value, str) and 0 < len(value) <= 90 and value.isprintable()


def _player(run, state, screen):
    player = {key: run[key] for key in ("hp", "max_hp", "gold") if type(run.get(key)) is int}
    native_player = _object(state.get("player"))
    block = native_player.get("block")
    player["block"] = block if screen == "combat" and type(block) is int else None
    potions = run.get("potions")
    if not isinstance(potions, list):
        potions = state.get("potions")
    player["potions"] = [item for item in potions if isinstance(item, dict)] if isinstance(potions, list) else None
    capacity = run.get("potion_capacity")
    player["potion_capacity"] = capacity if type(capacity) is int and capacity >= 0 else None
    player["character_id"] = run["character"]
    deck = run.get("deck")
    if isinstance(deck, list):
        player["deck"] = []
        for group in deck:
            item = _object(group)
            identifier, count = item.get("id"), item.get("count")
            if _inventory_id(identifier) and type(count) is int and 1 <= count <= 999:
                detail = {"id": identifier, "name": _item_label(identifier), "upgraded": item.get("is_upgraded") is True}
                player["deck"].extend([detail] * count)
    relics = run.get("relics")
    if isinstance(relics, list):
        live_relics = native_player.get("relics")
        if not isinstance(live_relics, list):
            live_relics = []
        details = {row["id"]: row for row in live_relics if isinstance(row, dict) and _inventory_id(row.get("id"))}
        player["relics"] = [{"name": _item_label(item), **details.get(item, {}), "id": item}
                            for item in relics if _inventory_id(item)]
    return player


def _map_data(state, context):
    rows, trace = defaultdict(list), []
    nodes = state.get("nodes")
    current = _coord(state.get("current"))
    for item in nodes if isinstance(nodes, list) else ():
        coord = _coord(item)
        if coord is None:
            continue
        kind = item.get("type")
        children = item.get("children")
        visited = item.get("state") in ("Traveled", "Visited") or coord == current
        if visited:
            trace.append(coord)
        rows[coord[1]].append({**_position(coord), "type": kind if isinstance(kind, str) else "Unknown",
                               "visited": visited, "current": coord == current,
                               "children": [_position(p) for v in children if (p := _coord(v)) is not None]
                               if isinstance(children, list) else []})
    if not rows:
        return None
    return {"type": "map", "context": context, "rows": [rows[r] for r in sorted(rows)],
            "current_coord": _position(current) if current is not None else None,
            "visited_path": [_position(p) for p in sorted(set(trace), key=lambda coord: (coord[1], coord[0]))]}


def _action_label(action):
    detail = _object(action.get("detail"))
    label = action["kind"].replace("_", " ").capitalize()
    card = _object(detail.get("card"))
    if isinstance(card.get("title"), str):
        return f"{label} · {' '.join(card['title'].split())[:100]}"
    for key in ("card", "title", "target", "type", "id"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            return f"{label} · {' '.join(value.split())[:100]}"
    return label


def _room_kind(screen, state):
    room = ROOMS.get(screen)
    if room == "battle":
        encounter = state.get("encounter")
        if isinstance(encounter, str) and encounter.upper().endswith(("_BOSS", "_ELITE")):
            return encounter.rsplit("_", 1)[-1].lower()
        if not encounter:
            return None
    return room


class SteamModArchive:
    """Append verified observations without blocking or influencing the live agent."""

    def __init__(self, history_dir, *, identity=None, provider="DeepSeek", model="deepseek-flash"):
        self.root = Path(history_dir)
        self.provider = provider
        self.model = model
        self.identity = None
        self.folder = None
        self.info = {}
        self.buffer = deque(maxlen=192)
        self.pending = None
        self.recovery_accepted = False
        self.step = 0
        self.seen = set()
        self.scenes = {}
        self.coordinates = {}
        self.expected_rooms = {}
        self.previous = None
        self.scene = None
        self.retry_stage = None
        self.rewinds = 0
        if identity is not None:
            self.bind(identity)

    def bind(self, identity):
        exact = _identity(identity)
        if exact is None or self.identity is not None:
            return self.identity is not None and exact == self.identity
        try:
            started = datetime.fromtimestamp(exact["start_time"], tz=timezone.utc).astimezone()
            label = CHARACTERS.get(exact["character"].split(".", 1)[1], "Run")
            key = sha256(json.dumps(exact, sort_keys=True).encode()).hexdigest()[:12]
            folder = self.root / f"{started:%Y-%m-%d_%H-%M-%S} Steam Mod {label} {key}"
            folder.mkdir(parents=True, exist_ok=True)
            info = _read_object(folder / "run.json")
            if info and (info.get("source") != "steam_mod" or info.get("native_identity") != exact):
                return False
            if not info:
                info = {"started": started.isoformat(timespec="seconds"), "status": "partial", "provider": self.provider,
                        "model": self.model, "character": label, "seed": exact["seed"], "ascension": exact["ascension"],
                        "last_stage": None, "source": "steam_mod", "native_identity": exact}
            if info.get("run_id") != key:
                info["run_id"] = key
                _atomic_json(folder / "run.json", info)
            for path in sorted(folder.glob("*/scene.json")):
                room = _read_object(path)
                name = room.get("room")
                if (location := _stage(room)) and isinstance(name, str) and name in ROOM_NAMES:
                    self.scenes[(*location, name)] = path.parent
            for row in _rows(folder / "gameplay.jsonl"):
                origin, step = row.get("origin"), row.get("step")
                if isinstance(origin, str):
                    self.seen.add(origin)
                if type(step) is int:
                    self.step = max(self.step, step)
                context = _object(_object(row.get("data")).get("context"))
                if stage := _stage(context):
                    if coord := _coord(context.get("map_coord")):
                        self.coordinates[stage] = coord
                    expected = context.get("expected_room")
                    if isinstance(expected, str) and expected in ROOM_NAMES:
                        self.expected_rooms[stage] = expected
                    elif context.get("room_type") == self.expected_rooms.get(stage):
                        self.expected_rooms.pop(stage, None)
        except (OSError, OverflowError, ValueError):
            return False
        self.identity, self.folder, self.info = exact, folder, info
        for row in self.buffer:
            self.append(row)
        self.buffer.clear()
        return True

    def append(self, row):
        if not isinstance(row, dict):
            return
        if self.folder is None:
            self.buffer.append(row)
            run = _object(row.get("run"))
            terminal = _object(row.get("state"))
            if row.get("type") == "settlement" and terminal.get("native_history") is True:
                run = {**run, "start_time": terminal.get("start_time")}
            self.bind(run)
            return
        try:
            self._append(row)
        except (OSError, ValueError, OverflowError):
            # Journaling is optional. Play and the independent source journal can continue.
            pass

    def _belongs(self, row, when):
        run = _object(row.get("run"))
        trusted = self.identity
        return (when >= trusted["start_time"] and all(run.get(k) == trusted[k] for k in ("profile", "seed", "character"))
                and all(k not in run or run[k] is None or run[k] == trusted[k] for k in ("start_time", "ascension")))

    def _append(self, row):
        kind = row.get("type")
        when = _timestamp(row.get("utc"))
        if when is None:
            return
        if kind in ("decision", "grid_recovery_decision"):
            action = _object(row.get("action"))
            index = row.get("index")
            self.pending = None
            self.recovery_accepted = False
            if isinstance(action.get("kind"), str) and (kind == "grid_recovery_decision" or type(index) is int):
                self.pending = (None if kind == "grid_recovery_decision" else index), action, row["utc"]
            return
        if kind == "grid_recovery_accepted":
            self.recovery_accepted = bool(self.pending and self.pending[0] is None and
                                          self.pending[1].get("id") == row.get("action_id") and
                                          isinstance(row.get("action_id"), str))
            return
        if kind in ("combat_retry_completed", "event_retry_completed"):
            if self._belongs(row, when):
                self.retry_stage = _stage(row["run"])
                self.pending = None
            return
        if kind in ("start", "state_changed", "grid_recovery"):
            self.pending = None
            self.recovery_accepted = False
        if kind == "start":
            self.scene, self.previous = None, None
        if kind not in ("start", "state_changed", "observed", "settlement", "grid_recovery", "grid_recovery_observed") or not self._belongs(row, when):
            return
        run = row["run"]
        stage, state = _stage(run), _object(row.get("state"))
        screen = "settlement" if kind == "settlement" else row.get("screen")
        if stage is None or not isinstance(screen, str):
            return
        origin = f"{row['utc']}:{kind}:{row.get('index', '')}"
        if origin in self.seen:
            self.previous = stage
            if self.pending and self.pending[0] == row.get("index"):
                self.pending = None
            return

        checkpoint = _checkpoint(run, state, screen) if screen in ROOMS else None
        if kind == "start" or stage == self.retry_stage:
            self._resume(stage, screen, checkpoint, explicit=stage == self.retry_stage)
            self.retry_stage = None
        position = state.get("current") if screen == "map" else run.get("map_coord")
        if (coord := _coord(position)) is not None:
            self.coordinates[stage] = coord
        decision = None
        if self.pending:
            index = self.pending[0]
            if ((kind == "observed" and index is not None and index == row.get("index")) or
                    (kind == "grid_recovery_observed" and index is None and self.recovery_accepted)):
                decision = self.pending
        self.pending = None
        self.recovery_accepted = False
        records = []
        if decision:
            _, action, timestamp = decision
            args = _object(action.get("detail"))
            if action["kind"] == "select_map_node":
                if self.previous is not None and stage != self.previous and (coord := _coord(args)) is not None:
                    self.coordinates[stage] = coord
                    node_type = args.get("type")
                    if isinstance(node_type, str) and (expected := MAP_ROOMS.get(node_type.casefold())):
                        self.expected_rooms[stage] = expected
                else:
                    args = {k: v for k, v in args.items() if k not in ("row", "col")}
            self.step += 1
            records.append({"step": self.step, "ts": timestamp, "type": "action", "origin": origin,
                            "data": {"cmd": "action", "action": action["kind"], "args": args}})

        context = dict(zip(("act", "floor"), stage))
        expected = self.expected_rooms.get(stage)
        room = _room_kind(screen, state)
        if expected is not None:
            if room == expected:
                del self.expected_rooms[stage]
            else:
                context["expected_room"] = expected
                if room is not None:
                    # The native floor can advance while the preceding room is still visible.
                    screen, state, room = "transition", {}, None
        scene = self._scene_for(stage, screen, room)
        if type(state.get("act_floor")) is int:
            context["act_floor"] = state["act_floor"]
        if stage in self.coordinates:
            context["map_coord"] = _position(self.coordinates[stage])
        if scene is not None:
            context["room_type"] = _read_object(scene / "scene.json").get("room")
        if screen == "map" and (map_data := _map_data(state, context)):
            records.append({"step": self.step, "ts": row["utc"], "type": "state", "origin": origin, "data": map_data})
        name = {"combat": "combat_play", "map": "map_select"}.get(screen, screen)
        data = {"type": "decision", "decision": name, "context": context, "player": _player(run, state, screen)}
        if screen == "combat":
            data.update({key: state[key] for key in ("energy", "max_energy", "turn", "hand", "enemies", "encounter") if key in state})
        elif screen in OVERLAYS or screen in ROOMS:
            data["steam_state"] = state
        entry = {"step": self.step, "ts": row["utc"], "type": "state", "origin": origin, "data": data}
        if checkpoint and screen == checkpoint["screen"]:
            entry["checkpoint"] = checkpoint
        records.append(entry)
        self._write_records(self.folder / "gameplay.jsonl", records)
        self.seen.add(origin)
        if scene is not None:
            self._write_records(scene / "states.jsonl", records)
        if decision:
            hp = run.get("hp", "?")
            transcript = f"{self.step} HP {hp} | {_action_label(decision[1])} -- \n"
            self._write_text(self.folder, transcript)
            if origin_scene := self.scene or scene:
                self._write_text(origin_scene, transcript)
        self.scene, self.previous = scene, stage
        last = _stage(_object(self.info.get("last_stage")))
        if last is None or stage > last:
            self.info["last_stage"] = dict(zip(("act", "floor"), stage))
        previous_update = _timestamp(self.info.get("last_updated"))
        if previous_update is None or when >= previous_update:
            self.info["last_updated"] = row["utc"]
        if screen == "settlement":
            self._settle(state, row["utc"])
        _atomic_json(self.folder / "run.json", self.info)

    def _resume(self, stage, screen, checkpoint, *, explicit):
        previous = _stage(_object(self.info.get("last_stage")))
        if previous is None or stage > previous:
            return
        # Only reloads can replace a branch. Ordinary repeated screens keep their history.
        path = self.folder / "gameplay.jsonl"
        records = list(_rows(path))
        boundary = None
        in_floor = []
        for index, record in enumerate(records):
            data = _object(record.get("data"))
            old_stage = _stage(_object(data.get("context")))
            if old_stage is None:
                continue
            if old_stage >= stage and boundary is None:
                # Actions immediately before a state share its origin and must stay with it.
                start = index
                while start and records[start - 1].get("origin") == record.get("origin"):
                    start -= 1
                boundary = start
            if old_stage == stage and data.get("type") == "decision":
                old = _object(record.get("checkpoint"))
                if not old:
                    old = {"screen": "combat" if data.get("decision") == "combat_play" else data.get("decision"),
                           "turn": data.get("turn")}
                in_floor.append((index, old))

        prior_rooms = [(index, old) for index, old in in_floor if old.get("screen") == screen]
        latest = prior_rooms[-1][1] if prior_rooms else {}
        if checkpoint is not None and prior_rooms:
            turn, prior_turn = checkpoint["turn"], latest.get("turn")
            fingerprint = checkpoint["fingerprint"]
            changed_instance = (checkpoint["run_instance"] and latest.get("run_instance")
                                and checkpoint["run_instance"] != latest["run_instance"])
            turn_rewound = (type(turn) is int and type(prior_turn) is int and turn < prior_turn)
            room_reloaded = bool(changed_instance and (screen == "combat" and turn == 1 or screen == "event"))
            candidates = prior_rooms if explicit or room_reloaded else reversed(prior_rooms)
            match = next((index for index, old in candidates if old.get("fingerprint") == fingerprint), None)
            returned_to_room = (match is not None and match < prior_rooms[-1][0])
            if stage < previous or explicit or turn_rewound or room_reloaded or returned_to_room:
                if match is not None:
                    boundary = match + 1
                elif type(turn) is int and not explicit and stage == previous and not room_reloaded:
                    first = next((index for index, old in prior_rooms
                                  if type(old.get("turn")) is int and old["turn"] >= turn), None)
                    if first is not None:
                        boundary = first
                        while boundary and records[boundary - 1].get("origin") == records[first].get("origin"):
                            boundary -= 1
            else:
                return
        elif stage == previous and not explicit:
            return
        if boundary is None or boundary >= len(records):
            return
        self._replace_history(records[:boundary])
        self.rewinds += 1

    def _replace_history(self, records):
        old_scenes = set(self.scenes.values())
        self.scenes.clear()
        self.seen.clear()
        self.coordinates.clear()
        self.expected_rooms.clear()
        self.step, self.scene, self.previous = 0, None, None
        scene_states, scene_text = defaultdict(list), defaultdict(list)
        transcript = []
        for origin, grouped in groupby(records, key=lambda record: record.get("origin")):
            chunk = list(grouped)
            if isinstance(origin, str):
                self.seen.add(origin)
            self.step = max((entry["step"] for entry in chunk if type(entry.get("step")) is int), default=self.step)
            view = next((_object(row.get("data")) for row in reversed(chunk) if row.get("type") == "state"), {})
            context = _object(view.get("context"))
            stage = _stage(context)
            if stage is None:
                continue
            if coord := _coord(context.get("map_coord")):
                self.coordinates[stage] = coord
            expected = context.get("expected_room")
            if expected in ROOM_NAMES:
                self.expected_rooms[stage] = expected
            else:
                self.expected_rooms.pop(stage, None)
            room = context.get("room_type")
            scene = self._scene_for(stage, "", room) if room in ROOM_NAMES else None
            if scene is not None:
                scene_states[scene].extend(chunk)
            for row in chunk:
                if row.get("type") != "action":
                    continue
                data = _object(row.get("data"))
                if not isinstance(data.get("action"), str):
                    continue
                action = {"kind": data["action"], "detail": data.get("args")}
                hp = _object(view.get("player")).get("hp", "?")
                line = f"{row.get('step', self.step)} HP {hp} | {_action_label(action)} -- \n"
                transcript.append(line)
                if target := self.scene or scene:
                    scene_text[target].append(line)
            self.scene, self.previous = scene, stage

        def json_lines(items):
            return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in items)

        # The per-session source journals are untouched. Regenerate the current branch
        # and hide room files that belonged only to the superseded suffix.
        _atomic_text(self.folder / "gameplay.jsonl", json_lines(records))
        _atomic_text(self.folder / "transcript.txt", "".join(transcript))
        for scene in set(self.scenes.values()):
            info = _read_object(scene / "scene.json")
            _atomic_text(scene / "states.jsonl", json_lines(scene_states[scene]))
            _atomic_text(scene / "transcript.txt",
                         f"Entered Act {info['act']} · Floor {info['floor']} · {ROOM_NAMES[info['room']]}\n"
                         + "".join(scene_text[scene]))
        for scene in old_scenes - set(self.scenes.values()):
            for name in ("scene.json", "states.jsonl", "transcript.txt"):
                (scene / name).unlink(missing_ok=True)
        self.info.update(status="partial", last_stage=dict(zip(("act", "floor"), self.previous)) if self.previous else None)
        for key in ("ended", "native_outcome", "build"):
            self.info.pop(key, None)

    def _scene_for(self, stage, screen, room):
        if room is None:
            if screen in OVERLAYS:
                return next((path for location, path in reversed(self.scenes.items()) if location[:2] == stage), None)
            if screen == "combat":
                return self.scenes.get((*stage, "battle"))
            return None
        key = (*stage, room)
        if key not in self.scenes:
            act, floor = stage
            name = ROOM_NAMES[room]
            scene = self.folder / f"A{act:02d} F{floor:03d} - {name}"
            scene.mkdir(exist_ok=True)
            _atomic_json(scene / "scene.json", {"act": act, "floor": floor, "room": room})
            if not (scene / "transcript.txt").is_file():
                self._write_text(scene, f"Entered Act {act} · Floor {floor} · {name}\n")
            self.scenes[key] = scene
        return self.scenes[key]

    def _settle(self, state, when):
        outcome = state.get("outcome")
        if (state.get("native_history") is not True or state.get("start_time") != self.identity["start_time"]
                or outcome not in ("victory", "defeat", "abandoned")):
            return
        previous = self.info.get("native_outcome")
        if previous is None or previous == outcome:
            self.info.update(status="ended" if outcome == "abandoned" else outcome, ended=when,
                             native_outcome=outcome)
            if isinstance(state.get("build"), str):
                self.info["build"] = state["build"]
            if previous is None:
                self._write_text(self.folder, f"Steam settlement · {outcome.capitalize()}\n")

    @staticmethod
    def _write_records(path, records):
        with path.open("a", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _write_text(folder, text):
        with (folder / "transcript.txt").open("a", encoding="utf-8") as file:
            file.write(text)


def import_steam_mod_journals(history_dir, paths, *, identity, provider="DeepSeek", model="deepseek-flash"):
    """Replay caller-verified staged journals in chronological order into one archive."""
    archive = SteamModArchive(history_dir, identity=identity, provider=provider, model=model)
    if archive.folder is None:
        return None
    staged = []
    for source in paths:
        with_rows = _rows(Path(source))
        first = next(with_rows, None)
        with_rows.close()
        if first is not None and (when := _timestamp(first.get("utc"))) is not None:
            staged.append((when, str(source)))
    for _, source in sorted(staged):
        for row in _rows(Path(source)):
            archive.append(row)
    return archive.folder
