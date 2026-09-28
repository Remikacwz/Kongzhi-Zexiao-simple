# -*- coding: utf-8 -*-
"""给 site_build.py 打补丁：学校栏配校徽。

素材：D:\\ZeXiao\\专业课选择\\images\\校徽\\<校名>.jpg（245 张，200×200）
做法：按校名匹配（精确 → 去校区后缀 → 去括号）后压成 72×72 JPEG，按 slug 放进 assets/logo/，
      在 首页/分级页学校卡、学校页标题、卷页标题 上显示。
"""
import io, re, sys

P = "site_build.py"
t = io.open(P, encoding="utf-8").read()

# 1) 常量 + 匹配函数
anchor = 'PARENT_HOME = ""          # 父站首页链接（嵌入已有站点时设置，见 --parent）'
add = anchor + '''
LOGO_SRC = Path(r"D:\\ZeXiao\\专业课选择\\images\\校徽")


def find_logo(school: str):
    """按校名找校徽（精确 → 去校区后缀 → 去括号）。找不到返回 None。"""
    if not LOGO_SRC.is_dir():
        return None
    for cand in (school, wb._base(school), re.sub(r"[（(].*?[）)]", "", school).strip()):
        p = LOGO_SRC / (str(cand) + ".jpg")
        if p.is_file():
            return p
    return None'''
assert t.count(anchor) == 1
t = t.replace(anchor, add)

# 2) 生成校徽资源
anchor2 = '''    if (INT_ASSETS / "katex").exists():'''
add2 = '''    # 校徽：裁成 72×72，按 slug 命名（ASCII 路径，避免中文 URL）
    logo_dst = out / "assets" / "logo"
    logo_dst.mkdir(parents=True, exist_ok=True)
    n_logo = 0
    for _sc in by_school:
        src = find_logo(_sc)
        if not src:
            continue
        dst = logo_dst / (slug_of(_sc) + ".jpg")
        if not dst.exists():
            try:
                from PIL import Image
                with Image.open(src) as im:
                    im.convert("RGB").resize((72, 72), Image.LANCZOS).save(
                        dst, "JPEG", quality=88, optimize=True)
            except Exception:
                continue
        n_logo += 1
    print("校徽 %d 个" % n_logo)

    if (INT_ASSETS / "katex").exists():'''
assert t.count(anchor2) == 1
t = t.replace(anchor2, add2, 1)

# 3) 学校卡片加校徽
old3 = '''        return ('<a class="scard" href="%sx/%s/%s/" data-k="%s" data-tier="%s"><b>%s</b>'
                '<div class="sm">%s · %d 套 · %s–%s</div><div class="years">%s</div></a>'
                % (pre, TIER_SLUG[t], sl, esc(key), esc(t), esc(school), esc(TIER_NAME[t]),
                   len(items), esc(min(o["year"] for o in items)), esc(max(o["year"] for o in items)), yrs))'''
new3 = '''        badge = ('<img class="slogo" src="%sassets/logo/%s.jpg" alt="%s校徽" width="36" height="36" loading="lazy">'
                 % (pre, sl, esc(school))) if find_logo(school) else ""
        return ('<a class="scard" href="%sx/%s/%s/" data-k="%s" data-tier="%s">'
                '<span class="scard-top">%s<b>%s</b></span>'
                '<div class="sm">%s · %d 套 · %s–%s</div><div class="years">%s</div></a>'
                % (pre, TIER_SLUG[t], sl, esc(key), esc(t), badge, esc(school), esc(TIER_NAME[t]),
                   len(items), esc(min(o["year"] for o in items)), esc(max(o["year"] for o in items)), yrs))'''
assert t.count(old3) == 1, "scard"
t = t.replace(old3, new3)

# 4) 学校页标题加校徽
old4 = '''        body.append('<main class="wrap"><div class="hero"><h1>%s · 控制类真题思维导图</h1>'
                    '<p>%s · 共 %d 套（%s–%s）。</p></div>'
                    '<div class="grid" id="kg-grid" style="margin-top:14px">%s</div></main>'
                    % (esc(school), esc(TIER_NAME[t]), len(items),'''
new4 = '''        _lg = ('<img class="hlogo" src="%sassets/logo/%s.jpg" alt="%s校徽" width="56" height="56">'
               % (prefix, sl, esc(school))) if find_logo(school) else ""
        body.append('<main class="wrap"><div class="hero"><div class="hero-title">%s<h1>%s · 控制类真题思维导图</h1></div>'
                    '<p>%s · 共 %d 套（%s–%s）。</p></div>'
                    '<div class="grid" id="kg-grid" style="margin-top:14px">%s</div></main>'
                    % (_lg, esc(school), esc(TIER_NAME[t]), len(items),'''
assert t.count(old4) == 1, "schoolpage"
t = t.replace(old4, new4)

# 5) 卷页标题加校徽
old5 = '''        body.append('<div class="titlebar"><h1>%s</h1><div class="actions">\''''
new5 = '''        _lg2 = ('<img class="hlogo" src="%sassets/logo/%s.jpg" alt="%s校徽" width="52" height="52">'
                % (pre, s["slug"], esc(s["school"]))) if find_logo(s["school"]) else ""
        body.append('<div class="titlebar">%s<h1>%s</h1><div class="actions">\''''
assert t.count(old5) == 1, "setpage-open"
t = t.replace(old5, new5)
# 该 append 的 % 参数里补 _lg2（原来是 ... % esc(title)）
old6 = '''                    '<button class="btn" id="btn-full">全屏</button></div></div>'
                    % esc(title))'''
new6 = '''                    '<button class="btn" id="btn-full">全屏</button></div></div>'
                    % (_lg2, esc(title)))'''
assert t.count(old6) == 1, "setpage-args"
t = t.replace(old6, new6)

io.open(P, "w", encoding="utf-8").write(t)
print("site_build.py 已打补丁：校徽匹配 + 生成 + 三处展示")
