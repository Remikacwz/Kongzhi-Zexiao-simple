#!/usr/bin/env python -u
# -*- coding: utf-8 -*-
r"""
思维导图渲染器 v6 —— 架构 B：共享考点知识库 + 卷级映射

   考点库/*.json        共享知识库（12 大类 / 细分考点）
   思维导图_v6/*.json   卷级映射（ref 引用知识库，只写本卷特有的东西）
        ↓  expand()
   Graphviz dot  →  PNG / SVG

相比 v5 的改动
  1. 公式批量渲染：一次 Edge 启动渲染整批公式（含 sha1 磁盘缓存），不再逐条启动
  2. 图片目录可配置且强制 ASCII（Graphviz 读不了中文路径）
  3. 断点续跑 + 进度表
  4. 卷级「本卷考法 / 本卷易错」置顶并标 ★

用法
  python mindmap_v6.py --json 思维导图_v6/东北大学_2021.json --dir LR
  python mindmap_v6.py --json "思维导图_v6/*.json" --dir LR
  python mindmap_v6.py --json ... --force          # 忽略缓存重跑
"""
from __future__ import annotations

import argparse
import copy
import glob
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
LIB_DIR = HERE / "考点库"
OUT = HERE / "思维导图_v6"
PROGRESS = OUT / "_progress.tsv"
DOT = Path(r"C:\Program Files\Graphviz\bin\dot.exe")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
KATEX = HERE / "katex" / "node_modules" / "katex"
# 必须 ASCII：Graphviz 无法从非 ASCII 路径读取 image=
IMGDIR = Path(os.environ.get("MINDMAP_IMGDIR", r"E:\_mm_tmp\imgs"))

CLUSTER_BG = ["#fdf6f5", "#f5f9f5", "#f4f8fd", "#faf5fd", "#fff8f2", "#f6f7f9", "#f2fafa"]
KC = {"板块": "#c0392b", "考点": "#2e7d32", "要点": "#2e7d32", "步骤": "#00695c",
      "思路": "#1565c0", "公式": "#6a1b9a", "考法": "#ad1457", "易错": "#e65100",
      "总览": "#37474f"}
KF = {"板块": "#ffffff", "考点": "#e8f5e9", "要点": "#f1f8e9", "步骤": "#e0f2f1",
      "思路": "#e3f2fd", "公式": "#ffffff", "考法": "#fce4ec", "易错": "#fff3e0",
      "总览": "#eceff1"}


# ============================================================ 知识库
def load_lib() -> dict[str, dict]:
    lib: dict[str, dict] = {}
    files = sorted(f for f in LIB_DIR.glob("*.json") if not f.name.startswith("_"))
    if not files:
        raise SystemExit(f"考点库为空：{LIB_DIR}")
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        for big in d.get("大类", []):
            for kp in big.get("细分", []):
                kp = dict(kp)
                kp["_大类"] = big["名称"]
                kp["_大类id"] = big["id"]
                if kp["id"] in lib:
                    raise SystemExit(f"考点库 id 重复：{kp['id']}")
                lib[kp["id"]] = kp
    return lib


def expand(spec: dict, lib: dict[str, dict]) -> tuple[dict, list[str]]:
    """把卷级 ref 展开成完整考点子树。"""
    out = copy.deepcopy(spec)
    missing: list[str] = []
    for b in out.get("板块", []):
        new: list[dict] = []
        for kp in b.get("考点", []):
            if isinstance(kp, str):
                kp = {"名称": kp}
            ref = kp.get("ref")
            if not ref:
                new.append(kp)
                continue
            base = lib.get(ref)
            if base is None:
                missing.append(f"{b.get('名称','?')} → {ref}")
                continue
            m = {"名称": kp.get("名称") or base["名称"], "ref": ref, "_大类": base["_大类"]}
            for k in ("要点", "步骤", "公式", "考法", "易错"):
                m[k] = list(base.get(k) or [])
            # 卷级「本题实例」原样透传
            if kp.get("本卷实例"):
                m["本卷实例"] = copy.deepcopy(kp["本卷实例"])
            if kp.get("页码"):
                m["页码"] = kp["页码"]
            # 本卷内容置顶
            for src, dst in (("本卷考法", "考法"), ("本卷易错", "易错")):
                v = kp.get(src) or []
                if isinstance(v, str):
                    v = [v]
                m[dst] = list(v) + m[dst]
                m["_" + src] = len(v)
            cu = kp.get("自定义") or {}
            for k in ("要点", "步骤", "公式", "考法", "易错"):
                v = cu.get(k) or []
                if isinstance(v, str):
                    v = [v]
                m[k] = m[k] + list(v)
                if v:
                    m["_自定义_" + k] = len(v)
            new.append(m)
        b["考点"] = new
    return out, missing


def collect_formulas(spec: dict) -> list[str]:
    fs: list[str] = []
    for b in spec.get("板块", []):
        for kp in b.get("考点", []):
            if isinstance(kp, dict):
                fs += list(kp.get("公式") or [])
    return list(dict.fromkeys(fs))


# ============================================================ KaTeX 批量
def _key(tex: str, fontsize: int, scale: float) -> str:
    return hashlib.sha1(f"{fontsize}|{scale}|{tex}".encode("utf-8")).hexdigest()[:16]


def _page(items: list[tuple[str, Path]], fontsize: int) -> str:
    css = (KATEX / "dist" / "katex.min.css").as_uri()
    js = (KATEX / "dist" / "katex.min.js").as_uri()
    blocks = []
    for i, (tex, _) in enumerate(items):
        if i:
            blocks.append("<div class='sep'></div>")
        blocks.append(f"<div class='f' id='f{i}'></div>")
    scripts = "\n".join(
        f"katex.render({json.dumps(t)}, document.getElementById('f{i}'), "
        "{displayMode:false,throwOnError:false,strict:false,trust:true});"
        for i, (t, _) in enumerate(items))
    return f"""<!doctype html><meta charset='utf-8'><link rel='stylesheet' href='{css}'>
<style>html,body{{margin:0;padding:0;background:#fff}}
.f{{display:block;padding:6px 8px;font-size:{fontsize}px;line-height:1.5;white-space:nowrap}}
.sep{{display:block;height:3px;background:#ff00ff;width:100%}}</style>
{''.join(blocks)}<script src='{js}'></script><script>{scripts}</script>"""


def _shot(page_html: Path, png: Path, height: int, scale: float) -> bool:
    r = subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
                        "--window-size=1800,%d" % height,
                        f"--force-device-scale-factor={scale}",
                        "--virtual-time-budget=8000",
                        f"--screenshot={png}", page_html.as_uri()],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return png.exists() and png.stat().st_size > 500


def katex_png_batch(formulas: list[str], outdir: Path, fontsize: int = 15,
                    scale: float = 2.0, chunk: int = 24, verbose: bool = True) -> dict[str, Path]:
    """一次 Edge 启动渲染一整批公式；按洋红分隔线切条。带磁盘缓存。"""
    from PIL import Image
    import numpy as np

    outdir.mkdir(parents=True, exist_ok=True)
    assert outdir.as_posix().isascii(), f"图片目录必须是 ASCII 路径：{outdir}"
    result: dict[str, Path] = {}
    todo: list[tuple[str, Path]] = []
    for tex in dict.fromkeys(formulas):
        p = outdir / (_key(tex, fontsize, scale) + ".png")
        if p.exists() and p.stat().st_size > 200:
            result[tex] = p
        else:
            todo.append((tex, p))
    if verbose and formulas:
        print(f"  公式 {len(list(dict.fromkeys(formulas)))} 条，缓存命中 "
              f"{len(formulas and list(dict.fromkeys(formulas))) - len(todo)}，待渲染 {len(todo)}")
    if not todo:
        return result

    tmp = outdir / "_batch"
    tmp.mkdir(exist_ok=True)
    for ci in range(0, len(todo), chunk):
        part = todo[ci:ci + chunk]
        h = tmp / f"p{ci}.html"
        h.write_text(_page(part, fontsize), encoding="utf-8")
        shot = tmp / f"p{ci}.png"
        bands = []
        for attempt, hh in enumerate((240 * len(part) + 400, 420 * len(part) + 800)):
            if not _shot(h, shot, hh, scale):
                continue
            a = np.array(Image.open(shot).convert("RGB"))
            r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
            mag = (r > 180) & (g < 120) & (b > 180)
            sep = mag.sum(axis=1) > a.shape[1] * 0.5
            runs, st = [], None
            for i, v in enumerate(sep):
                if v and st is None:
                    st = i
                elif not v and st is not None:
                    runs.append((st, i)); st = None
            if st is not None:
                runs.append((st, len(sep)))
            bands = []
            prev = 0
            for s0, s1 in runs:
                bands.append((prev, s0)); prev = s1
            bands.append((prev, len(sep)))
            if len(bands) == len(part):
                break
            if verbose:
                print(f"    重试（条带 {len(bands)}/{len(part)}）")
        if len(bands) != len(part):
            print(f"    [警告] 切条失败：{len(bands)}/{len(part)}，本批跳过")
            continue
        for (tex, dst), (y0, y1) in zip(part, bands):
            sub = a[max(y0, 0):y1]
            if sub.size == 0:
                continue
            m = (sub < 246).any(axis=2)
            if not m.any():
                continue
            ys, xs = np.where(m)
            pad = 4
            crop = a[max(y0 + ys.min() - pad, 0): y0 + ys.max() + pad + 1,
                     max(xs.min() - pad, 0): xs.max() + pad + 1]
            Image.fromarray(crop).save(dst)
            result[tex] = dst
    return result


# ============================================================ Graphviz
def esc(s) -> str:
    return html.escape(str(s)).replace("\n", "<BR/>")


def wrap(s: str, n: int = 22, maxl: int = 3) -> str:
    """按标点优先折行；无可折标点时按 n*1.45 硬折，避免出现超宽单行。"""
    hard = n + 3
    brk = "，。；、）,:：;!?！？ "
    lines, cur = [], ""
    for ch in str(s):
        cur += ch
        if (len(cur) >= n and ch in brk) or len(cur) >= hard:
            lines.append(cur); cur = ""
    if cur:
        lines.append(cur)
    if len(lines) > maxl:
        lines = lines[:maxl]
        lines[-1] = lines[-1].rstrip("，。；、,") + "…"
    return "<BR/>".join(esc(x) for x in lines)


def math_node(nid: str, tex: str, mpng: dict, indent: str = "    ") -> str:
    if tex not in mpng:
        return f'{indent}{nid} [label="公式：{esc(tex)}", fillcolor="#ffffff", color="{KC["公式"]}"];'
    p = mpng[tex]
    try:
        from PIL import Image
        w_px, h_px = Image.open(p).size
    except Exception:
        w_px, h_px = 200, 40
    W, H = max(w_px / 150.0, 0.45), max(h_px / 150.0, 0.20)
    return (f'{indent}{nid} [label="", shape=box, style="rounded", fixedsize=true, '
            f'width={W:.2f}, height={H:.2f}, color="{KC["公式"]}", penwidth=1.1, '
            f'image="{p.as_posix()}", imagescale=true];')


def _items(kp: dict, kind: str) -> list[tuple[str, bool]]:
    """返回 [(文本, 是否本卷内容)]"""
    vals = kp.get(kind) or []
    if isinstance(vals, str):
        vals = [vals]
    n = kp.get("_" + kind) or 0
    out = []
    for i, v in enumerate(vals):
        mark = kind in ("考法", "易错") and n and i < n
        out.append((v, bool(mark)))
    return out


def build(spec: dict, mpng: dict, direction: str = "LR") -> str:
    L = ["digraph mindmap {", f"  rankdir={direction};",
         '  graph [fontname="Microsoft YaHei", bgcolor="white", nodesep=0.10, '
         'ranksep=0.50, compound=true, pad=0.25];',
         '  node [fontname="Microsoft YaHei", shape=box, style="rounded,filled", '
         'penwidth=1.1, margin="0.12,0.06", fontsize=10];',
         '  edge [color="#9aa0a6", arrowsize=0.55, penwidth=0.9];',
         f'  root [label=<<B>{esc(spec.get("院校",""))}　{esc(spec.get("科目代码",""))}</B>'
         f'<BR/><FONT POINT-SIZE="10">{esc(spec.get("年份",""))} 真题</FONT>>, '
         'shape=circle, fillcolor="#1f4e79", fontcolor="white", width=1.9, '
         'penwidth=0, fontsize=14];']
    ov = spec.get("总览") or {}
    if ov:
        rows = []
        if ov.get("难度"):
            rows.append("难度：" + esc(ov["难度"]))
        if ov.get("特点"):
            rows.append("特点：" + wrap(ov["特点"], 26, 2))
        if ov.get("重点"):
            rows.append("重点：" + "、".join(esc(x) for x in ov["重点"]))
        L.append('  ov [label=<' + "<BR/>".join(rows) + '>, fillcolor="#eceff1", color="#37474f"];')
        L.append("  root -> ov;")
    for bi, b in enumerate(spec.get("板块", [])):
        tag = []
        if b.get("题号"):
            tag.append(f'第{b["题号"]}题')
        if b.get("分值"):
            tag.append(f'{b["分值"]}分')
        head = esc(b.get("名称", ""))
        if tag:
            head += f' <FONT POINT-SIZE="9">〔{"·".join(tag)}〕</FONT>'
        L.append(f"  subgraph cl{bi} {{")
        L.append(f'    style="rounded,filled"; fillcolor="{CLUSTER_BG[bi % len(CLUSTER_BG)]}"; '
                 'color="#e0e0e0"; penwidth=1; label=""; margin=12;')
        L.append(f'    b{bi} [label=<{head}>, fillcolor="white", color="{KC["板块"]}", '
                 'fontsize=12, penwidth=1.7];')
        for kind in ("思路", "易错"):
            vals = b.get(kind) or []
            if isinstance(vals, str):
                vals = [vals]
            for vi, v in enumerate(vals):
                nid = f"b{bi}_{'th' if kind=='思路' else 'er'}{vi}"
                L.append(f'    {nid} [label=<<FONT COLOR="{KC[kind]}">{kind}</FONT>'
                         f'<BR/>{wrap(v, 26)}>, fillcolor="{KF[kind]}", color="{KC[kind]}"];')
                L.append(f"    b{bi} -> {nid};")
        for ki, kp in enumerate(b.get("考点", [])):
            if isinstance(kp, str):
                kp = {"名称": kp}
            kid = f"b{bi}_kp{ki}"
            star = ' <FONT COLOR="#d32f2f">◆</FONT>' if kp.get("_本卷考法") else ''
            L.append(f'    {kid} [label=<<FONT POINT-SIZE="11"><B>{esc(kp.get("名称",""))}'
                     f'</B></FONT>{star}>, fillcolor="{KF["考点"]}", color="{KC["考点"]}", '
                     'penwidth=1.5];')
            L.append(f"    b{bi} -> {kid};")
            abbr = {"要点": "yd", "步骤": "bz", "考法": "kf", "易错": "er"}
            # 卷级「本题实例」放在最前：这一道题具体怎么破
            inst = kp.get("本卷实例")
            if inst:
                iid = f"{kid}_ins"
                pg = kp.get("页码")
                head = "本题实例" + (f' <FONT POINT-SIZE="9">〔{esc(pg)}〕</FONT>' if pg else "")
                L.append(f'    {iid} [label=<<B>{head}</B>>, fillcolor="#fff8e1", '
                         f'color="#f57f17", penwidth=1.6, fontsize=11];')
                L.append(f"    {kid} -> {iid};")
                for key, ab in (("关键一步", "k1"), ("中间结果", "k2"), ("卡点", "k3")):
                    vals = inst.get(key) or []
                    if isinstance(vals, str):
                        vals = [vals]
                    for vi, v in enumerate(vals):
                        nid = f"{iid}_{ab}{vi}"
                        L.append(f'    {nid} [label=<<FONT COLOR="#e65100" POINT-SIZE="9">'
                                 f'{key}</FONT><BR/>{wrap(v, 22, 3)}>, '
                                 f'fillcolor="#fffde7", color="#f9a825"];')
                        L.append(f"    {iid} -> {nid};")
            for kind in ("要点", "步骤", "考法", "易错"):
                for vi, (v, cur) in enumerate(_items(kp, kind)):
                    nid = f"{kid}_{abbr[kind]}{vi}"
                    lab = f'<FONT COLOR="{KC[kind]}" POINT-SIZE="9">{kind}{"◆本卷" if cur else ""}</FONT>'
                    fill = "#ffe0e0" if cur else KF[kind]
                    col = "#d32f2f" if cur else KC[kind]
                    L.append(f'    {nid} [label=<{lab}<BR/>{wrap(v, 20, 2)}>, '
                             f'fillcolor="{fill}", color="{col}"];')
                    L.append(f"    {kid} -> {nid};")
            for fi, tex in enumerate(kp.get("公式") or []):
                nid = f"{kid}_fm{fi}"
                L.append(math_node(nid, tex, mpng))
                L.append(f"    {kid} -> {nid};")
        L.append("  }")
        L.append(f"  root -> b{bi};")
    L.append("}")
    return "\n".join(L) + "\n"


# ============================================================ 主流程
def log_progress(row: list[str]) -> None:
    OUT.mkdir(exist_ok=True)
    new = not PROGRESS.exists()
    with PROGRESS.open("a", encoding="utf-8") as f:
        if new:
            f.write("时间\t卷\t状态\t耗时s\t公式数\t输出\n")
        f.write("\t".join(row) + "\n")


def _variants(spec: dict, split: bool) -> list[tuple[str, dict]]:
    """split=True 时输出「总览图 + 每板块子图」；否则输出整张图。"""
    if not split:
        return [("", spec)]
    out: list[tuple[str, dict]] = []
    ov = copy.deepcopy(spec)
    for b in ov.get("板块", []):
        for kp in b.get("考点", []):
            if isinstance(kp, dict):
                for k in ("要点", "步骤", "公式", "考法", "易错"):
                    kp[k] = []
                kp.pop("本卷实例", None)
    out.append(("_总览", ov))
    for i, b in enumerate(spec.get("板块", [])):
        sub = {k: copy.deepcopy(v) for k, v in spec.items() if k != "板块"}
        sub["板块"] = [copy.deepcopy(b)]
        name = re.sub(r'[\\/:*?"<>|\s]+', "", str(b.get("名称", f"b{i+1}")))[:12]
        out.append((f"_板块{i+1}_{name}", sub))
    return out


def render_one(jp: Path, lib: dict, direction: str, force: bool, split: bool = False,
               png: bool = False) -> bool:
    t0 = time.perf_counter()
    spec_raw = json.loads(jp.read_text(encoding="utf-8"))
    spec, missing = expand(spec_raw, lib)
    stem = re.sub(r'[\\/:*?"<>|]+', "_",
                  f"{spec.get('院校','')}_{spec.get('科目代码') or 'NA'}"
                  f"_{spec.get('年份','')}_导图")
    variants = _variants(spec, split)
    png0 = OUT / f"{stem}{variants[0][0]}_{direction}.png"
    if not force and png0.exists() and png0.stat().st_mtime >= jp.stat().st_mtime:
        print(f"[skip] {stem}（已存在）")
        log_progress([time.strftime("%F %T"), stem, "skip", "0", "-", png0.name])
        return True
    print(f"[{stem}] ref={sum(1 for b in spec.get('板块',[]) for k in b.get('考点',[]) if k.get('ref'))} "
          f"缺失={len(missing)}" + (f" {missing}" if missing else ""))
    all_f = collect_formulas(spec)
    mpng = katex_png_batch(all_f, IMGDIR) if all_f else {}
    ok = True
    outs = []
    for suffix, vspec in variants:
        fs = collect_formulas(vspec)
        vstem = f"{stem}{suffix}"
        dotf = OUT / f"{vstem}_{direction}.dot"
        dotf.write_text(build(vspec, mpng, direction), encoding="utf-8")
        for fmt in (("png", "svg") if png else ("svg",)):
            o = OUT / f"{vstem}_{direction}.{fmt}"
            r = subprocess.run([str(DOT), f"-T{fmt}", str(dotf), "-o", str(o)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            good = o.exists() and o.stat().st_size > 1000
            ok = ok and good
            if fmt == "png" and good:
                try:
                    from PIL import Image
                    sz = Image.open(o).size
                except Exception:
                    sz = ("?", "?")
                outs.append(f"{o.name} {sz[0]}x{sz[1]}")
                print(f"   {vstem}: {sz[0]}x{sz[1]}  {o.stat().st_size/1024:.0f} KB  ({len(fs)} 公式)")
            elif not good:
                print(f"   {vstem}.{fmt}: 失败 {(r.stderr or '')[:160]}")
    el = time.perf_counter() - t0
    print(f"   耗时 {el:.1f}s  共 {len(variants)} 张")
    log_progress([time.strftime("%F %T"), stem, "ok" if ok else "fail",
                  f"{el:.1f}", str(len(all_f)), " | ".join(outs)])
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="卷级映射 json，支持 glob")
    ap.add_argument("--dir", default="LR")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--split", action="store_true", help="输出总览图 + 每板块子图")
    ap.add_argument("--png", action="store_true",
                    help="额外输出 PNG（默认只出 SVG，PDF/HTML 都不需要 PNG）")
    ap.add_argument("--lib", action="store_true", help="只做知识库自检")
    a = ap.parse_args()

    lib = load_lib()
    n_kp = len(lib)
    n_f = len({f for kp in lib.values() for f in (kp.get("公式") or [])})
    print(f"考点库：{n_kp} 个细分考点 / {n_f} 条公式   图片目录 {IMGDIR}")
    if a.lib:
        return 0

    files = sorted(Path(p) for p in glob.glob(a.json) if Path(p).suffix == ".json")
    if not files:
        print("没有匹配到卷级 json"); return 1
    OUT.mkdir(exist_ok=True)
    bad = 0
    for jp in files:
        try:
            if not render_one(jp, lib, a.dir, a.force, a.split, a.png):
                bad += 1
        except Exception as e:
            bad += 1
            print(f"   [错误] {jp.name}: {type(e).__name__}: {e}")
            log_progress([time.strftime("%F %T"), jp.stem, "error", "-", "-", str(e)[:120]])
    print(f"\n完成 {len(files)-bad}/{len(files)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
