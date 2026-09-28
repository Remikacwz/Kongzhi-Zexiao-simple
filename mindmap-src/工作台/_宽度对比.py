# -*- coding: utf-8 -*-
"""重渲前后对比：总览 SVG 的版面宽度/高度，以及该套 SVG 文件总字节数。

旧产物在 思维导图_v6/_备份旧产物/（重渲时被移入）。
用法：python _宽度对比.py [样本数，默认 60]
"""
import re, random, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
V6 = HERE / "思维导图_v6"
BAK = V6 / "_备份旧产物"
WSZ = re.compile(rb'\bwidth="([\d.]+)pt"')
HSZ = re.compile(rb'\bheight="([\d.]+)pt"')


def root_size(p):
    if not p.exists():
        return None
    with p.open("rb") as f:
        head = f.read(4096)
    w = WSZ.search(head); h = HSZ.search(head)
    if not w:
        return None
    return (float(w.group(1)), float(h.group(1)) if h else float("nan"))


def bak_path(key, name):
    p = BAK / name
    if p.exists():
        return p
    hits = list(BAK.rglob(name))
    return hits[0] if hits else p


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    keys = sorted(p.stem for p in V6.glob("*.json"))
    keys = [k for k in keys if bak_path(k, k + "_导图_总览_LR.svg").exists()]
    random.seed(20260927)
    sample = random.sample(keys, min(n, len(keys)))
    rows = []
    for k in sample:
        new = root_size(V6 / (k + "_导图_总览_LR.svg"))
        old = root_size(bak_path(k, k + "_导图_总览_LR.svg"))
        if not new or not old:
            continue
        rows.append((k, old[0], new[0], old[1], new[1]))
    if not rows:
        print("无可比样本"); return 1
    ow = [r[1] for r in rows]; nw = [r[2] for r in rows]
    oh = [r[3] for r in rows]; nh = [r[4] for r in rows]
    print("可比样本 %d 套" % len(rows))
    print("总览宽度 pt  旧: 中位 %.0f  均值 %.0f   新: 中位 %.0f  均值 %.0f" %
          (statistics.median(ow), statistics.mean(ow), statistics.median(nw), statistics.mean(nw)))
    print("总览高度 pt  旧: 中位 %.0f  新: 中位 %.0f" % (statistics.median(oh), statistics.median(nh)))
    rat = [r[2] / r[1] for r in rows]
    print("宽度比(新/旧) 中位 %.3f  均值 %.3f  变窄套数 %d/%d" %
          (statistics.median(rat), statistics.mean(rat), sum(1 for x in rat if x < 0.99), len(rat)))
    rows.sort(key=lambda r: r[2] / r[1])
    print("最窄 5:")
    for k, a, b, _, _ in rows[:5]:
        print("   %-26s %.0f -> %.0f pt (%.2f)" % (k, a, b, b / a))
    print("最宽 5:")
    for k, a, b, _, _ in reversed(rows[-5:]):
        print("   %-26s %.0f -> %.0f pt (%.2f)" % (k, a, b, b / a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
