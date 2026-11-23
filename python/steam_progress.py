"""Read checkpoints and matching outcomes from the native Steam save directory."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re


STEAM_ID_BASE = 76561197960265728
MAX_SAVE_BYTES = 16 * 1024 * 1024


class SteamProgressError(RuntimeError):
    """The Steam account or selected test profile cannot be verified."""


@dataclass(frozen=True)
class RunIdentity:
    profile: int
    start_time: int
    seed: str
    character: str
    ascension: int


@dataclass(frozen=True)
class RunCheckpoint:
    identity: RunIdentity
    act: int
    act_id: str
    visited_points: int


@dataclass(frozen=True)
class RunSettlement:
    identity: RunIdentity
    outcome: str
    act_points: tuple[int, ...]
    build: str
    source_path: Path


def _read_save(path):
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_SAVE_BYTES + 1)
        if len(raw) <= MAX_SAVE_BYTES:
            saved = json.loads(raw)
            if isinstance(saved, dict):
                return saved
    except (OSError, ValueError, RecursionError):
        # The native game may be in the middle of updating this file.
        pass
    return {}


def _active_steam_account():
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess") as key:
            account, kind = winreg.QueryValueEx(key, "ActiveUser")
        if kind == winreg.REG_DWORD and 0 < account < 2**32:
            return str(STEAM_ID_BASE + account)
    except (ImportError, OSError):
        pass
    return None


def _steam_account_root():
    account_id = _active_steam_account()
    roots = [Path(value) / "SlayTheSpire2" / "steam" for name in ("APPDATA", "LOCALAPPDATA")
             if (value := os.environ.get(name))]
    if account_id is not None:
        matches = [root / account_id for root in roots if (root / account_id / "profile.save").is_file()]
    else:
        matches = [folder for root in roots for folder in root.glob("*")
                   if re.fullmatch(r"[0-9]{17}", folder.name) and (folder / "profile.save").is_file()]
    candidates = {path.resolve() for path in matches}
    if len(candidates) != 1:
        raise SteamProgressError("Could not uniquely identify the native Steam save account.")
    return candidates.pop()


def _identity(saved, profile, *, history):
    if saved.get("platform_type") != "steam" or saved.get("game_mode") != "standard":
        return None
    players = saved.get("players")
    if not isinstance(players, list) or len(players) != 1 or not isinstance(players[0], dict):
        return None
    character = players[0].get("character" if history else "character_id")
    if not isinstance(character, str) or not character.startswith("CHARACTER."):
        return None
    seed_fields = saved if history else saved.get("rng")
    seed = seed_fields.get("seed") if isinstance(seed_fields, dict) else None
    start_time, ascension = saved.get("start_time"), saved.get("ascension")
    if (not isinstance(seed, str) or not seed.strip() or type(start_time) is not int
            or start_time <= 0 or type(ascension) is not int or ascension < 0):
        return None
    return RunIdentity(profile, start_time, seed, character, ascension)


class SteamRunEvidence:
    """Read a single designated profile. Does not edit saves or select a profile."""

    def __init__(self, expected_profile: int | None = None, *, account_root: str | Path | None = None):
        if expected_profile is not None and (type(expected_profile) is not int or expected_profile not in (1, 2, 3)):
            raise ValueError("Choose a Steam profile number from 1 to 3.")
        self.account_root = Path(account_root) if account_root is not None else _steam_account_root()
        if expected_profile is None:
            expected_profile = self._selected_profile()
            if expected_profile is None:
                raise SteamProgressError("Could not identify the selected native Steam profile.")
        self.profile = expected_profile
        self.saves = self.account_root / f"profile{self.profile}" / "saves"

    def _selected_profile(self):
        selected = _read_save(self.account_root / "profile.save").get("last_profile_id")
        if type(selected) is int and selected in (1, 2, 3):
            return selected
        return None

    def require_profile(self) -> None:
        """Reject control when the native game selects a different slot."""
        if self._selected_profile() != self.profile:
            raise SteamProgressError(f"Select Steam profile {self.profile} before continuing.")

    def read_current(self) -> RunCheckpoint | None:
        """Return the official last checkpoint, if the selected run has one."""
        self.require_profile()
        saved = _read_save(self.saves / "current_run.save")
        identity = _identity(saved, self.profile, history=False)
        acts, index = saved.get("acts"), saved.get("current_act_index")
        visited = saved.get("visited_map_coords")
        if (identity is None or not isinstance(acts, list) or type(index) is not int
                or not 0 <= index < len(acts) or not isinstance(acts[index], dict)
                or not isinstance(visited, list)):
            return None
        act_id = acts[index].get("id")
        if not isinstance(act_id, str):
            return None
        return RunCheckpoint(identity, index + 1, act_id, len(visited))

    def read_result(self, identity: RunIdentity) -> RunSettlement | None:
        """Only accept a terminal record for the exact previously observed run."""
        if (not isinstance(identity, RunIdentity) or identity.profile != self.profile
                or type(identity.start_time) is not int or identity.start_time <= 0):
            return None
        source_path = self.saves / "history" / f"{identity.start_time}.run"
        saved = _read_save(source_path)
        if _identity(saved, self.profile, history=True) != identity:
            return None
        win, abandoned = saved.get("win"), saved.get("was_abandoned")
        history, build = saved.get("map_point_history"), saved.get("build_id")
        if (type(win) is not bool or type(abandoned) is not bool or (win and abandoned)
                or not isinstance(history, list) or not isinstance(build, str)
                or any(not isinstance(act, list) for act in history)):
            return None
        outcome = "defeat"
        if win:
            outcome = "victory"
        elif abandoned:
            outcome = "abandoned"
        return RunSettlement(identity, outcome, tuple(map(len, history)), build, source_path)
