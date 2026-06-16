# tools/ — 汉化助手

`localize.py` 是一个零依赖（仅 Python 标准库）的本地化辅助工具，服务两条线：

- **A) GameLanguage 的 JSON 本地化** —— `Client/Localization` 与 `Server.MirForms/Localization` 下的 `English.json` / `Chinese.json`。
- **B) 工具链界面的硬编码英文** —— `Server.MirForms`、`LibraryEditor`、`LibraryViewer`、`AutoPatcherAdmin` 的 WinForms `*.Designer.cs` 里 `.Text` / `.HeaderText` / `.ToolTipText` 的英文 UI 文本（这部分不走 GameLanguage）。

## 子命令

| 命令 | 作用 |
|---|---|
| `check` | 报告 JSON 翻译完成度 + 一致性（枚举↔JSON 缺键/多余键、大小写冲突键、未翻译清单） |
| `scan-forms [--out F] [--all]` | 扫描 Designer.cs 里**待汉化的纯英文 UI 文本** → TSV。已智能排除控件内部名（`toolStrip1`）、占位符（`$map`）、传奇属性缩写（`HP:`/`X:`/`MAC`）。`--all` 额外扫 `Client` |
| `apply-forms F [--dry-run]` | 按 TSV（填好 `chinese` 列）**精确回填** Designer.cs，保留 UTF-8 BOM / CRLF |
| `export-json {client\|server} [--out F]` | 导出 Chinese.json 里未翻译条目 → TSV |
| `apply-json {client\|server} F [--dry-run]` | 按 TSV 回填 Chinese.json，保留 no-BOM / CRLF / 键顺序 |

> Windows 终端默认 GBK，脚本已强制 UTF-8 输出。若仍乱码，命令前加 `PYTHONIOENCODING=utf-8`。
> 所有回填都是**精确字符串替换**，不重写整个文件，diff 最小、零格式漂移。`--dry-run` 先验证匹配再落地。

## 工作流 1：持续汉化 JSON（加了新 ClientTextKeys 后）

```bash
python tools/localize.py check                              # 看缺口
python tools/localize.py export-json client --out todo.tsv  # 导出未译
# 翻译 todo.tsv 的 chinese 列（人工 / AI）
python tools/localize.py apply-json client todo.tsv         # 回填
```

## 工作流 2：恢复工具链界面汉化（重要）

WinForms **设计器在 Visual Studio 里编辑窗体时会重写 `*.Designer.cs`**，可能把已汉化的中文冲回英文。此时不必手动重译：

```bash
python tools/localize.py apply-forms tools/forms_zh.tsv --dry-run   # 看会改哪些
python tools/localize.py apply-forms tools/forms_zh.tsv             # 一键恢复
```

`tools/forms_zh.tsv` 是已汉化的「英文→中文」翻译表（含文件:行号），是本次工具链界面汉化的成果记录，也是日后一键恢复/补译的依据。新增窗体后重新 `scan-forms` 追加即可。

## 已知边界

- `scan-forms` 的「是否待汉化」是启发式判断，可能漏判/误判少量项；回填前请扫一眼 TSV。
- `check` 报告的「大小写冲突键」（如 `LogOut`/`Logout`）在 C# 区分大小写下是**合法的不同键**，**不要删除**——只是提醒不区分大小写的外部工具（如 PowerShell `ConvertFrom-Json`）解析这些 JSON 会失败。
