"""Keep a small, player-visible memory for a single modded Steam run."""

from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from time import monotonic


HELPERS = str(Path(__file__).resolve().parents[1] / "python")
if HELPERS not in sys.path:
    sys.path.insert(0, HELPERS)
from steam_progress import SteamProgressError, SteamRunEvidence


MAX_CONTEXT_BYTES = 480
MAX_FILE_BYTES = 64 * 1024
MAX_NOTES = 6
MAX_NOTE_BYTES = 88
MAX_PLAN_BYTES = 160
CHECKPOINT_INTERVAL = 2.0


class _ModdedEvidence(SteamRunEvidence):
    def __init__(self, profile):
        account = SteamRunEvidence(profile)
        super().__init__(profile, account_root=account.account_root / "modded")


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _text(value, limit):
    if not isinstance(value, str):
        return ""
    clean = "".join(character for character in " ".join(value.split()) if character.isprintable())
    return clean.encode("utf-8")[:limit].decode("utf-8", errors="ignore").strip()


def _run(state):
    run = state.get("run") if isinstance(state, dict) else None
    return run if isinstance(run, dict) else {}


def _scope(state):
    run = _run(state)
    profile, seed, character = run.get("profile"), run.get("seed"), run.get("character")
    if (type(profile) is not int or profile not in (1, 2, 3) or not isinstance(seed, str)
            or not 0 < len(seed) <= 80 or not seed.strip() or not seed.isprintable() or not isinstance(character, str)
            or not character.startswith("CHARACTER.")):
        return None
    state_id = state.get("state_id")
    session = state_id.partition(":")[0] if isinstance(state_id, str) else ""
    started = run.get("start_time")
    return profile, seed, character, session, started if type(started) is int and started > 0 else None


def _deck(run):
    deck = run.get("deck")
    if not isinstance(deck, list):
        return None
    cards = Counter()
    for card in deck:
        if not isinstance(card, dict) or type(card.get("count")) is not int or card["count"] <= 0:
            return None
        name = _text(card.get("id"), 45)
        if not name:
            return None
        cards[name + ("+" if card.get("is_upgraded") is True else "")] += card["count"]
    return cards


def _relics(run):
    relics = run.get("relics")
    if not isinstance(relics, list):
        return None
    names = [_text(item, 45) for item in relics]
    return Counter(names) if all(names) else None


def _changes(label, before, after):
    if before is None or after is None or before == after:
        return ""
    items = []
    for sign, diff in (("+", after - before), ("-", before - after)):
        for name, count in sorted(diff.items()):
            items.append(f"{sign}{name}" if count == 1 else f"{sign}{name} x{count}")
    return f"{label} {', '.join(items)}" if items else ""


def _location(run):
    act, floor = run.get("act"), run.get("floor")
    return (act, floor) if type(act) is int and type(floor) is int else None


def _route_map_after(before, action, after):
    before_location = _location(_run(before))
    after_location = _location(_run(after))
    if before.get("screen") != "map" or action.get("kind") != "select_map_node":
        return None
    if before_location is None or after_location != (before_location[0], before_location[1] + 1):
        return None
    visible_map, detail = before["state"], action["detail"]
    col, row = detail.get("col"), detail.get("row")
    if ((visible_map.get("act"), visible_map.get("floor")) != before_location
            or type(col) is not int or type(row) is not int or not isinstance(visible_map.get("nodes"), list)):
        return None
    if not any(isinstance(node, dict) and (node.get("col"), node.get("row")) == (col, row)
               for node in visible_map["nodes"]):
        return None
    return {"act": after_location[0], "floor": after_location[1],
            "current": {"col": col, "row": row}, "nodes": visible_map["nodes"]}


def _facts(before, action, after):
    old_run, new_run = _run(before), _run(after)
    location = _location(new_run)
    stage = f"A{location[0]} F{location[1]}: " if location is not None else ""
    fact = _changes("Deck", _deck(old_run), _deck(new_run))
    if fact:
        yield stage + fact
    fact = _changes("Relics", _relics(old_run), _relics(new_run))
    if fact:
        yield stage + fact

    location = _location(new_run)
    if location is None:
        return
    act, floor = location
    screen = _text(after.get("screen"), 28)
    kind = action.get("kind") if isinstance(action, dict) else None
    detail = action.get("detail") if isinstance(action, dict) else None
    detail = detail if isinstance(detail, dict) else {}
    if location != _location(old_run) and screen:
        room = _text(detail.get("type"), 28) if kind == "select_map_node" else ""
        yield f"A{act} F{floor}: entered {room or screen}"
    if kind in ("choose_event_option", "choose_rest_option", "buy_shop_item"):
        title = _text(detail.get("title"), 50)
        if title:
            yield f"A{act} F{floor}: chose {title}"
    if before.get("screen") == "combat" and screen in ("rewards", "post_combat"):
        hp = new_run.get("hp")
        if type(hp) is int:
            yield f"A{act} F{floor}: finished combat at {hp} HP"


class SteamModMemory:
    """Bind optional persistence to a verified native checkpoint without blocking play."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.scope = None
        self.reader = None
        self.identity = None
        self.path = None
        self.plan = ""
        self.notes = []
        self.route_map = None
        self.next_check = 0.0

    def context(self, state):
        if not self._sync(state):
            return {}
        result = {}
        if self.plan:
            result["plan"] = self.plan
        if self.notes:
            result["recent"] = list(self.notes)
        if self.route_map and (self.route_map.get("act"), self.route_map.get("floor")) == _location(_run(state)):
            result["route_map"] = self.route_map
        return result

    def record(self, before, action, after, *, plan=""):
        if _scope(before) != _scope(after) or not self._sync(after):
            return
        previous = self.plan, list(self.notes)
        self.plan = _text(plan, MAX_PLAN_BYTES) or self.plan
        for fact in _facts(before, action, after):
            self._note(fact)
        self._compact()
        route_map = _route_map_after(before, action, after)
        if route_map is not None:
            self.route_map = route_map
        if (self.plan, self.notes) != previous or route_map is not None:
            self._save()

    def _sync(self, state):
        scope = _scope(state)
        if scope is None:
            return False
        if scope != self.scope:
            self.scope, self.reader, self.identity, self.path = scope, None, None, None
            self.plan, self.notes = "", []
            self.route_map = None
            self.next_check = 0.0
        now = monotonic()
        if now < self.next_check:
            return True
        self.next_check = now + CHECKPOINT_INTERVAL
        profile, seed, character, _, visible_start = scope
        try:
            if self.reader is None:
                self.reader = _ModdedEvidence(profile)
            checkpoint = self.reader.read_current()
        except (OSError, SteamProgressError):
            return True
        if checkpoint is None:
            return True
        native = checkpoint.identity
        run = _run(state)
        visible_ascension = run.get("ascension")
        if (native.profile != profile or native.seed != seed or native.character != character
                or (visible_start is not None and native.start_time != visible_start)
                or (type(visible_ascension) is int and native.ascension != visible_ascension)):
            return True
        if native != self.identity:
            self._bind(native)
        return True

    def _bind(self, identity):
        if self.identity is not None:
            self.plan, self.notes = "", []
        run_id = asdict(identity)
        scope_id = [str(self.reader.account_root), run_id]
        digest = sha256(_json(scope_id)).hexdigest()[:24]
        self.identity = identity
        self.path = self.directory / f"profile-{identity.profile}-{identity.start_time}-{digest}.json"
        pending_plan, pending_notes = self.plan, self.notes
        data = self._load()
        self.plan = pending_plan or _text(data.get("plan"), MAX_PLAN_BYTES)
        route_map = data.get("route_map")
        self.route_map = route_map if isinstance(route_map, dict) else None
        self.notes = []
        notes = data.get("recent")
        if isinstance(notes, list):
            for note in notes[-MAX_NOTES:]:
                self._note(note)
        for note in pending_notes:
            self._note(note)
        self._compact()
        if pending_plan or pending_notes:
            self._save()

    def _note(self, fact):
        note = _text(fact, MAX_NOTE_BYTES)
        if note and note not in self.notes:
            self.notes.append(note)

    def _compact(self):
        self.notes = self.notes[-MAX_NOTES:]
        while self.notes and len(_json({"plan": self.plan, "recent": self.notes})) > MAX_CONTEXT_BYTES:
            self.notes.pop(0)

    def _load(self):
        try:
            with self.path.open("rb") as source:
                raw = source.read(MAX_FILE_BYTES + 1)
            if len(raw) <= MAX_FILE_BYTES:
                data = json.loads(raw)
                if (isinstance(data, dict) and data.get("version") == 1
                        and data.get("identity") == asdict(self.identity)):
                    return data
        except (OSError, ValueError, RecursionError):
            pass
        return {}

    def _save(self):
        if self.path is None:
            return
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=self.directory, suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(_json({"version": 1, "identity": asdict(self.identity),
                                    "plan": self.plan, "recent": self.notes, "route_map": self.route_map}))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        except OSError:
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
