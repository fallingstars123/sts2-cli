# 杀戮尖塔 2 桌面启动器

[English](README.md) · **简体中文**

这是为 [sts2-cli](https://github.com/wuhao21/sts2-cli) 增加的 Windows 桌面启动器。可以手动控制对局，也可以让 DeepSeek 或 Claude 游玩并回看每个房间的过程。对局通过本机 Steam 游戏引擎运行，操作和状态显示在游戏终端里。

## 下载与启动

**[下载 Windows x64 便携版 ZIP](https://github.com/fallingstars123/sts2-cli/releases/latest/download/sts2-cli-windows-x64.zip)**

1. 通过 Steam 安装《杀戮尖塔 2》，然后下载上面的 ZIP。
2. 将 ZIP 完整解压到一个可写目录，再双击里面的 `Start STS2.cmd`。
3. 选择 **手动游玩** 或 **AI 游玩**，点击 **开始对局**。首次开局会自动查找 Steam 游戏。如果找不到，选择游戏安装目录即可。

ZIP 已包含 Python 和 .NET 运行环境，无需另装工具或输入安装命令。手动游玩无需 API 密钥。使用 AI 时，在右上角齿轮的 **API 设置** 保存密钥，再在 **人物面板** 选择模型。首次使用该服务商时，启动器会提示安装对应的 Python API 客户端，需要联网。

![中文启动器，显示 AI 人物、发言语言和模型](docs/screenshots/launcher-zh.png)

## 功能

- **人物与语言**。为每个人物保存模型、发言设定和输出语言，开局时直接切换人物。界面和 AI 发言各支持 17 种语言，可分别设置。
- **本机存档**。在齿轮菜单自动查找或手动设置存档目录，回到开局页即可选择存档。
- **AI 对话与对局记录**。左栏展开相应视图。每局都有独立目录，战斗、宝箱、休息点等房间保存在各自的子目录。
- **对局地图**。可切换对局和章节。地图按引擎原始列和房间连接布点，高亮点线标出已走路线，点击房间图标可打开对应记录。
- **游戏图标**。地图节点、图例与选角处优先使用本机 Steam 游戏的原图标，遇到缺失的图标时显示简洁符号。
- **角色和对局分析**。页面顶部是角色图、血条、近期血量走势、金币、牌组张数和遗物数量。选中进行中的对局时自动更新，下方保留整局图表和历史胜率。

## 界面预览

以下聊天内容、对局和统计均为演示数据。

![分析页顶部的角色状态、血条和近期走势，下方的是历史统计与整局曲线](docs/screenshots/analysis-zh.png)

![对局地图中的路线分支、房间图标和已走路线](docs/screenshots/map-zh.png)

![AI 对话中的人物发言和操作时间线](docs/screenshots/chat-zh.png)

## 文档与许可

- [桌面启动器使用指南](docs/desktop-launcher.md#中文)
- [命令行玩法、源码构建和 JSON 协议](docs/cli.md#中文)
- [版本更新与下载](https://github.com/fallingstars123/sts2-cli/releases)

本项目基于 [wuhao21/sts2-cli](https://github.com/wuhao21/sts2-cli)，沿用 [MIT 许可证](LICENSE)。
