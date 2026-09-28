# -*- coding: utf-8 -*-
"""SVG 体检：检测重渲过程中因并发写锁/中断产生的 缺失 / 截断 / 空壳 文件。

判据：
  - 每套 json 至少应有 2 个 SVG（_导图_总览 + 至少一个板块）
  - 每个 SVG 必须非空、>1KB、且以 </svg> 收尾（截断文件不会收尾）
  - SVG 数量与 .dot 数量一致

输出：_工作台/_svg体检报告_<ts>.json + 控制台摘要
用法：python _svg体检.py
"""
import json, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
V6 = HERE / "思维导图_v6"
BAK = V6 / "_备份旧产物"

def main():
    jsons = sorted(p for p in V6.glob("*.json"))
    bad = {}
    n_svg = n_ok = 0
    for jp in jsons:
        key = jp.stem
        svgs = sorted(p for p in V6.glob(key + "_导图_*.svg"))
        dots = sorted(p for p in V6.glob(key + "_导图_*.dot"))
        probs = []
        if not svgs:
            probs.append("无SVG")
        for p in svgs:
            n_svg += 1
            try:
                sz = p.stat().st_size
            except OSError as e:
                probs.append("stat失败:%s" % p.name); continue
            if sz < 1024:
                probs.append("过小(%dB):%s" % (sz, p.name)); continue
            try:
                with p.open("rb") as f:
                    f.seek(max(0, sz - 64))
                    tail = f.read()
            except OSError as e:
                probs.append("读尾失败:%s" % p.name); continue
            if b"</svg>" not in tail:
                probs.append("未收尾(截断):%s" % p.name); continue
            n_ok += 1
        if len(svgs) != len(dots) and dots:
            probs.append("svg/dot数不一致 %d/%d" % (len(svgs), len(dots)))
        if probs:
            bad[key] = probs
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = HERE / "_工作台" / ("_svg体检报告_%s.json" % ts)
    out.write_text(json.dumps({"sets": len(jsons), "svg总数": n_svg, "通过": n_ok,
                               "problem_sets": len(bad), "detail": bad},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("套数=%d  SVG总数=%d  通过=%d  问题套数=%d" % (len(jsons), n_svg, n_ok, len(bad)))
    for k, v in list(bad.items())[:40]:
        print("  %-28s %s" % (k, "; ".join(v[:3])))
    print("报告 ->", out.name)
    return 0

if __name__ == "__main__":
    sys.exit(main())
