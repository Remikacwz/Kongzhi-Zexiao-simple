# -*- coding: utf-8 -*-
"""补丁：① 首页/分级页加「考点」筛选维度 ② 新增 /k/ 考点索引页 ③ 考点页去掉编号代号。

① 卡片加 data-kps（该校出现过的考点 ref 集合）；筛选器加「考点」下拉（名称+套数）。
② /k/index.html：按大类分组列出全部考点（出现套数 / 覆盖院校），入口从首页筛选行与考点页可达。
③ 考点页此前显示 `rl_02` 这类内部编号（badge + 一行小字）→ 去掉，编号只留在 URL 与 JSON-LD。
"""
import io

P = "site_build.py"
t = io.open(P, encoding="utf-8").read()

# ---------- ①-1 卡片加 data-kps ----------
old = '''        return ('<div class="scard" data-k="%s" data-tier="%s" data-sets="%d" data-codes="%s">'
                '<a class="scard-link" href="%sx/%s/%s/">'
                '<span class="scard-top">%s<b>%s</b></span>'
                '<div class="sm">%s · %d 套 · %s–%s</div></a>'
                '<div class="years">%s</div></div>'
                % (esc(key), esc(t), len(items), esc(",".join(codes)), pre, TIER_SLUG[t], sl,
                   badge, esc(school), esc(TIER_NAME[t]),
                   len(items), esc(min(o["year"] for o in items)), esc(max(o["year"] for o in items)), yrs))'''
new = '''        kps = sorted({kp["ref"] for o in items for q in o["qs"] for kp in q["考点"] if kp.get("ref")})
        return ('<div class="scard" data-k="%s" data-tier="%s" data-sets="%d" data-codes="%s" data-kps="%s">'
                '<a class="scard-link" href="%sx/%s/%s/">'
                '<span class="scard-top">%s<b>%s</b></span>'
                '<div class="sm">%s · %d 套 · %s–%s</div></a>'
                '<div class="years">%s</div></div>'
                % (esc(key), esc(t), len(items), esc(",".join(codes)), esc(",".join(kps)),
                   pre, TIER_SLUG[t], sl,
                   badge, esc(school), esc(TIER_NAME[t]),
                   len(items), esc(min(o["year"] for o in items)), esc(max(o["year"] for o in items)), yrs))'''
assert t.count(old) == 1, "card-data"
t = t.replace(old, new)

# ---------- ①-2 筛选器加「考点」下拉 ----------
old = '''        rows.append('<div class="frow"><span class="flab">代码</span>'
                    '<select id="kg-code"><option value="">全部代码</option>%s</select>'
                    '<span class="flab">排序</span>'
                    '<select id="kg-sort"><option value="tier">按层级</option>'
                    '<option value="name">按校名</option><option value="count">按套数</option></select>'
                    '<input id="site-q" type="search" placeholder="搜学校 / 代码 / 年份">'
                    '<button class="btn" id="kg-clear">清除筛选</button></div>' % opts)'''
new = '''        rows.append('<div class="frow"><span class="flab">代码</span>'
                    '<select id="kg-code"><option value="">全部代码</option>%s</select>'
                    '<span class="flab">排序</span>'
                    '<select id="kg-sort"><option value="tier">按层级</option>'
                    '<option value="name">按校名</option><option value="count">按套数</option></select>'
                    '<input id="site-q" type="search" placeholder="搜学校 / 代码 / 年份">'
                    '<button class="btn" id="kg-clear">清除筛选</button></div>' % opts)
        # 考点维度：按"出现套数"倒序列出，选中后只留考过该考点的院校
        kpc = collections.Counter()
        for s in scope:
            for q in s["qs"]:
                for kp in q["考点"]:
                    if kp.get("ref"):
                        kpc[kp["ref"]] += 1
        kopts = "".join('<option value="%s">%s（%d 套）</option>'
                        % (esc(r), esc((kp_lib.get(r) or {}).get("名称", r)), n)
                        for r, n in sorted(kpc.items(), key=lambda kv: (-kv[1], kv[0])))
        rows.append('<div class="frow"><span class="flab">考点</span>'
                    '<select id="kg-kp"><option value="">全部考点</option>%s</select>'
                    '<a class="fmore" href="%sk/">浏览考点索引 →</a></div>' % (kopts, up(0)))'''
assert t.count(old) == 1, "filter-kp"
t = t.replace(old, new)

# ---------- ② 新增 /k/ 考点索引页（放在考点页循环之前） ----------
anchor = '''    n_kp = 0
    for rid, recs in refs.items():'''
add = '''    # ---- 考点索引（/k/）：按大类分组，供"考点维度"浏览 ----
    kp_nsets, kp_nsch = {}, {}
    for rid, recs in refs.items():
        kp_nsets[rid] = len({r["key"] for r in recs})
        kp_nsch[rid] = len({r["school"] for r in recs})
    by_cat = {}
    for rid in refs:
        by_cat.setdefault((kp_lib.get(rid) or {}).get("_大类", "其他"), []).append(rid)
    pre_k = up(2)
    cards = []
    for cat in sorted(by_cat, key=lambda c: -len(by_cat[c])):
        items_html = []
        for rid in sorted(by_cat[cat], key=lambda r: (-kp_nsets[r], r)):
            nm = (kp_lib.get(rid) or {}).get("名称", rid)
            items_html.append('<a class="kcard" href="%s%s/">'
                              '<b>%s</b><span>%d 套 · %d 校</span></a>'
                              % (pre_k, rid, esc(nm), kp_nsets[rid], kp_nsch[rid]))
        cards.append('<div class="kg-board"><header class="kg-board__head"><div>'
                     '<span class="kg-board__index">%d 个考点</span><h2>%s</h2></div></header>'
                     '<div class="kgrid">%s</div></div>' % (len(by_cat[cat]), esc(cat), "".join(items_html)))
    body = [site_head(pre_k, [("首页", pre_k), ("考点索引", None)])]
    body.append('<main class="wrap">')
    body.append(hero_html("01", "考点维度", "考点索引",
                          "按考点看真题：点任意考点，可看到它历年在哪些学校、哪一年、哪道题考过，'
                          '以及该考点的要点 / 步骤 / 公式 / 考法 / 易错。",
                          [("考点", len(refs)), ("大类", len(by_cat)), ("套卷", len(sets))], guidance))
    body.append("".join(cards))
    body.append("</main>")
    body.append(site_foot(pre_k))
    d = out / "k"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(page_shell(
        "考点索引 · 控制考研真题思维导图（%d 个考点）" % len(refs),
        "控制类考研 %d 个考点历年考法索引：每个考点覆盖的套数与院校数，可按考点反查真题。"
        % len(refs),
        pre_k, "\\n".join(body),
        canonical=(site.rstrip("/") + "/k/") if site else "", cls="page-index"),
        encoding="utf-8")
    print("考点索引页 1 个（%d 个考点 / %d 个大类）" % (len(refs), len(by_cat)))

    n_kp = 0
    for rid, recs in refs.items():'''
assert t.count(anchor) == 1, "kp-index"
t = t.replace(anchor, add)

# ---------- ③ 考点页去掉编号代号 ----------
old = '''        body.append('<main class="wrap"><div class="kphead"><h1>%s</h1>'
                    '<div class="tagrow"><span class="badge">%s</span>'
                    '<span class="badge">%s</span>'
                    '<span class="badge">%d 套卷出现</span><span class="badge">%d 所院校</span>'
                    '<span class="badge">%s–%s</span></div></div>'
                    '<p class="tiny muted rid" style="margin:6px 0 0">%s</p>'
                    % (esc(name), esc(info.get("_大类", "")), esc(rid), n_sets, len(schools),
                       esc(min(yrs)), esc(max(yrs)), esc(rid)))'''
new = '''        body.append('<main class="wrap"><div class="kphead"><h1>%s</h1>'
                    '<div class="tagrow"><span class="badge">%s</span>'
                    '<span class="badge">%d 套卷出现</span><span class="badge">%d 所院校</span>'
                    '<span class="badge">%s–%s</span></div></div>'
                    % (esc(name), esc(info.get("_大类", "")), n_sets, len(schools),
                       esc(min(yrs)), esc(max(yrs))))'''
assert t.count(old) == 1, "kp-page-rid"
t = t.replace(old, new)

# 考点页面包屑里的“考点”改成指向考点索引
old = '''        body = [site_head(prefix,  [("首页", prefix), ("考点", None), (name, None)])]'''
new = '''        body = [site_head(prefix,  [("首页", prefix), ("考点索引", prefix + "k/"), (name, None)])]'''
assert t.count(old) == 1, "crumb"
t = t.replace(old, new)

io.open(P, "w", encoding="utf-8").write(t)
print("site_build.py 补丁完成：考点筛选 + 考点索引页 + 考点页去编号")
