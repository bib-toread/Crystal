# 08 · NPC 脚本与任务

> 传奇2 的绝大部分玩法逻辑（商店、传送、活动、签到、兑换、剧情）都是 NPC 脚本写出来的。本篇讲清楚脚本格式、命令体系、怎么写、怎么扩展，以及任务系统。
>
> 相关源码：`Server/MirObjects/NPC/{NPCScript,NPCSegment,NPCChecks,NPCActions,NPCPage}.cs`、`Server/MirDatabase/NPCInfo.cs`/`QuestInfo.cs`、脚本文件 `Envir/NPCs/*.txt`、任务正文 `Envir/Quests/*.txt`。

---

## 第一部分 · 脚本文件格式

### 1.1 文件位置与加载

- 脚本是纯文本 `.txt`，放在 `Envir/NPCs/`（`Settings.NPCPath`）。每个 NPC 通过 `NPCInfo.FileName` 挂载一个脚本文件。
- 加载入口 `NPCScript.LoadInfo()`（`NPCScript.cs:136`）：读全部行 → `#INSERT`/`#INCLUDE` 预处理 → `ParseScript` 解析成多个**页面 `NPCPage`**，每页含若干**段落 `NPCSegment`**。
- 找不到文件会用本地化 key `ScriptNotFound` 报警。

### 1.2 页面与段落结构

- 脚本由若干 `[@XXX]` **页面键**分段。`[@MAIN]` 是玩家点击 NPC 默认进入的入口页。
- 页内用对白行（裸文本）+ 按钮 `<显示文字/@目标页>` 组织。点按钮跳到对应 `[@目标页]`。
- `ParsePages` 从入口页递归扫描所有可达页面解析进来（`NPCScript.cs:388`）。
- 每页可带**条件块**：`#IF { 条件 } #ACT { 动作 } #ELSEACT { 失败动作 }`，对应一个 `NPCSegment`（成员 `CheckList`/`ActList`/`ElseActList`/`Say`/`Buttons`）。执行时先跑 `CheckList`，全过则执行 `ActList` 并展示 `Say`/`Buttons`，否则走 `ElseSay`/`ElseActList`。
- **预处理指令**：`#INSERT [文件]` 整文件追加；`#INCLUDE [文件] 页名` 把外部文件某页 `{...}` 内容内联——脚本复用机制。

### 1.3 常见页面键（`NPCScript.cs:44`）

| 页面键 | 触发场景 |
|---|---|
| `[@MAIN]` | 点击 NPC 的默认主页 |
| `[@BUY]` / `[@SELL]` / `[@BUYSELL]` | 购买 / 出售 / 买卖一体界面 |
| `[@REPAIR]` / `[@SREPAIR]` | 普通修理 / 特修 |
| `[@STORAGE]` | 打开个人仓库 |
| `[@REFINE]` / `[@REFINECHECK]` / `[@REFINECOLLECT]` | 武器精炼 提交/查看/领取 |
| `[@CRAFT]` | 制造（配方合成）界面 |
| `[@CONSIGN]` / `[@MARKET]` | 寄售 / 拍卖行 |
| `[@CREATEGUILD]` / `[@REQUESTWAR]` | 创建行会 / 申请行会战 |
| `[@SENDPARCEL]` / `[@COLLECTPARCEL]` | 寄包裹 / 取包裹 |
| `[@AWAKENING]` / `[@DISASSEMBLE]` / `[@DOWNGRADE]` | 觉醒 / 分解 / 降级 |
| `[@CREATEHERO]` / `[@MANAGEHERO]` | 创建英雄 / 管理英雄 |
| `[@BUYBACK]` / `[@PEARLBUY]` | 回购 / 元宝购买 |

> 系统页（`[@BUY]`/`[@STORAGE]` 等）会直接打开对应游戏界面，不需要你写界面逻辑，只要跳转过去。

---

## 第二部分 · 命令体系

### 2.1 解析与执行机制

命令在**解析阶段**就被转成强类型对象，不是运行时逐字符解释：

- `NPCSegment.ParseCheck(line)`（`NPCSegment.cs:102`）把条件行 split，先 `ParseArguments`（替换 `%ARG(n)` 页面参数），再按 `parts[0]` 大写在大 `switch` 里 `CheckList.Add(new NPCChecks(CheckType.XXX, 参数))`。
- `ParseAct(line)` 同理 `ActList.Add(new NPCActions(ActionType.XXX, 参数))`。
- 运行时遍历 `CheckList` 调各 `NPCChecks` 判定，全真→执行 `ActList`，否则 `ElseActList`。判定/动作的实现在 `NPCChecks.cs`/`NPCActions.cs`（按枚举分发）。
- **命令名大小写不敏感**（统一 `.ToUpper()` 匹配）。

**变量**：`%P1…%An` 形式的 NPC 变量存在 `player.NPCVar`，用 `MOV`/`CALC` 读写；`%ARG(n)` 是 `#INCLUDE`/调用时传的页面参数。比较运算符 `< > <= >= == !=`，算术 `+ - * /`。

### 2.2 条件检查命令（写在 `#IF` 内 → `CheckList`）

| 命令 | 作用 |
|---|---|
| `CHECKLEVEL <op> <值>` | 玩家等级比较 |
| `CHECKGOLD <op> <值>` | 金币（另有 `CHECKGUILDGOLD`/`CHECKCREDIT`/`CHECKPEARLS`） |
| `CHECKITEM <物品名> <数量>` | 背包是否有某物品 |
| `CHECKGENDER` / `CHECKCLASS` | 性别 / 职业 |
| `CHECK <flag编号> <值>` | 检查持久标志位（配合 `SET`） |
| `CHECKQUEST <任务> <状态>` | 任务状态 |
| `CHECKHUM/CHECKMON <map> <x> <y> …` | 某坐标处玩家/怪物数量 |
| `CHECKBUFF` / `CHECKPET` / `HASBAGSPACE` | buff / 宠物 / 背包空间 |
| `CHECKMAP` / `CHECKRANGE` | 所在地图 / 坐标范围 |
| `RANDOM <n>` | n 分之一概率 |
| `DAYOFWEEK` / `HOUR` / `MIN` | 时间条件（做定时活动） |
| `ISADMIN` / `GROUPLEADER` / `INGUILD` | 身份判定 |
| `CHECKTIMER` / `CHECKCALC` | 计时器 / 表达式计算 |

### 2.3 动作命令（写在 `#ACT` 内 → `ActList`）

**给予/扣除（经济与物品）**
- `GIVEITEM <物品> <数量>` / `TAKEITEM`
- `GIVEGOLD` / `TAKEGOLD` / `GIVEGUILDGOLD` / `TAKEGUILDGOLD`
- `GIVECREDIT` / `GIVEPEARLS` / `GIVEEXP <值>` / `GIVEHP` / `GIVEMP`

**传送/移动**
- `MOVE <map> [x] [y]` / `INSTANCEMOVE <map> <实例> <x> <y>`（副本）
- `TIMERECALL` / `GROUPRECALL` / `GROUPTELEPORT` / `ENTERMAP`

**状态/属性变更**
- `GIVEBUFF <buff> …` / `REMOVEBUFF` / `REFRESHEFFECTS`
- `GIVESKILL` / `REMOVESKILL`
- `CHANGELEVEL` / `CHANGECLASS` / `CHANGEGENDER` / `CHANGEHAIR`
- `SETPKPOINT` / `REDUCEPKPOINT`

**任务/标志/变量与流程**
- `SET <flag> <0/1>`：设置持久标志位（配合 `CHECK`，最常用的「记住玩家做过某事」手段）
- `MOV <%变量> <值>` / `CALC <%变量> <op> <值>`：NPC 变量赋值/运算
- `GOTO <@页>`：无条件跳页；`CALL <[@页]>`：调用并返回；`BREAK`：中断
- `DELAYGOTO <秒> <@页>`：延迟跳转
- `LOADVALUE` / `SAVEVALUE`：玩家自定义持久数值读写

**世界/系统**
- `MONGEN <怪物> <数量>` / `MONCLEAR`：刷怪/清怪
- `LOCALMESSAGE` / `GLOBALMESSAGE` / `PLAYSOUND` / `OPENBROWSER`
- `ADDNAMELIST` / `DELNAMELIST` / `CLEARNAMELIST`（及 `…GUILDNAMELIST`）：名单文件读写
- `COMPOSEMAIL`/`ADDMAILGOLD`/`ADDMAILITEM`/`SENDMAIL`：发系统邮件
- `SETTIMER` / `EXPIRETIMER`：玩家计时器；`ROLLDIE` / `GETRANDOMTEXT`：随机

**模板变量（在对白文本里替换）**：`<$USERNAME>`、`<$LEVEL>`、`<$GAMEGOLD>`、`<$MAP>`、`<$HP>` 等，输出时替换成玩家实际数据。

> 上面是常用子集，完整清单以 `NPCSegment.cs` 的 `ParseCheck`/`ParseAct` 两个 `switch` 为准（Grep `case "` 可列全）。

---

## 第三部分 · 写一个新 NPC 脚本

### 步骤

1. 在 `Envir/NPCs/` 新建 `MyNPC.txt`（或用 `NPCInfoForm` 的「打开脚本」自动生成）。
2. 至少写 `[@MAIN]` 页：对白 + `<文字/@页名>` 按钮。
3. 子页用 `#IF { 条件 } #ACT { 动作 } #ELSEACT { 失败动作 }`。
4. 把脚本绑到 NPC：菜单「数据库 → NPC」新增 `NPCInfo`，设地图/坐标/图像，`FileName` 填 `MyNPC`（不含扩展名）。
5. 菜单「重载 → NPC」热加载生效（脚本是文本，不必重启；但新增的 `NPCInfo` 放置点进了库，需重启让 `Envir.Main` 加载该 NPC）。

### 最小可用示例（新手礼包，含防重复领取）

```
[@MAIN]
你好，勇士。需要点什么？           ; 对白
<我要领取新手礼包/@GIFT>           ; 按钮 → [@GIFT]
<打开仓库/@STORAGE>                ; 系统页：直接开仓库
<离开/@EXIT>                       ; @EXIT 关闭对话

[@GIFT]
#IF                                ; 条件块
CHECKLEVEL > 0                     ; 任意等级（演示）
CHECK 100 0                        ; 持久标志位 100 == 0（没领过）
#ACT                               ; 条件满足时
GIVEITEM 新手剑 1                  ; 给一把新手剑
GIVEGOLD 5000                      ; 给 5000 金币
SET 100 1                          ; 标志位 100 置 1，防重复领取
GOTO @THANKS
#ELSEACT                           ; 条件不满足时
GOTO @ALREADY

[@THANKS]
礼包已发放，祝你旅途顺利！

[@ALREADY]
你已经领取过新手礼包了。
```

> 关键技巧：用 `SET <flag> 1` + `CHECK <flag> 0` 这对命令，是「记住玩家是否做过某事」的标准做法。标志位存在 `CharacterInfo.Flags`，随角色存档。

---

## 第四部分 · 任务系统

任务是**两段式**：元数据进二进制库，逻辑正文走文本。

### 4.1 元数据 QuestInfo

菜单「数据库 → 任务」编辑 `Envir.QuestInfoList`：`Name`、`Group`、`QuestType`、`RequiredMinLevel`/`RequiredQuest`(前置)/`RequiredClass`、各种提示消息、`NpcIndex`(接)/`FinishNpcIndex`(交)、时限。`FileName` 关联任务正文。

### 4.2 任务正文 Envir/Quests/

点 `QuestInfoForm` 的「打开脚本」会生成含标准段的模板：

```
[@Description]
消灭洞穴里的 10 只毒蜘蛛。

[@TaskList]            ; 任务追踪面板显示的条目

[@KillTasks]
毒蜘蛛 10              ; 击杀目标：怪物名 + 数量

[@ItemTasks]
蜘蛛毒囊 5             ; 收集目标：物品名 + 数量

[@FlagTasks]           ; 标志位目标

[@FixedRewards]
金币 10000
经验 5000
回城卷 3

[@SelectRewards]       ; 多选其一的奖励
皮甲 1
布衣 1

[@ExpReward]
5000

[@GoldReward]
10000
```

由 `QuestInfo.ParseFile`（`QuestInfo.cs:161`）解析，目标/奖励按**名字**关联 `MonsterInfo`/`ItemInfo`。

### 4.3 任务与 NPC 脚本配合

- 接任务：NPC 脚本里用任务相关命令或客户端 `C.AcceptQuest`（点 NPC 头顶感叹号）。
- 进度：击杀/收集由战斗/拾取逻辑自动累加 `QuestProgressInfo`。
- 交任务：到 `FinishNpcIndex` 提交，发奖励。
- NPC 脚本可用 `CHECKQUEST <任务> <状态>` 根据任务进度分支对话。

> ⚠️ 任务窗体多选批量编辑有已知问题（见 [05 §7](05-内容开发总览.md#7-已知坑)），任务逐条编辑更稳。

---

## 第五部分 · 新增一个自定义脚本命令

NPC 命令是「解析期建对象 + 运行期分发」两段式，新增需改 3 处。

### 新增一个 ACT 命令（例：`GIVETITLE <称号>`）

1. **加枚举**：`NPCActions.cs` 的 `enum ActionType` 加 `GiveTitle`。
2. **加解析**：`NPCSegment.ParseAct` 的 `switch` 加：
   ```csharp
   case "GIVETITLE":
       if (parts.Length < 2) return;
       acts.Add(new NPCActions(ActionType.GiveTitle, parts[1]));
       break;
   ```
3. **加执行**：在 `NPCActions` 运行时分发（按 `ActionType` 的 `switch`）加 `case ActionType.GiveTitle:`，从 `act.Params[0]` 取参数（以 `%` 开头需先 `FindVariable` 解析变量），调用 `player.AddTitle(...)` 之类。

### 新增一个 CHECK 命令（例：`HASTITLE <称号>`）

1. `enum CheckType` 加 `HasTitle`。
2. `NPCSegment.ParseCheck` 的 `switch` 加 `case "HASTITLE": CheckList.Add(new NPCChecks(CheckType.HasTitle, parts[1])); break;`。
3. 在 `NPCChecks` 运行时 `switch (CheckType)` 加 `case CheckType.HasTitle:` 返回布尔（决定走 `ActList` 还是 `ElseActList`）。

> 要点：解析时传参顺序必须和运行期取 `Params[i]` 的顺序一致。改了命令实现是代码改动，需重新编译服务端。
