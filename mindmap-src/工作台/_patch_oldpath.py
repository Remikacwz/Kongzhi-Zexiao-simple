# -*- coding: utf-8 -*-
"""补旧路径兼容页：x/<分级>/<学校>/<年份>/ → 跳转到 /<代码>/（多代码时给选择页）。

背景：§211 把卷页路径从 `x/tier/school/year/` 改成 `x/tier/school/year/code/`，
老链接（书签/已分享的标签页）会 404。这里为所有「校+年」组合生成兼容页：
  - 该年只有 1 个专业课 → meta refresh 0 秒跳转到 <code>/，并带 canonical 与手动链接兜底；
  - 该年有 2 个专业课 → 给一个选择页（列出两个代码与科目名）。
兼容页不进 sitemap（它们不是内容页）。
"""
import io

P = "site_build.py"
t = io.open(P, encoding="utf-8").read()

anchor = '''    # ---- 嵌入用清单：key → 页面路径（kg-embed.js 用，避免前端猜 slug）'''
add = '''    # ---- 旧路径兼容页：x/<tier>/<school>/<year>/ → <code>/（§211 改路径后防老链接 404）
    ygroups = collections.defaultdict(list)
    for s in sets:
        ygroups[(TIER_SLUG[s["tier"]], s["slug"], s["year"])].append(s)
    n_stub = 0
    for (_ts, _sl, _yr), g in ygroups.items():
        pre4 = up(4)
        d = out / "x" / _ts / _sl / _yr
        d.mkdir(parents=True, exist_ok=True)
        if len(g) == 1:
            code = g[0]["code"]
            page = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                    '<meta http-equiv="refresh" content="0;url=%s/">'
                    '<link rel="canonical" href="%s/">'
                    '<title>%s %s 年真题思维导图</title>'
                    '<link rel="stylesheet" href="%sassets/kg.css"></head><body>'
                    '<main class="wrap"><section class="kg-board"><div class="fres">'
                    '正在前往 %s %s 年（%s）真题思维导图…　若未自动跳转，请点 '
                    '<a href="%s/">这里</a>。</div></section></main></body></html>'
                    % (code, code, esc(g[0]["school"]), _yr, pre4,
                       esc(g[0]["school"]), _yr, esc(code), code))
        else:
            opts = "".join(
                '<a class="scard" href="%s/"><span class="scard-top"><b>%s 年 %s</b></span>'
                '<div class="sm">%s · %d 题</div></a>'
                % (o["code"], _yr, esc(o["code"]), esc(o["subject"]), len(o["qs"]))
                for o in sorted(g, key=lambda x: x["code"]))
            page = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width, initial-scale=1">'
                    '<title>%s %s 年 · 选择专业课</title>'
                    '<link rel="stylesheet" href="%sassets/kg.css"></head><body>'
                    '<main class="wrap"><section class="kg-board">'
                    '<header class="kg-board__head"><div><span class="kg-board__index">CHOOSE</span>'
                    '<h2>%s %s 年</h2><p>该校该年有 %d 个专业课，请选择：</p></div></header>'
                    '<div class="grid" style="margin-top:20px">%s</div></section></main></body></html>'
                    % (esc(g[0]["school"]), _yr, pre4, esc(g[0]["school"]), _yr, len(g), opts))
        (d / "index.html").write_text(page, encoding="utf-8")
        n_stub += 1
    print("旧路径兼容页 %d 个（单代码跳转 / 多代码选择）" % n_stub)

'''
assert t.count(anchor) == 1, "anchor"
io.open(P, "w", encoding="utf-8").write(t.replace(anchor, add + anchor))
print("兼容页生成逻辑已加入 site_build.py")
