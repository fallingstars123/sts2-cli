# Command-line and engine reference

[中文](#中文) · [Windows launcher](../README.md)

The terminal interface supports Ironclad, Silent, Defect, Regent, and Necrobinder, and accepts `Fool` when the installed game contains the character. See the [upstream setup guide](https://github.com/wuhao21/sts2-cli#setup) for source builds and game compatibility. On Windows, the [portable ZIP](../README.md#download-and-play) already includes the built adapter and runtimes.

From a source checkout with its adapter prepared:

```text
python python/play.py --lang en
python python/play.py --character Silent --ascension 10
python python/play_full_run.py 5 Ironclad
```

Enter `help` during a run for available actions. `map`, `deck`, `potions`, and `relics` display run information. The source CLI records timestamped state and action lines in `logs/`, expires logs after seven days, and accepts `--no-log`.

## JSON protocol

The headless engine speaks one JSON message per line on stdin and stdout. In a prepared source checkout, launch it with `dotnet run --project src/Sts2Headless/Sts2Headless.csproj`.

```json
{"cmd":"start_run","character":"Ironclad","seed":"test","ascension":0}
{"cmd":"action","action":"select_map_node","args":{"col":3,"row":1}}
{"cmd":"action","action":"play_card","args":{"card_index":0,"target_index":0}}
{"cmd":"action","action":"end_turn"}
{"cmd":"quit"}
```

A response is a decision point such as `map_select`, `combat_play`, `card_reward`, `rest_site`, `event_choice`, `shop`, or `game_over`. Protocol identifiers are in English. A stalled combat turn returns `type: "error"` and `error_code: "combat_turn_timeout"` with the current HP, round, and phase. Stop automated actions and keep the state log and engine stderr. If the engine recovers, the first subsequent action returns the recovered decision before accepting another move.

## 中文

[Windows 启动器](../README.zh-CN.md) · [上游源码构建和兼容性说明](https://github.com/wuhao21/sts2-cli#安装)

准备好源码的游戏适配器以后，运行 `python python/play.py` 进入中文终端，或添加 `--lang en` 切换英文。支持 `--character Silent` 指定角色、`--ascension 10` 指定进阶。游戏内输入 `help` 查看操作。`map`、`deck`、`potions`、`relics` 分别显示地图、牌组、药水和遗物。

源码 CLI 默认将操作和状态保存到 `logs/` 下的 JSONL 文件，七天后清理，可用 `--no-log` 关闭。`python python/play_full_run.py 5 Ironclad` 可用于运行引擎兼容性检查。

程序可以通过标准输入和标准输出的逐行 JSON 消息操作引擎，参见上面的 [JSON 协议示例](#json-protocol)。战斗卡住时，`combat_turn_timeout` 响应包含当前血量、回合和阶段。请暂停自动操作并保留状态日志和引擎的 stderr。恢复时第一次提交的操作只返回恢复后的状态，下一次提交才会执行动作。
