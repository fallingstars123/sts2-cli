# Windows desktop launcher

[中文说明](#中文)

The optional Tkinter launcher uses the same headless engine as the upstream CLI. It supports manual runs and replay or native saves, AI personas backed by DeepSeek or Claude, a separate commentary view, and local run history and analysis. The launcher interface and AI commentary each offer 17 languages. The interactive game terminal uses English or Simplified Chinese.

## Start here

1. Install Slay the Spire 2 through Steam, the .NET 9 SDK, Python 3.10 or newer with Tkinter, and Git for Windows.
2. Open Git Bash, clone this fork, and run setup.

   ```bash
   git clone https://github.com/fallingstars123/sts2-cli.git
   cd sts2-cli
   bash setup.sh
   ```

   Setup copies the engine dependencies from your Steam installation into `lib/` and builds the adapter. For a non-default Steam library, pass the game folder as an argument to `bash setup.sh`.
3. Double-click `STS2 Launcher.pyw`. You can also run it from PowerShell.

   ```powershell
   python -X utf8 '.\STS2 Launcher.pyw'
   ```

The upstream [setup notes](../README.md#setup) describe the tested game version and compatibility checks. If Steam updates the game, rerun setup with a compatible game build.

## AI personas and history

- Open the gear menu and add the API key for your provider. The launcher uses Windows Credential Manager for keys and stores persona preferences beside the launcher in `STS2 Preferences.json`.
- In **AI play**, select a persona or open **Persona panel** to choose its provider, model, default game character, ascension, and speaking style. The launcher can install the required Python API client. Start with the 20-step trial to check your provider setup and usage.
- Turn on commentary to let the model add optional comments to its action responses. The **AI chat** sidebar shows these comments as they arrive. Changing how a persona speaks applies on the next decision. Changing its model or game settings applies on the next run.
- **Run history** opens the transcript and analysis for each run. Runs are grouped by floor and encounter in the local `STS2 Runs/` directory. The win-rate estimate uses earlier completed runs with the same model, character, and ascension that reached the current stage. Matching sample counts are shown next to the estimate.
- **Save folder** in the gear menu opens the folder setting. It detects a project or Steam save folder, and a custom path can be entered. Selecting a native `.save` can update that save while playing. To preserve a checkpoint, open a copy from a separate folder.

The launcher reads the current game state to build model requests. API calls use your provider account and may incur charges. Windows credentials, run archives, saves, and Steam engine files are local to your installation.

## 中文

Windows 启动器使用上游的无界面游戏引擎。它支持手动游玩、选择存档、配置 DeepSeek 或 Claude 人物、查看 AI 对话、回看对局及分析胜率。界面和 AI 发言各支持 17 种语言，独立游戏终端使用简体中文或英语。

1. 安装 Steam 版《杀戮尖塔 2》、.NET 9 SDK、带 Tkinter 的 Python 3.10 或更新版本，以及 Git for Windows。
2. 在 Git Bash 运行 `git clone https://github.com/fallingstars123/sts2-cli.git`，进入 `sts2-cli` 目录后运行 `bash setup.sh`。它会从你本机的 Steam 安装复制所需依赖到 `lib/` 并编译适配器。如果游戏在其他 Steam 库，把游戏目录作为参数传给 `bash setup.sh`。
3. 双击 `STS2 Launcher.pyw`。也可以在 PowerShell 运行 `python -X utf8 '.\STS2 Launcher.pyw'`。

- 在右上角齿轮的 **API 设置** 中保存密钥。密钥存入 Windows 凭据管理器。人物及界面设置保存在本地的 `STS2 Preferences.json`。
- 在 **AI 游玩** 中选择人物。人物面板可配置模型、游戏角色、进阶、试跑和发言语言。开启表达后，模型可以选择是否发言，内容会出现在左栏的 **AI 对话**。
- **对局记录** 按楼层和房间保存到本地 `STS2 Runs/`。分析页用同模型、角色和进阶的历史完赛局在相应进度上的结果来估算，并显示样本数。首次运行时可以用 20 步试跑确认 API 设置和用量。API 调用可能产生费用。
- 齿轮里的 **存档目录** 会自动查找项目或 Steam 存档目录，也可手动更换。继续原生 `.save` 时，游戏可能写回该文件。需要保留原进度时，可从单独目录打开副本。
