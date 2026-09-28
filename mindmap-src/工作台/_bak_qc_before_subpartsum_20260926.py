#!/usr/bin/env python -u
# -*- coding: utf-8 -*-
r"""
内容质检 —— 每一批写完必须跑，防止「漏题 / 分值错 / 公式乱码 / 内容误加 / 答案泄漏」。

用法
  python qc.py                 检查全部已有卷级映射
  python qc.py 燕山大学_2022     只查这一套
  python qc.py --fix-hint       额外给出源文里的题号-分值清单，便于人工核对

检查项
  A 边界  ① 题号覆盖（源文有、映射里没有 → 漏题）
          ② 分值核对（映射分值合计 vs 源文分值合计）
          ③ 科目代码与源文件名一致
  B 公式  ④ KaTeX 渲染（throwOnError=true）
          ⑤ 危险字符：裸 % < >、非 \text 内的中文、未配对花括号、$$ 残留
          ⑥ 公式长度异常（疑似 OCR 残留）
  C 文字  ⑦ 绝对化表述（一定/必然/绝对/肯定）
          ⑧ 答案泄漏（答案是/解得=/最终结果/具体数值）
          ⑨ 超长条目（要点 >40 字、其他 >45 字）
          ⑩ 套内重复节点
  D 结构  ⑪ 空考点 / 只有名称没内容
          ⑫ ref 未命中知识库
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
SRC = json.loads((HERE / "_工作台" / "sources.json").read_text(encoding="utf-8")) \
    if (HERE / "_工作台" / "sources.json").exists() else {}
LIB_DIR = HERE / "考点库"

CN = "一二三四五六七八九十"


def cn2i(s: str) -> int:
    if s.isdigit():
        return int(s)
    m = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
         "九": 9, "十": 10}
    if s in m:
        return m[s]
    if s.startswith("十"):
        return 10 + m.get(s[1:], 0)
    if "十" in s:
        a, b = s.split("十")
        return m.get(a, 1) * 10 + (m.get(b, 0) if b else 0)
    return 0


# 广告关键词。旧写法 `^.*(广告词).*$` 会整行删；OCR 常把广告与题面/分值挤在同一行，
# 于是分值/题面一起被删（交接 §56/§57/§59）。现在只删「广告片段」。
AD_WORDS = (r"控制考研初试交流群|公众号[:：]|打开\s*[Bb]\s*站|扫码查看真题解析"
            r"|做题中有任何疑问|微信[:：]|扫描下方二维码")


def strip_md(t: str) -> str:
    t = re.sub(r"!\[\]\(data:image/[^)]*\)", "", t)
    t = re.sub(r'<div class="fig">.*?</div>', "", t)
    # ① 被【】[]（）包住的广告块：整块删，块外的前缀/后缀（题面、分值）都保留。
    #    覆盖「【广告】第二题(本题满分17分)…」与「六、（14分）【广告】」两种前后缀/夹心。
    #    ★ 起始括号后紧跟「数字+分」的，不作为广告块起始（负向先行断言）：
    #    「（20分【广告…】」里那个「（」是分值括号，不是广告括号，否则会把分值一起吞掉。
    t = re.sub(r"[【\[（(](?!\s*\d+\s*分)[^】\]）)\n]*?(?:" + AD_WORDS + r")[^】\]）)\n]*?[】\]）)]", "", t)
    # ② 没被括号包的裸露广告：从广告词删到行尾（或同行最近的收尾「】」），保留前半句。
    #    `(?:】|$)` 让「广告夹在中间、后面还有真实内容」的情况也能保住尾部内容。
    t = re.sub(r"(?:" + AD_WORDS + r")[^\n]*?(?:】|$)", "", t, flags=re.M)
    return t


def nums_in(s: str) -> set[int]:
    """题号表示法归一：从题号字段里抽出阿拉伯题号集合（中文数字→阿拉伯，支持范围）。

    「一」→{1}、「十一」→{11}、「一、二」→{1,2}、「1~10」→{1..10}。
    旧代码只 findall 数字，于是映射写中文（一~八）时被算成「0 题覆盖」，
    修 strip_md 后源文解析出阿拉伯数字就误报 A①漏题（交接 §57）。
    """
    out: set[int] = set()
    s = str(s or "")
    for a, b in re.findall(r"(\d+)\s*[~～\-—–到至]\s*(\d+)", s):
        a, b = int(a), int(b)
        if 1 <= a and a <= b <= 30:
            out.update(range(a, b + 1))
    for tok in re.findall(r"[%s]+|\d+" % CN, s):
        v = cn2i(tok)
        if 1 <= v <= 30:
            out.add(v)
    return out


def num_tokens(s: str) -> list[str]:
    """题号字段里的题号 token（中文数字/阿拉伯数字各算一个）。

    '四4' → ['四', '4']（大题四的第 4 小问，是两个 token，不能当成单题「4」），
    '1' → ['1']，'一、二' → ['一', '二']。逐题比分值前要按 token 数判断是不是单题。
    """
    return re.findall(r"[%s]+|\d+" % CN, str(s or ""))


PATS = [
    r"第\s*([%s\d]+)\s*题[^\n]*?本题满分\s*(\d+)\s*分" % CN,
    r"第\s*([%s\d]+)\s*题[^\n]*?[（(]\s*(\d+)\s*分\s*[)）]" % CN,
    # 中文大题号：允许行首 Markdown 井号（「## 一、（15分）」），也允许「共」字前缀
    # （「一、简答题(共48分…)」，交接 §59 样本3）。
    r"(?<![\u4e00-\u9fff])[ 	]*#*[ 	]*([%s]+)\s*[、.．][^\n]*?[（(]\s*(?:本题满分\s*|本题共\s*|共\s*)?(\d+)\s*分" % CN,
    # 分值另起一行的中文大题头（「## 一、……\n\n(15分)」，内蒙古 867_2023 第一题）。
    r"^\s*#*\s*([%s]+)\s*[、.．][^\n]*?(?:\n[ \t]*)+[（(]\s*(?:本题满分\s*|本题共\s*|共\s*)?(\d+)\s*分" % CN,
    # 阿拉伯大题号：同样允许行首 Markdown 井号与「共」字前缀。
    r"^\s*#*\s*(\d+)\s*[、.．][^\n]*?[（(]\s*(?:本题满分\s*|本题共\s*|共\s*)?(\d+)\s*分",
    r"^\s*第?\s*(\d+)\s*题[^\n]*?[（(]\s*(\d+)\s*分",
    # 题号不一定在行首（例：OCR 把上一题尾巴和「九、(15分)」挤在同一行）
    r"([%s])\s*[、.．]\s*[（(]?\s*(?:共\s*)?(\d+)\s*分" % CN,
]

# 宽松模式：宝典里常见「## 一、简答题（50 分）」这种带 Markdown 前缀，
# 以及「二、…（20）」这种漏印「分」字的写法。因为容易把「（2）」当成 2 分，
# 这里只认 ≥ 5 的数，且优先级低于 PATS（见 paper_questions）。
PATS_LOOSE = [
    r"^#+\s*([%s\d]+)\s*[、.．][^\n]{0,20}?[（(]\s*(\d+)\s*分?\s*[)）]" % CN,
    r"^#+\s*([%s\d]+)\s*[、.．][^\n]{0,20}?[（(]\s*(\d+)\s*[)）]" % CN,
]


def paper_questions(key: str) -> dict[int, list[tuple[int, str]]]:
    """从源文正文里抽出 {题号: [(分值, 原文片段), ...]}，只取真题段。

    同一题号可能解析到多个分值：OCR 常把小问分和大题分挤在一起（交接 §59），
    或在答案段重复出现。这里按「大题优先」收集：
      * 一个题号只保留命中的**最高优先级**那一类写法（大题头 > 小问编号）；
      * 同一类写法若给出多个不同分值，才留下多个候选，由调用方降级为软提示。
    这样既排除了小问编号的干扰，又保留了「源文真有多个分值」的信号。
    """
    v = SRC.get(key)
    if not v:
        return {}
    f = v.get("真题文件") or v.get("宝典文件")
    if not f:
        return {}
    t = strip_md(Path(HERE / f).read_text(encoding="utf-8", errors="replace"))
    # 宝典：只保留该年份的真题段（答案段有大量重复）
    if v.get("源") == "宝典" and v.get("宝典真题页"):
        from workbench import find_bao_end, find_bao_head
        head = find_bao_head(t, v["院校"], v["年份"])
        if head is not None:
            nl = t.find(chr(10), head)
            body = nl + 1 if nl >= 0 else len(t)
            nxt = find_bao_end(t[body:])
            end = body + nxt if nxt is not None else len(t)
            t = t[head:end]

    # 正则按优先级从高到低排列。低优先级（小问编号/宽松写法）只在题号尚未被
    # 高优先级认领时使用。（阈值：宽松模式只认 ≥5，避免把「（2）」当 2 分。）
    simp = re.compile(r"第\s*([" + CN + r"\d]+)\s*题[^\n]{0,30}?本题共\s*\d+\s*小题"
                      r"[^\n]{0,24}?共\s*(\d+)\s*分")
    pats: list[tuple[re.Pattern, int]] = [(simp, 1)]
    pats += [(re.compile(pt, re.M), 1) for pt in PATS]
    pats += [(re.compile(pt, re.M), 5) for pt in PATS_LOOSE]

    found: dict[int, tuple[int, dict[int, str]]] = {}  # 题号 -> (优先级, {分值: 片段})
    for prio, (rx, lo) in enumerate(pats):
        for m in rx.finditer(t):
            n = cn2i(m.group(1))
            s = int(m.group(2))
            if not (1 <= n <= 30 and lo <= s <= 100):
                continue
            desc = m.group(0)[:50].replace("\n", " ")
            cur = found.get(n)
            if cur is None:
                found[n] = (prio, {s: desc})
            elif cur[0] == prio:
                cur[1].setdefault(s, desc)   # 同类写法多解 → 保留全部候选
            # 低优先级匹配：已有更高优先级的判读，忽略
    return {n: sorted(cand.items()) for n, (prio, cand) in sorted(found.items())}


# ---------------------------------------------------------------- 知识库
def load_lib() -> dict:
    lib = {}
    for f in sorted(LIB_DIR.glob("*.json")):
        if f.name.startswith("_"):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        for b in d.get("大类", []):
            for kp in b.get("细分", []):
                lib[kp["id"]] = kp
    return lib


TEX_BAD = [
    (re.compile(r"(?<!\\)%"), "裸 % （应为 \\% ）"),
    (re.compile(r"(?<!\\)<"), "裸 < （应为 \\lt ）"),
    (re.compile(r"(?<!\\)>"), "裸 > （应为 \\gt ）"),
    (re.compile(r"\$\$|\$"), "$ 残留（公式里不该有 $）"),
    (re.compile(r"[\uff08\uff09\uff0c\uff1b\uff1a\uff1f]"), "全角标点（KaTeX 不认）"),
]
CJK = re.compile(r"[\u4e00-\u9fff]")
TEXT_WRAP = re.compile(r"\\(?:text|mbox|mathrm|operatorname)\{[^}]*\}")
ABS = re.compile(r"一定|必然|绝对(?!值)|肯定|必定|毫无疑问")
ANSWER = re.compile(r"答案是|答案为|解得\s*[A-Za-z_]?\s*=|所以\s*[A-Za-z_]+\s*=\s*[\d\-]"
                    r"|最终结果|因此\s*[A-Za-z_]+\s*=\s*[\d\-]|正确答案")


def check_one(key: str, lib: dict, verbose: bool) -> list[str]:
    msgs: list[str] = []
    jf = HERE / "思维导图_v6" / f"{key}.json"
    if not jf.exists():
        return [f"[缺] {key} 没有卷级映射"]
    d = json.loads(jf.read_text(encoding="utf-8"))
    v = SRC.get(key, {})

    # ---- A① 题号覆盖
    pq = paper_questions(key)              # {题号: [(分值, 片段), ...]}
    if pq:
        src_nums = set(pq)
        # ★ 比对前把题号归一（映射常写中文「一~八」，源文解析出阿拉伯「4~8」；
        #   不归一就会把「已覆盖」误判成「漏题」，见交接 §57）。
        my_nums: set[int] = set()
        for b in d.get("板块", []):
            my_nums |= nums_in(b.get("题号"))
        miss = sorted(src_nums - my_nums)
        if miss:
            # 映射题号范围：范围内的缺失 = 真漏题（硬错误）；范围外的题号多半是
            # 刻意不收的追加题/跨科题（如北航833_2024 收 1~10、正文到十四；广工
            # 810_2022 收 2~6、正文到八），只提示、不拦渲染。
            lo, hi = (min(my_nums), max(my_nums)) if my_nums else (1, 30)
            miss_in = [n for n in miss if lo <= n <= hi]
            miss_out = [n for n in miss if not (lo <= n <= hi)]
            fmt = lambda n: f"第{n}题({'/'.join(str(s) for s, _ in pq[n])}分)"
            if miss_in:
                msgs.append(f"[A①漏题] 源文有 {len(src_nums)} 题，映射只覆盖 {len(my_nums)} 题；"
                            f"缺 {miss_in} → " + "；".join(fmt(n) for n in miss_in))
            if miss_out:
                msgs.append(f"[提示·A①范围外] 源文另有题号 {miss_out} 超出映射题号范围 "
                            f"{lo}~{hi}（可能是刻意不收的追加题/范围外题），请人工确认："
                            + "；".join(fmt(n) for n in miss_out))
        # ---- A② 分值核对（★ 源文没标分值的题，映射里必须留空，不许猜）
        blocks = d.get("板块", [])
        blank = [b.get("题号") for b in blocks if not b.get("分值")]
        my_sum = sum(b.get("分值") or 0 for b in blocks)
        src_known: dict[int, set[int]] = {n: {s for s, _ in lst} for n, lst in pq.items()}
        if blank:
            msgs.append(f"[提示·A②分值空缺] {len(blank)} 个板块未填分值：{blank}"
                        f"（源文未标注，保持留空即可）")
        # 只在「题号全覆盖 且 每个板块都能在源文里找到分值 且 全部填了分值」时才严格比合计。
        # 少一个条件就不能比：源文只解析出一部分题的分值时，合计必然对不上，
        # 那种情况报错是误报（实测南开大学 810：源文 6 题只解析出前 3 题分值）。
        covered = bool(blocks) and all(
            bool(nums_in(b.get("题号")) & set(src_known)) for b in blocks)
        # ★ 集合有多个值 = 源文该题号解析到多个分值（多半是小问分混入），
        #   一律降为软提示，绝不硬报（交接 §59 修法 a；否则 agent 会被迫留空已知分值）。
        all_unique = all(len(s) == 1 for s in src_known.values())
        if not miss and not blank and covered and all_unique:
            src_sum = sum(next(iter(s)) for s in src_known.values())
            if abs(my_sum - src_sum) > max(3, src_sum * 0.03):
                msgs.append(f"[A②分值] 源文合计 {src_sum} 分，映射合计 {my_sum} 分，"
                            f"差 {my_sum - src_sum:+d}")
        elif not covered and not miss:
            msgs.append(f"[提示·A②分值未核] 源文只解析出 {len(src_known)} 个题的分值"
                        f"（{sorted(src_known)}），无法核对合计，请人工确认")
        elif not miss and not blank and covered and not all_unique:
            _multi = "；".join(f"第{n}题{sorted(src_known[n])}"
                               for n in sorted(src_known) if len(src_known[n]) > 1)
            msgs.append(f"[提示·A②分值多解] 源文这些题号解析到多个分值，无法核对合计：{_multi}")
        # 逐题比对：源文标了、映射也填了但数值不同 → 明确报错（唯一值才硬报）
        for b in blocks:
            _toks = num_tokens(b.get("题号"))
            if len(_toks) != 1:
                # 「1、2、3、4、5」并块、或「四4」（大题号+小问号）这类，
                # 板块分值不是单题分值，不能逐题比对，跳过
                continue
            ni = cn2i(_toks[0])
            if ni in src_known and b.get("分值"):
                vals = src_known[ni]
                mv = int(b["分值"])
                if len(vals) == 1 and mv != next(iter(vals)):
                    msgs.append(f"[A②分值不符] 第{ni}题：源文 {next(iter(vals))} 分，"
                                f"映射 {mv} 分")
                elif len(vals) > 1:
                    msgs.append(f"[提示·A②分值多解] 第{ni}题：源文解析到多个分值"
                                f"{sorted(vals)}，映射 {mv} 分，请人工核实")
        if verbose:
            print("      源文题号-分值: " + "、".join(
                f"{n}:{'/'.join(str(s) for s, _ in lst)}分" for n, lst in pq.items()))

    # ---- A③ 科目代码一致性
    code = str(d.get("科目代码") or "")
    srcf = v.get("真题文件") or ""
    if code and srcf:
        m = re.search(r"(\d{3})控制考研", srcf)
        if m and m.group(1) != code:
            printed = ""
            if v.get("源") == "逐年":
                try:
                    _txt = Path(HERE / srcf).read_text(encoding="utf-8",
                                                       errors="replace")[:5000]
                    _pm = re.search(r"科目代码[^0-9]{0,12}?([0-9]{3})", _txt)
                    printed = _pm.group(1) if _pm else ""
                except OSError:
                    printed = ""
            if printed:
                if printed != code:
                    msgs.append(f"[A③代码] json 写 {code}，卷面正文印 {printed}，以正文为准")
            else:
                msgs.append(f"[A③代码] json 写 {code}，源文件名为 {m.group(1)}")

    # ---- A④ 未知键（渲染器只认固定键名，拼错的键会被**静默丢掉**）
    # 来由：南京大学_865_2025 第 9 题把「关键一步」误写成「关键步骤」，
    # 渲染器不认这个键，那条内容直接消失，而 qc 当时扫不到 —— 等于漏了内容却无人报。
    _ok_top = {"院校", "年份", "科目代码", "科目", "来源", "总览", "板块", "备注"}
    _ok_blk = {"名称", "题号", "思路", "考点", "分值", "备注"}
    _ok_kp = {"ref", "本卷考法", "本卷易错", "本卷实例", "分值", "名称", "题号", "备注", "页码"}
    _ok_inst = {"关键一步", "中间结果", "卡点", "题号参考", "公式"}
    for _k in d:
        if _k not in _ok_top:
            msgs.append(f"[A④未知键] 顶层多出「{_k}」：渲染器不认，内容会被丢掉")
    for _bi, _b in enumerate(d.get("板块", [])):
        if not isinstance(_b, dict):
            continue
        for _k in _b:
            if _k in _ok_blk:
                continue
            if _k == "页码":
                # 渲染器只在**考点级**读 页码，挂在板块级不会显示（也不报错），属无效标注
                msgs.append(f"[提示·无效键] 第{_bi+1}板块的「页码」挂在板块级，"
                            f"渲染器只在考点级读它，这条标注不会显示")
            else:
                msgs.append(f"[A④未知键] 第{_bi+1}板块多出「{_k}」：渲染器不认，内容会被丢掉")
        for _kp in _b.get("考点", []):
            if not isinstance(_kp, dict):
                continue
            for _k in _kp:
                if _k not in _ok_kp:
                    msgs.append(f"[A④未知键] 第{_bi+1}板块 ref={_kp.get('ref')} 多出"
                                f"「{_k}」：渲染器不认，内容会被丢掉")
            _inst = _kp.get("本卷实例")
            if isinstance(_inst, dict):
                for _k in _inst:
                    if _k not in _ok_inst:
                        msgs.append(f"[A④未知键] 第{_bi+1}板块 ref={_kp.get('ref')} 的"
                                    f"「本卷实例」里「{_k}」不是 关键一步/中间结果/卡点 之一，"
                                    f"内容会被静默丢掉")

    # ---- 逐考点
    bad_tex: list[tuple[str, str, str]] = []
    seen_text: dict[str, str] = {}
    for bi, b in enumerate(d.get("板块", [])):
        bn = b.get("名称", f"板块{bi+1}")
        if not b.get("考点"):
            msgs.append(f"[D⑪空] 板块「{bn}」没有考点")
        for kp in b.get("考点", []):
            if isinstance(kp, str):
                msgs.append(f"[D⑪空] 板块「{bn}」的考点是纯字符串：{kp}")
                continue
            ref = kp.get("ref")
            name = kp.get("名称") or (lib.get(ref, {}) or {}).get("名称") or "?"
            if ref and ref not in lib:
                msgs.append(f"[D⑫] ref「{ref}」不在知识库")
            # 公式
            inst = kp.get("本卷实例") or {}
            texs = list(kp.get("公式") or []) + list(inst.get("公式") or [])
            for tex in texs:
                for rx, why in TEX_BAD:
                    if rx.search(tex):
                        bad_tex.append((name, why, tex[:70]))
                tmp = TEXT_WRAP.sub("", tex)
                if CJK.search(tmp):
                    bad_tex.append((name, "非 \\text 内的中文", tex[:70]))
                if tmp.count("{") != tmp.count("}"):
                    bad_tex.append((name, "花括号不配对", tex[:70]))
                if len(tex) > 180:
                    bad_tex.append((name, f"公式过长({len(tex)}字，疑似OCR残留)", tex[:70]))
            # Markdown 残留：导图不渲染 markdown，星号/井号会原样显示
            _blob = json.dumps(kp, ensure_ascii=False)
            for _pat, _why in ((r"\*\*[^*]+\*\*", "Markdown 粗体 **…**"),
                               (r"(?<![\d\w])#{1,4}\s+\S", "Markdown 标题 #"),
                               (r"`[^`]+`", "Markdown 反引号")):
                if re.search(_pat, _blob):
                    msgs.append(f"[C⑬Markdown残留] 「{name}」含 {_why}，导图会原样显示")

            # 文字
            for kind in ("要点", "步骤", "考法", "易错", "本卷考法", "本卷易错"):
                vals = kp.get(kind) or []
                if isinstance(vals, str):
                    vals = [vals]
                for s in vals:
                    s = str(s)
                    lim = 40 if kind == "要点" else 45
                    if len(s) > lim:
                        msgs.append(f"[C⑨] 「{name}」{kind} {len(s)} 字超限：{s[:32]}…")
                    if ABS.search(s) and kind in ("要点", "考法", "本卷考法"):
                        msgs.append(f"[C⑦绝对化] 「{name}」{kind}：{s[:40]}")
                    if ANSWER.search(s):
                        msgs.append(f"[C⑧答案泄漏] 「{name}」{kind}：{s[:40]}")
            for k in ("关键一步", "中间结果", "卡点"):
                vals = inst.get(k) or []
                if isinstance(vals, str):
                    vals = [vals]
                for s in vals:
                    s = str(s)
                    if ANSWER.search(s):
                        msgs.append(f"[C⑧答案泄漏] 「{name}」实例.{k}：{s[:40]}")
                    if ABS.search(s) and k == "关键一步":
                        msgs.append(f"[C⑦绝对化] 「{name}」实例.{k}：{s[:40]}")
            # 三项齐全度：缺一项导图就少一个分支。不拦渲染，只提示，
            # 便于成批把历史缺口列出来一次补掉（口径：「实例覆盖」= 三项齐全，不是「非空」）。
            _lack = [k for k in ("关键一步", "中间结果", "卡点") if not (inst.get(k) or [])]
            if _lack:
                msgs.append(f"[提示·实例缺项] 「{name}」本卷实例缺：{'/'.join(_lack)}")
            # ★ 长度：`_本卷实例_规范.md` 写明「每条 ≤ 45 字」，但旧 qc 只查
            #   本卷考法/本卷易错 的长度，**从没查过 本卷实例** —— 于是全库有 259 条
            #   （2.9%、涉及 31 套）超限却无人知，最长一条 104 字。
            #   节点文字过长会把导图撑得很宽，故补上；不拦渲染，只提示便于成批清理。
            for _k in ("关键一步", "中间结果", "卡点"):
                for _s in (inst.get(_k) or []):
                    if len(str(_s)) > 45:
                        msgs.append(f"[提示·实例超长] 「{name}」实例.{_k} "
                                    f"{len(str(_s))} 字(>45)：{str(_s)[:30]}…")
            # 整块文本的重复检测
            blob = json.dumps(kp, ensure_ascii=False)
            for s in re.findall(r'"([^"]{12,})"', blob):
                if s in seen_text and seen_text[s] != name:
                    msgs.append(f"[C⑩重复] 「{name}」与「{seen_text[s]}」有相同内容：{s[:30]}")
                seen_text[s] = name

    for name, why, tex in bad_tex[:20]:
        msgs.append(f"[B⑤公式] 「{name}」{why}：{tex}")
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("key", nargs="?")
    ap.add_argument("--fix-hint", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    lib = load_lib()
    keys = [a.key] if a.key else sorted(
        p.stem for p in (HERE / "思维导图_v6").glob("*.json"))
    if a.limit:
        keys = keys[:a.limit]

    total = hard = soft = 0
    for k in keys:
        if not (HERE / "思维导图_v6" / f"{k}.json").exists():
            continue
        total += 1
        if a.fix_hint:
            print(f"\n── {k} ──")
        msgs = check_one(k, lib, a.fix_hint)
        if msgs:
            # 「[提示·…]」是提醒不是错误，不拦渲染
            if [m for m in msgs if not m.startswith("[提示")]:
                hard += 1
            else:
                soft += 1
            if not a.fix_hint:
                print(f"\n── {k} ──")
            for m in msgs:
                print("   " + m)
    print(f"\n{'='*60}\n检查 {total} 套：硬错误 {hard} 套，仅提示 {soft} 套")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
