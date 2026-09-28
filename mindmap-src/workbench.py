#!/usr/bin/env python -u
# -*- coding: utf-8 -*-
r"""
思维导图工作台 —— 跨会话续跑的单一入口。

设计原则
  · 进度不靠人工标记，而是**从文件系统自动推导**，永远不会失同步
  · 所有状态落在 _工作台/ 下，会话重启后读一次就恢复全部上下文
  · 每套卷的处理是幂等的：已有产物就跳过，可反复重跑

命令
  python workbench.py scan        重建 sources.json（810 套 → 源文件清单）
  python workbench.py status      打印总进度 + 各院校完成情况
  python workbench.py next [N]    下一批该做什么（默认按院校给 1 批）
  python workbench.py brief <key> 输出某一套的源文正文（供写作时阅读）
  python workbench.py xlsx        导出 思维导图进度表.xlsx（人看版）
  python workbench.py note <key> <文本>   记录问题/备注
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
WB = HERE / "_工作台"
SRC_JSON = WB / "sources.json"
NOTES = WB / "notes.json"
XLSX = HERE / "思维导图进度表.xlsx"

MINERU = HERE / "mineru_full" / "mineru_text"
MINERU_OUT = HERE / "mineru_out"
V6 = HERE / "思维导图_v6"
INTER = HERE / "思维导图_交互"
PDF = HERE / "思维导图_PDF"
import pdf_paths as PP          # PDF 按院校分文件夹（pdf_of 兼容旧平铺）
INDEX = HERE / "真题索引.xlsx"

YEAR_LO, YEAR_HI = "2015", "2025"

S985 = set("""清华大学 北京航空航天大学 北京理工大学 南开大学 天津大学 大连理工大学 东北大学 吉林大学
哈尔滨工业大学 同济大学 上海交通大学 南京大学 浙江大学 中国科学技术大学 厦门大学 山东大学 中国海洋大学
武汉大学 华中科技大学 湖南大学 中南大学 华南理工大学 四川大学 重庆大学 电子科技大学 西安交通大学
西北工业大学 国防科技大学""".split())
S211 = set("""北京交通大学 北京工业大学 北京科技大学 北京化工大学 北京邮电大学 北京林业大学 华北电力大学
河北工业大学 太原理工大学 内蒙古大学 大连海事大学 哈尔滨工程大学 东北林业大学 华东理工大学 东华大学
上海大学 南京航空航天大学 南京理工大学 苏州大学 南京师范大学 中国矿业大学 河海大学 江南大学 安徽大学
合肥工业大学 福州大学 南昌大学 郑州大学 武汉理工大学 海南大学 贵州大学 新疆大学 西安电子科技大学
长安大学 中国石油大学(北京) 中国石油大学(华东)""".split())
STRONG = set("广东工业大学 杭州电子科技大学 燕山大学 南京信息工程大学 西安理工大学 南京邮电大学 重庆邮电大学 \
浙江工业大学 上海理工大学 哈尔滨理工大学 武汉科技大学 深圳大学 山西大学 东北电力大学 天津工业大学 \
上海电力大学 中国计量大学 西安邮电大学 长沙理工大学 兰州理工大学 河南科技大学 华东交通大学 南京工业大学".split())




def _base(s: str) -> str:
    """去掉校区/学硕专硕后缀，用于匹配 985/211/强势双非 名单。"""
    return re.sub(r"\((保定|北京|徐州|华东|武汉|深圳|威海|苏州|盘锦)\)$", "", str(s)).strip()


def tier(s: str) -> str:
    b = _base(s)
    for cand in (s, b):
        if cand in S985:
            return "985"
        if cand in S211:
            return "211"
        if cand in STRONG:
            return "强势双非"
    return "其他"


# ============================================================ 扫描源
ALIAS = {"中国矿业大学": "中国矿业大学(徐州)"}


def norm(n: str) -> str:
    n = str(n).strip().replace("（", "(").replace("）", ")")
    n = n.replace("学硕", "").replace("专硕", "").strip()
    return ALIAS.get(n, n)


def key_of(school: str, code: str, year: str) -> str:
    """★ key 规则：院校_代码_年份（同年多套不同专业课代码的卷各自独立）"""
    return f"{school}_{code}_{year}"


def split_key(key: str) -> tuple[str, str, str]:
    parts = key.rsplit("_", 2)
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 else (key, "", "")



# ---------------------------------------------------------------- 从正文抽代码
CODE_RE = re.compile(r"(?:考试)?科目代码\s*[:：]\s*\*{0,2}\s*(\d{3})")
YEAR_HDR = None      # 运行时按院校填充


def codes_from_text(path: Path, school: str) -> dict[str, str]:
    """从合订本/试题册正文里抽出 {年份: 科目代码}。
    规则：宝典与试题册的代码一律以正文印的为准（文件名代码有 ~5% 是错的）。"""
    try:
        t = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    hdr = re.compile(rf"^#*\s*{re.escape(school)}\s*(20\d\d)\s*年", re.M)
    ms = list(hdr.finditer(t))
    out: dict[str, str] = {}
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else min(len(t), m.start() + 30000)
        seg = t[m.start():end]
        if "答案" in (seg.splitlines()[0] if seg.splitlines() else ""):
            continue
        c = CODE_RE.search(seg[:3000])
        if c:
            out.setdefault(m.group(1), c.group(1))
    if not out:
        c = CODE_RE.search(t[:20000])
        if c:
            y = re.search(r"(20\d\d)\s*年", t[:4000])
            if y:
                out[y.group(1)] = c.group(1)
    return out


def scan() -> dict:
    """从两个来源重建源清单：① 逐年真题文件 ② 宝典合订本卷目表。"""
    import openpyxl
    wb = openpyxl.load_workbook(INDEX, read_only=True)

    # 源① 逐年文件
    src_y: dict[tuple[str, str, str], Path] = {}
    for p in sorted(MINERU.glob("*/*.md")):
        m = re.match(r"^(.+?)(\d{3})控制考研(20\d\d)年真题", p.name)
        if m:
            src_y.setdefault((norm(m.group(1)), m.group(2), m.group(3)), p)
    for p in sorted(MINERU_OUT.glob("*/*2025试题册*.md")):
        m = re.match(r"^(.+?)2025试题册", p.name)
        if m:
            s = norm(m.group(1))
            c = codes_from_text(p, s).get("2025")
            if not c:                      # 试题册标题常写成「XX大学2025研究生入学考试试题」，无「年」
                mm = CODE_RE.search(p.read_text(encoding="utf-8", errors="replace")[:6000])
                c = mm.group(1) if mm else "NA"
            src_y.setdefault((s, c, "2025"), p)

    # 源② 宝典卷目
    rows = list(wb["宝典卷目"].iter_rows(values_only=True))
    hd = list(rows[0])
    src_b: dict[tuple[str, str, str], dict] = {}
    # ★ 宝典文件按 (院校, 文件名义代码) 建索引 —— 一校多宝典时不能只存一个
    bd_file: dict[tuple[str, str], Path] = {}
    for p in sorted(MINERU.glob("*/*.md")):
        m = re.match(r"^27宝典A[：:](.+?)(\d{3})?真题及[答解]", p.name)
        if m:
            bd_file[(norm(m.group(1)), m.group(2) or "")] = p
    text_codes: dict[str, dict[str, str]] = {}      # 宝典路径 -> {年份: 代码}
    for r in rows[1:]:
        d = dict(zip(hd, r))
        s = norm(d.get("院校")); c = str(d.get("院校代码") or "").strip()
        y = str(d.get("年份") or "").strip()
        if not (s and c and re.fullmatch(r"20\d\d", y)):
            continue
        f = bd_file.get((s, c)) or bd_file.get((s, ""))
        if f and (s, c) not in text_codes:
            text_codes[(s, c)] = codes_from_text(f, s)
        # ★ 代码优先级：该年正文 → 该合订本出现最多的正文代码 → 文件名
        tc = text_codes.get((s, c)) or {}
        if tc:
            from collections import Counter as _C
            real = tc.get(y) or _C(tc.values()).most_common(1)[0][0]
        else:
            real = c
        e = src_b.setdefault((s, real, y), {})
        t = str(d.get("卷目标题") or "")
        e["答案页" if "答案" in t else "真题页"] = d.get("合订本起始页")

    # 合并 + 补 NA 代码（用该校其它年份的代码）
    allk = set(src_y) | set(src_b)
    school_codes: dict[str, set[str]] = {}
    for (s, c, y) in allk:
        if c != "NA":
            school_codes.setdefault(s, set()).add(c)
    fixed: set[tuple[str, str, str]] = set()
    for (s, c, y) in allk:
        if c == "NA" and len(school_codes.get(s, ())) == 1:
            fixed.add((s, next(iter(school_codes[s])), y))
        else:
            fixed.add((s, c, y))

    out: dict[str, dict] = {}
    for (s, c, y) in sorted(fixed, key=lambda x: (x[0], x[2], x[1])):
        if tier(s) not in ("985", "211", "强势双非") or not (YEAR_LO <= y <= YEAR_HI):
            continue
        yy = src_y.get((s, c, y)) or src_y.get((s, "NA", y))
        bd = src_b.get((s, c, y), {})
        f = bd_file.get(s)
        rec = {
            "院校": s, "代码": c, "年份": y, "层级": tier(s),
            "真题文件": str(yy.relative_to(HERE)) if yy else "",
            "宝典文件": str((bd_file.get((s, c)) or bd_file.get((s, ""))).relative_to(HERE))
                         if (bd and (bd_file.get((s, c)) or bd_file.get((s, "")))) else "",
            "宝典真题页": bd.get("真题页", ""),
            "宝典答案页": bd.get("答案页", ""),
            "源": "逐年" if yy else ("宝典" if bd else "缺"),
        }
        out[key_of(s, c, y)] = rec

    WB.mkdir(exist_ok=True)
    SRC_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(out)
    miss = [k for k, v in out.items() if v["源"] == "缺"]
    print(f"已扫描 {n} 套 → {SRC_JSON}")
    print(f"  逐年 {sum(1 for v in out.values() if v['源']=='逐年')} | "
          f"仅宝典 {sum(1 for v in out.values() if v['源']=='宝典')} | 缺 {len(miss)}")
    for k in miss:
        print(f"    [缺源] {k}")
    return out


# ============================================================ 文件系统推导进度
STAGES = ("映射", "渲染", "HTML", "PDF")


def detect(key: str) -> dict:
    """从产物是否存在推导这套卷走到哪一步（幂等、不会失同步）。"""
    svg = V6 / f"{key}_导图_总览_LR.svg"
    return {
        "映射": (V6 / f"{key}.json").exists(),
        "渲染": svg.exists(),
        "HTML": (INTER / f"{key}.html").exists(),
        "PDF": PP.exists(key),
    }


def load_sources() -> dict:
    if not SRC_JSON.exists():
        print("没有 sources.json，先跑 scan")
        sys.exit(1)
    return json.loads(SRC_JSON.read_text(encoding="utf-8"))


def load_notes() -> dict:
    if NOTES.exists():
        return json.loads(NOTES.read_text(encoding="utf-8"))
    return {}


def load_alias() -> dict:
    """「别名 -> 正卷」映射。

    用户已拍板选 A：同一份试题被登记在两个科目代码下时，只出一套。
    别名 key 不生产、不计入交付量（详见 _工作台/重卷映射.json）。
    """
    f = HERE / "_工作台" / "重卷映射.json"
    if not f.is_file():
        return {}
    return json.loads(f.read_text(encoding="utf-8")).get("别名到正卷", {})


def summarize(src: dict) -> dict:
    alias = load_alias()
    out = {}
    for k, v in src.items():
        if k in alias:
            continue
        st = detect(k)
        done = all(st[s] for s in STAGES)
        out[k] = {**v, **st, "完成": done}
    return out


def stage_of(rec: dict) -> str:
    for s in STAGES:
        if not rec[s]:
            return s
    return "完成"


# ============================================================ 命令
def cmd_status() -> None:
    src = load_sources()
    rec = summarize(src)
    tot = len(rec)
    print(f"=== 总进度（{YEAR_LO}–{YEAR_HI}，985+211+强势双非）===")
    print(f"  交付目标 : {tot} 套 / {len({v['院校'] for v in rec.values()})} 所院校")
    for s in STAGES:
        n = sum(1 for v in rec.values() if v[s])
        print(f"  {s:<6}  : {n:>4} / {tot}  ({n/tot*100:5.1f}%)")
    print(f"  全流程完成: {sum(1 for v in rec.values() if v['完成']):>4} / {tot}")
    print()
    by_school = defaultdict(lambda: {"n": 0, "done": 0, "tier": ""})
    for k, v in rec.items():
        d = by_school[v["院校"]]
        d["n"] += 1
        d["done"] += 1 if v["完成"] else 0
        d["tier"] = v["层级"]
    full = [s for s, d in by_school.items() if d["done"] == d["n"]]
    part = [s for s, d in by_school.items() if 0 < d["done"] < d["n"]]
    zero = [s for s, d in by_school.items() if d["done"] == 0]
    print(f"院校批次：完成 {len(full)} 所 | 进行中 {len(part)} 所 | 未开始 {len(zero)} 所")
    if part:
        print("  进行中：" + "，".join(f"{s}({by_school[s]['done']}/{by_school[s]['n']})" for s in sorted(part)))
    # 按年
    by_year = defaultdict(lambda: [0, 0])
    for k, v in rec.items():
        by_year[v["年份"]][0] += 1
        by_year[v["年份"]][1] += 1 if v["完成"] else 0
    print("\n  按年份：")
    for y in sorted(by_year, reverse=True):
        a, b = by_year[y]
        bar = "█" * int(b / a * 20) + "·" * (20 - int(b / a * 20))
        print(f"    {y}  {b:>3}/{a:>3}  {bar}")


def cmd_next(n_school: int = 1) -> None:
    src = load_sources()
    rec = summarize(src)
    by_school = defaultdict(list)
    for k, v in rec.items():
        by_school[v["院校"]].append((k, v))
    # 未完成的院校，按「已完成比例降序、层级优先、套数降序」排序：先把开了头的做完
    todo = []
    for s, items in by_school.items():
        undone = [(k, v) for k, v in items if not v["完成"]]
        if not undone:
            continue
        done = len(items) - len(undone)
        pri = {"985": 0, "211": 1, "强势双非": 2, "其他": 3}[items[0][1]["层级"]]
        todo.append((0 if done else 1, pri, -len(items), s, items, undone))
    todo.sort()
    print(f"=== 下一批（共 {len(todo)} 所院校未完成）===")
    for i, (_, pri, _, s, items, undone) in enumerate(todo[:n_school]):
        tier_s = items[0][1]["层级"]
        print(f"\n【第 {i+1} 批】{s}　{tier_s}　{len(undone)} 套待做"
              f"（共 {len(items)} 套）")
        for k, v in sorted(undone, key=lambda x: x[0]):
            src_desc = v["源"]
            f1 = v["真题文件"] or "—"
            print(f"   · {k}  [{v['代码'] or '?'}]  源={src_desc}")
            print(f"       真题: {f1}")
            if v["宝典文件"]:
                print(f"       宝典: {v['宝典文件']}  真题p{v['宝典真题页']} 答案p{v['宝典答案页']}")



BAO_HEAD = [
    r"^#+\s*{school}\s*{year}\s*年[^\n#]*?(?:真题|试题)(?!答案)",
    r"^#+\s*[^\n#]*?{year}\s*年\s*[^\n#]*?{school}[^\n#]*?(?:真题|试题)(?!答案)",
    r"^#*\s*{school}\s*{year}\s*年[^\n#]*?(?:真题|试题)(?!答案)",
    r"^#*\s*[^\n#]*?{year}\s*年\s*[^\n#]*?{school}[^\n#]*?(?:真题|试题)(?!答案)",
    # ★ 标题被换行切断：实测「华北电力大学（保定）2024 年研究生入学考试初试真」
    #   换行后接「# 题」，上面四条都匹配不到（它们都用 [^\n#]*? 隔开，过不了换行）。
    #   这里让「真/试」与「题」之间可以夹换行与井号。
    r"^#*\s*{school}\s*{year}\s*年[^\n]*?(?:试|真)[\s#]*题(?!答案)",
]
BAO_ANY = [
    # 同一问题的「任意年」版本
    r"^#*\s*(?:第[一二三四五六七八九十百零\d]+章\s*)?20\d\d\s*年[^\n]*?(?:试|真)[\s#]*题(?!答案)",
    r"^#+\s*(?:第[一二三四五六七八九十百零\d]+章\s*)?20\d\d\s*年[^\n#]*?(?:真题|试题)(?!答案)",
    r"^#*\s*(?:第[一二三四五六七八九十百零\d]+章\s*)?20\d\d\s*年[^\n#]*?(?:真题|试题)(?!答案)",
]


BAO_END = [
    r"^#+\s*[^\n#]*?20\d\d\s*年[^\n#]*$",
    # 有的宝典里「答案章」标题不是 Markdown 标题（没有 #），若不认它，
    # 目标年份是最后一年时真题段会一路吃到后面的答案章里
    # （实测湖南大学 823：2025 题面段后紧跟「湖南大学 2010 年…真题答案」，
    #  原规则没停，把 2010 答案段一并吞进来）。
    r"^\s*#*\s*[^\n]{0,40}?(?:参考答案|试题答案|真题答案|答案)\s*[:：]?\s*$",
]


def find_bao_end(t: str):
    """定位下一段（任意年份的章节标题）起点；用于截断当前真题段。

    与 find_bao_head 的区别：这里**允许**匹配「参考答案」这类标题，
    否则合订本里「试题章 + 答案章」的顺序会让真题段一直吃到文件末尾。
    """
    for pat in BAO_END:
        m = re.search(pat, t, re.M)
        if m:
            return m.start()
    return None


def find_bao_head(t: str, school, year):
    """在合订本里定位某一年的真题段标题，返回起始下标；school/year 传 None 表示任意年。

    两种标题格式都要认：
      「中国矿业大学 2023 年硕士生招生入学考试試题」
      「第十三章 2025 年电子科技大学 862 研究生入学考试试题」
    """
    if school is None:
        sp = None
        pats = BAO_ANY
    else:
        sp = "".join(
            "[（(]" if ch in "(（" else "[）)]" if ch in ")）" else re.escape(ch)
            for ch in str(school)
        )
        pats = [p.format(school=sp, year=year)
                                            for p in BAO_HEAD] + BAO_ANY
    for pat in pats:
        m = re.search(pat, t, re.M)
        if m:
            return m.start()
    return None


def cmd_brief(key: str, maxlen: int = 3000) -> None:
    """输出某一套的源文正文（剥离 base64），供写作时阅读。"""
    src = load_sources()
    if key not in src:
        print(f"没有这套卷：{key}")
        return
    v = src[key]
    f = v.get("真题文件") or v.get("宝典文件")
    if not f:
        print(f"{key} 没有可用源文件")
        return
    p = HERE / f
    t = p.read_text(encoding="utf-8", errors="replace")
    t = re.sub(r"!\[\]\(data:image/[^)]*\)", "[图]", t)
    t = re.sub(r'<div class="fig">.*?</div>', "[图]", t)
    t = re.sub(r"^\s*\d{1,3}\s*$", "", t, flags=re.M)
    # 广告只删「片段」，绝不整行删（镜像 qc.strip_md；OCR 常把广告与题面/分值挤一行，
    # 整行删会把题面/分值一起丢掉，见交接 §56/§57/§59 与中国矿业大学(徐州)_868_2023）。
    _ad = (r"控制考研初试交流群|公众号[:：]|打开\s*[Bb]\s*站|扫码查看真题解析"
           r"|做题中有任何疑问|微信[:：]|扫描下方二维码")
    t = re.sub(r"[【\[（(][^】\]）)\n]*?(?:" + _ad + r")[^】\]）)\n]*?[】\]）)]", "", t)
    t = re.sub(r"(?:" + _ad + r")[^\n]*?(?:】|$)", "", t, flags=re.M)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if v["源"] == "宝典" and v.get("宝典真题页"):
        # 从合订本里切出该年份的真题段（两种标题格式都要认）
        y = v["年份"]
        head = find_bao_head(t, v["院校"], y)
        if head is not None:
            nl = t.find(chr(10), head)
            body = nl + 1 if nl >= 0 else len(t)
            nxt = find_bao_end(t[body:])
            end = body + nxt if nxt is not None else len(t)
            t = t[head:end]
    print(f"===== {key}  源={v['源']}  {f} =====")
    print(t[:maxlen])
    if len(t) > maxlen:
        print(f"\n…（共 {len(t)} 字符，已截断）")


def cmd_xlsx() -> None:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    src = load_sources()
    rec = summarize(src)
    notes = load_notes()
    wb = openpyxl.Workbook()

    ws = wb.active; ws.title = "总览"
    ws.append(["指标", "值"])
    tot = len(rec)
    for s in STAGES:
        ws.append([s, sum(1 for v in rec.values() if v[s])])
    ws.append(["全流程完成", sum(1 for v in rec.values() if v["完成"])])
    ws.append(["交付目标", tot])
    ws.append(["更新时间", datetime.now().strftime("%F %T")])

    ws2 = wb.create_sheet("院校进度")
    ws2.append(["层级", "院校", "套数", "映射", "渲染", "HTML", "PDF", "完成", "状态"])
    by = defaultdict(list)
    for k, v in rec.items():
        by[v["院校"]].append(v)
    for s, items in sorted(by.items(), key=lambda x: ({"985": 0, "211": 1, "强势双非": 2}[x[1][0]["层级"]], -len(x[1]))):
        row = [items[0]["层级"], s, len(items)] + [sum(1 for v in items if v[st]) for st in STAGES]
        done = sum(1 for v in items if v["完成"])
        row += [done, "完成" if done == len(items) else ("进行中" if done else "未开始")]
        ws2.append(row)

    ws3 = wb.create_sheet("逐套明细")
    ws3.append(["院校", "年份", "层级", "代码", "源", "映射", "渲染", "HTML", "PDF",
                "阶段", "真题文件", "宝典文件", "宝典答页", "备注"])
    for k, v in sorted(rec.items(), key=lambda x: (x[1]["院校"], x[1]["年份"])):
        ws3.append([v["院校"], v["年份"], v["层级"], v["代码"], v["源"],
                    "✓" if v["映射"] else "", "✓" if v["渲染"] else "",
                    "✓" if v["HTML"] else "", "✓" if v["PDF"] else "",
                    stage_of(v), v["真题文件"], v["宝典文件"], v["宝典答案页"],
                    notes.get(k, "")])
    for ws_ in (ws, ws2, ws3):
        for c in ws_[1]:
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="EEF3F8")
        for i, col in enumerate(ws_.iter_cols(), 1):
            w = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws_.column_dimensions[get_column_letter(i)].width = min(max(w + 2, 8), 60)
        ws_.freeze_panes = "A2"
    wb.save(XLSX)
    print(f"已导出 {XLSX.name}")


def cmd_note(key: str, text: str) -> None:
    notes = load_notes()
    old = notes.get(key, "")
    notes[key] = (old + " | " + text).strip(" |") if old else text
    NOTES.parent.mkdir(exist_ok=True)
    NOTES.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已记录 {key}: {text}")



def cmd_render(keys: list[str]) -> None:
    """对一个或多个 key 依次渲染 SVG / HTML / PDF。"""
    import subprocess as sp
    src = load_sources()
    if keys:
        unknown = [k for k in keys if k not in src]
        if unknown:
            # ★ 绝不能在这里回退成「渲染全部」：早先写成 `... or list(src)`，
            #   一旦传进来的 key 拼错/不存在，就会静默全量重渲染 900 多套（约 5 小时）。
            print(f"这些 key 不在 sources.json 里，已中止：{unknown}")
            print("（若是别名 key，请查 _工作台/重卷映射.json 找正卷；确需全量请用 `render --all`）")
            return
        keys = list(keys)
    else:
        keys = list(src)
    print(f"渲染 {len(keys)} 套…")
    blocked = []
    for k in keys:
        # ★ 渲染前先清掉该 key 的旧导图文件。
        # 为什么必须清：mindmap 的板块 SVG 文件名里带**板块名称**，一旦改了板块名，
        # 旧名的 SVG 会留在目录里，而 build_pdf.py 是按 `{key}_导图_*.svg` 通配拼 PDF 的
        # → 旧图会被一起拼进去，交付的 PDF 出现重复页/串页（实测上海大学_836_2025 曾发生）。
        for old_svg in list((HERE / "思维导图_v6").glob(f"{k}_导图_*")):
            try:
                old_svg.unlink()
            except OSError:
                pass
        # ★ 质检；不过关就拦下来，避免产出错图
        r0 = sp.run(["py", "-3.12", "qc.py", k], cwd=str(HERE),
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r0.returncode:
            blocked.append(k)
            print(f"--- {k} ---  ⛔ 质检未通过，跳过渲染")
            for ln in (r0.stdout or "").strip().splitlines():
                if ln.strip().startswith("["):
                    print("     " + ln.strip())
            continue
        print(f"--- {k} ---")
        for cmd, out in (
            (["py", "-3.12", "mindmap_v6.py", "--json", f"思维导图_v6/{k}.json",
              "--dir", "LR", "--split"], "SVG"),
            (["py", "-3.12", "build_interactive.py", k], "HTML"),
            (["py", "-3.12", "build_pdf.py", k, "--brand"], "PDF"),
        ):
            r = sp.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
            tail = [ln for ln in (r.stdout or "").strip().splitlines() if ln.strip()][-1:]
            print(f"  [{out}] {tail[0] if tail else '(无输出)'}")
            if r.returncode:
                print(f"     ! 失败: {(r.stderr or '')[:200]}")
    if blocked:
        print('质检未通过被拦下 %d 套：%s' % (len(blocked), '、'.join(blocked)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "status", "next", "brief", "xlsx", "note", "render"])
    ap.add_argument("a", nargs="?")
    ap.add_argument("b", nargs="?")
    ap.add_argument("rest", nargs="*")
    args = ap.parse_args()
    WB.mkdir(exist_ok=True)
    if args.cmd == "scan":
        scan()
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "next":
        cmd_next(int(args.a) if args.a else 1)
    elif args.cmd == "brief":
        # ★ 修 bug：以前写 `cmd_brief(args.a or "")`，第二参数 maxlen 恒为默认 3000，
        #   于是 agent 传的 `brief <key> 14000` 被**静默忽略**，只能读到 3000 字源文。
        #   （北航 873 那个 agent 发现并上报了这一点。）
        cmd_brief(args.a or "", int(args.b) if (args.b or "").strip().isdigit() else 3000)
    elif args.cmd == "xlsx":
        cmd_xlsx()
    elif args.cmd == "note":
        cmd_note(args.a or "", args.b or "")
    elif args.cmd == "render":
        keys = [x for x in ([args.a, args.b] + list(args.rest)) if x]
        cmd_render(keys)
    return 0


if __name__ == "__main__":
    sys.exit(main())
