# Windows desktop launcher

[中文说明](#中文) · [English README](../README.md)

Extract the [Windows portable ZIP](../README.md#download-and-play), double-click `Start STS2.cmd`, and install the included bridge for Steam Full Run. The [Steam setup guide](steam-mod.md) covers installation, startup, and stopping. The terminal controls appear on installations that include the terminal engine.

The Fool is selectable for game builds that include that character. Mega Crit introduced the character in the Steam `public-beta` branch in v0.113.0. [Official beta notes](https://store.steampowered.com/news/app/2868840/view/708914333639245837)

Desktop menus support 17 languages through `STS2 Languages.json`. Both Chinese menu options use Simplified Chinese game text in the adapter and terminal. All other menu options use English game text. AI commentary has its own language setting.

## AI personas and history

- **Steam Full Run** continues the active Steam single-player run with the selected persona's model. Open the run in Steam with the bridge enabled. The game can remain behind the launcher. [Steam setup guide](steam-mod.md)
- Open **API settings** in the gear menu and add the API key for your provider. The launcher uses Windows Credential Manager for keys and stores persona preferences beside the launcher in `STS2 Preferences.json`.
- In **AI play**, select a persona or open **Persona panel** to set its provider, model, and speaking style. **Play in terminal** starts a fresh run using the persona's character and ascension. Install the provider's API client if prompted, then start again.
- For terminal play, turn on commentary to let the model add optional comments to its action responses. **AI chat** shows these comments as they arrive. Changing how a persona speaks applies on the next decision. Changing its model or game settings applies on the next run.
- **Run history** opens the transcript and analysis for each run. Runs are grouped by floor and encounter in the local `STS2 Runs/` directory. The win-rate estimate uses earlier completed runs with the same model, character, and ascension that reached the current stage. Matching sample counts appear beside the estimate.
- **Map** shows each archived act with dashed branches, solid bright lines for the traveled route, and rings around visited rooms. Select a room and choose **Open room record** to read its transcript. Older archives can show visited rooms only. **Analysis** shows the latest character state and uses icons from the local Steam game for HP, gold, block, potions, and combat energy when those values have been recorded. Credits are in **About**.
- In **Analysis**, gold, block, and energy share one row, with a separate potion row underneath. Empty circles mark recorded empty slots. Expand **Relics** on the left and **Deck** on the right. The deck uses a grid that adjusts to the window width. Hover over an item for its details. Open **Card and relic dictionary** from the gear menu to search by name or ID. The previews read item images from the local Steam installation without a download.
- Drag vertically on the touchscreen to scroll the history, chat, analysis, map, and dictionary views. Tap a map node to select it. Card previews open beside the hovered row and show the upgrade state recorded in the deck. A cached reference image is used when its effects and known cost match that entry. Other cards use a frame and artwork from the local Steam installation. Relic previews place the icon beside the description.
- **Save folder** in the gear menu finds a local or Steam save folder and accepts a custom path. Continuing a native `.save` can update it. Open a copy in a separate folder to keep a checkpoint.

The launcher sends current game state to the selected provider when requesting a move. API usage may be billed by your provider. Keys are stored locally, and the API clients use them to authenticate. Run archives, saves, and prepared game files stay in your local folders.

## 中文

[简体中文 README](../README.zh-CN.md)

完整解压 [Windows 便携版 ZIP](../README.zh-CN.md#下载与启动)，双击 `Start STS2.cmd`。先按 [Steam 桥接指南](steam-mod.md#简体中文) 安装包内附带的桥接，再开始整局托管。终端入口会在含终端引擎的安装里显示。

启动器可为包含愚者的游戏版本选择该角色。愚者由 Steam `public-beta` 的 v0.113.0 首次加入。[官方测试分支公告](https://store.steampowered.com/news/app/2868840/view/708914333639245837)

桌面菜单通过 `STS2 Languages.json` 提供 17 种语言。选择简体或繁体中文菜单时，游戏适配器和终端使用简体中文游戏文本。选择其他菜单语言时，游戏文本使用英语。AI 发言语言可单独选择。

- 在右上角齿轮的 **API 设置** 保存服务商密钥。密钥存入 Windows 凭据管理器。人物及界面设置保存在本地的 `STS2 Preferences.json`。
- **Steam 整局托管** 从 Steam 当前单人对局接手，使用所选人物的模型。先在 Steam 启用桥接并进入对局，游戏可以留在启动器后面。[Steam 桥接使用说明](steam-mod.md#简体中文)
- 在 **AI 游玩** 中选择人物。人物面板可配置模型与发言。**终端开局** 按人物设定的角色和进阶开始新对局。首次使用若提示安装 API 客户端，等待完成后再开局。
- 终端游玩时，开启表达后，模型可自行决定是否发言，内容会出现在左栏的 **AI 对话**。发言设置在下一次决策生效，模型或游戏设置在下一次开局生效。
- **对局记录** 按楼层和房间保存到本地 `STS2 Runs/`。分析页用同模型、角色和进阶的历史完赛局在相应进度上的结果来估算，并显示样本数。
- **地图** 可切换章节，虚线显示房间分岔，亮实线标出走过的路，圆圈标出已到访房间。选中房间后可打开对应记录。较早的归档可能只保存了到访房间。**分析** 用本机 Steam 图标标注已记录的血量、金币、格挡、药水和战斗能量。图像和项目来源见齿轮菜单里的 **关于**。
- **分析** 将金币、格挡和能量放在同一行，下方单独一行显示药水，空圈表示有记录的空槽。左侧展开 **遗物**，右侧展开 **牌组**，牌组会随窗口宽度自动调整列数。把鼠标停在条目上可查看详情。齿轮里的 **卡牌与遗物图鉴** 支持按名称或 ID 搜索。预览从本机 Steam 安装读取物品图片，无需下载。
- 在对局记录、AI 对话、分析、地图和图鉴中，可以用触屏上下拖动。轻点地图节点可选中房间。卡牌预览在悬停行附近展开，仅显示牌组所记录的版本。效果和已知费用一致时使用缓存的完整卡面，其他卡牌使用本机 Steam 的卡框和原画。遗物预览在说明左侧显示图标。
- 齿轮里的 **存档目录** 会自动查找项目或 Steam 存档目录，也可手动更换。继续原生 `.save` 时，游戏可能写回该文件。需要保留原进度时，可从单独目录打开副本。

AI 游玩时，启动器会把当前游戏状态发送给所选服务商以请求下一步操作，API 调用可能计费。密钥保存在本机，API 客户端使用密钥认证。对局归档、存档和准备好的游戏文件保存在本地目录。
