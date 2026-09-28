# -*- coding: utf-8 -*-
"""给站点加全文搜索（本地开发版）。

① 生成 assets/search.js：按卷一条索引 {k:key, p:路径, s:院校, t:层级, y:年份, c:代码, kp:[考点名…], x:可搜文本}
   另附 window.KG_KPNAME = {考点名: ref}（供考点结果直接跳考点页）
② 首页/分级页：搜索框下加命中面板（考点 + 卷/题），由 kg.js 渲染
③ 关闭（清空搜索）时面板收起、卡片回到全量
"""
import io

P = "site_build.py"
t = io.open(P, encoding="utf-8").read()

# ---------- ① 生成搜索索引 ----------
anchor = '''    # ---- 旧路径兼容页：x/<tier>/<school>/<year>/ → <code>/（§211 改路径后防老链接 404）'''
add = '''    # ---- 搜索索引：assets/search.js（按卷一条；含考点名与可搜文本）
    idx = []
    for s in sets:
        kpnames = []
        for q in s["qs"]:
            for kp in q["考点"]:
                nm = kp.get("名称") or (kp_lib.get(kp.get("ref") or "") or {}).get("名称", "")
                if nm:
                    kpnames.append(nm)
        parts = [s["school"], s["code"], s["subject"], s["year"]]
        for q in s["qs"]:
            parts.append(str(q.get("名称") or ""))
            parts.append(str(q.get("tab") or ""))
            for x in (q.get("思路") or []):
                parts.append(str(x))
            parts += [str(kp.get("名称") or "") for kp in q["考点"]]
        idx.append({"k": s["key"],
                    "p": "x/%s/%s/%s/%s/" % (TIER_SLUG[s["tier"]], s["slug"], s["year"], s["code"]),
                    "s": s["school"], "t": s["tier"], "y": s["year"], "c": s["code"],
                    "kp": sorted(set(kpnames)), "x": " ".join(p for p in parts if p)[:700]})
    kpmap = {}
    for r in refs:
        nm = (kp_lib.get(r) or {}).get("名称")
        if nm:
            kpmap[nm] = r
    (out / "assets" / "search.js").write_text(
        "window.KG_SEARCH=" + json.dumps(idx, ensure_ascii=False, separators=(",", ":"))
        + ";window.KG_KPNAME=" + json.dumps(kpmap, ensure_ascii=False, separators=(",", ":")) + ";",
        encoding="utf-8")
    print("搜索索引 1 个（%d 套 / %d 考点，%.0f KB）"
          % (len(idx), len(kpmap), (out / "assets" / "search.js").stat().st_size / 1024))

'''
assert t.count(anchor) == 1, "anchor"
t = t.replace(anchor, add + anchor)

# ---------- ② 首页/分级页：搜索框后加命中面板 ----------
old = """                    '<input id="site-q" type="search" placeholder="搜学校 / 年份 / 代码">'"""
new = """                    '<input id="site-q" type="search" placeholder="搜学校 / 代码 / 年份 / 考点">'"""
assert t.count(old) == 1, "input"
t = t.replace(old, new)

old2 = """        body.append('<p class="muted tiny" id="kg-empty" hidden>没有匹配的院校，换个关键词试试。</p></section>'"""
new2 = """        body.append('<p class="muted tiny" id="kg-empty" hidden>没有匹配的院校，换个关键词试试。</p>'
                    '<div id="kg-hits" class="hits" hidden></div></section>'"""
assert t.count(old2) == 1, "hits-home"
t = t.replace(old2, new2)

old3 = """                    '<p class="muted tiny" id="kg-empty" hidden>没有匹配的院校。</p></section>'"""
new3 = """                    '<p class="muted tiny" id="kg-empty" hidden>没有匹配的院校。</p>'
                    '<div id="kg-hits" class="hits" hidden></div></section>'"""
assert t.count(old3) == 1, "hits-tier"
t = t.replace(old3, new3)

io.open(P, "w", encoding="utf-8").write(t)
print("site_build.py：搜索索引 + 命中面板容器 已加")
