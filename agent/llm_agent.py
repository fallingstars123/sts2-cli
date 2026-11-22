#!/usr/bin/env python3
"""LLM agent that plays Slay the Spire 2 through the sts2-cli headless engine.

Each decision point is rendered as compact text plus a numbered list of legal
actions; the LLM answers with JSON naming one option. Two providers:

  anthropic  - Claude via the Anthropic API      (env: ANTHROPIC_API_KEY)
  openai     - any OpenAI-compatible endpoint    (env: OPENAI_API_KEY, OPENAI_BASE_URL)
               e.g. OpenAI, DeepSeek, OpenRouter, Qwen, Kimi, Ollama, LM Studio

Examples:
  python agent/llm_agent.py --provider anthropic
  python agent/llm_agent.py --provider openai --model gpt-5 --character Silent
  python agent/llm_agent.py --provider openai --base-url https://api.deepseek.com --model deepseek-flash
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
sys.path.insert(0, os.path.join(ROOT, "agent"))
from game_log import GameLogger  # noqa: E402
from portable_runtime import engine_command  # noqa: E402
from run_expression import expression_prompt, profile_for, reply_message  # noqa: E402
from run_stats import completed_runs, estimated_wins, similar_runs, stage  # noqa: E402

PROJECT = os.path.join(ROOT, "src", "Sts2Headless", "Sts2Headless.csproj")
CHARACTERS = ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]
BUILD_DECISIONS = {"card_reward", "bundle_select", "shop", "event_choice", "rest_site", "card_select"}
PLAN_FIELDS = ("direction", "priorities", "pivot")

SYSTEM_PROMPT = """You are an expert Slay the Spire 2 player playing a full run, aiming to beat the final boss.
At every step you get the current game state and a numbered list of LEGAL actions.
Think about the situation, then answer with ONLY a JSON object, no other text:
  {"choice": <option number>}
For a multi-card selection step you may instead answer:
  {"indices": [<card index>, ...]}
If player-facing commentary is enabled, you may add a short "message" on anything worth sharing.
Use any historical estimate as background. Choose what to discuss or omit the message.
When asked for a build plan, add a "plan" object to either reply with three short strings:
  "direction", "priorities", and "pivot" (evidence that would change the current direction).
Base the plan on the actual deck and relics, plus the selected change if it succeeds.
Stay flexible until the run supports a clear direction. Unknown rooms remain unknown.

Strategy reminders:
- Combat: compare incoming damage (enemy intents) with your block. Block when the hit would hurt a lot, otherwise deal damage.
  Kill enemies when you can finish them. Play 0-cost and setup/power cards early. Don't end turn with unused energy if a useful card is playable.
- Use potions in dangerous fights (elites, bosses, or when HP is low); don't hoard them until death.
- Card rewards: pick cards that fix your deck's weaknesses (scaling, block, card draw, AoE). Skipping is fine when nothing helps; avoid bloating the deck.
- Map: take elites when healthy for relics, rest sites when low. Shops are good with 150+ gold.
- Rest sites: rest if HP is below ~50%, otherwise upgrade (smith) a key card."""


# ---------------------------------------------------------------- text helpers

_TPL = re.compile(r"\{(\w+)((?::[^{}]*(?:\{[^{}]*\}[^{}]*)*)?)\}")


def fill(desc, *sources):
    """Replace {Name:...} placeholders with numbers from stats/vars dicts."""
    if not desc:
        return ""
    vals = {}
    for s in sources:
        if isinstance(s, dict):
            for k, v in s.items():
                vals[k.lower()] = v

    def sub(m):
        v = vals.get(m.group(1).lower())
        fmt = m.group(2)
        if fmt.startswith(":plural:"):  # {X:plural:one|many}, "{}" stands for the value
            forms = fmt[len(":plural:"):].split("|")
            word = forms[0] if (v == 1 or len(forms) == 1) else forms[1]
            return word.replace("{}", str(v) if v is not None else "?")
        return str(v) if v is not None else m.group(1)

    return _TPL.sub(sub, desc).replace("\n", " ")


def card_text(c):
    kws = ", ".join(c.get("keywords") or [])
    up = "+" if c.get("upgraded") else ""
    cost = c.get("cost", "?")
    if c.get("star_cost") is not None:
        cost = f"{cost}E/{c['star_cost']}*"
    s = f"{c.get('name')}{up} [{cost}] {c.get('type', '')}: {fill(c.get('description'), c.get('stats'), c.get('vars'))}"
    if kws:
        s += f" ({kws})"
    return s


def powers_text(pws):
    if not pws:
        return "none"
    return ", ".join(f"{p.get('name')} {p.get('amount')}" for p in pws)


def player_text(p, with_deck=True):
    lines = [f"HP {p.get('hp')}/{p.get('max_hp')}  Gold {p.get('gold')}  Block {p.get('block', 0)}"]
    rel = p.get("relics") or []
    if rel:
        lines.append("Relics: " + "; ".join(f"{r['name']} ({fill(r.get('description'), r.get('vars'))})" for r in rel))
    pots = [x for x in (p.get("potions") or []) if x]
    lines.append("Potions: " + ("; ".join(f"[{x.get('index')}] {x['name']} ({fill(x.get('description'), x.get('vars'))})" for x in pots) if pots else "none"))
    if with_deck and p.get("deck"):
        counts = {}
        for c in p["deck"]:
            n = c["name"] + ("+" if c.get("upgraded") else "")
            counts[n] = counts.get(n, 0) + 1
        lines.append(f"Deck ({p.get('deck_size')}): " + ", ".join(f"{n} x{k}" if k > 1 else n for n, k in counts.items()))
    return "\n".join(lines)


def context_text(s):
    c = s.get("context") or {}
    boss = (c.get("boss") or {}).get("name")
    return f"Act {c.get('act')} ({c.get('act_name')}), floor {c.get('floor')}, room {c.get('room_type')}, act boss: {boss}"


def map_lookahead(choices, full_map):
    """Describe the current act's visible routes reachable from legal next rooms."""
    if full_map.get("type") != "map":
        return ""

    def coordinate(node):
        return node["row"], node["col"]

    def label(position):
        row, col = position
        return f"r{row}c{col}"

    nodes = {coordinate(node): node for row in full_map.get("rows", []) for node in row}
    if boss := full_map.get("boss"):
        nodes.setdefault(coordinate(boss), boss)

    reachable = set()
    pending = [coordinate(choice) for choice in choices]
    while pending:
        position = pending.pop()
        if position in reachable or position not in nodes:
            continue
        reachable.add(position)
        pending.extend(coordinate(child) for child in nodes[position].get("children") or [])

    lines = []
    for position in sorted(reachable):
        node = nodes[position]
        children = sorted(coordinate(child) for child in node.get("children") or []
                          if coordinate(child) in reachable)
        onward = " -> " + ", ".join(map(label, children)) if children else ""
        lines.append(f"{label(position)} {node.get('type', 'Unknown')}{onward}")
    if not lines:
        return ""
    return "Visible routes this act (r = row, c = column):\n" + "\n".join(lines)


def build_inventory(state):
    player = state.get("player") or {}
    cards = sorted((str(c.get("id") or c.get("name")), bool(c.get("upgraded"))) for c in player.get("deck") or [])
    relics = sorted(str(r.get("id") or r.get("name")) for r in player.get("relics") or [])
    return cards, relics


def clean_plan(candidate):
    if not isinstance(candidate, dict):
        return None
    plan = {}
    for field in PLAN_FIELDS:
        value = candidate.get(field)
        if not isinstance(value, str) or not value.strip():
            return None
        plan[field] = " ".join(value.split())[:180]
    return plan


class BuildMemory:
    def __init__(self, log_path):
        self.plan = None
        self.inventory = None
        self.path = Path(log_path).with_suffix(".plan.jsonl") if log_path else None

    def prompt(self, state):
        sections = []
        if self.plan:
            sections.append("Current build plan: " + self.summary())
        decision = state.get("decision")
        refresh = decision in BUILD_DECISIONS or self.inventory != build_inventory(state)
        if decision != "combat_play" and refresh:
            sections.append("Include a short updated plan in your reply, accounting for the action you choose.")
        return "\n".join(sections)

    def summary(self):
        return " | ".join(f"{field}: {self.plan[field]}" for field in PLAN_FIELDS)

    def remember(self, plan, step, decision, action, previous, result):
        if not plan or result.get("type") == "error":
            return
        self.inventory = build_inventory(result if result.get("player") else previous)
        if plan == self.plan:
            return
        self.plan = plan
        print("  Build plan: " + self.summary())
        if self.path:
            record = {"step": step, "decision": decision, "action": action, "plan": plan}
            try:
                with self.path.open("a", encoding="utf-8") as log:
                    log.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError as error:
                print(f"  ! Could not write build-plan log: {error}", file=sys.stderr)


# ------------------------------------------------------- legal-action builder

def act(action, **args):
    cmd = {"cmd": "action", "action": action}
    if args:
        cmd["args"] = args
    return cmd


def build_options(s):
    """Return (state_text, options) where options = [(label, command)]."""
    d = s.get("decision")
    p = s.get("player") or {}
    opts = []
    parts = [f"Decision: {d}", context_text(s)]

    if d == "combat_play":
        parts.append(f"Round {s.get('round')}  Energy {s.get('energy')}/{s.get('max_energy')}  "
                     f"Draw pile {s.get('draw_pile_count')}  Discard {s.get('discard_pile_count')}")
        parts.append("You: " + player_text(p, with_deck=False))
        parts.append("Your powers: " + powers_text(s.get("player_powers")))
        if s.get("orbs") is not None:
            parts.append(f"Orbs ({s.get('orb_slots')} slots): " + ", ".join(
                f"{o.get('name')}(passive {o.get('passive')}, evoke {o.get('evoke')})" for o in s["orbs"]))
        enemies = [e for e in (s.get("enemies") or []) if e.get("hp", 0) > 0]
        parts.append("Enemies:")
        for e in enemies:
            intents = []
            for it in e.get("intents") or []:
                t = it.get("type")
                if it.get("damage") is not None:
                    t += f" {it['damage']}" + (f"x{it['hits']}" if it.get("hits") else "")
                intents.append(t)
            parts.append(f"  [{e['index']}] {e['name']} HP {e['hp']}/{e['max_hp']} Block {e.get('block', 0)} "
                         f"Intent: {', '.join(intents) or '?'}  Powers: {powers_text(e.get('powers'))}")
        incoming = sum((it.get("total_damage") or it.get("damage") or 0)
                       for e in enemies for it in (e.get("intents") or []) if it.get("damage") is not None)
        parts.append(f"Total incoming attack damage this turn: {incoming} (your block: {p.get('block', 0)})")
        parts.append("Hand:")
        energy = s.get("energy", 0)
        for c in s.get("hand") or []:
            playable = c.get("can_play") and (c.get("cost", 0) or 0) <= energy
            parts.append(f"  ({c['index']}) {card_text(c)}" + ("" if playable else "  [unplayable now]"))
            if not playable:
                continue
            if c.get("target_type") == "AnyEnemy":
                for e in enemies:
                    dmg = next((x.get("total_damage") or x.get("damage") for x in (c.get("damage_by_target") or [])
                                if x.get("target_index") == e["index"]), None)
                    extra = f" for {dmg} dmg" if dmg is not None else ""
                    opts.append((f"Play {c['name']} on [{e['index']}] {e['name']}{extra}",
                                 act("play_card", card_index=c["index"], target_index=e["index"])))
            else:
                opts.append((f"Play {c['name']}", act("play_card", card_index=c["index"])))
        for pot in [x for x in (p.get("potions") or []) if x]:
            if pot.get("target_type") == "AnyEnemy":
                for e in enemies:
                    opts.append((f"Use potion {pot['name']} on [{e['index']}] {e['name']}",
                                 act("use_potion", potion_index=pot["index"], target_index=e["index"])))
            else:
                opts.append((f"Use potion {pot['name']}", act("use_potion", potion_index=pot["index"])))
        opts.append(("End turn", act("end_turn")))

    elif d == "map_select":
        parts.append(player_text(p))
        for ch in s.get("choices") or []:
            opts.append((f"Go to {ch.get('type')} (col {ch['col']}, row {ch['row']})",
                         act("select_map_node", col=ch["col"], row=ch["row"])))

    elif d == "card_reward":
        parts.append(player_text(p))
        for c in s.get("cards") or []:
            opts.append((f"Take {card_text(c)}", act("select_card_reward", card_index=c["index"])))
        if s.get("can_skip", True):
            opts.append(("Skip the card reward", act("skip_card_reward")))

    elif d == "event_choice":
        parts.append(f"Event: {s.get('event_name')}  {fill(s.get('description'))}")
        parts.append(player_text(p))
        for o in s.get("options") or []:
            if o.get("is_locked"):
                continue
            opts.append((f"{o.get('title')}: {fill(o.get('description'), o.get('vars'))}",
                         act("choose_option", option_index=o["index"])))
        if not opts:
            opts.append(("Leave", act("leave_room")))

    elif d == "rest_site":
        parts.append(player_text(p))
        for o in s.get("options") or []:
            if o.get("is_enabled", True):
                opts.append((f"{o.get('option_id') or o.get('name')}", act("choose_option", option_index=o["index"])))
        opts.append(("Leave the rest site", act("leave_room")))

    elif d == "shop":
        parts.append(player_text(p))
        gold = p.get("gold", 0)
        for c in s.get("cards") or []:
            if c.get("is_stocked") and c.get("cost", 1e9) <= gold:
                opts.append((f"Buy card {card_text({**c, 'cost': c.get('card_cost')})} for {c['cost']}g"
                             + (" (on sale)" if c.get("on_sale") else ""), act("buy_card", card_index=c["index"])))
        for r in s.get("relics") or []:
            if r.get("is_stocked") and r.get("cost", 1e9) <= gold:
                opts.append((f"Buy relic {r['name']} ({fill(r.get('description'))}) for {r['cost']}g",
                             act("buy_relic", relic_index=r["index"])))
        for x in s.get("potions") or []:
            if x.get("is_stocked") and x.get("cost", 1e9) <= gold:
                opts.append((f"Buy potion {x['name']} ({fill(x.get('description'))}) for {x['cost']}g",
                             act("buy_potion", potion_index=x["index"])))
        rc = s.get("card_removal_cost")
        if rc is not None and rc <= gold:
            opts.append((f"Remove a card from your deck for {rc}g", act("remove_card")))
        opts.append(("Leave the shop", act("leave_room")))

    elif d == "bundle_select":
        parts.append(player_text(p))
        for i, b in enumerate(s.get("bundles") or []):
            cards = b.get("cards") if isinstance(b, dict) else b
            names = "; ".join(card_text(c) for c in (cards or []))
            opts.append((f"Bundle: {names}", act("select_bundle", bundle_index=b.get("index", i) if isinstance(b, dict) else i)))

    elif d == "card_select":
        parts.append(player_text(p))
        mn, mx = s.get("min_select", 1), s.get("max_select", 1)
        parts.append(f"Select between {mn} and {mx} card(s). Cards:")
        for c in s.get("cards") or []:
            parts.append(f"  ({c['index']}) {card_text(c)}")
        if mx == 1:
            for c in s.get("cards") or []:
                opts.append((f"Select {c['name']}", act("select_cards", indices=str(c["index"]))))
        if mn == 0:
            opts.append(("Select nothing / skip", act("skip_select")))

    return "\n".join(parts), opts


# --------------------------------------------------------------- LLM backends

class LLM:
    def __init__(self, provider, model, base_url, effort):
        self.provider = provider
        self.effort = effort
        self.in_tok = self.out_tok = 0
        if provider == "random":  # offline smoke test, no API calls
            import random
            self.rng, self.model = random.Random(0), "random"
        elif provider == "anthropic":
            import anthropic
            self.anthropic = anthropic
            self.client = anthropic.Anthropic(base_url=base_url) if base_url else anthropic.Anthropic()
            self.model = model or "claude-opus-5-5"
        else:
            import openai
            self.client = openai.OpenAI(base_url=base_url or os.environ.get("OPENAI_BASE_URL"))
            self.model = model or os.environ.get("OPENAI_MODEL") or "gpt-5"

    def ask(self, prompt):
        if self.provider == "random":
            n = len(re.findall(r"^\d+\. ", prompt.split("Legal actions:")[-1], re.M))
            return json.dumps({"choice": self.rng.randrange(max(n, 1)), "reason": "random"})
        if self.provider == "anthropic":
            request = {"model": self.model, "max_tokens": 16000, "system": SYSTEM_PROMPT,
                       "messages": [{"role": "user", "content": prompt}]}
            if self.effort:
                request["output_config"] = {"effort": self.effort}
            try:
                r = self.client.messages.create(**request)
            except self.anthropic.BadRequestError as error:
                detail = str(error).lower()
                if not self.effort or not any(field in detail for field in ("effort", "output_config")):
                    raise
                if not any(term in detail for term in ("unsupported", "not support", "extra inputs", "unknown", "invalid")):
                    raise
                self.effort = None
                request.pop("output_config")
                r = self.client.messages.create(**request)
            self.in_tok += r.usage.input_tokens
            self.out_tok += r.usage.output_tokens
            if r.stop_reason == "refusal":
                return ""
            return "".join(b.text for b in r.content if b.type == "text")
        r = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        )
        if r.usage:
            self.in_tok += r.usage.prompt_tokens or 0
            self.out_tok += r.usage.completion_tokens or 0
        return r.choices[0].message.content or ""


def parse_reply(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        nums = re.findall(r'"choice"\s*:\s*(\d+)', m.group(0))
        return {"choice": int(nums[0])} if nums else None


# --------------------------------------------------------------- game process

class Engine:
    def __init__(self, verbose):
        self.proc = subprocess.Popen(
            engine_command(ROOT, "dotnet", PROJECT),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None if verbose else subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1)
        self.q = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            self.q.put(line)
        self.q.put(None)

    def read(self, timeout=60):
        while True:
            line = self.q.get(timeout=timeout)
            if line is None:
                raise RuntimeError("engine exited")
            if line.startswith("{"):
                return json.loads(line)

    def send(self, cmd):
        self.proc.stdin.write(json.dumps(cmd) + "\n")
        self.proc.stdin.flush()
        return self.read()

    def close(self):
        try:
            self.proc.stdin.write('{"cmd":"quit"}\n')
            self.proc.stdin.flush()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


# ------------------------------------------------------------------- main loop

def play(args):
    llm = LLM(args.provider, args.model, args.base_url, args.effort)
    seed = args.seed or f"llm_{int(time.time())}"
    print(f"Provider {args.provider}, model {llm.model}, {args.character}, A{args.ascension}, seed {seed}")
    logger = GameLogger(args.character, seed, enabled=True)
    memory = BuildMemory(logger.path)
    archive_root = os.environ.get("STS2_RUN_HISTORY_DIR")
    provider = {"openai": "DeepSeek", "anthropic": "Claude", "random": "random"}[args.provider]
    target = {"provider": provider, "model": llm.model, "character": args.character,
              "ascension": args.ascension, "started": datetime.now().astimezone().isoformat()}
    cohort = similar_runs(completed_runs(archive_root), target) if archive_root else []
    preferences_path = os.environ.get("STS2_EXPRESSION_SETTINGS")
    persona_id = os.environ.get("STS2_EXPRESSION_CARD", "")
    ui_language = os.environ.get("STS2_EXPRESSION_LANGUAGE", "en")
    expression_log = Path(logger.path).with_suffix(".expression.jsonl") if logger.path else None
    eng = Engine(args.debug)
    history = []
    try:
        ready = eng.read(timeout=120)
        if ready.get("type") != "ready":
            raise RuntimeError(f"unexpected engine greeting: {ready}")
        cmd = {"cmd": "start_run", "character": args.character, "seed": seed, "ascension": args.ascension}
        logger.log_action(cmd)
        s = eng.send(cmd)
        logger.log_state(s)
        last_error = None
        prev_state = s
        archived_acts = set()
        for step in range(args.max_steps):
            if s.get("type") == "error":
                print(f"  ! engine error: {s.get('message')}")
                if s.get("error_code") == "combat_turn_timeout":
                    break
                last_error = s.get("message")
                s = prev_state
            d = s.get("decision")
            if d == "game_over":
                pl = s.get("player") or {}
                c = s.get("context") or {}
                print(f"\n{'VICTORY' if s.get('victory') else 'DEFEAT'} - act {c.get('act')} floor {c.get('floor')}, "
                      f"HP {pl.get('hp')}/{pl.get('max_hp')}, deck {pl.get('deck_size')}")
                break
            prev_state = s
            text, opts = build_options(s)
            chapter = (s.get("context") or {}).get("act")
            full_map = {}
            if chapter and (chapter not in archived_acts or (d == "map_select" and len(opts) > 1)):
                map_cmd = {"cmd": "get_map"}
                logger.log_action(map_cmd)
                full_map = eng.send(map_cmd)
                logger.log_state(full_map)
                if full_map.get("type") == "map" and full_map.get("rows"):
                    archived_acts.add(chapter)
            proposed_plan = None
            message = ""
            if not opts and d != "card_select":
                cmd = act("proceed")
                reason = "(auto)"
            elif len(opts) == 1:
                cmd, reason = opts[0][1], "(only option)"
            else:
                profile = profile_for(preferences_path, persona_id, provider, ui_language)
                sections = [f"Character: {args.character} · Ascension: {args.ascension}", text]
                if d == "map_select":
                    sections.append(map_lookahead(s.get("choices") or [], full_map))
                sections.append(memory.prompt(s))
                wins, total = estimated_wins(cohort, stage(s.get("context")))
                if total:
                    sections.append(f"Historical win estimate at this progress: {wins / total:.0%} "
                                    f"({wins}/{total} prior completed runs of the same model, character and ascension "
                                    "that reached this stage; small samples can be noisy).")
                sections.append(expression_prompt(profile))
                sections.append("Recent actions:\n" + ("\n".join(history[-12:]) or "none"))
                if last_error:
                    sections.append(f"Your previous action failed: {last_error}. Choose something else.")
                sections.append("Legal actions:\n" + "\n".join(f"{i}. {lbl}" for i, (lbl, _) in enumerate(opts)))
                prompt = "\n\n".join(section for section in sections if section)
                cmd, reason = None, ""
                for attempt in range(3):
                    try:
                        reply = parse_reply(llm.ask(prompt))
                    except Exception as e:  # network / API errors
                        print(f"  ! LLM error: {e}")
                        time.sleep(3 * (attempt + 1))
                        continue
                    if not isinstance(reply, dict):
                        continue
                    if "indices" in reply and d == "card_select":
                        indices = reply["indices"]
                        allowed = {c["index"] for c in s.get("cards") or []}
                        if (isinstance(indices, list) and all(type(i) is int and i in allowed for i in indices)
                                and len(set(indices)) == len(indices)
                                and s.get("min_select", 1) <= len(indices) <= s.get("max_select", 1)):
                            cmd = act("select_cards", indices=",".join(map(str, indices))) if indices else act("skip_select")
                    ch = reply.get("choice")
                    if cmd is None and type(ch) is int and 0 <= ch < len(opts):
                        cmd = opts[ch][1]
                    if cmd is not None:
                        proposed_plan = clean_plan(reply.get("plan"))
                        if args.provider != "random":
                            message = reply_message(reply, profile)
                        reason = "random" if args.provider == "random" else " ".join(message.split())
                        break
                if cmd is None:
                    cmd = opts[0][1] if opts else act("skip_select")
                    reason = "(fallback: could not parse LLM reply)"
            last_error = None
            label = next((l for l, c in opts if c == cmd), json.dumps(cmd.get("args", cmd.get("action"))))
            hp = (s.get("player") or {}).get("hp")
            line = f"[{d}] {label}"
            history.append(line)
            print(f"{step:4d} HP {hp:>3} | {line}  -- {reason}")
            logger.log_action(cmd)
            s = eng.send(cmd)
            logger.log_state(s)
            memory.remember(proposed_plan, step, d, cmd, prev_state, s)
            if message and expression_log and s.get("type") != "error":
                position = prev_state.get("context") or {}
                item = {"step": step, "hp": hp, "action": label, "message": message, "name": profile["name"], "persona_id": persona_id,
                        "language": profile["language"], "act": position.get("act"), "floor": position.get("floor")}
                try:
                    with expression_log.open("a", encoding="utf-8") as log:
                        log.write(json.dumps(item, ensure_ascii=False) + "\n")
                except OSError as error:
                    print(f"  ! Could not write commentary log: {error}", file=sys.stderr)
        else:
            print("Reached max steps")
    finally:
        logger.close()
        eng.close()
        print(f"Tokens: {llm.in_tok} in / {llm.out_tok} out.  Log: {logger.path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", choices=["anthropic", "openai", "random"], default="anthropic")
    ap.add_argument("--model", help="model id (default: claude-opus-5-5 / $OPENAI_MODEL or gpt-5)")
    ap.add_argument("--base-url", help="API base URL (OpenAI-compatible endpoints, proxies)")
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"],
                    help="Anthropic effort level (default low: faster and cheaper per move)")
    ap.add_argument("--character", default="Ironclad", choices=CHARACTERS)
    ap.add_argument("--ascension", type=int, default=0)
    ap.add_argument("--seed")
    ap.add_argument("--max-steps", type=int, default=3000)
    ap.add_argument("--debug", action="store_true", help="show engine stderr")
    play(ap.parse_args())


if __name__ == "__main__":
    main()
