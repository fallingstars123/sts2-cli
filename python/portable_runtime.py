"""Prepare the Windows portable engine from a locally installed copy of STS2."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from uuid import uuid4


GAME_DLLS = (
    "sts2.dll", "SmartFormat.dll", "SmartFormat.ZString.dll", "Sentry.dll", "Sentry.Godot.dll",
    "Steamworks.NET.dll", "MonoMod.Backports.dll", "MonoMod.ILHelpers.dll", "0Harmony.dll", "System.IO.Hashing.dll",
)


def portable_dotnet(root):
    path = Path(root) / "runtime" / "dotnet" / "dotnet.exe"
    return path if path.is_file() else None


def engine_command(root, dotnet, project):
    bundled = portable_dotnet(root)
    if bundled:
        adapter = Path(root) / "src" / "Sts2Headless" / "bin" / "Debug" / "net9.0" / "Sts2Headless.dll"
        return [str(bundled), str(adapter)]
    return [dotnet, "run", "--no-build", "--project", project]


def game_dlls(folder):
    if not folder.is_dir():
        return None
    if (folder / "sts2.dll").is_file():
        return folder
    return next((path for path in sorted(folder.glob("data_sts2_windows_*")) if (path / "sts2.dll").is_file()), None)


def steam_libraries():
    import winreg

    roots = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as steam:
            roots.append(Path(winreg.QueryValueEx(steam, "SteamPath")[0]))
    except OSError:
        pass
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        if os.environ.get(variable):
            roots.append(Path(os.environ[variable]) / "Steam")
    libraries = list(roots)
    for root in dict.fromkeys(roots):
        configuration = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = configuration.read_text(encoding="utf-8-sig")
        except (OSError, ValueError):
            continue
        for path in re.findall(r'"path"\s+"([^"]+)"', text):
            libraries.append(Path(path.replace("\\\\", "\\")))
    return tuple(dict.fromkeys(libraries))


def find_game():
    explicit = os.environ.get("STS2_STEAM_GAME_DIR")
    if explicit:
        return game_dlls(Path(explicit))
    if os.name != "nt":
        return None
    for library in steam_libraries():
        apps = library / "steamapps"
        manifest = apps / "appmanifest_2868840.acf"
        name = "Slay the Spire 2"
        try:
            match = re.search(r'"installdir"\s+"([^"]+)"', manifest.read_text(encoding="utf-8-sig"))
            if match:
                name = match[1]
        except (OSError, ValueError):
            pass
        if found := game_dlls(apps / "common" / name):
            return found
    return None


def game_pack(source):
    if not source:
        return None
    return next((path for folder in (source, source.parent) for path in sorted(folder.glob("*.pck"))), None)


def find_game_pack(root):
    current = game_pack(find_game())
    if current:
        return current
    try:
        saved = json.loads((root / "lib" / "portable.json").read_text(encoding="utf-8"))
        return game_pack(game_dlls(Path(saved["folder"])))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def select_game():
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        folder = filedialog.askdirectory(parent=root, title="Select Slay the Spire 2 game folder / 选择杀戮尖塔 2 游戏目录",
                                         mustexist=True)
        return game_dlls(Path(folder)) if folder else None
    finally:
        root.destroy()


@contextmanager
def lock_setup(path):
    import msvcrt

    with path.open("a+b") as lock:
        deadline = time.monotonic() + 45
        while True:
            try:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as error:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Another launcher is still preparing the game.") from error
                time.sleep(0.2)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def prepare_game(root):
    root = Path(root)
    dotnet = portable_dotnet(root)
    if not dotnet:
        raise RuntimeError("The portable .NET runtime is missing. Extract the complete release ZIP.")
    patcher = root / "runtime" / "patcher" / "Patcher.dll"
    library = root / "lib"
    library.mkdir(exist_ok=True)
    with lock_setup(library / "setup.lock"):
        marker = library / "portable.json"
        try:
            saved = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        if not isinstance(saved, dict):
            saved = {}
        source = find_game()
        if not source and isinstance(saved.get("folder"), str):
            source = game_dlls(Path(saved["folder"]))
        if not source:
            source = select_game()
        if not source:
            raise RuntimeError("Install Slay the Spire 2 in Steam or select its game folder. / 请先安装 Steam 游戏或选择游戏目录。")
        missing = [name for name in GAME_DLLS if not (source / name).is_file()]
        if missing:
            raise RuntimeError("Game installation is missing: " + ", ".join(missing))
        pck = game_pack(source)
        if not pck:
            raise RuntimeError("The Steam game data file (.pck) could not be found.")
        fingerprint = {"folder": str(source.resolve()), "files": {name: (source / name).stat().st_mtime_ns for name in GAME_DLLS},
                       "localization": pck.stat().st_mtime_ns,
                       "patcher": hashlib.sha256(patcher.read_bytes()).hexdigest()}
        if (saved == fingerprint and all((library / name).is_file() for name in GAME_DLLS)
                and all((root / folder / "cards.json").is_file() for folder in ("localization_eng", "localization_zhs"))):
            return

        print("Preparing the local Steam game for the portable launcher… / 正在准备本机 Steam 游戏…", flush=True)
        staging = library / f"prepare-{uuid4().hex}"
        staging.mkdir()
        try:
            for name in GAME_DLLS:
                shutil.copy2(source / name, staging / name)
            subprocess.run([str(dotnet), str(patcher), str(staging / "sts2.dll")],
                           cwd=root, check=True, timeout=30)
            subprocess.run([sys.executable, "-B", str(root / "scripts" / "extract_localization.py"), str(pck),
                            "--root", str(staging)], cwd=root, check=True, timeout=90)
            for name in GAME_DLLS:
                (staging / name).replace(library / name)
            for folder in ("localization_eng", "localization_zhs"):
                target = root / folder
                target.mkdir(exist_ok=True)
                for table in (staging / folder).glob("*.json"):
                    table.replace(target / table.name)
            updated = staging / "portable.json"
            updated.write_text(json.dumps(fingerprint, ensure_ascii=False) + "\n", encoding="utf-8")
            updated.replace(marker)
        finally:
            if staging.resolve().parent == library.resolve():
                shutil.rmtree(staging)
