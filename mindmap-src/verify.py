#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量验收：把每轮重复的检查固化成一条命令，保证口径一致。

用法：
  py -3.12 verify.py 南开大学_809_2021 上海交通大学_816_2021 ...   # 指定套
  py -3.12 verify.py --range 2021-2024                            # 该年份段已产出的全部
  py -3.12 verify.py --pending 2021-2024                          # 该年份段待做的 key 清单（不验收）

检查项（均来自交接.md 的验收清单）：
  1 qc.py 独立复跑 → 硬错误
  2 四件产物齐（JSON / 总览+板块 SVG / HTML / PDF）
  3 每个产物 mtime > JSON 的 mtime（★ 逐产物比较，不用链式全序）
  4 SVG 张数 == 板块数 + 1
  5 本卷实例三项齐全（关键一步/中间结果/卡点）
  6 本卷实例每条 ≤ 45 字
  7 ref 全在考点库；未知键（渲染器不认的键）为 0
  8 markdown 残留（** / 反引号 / # 标题）
  9 分值：填了 `分值` 的板块列出（供人工核源文，脚本判不了）
退出码：有硬失败则 1。
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
V6 = HERE / "思维导图_v6"
import pdf_paths as PP          # PDF 按院校分文件夹（pdf_of 兼容旧的平铺布局）
OK_TOP = {"院校", "年份", "科目代码", "科目", "来源", "总览", "板块", "备注"}
OK_BLK = {"名称", "题号", "思路", "考点", "分值", "备注"}
OK_KP = {"ref", "本卷考法", "本卷易错", "本卷实例", "分值", "名称", "题号", "备注", "页码"}
OK_INST = {"关键一步", "中间结果", "卡点", "题号参考", "公式"}


def load_lib() -> set[str]:
    ids = set()
    for p in (HERE / "考点库").glob("*.json"):
        if p.name.startswith("_"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for da in d.get("大类", []):
            ids.add(da["id"])
            for xi in da.get("细分", []):
                ids.add(xi["id"])
    return ids


def check(key: str, lib: set[str]) -> tuple[list[str], str]:
    """返回 (问题列表, 摘要行)"""
    bad: list[str] = []
    jp = V6 / f"{key}.json"
    if not jp.exists():
        return ["无 JSON"], f"{key}|未产出"
    try:
        d = json.loads(jp.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"JSON 解析失败: {e}"], f"{key}|坏 JSON"
    tj = jp.stat().st_mtime

    # 2/3/4 产物
    svg = sorted(V6.glob(f"{key}_导图_*.svg"))
    ht = HERE / "思维导图_交互" / f"{key}.html"
    pf = PP.pdf_of(key)
    for label, p in (("HTML", ht), ("PDF", pf)):
        if not p.exists():
            bad.append(f"缺 {label}")
        elif p.stat().st_mtime <= tj:
            bad.append(f"{label} 早于 JSON（内容已改没重渲）")
    if not svg:
        bad.append("缺 SVG")
    nb = len(d.get("板块", []))
    if svg and len(svg) != nb + 1:
        bad.append(f"SVG 张数 {len(svg)} ≠ 板块数+1（{nb+1}）")
    if svg and any(s.stat().st_mtime <= tj for s in svg):
        bad.append("有 SVG 早于 JSON")

    # 7 未知键 + ref
    for k in d:
        if k not in OK_TOP:
            bad.append(f"顶层未知键 {k}")
    refs, lack, over, md = [], 0, 0, 0
    for b in d.get("板块", []):
        for k in b:
            if k not in OK_BLK:
                bad.append(f"板块未知键 {k}")
        for c in b.get("考点", []):
            if not isinstance(c, dict):
                bad.append("考点是纯字符串")
                continue
            for k in c:
                if k not in OK_KP:
                    bad.append(f"考点未知键 {k}")
            r = c.get("ref")
            if r:
                refs.append(r)
                if r not in lib:
                    bad.append(f"ref 不在知识库: {r}")
            inst = c.get("本卷实例") or {}
            if isinstance(inst, dict):
                for k in inst:
                    if k not in OK_INST:
                        bad.append(f"实例未知键 {k}")
            for k in ("关键一步", "中间结果", "卡点"):
                v = inst.get(k) or []
                if not v:
                    lack += 1
                for s in v:
                    if len(str(s)) > 45:
                        over += 1
            blob = json.dumps(c, ensure_ascii=False)
            md += len(re.findall(r"\*\*[^*]+\*\*|`[^`]+`|(?<![\d\w])#{1,4}\s+\S", blob))
    if lack:
        bad.append(f"实例缺项 {lack} 处")
    if over:
        bad.append(f"实例超 45 字 {over} 条")
    if md:
        bad.append(f"markdown 残留 {md} 处")

    # 1 qc
    r = subprocess.run(["py", "-3.12", "qc.py", key], cwd=str(HERE),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    hard = "硬错误 0" not in (r.stdout or "")
    if hard:
        bad.append("qc 硬错误≠0（详见 qc.py 输出）")
    # ★ 漏题判读项：qc 的 A①「范围外题号」意味着"源文有该题、映射没有"，
    #   可能是真漏题（广工 810_2022 就是这么暴露的：源文有一~八题，映射只有 2~6），
    #   也可能是刻意不收（如北航 833_2024 的理论力学题）。**不算失败，但必须逐条判读。**
    A1 = [ln.strip() for ln in (r.stdout or "").splitlines()
          if "A①" in ln and ("范围外" in ln or "漏题" in ln)]
    for ln in A1:
        bad.append(f"⚠漏题判读：{ln[:110]}")

    # 9 分值（列出供人工核）
    fen = [(str(b.get("题号")), b.get("分值")) for b in d.get("板块", []) if b.get("分值")]
    fs = ("  分值=" + ",".join(f"{t}:{v}" for t, v in fen)) if fen else "  分值=全空"

    summary = (f"{'✓' if not bad else '✗'} {key}|板块{nb}|ref{len(set(refs))}|"
               f"SVG{len(svg)}|qch{'✗' if hard else '0'}")
    if fen:
        summary += f"|{fs.strip()}"
    return bad, summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--range", help="年份段，如 2021-2024（验收该段已产出的）")
    ap.add_argument("--pending", help="年份段：只列待做 key，不验收")
    a = ap.parse_args()

    if a.pending:
        y0, y1 = (int(x) for x in a.pending.split("-"))
        src = json.loads((HERE / "_工作台" / "sources.json").read_text(encoding="utf-8"))
        al = json.loads((HERE / "_工作台" / "重卷映射.json").read_text(encoding="utf-8"))["别名到正卷"]
        done = {p.stem for p in V6.glob("*.json")}
        pend = [k for k in src if any(k.endswith(f"_{y}") for y in range(y0, y1 + 1))
                and k not in al and k not in done]
        print(f"待做 {len(pend)} 套：")
        for k in sorted(pend):
            print("  ", k)
        return 0

    if a.range:
        y0, y1 = (int(x) for x in a.range.split("-"))
        keys = sorted(p.stem for p in V6.glob("*.json")
                      if any(p.stem.endswith(f"_{y}") for y in range(y0, y1 + 1)))
    else:
        keys = a.keys
    if not keys:
        print("没给 key（或该范围没有已产出的）")
        return 0

    lib = load_lib()
    fails = []
    for k in keys:
        bad, summary = check(k, lib)
        print(summary)
        for b in bad:
            print("     ✗", b)
        if bad:
            fails.append(k)
    print(f"\n{'='*56}\n验收 {len(keys)} 套：通过 {len(keys)-len(fails)}，失败 {len(fails)}")
    if fails:
        print("失败清单：", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
