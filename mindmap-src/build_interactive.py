#!/usr/bin/env python -u
# -*- coding: utf-8 -*-
r"""
生成交互式思维导图（单文件 HTML，点击展开/折叠，公式用 KaTeX 实时排版）。

   考点库/*.json  +  思维导图_v6/<院校>_<年份>.json
        ↓ 复用 mindmap_v6 的 load_lib / expand
   思维导图_交互/<院校>_<年份>.html     ← 数据内嵌，引用 ./assets
   思维导图_交互/assets/               ← d3 + katex 离线包（写一次，所有卷共用）
   思维导图_交互/index.html            ← 目录页

用法
  python build_interactive.py                        # 全部卷
  python build_interactive.py 哈尔滨工业大学_2025     # 指定卷
  python build_interactive.py --assets-only          # 只铺静态资源
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "思维导图_交互"
ASSETS = OUT / "assets"
SPEC_DIR = HERE / "思维导图_v6"

_s = importlib.util.spec_from_file_location("mm6", HERE / "mindmap_v6.py")
mm6 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(mm6)

# 节点类型 → (前缀标签, 边框色, 底色)
TYPES = {
    "root":  ("",         "#1f4e79", "#1f4e79"),
    "block": ("板块",     "#c0392b", "#ffffff"),
    "idea":  ("思路",     "#1565c0", "#e3f2fd"),
    "warn":  ("易错",     "#e65100", "#fff3e0"),
    "kp":    ("",         "#2e7d32", "#e8f5e9"),
    "yd":    ("要点",     "#2e7d32", "#f1f8e9"),
    "bz":    ("步骤",     "#00695c", "#e0f2f1"),
    "kf":    ("考法",     "#ad1457", "#fce4ec"),
    "er":    ("易错",     "#e65100", "#fff3e0"),
    "ins":   ("",         "#f57f17", "#fff8e1"),
    "k1":    ("关键一步", "#e65100", "#fffde7"),
    "k2":    ("中间结果", "#e65100", "#fffde7"),
    "k3":    ("卡点",     "#e65100", "#fffde7"),
}


def nd(label: str, typ: str, **kw) -> dict:
    d = {"label": label, "type": typ}
    d.update(kw)
    return d


def to_tree(spec: dict) -> dict:
    """把展开后的卷级 spec 转成前端用的树。"""
    root = nd(f'{spec.get("院校","")} {spec.get("科目代码","")}', "root",
              sub=f'{spec.get("年份","")} · {spec.get("科目","")}')
    kids: list[dict] = []

    ov = spec.get("总览") or {}
    if ov:
        parts = []
        if ov.get("难度"):
            parts.append(f'难度：{ov["难度"]}')
        if ov.get("特点"):
            parts.append(f'特点：{ov["特点"]}')
        if ov.get("重点"):
            parts.append("重点：" + "、".join(ov["重点"]))
        kids.append(nd("　".join(parts), "warn"))

    for b in spec.get("板块", []):
        tag = []
        if b.get("题号"):
            tag.append(f'第{b["题号"]}题')
        if b.get("分值"):
            tag.append(f'{b["分值"]}分')
        lab = b.get("名称", "")
        if tag:
            lab += f'　〔{"·".join(tag)}〕'
        bn = nd(lab, "block")
        bk: list[dict] = []
        for key in ("思路", "易错"):
            vals = b.get(key) or []
            if isinstance(vals, str):
                vals = [vals]
            for v in vals:
                bk.append(nd(v, "idea" if key == "思路" else "warn"))
        for kp in b.get("考点", []):
            if isinstance(kp, str):
                kp = {"名称": kp}
            kn = nd(kp.get("名称", ""), "kp")
            kk: list[dict] = []
            inst = kp.get("本卷实例")
            if inst:
                inn = nd("本题实例" + (f'　〔{kp["页码"]}〕' if kp.get("页码") else ""), "ins")
                for key, tp in (("关键一步", "k1"), ("中间结果", "k2"), ("卡点", "k3")):
                    vals = inst.get(key) or []
                    if isinstance(vals, str):
                        vals = [vals]
                    for v in vals:
                        inn.setdefault("children", []).append(nd(v, tp))
                kk.append(inn)
            n1 = kp.get("_本卷考法") or 0
            for v in (kp.get("要点") or []):
                kk.append(nd(v, "yd"))
            for v in (kp.get("步骤") or []):
                kk.append(nd(v, "bz"))
            for v in (kp.get("公式") or []):
                kk.append(nd(v, "fm", tex=v))
            for i, v in enumerate(kp.get("考法") or []):
                kk.append(nd(v, "kf", own=(i < n1)))
            n2 = kp.get("_本卷易错") or 0
            for i, v in enumerate(kp.get("易错") or []):
                kk.append(nd(v, "er", own=(i < n2)))
            if kk:
                kn["children"] = kk
            bk.append(kn)
        if bk:
            bn["children"] = bk
        kids.append(bn)
    if kids:
        root["children"] = kids
    return root


def _walk(n):
    yield n
    for c in n.get("children", []):
        yield from _walk(c)


HTML_TPL = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>__TITLE__</title>
<link rel="stylesheet" href="assets/katex/katex.min.css">
<style>
*{box-sizing:border-box}
html,body{margin:0;height:100%;font-family:"Microsoft YaHei",system-ui,sans-serif;
  background:#fbfbfc;overflow:hidden}
#bar{position:fixed;left:0;right:0;top:0;height:46px;display:flex;align-items:center;gap:8px;
  padding:0 14px;background:#fff;border-bottom:1px solid #e3e6ea;z-index:10}
#bar h1{font-size:14px;margin:0;font-weight:600;color:#1f4e79;white-space:nowrap}
#bar .meta{font-size:12px;color:#7a828a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#bar .sp{flex:1}
button{font:inherit;font-size:12px;padding:5px 10px;border:1px solid #d6dbe0;background:#fff;
  border-radius:6px;cursor:pointer;color:#37474f;white-space:nowrap}
button:hover{background:#f2f6fa;border-color:#b9c3cc}
button.on{background:#1f4e79;border-color:#1f4e79;color:#fff}
input[type=search]{font:inherit;font-size:12px;padding:5px 9px;border:1px solid #d6dbe0;
  border-radius:6px;width:140px;outline:none}
input[type=search]:focus{border-color:#1f4e79}
#hint{position:fixed;left:14px;bottom:10px;font-size:11px;color:#98a2ab;z-index:10}
#brand{width:24px;height:24px;flex:none;display:block}
#wmBig{position:fixed;left:50%;top:52%;width:44vmin;max-width:520px;
  transform:translate(-50%,-50%);opacity:.04;pointer-events:none;z-index:0}
#wm{position:fixed;right:14px;bottom:12px;display:flex;align-items:center;gap:9px;
  z-index:9;pointer-events:none;opacity:.42;user-select:none}
#wm img{width:46px;height:46px;display:block}
#wm .txt{font-size:10px;line-height:1.65;color:#4a4a4a;text-align:left}
#wm .txt b{font-weight:600;color:#6A3D9A}
svg{display:block;width:100%;height:100%;cursor:grab;position:relative;z-index:1}
svg.grabbing{cursor:grabbing}
.link{fill:none;stroke:#c3c9cf;stroke-width:1.2px}
.box{font-size:12px;line-height:1.5;padding:4px 9px;border:1px solid #999;border-radius:7px;
  display:inline-block;max-width:288px;white-space:normal;word-break:break-word;color:#243238}
.box .tag{font-size:10px;opacity:.9;margin-right:5px;font-weight:700}
.box.own{box-shadow:inset 0 0 0 2px #ef9a9a}
.box .katex{font-size:1.02em}
.hit .box{outline:3px solid #ffd54f}
.dim{opacity:.2}
</style></head><body>
<div id="bar">
  <img id="brand" src="assets/wanren-education-logo.png" alt="">
  <h1>__TITLE__</h1><span class="meta">__META__</span><span class="sp"></span>
  <button id="b0" class="on">只看板块</button>
  <button id="b1">展开到考点</button>
  <button id="b2">展开全部</button>
  <button id="b3">重置视图</button>
  <input type="search" id="q" placeholder="搜索…">
</div>
<img id="wmBig" src="assets/wanren-education-logo.png" alt="">
<svg id="svg"><g id="g"></g></svg>
<div id="hint">点击节点展开 / 折叠　·　滚轮缩放　·　拖拽平移</div>
<div id="wm">
  <img src="assets/wanren-education-logo.png" alt="">
  <div class="txt">控制考研哪家强，<b>万人教育</b>来领航<br>
    公众号：控制自动化考研　微信：kongzhiwyz7<br>
    小白学长 QQ：3789432577</div>
</div>
<script src="assets/d3.min.js"></script>
<script src="assets/katex/katex.min.js"></script>
<script>
var DATA = __DATA__;
var TYPES = __TYPES__;
var COL = 300, GAP = 9, DEFH = 34;

var svg = d3.select("#svg"), g = d3.select("#g");
var linkG = g.append("g"), nodeG = g.append("g");
var root = d3.hierarchy(DATA);

var _u = 0;
(function tag(n){ n.uid = "n" + (_u++); (n.children || []).forEach(tag); })(root.data);

var H = {}, pass = 0;
var ZOOM = d3.zoom().scaleExtent([0.04, 2.5]).on("zoom", function (e) {
  g.attr("transform", e.transform);
});
svg.call(ZOOM);

function T(t, i, def) { return (t && t[i] != null) ? t[i] : def; }

function layout() {
  d3.tree().nodeSize([1, 1])(root);
  var cur = 0, pos = new Map();
  (function pack(n) {
    if (!n.children || !n.children.length) {
      var h = H[n.data.uid] || DEFH;
      pos.set(n, cur + h / 2);
      cur += h + GAP;
      return;
    }
    n.children.forEach(pack);
    pos.set(n, (pos.get(n.children[0]) + pos.get(n.children[n.children.length - 1])) / 2);
  })(root);
  root.each(function (n) { n.yy = pos.get(n); n.xx = n.depth * COL; });
}

function nodeH(d) { return H[d.data.uid] || DEFH; }

function draw() {
  layout();
  var nodes = root.descendants(), links = root.links();
  var ymin = d3.min(nodes, function (d) { return d.yy; });
  var ymax = d3.max(nodes, function (d) { return d.yy; });
  var mid = (ymin + ymax) / 2;

  linkG.selectAll("path").data(links, function (d) { return d.target.data.uid; })
    .join("path").attr("class", "link")
    .attr("d", function (d) {
      var y0 = d.source.yy - mid, y1 = d.target.yy - mid;
      var x0 = d.source.xx + 8, x1 = d.target.xx - 4, mx = (x0 + x1) / 2;
      return "M" + x0 + "," + y0 + "C" + mx + "," + y0 + " " + mx + "," + y1 + " " + x1 + "," + y1;
    });

  var sel = nodeG.selectAll("g.nd").data(nodes, function (d) { return d.data.uid; });
  sel.exit().remove();
  var ent = sel.enter().append("g").attr("class", "nd");
  ent.on("click", function (ev, d) {
    if (d.children) { d._children = d.children; d.children = null; }
    else if (d._children) { d.children = d._children; d._children = null; }
    else { return; }
    ev.stopPropagation();
    pass = 0; draw();
  });
  ent.append("foreignObject").append("xhtml:div").attr("class", "box");

  var all = ent.merge(sel);
  all.select("foreignObject")
    .attr("x", function (d) { return d.xx; })
    .attr("y", function (d) { return d.yy - mid - nodeH(d) / 2 - 12; })
    .attr("width", 296)
    .attr("height", function (d) { return nodeH(d) + 24; });

  all.select(".box")
    .attr("class", function (d) { return "box" + (d.data.own ? " own" : ""); })
    .style("background", function (d) { return T(TYPES[d.data.type], 2, "#eee"); })
    .style("border-color", function (d) { return T(TYPES[d.data.type], 1, "#999"); })
    .style("color", function (d) { return d.data.type === "root" ? "#fff" : "#243238"; })
    .each(function (d) {
      var el = d3.select(this);
      el.selectAll("*").remove();
      if (d.data.type === "fm") {
        var sp = el.append("span");
        try {
          katex.render(d.data.tex, sp.node(),
            { displayMode: false, throwOnError: false, strict: false, trust: true });
        } catch (err) { sp.text(d.data.tex); }
        return;
      }
      var tg = T(TYPES[d.data.type], 0, "");
      if (tg) {
        el.append("span").attr("class", "tag")
          .style("color", T(TYPES[d.data.type], 1, "#666")).text(tg);
      }
      el.append("span").text(d.data.label);
      if (d.data.type === "root" && d.data.sub) {
        el.append("div").style("font-size", "11px").style("opacity", 0.85).text(d.data.sub);
      }
    });

  if (pass === 0) {
    var m = {};
    nodeG.selectAll("g.nd").each(function (d) {
      var b = this.querySelector(".box");
      m[d.data.uid] = b ? Math.ceil(b.getBoundingClientRect().height) + 12 : DEFH;
    });
    H = m; pass = 1; draw(); return;
  }
  applySearch();
}

function setDepth(depth) {
  root.each(function (d) {
    if (d.depth < depth) {
      if (d._children) { d.children = d._children; d._children = null; }
    } else if (d.children) {
      d._children = d.children; d.children = null;
    }
  });
  pass = 0; draw(); setTimeout(resetView, 40);
  [["b0", 1], ["b1", 2], ["b2", 99]].forEach(function (p) {
    document.getElementById(p[0]).classList.toggle("on", p[1] === depth);
  });
}

function resetView() {
  var nodes = root.descendants();
  var y0 = d3.min(nodes, function (d) { return d.yy; });
  var y1 = d3.max(nodes, function (d) { return d.yy; });
  var x1 = d3.max(nodes, function (d) { return d.xx; });
  var w = svg.node().clientWidth, h = svg.node().clientHeight;
  var bw = x1 + 430, bh = (y1 - y0) + 90;
  var k = Math.max(0.12, Math.min(w / bw, h / bh, 1.0));
  var ty = h / 2 + 20;
  svg.transition().duration(300).call(ZOOM.transform, d3.zoomIdentity.translate(60, ty).scale(k));
}

function applySearch() {
  var q = document.getElementById("q").value.trim();
  nodeG.selectAll("g.nd").classed("hit", false).classed("dim", false);
  if (!q) return;
  var hit = new Set();
  root.each(function (d) {
    var s = (d.data.label || "") + " " + (d.data.tex || "");
    if (s.indexOf(q) >= 0) { d.ancestors().forEach(function (a) { hit.add(a); }); }
  });
  nodeG.selectAll("g.nd").each(function (d) {
    d3.select(this).classed(hit.has(d) ? "hit" : "dim", true);
  });
}

document.getElementById("b0").onclick = function () { setDepth(1); };
document.getElementById("b1").onclick = function () { setDepth(2); };
document.getElementById("b2").onclick = function () { setDepth(99); };
document.getElementById("b3").onclick = resetView;
document.getElementById("q").oninput = applySearch;

try { setDepth(1); } catch (e) { document.title = "ERR: " + e.message; }
</script></body></html>
'''


BRAND_LOGO_SRC = Path("E:/无引流择校/assets/wanren-education-logo.png")


def write_assets() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    if BRAND_LOGO_SRC.exists():
        shutil.copy2(BRAND_LOGO_SRC, ASSETS / "wanren-education-logo.png")
        print("  品牌 logo 已就位")
    d3src = HERE / "mindmap" / "node_modules" / "d3" / "dist" / "d3.min.js"
    ksrc = HERE / "katex" / "node_modules" / "katex" / "dist"
    if not d3src.exists():
        raise SystemExit(f"找不到 d3: {d3src}")
    if not (ksrc / "katex.min.js").exists():
        raise SystemExit(f"找不到 katex: {ksrc}")
    shutil.copy2(d3src, ASSETS / "d3.min.js")
    dst = ASSETS / "katex"
    dst.mkdir(exist_ok=True)
    for f in ("katex.min.js", "katex.min.css"):
        shutil.copy2(ksrc / f, dst / f)
    if (dst / "fonts").exists():
        shutil.rmtree(dst / "fonts")
    shutil.copytree(ksrc / "fonts", dst / "fonts")
    print(f"  资源就绪: {ASSETS}")


def build_one(jp: Path, lib: dict) -> dict:
    raw = json.loads(jp.read_text(encoding="utf-8"))
    spec, missing = mm6.expand(raw, lib)
    tree = to_tree(spec)
    title = f'{spec.get("院校","")} {spec.get("年份","")} {spec.get("科目代码","")}'
    meta = f'{spec.get("科目","")}　·　{spec.get("来源","")[:46]}'
    doc = (HTML_TPL
           .replace("__TITLE__", html.escape(title))
           .replace("__META__", html.escape(meta))
           .replace("__TYPES__", json.dumps(TYPES, ensure_ascii=False))
           .replace("__DATA__", json.dumps(tree, ensure_ascii=False)))
    out = OUT / (f'{spec.get("院校","")}_{spec.get("科目代码") or "NA"}'
                 f'_{spec.get("年份","")}.html')
    out.write_text(doc, encoding="utf-8")
    n = sum(1 for _ in _walk(tree))
    print(f'  {out.name}  {out.stat().st_size/1024:.0f} KB  节点 {n}  缺 ref {len(missing)}')
    return {"file": out.name, "院校": spec.get("院校"), "年份": spec.get("年份"),
            "代码": spec.get("科目代码"), "科目": spec.get("科目"), "节点": n}


def write_index(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: (str(r["院校"]), r["年份"]))
    tr = "\n".join(
        f'<tr><td><a href="{html.escape(r["file"])}">{html.escape(str(r["院校"]))}</a></td>'
        f'<td>{r["年份"]}</td><td>{html.escape(str(r["代码"]))}</td>'
        f'<td>{html.escape(str(r["科目"]))}</td><td>{r["节点"]}</td></tr>' for r in rows)
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>控制考研真题思维导图 · 交互版</title><style>
body{{font-family:"Microsoft YaHei",system-ui,sans-serif;margin:36px;color:#243238}}
h1{{font-size:20px;color:#1f4e79}} table{{border-collapse:collapse;font-size:13px}}
th,td{{border-bottom:1px solid #e8ebee;padding:7px 14px;text-align:left}}
th{{color:#7a828a;font-weight:500}} a{{color:#1565c0;text-decoration:none}}
a:hover{{text-decoration:underline}}
</style></head><body>
<h1>控制考研真题思维导图 · 交互版</h1>
<p style="font-size:13px;color:#7a828a">共 {len(rows)} 套。点击进入；节点可展开 / 折叠，滚轮缩放，右上角可搜索。</p>
<table><tr><th>院校</th><th>年份</th><th>代码</th><th>科目</th><th>节点数</th></tr>
{tr}</table></body></html>"""
    (OUT / "index.html").write_text(doc, encoding="utf-8")
    print(f"  目录页: index.html（{len(rows)} 套）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json", nargs="*", help="卷级 json 文件名（不带目录），留空=全部")
    ap.add_argument("--assets-only", action="store_true")
    a = ap.parse_args()

    print("铺静态资源…")
    write_assets()
    if a.assets_only:
        return 0

    lib = mm6.load_lib()
    OUT.mkdir(exist_ok=True)
    if a.json:
        files = [SPEC_DIR / (n if n.endswith(".json") else n + ".json") for n in a.json]
    else:
        files = sorted(SPEC_DIR.glob("*.json"))
    rows = []
    for jp in files:
        if not jp.exists():
            print(f"  [缺] {jp.name}")
            continue
        rows.append(build_one(jp, lib))
    if len(files) > 1:
        write_index(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
