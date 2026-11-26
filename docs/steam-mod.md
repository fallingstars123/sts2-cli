# STS2 Live Bridge

[简体中文](#简体中文)

STS2 Live Bridge connects the Windows launcher to the active standard or daily Steam single-player run. It reads structured game state and executes native game actions through a local named pipe. The game plays its normal animations and can stay behind the launcher.

## Start a full run

1. Copy the `Sts2LiveBridge` folder into the Steam game's `mods` directory. It contains the bridge DLL and JSON manifest. If you have a source checkout, build it using the command below.
2. Restart the game, enable **STS2 Live Bridge** in its mod settings, and open or continue a standard or daily single-player run.
3. Save a DeepSeek or Claude key under **API settings**, then choose the persona and select **AI play → Steam Full Run**. The model takes over from the current screen, using the character and ascension already active in Steam.

Use **Run history** to follow recorded rooms, health, inventory, route, and decisions. The agent stops at the native run result, an unsupported state, or its action limit. Press **Ctrl+C** in the console to stop it earlier. The provider may bill API requests. Keys are managed by the launcher.

## Build the bridge

With the .NET 9 SDK, build against your local Steam installation:

```powershell
dotnet build src/Sts2LiveBridge -c Release -p:Sts2GameDir="C:/path/to/Slay the Spire 2"
```

Copy `Sts2LiveBridge.dll` and `Sts2LiveBridge.json` from `src/Sts2LiveBridge/bin/Release/net9.0` into a folder named `Sts2LiveBridge` under the game's `mods` directory.

## Command-line and MCP checks

- Use `agent/steam_mod_agent.py --verify` to read the active game state without an API request. To step through one live combat, use the same script with `--checkpoint combat`.
- An MCP client can launch `python -u python/steam_mcp.py` over stdio. Call `get_state`, choose an action ID from `actions`, and send it with the returned `state_id` to `perform_action`. Read state again to confirm the result. The bridge requires the same Windows user and rejects stale states and unsupported runs.

## 简体中文

STS2 Live Bridge 将 Windows 启动器接到当前 Steam 标准单人对局或每日挑战。它通过本机命名管道读取结构化游戏状态、执行游戏原生动作。游戏会照常播放动画，也可以留在启动器后面。

### 启动整局托管

1. 把包含桥接 DLL 和 JSON 清单的 `Sts2LiveBridge` 文件夹放到 Steam 游戏目录的 `mods` 下。从源码安装时，按下面的命令构建。
2. 重启游戏，在 Mod 设置里启用 **STS2 Live Bridge**，然后开始或继续一局标准单人对局或每日挑战。
3. 在启动器的 **API 设置** 保存 DeepSeek 或 Claude 密钥，选好人物后点 **AI 游玩 → Steam 整局托管**。AI 从当前画面接手，角色和进阶以 Steam 已打开的对局为准。

在 **对局记录** 可跟踪房间、血量、牌组、地图和 AI 决策。对局结算、遇到未支持的界面或达到操作上限时会停止。要提前停止，在控制台按 **Ctrl+C**。API 调用可能计费，密钥由启动器管理。

### 从源码构建桥接

用 .NET 9 SDK 执行下面的命令，将路径换成本机 Steam 游戏目录。

```powershell
dotnet build src/Sts2LiveBridge -c Release -p:Sts2GameDir="C:/path/to/Slay the Spire 2"
```

将 `src/Sts2LiveBridge/bin/Release/net9.0` 下的 `Sts2LiveBridge.dll` 与 `Sts2LiveBridge.json` 放到游戏的 `mods/Sts2LiveBridge` 文件夹。

### 命令行与 MCP 验证

- `agent/steam_mod_agent.py --verify` 只读游戏状态。调试单场战斗可使用同一脚本的 `--checkpoint combat`。
- MCP 客户端可以通过 stdio 启动 `python -u python/steam_mcp.py`。先用 `get_state` 读状态，从 `actions` 中选动作 ID，连同返回的 `state_id` 交给 `perform_action`。再次读取状态即可核对结果。桥接要求同一个 Windows 用户，并会拒绝过期状态和不支持的对局。
