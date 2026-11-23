"""Rank visible native routes without deciding which action the model must take."""

from collections import deque
from dataclasses import dataclass


SHOP_GOLD = 150
MAX_NODES = 256
MAX_ROUTE_STEPS = 20000
ROOM_TYPES = {name.casefold(): name for name in (
    "Ancient", "Boss", "SecondBoss", "Elite", "Monster", "RestSite", "Shop", "Treasure", "Unknown",
)}
BOSS_ROOMS = {"Boss", "SecondBoss"}
POLICIES = {
    "recover": "Prefer a nearby rest with fewer elite and other risky rooms before it.",
    "recover_then_shop": "Prefer a safe, nearby rest followed by a known shop when viable. Otherwise prioritize recovery.",
    "shop": "Prefer an early reachable shop with fewer elites on the way, then lower overall risk.",
    "avoid_elites": "Prefer fewer total elites, then fewer normal fights and uncertain rooms.",
}


@dataclass(frozen=True)
class MapNode:
    kind: str
    children: tuple
    incomplete: bool


def _object(value):
    return value if isinstance(value, dict) else {}


def _coordinate(value):
    value = _object(value)
    col, row = value.get("col"), value.get("row")
    if type(col) is int and type(row) is int and 0 <= col < MAX_NODES and 0 <= row < MAX_NODES:
        return col, row
    return None


def _room_type(value):
    return ROOM_TYPES.get(value.casefold(), "Unclassified") if isinstance(value, str) else "Unclassified"


def _read_graph(items):
    if not isinstance(items, list) or len(items) > MAX_NODES:
        return {}, True
    graph = {}
    invalid = False
    for item in items:
        at = _coordinate(item)
        if at is None:
            invalid = True
            continue
        raw_children = item.get("children")
        children = set()
        incomplete = not isinstance(raw_children, list)
        if isinstance(raw_children, list):
            for item_child in raw_children:
                child = _coordinate(item_child)
                if child is None or child[1] <= at[1]:
                    incomplete = True
                else:
                    children.add(child)
        kind = _room_type(item.get("type"))
        node = MapNode(kind, tuple(sorted(children)), incomplete or kind == "Unclassified")
        if at in graph and graph[at] != node:
            invalid = True
        graph[at] = node
    return graph, invalid


def _priority(run):
    hp, max_hp, gold = run.get("hp"), run.get("max_hp"), run.get("gold")
    wealthy = type(gold) is int and gold >= SHOP_GOLD
    if type(hp) is not int or type(max_hp) is not int or not 0 < hp <= max_hp:
        return "avoid_elites"
    if 20 * hp <= 7 * max_hp:
        return "recover"
    if 5 * hp <= 3 * max_hp:
        return "recover_then_shop" if wealthy else "recover"
    return "shop" if wealthy else "avoid_elites"


def _reachable(graph, starts):
    queue = deque((point, 1) for point in starts)
    distances = {}
    complete = bool(starts)
    while queue:
        point, steps = queue.popleft()
        if point in distances:
            continue
        node = graph.get(point)
        if node is None:
            complete = False
            continue
        distances[point] = steps
        if node.incomplete or (not node.children and node.kind not in BOSS_ROOMS):
            complete = False
        queue.extend((child, steps + 1) for child in node.children)
    return distances, complete


def _type_counts(kinds):
    return kinds.count("Elite"), kinds.count("Monster"), kinds.count("Unknown") + kinds.count("Unclassified")


def _before(kinds, point):
    if point is None:
        return (1, 0, 0, 0)
    elites, monsters, uncertain = _type_counts(kinds[:point])
    return (0, elites, 2 * monsters + uncertain, point + 1)


def _stops(kinds):
    rest = next((index for index, kind in enumerate(kinds) if kind == "RestSite"), None)
    shop = next((index for index, kind in enumerate(kinds) if kind == "Shop"), None)
    shop_after_rest = next((index for index, kind in enumerate(kinds)
                            if rest is not None and index > rest and kind == "Shop"), None)
    return rest, shop, shop_after_rest


def _score(kinds, priority):
    total = _type_counts(kinds)
    if priority == "avoid_elites":
        return total
    rest, shop, shop_after_rest = _stops(kinds)
    rest_cost = _before(kinds, rest)
    shop_cost = _before(kinds, shop)
    if priority == "shop":
        missing, elites, danger, distance = shop_cost
        return (missing, elites, distance, danger, *total)
    if priority == "recover_then_shop":
        safe_rest = rest is not None and rest <= 4 and rest_cost[2] <= 4
        safe_pair = safe_rest and shop_after_rest is not None and "Elite" not in kinds[:shop_after_rest]
        if safe_pair:
            return (0, *rest_cost, shop_after_rest, *total)
        return (1, *rest_cost, *total)
    if priority == "recover":
        return (*rest_cost, *total)
    return total


def _representative_route(graph, start, priority):
    pending = [(start,)]
    best = None
    best_key = None
    steps = 0
    while pending and steps < MAX_ROUTE_STEPS:
        route = pending.pop()
        steps += 1
        node = graph[route[-1]]
        children = [child for child in node.children if child in graph]
        if children:
            pending.extend(route + (child,) for child in reversed(children))
            continue
        kinds = tuple(graph[point].kind for point in route)
        at_boss = node.kind in BOSS_ROOMS
        key = (not at_boss, _score(kinds, priority), route)
        if best_key is None or key < best_key:
            best, best_key = route, key
    return best, best_key, not pending


def _shown(point, kind):
    return {"col": point[0], "row": point[1], "type": kind}


def _path_stops(path, kinds):
    stops = {}
    for label, index in zip(("first_rest", "first_shop", "shop_after_rest"), _stops(kinds)):
        if index is not None:
            stops["path_" + label] = path[index] | {"steps": index + 1}
    return stops


def _destinations(graph, distances, kind):
    ordered = sorted(distances, key=lambda point: (distances[point], point[1], point[0]))
    return [_shown(point, kind) | {"steps": distances[point]} for point in ordered if graph[point].kind == kind]


def _summary(graph, distances):
    shops = _destinations(graph, distances, "Shop")
    rests = _destinations(graph, distances, "RestSite")
    return {
        "reachable_shop_count": len(shops), "known_shops": shops, "nearest_shop": shops[0] if shops else None,
        "reachable_rest_count": len(rests), "known_rests": rests, "nearest_rest": rests[0] if rests else None,
    }


def _live_routes(snapshot, graph, priority):
    options = []
    actions = snapshot.get("actions")
    if not isinstance(actions, list):
        return options
    for choice, action in enumerate(actions, 1):
        action = _object(action)
        if action.get("kind") != "select_map_node":
            continue
        detail = _object(action.get("detail"))
        point = _coordinate(detail)
        node = graph.get(point)
        kind = _room_type(detail.get("type"))
        option = {"choice": choice, "action_id": action.get("id")}
        if point is not None:
            option["node"] = _shown(point, kind)
        if node is None or (kind != "Unclassified" and node.kind != kind):
            options.append((option, (), False))
            continue
        distances, complete = _reachable(graph, (point,))
        route, score, finished = _representative_route(graph, point, priority)
        option.update(_summary(graph, distances))
        if route is not None:
            kinds = tuple(graph[step].kind for step in route)
            elites, monsters, uncertain = _type_counts(kinds)
            path = [_shown(step, graph[step].kind) for step in route]
            option.update(path=path, reaches_boss=kinds[-1] in BOSS_ROOMS,
                          elites=elites, monsters=monsters, uncertain_rooms=uncertain)
            option.update(_path_stops(path, kinds))
        options.append((option, score, complete and finished and route is not None))
    return options


def route_context(snapshot, map_state=None):
    """Return advice for live choices, or known destinations beyond a confirmed current room.

    For non-map screens, pass a copy of the last observed map with ``act``, ``floor`` and
    ``current`` updated only after a native map action was accepted and the run advanced.
    """
    snapshot = _object(snapshot)
    run = _object(snapshot.get("run"))
    live = snapshot.get("screen") == "map"
    data = _object(snapshot.get("state") if live else map_state)
    if not live and not data:
        return None
    priority = _priority(run)
    result = {"source": "visible_map" if live else "recorded_visible_map", "priority": priority,
              "policy": POLICIES[priority], "coverage": "partial",
              "unknown_rooms": "Unknown rooms may resolve to different encounters. Only marked destinations are counted."}
    if data.get("act") is not None:
        result["act"] = data["act"]
    graph, invalid = _read_graph(data.get("nodes"))
    current = _coordinate(data.get("current"))
    floor = data.get("floor")
    if current is not None and type(floor) is int:
        result["floor_offset"] = floor - current[1]
    if live:
        options = _live_routes(snapshot, graph, priority)
        complete = bool(options) and not invalid and all(option[2] for option in options)
        if complete:
            options.sort(key=lambda option: (option[1], option[0]["choice"]))
            result["coverage"] = "complete"
        else:
            result["reason"] = "Some visible route links or legal choices are missing. Use the listed choices without assuming a full route or a guaranteed destination."
        result["ranked_choices"] = [option[0] for option in options]
        return result
    if (type(run.get("act")) is not int or type(run.get("floor")) is not int or run["act"] != data.get("act")
            or run["floor"] != floor or current not in graph):
        result["reason"] = "The last visible map does not confirm the current room. Future destinations are unavailable."
        return result
    here = graph[current]
    distances, complete = _reachable(graph, here.children)
    if not here.children and here.kind in BOSS_ROOMS:
        complete = True
    result.update(_summary(graph, distances))
    if complete and not invalid and not here.incomplete:
        result["coverage"] = "complete"
    else:
        result["reason"] = "Only confirmed visible destinations are listed. Unseen routes can contain other rooms."
    return result
