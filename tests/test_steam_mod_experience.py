"""Cross-run experience: recording attempts, post-fight review, and evidence-gated lessons."""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

import steam_mod_agent as agent  # noqa: E402
from steam_mod_experience import Experience  # noqa: E402


def test_post_fight_review_records_usage_even_when_it_returns_no_lesson():
    usage = SimpleNamespace(input_tokens=100, output_tokens=25, cache_read_input_tokens=50,
                            cache_creation_input_tokens=10)
    response = SimpleNamespace(usage=usage, stop_reason="max_tokens", content=[])
    claude = agent.ClaudeDecisions(SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: response)), "test")
    recorded = []
    assert agent.request_review(claude, "Review", "{}", record_usage=recorded.append) == ""
    assert recorded == [{
        "prompt_tokens": 100, "completion_tokens": 25, "prompt_cache_hit_tokens": 50,
        "prompt_cache_miss_tokens": 110, "prompt_cache_write_tokens": 10,
    }]

    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=12, prompt_cache_hit_tokens=40,
                              prompt_cache_miss_tokens=60),
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"lessons":[]}'))],
    )
    deepseek = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    assert agent.request_review(deepseek, "Review", "{}", record_usage=recorded.append) == '{"lessons":[]}'
    assert recorded[-1] == {"prompt_tokens": 100, "completion_tokens": 12, "prompt_cache_hit_tokens": 40,
                            "prompt_cache_miss_tokens": 60}


def combat(turn, hp, *, encounter="SPINY_TOAD_NORMAL", seed="SEED", floor=27, attack=23, powers=()):
    return {"screen": "combat", "run": {"seed": seed, "act": 2, "floor": floor, "hp": hp, "max_hp": 100,
                                        "character": "CHARACTER.SILENT"},
            "state": {"encounter": encounter, "turn": turn, "energy": 3,
                      "player": {"hp": hp, "max_hp": 100, "block": 0},
                      "enemies": [{"name": "Spiny Toad", "hp": 90, "block": 0, "powers": list(powers),
                                   "intents": [{"type": "Attack", "damage": attack, "hits": 1, "total_damage": attack}]}]},
            "actions": []}


def screen(name, hp=None, **state):
    return {"screen": name, "run": {"hp": hp}, "state": state, "actions": []}


def play_fight(ledger, start, end, *, model="m", reviewer=None, seed="SEED"):
    """One fight: two turns, then the rewards screen."""
    experience = Experience(ledger, model=model, reviewer=reviewer, log=lambda _m: None)
    shown = experience.observe(combat(1, start, seed=seed))
    experience.acted({"kind": "play_card", "detail": {"card_id": "STRIKE_SILENT", "target_index": 0}})
    experience.observe(combat(2, start, seed=seed, powers=[{"name": "Thorns", "amount": 5}]))
    experience.settle(screen("rewards", hp=end))
    return experience, shown


def test_a_fight_is_recorded_with_its_worst_turn(tmp_path):
    ledger = tmp_path / "x.json"
    experience = Experience(ledger, model="deepseek-flash", log=lambda _m: None)
    experience.observe(combat(1, 54))
    experience.acted({"kind": "play_card", "detail": {"card_id": "BACKSTAB", "target_index": 0}})
    experience.observe(combat(2, 54, powers=[{"name": "Thorns", "amount": 5}]))
    experience.observe(combat(3, 17))
    experience.settle(screen("card_selection"))  # a mid-combat choice must not end the fight
    assert experience.current is not None
    experience.settle(screen("rewards", hp=17))
    attempt = json.loads(ledger.read_text())["encounters"]["SPINY_TOAD_NORMAL"]["attempts"][0]
    assert attempt["result"] == "won" and attempt["hp_lost_pct"] == 0.37 and attempt["model"] == "deepseek-flash"
    worst = attempt["worst_turns"][0]
    assert worst["turn"] == 2 and worst["hp_lost"] == 37
    assert "Thorns 5" in worst["enemies_at_turn_start"][0]
    assert "in_progress" not in json.loads(ledger.read_text())


def test_one_fight_over_several_one_turn_sessions_is_one_attempt(tmp_path):
    ledger = tmp_path / "x.json"
    Experience(ledger, log=lambda _m: None).observe(combat(1, 60))
    second = Experience(ledger, log=lambda _m: None)        # a new launcher session
    second.observe(combat(2, 50))
    third = Experience(ledger, log=lambda _m: None)
    third.settle(screen("rewards", hp=45))                   # the fight ended between sessions
    attempts = json.loads(ledger.read_text())["encounters"]["SPINY_TOAD_NORMAL"]["attempts"]
    assert [(a["result"], a["hp_start"], a["hp_end"], a["turns"]) for a in attempts] == [("won", 60, 45, 2)]


def test_a_retry_closes_the_first_attempt_and_a_defeat_is_recorded(tmp_path):
    ledger = tmp_path / "x.json"
    experience = Experience(ledger, log=lambda _m: None)
    experience.observe(combat(1, 42, encounter="THE_INSATIABLE_BOSS", floor=33))
    experience.observe(combat(3, 20, encounter="THE_INSATIABLE_BOSS", floor=33))
    experience.observe(combat(1, 42, encounter="THE_INSATIABLE_BOSS", floor=33))   # retry_current_combat
    experience.settle(screen("settlement", outcome="defeat"))
    attempts = json.loads(ledger.read_text())["encounters"]["THE_INSATIABLE_BOSS"]["attempts"]
    assert [(a["result"], a["hp_end"]) for a in attempts] == [("retried", 20), ("lost", 0)]


def test_a_costly_fight_is_reviewed_and_a_failed_review_never_raises(tmp_path):
    ledger = tmp_path / "x.json"
    calls = []

    def reviewer(instructions, data):
        calls.append(json.loads(data))
        return '{"lessons": ["Spiny Toad has Thorns 5 on its 23-damage turn: block that turn instead of attacking."]}'

    play_fight(ledger, 54, 17, reviewer=reviewer)
    assert calls and calls[0]["turn_log"][1]["enemies"][0].endswith("powers: Thorns 5")
    lessons = json.loads(ledger.read_text())["encounters"]["SPINY_TOAD_NORMAL"]["lessons"]
    assert [lesson["status"] for lesson in lessons] == ["trial"]

    play_fight(ledger, 90, 88, reviewer=reviewer)             # cheap fight: no review
    assert len(calls) == 1

    def broken(_instructions, _data):
        raise RuntimeError("provider down")
    play_fight(ledger, 54, 10, reviewer=broken)               # must not raise


def test_lessons_are_kept_or_retired_by_later_results(tmp_path):
    ledger = tmp_path / "x.json"
    play_fight(ledger, 100, 60)                               # baseline: 40% lost
    experience = Experience(ledger, log=lambda _m: None)
    experience.add_lessons("SPINY_TOAD_NORMAL", ["Block on the Thorns turn and attack on turns 1 and 3 instead."])
    experience.add_lessons("SPINY_TOAD_NORMAL", ["Open with Neutralize so the 23-damage hit is Weakened."])
    experience.save()
    shown_texts = []
    for _ in range(4):                                        # four better fights (15% lost)
        _, shown = play_fight(ledger, 100, 85)
        trials = [lesson for lesson in shown["lessons"] if lesson["status"] == "trial"]
        assert len(trials) == 1                               # one untested lesson at a time
        shown_texts.append(trials[0]["text"])
    assert shown_texts[0] != shown_texts[1]                   # trials take turns
    lessons = json.loads(ledger.read_text())["encounters"]["SPINY_TOAD_NORMAL"]["lessons"]
    assert [lesson["status"] for lesson in lessons] == ["kept", "kept"]

    # A new lesson followed by worse fights is retired and no longer shown;
    # the kept lessons shown alongside it survive two bad fights.
    experience = Experience(ledger, log=lambda _m: None)
    experience.add_lessons("SPINY_TOAD_NORMAL", ["Skip blocking entirely; Thorns never matters in this fight."])
    experience.save()
    _, shown = play_fight(ledger, 100, 30)
    assert len(shown["lessons"]) == 3                         # two kept + the new trial
    play_fight(ledger, 100, 20)
    lessons = json.loads(ledger.read_text())["encounters"]["SPINY_TOAD_NORMAL"]["lessons"]
    assert [lesson["status"] for lesson in lessons] == ["kept", "kept", "retired"]
    shown = Experience(ledger, log=lambda _m: None).context("SPINY_TOAD_NORMAL")["lessons"]
    assert len(shown) == 2 and all("Skip blocking" not in lesson["text"] for lesson in shown)


def test_a_lesson_without_history_still_rotates_with_newer_trials(tmp_path):
    ledger = tmp_path / "x.json"
    experience = Experience(ledger, log=lambda _m: None)
    experience.add_lessons("SPINY_TOAD_NORMAL", ["Written by hand before any recorded attempt at this fight."])
    experience.save()
    play_fight(ledger, 100, 70)
    experience = Experience(ledger, log=lambda _m: None)
    experience.add_lessons("SPINY_TOAD_NORMAL", ["A later trial lesson must also get its turn to be measured."])
    experience.save()
    _, shown = play_fight(ledger, 100, 70)
    assert shown["lessons"][0]["text"].startswith("A later trial")


def test_the_model_sees_encounter_experience(tmp_path):
    ledger = tmp_path / "x.json"
    play_fight(ledger, 54, 17)
    experience = Experience(ledger, log=lambda _m: None)
    experience.add_lessons("SPINY_TOAD_NORMAL", ["Spiny Toad has Thorns 5 on its 23-damage turn: block that turn."])
    experience.save()
    state = {**combat(1, 70, seed="NEW"), "state_id": "s:1:x",
             "actions": [{"id": "end", "kind": "end_turn", "detail": {}}, {"id": "x", "kind": "end_turn", "detail": {}}]}
    notes = Experience(ledger, log=lambda _m: None).observe(state)
    seen = {}

    def request(_client, instructions, data, _high_risk, **_stable):
        seen.update(instructions=instructions, context=json.loads(data))
        message = SimpleNamespace(content='{"choice":1}')
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=message)], usage=None)

    with patch.object(agent, "request_choice", side_effect=request):
        agent.choose(None, state, [], "", {"encounter_experience": notes})
    assert seen["context"]["encounter_experience"]["past_attempts"] == 1
    assert "Thorns 5" in seen["context"]["encounter_experience"]["lessons"][0]["text"]
    assert "encounter_experience summarizes earlier attempts" in seen["instructions"]
