# sts2-cli

<details open>
<summary><b>English</b></summary>

A CLI for Slay the Spire 2.

Runs the real game engine headless in your terminal — all damage, card effects, enemy AI, relics, and RNG are identical to the actual game.

![demo](docs/demo_en.gif)

## Setup

Requirements:
- [Slay the Spire 2](https://store.steampowered.com/app/2868840/Slay_the_Spire_2/) on Steam
- [.NET 9+ SDK](https://dotnet.microsoft.com/download)
- Python 3.9+

```bash
git clone https://github.com/wuhao21/sts2-cli.git
cd sts2-cli
./setup.sh      # copies DLLs from Steam → IL patches → builds
```

Or just run `python3 python/play.py` — it auto-detects and sets up on first run.

### Optional: zsh alias (macOS)

Add to `~/.zshrc` for a quick `sts2` shortcut:

```zsh
alias sts2='uv run python3 /path/to/sts2-cli/python/play.py'
```

Then `source ~/.zshrc` and use `sts2` instead of the full command.

## Play

```bash
python3 python/play.py                    # Ironclad, Ascension 0
python3 python/play.py d 4                # Defect, Ascension 4
python3 python/play.py s 10 --lang en     # Silent, Ascension 10, English
```

### Character & Ascension

| Flag | Short | Positional | Example |
|---|---|---|---|
| `--character` | `-c` | first non-number arg | `sts2 d` |
| `--ascension` | `-a` | first number arg | `sts2 7` |

Character abbreviations: `i` Ironclad, `s` Silent, `d` Defect, `r` Regent, `n` Necrobinder (case-insensitive).

```bash
python3 python/play.py d 4        # positional
python3 python/play.py -c d -a 4  # flags
python3 python/play.py -c Defect --ascension 4  # full names
```

Type `help` in-game:

```
  help     — show help
  map      — show map
  deck     — show deck
  potions  — show potions
  relics   — show relics
  quit     — quit

  Map:     path number (1, 2, 3...)
  Combat:  card index / e (end turn) / p1 (use potion 1)
  Reward:  card index / s (skip)
  Rest:    option index
  Event:   option index / leave
  Shop:    c1 (card) / r1 (relic) / p1 (potion) / rm (remove) / leave
```

All indices start from **1**. For selections requiring multiple cards (e.g. an event asking you to remove 2), enter indices separated by commas or spaces:

```
> Choose 2-2 card(s) [index]: 1,3
> Choose 2-2 card(s) [index]: 1 3
```

The prompt shows the required count range. Invalid indices or wrong counts are rejected with an explanation.

## JSON Protocol

For programmatic control (AI agents, RL, etc.), communicate via stdin/stdout JSON:

```bash
dotnet run --project Sts2Headless/Sts2Headless.csproj
```

```json
{"cmd": "start_run", "character": "Ironclad", "seed": "test", "ascension": 0}
{"cmd": "action", "action": "play_card", "args": {"card_index": 0, "target_index": 0}}
{"cmd": "action", "action": "end_turn"}
{"cmd": "action", "action": "select_map_node", "args": {"col": 3, "row": 1}}
{"cmd": "action", "action": "skip_card_reward"}
{"cmd": "quit"}
```

Each command returns a JSON decision point (`map_select` / `combat_play` / `card_reward` / `rest_site` / `event_choice` / `shop` / `game_over`). All names are bilingual (en/zh).

## Supported Characters

| Character | Status |
|---|---|
| Ironclad | Fully playable |
| Silent | Fully playable |
| Defect | Fully playable |
| Necrobinder | Fully playable |
| Regent | Fully playable |

## Architecture

```
Your code (Python / JS / LLM)
    │  JSON stdin/stdout
    ▼
Sts2Headless (C#)
    │  RunSimulator.cs
    ▼
sts2.dll (game engine, IL patched)
  + GodotStubs (replaces GodotSharp.dll)
  + Harmony patches (localization)
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

</details>

<details>
<summary><b>中文</b></summary>

杀戮尖塔2的命令行版本。

在终端里运行真实游戏引擎 — 所有伤害计算、卡牌效果、敌人AI、遗物触发、随机数都和真实游戏一致。

![demo](docs/demo_zh.gif)

## 安装

需要：
- [Slay the Spire 2](https://store.steampowered.com/app/2868840/Slay_the_Spire_2/) (Steam)
- [.NET 9+ SDK](https://dotnet.microsoft.com/download)
- Python 3.9+

```bash
git clone https://github.com/wuhao21/sts2-cli.git
cd sts2-cli
./setup.sh      # 从 Steam 复制 DLL → IL patch → 编译
```

或者直接运行 `python3 python/play.py`，首次会自动完成 setup。

### 可选：zsh 快捷别名（macOS）

在 `~/.zshrc` 中添加：

```zsh
alias sts2='uv run python3 /path/to/sts2-cli/python/play.py'
```

然后 `source ~/.zshrc`，之后可以直接用 `sts2` 代替完整命令。

## 玩

```bash
python3 python/play.py                    # 铁甲战士，进阶 0
python3 python/play.py d 4                # 故障机器人，进阶 4
python3 python/play.py s 10 --lang en     # 静默猎手，进阶 10，英文
```

### 角色与进阶

| 完整参数 | 短参数 | 位置参数 | 示例 |
|---|---|---|---|
| `--character` | `-c` | 第一个非数字参数 | `sts2 d` |
| `--ascension` | `-a` | 第一个数字参数 | `sts2 7` |

角色缩写：`i` 铁甲战士, `s` 静默猎手, `d` 故障机器人, `r` 储君, `n` 亡灵契约师（大小写不敏感）。

```bash
python3 python/play.py d 4        # 位置参数
python3 python/play.py -c d -a 4  # 短参数
python3 python/play.py -c Defect --ascension 4  # 完整参数
```

游戏内输入 `help` 查看所有命令：

```
  help     — 帮助
  map      — 显示地图
  deck     — 查看牌组
  potions  — 查看药水
  relics   — 查看遗物
  quit     — 退出

  地图:    输入编号 (1, 2, 3...)
  战斗:    输入卡牌编号 / e 结束回合 / p1 使用药水1
  奖励:    输入卡牌编号 / s 跳过
  休息:    输入选项编号
  事件:    输入选项编号 / leave 离开
  商店:    c1 买卡 / r1 买遗物 / p1 买药水 / rm 移除 / leave 离开
```

所有编号从 **1** 开始。需要选择多张卡牌时（如某些事件要求移除2张），用逗号或空格分隔编号：

```
> 选择 2-2 张卡牌 [编号]: 1,3
> 选择 2-2 张卡牌 [编号]: 1 3
```

提示语会显示所需数量范围，输入无效编号或数量不符时会给出说明并重新提示。

## 角色支持

| 角色 | 状态 |
|---|---|
| 铁甲战士 (Ironclad) | 完全可玩 |
| 静默猎手 (Silent) | 完全可玩 |
| 故障机器人 (Defect) | 完全可玩 |
| 亡灵契约师 (Necrobinder) | 完全可玩 |
| 储君 (Regent) | 完全可玩 |

## JSON 协议

除了交互模式，也可以通过 stdin/stdout JSON 协议编程控制（写 AI agent、RL 训练等）：

```bash
dotnet run --project Sts2Headless/Sts2Headless.csproj
```

```json
{"cmd": "start_run", "character": "Ironclad", "seed": "test", "ascension": 0}
{"cmd": "action", "action": "play_card", "args": {"card_index": 0, "target_index": 0}}
{"cmd": "action", "action": "end_turn"}
{"cmd": "action", "action": "select_map_node", "args": {"col": 3, "row": 1}}
{"cmd": "action", "action": "skip_card_reward"}
{"cmd": "quit"}
```

每个命令返回一个 JSON decision point（`map_select` / `combat_play` / `card_reward` / `rest_site` / `event_choice` / `shop` / `game_over`），所有名称都是中英双语。

## 架构

```
你的代码 (Python / JS / LLM)
    │  JSON stdin/stdout
    ▼
Sts2Headless (C#)
    │  RunSimulator.cs
    ▼
sts2.dll (游戏引擎, IL patched)
  + GodotStubs (替代 GodotSharp.dll)
  + Harmony patches (本地化)
```

## 更新日志

参见 [CHANGELOG.md](CHANGELOG.md)。

</details>
