# Crystal 开发文档

本目录是对 Crystal（《热血传奇2 / Legend of Mir 2》开源服务端+客户端引擎）的系统性中文开发文档，分为**两册**：

- **第一册：架构分析** —— 讲清楚系统「怎么运转」，面向要改引擎、加系统的开发者，深入到类、数据流与扩展点。
- **第二册：内容开发指南** —— 讲清楚「怎么往里加游戏内容」，面向做怪物/物品/NPC/技能/任务/地图/玩法的策划与开发，给完整步骤和示例。

> 本文档基于 `futures/chines` 分支源码分析整理。正文中的 `文件路径:行号`（如 `Server/MirEnvir/Envir.cs:1996`）均指向仓库内真实位置，可据此定位源码；行号会随代码改动漂移，以**方法名/类名**为准更可靠。
> 工程总览、编译命令、代码风格见仓库根目录的 [`CLAUDE.md`](../CLAUDE.md)，不在此重复。

---

## 文档导航

### 第一册 · 架构分析

| 文档 | 内容 |
|---|---|
| [01-总体架构](01-总体架构.md) | 解决方案结构、三大进程、一次端到端交互的数据流、世界模型与运行模型总览 |
| [02-通信协议](02-通信协议.md) | 封包线上格式、序列化、注册表、`GameStage` 状态机、收发与广播、**端到端新增一个封包** |
| [03-服务端架构](03-服务端架构.md) | `Envir` 主循环、对象调度、多线程怪物、实体层级与战斗/属性/技能/状态、数据持久化与版本兼容 |
| [04-客户端架构](04-客户端架构.md) | `CMain` 循环、DirectX9 图形栈、`.Lib` 图档、场景/控件框架、对象表现层与帧动画、玩法 UI↔封包闭环 |

### 第二册 · 内容开发指南

| 文档 | 内容 |
|---|---|
| [05-内容开发总览](05-内容开发总览.md) | 数据怎么组织（二进制库 vs 文本文件）、编辑器工作流、热重载与生效、**新建一份内容的推荐流程** |
| [06-物品与技能](06-物品与技能.md) | 新增物品 `ItemInfo`、装备外观、`UserItem` 实例、技能 `MagicInfo`/`Spell`、给技能加新效果 |
| [07-怪物与AI](07-怪物与AI.md) | 新增 `MonsterInfo`、自定义怪物 AI 子类、刷怪、掉落、客户端图档与帧动画 |
| [08-NPC脚本与任务](08-NPC脚本与任务.md) | NPC 脚本格式、命令大全（CHECK/ACT）、最小示例、任务系统、新增脚本命令 |
| [09-地图与玩法系统](09-地图与玩法系统.md) | 地图 `MapInfo`、安全区/传送/刷怪、可视化编辑、行会/攻城等玩法、**新增全局定时世界事件** |

---

## 速查：核心概念地图

| 概念 | 关键位置 | 一句话 |
|---|---|---|
| 世界单例 | `Envir.Main`（`Server/MirEnvir/Envir.cs`） | 持有整个游戏世界；`Envir.Edit` 是编辑器用的第二实例 |
| 服务端主循环 | `Envir.WorkLoop()` | 单线程权威循环，推进 `Time`、处理连接与对象、定时存盘 |
| 封包协议 | `Shared/Packet.cs` | `[2字节长度][2字节id][负载]`，注册表 `GetClientPacket`/`GetServerPacket` |
| 服务端连接 | `MirConnection.ProcessPacket`（`Server/MirNetwork/`） | 把客户端封包路由到 `Player.*` / `Envir.*` |
| 实体基类 | `MapObject`（服务端/客户端各一套） | 地图上一切对象的抽象基类 |
| 战斗/属性/技能 | `HumanObject.cs`（服务端） | 玩家+英雄共享的战斗代码几乎都在这 |
| 怪物 AI | `MonsterObject.GetMonster()` + `Monsters/*.cs` | `MonsterInfo.AI`（int）选具体子类 |
| NPC 脚本 | `Envir/NPCs/*.txt` + `NPCScript`/`NPCSegment` | 文本段落 `[@MAIN]`，命令 CHECK/ACT |
| 数据模板 | `Server/MirDatabase/*Info.cs` | `ItemInfo`/`MonsterInfo`/`MapInfo`… 存进二进制库 |
| 持久化 | `Server.MirDB`（世界）+ `Server.MirADB`（账号） | 平铺二进制文件，非 SQL；`Envir/` 下另有文本数据树 |
| 客户端循环 | `CMain`（`Client/Forms/CMain.cs`） | `Application.Idle` 驱动，SlimDX/DirectX9 渲染 |
| 客户端图档 | `MLibrary`/`MImage`（`Client/MirGraphics/`） | `.Lib` 资源包按 index 取帧绘制 |
| 客户端场景 | `MirScene.ActiveScene` | `LoginScene`/`SelectScene`/`GameScene` 三大场景 |

---

## 怎么用这套文档

- **第一次接触代码**：先读 [01-总体架构](01-总体架构.md) 建立全局观，再按需要深入 02/03/04。
- **要加一种游戏内容**：直接翻第二册对应章节，每章都有「完整步骤 + 示例 + 要动哪些文件」。
- **要改协议/加系统**：[02-通信协议](02-通信协议.md) 的「端到端新增封包」是绕不开的一步，配合 03（服务端落点）与 04（客户端落点）。
