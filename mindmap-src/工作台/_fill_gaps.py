# -*- coding: utf-8 -*-
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from _gap_data import GAPS

ROOT = "思维导图_v6"

def flat_inst(d):
    out = []
    for bi, b in enumerate(d["板块"]):
        for ci, c in enumerate(b["考点"]):
            if "本卷实例" in c:
                out.append((bi, ci))
    return out

def find_occurrences(t):
    pos = []
    start = 0
    while True:
        i = t.find('"本卷实例"', start)
        if i < 0:
            break
        pos.append(i)
        start = i + 1
    return pos

def brace_after_key(t, key_pos):
    j = t.find('{', key_pos)
    assert j > 0, "no brace"
    return j

def line_indent(t, pos):
    ls = t.rfind("\n", 0, pos) + 1
    k = ls
    while t[k] == " ":
        k += 1
    return t[ls:k]

def apply(key):
    path = f"{ROOT}/{key}.json"
    t = open(path, encoding="utf-8").read()
    d = json.loads(t)
    flat = flat_inst(d)
    occ = find_occurrences(t)
    assert len(flat) == len(occ), (key, len(flat), len(occ))
    idx = {fc: n for n, fc in enumerate(flat)}
    # 校验目标
    for bi, ci, field, vals in GAPS[key]:
        ins = d["板块"][bi]["考点"][ci]["本卷实例"]
        assert field not in ins, (key, bi, ci, field, "已存在")
        for f in vals:
            assert len(f) <= 45, (key, field, len(f), f)
    # 按 occurrence 聚合
    by_occ = {}
    for bi, ci, field, vals in GAPS[key]:
        n = idx[(bi, ci)]
        by_occ.setdefault(n, []).append((field, vals))
    edits = []  # (pos_after_brace, text)
    for n, fields in by_occ.items():
        key_pos = occ[n]
        bp = brace_after_key(t, key_pos)
        ind = line_indent(t, key_pos) + "  "
        parts = []
        for field, vals in fields:
            parts.append("\n" + ind + '"' + field + '": ' +
                         json.dumps(vals, ensure_ascii=False) + ",")
        edits.append((bp + 1, "".join(parts)))
    # 从后往前插，避免位移
    for pos, txt in sorted(edits, key=lambda x: -x[0]):
        t = t[:pos] + txt + t[pos:]
    # 校验
    d2 = json.loads(t)
    for bi, ci, field, vals in GAPS[key]:
        got = d2["板块"][bi]["考点"][ci]["本卷实例"].get(field)
        assert got == vals, (key, bi, ci, field, got)
    open(path, "w", encoding="utf-8", newline="").write(t)
    print("OK", key, "补", sum(len(v[3]) for v in GAPS[key]), "条内容 /",
          len(GAPS[key]), "个字段")

if __name__ == "__main__":
    for k in GAPS:
        apply(k)
