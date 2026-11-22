# Windows desktop launcher

[中文说明](#中文) · [English README](../README.md)

Start with the [Windows portable ZIP](../README.md#download-and-play). Extract the whole folder, double-click `Start STS2.cmd`, and start a manual run to confirm the launcher can find your Steam installation. On first play, the launcher prepares the game dependencies and English and Chinese game text inside the extracted folder. If it cannot locate the game, choose its installation folder. Adapter compatibility can vary by game version. Tested builds are listed in the [release notes](https://github.com/fallingstars123/sts2-cli/releases).

The Fool is selectable for game builds that include that character. Mega Crit introduced the character in the Steam `public-beta` branch in v0.113.0. [Official beta notes](https://store.steampowered.com/news/app/2868840/view/708914333639245837)

## AI personas and history

- Open **API settings** in the gear menu and add the API key for your provider. The launcher uses Windows Credential Manager for keys and stores persona preferences beside the launcher in `STS2 Preferences.json`.
- In **AI play**, select a persona or open **Persona panel** to choose its provider, model, game character, ascension, and speaking style. Choose a 20-step trial to check provider setup and usage. If prompted to install the provider's API client, let installation finish, then start again.
- Turn on commentary to let the model add optional comments to its action responses. **AI chat** shows these comments as they arrive. Changing how a persona speaks applies on the next decision. Changing its model or game settings applies on the next run.
- **Run history** opens the transcript and analysis for each run. Runs are grouped by floor and encounter in the local `STS2 Runs/` directory. The win-rate estimate uses earlier completed runs with the same model, character, and ascension that reached the current stage. Matching sample counts appear beside the estimate.
- **Map** shows each archived act with visited rooms and the route highlighted. Select a room and choose **Open room record** to read its transcript. Older archives can show visited rooms only. **Analysis** shows the latest available character state and a portrait read from the local Steam game. Use **Character wiki** for the character reference and **About** for credits.
- Expand **Deck** and **Relics** below the character in **Analysis** to see the contents of the latest recorded inventory.
- **Save folder** in the gear menu finds a local or Steam save folder and accepts a custom path. Continuing a native `.save` can update it. Open a copy in a separate folder to keep a checkpoint.

The launcher sends current game state to the selected provider when requesting a move. API usage may be billed by your provider. Keys are stored locally, and the API clients use them to authenticate. Run archives, saves, and prepared game files stay in your local folders.

## 中文

[简体中文 README](../README.zh-CN.md)

下载并完整解压 [Windows 便携版 ZIP](../README.zh-CN.md#下载与启动)，然后双击 `Start STS2.cmd`。可以先手动开一局，确认启动器能找到已安装的 Steam 游戏。首次开局会在解压目录内准备游戏依赖和中英文游戏文本。如果没有自动找到游戏，选择安装目录即可。适配情况因游戏版本而异，已测试的构建见 [发布说明](https://github.com/fallingstars123/sts2-cli/releases)。

启动器可为包含愚者的游戏版本选择该角色。愚者由 Steam `public-beta` 的 v0.113.0 首次加入。[官方测试分支公告](https://store.steampowered.com/news/app/2868840/view/708914333639245837)

- 在右上角齿轮的 **API 设置** 保存服务商密钥。密钥存入 Windows 凭据管理器。人物及界面设置保存在本地的 `STS2 Preferences.json`。
- 在 **AI 游玩** 中选择人物。人物面板可配置模型、游戏角色、进阶、试跑和发言语言。可以先用 20 步试跑确认服务商设置和用量。首次使用若提示安装 API 客户端，等待完成后再开局。
- 开启表达后，模型可自行决定是否发言，内容会出现在左栏的 **AI 对话**。发言设置在下一次决策生效，模型或游戏设置在下一次开局生效。
- **对局记录** 按楼层和房间保存到本地 `STS2 Runs/`。分析页用同模型、角色和进阶的历史完赛局在相应进度上的结果来估算，并显示样本数。
- **地图** 可切换章节并高亮已走路线。选中房间后可打开对应记录。较早的归档可能只保存了到访房间。**分析** 显示最近记录的角色状态和本机 Steam 游戏中的角色图。角色卡带有 Wiki 入口，图像和项目来源见齿轮菜单里的 **关于**。
- 在 **分析** 的角色卡下方展开 **牌组** 和 **遗物**，即可查看最近记录的清单和数量。
- 齿轮里的 **存档目录** 会自动查找项目或 Steam 存档目录，也可手动更换。继续原生 `.save` 时，游戏可能写回该文件。需要保留原进度时，可从单独目录打开副本。

AI 游玩时，启动器会把当前游戏状态发送给所选服务商以请求下一步操作，API 调用可能计费。密钥保存在本机，API 客户端使用密钥认证。对局归档、存档和准备好的游戏文件保存在本地目录。
