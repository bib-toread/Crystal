#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crystal 汉化助手 (localization helper) —— 零依赖，仅用 Python 标准库。

本工具服务两条线：
  A) GameLanguage 的 JSON 本地化 (Client/Server 的 English.json / Chinese.json)
  B) 工具链界面的 WinForms Designer.cs 里硬编码的英文 UI 文本

子命令：
  check                          报告 JSON 翻译完成度 + 一致性
                                 (枚举↔JSON 缺键/多余键、大小写冲突、未翻译清单)
  scan-forms [--out F] [--all]   扫描工具链 Designer.cs 里待汉化的纯英文 UI 文本 -> TSV
  apply-forms F [--dry-run]      按 TSV(填好 chinese 列) 精确回填 Designer.cs
  export-json SCOPE [--out F]    导出 JSON 未翻译条目 -> TSV  (SCOPE = client | server)
  apply-json SCOPE F [--dry-run] 按 TSV(填好 chinese 列) 回填 Chinese.json

典型工作流（持续汉化）：
  1) python tools/localize.py check                      # 看缺口
  2) python tools/localize.py export-json client --out todo.tsv
     python tools/localize.py scan-forms --out forms.tsv
  3) 翻译 TSV 的 chinese 列（人工 / AI）
  4) python tools/localize.py apply-json client todo.tsv
     python tools/localize.py apply-forms forms.tsv

TSV 一律制表符分隔、UTF-8、首行表头。回填只处理 chinese 列非空的行，
采用精确字符串替换，不重写整个文件，保证最小 diff、保留 BOM/CRLF/键顺序。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Windows 终端默认 GBK，统一用 UTF-8 输出，避免中文乱码/特殊字符崩溃
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent  # 仓库根目录

# ---- 本地化 JSON 文件 ----
SCOPES = {
    "client": {
        "en": ROOT / "Client" / "Localization" / "English.json",
        "zh": ROOT / "Client" / "Localization" / "Chinese.json",
        "enum": "ClientTextKeys",
    },
    "server": {
        "en": ROOT / "Server.MirForms" / "Localization" / "English.json",
        "zh": ROOT / "Server.MirForms" / "Localization" / "Chinese.json",
        "enum": "ServerTextKeys",
    },
}
LANGUAGE_CS = ROOT / "Shared" / "Language.cs"

# ---- 工具链界面项目（默认扫描范围）----
FORM_PROJECTS = ["Server.MirForms", "LibraryEditor", "LibraryViewer", "AutoPatcherAdmin"]
# 加 --all 时额外扫描客户端自带的配置窗体
FORM_PROJECTS_ALL = FORM_PROJECTS + ["Client"]

CJK = re.compile(r"[一-鿿]")
# WinForms 设计器默认控件名：camelCase 标识符 + 可选数字，如 toolStrip1 / label3 / statusStrip1
CONTROL_NAME = re.compile(r"^[a-z][A-Za-z]*\d*$")
# 纯技术缩写/符号，不需要翻译
TECH_WORDS = {
    "ai", "hp", "mp", "ac", "mac", "dc", "mc", "sc", "gm", "npc", "id", "ip",
    "http", "https", "url", "xp", "ok", "lib", "db", "ui", "fps", "exp", "pk",
    "x", "y", "z", "rgb", "csv", "json", "ini", "io", "cd", "n/a",
}
# 匹配 someControl.Text = "..."; / .HeaderText / .ToolTipText
FORM_TEXT = re.compile(
    r'(?P<member>[A-Za-z_]\w*)\.(?P<prop>Text|HeaderText|ToolTipText)\s*=\s*"(?P<val>(?:[^"\\]|\\.)*)"'
)


# ============================ 通用 IO ============================
def read_text_keep(path: Path):
    """读取文本，返回 (text, has_bom)。统一用 \\n 处理，写回时还原。"""
    raw = path.read_bytes()
    has_bom = raw[:3] == b"\xef\xbb\xbf"
    if has_bom:
        raw = raw[3:]
    return raw.decode("utf-8"), has_bom


def write_text_keep(path: Path, text: str, has_bom: bool, crlf: bool = True):
    if crlf:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    data = text.encode("utf-8")
    if has_bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def load_json_pairs(path: Path):
    """按 (section, key, value) 顺序返回；保留顺序，区分大小写。"""
    text, _ = read_text_keep(path)
    obj = json.loads(text)
    pairs = []
    for section in ("Text", "Enum"):
        d = obj.get(section) or {}
        for k, v in d.items():
            pairs.append((section, k, v))
    return pairs


def detect_dup_keys_ci(path: Path):
    """检测同一文件内仅大小写不同的键（不区分大小写的解析器会失败）。"""
    text, _ = read_text_keep(path)
    keys = re.findall(r'^\s*"((?:[^"\\]|\\.)*)"\s*:', text, re.M)
    seen = {}
    dups = []
    for k in keys:
        low = k.lower()
        if low in seen and seen[low] != k:
            dups.append((seen[low], k))
        seen.setdefault(low, k)
    return dups


def parse_enum_members(enum_name: str):
    """从 Language.cs 提取某枚举的成员名（best-effort）。"""
    if not LANGUAGE_CS.exists():
        return []
    text, _ = read_text_keep(LANGUAGE_CS)
    m = re.search(r"public\s+enum\s+" + re.escape(enum_name) + r"\s*\{", text)
    if not m:
        return []
    i = m.end()
    depth = 1
    j = i
    while j < len(text) and depth:
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
        j += 1
    body = text[i : j - 1]
    members = []
    for line in body.splitlines():
        line = line.split("//")[0].strip()
        if not line:
            continue
        for token in line.split(","):
            token = token.strip()
            if re.fullmatch(r"[A-Za-z_]\w*", token):
                members.append(token)
    return members


# ============================ 启发式 ============================
def needs_translation(val: str) -> bool:
    """判断一个字符串是否像「待汉化的面向用户 UI 文本」。

    传奇2 编辑器里大量属性缩写（HP:/MP:/DC/MAC/X:/Y:）按惯例保留英文，
    占位符（$map/$x/y）与控件内部名（toolStrip1）也不该翻译，这里统一排除。
    """
    s = val.strip()
    if not s:
        return False
    if CJK.search(s):                       # 已含中文
        return False
    if not re.search(r"[A-Za-z]", s):       # 无字母（纯数字/符号）
        return False
    if s.startswith("$"):                   # 模板占位符 $map / $x/y
        return False
    if CONTROL_NAME.match(s):               # 控件内部名 toolStrip1 / label3
        return False
    if re.match(r"^-?\d", s):               # -1.Lib / 数字占位
        return False
    if re.search(r"\.(Lib|txt|json|ini|map|png|jpg|bmp|dll|exe)$", s, re.I):
        return False
    core = re.sub(r"[^A-Za-z]", "", s)      # 仅保留字母作为「核心词」
    if core.lower() in TECH_WORDS:          # 纯技术缩写（含带标点的 HP: / Mp+%）
        return False
    if len(core) <= 3 and core.isupper():   # 短全大写缩写 X / UID / AI / SC ...
        return False
    return True


# ============================ check ============================
def cmd_check(args):
    for scope, cfg in SCOPES.items():
        print(f"\n=== {scope.upper()} ===")
        if not cfg["zh"].exists() or not cfg["en"].exists():
            print("  JSON 缺失，跳过")
            continue
        en = load_json_pairs(cfg["en"])
        zh = load_json_pairs(cfg["zh"])
        en_keys = {(s, k) for s, k, _ in en}
        zh_map = {(s, k): v for s, k, v in zh}

        total = len(zh)
        zh_cnt = sum(1 for _, _, v in zh if isinstance(v, str) and CJK.search(v))
        untr = [
            (s, k, v) for s, k, v in zh
            if isinstance(v, str) and needs_translation(v)
        ]
        pct = round(100 * zh_cnt / total, 1) if total else 0
        print(f"  翻译完成度: {zh_cnt}/{total} 含中文 ({pct}%)，疑似待翻译 {len(untr)} 条")
        for s, k, v in untr[:20]:
            print(f"    [未译] {s}.{k} = {v!r}")
        if len(untr) > 20:
            print(f"    ... 还有 {len(untr) - 20} 条")

        # 一致性：zh 相对 en 缺/多
        zh_keys = set(zh_map.keys())
        missing = en_keys - zh_keys
        extra = zh_keys - en_keys
        if missing:
            print(f"  [!] Chinese.json 缺少 {len(missing)} 个键（English.json 有）: "
                  + ", ".join(k for _, k in list(missing)[:8]) + (" ..." if len(missing) > 8 else ""))
        if extra:
            print(f"  [!] Chinese.json 多出 {len(extra)} 个键（English.json 无）: "
                  + ", ".join(k for _, k in list(extra)[:8]) + (" ..." if len(extra) > 8 else ""))

        # 枚举 ↔ JSON
        members = set(parse_enum_members(cfg["enum"]))
        if members:
            json_text_keys = {k for s, k, _ in en if s == "Text"}
            no_text = members - json_text_keys
            if no_text:
                print(f"  [!] 枚举 {cfg['enum']} 有 {len(no_text)} 个键在 JSON.Text 无文案: "
                      + ", ".join(list(no_text)[:8]) + (" ..." if len(no_text) > 8 else ""))

        # 大小写冲突
        for which in ("en", "zh"):
            dups = detect_dup_keys_ci(cfg[which])
            if dups:
                print(f"  [!] {which.upper()}.json 大小写冲突键: "
                      + "; ".join(f"{a} vs {b}" for a, b in dups))


# ============================ scan-forms ============================
def cmd_scan_forms(args):
    projects = FORM_PROJECTS_ALL if args.all else FORM_PROJECTS
    rows = []
    for proj in projects:
        base = ROOT / proj
        if not base.exists():
            continue
        for f in sorted(base.rglob("*.Designer.cs")):
            text, _ = read_text_keep(f)
            for ln, line in enumerate(text.splitlines(), 1):
                for m in FORM_TEXT.finditer(line):
                    val = m.group("val")
                    # 反转义后判断
                    try:
                        decoded = json.loads('"' + val + '"')
                    except Exception:
                        decoded = val
                    if needs_translation(decoded):
                        rel = f.relative_to(ROOT).as_posix()
                        rows.append((proj, rel, ln, f"{m.group('member')}.{m.group('prop')}", val, ""))
    header = "project\tfile\tline\tmember\tenglish\tchinese"
    out_lines = [header] + ["\t".join(str(c) for c in r) for r in rows]
    content = "\n".join(out_lines) + "\n"
    if args.out:
        Path(args.out).write_text(content, encoding="utf-8")
        print(f"扫描到 {len(rows)} 条待汉化 UI 文本 -> {args.out}")
    else:
        print(content)
        print(f"# 共 {len(rows)} 条", file=sys.stderr)


# ============================ apply-forms ============================
def cmd_apply_forms(args):
    lines = Path(args.tsv).read_text(encoding="utf-8").splitlines()
    if lines and lines[0].startswith("project\t"):
        lines = lines[1:]
    # 按文件分组
    by_file = {}
    for raw in lines:
        if not raw.strip():
            continue
        cols = raw.split("\t")
        if len(cols) < 6:
            continue
        proj, rel, ln, member, eng, zh = cols[:6]
        if not zh.strip():
            continue
        by_file.setdefault(rel, []).append((int(ln), eng, zh))

    total = 0
    for rel, items in by_file.items():
        path = ROOT / rel
        text, has_bom = read_text_keep(path)
        flines = text.split("\n")
        changed = 0
        for ln, eng, zh in items:
            idx = ln - 1
            if idx < 0 or idx >= len(flines):
                continue
            needle = '"' + eng + '"'
            repl = '"' + zh + '"'
            if needle in flines[idx]:
                flines[idx] = flines[idx].replace(needle, repl, 1)
                changed += 1
            else:
                print(f"  跳过(未匹配) {rel}:{ln}  {eng!r}")
        if changed and not args.dry_run:
            write_text_keep(path, "\n".join(flines), has_bom, crlf=True)
        print(f"  {rel}: {'将改' if args.dry_run else '已改'} {changed} 处")
        total += changed
    print(f"{'[dry-run] ' if args.dry_run else ''}共回填 {total} 处")


# ============================ export-json ============================
def cmd_export_json(args):
    cfg = SCOPES[args.scope]
    en_map = {(s, k): v for s, k, v in load_json_pairs(cfg["en"])}
    zh = load_json_pairs(cfg["zh"])
    rows = []
    for s, k, v in zh:
        if isinstance(v, str) and needs_translation(v):
            rows.append((args.scope, s, k, en_map.get((s, k), v), v, ""))
    header = "scope\tsection\tkey\tenglish\tcurrent\tchinese"
    content = "\n".join([header] + ["\t".join(str(c) for c in r) for r in rows]) + "\n"
    if args.out:
        Path(args.out).write_text(content, encoding="utf-8")
        print(f"导出 {len(rows)} 条未翻译 -> {args.out}")
    else:
        print(content)


# ============================ apply-json ============================
def cmd_apply_json(args):
    cfg = SCOPES[args.scope]
    path = cfg["zh"]
    text, has_bom = read_text_keep(path)
    flines = text.split("\n")

    lines = Path(args.tsv).read_text(encoding="utf-8").splitlines()
    if lines and lines[0].startswith("scope\t"):
        lines = lines[1:]

    # key -> 新中文
    updates = {}
    for raw in lines:
        if not raw.strip():
            continue
        cols = raw.split("\t")
        if len(cols) < 6:
            continue
        _, section, key, eng, cur, zh = cols[:6]
        if zh.strip():
            updates[key] = zh

    # 行级精确替换： "Key": "....."
    changed = 0
    for i, line in enumerate(flines):
        m = re.match(r'^(\s*)"((?:[^"\\]|\\.)*)"(\s*:\s*)"((?:[^"\\]|\\.)*)"(,?)\s*$', line)
        if not m:
            continue
        key = m.group(2)
        if key in updates:
            new_val = json.dumps(updates[key], ensure_ascii=False)[1:-1]  # 转义但不带外层引号
            flines[i] = f'{m.group(1)}"{key}"{m.group(3)}"{new_val}"{m.group(5)}'
            changed += 1
            del updates[key]
    if changed and not args.dry_run:
        write_text_keep(path, "\n".join(flines), has_bom, crlf=True)
    print(f"{'[dry-run] ' if args.dry_run else ''}{path.name}: 回填 {changed} 处"
          + (f"，未匹配 {len(updates)} 个键: {', '.join(list(updates)[:5])}" if updates else ""))


# ============================ main ============================
def main():
    ap = argparse.ArgumentParser(description="Crystal 汉化助手")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="报告翻译完成度与一致性").set_defaults(func=cmd_check)

    p = sub.add_parser("scan-forms", help="扫描 Designer.cs 待汉化 UI 文本")
    p.add_argument("--out", help="输出 TSV 路径（默认打印到 stdout）")
    p.add_argument("--all", action="store_true", help="额外扫描 Client 项目")
    p.set_defaults(func=cmd_scan_forms)

    p = sub.add_parser("apply-forms", help="按 TSV 回填 Designer.cs")
    p.add_argument("tsv")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_apply_forms)

    p = sub.add_parser("export-json", help="导出 JSON 未翻译条目")
    p.add_argument("scope", choices=["client", "server"])
    p.add_argument("--out")
    p.set_defaults(func=cmd_export_json)

    p = sub.add_parser("apply-json", help="按 TSV 回填 Chinese.json")
    p.add_argument("scope", choices=["client", "server"])
    p.add_argument("tsv")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_apply_json)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
