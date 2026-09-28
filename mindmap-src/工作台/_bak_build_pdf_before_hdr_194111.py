#!/usr/bin/env python -u
# -*- coding: utf-8 -*-
r"""
把思维导图_v6 里已生成的 SVG 拼成「一套卷一个 PDF」。

普通模式：每页一张图，A4 统一或页随图自适应。
品牌模式（--brand，宝典A 同款）：封面页 + 页眉 + 页中 logo 水印 + 页脚页码。

用法
  python build_pdf.py 哈尔滨工业大学_2025 --brand      # 品牌样板
  python build_pdf.py                                  # 全部卷（普通版式）
  python build_pdf.py --fit raw                        # 页随图自适应无留白
"""
from __future__ import annotations

import argparse
import json as _json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "思维导图_v6"
OUT = HERE / "思维导图_PDF"
import pdf_paths as PP          # PDF 归档路径（按院校分文件夹）
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
LONG_MM = 297.0
MARGIN_MM = 6.0
PT2MM = 25.4 / 72.0

BRAND = {
    "标语":     "控制考研哪家强，万人教育来领航",
    "群号":     "27控制考研初试交流群：635970715",
    "公众号":   "控制自动化考研",
    "微信":     "kongzhiwyz7",
    "QQ":       "小白学长 QQ：3789432577",
    "品牌名":   "万人教育",
    "主题色":   "#6A3D9A",
    "logo源":   Path(r"E:\无引流择校\assets\wanren-education-logo.png"),
    "logo":     "assets/wanren-education-logo.png",
    "追溯编号": "",
}
ASSET_DIR = OUT / "assets"

SVG_HDR = re.compile(r'<svg[^>]*?width="([\d.]+)pt"[^>]*?height="([\d.]+)pt"', re.S)


def load_svg(p: Path):
    t = p.read_text(encoding="utf-8", errors="replace")
    m = SVG_HDR.search(t)
    if not m:
        return None
    w, h = float(m.group(1)), float(m.group(2))
    t = re.sub(r"<\?xml[^>]*\?>", "", t)
    t = re.sub(r"<!DOCTYPE[^>]*>", "", t, flags=re.S)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r'(<title>mindmap</title>\s*)<polygon fill="white" stroke="none"[^/]*/>',
               r"\1", t, count=1)
    t = re.sub(r'(<svg\b[^>]*?)\swidth="[\d.]+pt"', r'\1 width="100%"', t, count=1)
    t = re.sub(r'(<svg\b[^>]*?)\sheight="[\d.]+pt"', r'\1 height="100%"', t, count=1)
    return t.strip(), w, h


def page_mm(w_pt, h_pt, long_mm=LONG_MM):
    w_mm, h_mm = w_pt * PT2MM, h_pt * PT2MM
    k = long_mm / max(w_mm, h_mm)
    return round(w_mm * k, 2), round(h_mm * k, 2)


def collect(stem_base: str):
    o = SRC / f"{stem_base}_导图_总览_LR.svg"
    out = [o] if o.exists() else []
    blocks = sorted(SRC.glob(f"{stem_base}_导图_板块*_LR.svg"),
                    key=lambda p: int(re.search(r"_板块(\d+)_", p.name).group(1)))
    return out + blocks


def school_of(stem_base: str) -> str:
    return stem_base.split("_")[0]


def build_html(svgs, fit="portrait"):
    if fit == "raw":
        css, body = [], []
        for i, (markup, w, h) in enumerate(svgs):
            pw, ph = page_mm(w, h)
            css.append(f"@page p{i} {{ size: {pw}mm {ph}mm; margin: 0 }}")
            body.append(f'<section class="pg" style="page:p{i};width:{pw}mm;'
                        f'height:{ph}mm">{markup}</section>')
        return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{chr(10).join(css)}
html,body{{margin:0;padding:0;background:#fff}}
.pg{{display:block;overflow:hidden;page-break-after:always;break-after:page}}
.pg:last-child{{page-break-after:auto;break-after:auto}}
.pg svg{{display:block;width:100%;height:100%}}
</style></head><body>
{chr(10).join(body)}
</body></html>"""

    def orient(w, h):
        if fit == "portrait":
            return "P"
        if fit == "landscape":
            return "L"
        return "L" if (w / h) > 1.15 else "P"

    m = MARGIN_MM
    geom = {}
    for k in sorted({orient(w, h) for _, w, h in svgs}):
        pw, ph = (210.0, 297.0) if k == "P" else (297.0, 210.0)
        geom[k] = (f"pgA4{k}", pw - 2 * m, ph - 2 * m, pw, ph)
    rules = "\n".join(f"@page {n} {{ size: {pw}mm {ph}mm; margin: {m}mm }}"
                      for n, cw, ch, pw, ph in geom.values())
    blocks = []
    for mk, w, h in svgs:
        n, cw, ch, _pw, _ph = geom[orient(w, h)]
        blocks.append(f'<section class="pg" style="page:{n};width:{cw}mm;'
                      f'height:{ch}mm">{mk}</section>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{rules}
html,body{{margin:0;padding:0;background:#fff}}
.pg{{display:block;overflow:hidden;page-break-after:always;break-after:page}}
.pg:last-child{{page-break-after:auto;break-after:auto}}
.pg svg{{display:block;width:100%;height:100%}}
</style></head><body>
{chr(10).join(blocks)}
</body></html>"""


def _brand_css() -> str:
    c = BRAND["主题色"]
    return f"""
@page {{ size: 210mm 297mm; margin: 0 }}
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;background:#fff;
  font-family:"Microsoft YaHei","PingFang SC",sans-serif;color:#243238}}
.pg{{position:relative;width:210mm;height:297mm;overflow:hidden;background:#fff;
  page-break-after:always;break-after:page}}
.pg:last-child{{page-break-after:auto;break-after:auto}}
.hd{{position:absolute;top:7mm;left:11mm;right:11mm;height:8mm;
  display:flex;justify-content:space-between;align-items:flex-end;
  font-size:8pt;color:#444;border-bottom:0.35mm solid #b9b9b9;padding-bottom:1.2mm}}
.ft{{position:absolute;bottom:7mm;left:11mm;right:11mm;height:10mm;
  display:flex;justify-content:space-between;align-items:flex-start;
  font-size:8pt;color:#444;border-top:0.35mm solid #b9b9b9;padding-top:1.2mm}}
.ft .mid{{position:absolute;left:0;right:0;top:1.2mm;text-align:center;color:#666}}
.wm{{position:absolute;left:50%;top:50%;width:122mm;transform:translate(-50%,-50%);
  opacity:0.09;z-index:0}}
.body{{position:absolute;top:17mm;left:9mm;right:9mm;bottom:18mm;z-index:1}}
.body svg{{display:block;width:100%;height:100%}}
.cover{{display:flex;flex-direction:column;align-items:center;padding:36mm 22mm 20mm}}
.cover .lg{{width:54mm}}
.cover .tt{{margin-top:15mm;font-size:29pt;font-weight:700;letter-spacing:2mm;color:{c}}}
.cover .cd{{margin-top:7mm;font-size:16pt;color:#555;letter-spacing:1.2mm}}
.cover .yr{{margin-top:20mm;font-size:14pt;color:#333}}
.cover .sb{{margin-top:5mm;font-size:19pt;font-weight:600;color:{c};letter-spacing:1mm}}
.cover .rule{{margin-top:13mm;width:76mm;border-top:0.6mm solid {c}}}
.cover .tg{{margin-top:11mm;font-size:10.5pt;color:#777;letter-spacing:0.8mm}}
.cover .bt{{position:absolute;bottom:24mm;left:0;right:0;text-align:center;
  font-size:9pt;color:#8d8d8d;line-height:2}}
.cover .no{{position:absolute;bottom:13mm;left:0;right:0;text-align:center;
  font-size:8pt;color:#c0c0c0}}
.cover .wm2{{position:absolute;left:50%;top:74%;width:104mm;
  transform:translate(-50%,-50%);opacity:0.045;z-index:0}}
.cover > *{{position:relative;z-index:1}}
"""


def _logo_src() -> str:
    """返回 logo 的绝对 file:// 地址（HTML 在 _work 子目录里，相对路径会失效）。"""
    p = ASSET_DIR / "wanren-education-logo.png"
    if not p.exists():
        p = BRAND["logo源"]
    return p.as_uri()


def build_html_brand(svgs, meta, cover=True):
    lg = _logo_src()
    no = BRAND.get("追溯编号") or "&nbsp;"
    parts = []
    if cover:
        parts.append(f'''<section class="pg cover">
<img class="wm2" src="{lg}">
<img class="lg" src="{lg}">
<div class="tt">真题思维导图</div>
<div class="cd">{meta.get("院校","")}　{meta.get("代码","")}</div>
<div class="yr">{meta.get("年份","")} 年硕士研究生入学考试</div>
<div class="sb">{meta.get("科目","")}</div>
<div class="rule"></div>
<div class="tg">板块划分　·　考点展开　·　公式排版　·　本题实例</div>
<div class="bt">{BRAND["标语"]}<br>公众号：{BRAND["公众号"]}　|　微信：{BRAND["微信"]}　|　{BRAND["QQ"]}</div>
<div class="no">{BRAND.get("追溯编号") or ""}</div>
</section>''')
    start = 1 if cover else 0
    for i, (mk, w, h) in enumerate(svgs, start):
        parts.append(f'''<section class="pg">
<div class="hd"><span>{BRAND["标语"]}</span><span>{BRAND["群号"]}</span></div>
<img class="wm" src="{lg}">
<div class="body">{mk}</div>
<div class="ft"><span>公众号：{BRAND["公众号"]}</span><span>{no}</span>
<span>微信：{BRAND["微信"]}　{BRAND["QQ"]}</span><span class="mid">第 {i} 页</span></div>
</section>''')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{_brand_css()}</style>
</head><body>
{chr(10).join(parts)}
</body></html>"""


def print_pdf(html_path: Path, pdf_path: Path, timeout_s=240) -> bool:
    tmp = pdf_path.with_suffix(".tmp.pdf")
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            pass
    r = subprocess.run([EDGE, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=20000",
                        f"--print-to-pdf={tmp}", html_path.as_uri()],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout_s)
    if not tmp.exists() or tmp.stat().st_size < 1000:
        print(f"    打印失败: {(r.stderr or r.stdout or '')[:200]}")
        return False
    for k in range(4):
        try:
            os.replace(tmp, pdf_path)
            return True
        except OSError:
            time.sleep(0.6)
            pdf_path = pdf_path.with_name(f"{pdf_path.stem}_v{k+1}.pdf")
    print("    改名失败（PDF 被占用）")
    return False


def write_assets() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    src = BRAND["logo源"]
    if src.exists():
        dst = ASSET_DIR / "wanren-education-logo.png"
        shutil.copy2(src, dst)
        print(f"  logo 已就位: {dst}")
    else:
        print(f"  [警告] 找不到 logo: {src}")


def build_one(stem_base: str, fit="portrait", brand=False):
    svgs = []
    for p in collect(stem_base):
        got = load_svg(p)
        if got:
            svgs.append(got)
    if not svgs:
        print(f"  [跳过] {stem_base}：找不到 SVG")
        return None
    OUT.mkdir(exist_ok=True)
    work = OUT / "_work"
    work.mkdir(exist_ok=True)
    html = work / f"{stem_base}.html"
    if brand:
        sch = school_of(stem_base)
        yr = stem_base.split("_")[2] if stem_base.count("_") >= 2 else ""
        code, subj = "", ""
        js = SRC / f"{stem_base}.json"
        if js.exists():
            d = _json.loads(js.read_text(encoding="utf-8"))
            code, subj = str(d.get("科目代码", "")), str(d.get("科目", ""))
            yr = str(d.get("年份") or yr)      # 年份优先取卷级 JSON 字段
        meta = {"院校": sch, "年份": yr, "代码": code, "科目": subj}
        html.write_text(build_html_brand(svgs, meta), encoding="utf-8")
        suffix = "_品牌版"
    else:
        html.write_text(build_html(svgs, fit), encoding="utf-8")
        suffix = {"portrait": "", "landscape": "_A4横",
                  "auto": "_A4混排", "raw": "_自适应"}[fit]
    pdf = PP.target_of(stem_base.replace("_导图", ""), suffix)   # 按院校分文件夹
    pdf.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    if not print_pdf(html, pdf):
        return None
    try:
        from pypdf import PdfReader
        n = len(PdfReader(str(pdf)).pages)
    except Exception:
        n = -1
    print(f"  {pdf.name}  {pdf.stat().st_size/1024/1024:.2f} MB  {n} 页  "
          f"{time.perf_counter()-t0:.1f}s")
    return {"file": pdf.name, "path": pdf, "stem": stem_base, "pages": n,
            "mb": round(pdf.stat().st_size / 1024 / 1024, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="*", help="如 哈尔滨工业大学_2025")
    ap.add_argument("--fit", default="portrait",
                    choices=["portrait", "landscape", "auto", "raw"])
    ap.add_argument("--brand", action="store_true",
                    help="宝典A 同款版式（封面+页眉+页中水印+页脚页码）")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()

    if a.brand:
        print("铺品牌资源…")
        write_assets()

    all_specs = sorted(p.stem.replace("_导图_总览_LR", "")
                       for p in SRC.glob("*_导图_总览_LR.svg"))
    names = a.name or all_specs
    print(f"待生成 {len(names)} 套 → {OUT}")
    rows = []
    for n in names:
        r = build_one(n, a.fit, a.brand)
        if r:
            rows.append(r)
    print(f"\n完成 {len(rows)}/{len(names)}")
    if a.open and rows:
        os.startfile(str(Path(rows[0]["path"]).resolve()))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
