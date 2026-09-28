# -*- coding: utf-8 -*-
"""顶部层级导航：首页 ｜ ← 上一级 ｜ 下一级 →（用户选 A：层级上下）。"""
import io

P = "site_build.py"
t = io.open(P, encoding="utf-8").read()

# ---- 1) 新增 levelnav_html + site_head 增加 level 参数 ----
old = "def site_head(prefix: str, crumbs: list, show_search=True) -> str:"
new = '''def levelnav_html(prefix: str, parent, child) -> str:
    """顶部层级导航：首页 / 上一级 / 下一级。parent、child 为 (href, label) 或 None。"""
    if parent:
        p_html = '<a class="lv" href="%s">← %s</a>' % (parent[0], esc(parent[1]))
    else:
        p_html = '<span class="lv off">← 上一级</span>'
    if child:
        c_html = '<a class="lv" href="%s">%s →</a>' % (child[0], esc(child[1]))
    else:
        c_html = '<span class="lv off">下一级 →</span>'
    return ('<nav class="levelnav" aria-label="层级导航">'
            '<a class="lv home" href="%s">首页</a>%s%s</nav>' % (prefix, p_html, c_html))


def site_head(prefix: str, crumbs: list, show_search=True, level: str = "") -> str:'''
assert t.count(old) == 1, "def"
t = t.replace(old, new)

# ---- 2) 顶栏模板插入 level 位 ----
old = """            '%s'
            '<nav class="crumbs">%s</nav>'
            '%s'
            '</div></header>') % (ph, prefix, prefix, s_btn, "".join(c), s_inp)"""
new = """            '%s'
            '<nav class="crumbs">%s</nav>'
            '%s'
            '%s'
            '</div></header>') % (ph, prefix, prefix, s_btn, "".join(c), level, s_inp)"""
assert t.count(old) == 1, "tpl"
t = t.replace(old, new)

# ---- 3) 六个页面类型各自传入 level ----
# 3.1 首页
old = '''    body = [site_head("", [("首页", None)])]'''
new = '''    body = [site_head("", [("首页", None)],
                      level=levelnav_html("", None, ("x/985/", "985 院校")))]'''
assert t.count(old) == 1, "home"
t = t.replace(old, new)

# 3.2 分级页
old = '''        body = [site_head(prefix, [("首页", prefix), (TIER_NAME[t], None)])]'''
new = '''        _first = sorted(ss, key=slug_of)[0]
        body = [site_head(prefix, [("首页", prefix), (TIER_NAME[t], None)],
                          level=levelnav_html(prefix, (prefix, "首页"),
                                              (prefix + "x/%s/%s/" % (TIER_SLUG[t], slug_of(_first)),
                                               "第一所院校")))]'''
assert t.count(old) == 1, "tier"
t = t.replace(old, new)

# 3.3 学校页
old = '''        body = [site_head(prefix, [("首页", prefix),
                                   (TIER_NAME[t], prefix + "x/%s/" % TIER_SLUG[t]),
                                   (school, None)])]'''
new = '''        _new = items[-1]
        body = [site_head(prefix, [("首页", prefix),
                                   (TIER_NAME[t], prefix + "x/%s/" % TIER_SLUG[t]),
                                   (school, None)],
                          level=levelnav_html(prefix,
                                              (prefix + "x/%s/" % TIER_SLUG[t], TIER_NAME[t]),
                                              (prefix + "%s/%s/" % (_new["year"], _new["code"]),
                                               "最新年份")))]'''
assert t.count(old) == 1, "school"
t = t.replace(old, new)

# 3.4 卷页
old = '''                                 (_ylab, None)])]'''
new = '''                                 (_ylab, None)],
                          level=levelnav_html(pre,
                                              (pre + "x/%s/%s/" % (TIER_SLUG[s["tier"]], s["slug"]),
                                               s["school"]),
                                              ("#q1", "第 1 题")))]'''
assert t.count(old) == 1, "setpage"
t = t.replace(old, new)

# 3.5 考点索引
old = '''    body = [site_head(pre_k, [("首页", pre_k), ("考点索引", None)])]'''
new = '''    _first_kp = sorted(refs, key=lambda r: (-kp_nsets[r], r))[0]
    body = [site_head(pre_k, [("首页", pre_k), ("考点索引", None)],
                      level=levelnav_html(pre_k, (pre_k, "首页"),
                                          (pre_k + _first_kp + "/", "第一个考点")))]'''
assert t.count(old) == 1, "kpindex"
t = t.replace(old, new)

# 3.6 考点页
old = '''        body = [site_head(prefix,  [("首页", prefix), ("考点索引", prefix + "k/"), (name, None)])]'''
new = '''        body = [site_head(prefix,  [("首页", prefix), ("考点索引", prefix + "k/"), (name, None)],
                          level=levelnav_html(prefix, (prefix + "k/", "考点索引"), None))]'''
assert t.count(old) == 1, "kppage"
t = t.replace(old, new)

io.open(P, "w", encoding="utf-8").write(t)
print("site_build.py：层级导航已接入 6 类页面")
