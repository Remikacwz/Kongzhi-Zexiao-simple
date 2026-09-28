# -*- coding: utf-8 -*-
"""重渲前后 · 打印字号对比（从真实 PDF 量，单位=pt 即纸面实际字号）。

对抽样的每套卷，分别量：新 PDF（思维导图_PDF）与 旧 PDF（思维导图_PDF/_备份旧产物）
指标：字符数、字号中位/均值、<4pt 字符占比、页数（抽到的页）。
用法：python _打印字号对比.py [样本数=12] [每份最多页数=8]
"""
import random, statistics, sys
from pathlib import Path
import pdfplumber

HERE = Path(__file__).resolve().parent.parent
NEW = HERE / "思维导图_PDF"
OLD = NEW / "_备份旧产物"
KEY_EXTRA = ["天津大学_812_2020"]


def old_path(stem):
    p = OLD / (stem + "_品牌版.pdf")
    if p.exists():
        return p
    hits = list(OLD.rglob(stem + "_品牌版.pdf"))
    return hits[0] if hits else p


def measure(p, maxpages):
    sizes = []
    nchars_total = 0
    with pdfplumber.open(str(p)) as pdf:
        npages = len(pdf.pages)
        for pg in pdf.pages[:maxpages]:
            try:
                for ch in pg.chars:
                    if ch.get("text", " ").strip():
                        sizes.append(float(ch["size"]))
            except Exception:
                pass
    return sizes, npages


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    maxp = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    stems = sorted(p.name[:-len("_品牌版.pdf")] for p in NEW.glob("*_品牌版.pdf"))
    stems = [s for s in stems if old_path(s).exists()]
    random.seed(20260927)
    sample = random.sample(stems, min(n, len(stems)))
    for k in KEY_EXTRA:
        if k in stems and k not in sample:
            sample.append(k)
    print("样本 %d 套（每份最多量 %d 页）" % (len(sample), maxp))
    print("%-26s %-7s %-7s %-7s %s" % ("key", "旧中位", "新中位", "旧<4pt", "新<4pt"))
    rows = []
    for s in sample:
        so, _ = measure(old_path(s), maxp)
        sn, _ = measure(NEW / (s + "_品牌版.pdf"), maxp)
        if not so or not sn:
            print("  %-26s (无文字，跳过)" % s); continue
        mo, mn = statistics.median(so), statistics.median(sn)
        lo = sum(1 for x in so if x < 4) / len(so)
        ln = sum(1 for x in sn if x < 4) / len(sn)
        rows.append((s, mo, mn, lo, ln))
        print("%-26s %-7.2f %-7.2f %-7.0f%% %.0f%%" % (s, mo, mn, lo * 100, ln * 100))
    if rows:
        print("-" * 66)
        print("中位字号(pt)  旧 %.2f  →  新 %.2f   (提升 %.0f%%)" %
              (statistics.median([r[1] for r in rows]), statistics.median([r[2] for r in rows]),
               100 * (statistics.median([r[2] for r in rows]) / statistics.median([r[1] for r in rows]) - 1)))
        print("<4pt 占比    旧 %.0f%%  →  新 %.0f%%" %
              (100 * statistics.median([r[3] for r in rows]), 100 * statistics.median([r[4] for r in rows])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
