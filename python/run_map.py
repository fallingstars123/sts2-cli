"""Read archived chapters and render their paths in the desktop launcher."""

import json
from hashlib import blake2s
from math import hypot
from tkinter import Canvas, ttk
from typing import NamedTuple


KINDS = {"monster": "battle", "elite": "elite", "boss": "boss", "restsite": "rest",
         "shop": "shop", "treasure": "chest", "event": "event", "unknown": "event", "ancient": "start"}
COLORS = {"battle": "#F29F95", "elite": "#F0AA7E", "boss": "#F8D393", "chest": "#F5CB7E",
          "rest": "#E3B9F5", "shop": "#9CCAF4", "event": "#A7B8DC", "start": "#9EDCCA"}
LEGEND_ROOMS = ("event", "shop", "chest", "rest", "battle", "elite", "boss", "start")
MAP_BACKGROUND = "#1D2725"
NODE_SIZES = {"elite": 25, "boss": 48, "start": 30}


class Chapter(NamedTuple):
    name: object
    full: bool
    nodes: dict
    edges: list
    art: dict
    columns: int
    current: tuple | None
    special_art: dict


def coordinate(value):
    if isinstance(value, dict):
        col, row = value.get("col"), value.get("row")
        if type(col) is int and type(row) is int and 0 <= col <= 30 and 0 <= row <= 60:
            return col, row
    return None


def scene_records(folder):
    scenes = {}
    for path in sorted(folder.glob("*/scene.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (isinstance(data, dict) and type(data.get("act")) is int and type(data.get("floor")) is int
                and isinstance(data.get("room"), str) and data["room"] in COLORS):
            scenes.setdefault(data["act"], []).append((path.parent, data))
    return scenes


def read_chapters(folder, records):
    if not folder:
        return {}
    snapshots, visited, traces = {}, {}, {}
    pending = None
    for record in records(folder):
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        if record.get("type") == "action" and data.get("cmd") == "action":
            pending = coordinate(data.get("args")) if data.get("action") == "select_map_node" else None
        if record.get("type") != "state":
            continue
        ctx = data.get("context")
        if not isinstance(ctx, dict) or type(ctx.get("act")) is not int:
            pending = None
            continue
        act = ctx["act"]
        if data.get("type") == "map" and isinstance(data.get("rows"), list) and data["rows"]:
            snapshots[act] = data
            position = coordinate(data.get("current_coord"))
            if isinstance(data.get("visited_path"), list):
                traces[act] = [point for item in data["visited_path"] if (point := coordinate(item)) is not None]
        elif data.get("decision"):
            position = coordinate(ctx.get("map_coord")) or pending
        else:
            pending = None
            continue
        if position and type(ctx.get("floor")) is int:
            visited.setdefault(act, {})[position] = ctx["floor"]
            trace = traces.setdefault(act, [])
            if not trace or trace[-1] != position:
                trace.append(position)
        pending = None

    scenes = scene_records(folder)
    chapters = {}
    for act in sorted(snapshots.keys() | scenes.keys()):
        snapshot = snapshots.get(act, {})
        nodes, edges = {}, set()
        floors = visited.get(act, {})
        rooms = {data["floor"]: (path, data) for path, data in scenes.get(act, [])}
        raw = {point: item for row in snapshot.get("rows", []) if isinstance(row, list)
               for item in row if (point := coordinate(item)) is not None}
        specials = (snapshot.get("start"), snapshot.get("boss"), snapshot.get("second_boss"))
        for item in specials:
            if (point := coordinate(item)) is not None:
                raw[point] = {**raw.get(point, {}), **item}
        trace = [point for point in traces.get(act, ()) if point in raw]
        traveled = set(trace)
        for point, item in raw.items():
            floor = floors.get(point, point[1] + 1)
            logged = point in traveled or item.get("visited") is True or item.get("current") is True
            scene_path, scene = rooms.get(floor, (None, {})) if logged else (None, {})
            kind = item.get("type")
            room = KINDS.get(kind.casefold(), "event") if isinstance(kind, str) else "event"
            if room == "event":
                room = scene.get("room", room)
            nodes[point] = (room, floor, logged, scene_path)
            children = item.get("children")
            if isinstance(children, list):
                edges.update((point, target) for child in children if (target := coordinate(child)) and target != point)
        full = bool(nodes)
        if not full:
            for index, (path, scene) in enumerate(scenes.get(act, [])):
                nodes[0, index] = (scene["room"], scene["floor"], True, path)
                if index:
                    edges.add(((0, index - 1), (0, index)))
        # A legacy archive may start midway through an act with only visit flags for earlier rooms.
        first_row = trace[0][1] if trace else float("inf")
        earlier = sorted((point for point, node in nodes.items() if node[2] and point not in traveled
                          and point[1] < first_row), key=lambda point: (point[1], point[0]))
        route = earlier + trace
        actual = set(zip(route, route[1:]))
        name = snapshot.get("context", {}).get("act_name")
        boss = snapshot.get("boss")
        boss_id = boss.get("id") if isinstance(boss, dict) and isinstance(boss.get("id"), str) else None
        ancient_id = snapshot.get("ancient_id")
        art = {"boss": boss_id, "start": ancient_id if isinstance(ancient_id, str) else None}
        special_art = {point: item.get("id") for item in specials[1:]
                       if (point := coordinate(item)) is not None and isinstance(item.get("id"), str)}
        columns = snapshot.get("column_count")
        minimum_columns = max((col for col, _ in nodes), default=0) + 1
        columns = max(columns, minimum_columns) if type(columns) is int and 0 < columns <= 31 else minimum_columns
        chapters[act] = Chapter(name, full, nodes,
                                [(p, q, (p, q) in actual) for p, q in sorted(edges) if p in nodes and q in nodes],
                                art, columns, route[-1] if route else None, special_art)
    return chapters


class RunMap:
    def __init__(self, parent, launcher, records, open_room):
        self.launcher, self.records, self.open_room = launcher, records, open_room
        self.folder = self.scene_folder = self.act = self.selected = None
        self.seed = ""
        self.focus_route = True
        self.chapters = {}
        self.chapter_ids = []
        filters = ttk.Frame(parent, padding=(0, 0, 0, 8))
        filters.pack(fill="x")
        self.acts = ttk.Combobox(filters, state="readonly", width=29, font=launcher.fonts["body"])
        self.acts.pack(side="left")
        self.acts.bind("<<ComboboxSelected>>", self.switch_act)
        self.tip = ttk.Label(filters, style="Caption.TLabel")
        self.tip.pack(side="left", padx=12)
        filters.bind("<Configure>", lambda e: self.tip.configure(wraplength=max(85, e.width - self.acts.winfo_width() - 24)))
        view = ttk.Frame(parent)
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(0, weight=1)
        graph = ttk.Frame(view)
        graph.grid(row=0, column=0, sticky="nsew")
        self.canvas = Canvas(graph, background=MAP_BACKGROUND, highlightthickness=0, width=300, height=400)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(graph, orient="vertical", command=self.canvas.yview, style="History.Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.bind("<Configure>", self.draw)
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-int(e.delta / 120), "units"))
        self.legend = Canvas(view, width=1, height=53, background=MAP_BACKGROUND, highlightthickness=0)
        self.legend.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self.legend_at_side = False
        self.legend.bind("<Configure>", self.draw_legend)
        view.bind("<Configure>", self.fit_legend)
        actions = ttk.Frame(parent, padding=(0, 7, 0, 0))
        actions.pack(side="bottom", fill="x")
        view.pack(fill="both", expand=True)
        self.selection = ttk.Label(actions, style="Caption.TLabel")
        self.selection.pack(side="left")
        self.room_button = ttk.Button(actions, command=self.show_room)
        self.room_button.pack(side="right")

    def fit_legend(self, event):
        side = event.width >= 542
        if side == self.legend_at_side:
            return
        self.legend_at_side = side
        if side:
            self.legend.configure(width=150, height=251, background="#253330")
            self.legend.grid(row=0, column=1, sticky="n", padx=(9, 0), pady=(0, 0))
        else:
            self.legend.configure(width=1, height=53, background=MAP_BACKGROUND)
            self.legend.grid(row=1, column=0, sticky="ew", padx=(0, 0), pady=(3, 0))

    def text(self, key, **values):
        return self.launcher.text(key, **values)

    def set_run(self, folder, scene_folder, scene, seed=None):
        changed = folder != self.folder
        select_scene = scene_folder != self.scene_folder or changed
        previous_act = self.act
        self.folder = folder
        self.scene_folder = scene_folder
        self.seed = seed if isinstance(seed, str) else ""
        self.launcher.art.refresh()
        self.chapters = read_chapters(folder, self.records)
        self.chapter_ids = sorted(self.chapters)
        labels = []
        for act in self.chapter_ids:
            name = self.chapters[act][0]
            if isinstance(name, dict):
                language = "zh" if self.launcher.language in ("zh", "zh-TW") else "en"
                name = name.get(language) or name.get("en")
            label = self.text("map_act", act=act)
            labels.append(f"{label} · {name}" if isinstance(name, str) and name else label)
        self.acts.configure(values=labels)
        if not labels:
            self.act = self.selected = None
            self.acts.set("")
            self.acts.state(["disabled"])
        else:
            self.acts.state(["!disabled", "readonly"])
            if changed or self.act not in self.chapters:
                self.act = self.chapter_ids[-1]
                self.selected = None
            if select_scene and scene and scene.get("act") in self.chapters:
                self.act = scene["act"]
                self.selected = next((p for p, data in self.chapters[self.act][2].items() if data[3] == scene_folder), None)
            self.acts.current(self.chapter_ids.index(self.act))
        self.focus_route |= changed or select_scene or self.act != previous_act
        self.update_labels()
        self.draw()
        self.draw_legend()

    def switch_act(self, _event):
        index = self.acts.current()
        if 0 <= index < len(self.chapter_ids):
            self.act = self.chapter_ids[index]
            self.selected = None
            self.acts.selection_clear()
            self.focus_route = True
            self.update_labels()
            self.draw()
            self.draw_legend()

    def update_labels(self):
        label = self.chapters.get(self.act)
        self.tip.configure(text=self.text("map_full_hint" if label and label[1] else "map_archive_hint") if label else "")
        node = label[2].get(self.selected) if label else None
        self.selection.configure(text=(f"{self.text('map_floor', floor=node[1])} · {self.room_name(node[0])}"
                                       if node else ""))
        self.room_button.configure(text=self.text("map_open_room"))
        self.room_button.state(["!disabled"] if node and node[3] else ["disabled"])

    def room_name(self, room):
        return self.text("map_start" if room == "start" else "room_" + room)

    def select_node(self, point):
        self.selected = point
        self.update_labels()
        self.draw()

    def show_room(self):
        node = self.chapters.get(self.act, (None, None, {}, []))[2].get(self.selected)
        if node and node[3]:
            self.open_room(node[3])

    def draw(self, _event=None):
        view = self.canvas
        view.delete("all")
        width, height = view.winfo_width(), view.winfo_height()
        if width < 100 or height < 50:
            return
        chapter = self.chapters.get(self.act)
        if not chapter or not chapter.nodes:
            view.create_text(width / 2, height / 2, text=self.text("map_empty"), fill="#AAC0B5",
                             font=self.launcher.fonts["body"], width=width - 30)
            view.configure(scrollregion=(0, 0, width, height))
            return
        nodes = chapter.nodes
        rows = {row for _, row in nodes}
        first, last = min(rows), max(rows)
        step_y = 63
        content_height = max(height, step_y * (last - first) + 124)
        step_x = min(70, max(0, width - 85) / max(1, chapter.columns - 1))
        top = (content_height - step_y * (last - first)) / 2
        ys = {row: top + step_y * (last - row) for row in rows}
        positions = {}
        for (col, row), node in nodes.items():
            dx = dy = 0
            if chapter.full and node[0] not in ("start", "boss"):
                a, b = blake2s(f"{self.seed}:{self.act}:{col}:{row}".encode(), digest_size=2).digest()
                dx = (a / 255 - .5) * min(33, step_x * .53)
                dy = (b / 255 - .5) * 33
            positions[col, row] = (width / 2 + 12 + (col - (chapter.columns - 1) / 2) * step_x + dx, ys[row] + dy)
        view.configure(scrollregion=(0, 0, width, content_height))
        view.create_line(35, 20, 35, content_height - 20, fill="#2D3E39")
        for row in sorted(rows):
            floor = row if chapter.full else nodes[0, row][1]
            view.create_text(18, ys[row], text=str(floor), fill="#7D9589", font=self.launcher.fonts["small"])
        for left, right, reached in sorted(chapter.edges, key=lambda edge: edge[2]):
            self.draw_path(left, right, positions, chapter, reached)
        current = chapter.current
        for point, (room, _, reached, _) in nodes.items():
            x, y = positions[point]
            tag = f"room_{point[0]}_{point[1]}"
            edge = NODE_SIZES.get(room, 20)
            radius = edge / 2 + 4
            selected = self.selected == point
            ring = "#89C7EE" if current == point else "#F8D393" if selected else "#9ABC8B" if reached else ""
            view.create_oval(x-radius, y-radius, x+radius, y+radius, outline=ring,
                             fill="#293A34" if reached or selected else MAP_BACKGROUND,
                             width=2 if current == point or selected else 1, tags=tag)
            self.icon(room, x, y, tag, edge=edge, detail=chapter.special_art.get(point))
            view.tag_bind(tag, "<Button-1>", lambda _event, point=point: self.select_node(point))
            view.tag_bind(tag, "<Enter>", lambda _event: view.configure(cursor="hand2"))
            view.tag_bind(tag, "<Leave>", lambda _event: view.configure(cursor=""))
        if self.focus_route:
            target = self.selected or current
            if target in positions:
                view.yview_moveto(max(0, (positions[target][1] - height * .57) / content_height))
            else:
                view.yview_moveto(0)
            self.focus_route = False

    def draw_path(self, left, right, positions, chapter, reached):
        x, y = positions[left]
        ex, ey = positions[right]
        dx, dy = ex - x, ey - y
        length = hypot(dx, dy)
        first = NODE_SIZES.get(chapter.nodes[left][0], 20) / 2 + 5
        last = length - NODE_SIZES.get(chapter.nodes[right][0], 20) / 2 - 5
        if first >= last:
            return
        ux, uy = dx / length, dy / length
        count = max(1, round((last - first) / 8))
        spacing = (last - first) / count
        seed = left[0] * 17 + left[1] * 5 + right[0] * 13 + right[1] * 3
        color = "#C9EEAB" if reached else "#6A8679"
        for index in range(count):
            phase = (seed + index * 7) % 11
            start = first + index * spacing + spacing * (.15 + phase / 55)
            end = min(last, start + spacing * (.36 + phase / 44))
            offset = (phase - 5) * .17
            self.canvas.create_line(x + ux * start - uy * offset, y + uy * start + ux * offset,
                                    x + ux * end - uy * offset, y + uy * end + ux * offset,
                                    fill=color, width=2 if reached else 1, capstyle="round",
                                    tags="route" if reached else "path")

    def draw_legend(self, _event=None):
        view = self.legend
        view.delete("all")
        if not self.chapters:
            return
        font = self.launcher.fonts["small"]
        if self.legend_at_side:
            view.create_text(13, 17, text=self.text("map_legend"), fill="#D8E4DB",
                             font=self.launcher.fonts["small_bold"], anchor="w")
            view.create_line(12, 31, 138, 31, fill="#435953")
            for index, room in enumerate(LEGEND_ROOMS):
                y = 47 + 26 * index
                self.icon(room, 22, y, "legend", view)
                view.create_text(40, y, text=self.room_name(room), width=104, fill="#AAC0B5", font=font, anchor="w")
            return
        width = view.winfo_width()
        x, y = 15, 13
        for room in LEGEND_ROOMS:
            label = self.room_name(room)
            size = font.measure(label) + 30
            if x + size > width and x > 15:
                x, y = 15, y + 17
            self.icon(room, x, y, "legend", view)
            view.create_text(x + 12, y, text=label, fill="#AAC0B5", font=font, anchor="w")
            x += size

    def icon(self, room, x, y, tag, canvas=None, edge=15, detail=None):
        canvas, color = canvas or self.canvas, COLORS[room]
        chapter = self.chapters.get(self.act)
        detail = detail or (chapter.art.get(room) if chapter else None)
        image = self.launcher.art.room_icon(room, detail, (edge, edge))
        if image:
            canvas.create_image(x, y, image=image, tags=tag)
            return

        scale = edge / 15

        def shape(*coords):
            return [origin + value * scale for origin, value in zip((x, y) * (len(coords) // 2), coords)]

        if room == "battle":
            canvas.create_line(*shape(-4, -5, 4, 4, -1, 4), fill=color, width=2, tags=tag)
            canvas.create_line(*shape(4, -5, -4, 4, 1, 4), fill=color, width=2, tags=tag)
        elif room in ("elite", "boss"):
            if room == "elite":
                canvas.create_polygon(*shape(-5, 0, 0, -5, 5, 0, 0, 5), fill=color, tags=tag)
            else:
                canvas.create_polygon(*shape(-5, 3, -6, -4, -2, -1, 0, -6, 2, -1, 6, -4, 5, 3),
                                      fill=color, tags=tag)
        elif room == "chest":
            canvas.create_rectangle(*shape(-5, -4, 5, 4), outline=color, tags=tag)
            canvas.create_line(*shape(-5, 0, 5, 0), fill=color, tags=tag)
            canvas.create_line(*shape(0, -1, 0, 2), fill=color, width=2, tags=tag)
        elif room == "rest":
            canvas.create_polygon(*shape(0, -6, 5, 1, 2, 5, -3, 5, -5, 1, -2, -3, -1, 2),
                                  fill=color, tags=tag)
        else:
            symbol = {"shop": "$", "event": "?", "start": "●"}[room]
            canvas.create_text(x, y-1, text=symbol, fill=color, font=self.launcher.fonts["small_bold"], tags=tag)
