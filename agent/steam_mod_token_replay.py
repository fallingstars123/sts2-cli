"""Replay archived Steam Mod sessions offline and estimate model token use.

No provider is called. Each archived decision is fed back through ``choose`` with a fake
Claude client that answers with the action the original run took, so the agent builds the
exact requests it would send today. Those requests are then measured:

* input tokens: an offline estimate from request characters, calibrated against the
  provider-reported usage recorded in the archived journals (``--calibrate``);
* cache reads and writes: a simulation of Anthropic prompt caching (prefix match at
  ``cache_control`` breakpoints, 5-minute TTL measured from the archived timestamps);
* output tokens: the archived output of each decision that is still model-backed. A
  decision the new code resolves locally is counted as zero.

Usage:
  steam_mod_token_replay.py SESSION_DIR... [--agent-dir DIR] [--fields] [--json]
"""

import argparse
from collections import Counter, deque
from datetime import datetime
from hashlib import sha256
import importlib
import inspect
import json
from pathlib import Path
import shutil
import sys
from tempfile import mkdtemp
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "python"))
# Fitted with --calibrate on the Regent floor-48 boss journal (42 requests, median error 0.6%).
CHARS_PER_TOKEN = 2.256
REQUEST_OVERHEAD_TOKENS = 365
CACHE_TTL_SECONDS = 300
LOOKBACK_BLOCKS = 20


def _load_agent(agent_dir):
    agent_dir = Path(agent_dir).resolve()
    for name in [module for module in sys.modules if module.startswith("steam_mod") or module == "llm_agent"]:
        del sys.modules[name]
    sys.path.insert(0, str(agent_dir))
    try:
        return importlib.import_module("steam_mod_agent")
    finally:
        sys.path.remove(str(agent_dir))


def _text_of(content):
    if isinstance(content, str):
        return [content]
    return [block.get("text", "") for block in content if isinstance(block, dict)]


def _blocks(request):
    """Flatten a messages.create call into (text, has_breakpoint) blocks in render order."""
    blocks = []
    system = request.get("system") or []
    if isinstance(system, str):
        system = [{"type": "text", "text": system}]
    for block in system:
        blocks.append((block.get("text", ""), bool(block.get("cache_control"))))
    for message in request.get("messages", []):
        content = message["content"]
        if isinstance(content, str):
            blocks.append((content, bool(message.get("cache_control"))))
            continue
        for block in content:
            blocks.append((block.get("text", ""), bool(block.get("cache_control"))))
    if request.get("cache_control") and blocks:          # top-level automatic caching
        text, _ = blocks[-1]
        blocks[-1] = (text, True)
    return blocks


def tokens(chars):
    return chars / CHARS_PER_TOKEN


class CacheModel:
    """Approximate Anthropic prompt caching: entries exist at written breakpoints only."""

    def __init__(self, enabled=True):
        self.entries = {}
        self.enabled = enabled

    def measure(self, request, at):
        blocks = _blocks(request)
        sizes = [len(text) for text, _ in blocks]
        # Conservative: a different schema, effort or thinking setting misses every cached tier.
        config = request.get("output_config", {})
        keys, digest = [], sha256(repr((config.get("format"), config.get("effort"),
                                        request.get("thinking"), request.get("model"))).encode())
        for text, _ in blocks:
            digest.update(text.encode("utf-8"))
            keys.append(digest.copy().hexdigest())
        breakpoints = [index for index, (_, marked) in enumerate(blocks) if marked] if self.enabled else []
        for key in list(self.entries):
            if at - self.entries[key] > CACHE_TTL_SECONDS:
                del self.entries[key]
        read_upto = -1
        for point in breakpoints:
            for index in range(point, max(-1, point - LOOKBACK_BLOCKS), -1):
                if keys[index] in self.entries:
                    read_upto = max(read_upto, index)
                    break
        if read_upto >= 0:
            self.entries[keys[read_upto]] = at
        write_upto = breakpoints[-1] if breakpoints else -1
        for point in breakpoints:
            if point > read_upto:
                self.entries[keys[point]] = at
        read = sum(sizes[:read_upto + 1])
        written = sum(sizes[read_upto + 1:write_upto + 1]) if write_upto > read_upto else 0
        total = sum(sizes)
        return {"chars": total, "read_chars": read, "write_chars": written,
                "uncached_chars": total - read - written}


class FakeMessages:
    def __init__(self, owner):
        self.owner = owner

    def create(self, **request):
        self.owner.requests.append(request)
        answer = self.owner.answer(request)
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(answer))],
            usage=SimpleNamespace(input_tokens=0, output_tokens=0,
                                  cache_read_input_tokens=0, cache_creation_input_tokens=0),
        )


class FakeAnthropic:
    """Answers with the archived choice; the first call of a recheck gets the initial choice."""

    def __init__(self):
        self.messages = FakeMessages(self)
        self.requests = []
        self.script = None

    def answer(self, _request):
        script = self.script
        calls = script.setdefault("calls", 0)
        script["calls"] = calls + 1
        initial = script.get("initial")
        if initial is not None and calls == 0:
            return {"choice": initial}
        answer = {"choice": script["final"]}
        if script.get("sequence"):
            answer["sequence"] = script["sequence"]
        return answer


def _same_move(left, right):
    a, b = left["detail"], right["detail"]
    if left["kind"] != right["kind"]:
        return False
    keys = ("card_instance_id", "target_instance_id") if left["kind"] == "play_card" else (
        ("potion_index", "potion_id", "target_instance_id") if left["kind"] == "use_potion" else ())
    return bool(keys) and all(a.get(key) == b.get(key) for key in keys)


def _journal(session):
    path = Path(session)
    path = path / "actions.jsonl" if path.is_dir() else path
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def _time(row):
    return datetime.fromisoformat(row["utc"]).timestamp()


def replay(session, agent, workdir, *, planned_end_turn=False):
    """Yield one record per archived decision with the requests the agent builds now."""
    from steam_mod_memory import SteamModMemory          # resolved from the loaded agent directory
    from steam_mod_experience import Experience
    from steam_mod_sequence import CombatSequence, can_plan
    from steam_mod_shop import shop_actions

    rows = _journal(session)
    supports = inspect.signature(agent.choose).parameters
    reference = None
    if "reference" in supports:
        from steam_mod_prompt import FightReference
        reference = FightReference()
    memory = SteamModMemory(Path(workdir) / "memory")
    experience = Experience(Path(workdir) / "experience.json", reviewer=None, log=lambda _m: None)
    fake = FakeAnthropic()
    client = agent.ClaudeDecisions(fake, "claude-sonnet-5-5")
    decisions = [index for index, row in enumerate(rows) if row["type"] == "decision"]
    states = {}
    current, serial = None, 0
    label = Path(session).name

    def snapshot(row):
        nonlocal serial
        serial += 1
        keys = ("screen", "state", "run", "actions")
        return {**{key: row.get(key) for key in keys}, "state_id": f"replay-{label}:{serial}:x"}

    for index, row in enumerate(rows):
        if row["type"] in {"start", "observed", "state_changed", "combat_retry_completed"} and row.get("actions") is not None:
            current = snapshot(row)
        if row["type"] == "decision":
            states[index] = current
    recent = deque(maxlen=5)
    sequence = CombatSequence()
    reviewed_turn, reviewed = None, set()
    for position, index in enumerate(decisions):
        row, state = rows[index], states[index]
        taken = row["action"]
        usage = row.get("usage") or {}
        run = state.get("run") or {}
        turn_key = (run.get("act"), run.get("floor"), (state.get("state") or {}).get("turn"))
        notes = memory.context(state)
        if encounter := experience.observe(state):
            notes = {**(notes or {}), "encounter_experience": encounter}
        offered = {**state, "actions": shop_actions(state)}
        retry_kinds = {agent.COMBAT_RETRY, agent.EVENT_RETRY}
        offered["actions"] = [action for action in offered["actions"]
                              if action["kind"] not in retry_kinds or action["id"] == taken["id"]]
        numbers = {action["id"]: number for number, action in enumerate(offered["actions"], 1)}
        if reviewed_turn != turn_key:
            reviewed_turn, reviewed = turn_key, set()
        record = {"session": label, "index": position, "screen": state["screen"], "time": _time(row),
                  "archived": usage, "taken": taken["kind"], "requests": [], "agreed": True}
        before = len(fake.requests)
        forced = getattr(agent, "_forced_action", lambda _s: None)(offered)
        confirm = getattr(agent, "_completed_hand_selection", lambda _s, _r: None)(offered, recent)
        if forced is not None:
            record["resolution"] = "local_forced"
            chosen = forced["id"]
        elif confirm is not None:
            record["resolution"] = "local_confirm"
            chosen = confirm["id"]
            record["agreed"] = chosen == taken["id"]
        elif taken["id"] not in numbers:
            record["resolution"] = "unmatched"
            chosen = taken["id"]
        else:
            script = {"final": numbers[taken["id"]]}
            initial = next((value for key, value in usage.items() if key.startswith("rechecked_")), None)
            if type(initial) is int:
                script["initial"] = initial
            proposed = usage.get("turn_plan_proposed")
            if type(proposed) is int and proposed >= 2:
                plan = [script["final"]]
                for later in decisions[position + 1:position + proposed]:
                    move = rows[later]["action"]
                    match = next((number for number, action in enumerate(offered["actions"], 1)
                                  if _same_move(action, move)), None)
                    if match is None:
                        break
                    plan.append(match)
                # What-if: the model also planned the end turn it took right after this plan.
                # The archive cannot show that, so it is an optimistic estimate (off by default).
                following = position + len(plan)
                if (planned_end_turn and len(plan) == proposed and following < len(decisions)
                        and rows[decisions[following]]["action"]["kind"] == "end_turn"):
                    end = next((number for number, action in enumerate(offered["actions"], 1)
                                if action["kind"] == "end_turn"), None)
                    if end is not None:
                        plan.append(end)
                if len(plan) >= 2:
                    script["sequence"] = plan
            fake.script = script
            options = {"turn_sequence": sequence} if sequence.has_pending or can_plan(offered) else {}
            if reference is not None:
                options["reference"] = reference
            chosen, _strategy, result = agent.choose(client, offered, recent, "", notes,
                                                     reviewed_hazards=frozenset(reviewed), **options)
            reviewed.update(key for key in result if key.startswith("rechecked_"))
            record["resolution"] = ("local_end_turn" if "local_end_turn" in result and len(fake.requests) == before
                                    else "reused_turn_plan" if "reused_turn_plan" in result
                                    else "local_guard" if "end_turn_guard" in result and len(fake.requests) == before
                                    else "local" if len(fake.requests) == before else "model")
            record["rechecks"] = sorted(key for key in result if key.startswith("rechecked_"))
            record["agreed"] = chosen == taken["id"]
        record["requests"] = fake.requests[before:]
        yield record
        # Follow the archived run, whatever the replayed choice was.
        after_row = next((rows[later] for later in range(index + 1, len(rows))
                          if rows[later]["type"] in {"observed", "state_changed", "settlement"}), None)
        action = next((item for item in offered["actions"] if item["id"] == taken["id"]), taken)
        if after_row is None or after_row["type"] != "observed":
            sequence.clear()
            continue
        after = states.get(decisions[position + 1]) if position + 1 < len(decisions) else snapshot(after_row)
        sequence.advance(state, action, after)
        experience.acted(action)
        experience.settle(after)
        memory.record(state, action, after, plan="")
        detail = action["detail"]
        item = detail.get("card_id") or detail.get("potion_id") or detail.get("target") or action["id"]
        target = detail.get("target_index")
        recent.append(f"{action['kind']} {item}" + (f" at enemy index {target}" if type(target) is int else ""))


def measure(records, *, caching=True):
    cache = CacheModel(enabled=caching)
    totals = Counter()
    for record in records:
        archived = record["archived"]
        modeled = bool(record["requests"])
        totals["decisions"] += 1
        totals[record["resolution"]] += 1
        totals["recheck_requests"] += max(0, len(record["requests"]) - 1)
        if record["screen"] == "combat":
            totals["combat_decisions"] += 1
        record["measured"] = []
        for request in record["requests"]:
            sizes = cache.measure(request, record["time"])
            record["measured"].append(sizes)
            overhead = REQUEST_OVERHEAD_TOKENS
            totals["requests"] += 1
            totals["input_tokens"] += tokens(sizes["uncached_chars"]) + overhead
            totals["cache_read_tokens"] += tokens(sizes["read_chars"])
            totals["cache_write_tokens"] += tokens(sizes["write_chars"])
        if modeled:
            totals["model_backed"] += 1
            totals["output_tokens"] += archived.get("completion_tokens") or 0
        totals["archived_input_tokens"] += archived.get("prompt_tokens") or 0
        totals["archived_output_tokens"] += archived.get("completion_tokens") or 0
        totals["archived_cache_read_tokens"] += archived.get("prompt_cache_hit_tokens") or 0
        totals["archived_model_backed"] += 1 if archived.get("prompt_tokens") else 0
        totals["disagreements"] += 0 if record["agreed"] else 1
    # Claude Sonnet 5.5 list-price weights: input 1, 5-minute cache write 1.25, cache read 0.05,
    # output 5 (input-token equivalents). Lets one figure compare caching trade-offs.
    totals["cost_input_equivalent"] = (totals["input_tokens"] + 1.25 * totals["cache_write_tokens"]
                                       + 0.05 * totals["cache_read_tokens"] + 5 * totals["output_tokens"])
    return {key: round(value) for key, value in totals.items()}


def calibrate(records):
    """Least-squares fit of archived input tokens against today's uncached request characters."""
    points = [(sum(len(text) for request in record["requests"] for text, _ in _blocks(request)),
               len(record["requests"]), record["archived"].get("prompt_tokens"))
              for record in records if record["requests"] and record["archived"].get("prompt_tokens")]
    # tokens = chars / k + overhead * requests  ->  solve for 1/k and overhead.
    sxx = sum(c * c for c, _, _ in points); sxr = sum(c * r for c, r, _ in points)
    srr = sum(r * r for _, r, _ in points); sxt = sum(c * t for c, _, t in points)
    srt = sum(r * t for _, r, t in points)
    det = sxx * srr - sxr * sxr
    inverse = (sxt * srr - srt * sxr) / det
    overhead = (sxx * srt - sxr * sxt) / det
    errors = [abs(c * inverse + r * overhead - t) / t for c, r, t in points]
    return {"chars_per_token": round(1 / inverse, 3), "overhead_per_request": round(overhead),
            "points": len(points), "median_abs_error": round(sorted(errors)[len(errors) // 2], 3)}


def field_sizes(records):
    """Characters per top-level context field across model-backed combat requests."""
    sizes = Counter()
    for record in records:
        if record["screen"] != "combat":
            continue
        for request in record["requests"]:
            for message in request.get("messages", []):
                for text in _text_of(message["content"]):
                    start = 0 if text.startswith("{") else text.find("\n{") + 1
                    if start:
                        sizes["(note) " + text[:40]] += start
                    try:
                        data = json.loads(text[start:]) if text.startswith("{") or start else None
                    except ValueError:
                        data = None
                    if not isinstance(data, dict):
                        sizes["(text) " + text[:40]] += len(text) - start
                        continue
                    for key, value in data.items():
                        if isinstance(value, dict) and key in {"state", "run", "combat_summary"}:
                            for inner, part in value.items():
                                sizes[f"{key}.{inner}"] += len(json.dumps(part, ensure_ascii=False, separators=(",", ":")))
                        else:
                            sizes[key] += len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            system = request.get("system")
            sizes["(system prompt)"] += sum(len(text) for text in _text_of(system or ""))
    return sizes


def run(sessions, agent_dir, *, planned_end_turn=False):
    agent = _load_agent(agent_dir)
    records = []
    for session in sessions:
        workdir = Path(mkdtemp(prefix="token-replay-"))
        try:
            records.extend(replay(session, agent, workdir, planned_end_turn=planned_end_turn))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sessions", nargs="+", type=Path)
    parser.add_argument("--agent-dir", type=Path, default=ROOT / "agent")
    parser.add_argument("--fields", action="store_true", help="Show the largest combat context fields.")
    parser.add_argument("--calibrate", action="store_true", help="Fit chars per token to the archived usage.")
    parser.add_argument("--no-cache", action="store_true", help="Measure as if no cache_control were sent.")
    parser.add_argument("--assume-planned-end-turn", action="store_true",
                        help="What-if: each archived plan also ended the turn when the next archived move was End Turn.")
    parser.add_argument("--json", action="store_true")
    options = parser.parse_args(argv)
    records = run(options.sessions, options.agent_dir, planned_end_turn=options.assume_planned_end_turn)
    if options.calibrate:
        print(json.dumps(calibrate(records)))
        return 0
    totals = measure(records, caching=not options.no_cache)
    if options.json:
        print(json.dumps(totals))
    else:
        for key in sorted(totals):
            print(f"{key:28} {totals[key]}")
    if options.fields:
        print()
        sizes = field_sizes(records)
        whole = sum(sizes.values()) or 1
        for key, size in sizes.most_common(30):
            print(f"{size:>9} {100 * size / whole:5.1f}%  {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
