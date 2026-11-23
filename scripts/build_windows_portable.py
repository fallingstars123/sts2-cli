"""Build the Windows x64 release with prepared Python and .NET runtime directories."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from portable_runtime import GAME_DLLS, game_dlls


PACKAGE_NAME = "sts2-cli-windows-x64"
PACKAGE_FILES = (
    "Start STS2.cmd", "STS2 Launcher.pyw", "STS2 Languages.json", "LICENSE", "README.md", "README.zh-CN.md",
    "agent/llm_agent.py", "agent/run_expression.py", "agent/run_stats.py",
    "agent/steam_mod_agent.py", "agent/steam_mod_archive.py", "agent/steam_mod_memory.py", "agent/steam_mod_tactics.py",
    "agent/steam_mod_shop.py", "agent/steam_mod_route.py", "agent/steam_mod_draw.py", "agent/steam_mod_sequence.py",
    "agent/steam_mod_strategy.py", "agent/steam_mod_strategy.json",
    "agent/steam_mod_prompt.py", "agent/steam_mod_experience.py",
    "agent/steam_mod_benchmark.py", "agent/steam_mod_token_replay.py",
    "python/steam_mcp.py",
    "python/play.py", "python/game_log.py", "python/character_catalog.py", "python/game_art.py",
    "python/card_hover.py", "python/inventory_book.py", "python/inventory_catalog.py",
    "python/scroll_gestures.py",
    "python/portable_runtime.py", "python/run_map.py", "python/steam_progress.py", "python/steam_window.py", "python/wiki_card_icons.py",
    "scripts/extract_localization.py",
    "docs/cli.md", "docs/desktop-launcher.md", "docs/steam-mod.md",
)
ENGINE_FILES = ("Sts2Headless.dll", "Sts2Headless.deps.json", "Sts2Headless.runtimeconfig.json", "GodotSharp.dll")
ENGINE_OUTPUT = Path("src/Sts2Headless/bin/Debug/net9.0")


def build(dotnet, project, configuration, *properties):
    subprocess.run([dotnet, "build", str(project), "--configuration", configuration, "--nologo",
                    "-p:NuGetAudit=false", "-p:UseAppHost=false", *properties], check=True)


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def patcher_sources(folder):
    # The source setup script also uses these two patcher files.
    setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
    folder.mkdir()
    for delimiter, name in (("PROJ", "Patcher.csproj"), ("CSHARP", "Program.cs")):
        _, _, tail = setup.partition(f"<< '{delimiter}'\n")
        content, found, _ = tail.partition(f"\n{delimiter}\n")
        if not content or not found:
            raise ValueError(f"Cannot locate {name} in setup.sh")
        (folder / name).write_text(content + "\n", encoding="utf-8")


def package(args, scratch):
    game = game_dlls(args.game_dir)
    if not game:
        raise ValueError("Choose the directory of an installed Windows copy of Slay the Spire 2.")
    compile_root, release = scratch / "build", scratch / PACKAGE_NAME
    shutil.copytree(ROOT / "src", compile_root / "src", ignore=shutil.ignore_patterns("bin", "obj"))
    if not args.steam_only:
        for name in GAME_DLLS:
            copy_file(game / name, compile_root / "lib" / name)
        patcher = compile_root / "patcher"
        patcher_sources(patcher)
        build(args.dotnet_sdk, patcher / "Patcher.csproj", "Release")
        build(args.dotnet_sdk, compile_root / "src" / "Sts2Headless" / "Sts2Headless.csproj", "Debug")
    bridge = compile_root / "src" / "Sts2LiveBridge"
    build(args.dotnet_sdk, bridge / "Sts2LiveBridge.csproj", "Release", f"-p:Sts2GameDir={game.parent.resolve()}")

    for name in PACKAGE_FILES:
        copy_file(ROOT / name, release / name)
    for name in ("Sts2LiveBridge.dll", "Sts2LiveBridge.json"):
        copy_file(bridge / "bin" / "Release" / "net9.0" / name, release / "Sts2LiveBridge" / name)
    for language in ("en", "zh"):
        for view in ("launcher", "analysis", "chat", "map"):
            screenshot = Path("docs/screenshots") / f"{view}-{language}.png"
            copy_file(ROOT / screenshot, release / screenshot)
    launcher = release / "Start STS2.cmd"
    launcher.write_text(launcher.read_text(encoding="ascii"), encoding="ascii", newline="\r\n")
    if not args.steam_only:
        for name in ENGINE_FILES:
            copy_file(compile_root / ENGINE_OUTPUT / name, release / ENGINE_OUTPUT / name)
        patcher_runtime = release / "runtime" / "patcher"
        for artifact in (patcher / "bin" / "Release" / "net9.0").iterdir():
            if artifact.suffix == ".dll" or artifact.name.endswith((".deps.json", ".runtimeconfig.json")):
                copy_file(artifact, patcher_runtime / artifact.name)
        copy_file(args.cecil_license, patcher_runtime / "Mono.Cecil.LICENSE.txt")
        shutil.copytree(args.dotnet_dir, release / "runtime" / "dotnet")
    python = release / "runtime" / "python"
    for component in args.python_dir:
        shutil.copytree(component, python, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*.msi", "__pycache__", "*.pyc"))
    pip_wheel, = (python / "Lib" / "ensurepip" / "_bundled").glob("pip-*.whl")
    # Only the official pure-Python pip module is needed for `python -m pip`.
    with ZipFile(pip_wheel) as bundled_pip:
        bundled_pip.extractall(python / "Lib" / "site-packages")
    with ZipFile(args.pillow_wheel) as pillow:
        pillow.extractall(python / "Lib" / "site-packages")
    env = {**os.environ, "PYTHONHOME": str(python), "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([str(python / "python.exe"), "-B", "-c",
                    "import pip, tkinter; from PIL import features; assert features.check('webp'); print(tkinter.TkVersion)"],
                   env=env, check=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(release.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                archive.write(path, path.relative_to(scratch).as_posix())
    print(f"Created {args.output} ({args.output.stat().st_size:,} bytes)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-dir", type=Path, action="append", required=True,
                        help="official Python runtime directory or expanded MSI component (repeat for each)")
    parser.add_argument("--dotnet-dir", type=Path, help="expanded Windows x64 .NET 9 runtime for terminal play")
    parser.add_argument("--steam-only", action="store_true", help="Package the launcher and Steam bridge without the terminal engine.")
    parser.add_argument("--dotnet-sdk", default="dotnet", help="build-time .NET SDK executable")
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--cecil-license", type=Path, help="license file for Mono.Cecil 0.11.6")
    parser.add_argument("--pillow-wheel", type=Path, required=True, help="official Pillow wheel matching the Python runtime")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.steam_only and (args.dotnet_dir is None or args.cecil_license is None):
        parser.error("--dotnet-dir and --cecil-license are required when including the terminal engine.")
    with TemporaryDirectory(prefix="sts2-portable-") as scratch:
        package(args, Path(scratch))


if __name__ == "__main__":
    main()
