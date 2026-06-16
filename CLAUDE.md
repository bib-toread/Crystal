# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指导。

## 这是什么

Crystal —— LOMCN 社区开源的 *热血传奇2（The Legend of Mir 2）* 服务端与客户端引擎，原游戏是 1999 年的 2D MMORPG。纯托管 C#/.NET 8，**仅支持 Windows**（WinForms + DirectX 9）。整个解决方案 `Legend of Mir.sln` 包含游戏客户端、游戏服务端、共享协议层，以及若干编辑器/补丁工具。

图档（`.Lib` 资源包）、地图和运行期游戏数据**不在本仓库内** —— 它们由社区单独分发。仓库里的代码不依赖这些资源即可编译，但客户端/服务端在运行时需要它们。

## 深度开发文档

`docs/` 目录下有一套系统性的中文开发文档（见 [`docs/README.md`](docs/README.md)），分两册：**架构分析**（总体/通信协议/服务端/客户端）与**内容开发指南**（物品技能/怪物AI/NPC脚本任务/地图玩法）。需要深入某个子系统、或要新增游戏内容时，优先查阅对应篇章——本文件只是速览，`docs/` 才是细节与扩展点。

## 编译与运行

本仓库**没有测试套件**，也没有 CI —— 验证方式是编译并运行程序。

- 编译全部：用 Visual Studio 2022 (17.5+) 打开 `Legend of Mir.sln`，或在已安装 .NET 8 SDK 时执行 `dotnet build "Legend of Mir.sln"`。（默认 shell 的 PATH 里没有 `dotnet`，请使用 VS 开发者命令提示符或自行安装 SDK。）
- 编译单个项目：`dotnet build Client/Client.csproj -c Debug`
- 编译产物输出到 **`Build\Client\`** 和 **`Build\Server\`**（通过 `BaseOutputPath` 重定向，不会追加 `net8.0`/RID 子目录）。
- 启动顺序：先启动**服务端**（`Build\Server\Server.exe`），再启动**客户端**（`Build\Client\Client.exe`）。
- 客户端 `DEBUG` 编译（以及 `-tc` 命令行参数）会设置 `Settings.UseTestConfig = true`，加载独立的测试配置，便于开发客户端连接本地服务端。
- 原生依赖位于 `Components/`，通过 `HintPath` 引用（SlimDX = DirectX 9 封装，ManagedSquish = 纹理压缩，Ionic.Zlib，CustomFormControl，VisualBasic.PowerPacks）。这些不在 NuGet 上。

## 项目结构（整体视图）

| 项目（目录） | 目标框架 | 职责 |
|---|---|---|
| **Shared** (`Shared/`) | net8.0 | 客户端与服务端共享的协议层和数据类型，是两者之间的契约。 |
| **Server.Library** (`Server/`) | net8.0 | 游戏引擎：世界模拟、实体、持久化、网络、NPC 脚本。命名空间是 `Server.*`，与目录名不同。 |
| **Server** (`Server.MirForms/`) | net8.0-windows | WinForms 管理程序 + **服务端入口**（`Program.cs` → `SMain`）。引用 Server.Library + Shared，最终产出 `Server.exe`。 |
| **Client** (`Client/`) | net8.0-windows | WinForms + SlimDX (DirectX 9) 游戏客户端。 |
| AutoPatcherAdmin、LibraryEditor、LibraryViewer、CustomFormControl、PatcherWebSite | — | 工具链：补丁构建器、`.Lib` 图档编辑器/查看器、共享 WinForms 控件，以及补丁网站前端（ASP.NET，net4.8）。 |

注意命名陷阱：引擎库在 `Server/` 目录（`Server.Library.csproj`），而可运行的服务端可执行文件在 `Server.MirForms/` 目录（`Server.csproj`）。

## 网络协议（系统的核心）

所有客户端/服务端通信都是定义在 `Shared/` 中的"长度前缀二进制封包"：

- **线上格式**：`[2 字节长度][2 字节封包 id][负载]`。见 `Shared/Packet.cs`（`ReceivePacket` / `GetPacketBytes`）。
- `Packet.IsServer`（静态，在各自的 `Program.cs` 启动时设置一次）决定反序列化方向。
- **客户端→服务端**的封包是 `Shared/ClientPackets.cs` 里的类（别名 `C`）；**服务端→客户端**在 `Shared/ServerPackets.cs`（别名 `S`）。每个封包都有 `Index`（来自 `Shared/Enums.cs` 里的 `ClientPacketIds`/`ServerPacketIds` 枚举），并通过 `BinaryReader`/`BinaryWriter` 实现 `ReadPacket`/`WritePacket`。
- **注册表**：`Shared/Packet.cs` 里的大型 `switch`（`GetClientPacket` / `GetServerPacket`）把 id 映射到新的封包实例。每个封包都必须登记在这里，否则会被静默丢弃。

**端到端新增一个封包**（需要改动多个文件）：
1. 在 `Shared/Enums.cs` 的 `ClientPacketIds` 或 `ServerPacketIds` 枚举中加入 id。
2. 在 `Shared/ClientPackets.cs` 或 `Shared/ServerPackets.cs` 中加入封包类（`Index` + `ReadPacket`/`WritePacket`）。
3. 在 `Shared/Packet.cs` 对应的 `switch` 中注册。
4. 处理它：**服务端**在 `MirConnection.ProcessPacket`（`Server/MirNetwork/MirConnection.cs`）；**客户端**在当前激活场景的 `ProcessPacket`（`LoginScene` / `SelectScene` / `GameScene`），由 `Network.Process`（`Client/MirNetwork/Network.cs`）分发。

## 服务端运行模型

- 单例 **`Envir.Main`**（`Server/MirEnvir/Envir.cs`）持有整个世界。（`Envir.Edit` 是编辑器窗体使用的第二个实例。）
- 单一权威游戏线程运行 `WorkLoop()`：推进 `Time`（Stopwatch 毫秒），每毫秒 tick 处理一次所有连接，遍历 `Objects` 链表并以约 20ms 的时间片调用 `MapObject.Process()`，处理地图，并按保存定时器刷写数据库。
- 可选的多线程怪物处理（`Settings.Multithreaded`、`MobThreads`）：非宠物怪物分摊到多个工作线程，而玩家/宠物保留在主线程。改动怪物 AI 时要注意跨线程状态。
- **实体层级**：`MapObject`（抽象）→ `HumanObject` → `PlayerObject` / `HeroObject`；以及 `MapObject` → `MonsterObject` → 各怪物子类。NPC 是由脚本驱动的独立对象。
- **持久化是平铺文件**，不是 SQL 数据库：二进制 `Server.MirDB`（世界/游戏数据）与 `Server.MirADB`（账号），外加 `Envir/` 下的文本/数据目录树（`NPCs/`、`Quests/`、`Drops/`、`Recipe/`、`Routes/`、`Values/` 等）、`Maps/` 和 `Configs/Setup.ini`。定期备份写入 `Back Up/`。路径定义在 `Server/Settings.cs` 和 `Envir.cs`。
- **怪物 AI**：每种怪物行为是 `Server/MirObjects/Monsters/` 下 `MonsterObject` 的子类，由 `MonsterInfo.AI`（一个 int）通过 `MonsterObject.GetMonster()` 里的大 `switch` 选择。新增一种行为 = 新建一个子类 + 加一个 `case`。
- **NPC 脚本**：文本脚本位于 `Envir/NPCs/*.txt`，由 `NPCScript` + `NPCSegment`（`Server/MirObjects/NPC/`）解析执行。逻辑按段落组织，段落键形如 `[@MAIN]`、`[@BUY]`、`[@SELL]`、`[@STORAGE]` 等（见 `NPCScript.cs` 里的 `*Key` 常量）。
- **版本校验**：当 `Settings.CheckVersion` 开启时，`Envir.Version` / `Envir.MinVersion` 必须与客户端匹配。协议变动时需要更新这些值。

## 客户端运行模型

- `CMain : RenderForm`（`Client/Forms/CMain.cs`）—— SlimDX 渲染窗体。游戏循环由 `Application.Idle` 驱动 → `UpdateEnviroment()` + `RenderEnvironment()`（经 `DXManager` 走 DirectX 9），而非固定定时器。
- UI 是场景/控件树：`MirScene` 子类（`LoginScene`、`SelectScene`、`GameScene`，位于 `Client/MirScenes/`）承载 `MirControl` 派生的控件（`Client/MirControls/`）和对话框（`Client/MirScenes/Dialogs/`）。
- 图档从 `.Lib` 资源包经 `MLibrary`/`DXManager`（`Client/MirGraphics/`）加载；音频使用 NAudio（`Client/MirSounds/`）。
- 自动补丁器（`AMain`）可在游戏窗体之前运行；若已暂存 `.gz` 更新包，`Program.cs` 会换入 `AutoPatcher.exe`。

## 本地化

字符串通过 `GameLanguage`（`Shared/Language.cs`）查找，以 `ClientTextKeys` / `ServerTextKeys` 枚举为键，由 `Client/Localization/` 和 `Server.MirForms/Localization/` 下的 JSON 支撑（`English.json`、`Chinese.json`；会复制到输出目录）。服务端语言由 `Settings.Language` 选择。

**优先使用 `GameLanguage.ClientTextMap.GetLocalization(key, args…)` / `ServerTextMap.GetLocalization(...)`，而不是硬编码面向用户的字符串。** 新增 UI 文本时，往枚举里加一个键，并在每个 JSON 文件中加一条目。（这是当前分支正在进行的工作 —— 近期提交在处理中文翻译。）

## 代码风格

`.editorconfig` 是权威标准，作用于整个解决方案：
- CRLF 换行，4 空格缩进。
- 对内置类型和类型显而易见的场景，**优先使用显式类型而非 `var`**（`csharp_style_var_* = false`）。
- 表达式体成员用于属性/访问器/索引器，但**不**用于方法或构造函数。
- 接口以 `I` 前缀；类型和成员用 PascalCase。
- 各项目均为 `<Nullable>disable</Nullable>` 和 `<ImplicitUsings>enable</ImplicitUsings>` —— 全局 using 已开启，因此很多文件没有 `using` 块。
