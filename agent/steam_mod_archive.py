"""Convert confirmed Steam Mod journal rows to desktop run archives."""

from collections import defaultdict, deque
from datetime import datetime, timezone
from hashlib import sha256
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

        if screen == "map" and (coord := _coord(state.get("current"))) is not None:
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
        records.append({"step": self.step, "ts": row["utc"], "type": "state", "origin": origin, "data": data})
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


def import_steam_mod_journals(history_dir, paths, *, identity, model="deepseek-flash"):
    """Replay caller-verified staged journals in chronological order into one archive."""
    archive = SteamModArchive(history_dir, identity=identity, model=model)
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
