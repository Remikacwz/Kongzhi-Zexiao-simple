#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""派活前必跑：按「院校线」输出接下来可派的真实待做 key（每个 agent 最多 3 套）。

存在意义（§61/§77 两次事故）：我曾两次凭"同校已有某年 key"**推测**出并不存在的 key 派给 agent，
agent 白跑（幸好它们都拒绝臆造并上报）。
根因是「**需要 N 个 key 但真 key 不够，就推测补齐**」。
→ 本脚本只从 sources.json 的真实待做清单里取；**取不够就返回少的，绝不推测**。

用法：
  py -3.12 nextkeys.py            # 输出 6 条院校线（供 6 个 agent）
  py -3.12 nextkeys.py 6 2021-2024   # 输出 6 条院校线（限定年份段）
"""
from __future__ import annotations
import json, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
src = json.loads((HERE / "_工作台" / "sources.json").read_text(encoding="utf-8"))
alias = json.loads((HERE / "_工作台" / "重卷映射.json").read_text(encoding="utf-8"))["别名到正卷"]
done = {p.stem for p in (HERE / "思维导图_v6").glob("*.json")}

n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
rng = sys.argv[2] if len(sys.argv) > 2 else None      # 形如 2021-2024；不给则不限年份
y0, y1 = (int(x) for x in rng.split("-")) if rng else (0, 9999)
# ★ 还要排除「正在制」的 key：否则会把刚派出去的又派一遍（§22 同 key 双派风险）
inflight_f = HERE / "_工作台" / "_在制.txt"
inflight = {ln.strip() for ln in inflight_f.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")} if inflight_f.exists() else set()
pend = [k for k in src
        if k not in alias and k not in done and k not in inflight
        and y0 <= int(k.rsplit("_", 1)[1]) <= y1]
bysch: dict[str, list[str]] = defaultdict(list)
for k in pend:
    bysch[k.rsplit("_", 2)[0]].append(k)
# 按年份早的、院校内年份多的优先（一条线尽量同年份段连做）
lines = sorted(bysch.items(), key=lambda x: (min(k.rsplit("_", 1)[1] for k in x[1]), -len(x[1])))
print(f"待做 {len(pend)} 套 / {len(bysch)} 所院校（已排除别名、已产出、在制 {len(inflight)} 套）；下面给出 {n} 条院校线（每条最多 3 套，**全部真实存在**）：")
for s, ks in lines[:n]:
    take = sorted(ks, key=lambda k: k.rsplit("_", 1)[1])[:3]
    print(f"{s}|" + "、".join(take))
print("\n★ 派活直接把上面每行的 key 抄进提示词；**不要凭同校其他年份推测 key**。")
