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


def strip_md(t: str) -> str:
    t = re.sub(r"!\[\]\(data:image/[^)]*\)", "", t)
    t = re.sub(r'<div class="fig">.*?</div>', "", t)
    t = re.sub(r"^.*(控制考研初试交流群|公众号[:：]|打开\s*B\s*站|扫码查看真题解析"
               r"|做题中有任何疑问|微信[:：]|扫描下方二维码).*$", "", t, flags=re.M)
    return t


PATS = [
    r"第\s*([%s\d]+)\s*题[^\n]{0,24}?本题满分\s*(\d+)\s*分" % CN,
    r"第\s*([%s\d]+)\s*题[^\n]{0,12}?[（(]\s*(\d+)\s*分\s*[)）]" % CN,
    r"^\s*([%s]+)\s*[、.．][^\n]{0,24}?[（(]\s*(?:本题满分\s*)?(\d+)\s*分" % CN,
    r"^\s*(\d+)\s*[、.．][^\n]{0,24}?[（(]\s*(?:本题满分\s*)?(\d+)\s*分",
    r"^\s*第?\s*(\d+)\s*题[^\n]{0,10}?[（(]\s*(\d+)\s*分",
    # 题号不一定在行首（例：OCR 把上一题尾巴和「九、(15分)」挤在同一行）
    r"([%s])\s*[、.．]\s*[（(]?\s*(\d+)\s*分" % CN,
]

# 宽松模式：宝典里常见「## 一、简答题（50 分）」这种带 Markdown 前缀，
# 以及「二、…（20）」这种漏印「分」字的写法。因为容易把「（2）」当成 2 分，
# 这里只认 ≥ 5 的数，且优先级低于 PATS（见 paper_questions）。
PATS_LOOSE = [
    r"^#+\s*([%s\d]+)\s*[、.．][^\n]{0,20}?[（(]\s*(\d+)\s*分?\s*[)）]" % CN,
    r"^#+\s*([%s\d]+)\s*[、.．][^\n]{0,20}?[（(]\s*(\d+)\s*[)）]" % CN,
]


def paper_questions(key: str) -> list[tuple[int, int, str]]:
    """从源文正文里抽出 [(题号, 分值, 原文片段)]，只取真题段、每题第一次出现。"""
    v = SRC.get(key)
    if not v:
        return []
    f = v.get("真题文件") or v.get("宝典文件")
    if not f:
        return []
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
    found: dict[int, tuple[int, str]] = {}
    # 简答题：「第X题 (本题共 N 小题, 每小题 M 分, 共 T 分)」→ 取总分 T
    simp = re.compile(r"第\s*([" + CN + r"\d]+)\s*题[^\n]{0,30}?本题共\s*\d+\s*小题"
                      r"[^\n]{0,24}?共\s*(\d+)\s*分")
    for m in simp.finditer(t):
        n = cn2i(m.group(1))
        tot = int(m.group(2))
        if 1 <= n <= 30 and 1 <= tot <= 100:
            found.setdefault(n, (tot, m.group(0)[:50].replace("\n", " ")))
    for pt in PATS:
        for m in re.finditer(pt, t, re.M):
            n = cn2i(m.group(1))
            s = int(m.group(2))
            if 1 <= n <= 30 and 1 <= s <= 100 and n not in found:
                found[n] = (s, m.group(0)[:50].replace("\n", " "))
    for pt in PATS_LOOSE:
        for m in re.finditer(pt, t, re.M):
            n = cn2i(m.group(1))
            s = int(m.group(2))
            if 1 <= n <= 30 and 5 <= s <= 100 and n not in found:
                found[n] = (s, m.group(0)[:50].replace("\n", " "))
    return [(n, s, d) for n, (s, d) in sorted(found.items())]


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
    pq = paper_questions(key)
    if pq:
        src_nums = {n for n, _, _ in pq}
        my_nums: set[int] = set()
        for b in d.get("板块", []):
            for x in re.findall(r"\d+", str(b.get("题号") or "")):
                my_nums.add(int(x))
        # 板块里的题号可能写成「7、8」或范围
        miss = sorted(src_nums - my_nums)
        if miss:
            detail = "；".join(f"第{n}题({s}分)" for n, s, _ in pq if n in miss)
            msgs.append(f"[A①漏题] 源文有 {len(src_nums)} 题，映射只覆盖 {len(my_nums)} 题；"
                        f"缺 {miss} → {detail}")
        # ---- A② 分值核对（★ 源文没标分值的题，映射里必须留空，不许猜）
        src_sum = sum(s for _, s, _ in pq)
        blocks = d.get("板块", [])
        blank = [b.get("题号") for b in blocks if not b.get("分值")]
        my_sum = sum(b.get("分值") or 0 for b in blocks)
        src_known = {n: s for n, s, _ in pq}
        if blank:
            msgs.append(f"[提示·A②分值空缺] {len(blank)} 个板块未填分值：{blank}"
                        f"（源文未标注，保持留空即可）")
        # 只在「题号全覆盖 且 每个板块都能在源文里找到分值 且 全部填了分值」时才严格比合计。
        # 少一个条件就不能比：源文只解析出一部分题的分值时，合计必然对不上，
        # 那种情况报错是误报（实测南开大学 810：源文 6 题只解析出前 3 题分值）。
        covered = bool(blocks) and all(
            any(int(n) in src_known for n in re.findall(r"\d+", str(b.get("题号") or "")))
            for b in blocks)
        if not miss and not blank and covered and abs(my_sum - src_sum) > max(3, src_sum * 0.03):
            msgs.append(f"[A②分值] 源文合计 {src_sum} 分，映射合计 {my_sum} 分，"
                        f"差 {my_sum - src_sum:+d}")
        elif not covered and not miss:
            msgs.append(f"[提示·A②分值未核] 源文只解析出 {len(src_known)} 个题的分值"
                        f"（{sorted(src_known)}），无法核对合计，请人工确认")
        # 逐题比对：源文标了、映射也填了但数值不同 → 明确报错
        # ★ 注意 src_known 的键是 int，这里必须转成 int 才能命中
        #   （早期写成字符串比较，导致这条检查从来没触发过）
        for b in blocks:
            _nums = re.findall(r"\d+", str(b.get("题号") or ""))
            if len(_nums) != 1:
                # 「1、2、3、4、5」这种把多题并进一个板块的，板块分值是那几题的合计，
                # 不能拿它逐题比对，跳过
                continue
            ni = int(_nums[0])
            if ni in src_known and b.get("分值") and int(b["分值"]) != src_known[ni]:
                msgs.append(f"[A②分值不符] 第{ni}题：源文 {src_known[ni]} 分，"
                            f"映射 {b['分值']} 分")
        if verbose:
            print(f"      源文题号-分值: " + "、".join(f"{n}:{s}分" for n, s, _ in pq))

    # ---- A③ 科目代码一致性
    code = str(d.get("科目代码") or "")
    srcf = v.get("真题文件") or ""
    if code and srcf:
        m = re.search(r"(\d{3})控制考研", srcf)
        if m and m.group(1) != code:
            msgs.append(f"[A③代码] json 写 {code}，源文件名是 {m.group(1)}")

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
