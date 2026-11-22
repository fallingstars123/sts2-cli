import builtins
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from string import Formatter
import importlib.util
import json
import os
from pathlib import Path
from queue import Empty, SimpleQueue
import re
import runpy
import shutil
import subprocess
import sys
from threading import Thread
from time import sleep
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk
import traceback
from types import SimpleNamespace
from uuid import uuid4
import webbrowser


LAUNCHER = Path(__file__).resolve()
sys.path.insert(0, str(LAUNCHER.parent / "python"))
from character_catalog import CHARACTERS, character_id
from game_art import GameArt

HISTORY_DIR = LAUNCHER.parent / "STS2 Runs"
PREFERENCES_PATH = LAUNCHER.parent / "STS2 Preferences.json"
CHINESE_CHARACTERS = ("铁甲战士", "静默猎手", "故障机器人", "储君", "亡灵契约师", "愚者")
TRADITIONAL_CHARACTERS = ("鐵甲戰士", "靜默獵手", "故障機器人", "儲君", "亡靈契約師", "愚者")
INTERFACE_LANGUAGES = {"zh": "简体中文", "en": "English"}
PROVIDERS = {
    "DeepSeek": ("openai", "https://api.deepseek.com", "OPENAI_API_KEY"),
    "Claude": ("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY"),
}
TEXT = {
    "zh": {
        "title": "杀戮尖塔 2",
        "window": "杀戮尖塔 2 · 启动器",
        "manual": "手动游玩",
        "character": "角色",
        "ascension": "进阶",
        "model": "模型",
        "key": "API 密钥",
        "test": "试跑 20 步",
        "load": "读取存档",
        "start": "启动对局",
        "running": "对局正在终端中运行。",
        "installing": "安装完成后，关闭安装窗口即可启动对局。",
        "finished": "终端已关闭，可以启动下一局。",
        "missing_key": "请在 API 设置里保存 {provider} 的密钥。",
        "missing_sdk": "当前 Python 缺少 {package}。要打开安装窗口吗？",
        "missing_dotnet": "找不到 dotnet，请先安装 .NET 9 SDK。",
        "missing_python": "找不到 python.exe。",
        "pick_project": "选择 sts2-cli 项目目录",
        "bad_project": "请选择包含 python/play.py 和 agent/llm_agent.py 的 sts2-cli 目录。",
        "save_file": "游戏存档",
        "bad_save": "无法读取此存档。请选择有效的 .save 或对局回放 .json 文件。",
        "close_console": "按回车关闭此窗口…",
        "history": "对局记录",
        "refresh": "刷新",
        "open_folder": "打开文件夹",
        "no_runs": "从启动器开一局，过程就会显示在这里。",
        "no_transcript": "这局还没有可显示的记录。",
        "player": "玩家",
        "step": "第 {step} 步 · HP {hp}",
        "reason": "理由",
        "status_partial": "未结束",
        "status_ended": "已停止",
        "status_error": "异常退出",
        "status_victory": "胜利",
        "status_defeat": "战败",
        "offline": "离线代理",
        "scene": "第 {act} 幕 · {floor} 层 · {room}",
        "relics_found": "获得遗物：{relics}",
        "entered": "进入：{scene}",
        "record_tab": "过程",
        "analysis_tab": "分析",
        "map_tab": "地图",
        "map_legend": "房间图例",
        "map_act": "第 {act} 幕",
        "map_floor": "第 {floor} 层",
        "map_start": "出发点",
        "map_full_hint": "亮线和圆圈标出已走路线 · 点击节点查看房间",
        "map_archive_hint": "历史记录仅保存了到访房间",
        "map_open_room": "查看房间记录",
        "map_empty": "此对局暂无地图记录。",
        "about": "关于",
        "wiki": "角色百科",
        "latest_hp": "最近记录血量",
        "live_hp": "实时血量",
        "inventory_deck": "牌组",
        "inventory_relics": "遗物",
        "inventory_empty": "这局没有记录该列表。",
        "resource_gold": "金币",
        "resource_block": "格挡",
        "resource_energy": "能量",
        "resource_potions": "药水",
        "observed_rate": "实测 AI 胜率",
        "finished_ai": "AI 已分胜负",
        "stage_estimate": "本局历史估算",
        "wins_sample": "{wins} 胜 / {total} 局",
        "wins_losses": "{wins} 胜 · {losses} 负",
        "no_estimate": "暂无匹配样本",
        "no_selected_run": "请先选择一局",
        "provider_rates": "按服务商统计",
        "trend": "本局走势",
        "health": "血量比例",
        "estimate_line": "历史估算",
        "action_axis": "{total} 次操作",
        "no_chart": "暂无对局状态",
        "ai_notes": "AI 决策说明",
        "no_notes": "这局暂无 AI 决策说明。",
        "plan_direction": "当前打法",
        "plan_priorities": "优先补强",
        "plan_pivot": "转向条件",
        "rate_scope": "估算使用同模型、角色和进阶，并到达同进度的历史完赛局。",
        "expression": "开启表达",
        "identity_settings": "编辑身份卡",
        "persona_panel": "人物面板",
        "new_identity": "新建人物",
        "ai_character": "AI 人物",
        "name_required": "请给这个人物起个名字。",
        "ai_play": "AI 游玩",
        "provider": "服务商",
        "speaker_name": "AI 称呼",
        "output_language": "发言语言",
        "identity_card": "语气和身份设定",
        "save_profile": "保存",
        "chat_title": "AI 对话",
        "no_chat": "AI 有发言时会显示在这里。",
        "chat_step": "第 {step} 步",
        "live_profile": "表达设置下次决策生效，对局设置下局生效。",
        "run_preview": "{character} · 进阶 {ascension}",
        "api_settings": "API 设置",
        "save_settings": "存档目录",
        "save_directory": "从这个目录读取存档",
        "save_default": "使用自动查找的目录",
        "browse": "浏览",
        "invalid_save_directory": "找不到这个目录。请输入一个存在的文件夹。",
        "choose_save": "选择存档",
        "no_saves": "这个目录没有可继续的存档",
        "home": "启动",
        "key_storage": "密钥存于当前 Windows 账户。留空保留已有密钥。",
        "refresh_models": "刷新模型",
        "loading_models": "正在读取模型列表…",
        "model_count": "已读取 {total} 个模型",
        "full_run": "整局",
        "interface_language": "界面语言",
        "default_speech": "默认发言语言",
        "follow_interface": "跟随界面语言",
        "follow_default": "跟随默认发言语言",
    },
    "en": {
        "title": "Slay the Spire 2",
        "window": "Slay the Spire 2 · Launcher",
        "manual": "Manual",
        "character": "Character",
        "ascension": "Ascension",
        "model": "Model",
        "key": "API key",
        "test": "Test 20 steps",
        "load": "Load save",
        "start": "Start run",
        "running": "The run is open in a terminal window.",
        "installing": "Close the installer window when it finishes, then start a run.",
        "finished": "Terminal closed. Ready for the next run.",
        "missing_key": "Save the API key for {provider} in API settings.",
        "missing_sdk": "This Python installation is missing {package}. Open the installer?",
        "missing_dotnet": "dotnet was not found. Install the .NET 9 SDK.",
        "missing_python": "python.exe was not found.",
        "pick_project": "Select the sts2-cli project folder",
        "bad_project": "Select the sts2-cli folder containing python/play.py and agent/llm_agent.py.",
        "save_file": "Game saves",
        "bad_save": "This save could not be read. Select a valid .save file or .json replay.",
        "close_console": "Press Enter to close this window…",
        "history": "Run history",
        "refresh": "Refresh",
        "open_folder": "Open folder",
        "no_runs": "Start a run from the launcher to see it here.",
        "no_transcript": "There is no transcript to show yet.",
        "player": "Player",
        "step": "Step {step} · HP {hp}",
        "reason": "Reason",
        "status_partial": "In progress or interrupted",
        "status_ended": "Ended",
        "status_error": "Exited with an error",
        "status_victory": "Victory",
        "status_defeat": "Defeat",
        "offline": "Offline agent",
        "scene": "Act {act} · Floor {floor} · {room}",
        "relics_found": "Relics gained: {relics}",
        "entered": "Entered: {scene}",
        "record_tab": "Transcript",
        "analysis_tab": "Analysis",
        "map_tab": "Map",
        "map_legend": "Room legend",
        "map_act": "Act {act}",
        "map_floor": "Floor {floor}",
        "map_start": "Start",
        "map_full_hint": "Bright lines and rings show your route. Select a room for details.",
        "map_archive_hint": "This archive contains visited rooms only.",
        "map_open_room": "Open room record",
        "map_empty": "There is no recorded map for this run.",
        "about": "About",
        "wiki": "Character wiki",
        "latest_hp": "Last recorded HP",
        "live_hp": "Live HP",
        "inventory_deck": "Deck",
        "inventory_relics": "Relics",
        "inventory_empty": "This run has no recorded items here.",
        "resource_gold": "Gold",
        "resource_block": "Block",
        "resource_energy": "Energy",
        "resource_potions": "Potions",
        "observed_rate": "Observed AI win rate",
        "finished_ai": "Finished AI runs",
        "stage_estimate": "Historical run estimate",
        "wins_sample": "{wins} wins / {total} runs",
        "wins_losses": "{wins} wins · {losses} losses",
        "no_estimate": "No matching runs yet",
        "no_selected_run": "Select a run",
        "provider_rates": "By provider",
        "trend": "Run trends",
        "health": "Health %",
        "estimate_line": "Historical estimate",
        "action_axis": "{total} actions",
        "no_chart": "No recorded states",
        "ai_notes": "AI decision notes",
        "no_notes": "No AI decision notes for this run.",
        "plan_direction": "Direction",
        "plan_priorities": "Priorities",
        "plan_pivot": "When to pivot",
        "rate_scope": "Estimate uses prior finished runs with the same model, character and ascension that reached this progress.",
        "expression": "Enable commentary",
        "identity_settings": "Edit persona",
        "persona_panel": "Persona panel",
        "new_identity": "New persona",
        "ai_character": "AI persona",
        "name_required": "Enter a name for this persona.",
        "ai_play": "AI play",
        "provider": "Provider",
        "speaker_name": "AI display name",
        "output_language": "Commentary language",
        "identity_card": "Persona and voice",
        "save_profile": "Save",
        "chat_title": "AI chat",
        "no_chat": "AI comments will appear here when it chooses to speak.",
        "chat_step": "Step {step}",
        "live_profile": "Commentary settings apply next decision. Run settings apply next run.",
        "run_preview": "{character} · Ascension {ascension}",
        "api_settings": "API settings",
        "save_settings": "Save folder",
        "save_directory": "Load saves from this folder",
        "save_default": "Use detected folder",
        "browse": "Browse",
        "invalid_save_directory": "Folder not found. Enter an existing folder.",
        "choose_save": "Select a save",
        "no_saves": "No playable saves in this folder",
        "home": "Play",
        "key_storage": "Keys are stored in your Windows account. Blank fields keep the saved key.",
        "refresh_models": "Refresh models",
        "loading_models": "Loading models…",
        "model_count": "Loaded {total} models",
        "full_run": "Full run",
        "interface_language": "Interface language",
        "default_speech": "Default commentary language",
        "follow_interface": "Follow interface language",
        "follow_default": "Follow default commentary language",
    },
}

BACKGROUND = "#151C1B"
PANEL = "#202A28"
FIELD = "#293633"
HOVER = "#354541"
BORDER = "#3B4D47"
TEXT_COLOR = "#F0F6F2"
MUTED = "#AAC0B5"
ACCENT = "#C9EEAB"
ACCENT_HOVER = "#DCF7C5"
BLUE = "#89C7EE"
TREE_ROW_HEIGHT = 32
FONT_FAMILIES = {"zh": "Microsoft YaHei UI", "zh-TW": "Microsoft JhengHei UI", "ja": "Yu Gothic UI",
                 "ko": "Malgun Gothic", "hi": "Nirmala UI", "th": "Leelawadee UI", "en": "Segoe UI"}
ROOMS = {
    "battle": ("战斗", "Battle"), "elite": ("精英战", "Elite"), "boss": ("首领战", "Boss"),
    "chest": ("宝箱", "Chest"), "event": ("事件", "Event"), "rest": ("休息点", "Rest site"),
    "shop": ("商店", "Shop"),
}
ROOM_TYPES = {
    "monster": "battle", "elite": "elite", "boss": "boss", "treasure": "chest",
    "event": "event", "restsite": "rest", "rest_site": "rest", "shop": "shop", "merchant": "shop",
}
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
AI_STEP = re.compile(r"^\s*(\d+) HP\s+(\S+) \| (.*?)  -- (.*)$")


def load_interface_locales(path):
    for room, (zh, en) in ROOMS.items():
        TEXT["zh"]["room_" + room] = zh
        TEXT["en"]["room_" + room] = en
    try:
        catalogs = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(catalogs, dict):
        return
    formatter = Formatter()
    expected = {key: {field for _, field, _, _ in formatter.parse(value) if field}
                for key, value in TEXT["en"].items()}
    names = {}
    for code, catalog in catalogs.items():
        if not isinstance(catalog, dict) or not isinstance(catalog.get("label"), str):
            continue
        if code in TEXT:
            names[code] = catalog["label"]
            continue
        strings = catalog.get("strings")
        if not isinstance(strings, dict):
            continue
        try:
            valid = all(isinstance(strings.get(key), str) and strings[key] and
                        fields == {field for _, field, _, _ in formatter.parse(strings[key]) if field}
                        for key, fields in expected.items())
        except ValueError:
            continue
        if valid:
            TEXT[code] = strings
            names[code] = catalog["label"]
    names.update({code: label for code, label in INTERFACE_LANGUAGES.items() if code not in names})
    INTERFACE_LANGUAGES.clear()
    INTERFACE_LANGUAGES.update(names)


load_interface_locales(LAUNCHER.parent / "STS2 Languages.json")


def engine_language(language):
    return "zh" if language in ("zh", "zh-TW") else "en"


def character_names(language):
    return {"zh": CHINESE_CHARACTERS, "zh-TW": TRADITIONAL_CHARACTERS}.get(language, CHARACTERS)


ENTERED_PREFIXES = tuple(strings["entered"].split("{scene}", 1)[0] for strings in TEXT.values())
PLAYER_PREFIXES = tuple(strings["player"] + " ›" for strings in TEXT.values())


def scene_title(language, info):
    room = TEXT[language]["room_" + info["room"]]
    return TEXT[language]["scene"].format(act=info["act"], floor=info["floor"], room=room)


def write_json(path, record):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for delay in (0.01, 0.03, 0.08):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            sleep(delay)
    temporary.replace(path)


def option(options, flag):
    return next((value for name, value in zip(options, options[1:]) if name == flag), "")


class RunArchive:
    def __init__(self, root, language, options):
        self.root = root
        self.language = language
        self.provider = {"openai": "DeepSeek", "anthropic": "Claude", "random": "random"}.get(
            option(options, "--provider"), "manual"
        )
        self.model = option(options, "--model")
        self.secrets = tuple(value for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY") if (value := os.environ.get(name)))
        self.transcript = None
        self.scene = None

    def start(self, character, seed):
        self.finish(0)
        started = datetime.now().astimezone()
        label = character if character in CHARACTERS else "Run"
        self.folder = self.root / f"{started:%Y-%m-%d_%H-%M-%S} {self.provider} {label} {uuid4().hex[:8]}"
        self.folder.mkdir(parents=True)
        self.last_state = {}
        self.last_ai_line = ""
        self.pending_move = None
        self.scene_index = 0
        self.info = {"started": started.isoformat(timespec="seconds"), "status": "partial",
                     "provider": self.provider, "model": self.model, "character": label, "seed": seed,
                     "ascension": None, "last_stage": None, "expression_format": 1}
        if self.provider in PROVIDERS:
            self.info["persona_id"] = os.environ.get("STS2_EXPRESSION_CARD", "")
            self.info["persona_name"] = os.environ.get("STS2_EXPRESSION_NAME", "")
        self.transcript = (self.folder / "transcript.txt").open("w", encoding="utf-8", buffering=1, errors="replace")
        write_json(self.folder / "run.json", self.info)
        return self.folder

    def write(self, value):
        if self.transcript is None:
            return
        value = ANSI.sub("", value)
        for secret in self.secrets:
            value = value.replace(secret, "[redacted]")
        if AI_STEP.fullmatch(value.rstrip("\n")):
            self.last_ai_line = value.rstrip("\n")
        self.transcript.write(value)
        self.transcript.flush()
        if self.scene:
            self.scene["text"].write(value)
            self.scene["text"].flush()

    def observe_action(self, record):
        action = record["data"]
        if action.get("cmd") == "start_run" and type(action.get("ascension")) is int:
            self.info["ascension"] = action["ascension"]
            write_json(self.folder / "run.json", self.info)
        if action.get("action") == "select_map_node":
            args = action.get("args") or {}
            choice = next((c for c in self.last_state.get("choices", [])
                           if c.get("col") == args.get("col") and c.get("row") == args.get("row")), {})
            self.pending_move = (record, choice, self.last_ai_line)
        self.write_scene_record(record)

    def observe_state(self, record):
        state = record["data"]
        context = state.get("context") or {}
        decision = state.get("decision")
        move, self.pending_move = self.pending_move, None
        if decision == "game_over":
            self.info["status"] = "victory" if state.get("victory") else "defeat"

        kind = ROOM_TYPES.get(str(context.get("room_type", "")).lower())
        if decision == "combat_play" and kind not in ("battle", "elite", "boss"):
            kind = "battle"
        if decision == "map_select" and move and str(move[1].get("type", "")).lower() == "treasure":
            kind = "chest"

        if kind and decision and context.get("act") is not None and context.get("floor") is not None:
            location = (context["act"], context["floor"], kind)
            if not self.scene or location != self.scene["location"]:
                self.start_scene(location)
                if move:
                    self.write_scene_record(move[0])
                    if move[2]:
                        self.scene["text"].write(move[2] + "\n")
                if kind == "chest":
                    before = {relic.get("id") or str(relic.get("name")) for relic in self.relics(self.last_state)}
                    gained = [self.relic_name(relic) for relic in self.relics(state)
                              if (relic.get("id") or str(relic.get("name"))) not in before]
                    if gained:
                        line = TEXT[self.language]["relics_found"].format(relics=", ".join(gained))
                        self.write(line + "\n")

        self.write_scene_record(record)
        if decision and context:
            self.last_state = state
            changed = False
            act, floor = context.get("act"), context.get("floor")
            if type(act) is int and type(floor) is int and act > 0 and floor >= 0:
                previous = self.info["last_stage"]
                if previous is None or (act, floor) > (previous["act"], previous["floor"]):
                    self.info["last_stage"] = {"act": act, "floor": floor}
                    changed = True
            player = state.get("player") or {}
            character = character_id(player.get("character_id")) or character_id(player.get("name"))
            if character and character != self.info["character"]:
                self.info["character"] = character
                changed = True
            if changed:
                write_json(self.folder / "run.json", self.info)

    @staticmethod
    def relics(state):
        return [relic for relic in (state.get("player") or {}).get("relics", []) if isinstance(relic, dict)]

    def relic_name(self, relic):
        name = relic.get("name")
        if isinstance(name, dict):
            return name.get(engine_language(self.language)) or name.get("en") or relic.get("id", "?")
        return name or relic.get("id", "?")

    def start_scene(self, location):
        self.close_scene()
        self.scene_index += 1
        act, floor, room = location
        folder = self.folder / f"{self.scene_index:02d} - A{act} F{floor} - {TEXT[self.language]['room_' + room]}"
        folder.mkdir()
        info = {"act": act, "floor": floor, "room": room}
        write_json(folder / "scene.json", info)
        self.scene = {"location": location,
                      "text": (folder / "transcript.txt").open("w", encoding="utf-8", buffering=1, errors="replace"),
                      "records": (folder / "states.jsonl").open("w", encoding="utf-8", buffering=1)}
        heading = TEXT[self.language]["entered"].format(scene=scene_title(self.language, info))
        self.write("\n" + heading + "\n")

    def write_scene_record(self, record):
        if self.scene:
            self.scene["records"].write(json.dumps(record, ensure_ascii=False) + "\n")

    def close_scene(self):
        if self.scene:
            self.scene["text"].close()
            self.scene["records"].close()
            self.scene = None

    def finish(self, exit_code):
        if self.transcript is None:
            return
        self.close_scene()
        self.transcript.close()
        self.transcript = None
        if self.info["status"] == "partial":
            self.info["status"] = "error" if exit_code not in (0, 130) else "ended"
        self.info["ended"] = datetime.now().astimezone().isoformat(timespec="seconds")
        write_json(self.folder / "run.json", self.info)


class RecordedStream:
    def __init__(self, stream, archive):
        self.stream = stream
        self.archive = archive

    def write(self, value):
        self.archive.write(value)
        return self.stream.write(value)

    def __getattr__(self, name):
        return getattr(self.stream, name)


def configure_theme(root):
    fonts = {
        "body": font.Font(root, family=FONT_FAMILIES["zh"], size=11),
        "button": font.Font(root, family=FONT_FAMILIES["zh"], size=11, weight="bold"),
        "small": font.Font(root, family=FONT_FAMILIES["zh"], size=10),
        "small_bold": font.Font(root, family=FONT_FAMILIES["zh"], size=10, weight="bold"),
        "title": font.Font(root, family=FONT_FAMILIES["zh"], size=23, weight="bold"),
    }
    root.configure(background=BACKGROUND)
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT_COLOR)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", BACKGROUND)
    root.option_add("*TCombobox*Listbox.font", fonts["body"])

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background=BACKGROUND)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", font=fonts["body"], foreground=TEXT_COLOR, background=PANEL)
    style.configure("Title.TLabel", font=fonts["title"], foreground=TEXT_COLOR, background=BACKGROUND)
    style.configure("Status.TLabel", font=fonts["small"], foreground=MUTED, background=BACKGROUND)
    style.configure("TButton", font=fonts["body"], padding=(12, 9), background=FIELD,
                    foreground=TEXT_COLOR, bordercolor=BORDER, lightcolor=FIELD,
                    darkcolor=FIELD, relief="flat", focusthickness=2, focuscolor=TEXT_COLOR)
    style.map("TButton", background=[("disabled", PANEL), ("active", HOVER)],
              foreground=[("disabled", MUTED)])
    style.configure("Selected.TButton", font=fonts["button"], background=ACCENT,
                    foreground=BACKGROUND, bordercolor=ACCENT, lightcolor=ACCENT,
                    darkcolor=ACCENT, focuscolor=BACKGROUND)
    style.map("Selected.TButton", background=[("disabled", FIELD), ("active", ACCENT_HOVER)],
              foreground=[("disabled", MUTED), ("!disabled", BACKGROUND)])
    style.configure("Language.TButton", font=fonts["small"], padding=(8, 5))
    style.layout("Gear.TMenubutton", [("Menubutton.border", {"sticky": "nswe", "children": [
        ("Menubutton.padding", {"sticky": "nswe", "children": [("Menubutton.label", {"sticky": "nswe"})]})]})])
    style.configure("Gear.TMenubutton", font=("Segoe UI Symbol", 17), padding=0, foreground=TEXT_COLOR,
                    background=FIELD, bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD, anchor="center")
    style.map("Gear.TMenubutton", background=[("active", HOVER)])
    style.configure("TCombobox", padding=(9, 6), background=FIELD,
                    foreground=TEXT_COLOR, fieldbackground=FIELD, arrowcolor=TEXT_COLOR,
                    bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)],
              foreground=[("readonly", TEXT_COLOR)], bordercolor=[("focus", ACCENT)])
    style.configure("Display.TCombobox", selectbackground=FIELD, selectforeground=TEXT_COLOR)
    style.map("Display.TCombobox", selectbackground=[("readonly", FIELD)],
              selectforeground=[("readonly", TEXT_COLOR)])
    style.configure("TEntry", padding=(9, 6), foreground=TEXT_COLOR, fieldbackground=FIELD,
                    insertcolor=TEXT_COLOR, bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD)
    style.map("TEntry", bordercolor=[("focus", ACCENT)])
    style.configure("TCheckbutton", font=fonts["small"], foreground=MUTED, background=PANEL,
                    indicatorbackground=FIELD, indicatorforeground=BACKGROUND,
                    bordercolor=BORDER, lightcolor=PANEL, darkcolor=PANEL, padding=(0, 4))
    style.map("TCheckbutton", background=[("active", PANEL)],
              indicatorbackground=[("selected", ACCENT)])
    style.configure("History.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT_COLOR,
                    font=fonts["small"], rowheight=TREE_ROW_HEIGHT, borderwidth=0, bordercolor=BORDER,
                    lightcolor=PANEL, darkcolor=PANEL)
    style.map("History.Treeview", background=[("selected", HOVER)], foreground=[("selected", ACCENT)])
    style.configure("History.Vertical.TScrollbar", background=FIELD, troughcolor=BACKGROUND, arrowcolor=MUTED,
                    bordercolor=BACKGROUND, lightcolor=FIELD, darkcolor=FIELD, arrowsize=11)
    style.map("History.Vertical.TScrollbar", background=[("active", HOVER)])
    style.configure("Navigation.TButton", anchor="w", padding=(12, 9), background=PANEL, foreground=MUTED,
                    focusthickness=0, bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
    style.map("Navigation.TButton", background=[("active", HOVER)], bordercolor=[("focus", ACCENT)])
    style.configure("Current.Navigation.TButton", background=FIELD, foreground=ACCENT,
                    bordercolor=FIELD, lightcolor=FIELD, darkcolor=FIELD)
    style.configure("DetailTab.TButton", padding=(16, 8), font=fonts["small_bold"], background=FIELD,
                    foreground=MUTED, bordercolor=FIELD, lightcolor=FIELD, darkcolor=FIELD, focusthickness=0)
    style.map("DetailTab.TButton", background=[("active", HOVER)], bordercolor=[("focus", ACCENT)])
    style.configure("Current.DetailTab.TButton", background=ACCENT, foreground=BACKGROUND,
                    bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
    style.map("Current.DetailTab.TButton", background=[("active", ACCENT_HOVER)])
    style.configure("Metric.TLabel", background=PANEL, foreground=ACCENT, font=fonts["title"])
    style.configure("PlayerName.TLabel", background=PANEL, foreground=TEXT_COLOR, font=fonts["title"])
    style.configure("Caption.TLabel", background=PANEL, foreground=MUTED, font=fonts["small"])
    style.configure("Section.TLabel", background=PANEL, foreground=TEXT_COLOR, font=fonts["button"])
    style.configure("Inventory.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT_COLOR,
                    borderwidth=0, rowheight=27, font=fonts["small"])
    return fonts


class RunInventory:
    def __init__(self, parent, launcher):
        self.launcher = launcher
        self.sections = {}
        self.expanded = set()
        self.player = {}
        self.polling = False
        area = ttk.Frame(parent)
        area.pack(fill="x", pady=(7, 0))
        area.grid_columnconfigure((0, 1), weight=1, uniform="inventory")
        for column, kind in enumerate(("deck", "relics")):
            panel = ttk.Frame(area, style="Panel.TFrame")
            panel.grid(row=0, column=column, sticky="new", padx=(0, 6 if column == 0 else 0))
            button = ttk.Button(panel, style="Language.TButton", compound="left",
                                command=lambda kind=kind: self.toggle(kind))
            button.pack(fill="x", anchor="n")
            body = ttk.Frame(panel, style="Panel.TFrame", padding=(4, 3))
            table = ttk.Treeview(body, show="tree", columns=("count",), height=4, style="Inventory.Treeview",
                                 selectmode="none")
            table.column("#0", width=145, stretch=True)
            table.column("count", width=44, minwidth=40, stretch=False, anchor="e")
            table.pack(side="left", fill="both", expand=True)
            bar = ttk.Scrollbar(body, orient="vertical", command=table.yview, style="History.Vertical.TScrollbar")
            bar.pack(side="right", fill="y")
            table.configure(yscrollcommand=bar.set)
            self.sections[kind] = (button, body, table)
        self.signatures = {}
        self.counts = {}

    def toggle(self, kind):
        body = self.sections[kind][1]
        if kind in self.expanded:
            self.expanded.remove(kind)
            body.pack_forget()
        else:
            self.expanded.add(kind)
            body.pack(fill="x", expand=True)
        self.update(self.player)

    def set_button(self, kind):
        count = self.counts.get(kind)
        label = self.launcher.text("inventory_" + kind)
        prefix = "▾" if kind in self.expanded else "▸"
        image = self.launcher.art.resource_icon("deck", "", (15, 15)) if kind == "deck" else None
        self.sections[kind][0].configure(text=f"{prefix}  {label}" + (f"  ({count})" if count is not None else ""),
                                         image=image or "")

    def update(self, player):
        self.player = player
        art = self.launcher.art
        wiki = art.wiki_cards
        language = engine_language(self.launcher.language)
        for kind, (_, _, table) in self.sections.items():
            items = player.get(kind)
            self.counts[kind] = len(items) if isinstance(items, list) else player.get("deck_size") if kind == "deck" else None
            self.set_button(kind)
            if kind not in self.expanded:
                continue
            rows = Counter()
            for item in items if isinstance(items, list) else ():
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                english = name.get("en", "") if isinstance(name, dict) else name
                label = name.get(language) or english if isinstance(name, dict) else name
                identifier = item.get("id")
                if not isinstance(identifier, str):
                    identifier = re.sub(r"[^a-z0-9]+", "_", english.casefold()).strip("_") if isinstance(english, str) else ""
                if not isinstance(label, str) or not label:
                    label = identifier.rsplit(".", 1)[-1].replace("_", " ").title()
                if not label:
                    continue
                if item.get("upgraded") and not label.endswith("+"):
                    label += "+"
                variant = None
                if kind == "deck":
                    properties = [item.get(key) for key in ("pool", "rarity", "type")]
                    variant = art.card_variant(identifier, *(value if isinstance(value, str) else "" for value in properties))
                rows[identifier, label, variant] += 1
            if kind == "deck":
                wiki.request(variant for _, _, variant in rows)
            signature = (self.launcher.language, tuple(rows.items()), wiki.revision if kind == "deck" else None)
            if self.signatures.get(kind) == signature:
                continue
            self.signatures[kind] = signature
            scroll = table.yview()[0]
            table.delete(*table.get_children())
            for (identifier, label, variant), copies in rows.items():
                icon = art.card_icon(variant, (22, 23)) if variant else art.relic_icon(identifier, (22, 22))
                table.insert("", "end", text=label if icon else "◇  " + label,
                             image=icon or "", values=(f"×{copies}",))
            if not rows:
                table.insert("", "end", text=self.launcher.text("inventory_empty"))
            table.configure(height=min(5, max(1, len(rows))))
            table.yview_moveto(scroll)
        if wiki.pending and not self.polling:
            self.polling = True
            self.launcher.root.after(120, self.poll_cards)

    def poll_cards(self):
        self.polling = False
        self.launcher.art.wiki_cards.poll()
        self.update(self.player)


class RunAnalysis:
    def __init__(self, parent, launcher):
        self.launcher = launcher
        module = launcher.project / "agent" / "run_stats.py"
        self.stats = SimpleNamespace(**runpy.run_path(str(module))) if module.is_file() else None
        self.character = ""
        self.hp_ratio = None
        self.provider_rates = []
        self.timeline = []
        self.metrics = []
        area = ttk.Frame(parent, padding=(6, 7, 6, 0))
        area.pack(fill="both", expand=True)

        player = ttk.Frame(area, style="Panel.TFrame", padding=(12, 10))
        player.pack(fill="x")
        self.portrait_view = tk.Canvas(player, width=106, height=136, bg=FIELD, highlightthickness=1,
                                       highlightbackground=BORDER)
        self.portrait_view.pack(side="left", padx=(0, 15))
        card = ttk.Frame(player, style="Panel.TFrame")
        card.pack(side="left", fill="both", expand=True)
        name_row = ttk.Frame(card, style="Panel.TFrame")
        name_row.pack(fill="x")
        self.player_name = ttk.Label(name_row, style="PlayerName.TLabel")
        self.player_name.pack(side="left")
        self.wiki = tk.Label(name_row, bg=PANEL, fg=BLUE, font=launcher.fonts["small"], cursor="hand2")
        self.wiki.pack(side="right")
        self.wiki.bind("<Button-1>", self.open_wiki)
        self.player_progress = ttk.Label(card, style="Caption.TLabel", compound="left")
        self.player_progress.pack(anchor="w")
        health_row = ttk.Frame(card, style="Panel.TFrame")
        health_row.pack(fill="x", pady=(6, 2))
        self.hp_caption = ttk.Label(health_row, style="Caption.TLabel", compound="left")
        self.hp_caption.pack(side="left")
        self.player_hp = ttk.Label(health_row, style="Section.TLabel")
        self.player_hp.pack(side="right")
        self.health_bar = tk.Canvas(card, bg=FIELD, width=1, height=8, highlightthickness=0)
        self.health_bar.pack(fill="x")
        self.health_bar.bind("<Configure>", self.draw_player_health)
        self.recent_hp = tk.Canvas(card, bg=PANEL, width=1, height=24, highlightthickness=0)
        self.recent_hp.pack(fill="x", pady=(3, 2))
        self.recent_hp.bind("<Configure>", self.draw_player_health)
        resources = ttk.Frame(card, style="Panel.TFrame")
        resources.pack(fill="x", pady=(1, 0))
        self.resource_labels = {}
        for index, key in enumerate(("gold", "block", "potions", "energy")):
            badge = ttk.Label(resources, style="Caption.TLabel", compound="left")
            badge.grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 16))
            self.resource_labels[key] = badge
        self.inventory = RunInventory(area, launcher)

        summary = ttk.Frame(area)
        summary.pack(fill="x", pady=(7, 0))
        summary.grid_columnconfigure((0, 1, 2), weight=1, uniform="metrics")
        for column in range(3):
            panel = ttk.Frame(summary, style="Panel.TFrame", padding=(10, 7))
            panel.grid(row=0, column=column, sticky="nsew", padx=(0, 6 if column < 2 else 0))
            caption = ttk.Label(panel, style="Caption.TLabel")
            value = ttk.Label(panel, style="Metric.TLabel")
            detail = ttk.Label(panel, style="Caption.TLabel")
            for widget in (caption, value, detail):
                widget.pack(anchor="w")
            self.metrics.append((caption, value, detail))

        self.trend = tk.Canvas(area, height=135, bg=PANEL, highlightthickness=0)
        self.trend.pack(fill="x", pady=(7, 0))
        self.trend.bind("<Configure>", self.draw_trend)

        detail = ttk.Frame(area)
        detail.pack(fill="both", expand=True, pady=(7, 0))
        detail.grid_columnconfigure((0, 1), weight=1, uniform="details")
        detail.grid_rowconfigure(0, weight=1)
        notes = ttk.Frame(detail, padding=(10, 7), style="Panel.TFrame")
        notes.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.bars = tk.Canvas(detail, width=1, height=93, bg=PANEL, highlightthickness=0)
        self.bars.grid(row=0, column=1, sticky="nsew")
        self.bars.bind("<Configure>", self.draw_bars)
        self.notes_title = ttk.Label(notes, style="Section.TLabel")
        self.notes_title.pack(anchor="w")
        self.notes = tk.Text(notes, bg=PANEL, fg=TEXT_COLOR, font=launcher.fonts["small"],
                             wrap="word", padx=0, pady=6, highlightthickness=0, relief="flat",
                             height=1, width=1, state="disabled", selectbackground=BORDER)
        self.notes.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(notes, orient="vertical", command=self.notes.yview,
                               style="History.Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        self.notes.configure(yscrollcommand=scroll.set)
        self.notes.tag_configure("muted", foreground=MUTED, spacing3=6)
        self.notes.tag_configure("plan", foreground=ACCENT)

    def text(self, key, **values):
        return self.launcher.text(key, **values)

    def metrics_for(self, folder, info, archive_root):
        complete = self.stats.completed_runs(archive_root) if self.stats else []
        groups = {provider: [run for run in complete if run.get("provider") == provider] for provider in PROVIDERS}
        self.provider_rates = [(provider, *(self.stats.win_counts(games) if self.stats else (0, 0)))
                               for provider, games in groups.items()]
        wins = sum(w for _, w, _ in self.provider_rates)
        total = sum(n for _, _, n in self.provider_rates)
        self.timeline = []
        estimate_wins = estimate_total = 0
        player = {}
        if folder and self.stats:
            target = dict(info)
            self.stats.fill_legacy_progress(folder, target)
            provider = target.get("provider")
            cohort = self.stats.similar_runs(groups.get(provider, []) if isinstance(provider, str) else [], target)
            estimates = {}
            progress, player = self.stats.run_progress(folder)
            for step, hp, stage in progress:
                if stage not in estimates:
                    estimates[stage] = self.stats.estimated_wins(cohort, stage)
                estimate_wins, estimate_total = estimates[stage]
                estimate = 100 * estimate_wins / estimate_total if estimate_total else None
                self.timeline.append((step, hp, estimate))

        metrics = [
            ("observed_rate", self.rate(wins, total), self.text("wins_sample", wins=wins, total=total)),
            ("finished_ai", str(total), self.text("wins_losses", wins=wins, losses=total - wins)),
            ("stage_estimate", self.rate(estimate_wins, estimate_total),
             self.text("wins_sample", wins=estimate_wins, total=estimate_total) if estimate_total
             else self.text("no_estimate" if folder else "no_selected_run")),
        ]
        for (caption, value, detail), (caption_key, number, hint) in zip(self.metrics, metrics):
            caption.configure(text=self.text(caption_key))
            value.configure(text=number)
            detail.configure(text=hint)
        self.draw_bars()
        self.draw_trend()
        self.show_player(info, player)
        self.inventory.update(player)
        self.show_notes(folder, info)

    def show_player(self, info, player):
        character = info.get("character")
        self.character = character if character in CHARACTERS else ""
        name = character_names(self.launcher.language)[CHARACTERS.index(character)] if self.character else "—"
        self.player_name.configure(text=name)
        health, maximum = player.get("hp"), player.get("max_hp")
        has_health = type(health) is int and type(maximum) is int and maximum > 0
        started = self.stats.timestamp(info.get("started")) if self.stats else None
        live = (self.launcher.console_started is not None and started is not None
                and started >= self.launcher.console_started and not info.get("ended"))
        art = self.launcher.art
        self.hp_caption.configure(text="  " + self.text("live_hp" if live else "latest_hp"),
                                  image=art.resource_icon("hp", self.character, (15, 15)) or "")
        self.player_hp.configure(text=f"{health}/{maximum}" if has_health else "—")
        self.hp_ratio = min(1, max(0, health / maximum)) if has_health else None
        self.draw_player_health()
        progress = []
        if type(info.get("ascension")) is int:
            progress.append(f"{self.text('ascension')} {info['ascension']}")
        stage = self.stats.stage(player) or self.stats.stage(info.get("last_stage")) if self.stats else None
        if stage:
            progress.extend((self.text("map_act", act=stage[0]), self.text("map_floor", floor=stage[1])))
        self.player_progress.configure(text=("  " + " · ".join(progress)) if progress else "",
                                       image=(art.resource_icon("floor", self.character, (14, 14)) or "") if stage else "")
        potions = player.get("potions")
        energy = player.get("energy")
        maximum_energy = player.get("max_energy")
        values = {"gold": player.get("gold"), "block": player.get("block"),
                  "potions": sum(isinstance(potion, dict) for potion in potions) if isinstance(potions, list) else None,
                  "energy": energy}
        for key, badge in self.resource_labels.items():
            number = values[key]
            if type(number) is not int:
                badge.grid_remove()
                continue
            value = f"{number}/{maximum_energy}" if key == "energy" and type(maximum_energy) is int else str(number)
            badge.configure(text=f"  {self.text('resource_' + key)}  {value}",
                            image=art.resource_icon(key, self.character, (16, 16)) or "")
            badge.grid()
        self.wiki.configure(text=self.text("wiki") if self.character else "", cursor="hand2" if self.character else "")
        photo = self.player_portrait(self.character)
        self.portrait_view.delete("all")
        if photo:
            self.portrait_view.create_image(53, 68, image=photo)
        elif self.character:
            self.portrait_view.create_oval(36, 29, 70, 63, fill=HOVER, outline=BORDER, width=2)
            self.portrait_view.create_arc(21, 66, 85, 105, start=0, extent=180, outline=BORDER, fill=HOVER, width=2)

    def draw_player_health(self, _event=None):
        bar, recent = self.health_bar, self.recent_hp
        bar.delete("all")
        recent.delete("all")
        if self.hp_ratio is not None:
            bar.create_rectangle(0, 0, bar.winfo_width() * self.hp_ratio, bar.winfo_height(), fill="#E99990", outline="")
        width, height = recent.winfo_width(), recent.winfo_height()
        points = self.timeline[-22:]
        if width < 20 or len(points) < 2:
            return
        recent.create_line(0, height / 2, width, height / 2, fill=BORDER)
        coords = [(3 + i * (width - 7) / (len(points) - 1), 2 + (height - 5) * (1 - hp / 100))
                  for i, (_, hp, _) in enumerate(points)]
        recent.create_line(*[dimension for p in coords for dimension in p], fill=ACCENT, width=2)
        x, y = coords[-1]
        recent.create_oval(x-2, y-2, x+2, y+2, fill=ACCENT, outline="")

    def player_portrait(self, character):
        return self.launcher.art.character_image(character, (97, 116), portrait=True) if character else None

    def open_wiki(self, _event):
        if self.character:
            if self.character == "Regent" or engine_language(self.launcher.language) == "zh":
                from urllib.parse import quote

                page = CHINESE_CHARACTERS[CHARACTERS.index(self.character)]
                webbrowser.open("https://sts2.huijiwiki.com/wiki/" + quote(page))
            else:
                webbrowser.open(f"https://sts.wiki/characters/{self.character.casefold()}")

    @staticmethod
    def rate(wins, total):
        return f"{wins / total:.0%}" if total else "—"

    def draw_bars(self, _event=None):
        canvas = self.bars
        canvas.delete("all")
        width = canvas.winfo_width()
        if width < 210:
            return
        fonts = self.launcher.fonts
        canvas.create_text(12, 8, text=self.text("provider_rates"), anchor="nw", fill=TEXT_COLOR, font=fonts["button"])
        for row, (provider, wins, total) in enumerate(self.provider_rates):
            y = 44 + 25 * row
            start, end = 92, width - 116
            canvas.create_text(12, y, text=provider, anchor="w", fill=TEXT_COLOR, font=fonts["small"])
            canvas.create_rectangle(start, y-4, end, y+4, outline="", fill=FIELD)
            if wins and total:
                canvas.create_rectangle(start, y-4, start+(end-start)*wins/total, y+4, outline="", fill=ACCENT if row == 0 else BLUE)
            canvas.create_text(width-12, y, text=f"{self.rate(wins, total)}  ·  {wins}/{total}",
                               anchor="e", fill=MUTED, font=fonts["small"])

    def draw_trend(self, _event=None):
        canvas = self.trend
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 230 or height < 85:
            return
        fonts = self.launcher.fonts
        canvas.create_text(12, 8, text=self.text("trend"), anchor="nw", fill=TEXT_COLOR, font=fonts["button"])
        chart_left, chart_right = 49, width - 16
        chart_top, chart_bottom = 40, height - 29
        canvas.create_text(width-12, 15, text=self.text("estimate_line"), anchor="e", fill=BLUE, font=fonts["small"])
        estimate_width = fonts["small"].measure(self.text("estimate_line"))
        canvas.create_text(width-28-estimate_width, 15, text=self.text("health"), anchor="e", fill=ACCENT, font=fonts["small"])
        if not self.timeline:
            canvas.create_text(width/2, (chart_top + chart_bottom) / 2, text=self.text("no_chart"),
                               fill=MUTED, font=fonts["small"])
            return
        total = self.timeline[-1][0]
        for percent in (0, 50, 100):
            y = chart_bottom - (chart_bottom - chart_top) * percent / 100
            canvas.create_line(chart_left, y, chart_right, y, fill=BORDER)
            canvas.create_text(chart_left-7, y, text=f"{percent}%", anchor="e", fill=MUTED, font=fonts["small"])
        for column, color in ((1, ACCENT), (2, BLUE)):
            points = []
            for point in self.timeline:
                step, value = point[0], point[column]
                if value is None:
                    break
                x = chart_left + (chart_right - chart_left) * step / max(1, total)
                y = chart_bottom - (chart_bottom - chart_top) * value / 100
                points.append((x, y))
            if len(points) > 1:
                canvas.create_line(*[coordinate for point in points for coordinate in point], fill=color, width=2)
            if points:
                x, y = points[-1]
                canvas.create_oval(x-3, y-3, x+3, y+3, fill=color, outline="")
        canvas.create_text(width-16, height-10, text=self.text("action_axis", total=total), anchor="e",
                           fill=MUTED, font=fonts["small"])

    def show_notes(self, folder, info):
        self.notes_title.configure(text=self.text("ai_notes"))
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        self.notes.insert("end", self.text("rate_scope") + "\n", "muted")
        latest = {}
        if folder and self.stats:
            for record in self.stats.json_lines(sorted(folder.glob("*.plan.jsonl"))):
                if isinstance(record.get("plan"), dict):
                    latest = record["plan"]
        for field in ("direction", "priorities", "pivot"):
            value = latest.get(field)
            if isinstance(value, str) and value:
                self.notes.insert("end", self.text("plan_" + field) + "  ", "plan")
                self.notes.insert("end", value + "\n")

        module = self.launcher.expression_module
        decisions = module.archived_messages(folder, info) if folder and module else []
        for item in reversed(decisions[-6:]):
            step = self.text("step", step=item.get("step", "?"), hp=item.get("hp", "?"))
            self.notes.insert("end", f"\n{step}  {item.get('action', '')}\n", "plan")
            self.notes.insert("end", item["message"] + "\n")
        if not latest and not decisions:
            self.notes.insert("end", self.text("no_notes") + "\n", "muted")
        self.notes.configure(state="disabled")


class RunHistory:
    def __init__(self, launcher):
        self.launcher = launcher
        self.window = ttk.Frame(launcher.view_host)
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(2, weight=1)

        toolbar = ttk.Frame(self.window)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.heading = ttk.Label(toolbar, style="Title.TLabel")
        self.heading.pack(side="left")
        self.folder_button = ttk.Button(toolbar, command=self.open_folder)
        self.folder_button.pack(side="right")
        self.refresh_button = ttk.Button(toolbar, command=self.refresh)
        self.refresh_button.pack(side="right", padx=(0, 7))

        sidebar = launcher.history_drawer
        self.tree = ttk.Treeview(sidebar, show="tree", selectmode="browse", style="History.Treeview")
        self.tree.column("#0", width=196, stretch=True)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll = ttk.Scrollbar(sidebar, orient="vertical", command=self.tree.yview,
                                    style="History.Vertical.TScrollbar")
        tree_scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.show_record)
        for event in ("<<TreeviewOpen>>", "<<TreeviewClose>>"):
            self.tree.bind(event, lambda _event: self.launcher.root.after_idle(self.launcher.fit_drawer))

        tab_bar = ttk.Frame(self.window)
        tab_bar.grid(row=1, column=0, sticky="w", pady=(0, 7))
        tab_bar.grid_columnconfigure((0, 1, 2), weight=1, uniform="detail_tabs")
        self.detail_tab = "record_tab"
        self.detail_buttons = {}
        for index, tab in enumerate(("record_tab", "analysis_tab", "map_tab")):
            button = ttk.Button(tab_bar, width=13, command=lambda tab=tab: self.select_detail(tab))
            button.grid(row=0, column=index, sticky="ew", padx=(0, 5))
            self.detail_buttons[tab] = button
        reading = ttk.Frame(self.window, style="Panel.TFrame")
        self.transcript_panel = reading
        self.analysis_panel = ttk.Frame(self.window)
        self.analysis = RunAnalysis(self.analysis_panel, launcher)
        self.map_panel = ttk.Frame(self.window)
        map_module = runpy.run_path(str(launcher.project / "python" / "run_map.py"))
        self.maps = map_module["RunMap"](self.map_panel, launcher, self.analysis.stats.game_records, self.open_room)
        self.body = tk.Text(reading, bg=PANEL, fg=TEXT_COLOR, font=launcher.fonts["body"],
                            wrap="word", padx=18, pady=15, relief="flat", selectbackground=BORDER,
                            highlightthickness=0, width=1, height=1, state="disabled")
        self.body.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(reading, orient="vertical", command=self.body.yview,
                                   style="History.Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        self.body.configure(yscrollcommand=scrollbar.set)
        self.body.tag_configure("heading", font=launcher.fonts["button"], foreground=ACCENT, spacing3=8)
        self.body.tag_configure("step", font=launcher.fonts["small_bold"], foreground=ACCENT, spacing1=12)
        self.body.tag_configure("reason", foreground=MUTED, spacing3=6)
        self.body.tag_configure("player", foreground=ACCENT, spacing1=5, spacing3=6)
        self.select_detail("record_tab")
        self.refresh()

    def select_detail(self, tab):
        self.detail_tab = tab
        for name, panel in (("record_tab", self.transcript_panel), ("analysis_tab", self.analysis_panel),
                            ("map_tab", self.map_panel)):
            if name == tab:
                panel.grid(row=2, column=0, sticky="nsew")
            else:
                panel.grid_remove()
            style = "Current.DetailTab.TButton" if name == tab else "DetailTab.TButton"
            self.detail_buttons[name].configure(style=style)
        self.show_detail()

    def label(self, info):
        provider = info.get("provider", "manual")
        if not isinstance(provider, str):
            provider = "manual"
        if provider in ("manual", "random"):
            provider = self.launcher.text("offline" if provider == "random" else "manual")
        character = info.get("character", "")
        if character in CHARACTERS:
            character = character_names(self.launcher.language)[CHARACTERS.index(character)]
        return provider + (f" · {character}" if isinstance(character, str) and character else "")

    def refresh(self):
        title = self.launcher.text("history")
        self.heading.configure(text=title)
        self.refresh_button.configure(text=self.launcher.text("refresh"))
        self.folder_button.configure(text=self.launcher.text("open_folder"))
        for key, button in self.detail_buttons.items():
            button.configure(text=self.launcher.text(key))
        previous = self.tree.selection()
        old_rows = self.tree.get_children()
        expanded = {key for key in old_rows if self.tree.item(key, "open")}
        self.tree.delete(*self.tree.get_children())
        self.entries = {}
        runs = sorted(HISTORY_DIR.glob("*/run.json"), reverse=True)
        for index, path in enumerate(runs):
            info = self.read_metadata(path)
            started = info.get("started")
            if not isinstance(started, str) or not started:
                continue
            folder = path.parent
            key = str(folder)
            started = started[5:16].replace("T", " ")
            self.tree.insert("", "end", iid=key, text=f"{started}  {self.label(info)}",
                             open=key in expanded or (index == 0 and not old_rows))
            self.entries[key] = (folder, info, None)
            for scene in sorted(folder.glob("*/scene.json")):
                scene_info = self.read_metadata(scene)
                room = scene_info.get("room")
                if not isinstance(room, str) or room not in ROOMS:
                    continue
                if any(type(scene_info.get(field)) is not int for field in ("act", "floor")):
                    continue
                scene_key = str(scene.parent)
                self.tree.insert(key, "end", iid=scene_key, text=scene_title(self.launcher.language, scene_info))
                self.entries[scene_key] = (scene.parent, info, scene_info)
        if self.entries:
            key = previous[0] if previous and previous[0] in self.entries else next(iter(self.entries))
            self.tree.selection_set(key)
            self.tree.see(key)
        self.show_record()
        self.launcher.fit_drawer()

    @staticmethod
    def read_metadata(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def show_record(self, _event=None):
        selected = self.tree.selection()
        self.body.configure(state="normal")
        self.body.delete("1.0", "end")
        if not selected or selected[0] not in self.entries:
            self.body.insert("end", self.launcher.text("no_runs"))
        else:
            folder, info, scene = self.entries[selected[0]]
            title = scene_title(self.launcher.language, scene) if scene else self.label(info)
            self.body.insert("end", title + "\n", "heading")
            messages = TEXT[self.launcher.language]
            status = messages.get(f"status_{info.get('status')}", messages["status_partial"])
            details = " · ".join(value for value in (info.get("model"), status) if isinstance(value, str) and value)
            self.body.insert("end", details + "\n\n", "reason")
            try:
                transcript = (folder / "transcript.txt").read_text(encoding="utf-8", errors="replace")
            except OSError:
                transcript = ""
            lines = (transcript.strip("\n") or self.launcher.text("no_transcript")).splitlines()
            if scene and lines[0].startswith(ENTERED_PREFIXES):
                lines = lines[1:]
            for line in lines:
                match = AI_STEP.fullmatch(line)
                if match:
                    step, hp, action, reason = match.groups()
                    self.body.insert("end", self.launcher.text("step", step=step, hp=hp) + "\n", "step")
                    self.body.insert("end", action + "\n")
                    if reason:
                        self.body.insert("end", f"{self.launcher.text('reason')}  {reason}\n", "reason")
                elif line.startswith(PLAYER_PREFIXES):
                    self.body.insert("end", line + "\n", "player")
                elif not line or set(line.strip()) not in ({"─"}, {"═"}):
                    self.body.insert("end", line.rstrip() + "\n")
        self.body.configure(state="disabled")
        self.show_detail()

    def show_detail(self):
        if self.detail_tab == "record_tab":
            return
        selected = self.tree.selection()
        folder, info, scene = self.entries.get(selected[0], (None, {}, None)) if selected else (None, {}, None)
        run = folder.parent if scene else folder
        if self.detail_tab == "analysis_tab":
            self.analysis.metrics_for(run, info, HISTORY_DIR)
        else:
            self.maps.set_run(run, folder if scene else None, scene, info.get("seed"))

    def open_room(self, path):
        key = str(path)
        if key in self.entries:
            self.tree.item(self.tree.parent(key), open=True)
            self.tree.selection_set(key)
            self.tree.see(key)
            self.select_detail("record_tab")
            self.show_record()

    def open_folder(self):
        selected = self.tree.selection()
        path = self.entries[selected[0]][0] if selected and selected[0] in self.entries else HISTORY_DIR
        try:
            if path == HISTORY_DIR:
                path.mkdir(exist_ok=True)
            os.startfile(path)
        except OSError as error:
            messagebox.showerror(self.launcher.text("history"), str(error), parent=self.window)


class SaveFolderSettings:
    def __init__(self, launcher):
        self.launcher = launcher
        self.window = tk.Toplevel(launcher.root)
        self.window.title(launcher.text("save_settings"))
        self.window.transient(launcher.root)
        self.window.resizable(False, False)
        self.detected = default_save_folder(launcher.project)
        self.path = tk.StringVar(value=str(launcher.save_folder()))
        area = ttk.Frame(self.window, style="Panel.TFrame", padding=16)
        area.pack(fill="both", expand=True)
        area.grid_columnconfigure(0, weight=1)
        ttk.Label(area, text=launcher.text("save_directory")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        entry = ttk.Entry(area, textvariable=self.path, font=launcher.fonts["body"], width=63)
        entry.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(area, text=launcher.text("browse"), command=self.browse).grid(row=1, column=1, sticky="ew")
        ttk.Button(area, text=launcher.text("save_default"), style="Language.TButton",
                   command=lambda: self.path.set(str(self.detected))).grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Button(area, text=launcher.text("save_profile"), style="Selected.TButton", command=self.save).grid(
            row=2, column=1, sticky="ew", pady=(12, 0))
        entry.focus_set()

    def browse(self):
        directory = self.launcher.absolute_save_folder(self.path.get())
        initial = directory if directory and directory.is_dir() else self.launcher.project
        selected = filedialog.askdirectory(parent=self.window, initialdir=initial, mustexist=True)
        if selected:
            self.path.set(selected)

    def save(self):
        launcher = self.launcher
        directory = launcher.absolute_save_folder(self.path.get())
        if directory is None or (directory != self.detected and not directory.is_dir()):
            messagebox.showerror(launcher.text("save_settings"), launcher.text("invalid_save_directory"), parent=self.window)
            return
        data = launcher.preferences()
        if directory == self.detected:
            data.pop("save_directory", None)
        else:
            data["save_directory"] = str(directory)
        if launcher.persist_expression(data, self.window):
            launcher.refresh_saves()
            self.window.destroy()


class ApiKeySettings:
    def __init__(self, launcher):
        self.launcher = launcher
        self.window = tk.Toplevel(launcher.root)
        self.window.title(launcher.text("api_settings"))
        self.window.transient(launcher.root)
        self.window.resizable(False, False)
        area = ttk.Frame(self.window, padding=16, style="Panel.TFrame")
        area.pack(fill="both", expand=True)
        self.keys = {}
        for provider in PROVIDERS:
            ttk.Label(area, text=provider).pack(anchor="w", pady=(4, 5))
            key = tk.StringVar(value=launcher.api_keys[provider].get())
            ttk.Entry(area, textvariable=key, show="•", font=launcher.fonts["body"], width=35).pack(fill="x", pady=(0, 6))
            self.keys[provider] = key
        ttk.Label(area, text=launcher.text("key_storage"), style="Caption.TLabel", wraplength=355).pack(anchor="w", pady=(6, 9))
        ttk.Button(area, text=launcher.text("save_profile"), style="Selected.TButton", command=self.save).pack(anchor="e")

    def save(self):
        for provider, entry in self.keys.items():
            key = entry.get().strip()
            if not key or key == self.launcher.api_keys[provider].get() and provider in self.launcher.stored_keys:
                continue
            try:
                self.launcher.expression_module.save_key(provider, key)
            except OSError as error:
                messagebox.showerror(self.launcher.text("api_settings"), str(error), parent=self.window)
                return
            self.launcher.api_keys[provider].set(key)
            self.launcher.stored_keys.add(provider)
        self.window.destroy()


class PersonaEditor:
    def __init__(self, launcher, card_id):
        self.launcher = launcher
        self.card_id = card_id
        self.window = tk.Toplevel(launcher.root)
        self.window.title(launcher.text("persona_panel"))
        self.window.transient(launcher.root)
        self.window.configure(background=BACKGROUND)
        self.window.resizable(False, False)
        module = launcher.expression_module
        card = module.catalog(PREFERENCES_PATH, launcher.language).get(card_id) or launcher.selected_persona()
        self.name = tk.StringVar(value=card["name"] if card_id else "")
        self.follow_default = launcher.text("follow_default")
        self.language = tk.StringVar(value=card["language"] or self.follow_default)
        self.provider = tk.StringVar(value=card["provider"])
        self.model = tk.StringVar(value=card["model"])
        self.enabled = tk.BooleanVar(value=card["enabled"])
        self.trial = tk.BooleanVar(value=card["trial"])
        area = ttk.Frame(self.window, padding=16, style="Panel.TFrame")
        area.pack(fill="both", expand=True)
        area.grid_columnconfigure((0, 1), weight=1, uniform="persona_fields")
        ttk.Label(area, text=launcher.text("speaker_name")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(area, text=launcher.text("output_language")).grid(row=0, column=1, sticky="w", padx=(8, 0), pady=(0, 6))
        name = ttk.Entry(area, textvariable=self.name, font=launcher.fonts["body"], width=18)
        name.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Combobox(area, textvariable=self.language, font=launcher.fonts["body"], width=18,
                     values=(self.follow_default, *module.SPEECH_LANGUAGES)).grid(
                         row=1, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(area, text=launcher.text("provider")).grid(row=2, column=0, sticky="w", pady=(12, 6))
        ttk.Label(area, text=launcher.text("model")).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(12, 6))
        provider = ttk.Combobox(area, textvariable=self.provider, state="readonly", values=tuple(PROVIDERS),
                                font=launcher.fonts["body"], width=18)
        provider.grid(row=3, column=0, sticky="ew", padx=(0, 8))
        provider.bind("<<ComboboxSelected>>", self.provider_changed)
        self.model_box = ttk.Combobox(area, textvariable=self.model, font=launcher.fonts["body"], width=18)
        self.model_box.grid(row=3, column=1, sticky="ew", padx=(8, 0))
        self.model_box.configure(values=launcher.models_for(card["provider"]))
        self.model_status = ttk.Label(area, style="Caption.TLabel")
        self.model_status.grid(row=4, column=0, sticky="w", pady=(4, 0))
        self.refresh_models_button = ttk.Button(area, text=launcher.text("refresh_models"), style="Language.TButton",
                                                command=self.refresh_models)
        self.refresh_models_button.grid(row=4, column=1, sticky="e", pady=(4, 0))

        ttk.Label(area, text=launcher.text("character")).grid(row=5, column=0, sticky="w", pady=(10, 6))
        ttk.Label(area, text=launcher.text("ascension")).grid(row=5, column=1, sticky="w", padx=(8, 0), pady=(10, 6))
        role, self.role_box = launcher.character_picker(area, 18, card["character"])
        role.grid(row=6, column=0, sticky="ew", padx=(0, 8))
        self.ascension_box = ttk.Combobox(area, state="readonly", width=18, font=launcher.fonts["body"], values=tuple(range(11)))
        self.ascension_box.grid(row=6, column=1, sticky="ew", padx=(8, 0))
        self.ascension_box.current(card["ascension"])
        ttk.Checkbutton(area, text=launcher.text("expression"), variable=self.enabled).grid(row=7, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(area, text=launcher.text("test"), variable=self.trial).grid(row=7, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Label(area, text=launcher.text("identity_card")).grid(row=8, column=0, columnspan=2, sticky="w", pady=(12, 6))
        self.voice = tk.Text(area, width=44, height=6, wrap="word", bg=FIELD, fg=TEXT_COLOR,
                             insertbackground=TEXT_COLOR, font=launcher.fonts["body"], padx=8, pady=7,
                             relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
        self.voice.insert("1.0", card["identity"] if card_id else "")
        self.voice.grid(row=9, column=0, columnspan=2, sticky="ew")
        ttk.Label(area, text=launcher.text("live_profile"), style="Caption.TLabel", wraplength=295).grid(
            row=10, column=0, sticky="w", pady=(10, 0))
        ttk.Button(area, text=launcher.text("save_profile"), style="Selected.TButton", command=self.save).grid(
            row=10, column=1, sticky="e", pady=(10, 0))
        ttk.Button(area, text=launcher.text("new_identity"), style="Language.TButton", command=self.new_card).grid(
            row=11, column=0, sticky="w", pady=(7, 0))
        name.focus_set()

    def new_card(self):
        self.card_id = ""
        self.name.set("")
        self.voice.delete("1.0", "end")

    def provider_changed(self, _event=None):
        provider = self.provider.get()
        self.model.set(self.launcher.expression_module.PROVIDER_MODELS[provider])
        self.model_box.configure(values=self.launcher.models_for(provider))
        self.model_status.configure(text="")

    def refresh_models(self):
        launcher = self.launcher
        provider = self.provider.get()
        key = launcher.api_keys[provider].get().strip()
        if not key:
            messagebox.showerror(launcher.text("api_settings"), launcher.text("missing_key", provider=provider), parent=self.window)
            launcher.show_api_settings()
            return
        self.refresh_models_button.state(["disabled"])
        self.model_status.configure(text=launcher.text("loading_models"))
        result = SimpleQueue()

        def fetch():
            try:
                result.put((launcher.expression_module.list_models(provider, key), None))
            except (OSError, ValueError, KeyError, TypeError) as error:
                result.put(((), error))

        def finish():
            if not self.window.winfo_exists():
                return
            try:
                models, error = result.get_nowait()
            except Empty:
                launcher.root.after(120, finish)
                return
            self.refresh_models_button.state(["!disabled"])
            if error:
                self.model_status.configure(text="")
                messagebox.showerror(launcher.text("refresh_models"), str(error), parent=self.window)
                return
            launcher.available_models[provider] = models
            if provider == self.provider.get():
                self.model_box.configure(values=launcher.models_for(provider))
                self.model_status.configure(text=launcher.text("model_count", total=len(models)))

        Thread(target=fetch, daemon=True).start()
        launcher.root.after(120, finish)

    def save(self):
        launcher = self.launcher
        name = self.name.get().strip()
        if not name:
            messagebox.showerror(launcher.text("new_identity"), launcher.text("name_required"), parent=self.window)
            return
        module = launcher.expression_module
        data = module.preferences(PREFERENCES_PATH)
        cards = module.cards_in(data)
        card_id = self.card_id or uuid4().hex
        language = self.language.get().strip()
        cards[card_id] = module.clean_card({"name": name, "language": "" if language == self.follow_default else language,
                                           "provider": self.provider.get(), "model": self.model.get(),
                                           "enabled": self.enabled.get(), "trial": self.trial.get(),
                                           "character": CHARACTERS[self.role_box.current()],
                                           "ascension": int(self.ascension_box.get()),
                                           "identity": self.voice.get("1.0", "end-1c")}, name)
        data["cards"] = cards
        data["selected_card"] = card_id
        if launcher.persist_expression(data, self.window):
            self.window.destroy()


class RunChat:
    def __init__(self, launcher):
        self.launcher = launcher
        self.window = ttk.Frame(launcher.view_host)
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(1, weight=1)
        self.title = ttk.Label(self.window, style="Title.TLabel")
        self.title.grid(row=0, column=0, sticky="w", pady=(0, 12))

        sidebar = launcher.chat_drawer
        self.runs = ttk.Treeview(sidebar, show="tree", selectmode="browse", style="History.Treeview")
        self.runs.column("#0", width=196, stretch=True)
        self.runs.pack(side="left", fill="both", expand=True)
        tree_scroll = ttk.Scrollbar(sidebar, orient="vertical", command=self.runs.yview, style="History.Vertical.TScrollbar")
        tree_scroll.pack(side="right", fill="y")
        self.runs.configure(yscrollcommand=tree_scroll.set)
        self.runs.bind("<<TreeviewSelect>>", self.render)

        chat = ttk.Frame(self.window, padding=(9, 7), style="Panel.TFrame")
        chat.grid(row=1, column=0, sticky="nsew")
        self.run_title = ttk.Label(chat, style="Section.TLabel")
        self.run_title.pack(anchor="w", pady=(0, 7))
        self.body = tk.Text(chat, bg=BACKGROUND, fg=TEXT_COLOR, wrap="word", font=launcher.fonts["body"],
                            padx=12, pady=10, width=1, height=1, highlightthickness=0, relief="flat",
                            selectbackground=BORDER, state="disabled")
        self.body.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(chat, orient="vertical", command=self.body.yview, style="History.Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        self.body.configure(yscrollcommand=scroll.set)
        self.body.tag_configure("speaker", font=launcher.fonts["small_bold"], foreground=ACCENT, spacing1=7)
        self.body.tag_configure("message", background=PANEL, lmargin1=10, lmargin2=10, rmargin=25, spacing1=6, spacing3=8)
        self.body.tag_configure("context", font=launcher.fonts["small"], foreground=MUTED, spacing3=5)
        self.rows = {}
        self.signature = None
        self.poll_id = None
        self.window.bind("<Destroy>", self.stop, add="+")
        self.tick()

    def tick(self):
        if self.window.winfo_ismapped():
            self.refresh()
        self.poll_id = self.window.after(1500, self.tick)

    def stop(self, event):
        if event.widget is self.window and self.poll_id:
            self.window.after_cancel(self.poll_id)
            self.poll_id = None

    def refresh(self):
        title = self.launcher.text("chat_title")
        self.title.configure(text=title)
        rows = {}
        for metadata in sorted(HISTORY_DIR.glob("*/run.json"), reverse=True):
            info = RunHistory.read_metadata(metadata)
            if info.get("provider") in ("DeepSeek", "Claude") and isinstance(info.get("started"), str):
                rows[str(metadata.parent)] = info
        if rows != self.rows:
            selected = self.runs.selection()
            self.rows = rows
            self.runs.delete(*self.runs.get_children())
            for key, info in rows.items():
                time = info["started"][5:16].replace("T", " ")
                persona = info.get("persona_name") or info["provider"]
                self.runs.insert("", "end", iid=key, text=f"{time}  {persona}")
            if rows:
                key = selected[0] if selected and selected[0] in rows else next(iter(rows))
                self.runs.selection_set(key)
                self.runs.see(key)
        self.render()
        self.launcher.fit_drawer()

    def render(self, _event=None):
        chosen = self.runs.selection()
        key = chosen[0] if chosen and chosen[0] in self.rows else ""
        info = self.rows.get(key, {})
        files = []
        if key:
            root = Path(key)
            paths = sorted(root.glob("*.expression.jsonl")) if info.get("expression_format") else [root / "transcript.txt"]
            for path in paths:
                try:
                    status = path.stat()
                    files.append((path, status.st_mtime_ns, status.st_size))
                except OSError:
                    continue
        signature = key, self.launcher.language, tuple(files)
        if signature == self.signature:
            return
        at_bottom = self.signature is None or key != self.signature[0] or self.body.yview()[1] >= 0.98
        position = self.body.yview()[0]
        self.signature = signature
        model = info.get("model")
        self.run_title.configure(text=" · ".join(value for value in (info.get("provider"), model) if isinstance(value, str) and value))
        module = self.launcher.expression_module
        messages = module.archived_messages(Path(key), info) if key and module else []
        self.body.configure(state="normal")
        self.body.delete("1.0", "end")
        if not messages:
            self.body.insert("end", self.launcher.text("no_chat"), "context")
        for item in messages:
            speaker = item.get("name") or info.get("provider") or "AI"
            step = item.get("step", "?")
            self.body.insert("end", f"{speaker}  ·  {self.launcher.text('chat_step', step=step)}\n", "speaker")
            self.body.insert("end", item["message"] + "\n", "message")
            if isinstance(item.get("action"), str):
                self.body.insert("end", item["action"] + "\n", "context")
        self.body.configure(state="disabled")
        if at_bottom:
            self.body.see("end")
        else:
            self.body.yview_moveto(position)


class Launcher:
    def __init__(self, root, project):
        self.root = root
        self.project = project
        self.language = "zh"
        self.mode = "manual"
        self.child = None
        self.console_started = None
        self.history = None
        self.chat = None
        self.key_settings = None
        self.save_settings = None
        self.persona_editor = None
        self.status_key = ""
        self.page = "home"
        self.saves = []
        pack_reader = runpy.run_path(str(project / "scripts" / "extract_localization.py"))
        game_pack = runpy.run_path(str(project / "python" / "portable_runtime.py"))["find_game_pack"]
        self.art = GameArt(project, game_pack, pack_reader["entries"], pack_reader["portrait"], root)
        self.art.refresh()
        expression_file = project / "agent" / "run_expression.py"
        self.expression_module = SimpleNamespace(**runpy.run_path(str(expression_file))) if expression_file.is_file() else None
        saved_language = self.preferences().get("ui_language")
        if isinstance(saved_language, str) and saved_language in INTERFACE_LANGUAGES:
            self.language = saved_language
        self.persona_id = ""
        self.personas = {}
        self.available_models = {}
        self.stored_keys = set()
        self.api_keys = {
            "DeepSeek": tk.StringVar(value=os.environ.get("DEEPSEEK_API_KEY", "")),
            "Claude": tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", "")),
        }
        if self.expression_module:
            for provider, key in self.api_keys.items():
                try:
                    saved_key = self.expression_module.load_key(provider)
                except (OSError, UnicodeError):
                    continue
                if saved_key:
                    key.set(saved_key)
                    self.stored_keys.add(provider)
        self.fonts = configure_theme(root)
        for face in self.fonts.values():
            face.configure(family=FONT_FAMILIES.get(self.language, FONT_FAMILIES["en"]))
        root.geometry("800x500")
        root.minsize(720, 445)
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        content = ttk.Frame(root, padding=(16, 14, 16, 10))
        content.grid(row=0, column=0, sticky="nsew")
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(1, weight=1)
        header = ttk.Frame(content)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 13))
        header.grid_columnconfigure(0, weight=1)
        self.title = ttk.Label(header, style="Title.TLabel")
        self.title.grid(row=0, column=0, sticky="w", padx=(0, 20))
        edge = round(root.winfo_fpixels("0.43i"))
        gear = ttk.Frame(header, width=edge, height=edge)
        gear.grid(row=0, column=1, sticky="e")
        gear.grid_propagate(False)
        gear.grid_columnconfigure(0, weight=1)
        gear.grid_rowconfigure(0, weight=1)
        self.settings_button = ttk.Menubutton(gear, text="⚙", style="Gear.TMenubutton", takefocus=True)
        self.settings_button.grid(row=0, column=0, sticky="nsew")
        menu_style = {"tearoff": False, "background": PANEL, "foreground": TEXT_COLOR,
                      "activebackground": HOVER, "activeforeground": ACCENT, "font": self.fonts["small"]}
        self.settings_menu = tk.Menu(self.settings_button, **menu_style)
        self.interface_menu = tk.Menu(self.settings_menu, **menu_style)
        self.speech_menu = tk.Menu(self.settings_menu, **menu_style)
        self.settings_button.configure(menu=self.settings_menu)
        self.interface_option = tk.StringVar(value=self.language)
        self.speech_option = tk.StringVar(value="")

        side = ttk.Frame(content, style="Panel.TFrame", padding=7, width=218)
        side.grid(row=1, column=0, sticky="ns", padx=(0, 12))
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        self.sidebar = side
        self.nav_buttons = {}
        for name, row in (("home", 0), ("chat_title", 1), ("history", 3)):
            button = ttk.Button(side, style="Navigation.TButton", command=lambda name=name: self.show_page(name))
            button.grid(row=row, column=0, sticky="ew", pady=(0, 4))
            self.nav_buttons[name] = button
        self.chat_drawer = ttk.Frame(side, style="Panel.TFrame")
        self.chat_drawer.grid(row=2, column=0, sticky="nsew", pady=(0, 5))
        self.chat_drawer.grid_remove()
        self.history_drawer = ttk.Frame(side, style="Panel.TFrame")
        self.history_drawer.grid(row=4, column=0, sticky="nsew")
        self.history_drawer.grid_remove()
        side.bind("<Configure>", self.fit_drawer)

        self.view_host = ttk.Frame(content)
        self.view_host.grid(row=1, column=1, sticky="nsew")
        self.view_host.grid_columnconfigure(0, weight=1)
        self.view_host.grid_rowconfigure(0, weight=1)
        self.home = ttk.Frame(self.view_host)
        self.home.grid(row=0, column=0, sticky="nsew")
        panel = ttk.Frame(self.home, style="Panel.TFrame", padding=16)
        panel.pack(fill="x")
        panel.grid_columnconfigure((0, 1), weight=1, uniform="fields")
        modes = ttk.Frame(panel, style="Panel.TFrame")
        modes.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        modes.grid_columnconfigure((0, 1), weight=1, uniform="modes")
        self.modes = {}
        for column, name in enumerate(("manual", "ai_play")):
            button = ttk.Button(modes, width=12, command=lambda name=name: self.select_mode(name))
            button.grid(row=0, column=column, sticky="ew", padx=(0, 6 if column == 0 else 0))
            self.modes[name] = button

        self.character_label = ttk.Label(panel)
        self.character_label.grid(row=1, column=0, sticky="w", pady=(0, 5))
        self.ascension_label = ttk.Label(panel)
        self.ascension_label.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(0, 5))
        manual_role, self.character_box = self.character_picker(panel, 16)
        manual_role.grid(row=2, column=0, sticky="ew", padx=(0, 8))
        self.ascension_box = ttk.Combobox(panel, width=15, state="readonly", font=self.fonts["body"],
                                         values=tuple(range(11)))
        self.ascension_box.grid(row=2, column=1, sticky="ew", padx=(8, 0))
        self.ascension_box.current(0)
        self.manual_fields = (self.character_label, self.ascension_label, manual_role, self.ascension_box)

        self.api_panel = ttk.Frame(panel, style="Panel.TFrame")
        self.api_panel.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.api_panel.grid_columnconfigure(0, weight=1)
        self.persona_label = ttk.Label(self.api_panel)
        self.persona_label.grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.persona_box = ttk.Combobox(self.api_panel, style="Display.TCombobox", state="readonly",
                                         exportselection=False, width=18, font=self.fonts["body"])
        self.persona_box.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.persona_box.bind("<<ComboboxSelected>>", self.select_persona)
        self.persona_box.bind("<FocusIn>", lambda _event: self.root.after_idle(self.persona_box.selection_clear), add="+")
        self.persona_panel_button = ttk.Button(self.api_panel, style="Language.TButton", command=self.show_persona_panel)
        self.persona_panel_button.grid(row=1, column=1, sticky="e")
        preview_frame = ttk.Frame(self.api_panel, style="Panel.TFrame")
        preview_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.persona_role_icon = tk.Canvas(preview_frame, width=25, height=25, bg=PANEL, highlightthickness=0)
        self.persona_role_icon.pack(side="left", padx=(0, 5))
        self.run_preview = ttk.Label(preview_frame, style="Caption.TLabel")
        self.run_preview.pack(side="left")

        self.save_panel = ttk.Frame(panel, style="Panel.TFrame")
        self.save_panel.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(13, 0))
        self.save_panel.grid_columnconfigure(0, weight=1)
        self.save_label = ttk.Label(self.save_panel)
        self.save_label.grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.saves_refresh = ttk.Button(self.save_panel, style="Language.TButton", command=self.refresh_saves)
        self.saves_refresh.grid(row=0, column=1, sticky="e", pady=(0, 5))
        self.save_box = ttk.Combobox(self.save_panel, style="Display.TCombobox", state="readonly",
                                     exportselection=False, width=18, font=self.fonts["body"])
        self.save_box.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.save_box.bind("<<ComboboxSelected>>", lambda _event: self.save_box.selection_clear())
        self.load_button = ttk.Button(self.save_panel, width=12, command=self.load_save)
        self.load_button.grid(row=1, column=1, sticky="ew")

        actions = ttk.Frame(panel, style="Panel.TFrame")
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(17, 0))
        actions.grid_columnconfigure(1, weight=1)
        self.start_button = ttk.Button(actions, width=13, style="Selected.TButton", command=self.start_game)
        self.start_button.grid(row=0, column=1, sticky="e")
        footer = ttk.Frame(content)
        footer.grid(row=2, column=1, sticky="ew", pady=(7, 0))
        self.status_label = ttk.Label(footer, style="Status.TLabel", wraplength=470)
        self.status_label.pack(side="left", fill="x", expand=True)
        if not self.expression_module:
            self.modes["ai_play"].state(["disabled"])

        self.refresh()

    def show_page(self, page):
        self.page = "home" if page == self.page else page
        if self.page == "history" and self.history is None:
            self.history = RunHistory(self)
        if self.page == "chat_title" and self.chat is None:
            self.chat = RunChat(self)

        if self.page == "home":
            self.home.grid()
        else:
            self.home.grid_remove()
        for name, view, drawer in (("chat_title", self.chat, self.chat_drawer),
                                   ("history", self.history, self.history_drawer)):
            if self.page == name:
                drawer.grid()
                view.window.grid(row=0, column=0, sticky="nsew")
                view.refresh()
            else:
                drawer.grid_remove()
                if view:
                    view.window.grid_remove()
        if self.page != "home":
            width = max(self.root.winfo_width(), min(1010, self.root.winfo_screenwidth() - 40))
            preferred_height = 795 if self.page == "history" else 685
            height = max(self.root.winfo_height(), min(preferred_height, self.root.winfo_screenheight() - 80))
            self.root.geometry(f"{width}x{height}")
        self.refresh_navigation()
        self.fit_drawer()

    def fit_drawer(self, _event=None):
        if self.page == "history" and self.history:
            tree = self.history.tree
        elif self.page == "chat_title" and self.chat:
            tree = self.chat.runs
        else:
            return
        parents = tree.get_children()
        visible = len(parents) + sum(len(tree.get_children(item)) for item in parents if tree.item(item, "open"))
        header_height = sum(button.winfo_reqheight() + 4 for button in self.nav_buttons.values())
        available = max(1, (self.sidebar.winfo_height() - header_height - 24) // TREE_ROW_HEIGHT)
        tree.configure(height=min(max(1, visible), available))

    def refresh_navigation(self):
        for name, button in self.nav_buttons.items():
            active = name == self.page
            prefix = "   " if name == "home" else ("▾  " if active else "▸  ")
            button.configure(text=prefix + self.text(name),
                             style="Current.Navigation.TButton" if active else "Navigation.TButton")

    def selected_persona(self):
        return self.personas[self.persona_id]

    def preferences(self):
        if self.expression_module:
            return self.expression_module.preferences(PREFERENCES_PATH)
        return RunHistory.read_metadata(PREFERENCES_PATH)

    def refresh_settings_menu(self):
        self.settings_menu.delete(0, "end")
        self.interface_menu.delete(0, "end")
        self.speech_menu.delete(0, "end")
        self.interface_option.set(self.language)
        saved_speech = self.preferences().get("output_language")
        self.speech_option.set(saved_speech if isinstance(saved_speech, str) else "")
        for code, label in INTERFACE_LANGUAGES.items():
            self.interface_menu.add_radiobutton(label=label, value=code, variable=self.interface_option,
                                                command=lambda code=code: self.select_language(code))
        self.settings_menu.add_cascade(label=self.text("interface_language"), menu=self.interface_menu)
        if self.expression_module:
            options = [("", self.text("follow_interface"))]
            options.extend((language, language) for language in self.expression_module.SPEECH_LANGUAGES)
            for language, label in options:
                self.speech_menu.add_radiobutton(label=label, value=language, variable=self.speech_option,
                                                 command=lambda language=language: self.select_default_speech(language))
            self.settings_menu.add_cascade(label=self.text("default_speech"), menu=self.speech_menu)
        self.settings_menu.add_separator()
        self.settings_menu.add_command(label=self.text("save_settings"), command=self.show_save_settings)
        if self.expression_module:
            self.settings_menu.add_command(label=self.text("api_settings"), command=self.show_api_settings)
        self.settings_menu.add_separator()
        self.settings_menu.add_command(label=self.text("about"), command=self.show_about)

    def show_about(self):
        credits = ("基于 wuhao21/sts2-cli，使用 MIT 许可证。\n"
                   "角色、状态和地图图标 © Mega Crit，从本机 Steam 游戏读取。\n"
                   "卡牌小图和角色资料来自灰机 Wiki。适用的站点内容采用 CC BY-NC-SA 4.0。") if engine_language(self.language) == "zh" else (
                   "Based on wuhao21/sts2-cli under the MIT license.\n"
                   "Character, status, and map art © Mega Crit, read from the local Steam game.\n"
                   "Card badges come from the Huiji STS2 Wiki card navigation page.\n"
                   "Huiji Wiki site content is published under CC BY-NC-SA 4.0 where applicable.")
        messagebox.showinfo(self.text("about"), f"{self.text('window')}\n\n{credits}", parent=self.root)

    def select_default_speech(self, language):
        data = self.preferences()
        data["output_language"] = language
        self.persist_expression(data)
        self.refresh_settings_menu()

    def models_for(self, provider):
        return self.available_models.get(provider) or self.expression_module.MODEL_CHOICES[provider]

    def show_api_settings(self):
        if self.key_settings and self.key_settings.window.winfo_exists():
            self.key_settings.window.lift()
        else:
            self.key_settings = ApiKeySettings(self)

    def show_save_settings(self):
        if self.save_settings and self.save_settings.window.winfo_exists():
            self.save_settings.window.lift()
        else:
            self.save_settings = SaveFolderSettings(self)

    def absolute_save_folder(self, value):
        if not isinstance(value, str) or not value.strip().strip('"'):
            return None
        try:
            path = Path(os.path.expandvars(value.strip().strip('"'))).expanduser()
            return (self.project / path).resolve()
        except (OSError, RuntimeError, ValueError):
            return None

    def save_folder(self):
        return self.absolute_save_folder(self.preferences().get("save_directory")) or default_save_folder(self.project)

    def refresh_saves(self):
        index = self.save_box.current()
        current = self.saves[index] if 0 <= index < len(self.saves) else None
        self.saves = playable_saves(self.save_folder())
        self.save_box.configure(values=[path.name for path in self.saves])
        if self.saves:
            self.save_box.configure(state="readonly")
            self.save_box.current(self.saves.index(current) if current in self.saves else 0)
        else:
            self.save_box.set(self.text("no_saves"))
            self.save_box.configure(state="disabled")
        self.load_button.state(["!disabled" if self.saves and self.child is None else "disabled"])
        self.save_box.selection_clear()

    def show_persona_panel(self):
        if self.persona_editor and self.persona_editor.window.winfo_exists():
            self.persona_editor.window.lift()
        else:
            self.persona_editor = PersonaEditor(self, self.persona_id)

    def refresh_personas(self):
        if not self.expression_module:
            return
        data = self.preferences()
        self.personas = self.expression_module.catalog_from(data, self.language)
        persisted = data.get("selected_card")
        selected = persisted if isinstance(persisted, str) and persisted in self.personas else self.persona_id
        self.persona_id = selected if selected in self.personas else next(iter(self.personas))
        fallback = self.expression_module.default_speech(data, self.language)
        values = [f"{card['name']} · {card['language'] or fallback} [{card['model']}]" for card in self.personas.values()]
        self.persona_box.configure(values=values)
        self.persona_box.current(list(self.personas).index(self.persona_id))
        self.persona_box.selection_clear()
        card = self.selected_persona()
        role = character_names(self.language)[CHARACTERS.index(card["character"])]
        self.draw_character_icon(self.persona_role_icon, card["character"])
        preview = self.text("run_preview", character=role, ascension=card["ascension"])
        self.run_preview.configure(text=preview + " · " + self.text("test" if card["trial"] else "full_run"))

    def persist_expression(self, data, parent=None):
        try:
            write_json(PREFERENCES_PATH, data)
        except OSError as error:
            messagebox.showerror(self.text("identity_settings"), str(error), parent=parent or self.root)
            self.refresh_personas()
            return False
        self.refresh_personas()
        return True

    def select_persona(self, _event=None):
        index = self.persona_box.current()
        if index < 0:
            return
        data = self.expression_module.preferences(PREFERENCES_PATH)
        data["selected_card"] = list(self.personas)[index]
        self.persist_expression(data)
        self.root.after_idle(self.persona_box.selection_clear)

    def text(self, key, **values):
        return TEXT[self.language][key].format(**values)

    def select_language(self, language):
        if language not in INTERFACE_LANGUAGES:
            return
        data = self.preferences()
        data["ui_language"] = language
        if not self.persist_expression(data):
            self.refresh_settings_menu()
            return
        self.language = language
        for face in self.fonts.values():
            face.configure(family=FONT_FAMILIES.get(language, FONT_FAMILIES["en"]))
        self.refresh()
        if self.history and self.history.window.winfo_exists():
            self.history.refresh()
        if self.chat and self.chat.window.winfo_exists():
            self.chat.refresh()

    def select_mode(self, mode):
        self.mode = mode
        self.refresh()

    def character_picker(self, parent, width, character="Ironclad"):
        picker = ttk.Frame(parent, style="Panel.TFrame")
        mark = tk.Canvas(picker, width=25, height=25, bg=PANEL, highlightthickness=0)
        mark.pack(side="left", padx=(0, 5))
        box = ttk.Combobox(picker, width=width, state="readonly", font=self.fonts["body"],
                           values=character_names(self.language))
        box.pack(side="left", fill="x", expand=True)
        box.current(CHARACTERS.index(character))
        self.draw_character_icon(mark, character)

        def change(_event):
            index = box.current()
            if 0 <= index < len(CHARACTERS):
                self.draw_character_icon(mark, CHARACTERS[index])

        box.bind("<<ComboboxSelected>>", change)
        return picker, box

    def draw_character_icon(self, canvas, character):
        canvas.delete("all")
        image = self.art.character_image(character, (23, 23))
        if image:
            canvas.create_image(12, 12, image=image)
        else:
            canvas.create_oval(2, 2, 23, 23, fill=FIELD, outline=BORDER)
            canvas.create_text(12, 12, text=character[0], fill=MUTED, font=self.fonts["small_bold"])

    def character_ready(self, character):
        if character != "Fool" or self.art.has_character(character) is not False:
            return True
        text = ("愚者需要包含该角色的 Steam 游戏版本。当前可在 Steam 库的游戏属性中选择 public-beta。"
                if engine_language(self.language) == "zh" else
                "The Fool requires a Steam build with the character. Select public-beta under the game's Steam properties.")
        messagebox.showinfo(self.text("window"), text, parent=self.root)
        return False

    def refresh(self):
        selected_character = max(0, self.character_box.current())
        self.character_box.configure(values=character_names(self.language))
        self.character_box.current(selected_character)
        self.root.title(self.text("window"))
        for widget, label in ((self.title, "title"), (self.character_label, "character"),
                              (self.ascension_label, "ascension"), (self.persona_label, "ai_character"),
                              (self.load_button, "load"), (self.start_button, "start"),
                              (self.save_label, "choose_save"), (self.saves_refresh, "refresh"),
                              (self.persona_panel_button, "persona_panel")):
            widget.configure(text=self.text(label))
        self.refresh_settings_menu()
        self.refresh_navigation()
        for name, button in self.modes.items():
            button.configure(text=self.text(name),
                             style="Selected.TButton" if name == self.mode else "TButton")

        if self.mode == "manual":
            for widget in self.manual_fields:
                widget.grid()
            self.api_panel.grid_remove()
            self.save_panel.grid()
            self.refresh_saves()
        else:
            for widget in self.manual_fields:
                widget.grid_remove()
            self.refresh_personas()
            self.api_panel.grid()
            self.save_panel.grid_remove()
        self.status_label.configure(text=self.text(self.status_key) if self.status_key else "")

    def start_game(self):
        if self.child is not None:
            return
        if self.mode == "manual":
            character = CHARACTERS[self.character_box.current()]
            if not self.character_ready(character):
                return
            options = ["--character", character, "--ascension", self.ascension_box.get()]
            self.launch_console("play", ["--lang", engine_language(self.language), *options])
            return

        if not self.expression_module:
            return
        card = self.selected_persona()
        if not self.character_ready(card["character"]):
            return
        provider = card["provider"]
        package, endpoint, env_name = PROVIDERS[provider]
        key = self.api_keys[provider].get().strip()
        model = card["model"]
        if not key:
            messagebox.showerror(self.text("window"), self.text("missing_key", provider=provider), parent=self.root)
            self.show_api_settings()
            return
        if importlib.util.find_spec(package) is None:
            if messagebox.askyesno(self.text("window"), self.text("missing_sdk", package=package), parent=self.root):
                self.launch_console("install", [package])
            return

        options = ["--character", card["character"], "--ascension", str(card["ascension"]),
                   "--provider", package, "--base-url", endpoint, "--model", model]
        if card["trial"]:
            options += ["--max-steps", "20"]
        self.launch_console("agent", options, credentials={env_name: key}, persona=(self.persona_id, card["name"]))

    def load_save(self):
        if self.child is not None:
            return
        index = self.save_box.current()
        if not 0 <= index < len(self.saves):
            return
        selected = self.saves[index]
        flag = save_option(selected)
        if flag is None:
            messagebox.showerror(self.text("window"), self.text("bad_save"), parent=self.root)
            self.refresh_saves()
            return
        self.launch_console("play", ["--lang", engine_language(self.language), flag, str(selected)])

    def launch_console(self, task, options, credentials=None, persona=None):
        bundled = self.project / "runtime" / "dotnet" / "dotnet.exe"
        if task != "install" and not bundled.is_file() and shutil.which("dotnet") is None:
            messagebox.showerror(self.text("window"), self.text("missing_dotnet"), parent=self.root)
            return
        python = Path(sys.executable).with_name("python.exe")
        if not python.is_file():
            messagebox.showerror(self.text("window"), self.text("missing_python"), parent=self.root)
            return
        env = dict(os.environ)
        for secret in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(secret, None)
        env.update(credentials or {})
        env["DOTNET_ROLL_FORWARD"] = "LatestPatch"
        if persona:
            env["STS2_EXPRESSION_SETTINGS"] = str(PREFERENCES_PATH)
            env["STS2_EXPRESSION_CARD"], env["STS2_EXPRESSION_NAME"] = persona
            env["STS2_EXPRESSION_LANGUAGE"] = self.language
        started = int(datetime.now().timestamp())
        try:
            self.child = subprocess.Popen(
                [str(python), "-B", "-X", "utf8", str(LAUNCHER), "--console", self.language, task, *options],
                cwd=self.project, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except OSError as error:
            messagebox.showerror(self.text("window"), str(error), parent=self.root)
            return
        self.console_started = started if task != "install" else None
        self.start_button.state(["disabled"])
        self.load_button.state(["disabled"])
        self.status_key = "installing" if task == "install" else "running"
        self.status_label.configure(text=self.text(self.status_key))
        self.root.after(450, self.poll_console)

    def poll_console(self):
        if self.child.poll() is None:
            if self.page == "history" and self.history.detail_tab in ("analysis_tab", "map_tab"):
                self.history.refresh()
            self.root.after(1200, self.poll_console)
            return
        self.child = None
        self.console_started = None
        self.start_button.state(["!disabled"])
        if self.mode == "manual":
            self.refresh_saves()
        self.status_key = "finished"
        self.status_label.configure(text=self.text(self.status_key))
        if self.page == "history":
            self.history.refresh()


def playable_saves(folder):
    try:
        files = list(folder.iterdir())
    except OSError:
        return []
    entries = []
    for file in files:
        if file.suffix.lower() not in (".save", ".json") or not file.is_file() or not save_option(file):
            continue
        try:
            entries.append((file.stat().st_mtime_ns, file))
        except OSError:
            continue
    return [file for _, file in sorted(entries, key=lambda entry: (entry[0], entry[1].name.casefold()), reverse=True)]


def default_save_folder(project):
    local = (project / "saves").resolve()
    if playable_saves(local):
        return local

    native = {}
    for variable in ("APPDATA", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if not root:
            continue
        steam = Path(root) / "SlayTheSpire2" / "steam"
        for folder in steam.glob("*/profile*/saves"):
            try:
                if folder.is_dir():
                    native[folder.resolve()] = folder.stat().st_mtime_ns
            except OSError:
                continue
    candidates = sorted(native, key=native.get, reverse=True)
    for folder in candidates:
        if playable_saves(folder):
            return folder
    return candidates[0] if candidates else local


def save_option(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    suffix = path.suffix.lower()
    if suffix == ".json" and isinstance(data.get("actions"), list):
        if isinstance(data.get("character"), str) and isinstance(data.get("seed"), str):
            return "--load"
    if suffix == ".save" and isinstance(data.get("players"), list) and data["players"]:
        if all(isinstance(player, dict) for player in data["players"]):
            return "--continue"
    return None


def is_project(path):
    return (path / "python" / "play.py").is_file() and (path / "agent" / "llm_agent.py").is_file()


def choose_project(root):
    if is_project(LAUNCHER.parent):
        return LAUNCHER.parent
    saved = RunHistory.read_metadata(PREFERENCES_PATH).get("ui_language")
    messages = TEXT[saved] if isinstance(saved, str) and saved in TEXT else TEXT["zh"]
    while True:
        selected = filedialog.askdirectory(parent=root, title=messages["pick_project"], initialdir=LAUNCHER.parent, mustexist=True)
        if not selected:
            return None
        path = Path(selected)
        if is_project(path):
            return path
        messagebox.showerror(messages["window"], messages["bad_project"], parent=root)


def run_recorded_game(language, task, options):
    project = Path.cwd()
    sys.path.insert(0, str(project / "python"))
    import game_log

    archive = RunArchive(HISTORY_DIR, language, options)
    original_input = builtins.input
    original_logger = game_log.GameLogger
    original_popen = subprocess.Popen

    class ArchivedLogger(original_logger):
        def __init__(self, character, seed, enabled=True):
            game_log.LOG_DIR = str(archive.start(character, seed))
            super().__init__(character, seed, enabled)

        def log_state(self, state):
            super().log_state(state)
            archive.observe_state(self.scene_entry("state", state))

        def log_action(self, action):
            super().log_action(action)
            archive.observe_action(self.scene_entry("action", action))

        def scene_entry(self, kind, data):
            return {"step": self._step, "ts": datetime.now().astimezone().isoformat(), "type": kind, "data": data}

    def record_input(prompt=""):
        sys.stdout.write(str(prompt))
        sys.stdout.flush()
        answer = original_input()
        archive.write(f"\n{TEXT[language]['player']} › {answer}\n")
        return answer

    def launch_engine(command, *args, **kwargs):
        if (archive.transcript is not None and kwargs.get("stderr") == subprocess.PIPE
                and isinstance(command, list) and str(command[-1]).endswith(("Sts2Headless.csproj", "Sts2Headless.dll"))):
            # The interactive CLI does not drain engine stderr. Redirect it so the pipe cannot fill.
            with (archive.folder / "engine.stderr.log").open("ab") as diagnostics:
                return original_popen(command, *args, **{**kwargs, "stderr": diagnostics})
        return original_popen(command, *args, **kwargs)

    exit_code = 1
    game_log.GameLogger = ArchivedLogger
    builtins.input = record_input
    if task == "play":
        subprocess.Popen = launch_engine
    old_argv = sys.argv
    try:
        with redirect_stdout(RecordedStream(sys.stdout, archive)), redirect_stderr(RecordedStream(sys.stderr, archive)):
            try:
                if task == "agent":
                    from play import ensure_setup

                    ensure_setup()
                    os.environ["STS2_RUN_HISTORY_DIR"] = str(HISTORY_DIR)
                    entry = project / "agent" / "llm_agent.py"
                else:
                    entry = project / "python" / "play.py"
                sys.argv = [str(entry), *options]
                runpy.run_path(str(entry), run_name="__main__")
                exit_code = 0
            except SystemExit as error:
                if error.code is None or isinstance(error.code, int):
                    exit_code = error.code or 0
                else:
                    print(error.code, file=sys.stderr)
            except KeyboardInterrupt:
                exit_code = 130
            except Exception:
                traceback.print_exc()
    finally:
        sys.argv = old_argv
        builtins.input = original_input
        game_log.GameLogger = original_logger
        subprocess.Popen = original_popen
        archive.finish(exit_code)
    return exit_code


def run_console(language, task, options):
    if task == "install":
        try:
            exit_code = subprocess.call([sys.executable, "-m", "pip", "install", "--upgrade", *options])
        except KeyboardInterrupt:
            exit_code = 130
        except OSError as error:
            print(error, file=sys.stderr)
            exit_code = 1
    else:
        exit_code = run_recorded_game(language, task, options)

    if (task != "play" or exit_code) and sys.stdin.isatty():
        try:
            input("\n" + TEXT[language]["close_console"])
        except (EOFError, KeyboardInterrupt):
            pass
    return exit_code


def main():
    if sys.argv[1:2] == ["--console"]:
        language, task, *options = sys.argv[2:]
        return run_console(language if language in TEXT else "en", task, options)

    root = tk.Tk()
    root.withdraw()
    project = choose_project(root)
    if project is None:
        root.destroy()
        return 0

    Launcher(root, project)
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2)
    y = max(0, (root.winfo_screenheight() - root.winfo_reqheight()) // 3)
    root.geometry(f"+{x}+{y}")
    root.deiconify()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
