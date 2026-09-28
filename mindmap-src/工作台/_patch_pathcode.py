# -*- coding: utf-8 -*-
"""修 bug：卷页路径未含专业课代码 → 同校同年两个代码互相覆盖（39 组 78 套只剩 39 页）。

新路径：x/<分级>/<学校slug>/<年份>/<代码>/
涉及：卷页输出目录、面包屑前缀深度、同校其它年份、上一套/下一套、学校页年份卡、
      嵌入清单 sets.js、sitemap、考点页里指向卷页的链接。
"""
import io

P = "site_build.py"
t = io.open(P, encoding="utf-8").read()

# ---------- 1) 卷页循环：深度 4 → 5，并按（年份, 代码）排序取前后 ----------
old = '''        p = 4                                     # x/tier/school/year
        pre = up(p)
        ylist = [x["year"] for x in by_school[s["school"]]]
        idx = ylist.index(s["year"])
        prev_s = by_school[s["school"]][idx - 1] if idx > 0 else None
        next_s = by_school[s["school"]][idx + 1] if idx + 1 < len(by_school[s["school"]]) else None'''
new = '''        p = 5                                     # x/tier/school/year/code
        pre = up(p)
        sibs = sorted(by_school[s["school"]], key=lambda x: (x["year"], x["code"]))
        idx = sibs.index(s)
        prev_s = sibs[idx - 1] if idx > 0 else None
        next_s = sibs[idx + 1] if idx + 1 < len(sibs) else None'''
assert t.count(old) == 1, "p5"
t = t.replace(old, new)

# ---------- 2) 同校其它年份：带上代码（同校同年多代码时必须区分） ----------
old = '''                sidelen.append('<a class="yearchip" href="../%s/">%s <span class="n">%d题</span></a>'
                               % (o["year"], esc(o["year"]), len(o["qs"])))'''
new = '''                lab = o["year"] if o["code"] == s["code"] else "%s·%s" % (o["year"], o["code"])
                sidelen.append('<a class="yearchip" href="../../%s/%s/">%s <span class="n">%d题</span></a>'
                               % (o["year"], o["code"], esc(lab), len(o["qs"])))'''
assert t.count(old) == 1, "sidelen"
t = t.replace(old, new)

# ---------- 3) 上一套 / 下一套：路径带代码 ----------
old = '''        if prev_s:
            nav.append('<a class="yearchip" href="../%s/">← %s</a>' % (prev_s["year"], prev_s["year"]))
        if next_s:
            nav.append('<a class="yearchip" href="../%s/">%s →</a>' % (next_s["year"], next_s["year"]))'''
new = '''        def _lab(o):
            return "%s·%s" % (o["year"], o["code"]) if o["code"] != s["code"] else o["year"]
        if prev_s:
            nav.append('<a class="yearchip" href="../../%s/%s/">← %s</a>'
                       % (prev_s["year"], prev_s["code"], esc(_lab(prev_s))))
        if next_s:
            nav.append('<a class="yearchip" href="../../%s/%s/">%s →</a>'
                       % (next_s["year"], next_s["code"], esc(_lab(next_s))))'''
assert t.count(old) == 1, "prevnext"
t = t.replace(old, new)

# ---------- 4) 卷页输出目录 ----------
old = '''        d = out / "x" / TIER_SLUG[s["tier"]] / s["slug"] / s["year"]'''
new = '''        d = out / "x" / TIER_SLUG[s["tier"]] / s["slug"] / s["year"] / s["code"]'''
assert t.count(old) == 1, "outdir"
t = t.replace(old, new)

# ---------- 5) 嵌入清单 ----------
old = '''    man = {s["key"]: "x/%s/%s/%s/" % (TIER_SLUG[s["tier"]], s["slug"], s["year"]) for s in sets}'''
new = '''    man = {s["key"]: "x/%s/%s/%s/%s/" % (TIER_SLUG[s["tier"]], s["slug"], s["year"], s["code"])
           for s in sets}'''
assert t.count(old) == 1, "manifest"
t = t.replace(old, new)

# ---------- 6) 学校页年份卡：两段路径 + 标出代码 ----------
old = '''        rows = "".join(
            '<div class="scard" data-k="%s" data-sets="1"><a class="scard-link" href="%s/">'
            '<span class="scard-top"><b>%s 年</b></span>'
            '<div class="sm">%s %s · %d 题</div></a></div>'
            % (esc(o["year"]), o["year"], esc(o["year"]), esc(o["code"]), esc(o["subject"]), len(o["qs"]))
            for o in items)'''
new = '''        multi = len({o["code"] for o in items}) > 1
        rows = "".join(
            '<div class="scard" data-k="%s" data-sets="1"><a class="scard-link" href="%s/%s/">'
            '<span class="scard-top"><b>%s 年%s</b></span>'
            '<div class="sm">%s %s · %d 题</div></a></div>'
            % (esc(o["year"]), o["year"], o["code"], esc(o["year"]),
               esc("　" + o["code"]) if multi else "", esc(o["code"]), esc(o["subject"]), len(o["qs"]))
            for o in items)'''
assert t.count(old) == 1, "schoolrows"
t = t.replace(old, new)

# ---------- 7) 考点页 → 卷页链接 ----------
old = '''    def url_of_set(rec):
        return "/x/%s/%s/%s/" % (TIER_SLUG[rec["tier"]], rec["schoolSlug"], rec["year"])'''
new = '''    def url_of_set(rec):
        return "/x/%s/%s/%s/%s/" % (TIER_SLUG[rec["tier"]], rec["schoolSlug"], rec["year"], rec["code"])'''
assert t.count(old) == 1, "kpseturl"
t = t.replace(old, new)

# ---------- 8) sitemap ----------
old = '''        urls += ["%s/x/%s/%s/%s/" % (base, TIER_SLUG[s["tier"]], s["slug"], s["year"]) for s in sets]'''
new = '''        urls += ["%s/x/%s/%s/%s/%s/" % (base, TIER_SLUG[s["tier"]], s["slug"], s["year"], s["code"])
                 for s in sets]'''
assert t.count(old) == 1, "sitemap"
t = t.replace(old, new)

io.open(P, "w", encoding="utf-8").write(t)
print("已把专业课代码纳入卷页路径（8 处）")
