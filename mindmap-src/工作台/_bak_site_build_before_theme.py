# -*- coding: utf-8 -*-
"""生成「控制考研真题思维导图」静态站点（对外收录用，可整站部署，也可片段嵌入已有站点）。

导航模型（用户裁定）：学校分级 → 学校 → 年份 → 题
  首页                /                                   分级筛选 + 学校网格 + 搜索
  分级页              /x/985/                             该分级下的学校
  学校页              /x/985/tianjin/                     该校各年份
  卷页（题清单+内容）  /x/985/tianjin/2020/                整卷/单题切换，含全部题的静态内容
  考点页              /k/rl_02/                           该考点历年考法（跨校跨年）

SEO 设计：每页都有真实内容 DOM（不靠 JS 生成）、独立 title/description、canonical、OG、
JSON-LD；导图是增强层。链接全部相对路径（file:// 可直接预览，放任意子目录也能用）。

用法：
  python site_build.py                    # 全量生成到 网站原型/
  python site_build.py --out 目录 --only 天津大学_812_2020 --site https://你的域名
"""
from __future__ import annotations
import argparse, html, json, re, shutil, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mindmap_v6 as mm6                      # noqa: E402
import build_interactive as bi                # noqa: E402
import workbench as wb                        # noqa: E402
from pypinyin import lazy_pinyin              # noqa: E402

V6 = HERE / "思维导图_v6"
KP_DIR = HERE / "考点库"
FRONT = HERE / "网站前端"
INT_ASSETS = HERE / "思维导图_交互" / "assets"
YEAR_LO, YEAR_HI = "2015", "2025"

TIER_SLUG = {"985": "985", "211": "211", "强势双非": "shuangfei"}
TIER_NAME = {"985": "985 院校", "211": "211 院校", "强势双非": "强势双非"}
TIER_ORDER = ["985", "211", "强势双非"]
PARENT_HOME = ""          # 父站首页链接（嵌入已有站点时设置，见 --parent）
LOGO_SRC = Path(r"D:\ZeXiao\专业课选择\images\校徽")


def find_logo(school: str):
    """按校名找校徽（精确 → 去校区后缀 → 去括号）。找不到返回 None。"""
    if not LOGO_SRC.is_dir():
        return None
    for cand in (school, wb._base(school), re.sub(r"[（(].*?[）)]", "", school).strip()):
        p = LOGO_SRC / (str(cand) + ".jpg")
        if p.is_file():
            return p
    return None

# 卷页主栏的导图画布（放在大纲之前：默认视图就是导图，且不被侧栏高度挤压）
MAP_TMPL = """<div class="mapwrap" id="mapwrap">
<div class="maptools">
<button class="btn on" data-depth="1">板块</button>
<button class="btn" data-depth="2">考点</button>
<button class="btn" data-depth="99">全部</button>
<button class="btn" data-zoom="in" title="放大">＋</button>
<button class="btn" data-zoom="out" title="缩小">－</button>
<button class="btn" data-fit="1">适应</button>
<input id="map-q" type="search" placeholder="图内搜索">
</div>
<svg id="svg"><g id="g"></g></svg>
<div class="map-foot">点击节点展开/折叠　·　滚轮缩放　·　拖拽平移</div>
<div class="map-wm"><img src="%sassets/wanren-education-logo.png" alt="">
<div class="txt">控制考研哪家强，<b>万人教育</b>来领航<br>公众号：控制自动化考研　微信：kongzhiwyz7</div></div>
</div>"""


# ---------------------------------------------------------------- 工具
def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def slug_of(name: str) -> str:
    """校名 → ASCII slug：全拼去“大学/学院”尾缀，括号校区用 - 连接。"""
    s = str(name).strip()
    m = re.match(r"^(.*?)[（(]([^）)]+)[）)]$", s)
    main, sub = (m.group(1), m.group(2)) if m else (s, "")
    def py(x: str) -> str:
        return re.sub(r"[^a-z0-9]", "", "".join(lazy_pinyin(x)).lower())
    main_py = py(main)
    for suf in ("daxue", "xueyuan"):
        if main_py.endswith(suf) and len(main_py) > len(suf) + 3:
            main_py = main_py[: -len(suf)]
            break
    return main_py + ("-" + py(sub) if sub else "")


def up(prefix_depth: int) -> str:
    return "../" * prefix_depth


# ---------------------------------------------------------------- 数据装载
def load_kp_lib() -> tuple[dict, dict]:
    """返回 (考点明细 id→信息, 大类 id→名称)"""
    detail, cat = {}, {}
    for p in sorted(KP_DIR.glob("*.json")):
        if p.name.startswith("_"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for da in d.get("大类", []):
            cat[da.get("id")] = da.get("名称", "")
            for xi in da.get("细分", []):
                info = dict(xi)
                info["_大类"] = da.get("名称", "")
                info["_大类id"] = da.get("id", "")
                info["_板块别名"] = da.get("板块别名", "")
                detail[xi.get("id")] = info
    return detail, cat


def norm_list(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return [x for x in v if x]


# ---------------------------------------------------------------- 静态 HTML 片段
def kp_detail_html(kp: dict) -> str:
    """考点库正文：要点 / 步骤 / 公式 / 通用考法 / 常见易错（本卷实际考过的条目打标）。"""
    def li(x, own=False):
        mark = '<span class="ownmark">本卷考过</span>' if own else ""
        return "<li>%s%s</li>" % (mark, esc(x))

    secs = []
    if kp.get("要点"):
        secs.append(("要点", "".join(li(x) for x in kp["要点"])))
    if kp.get("步骤"):
        secs.append(("步骤", "".join(li(x) for x in kp["步骤"])))
    if kp.get("考法"):
        n = int(kp.get("_n考法") or 0)
        secs.append(("通用考法", "".join(li(x, i < n) for i, x in enumerate(kp["考法"]))))
    if kp.get("易错"):
        n = int(kp.get("_n易错") or 0)
        secs.append(("常见易错", "".join(li(x, i < n) for i, x in enumerate(kp["易错"]))))
    fml = "".join('<div class="formula" data-tex="%s"></div>' % esc(x) for x in (kp.get("公式") or []))
    if not secs and not fml:
        return ""
    out = ['<details class="kpdetail" open><summary>考点详解（要点 / 步骤 / 公式 / 考法 / 易错）</summary>']
    for title, items in secs:
        out.append('<div class="kpsec"><div class="lab">%s</div><ul>%s</ul></div>' % (title, items))
    if fml:
        out.append('<div class="kpsec"><div class="lab">公式</div>%s</div>' % fml)
    out.append("</details>")
    return "".join(out)


def qcard_html(q: dict, prefix: str) -> str:
    o = ['<article class="qcard" id="q%s" data-q="%s">' % (q["i"], q["i"])]
    head = '<span class="no">%s</span>' % esc(q["tab"])
    if q.get("名称"):
        head += "<span>%s</span>" % esc(q["名称"])
    else:
        head += "<span>%s</span>" % esc("板块 " + str(q["i"]))
    if q.get("分值"):
        head += '<span class="sc">%s 分</span>' % esc(q["分值"])
    head += '<a class="anchorlink" data-q="%s" href="#q%s" title="单独看这一题">#</a>' % (q["i"], q["i"])
    o.append("<h2>%s</h2>" % head)

    o.append('<div class="kv">')
    if q.get("思路"):
        o.append('<div class="k">思路</div><ul>')
        for x in q["思路"]:
            o.append('<li class="idea">%s</li>' % esc(x))
        o.append("</ul>")
    if q.get("易错"):
        o.append('<div class="k">易错</div><ul>')
        for x in q["易错"]:
            o.append('<li class="warn">%s</li>' % esc(x))
        o.append("</ul>")
    o.append("</div>")

    for kp in q["考点"]:
        o.append('<div class="kpbox">')
        link = prefix + "k/%s/" % kp["ref"] if kp.get("ref") else ""
        title = esc(kp.get("名称") or kp.get("ref") or "考点")
        o.append('<div class="kptitle">')
        o.append('<a href="%s">%s</a>' % (link, title) if link else "<span>%s</span>" % title)
        if kp.get("_大类"):
            o.append('<span class="tiny muted">%s</span>' % esc(kp["_大类"]))
        o.append("</div>")
        if kp.get("_本卷考法"):
            o.append('<div class="kpb"><div class="lab">本卷考法</div><ul>')
            for x in kp["_本卷考法"]:
                o.append("<li>%s</li>" % esc(x))
            o.append("</ul></div>")
        inst = kp.get("本卷实例") or {}
        if inst:
            o.append('<div class="kpb"><div class="lab">本卷实例%s</div><ul>'
                     % ("　" + esc(kp["页码"]) if kp.get("页码") else ""))
            for key in ("关键一步", "中间结果", "卡点"):
                for x in norm_list(inst.get(key)):
                    o.append("<li><b>%s：</b>%s</li>" % (esc(key), esc(x)))
            o.append("</ul></div>")
        o.append(kp_detail_html(kp))
        o.append("</div>")
    o.append("</article>")
    return "\n".join(o)


def page_shell(title, desc, prefix, body, canonical="", extra_head="", cls=""):
    ld = extra_head
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
{canon}
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta name="theme-color" content="#1f4e79">
<link rel="stylesheet" href="{prefix}assets/kg.css">
<link rel="icon" href="{prefix}assets/wanren-education-logo.png">
{ld}
</head>
<body class="{cls}">
{body}
<script src="{prefix}assets/d3.min.js"></script>
<script src="{prefix}assets/kg.js"></script>
</body></html>
""".format(title=esc(title), desc=esc(desc), prefix=prefix, body=body,
           canon='<link rel="canonical" href="%s">' % esc(canonical) if canonical else "",
           ld=ld, cls=cls)


def site_head(prefix: str, crumbs: list, show_search=True) -> str:
    c = []
    for i, (lab, href) in enumerate(crumbs):
        if i:
            c.append('<span class="sep">›</span>')
        c.append('<a href="%s">%s</a>' % (href, esc(lab)) if href else "<span>%s</span>" % esc(lab))
    s = ('<input id="site-q" type="search" placeholder="搜学校 / 年份 / 代码" '
         'aria-label="搜索">') if show_search else ""
    ph = ""
    if PARENT_HOME:
        # 相对父站首页要按当前页深度上溯（PARENT_HOME 以本站根为基准，如 "../index.html"）
        href = PARENT_HOME if re.match(r"^[a-zA-Z]+://", PARENT_HOME) else prefix + PARENT_HOME
        ph = '<a class="parent-home" href="%s">← 择校首页</a>' % href
    return ('<header class="site-head"><div class="inner">'
            '%s'
            '<a class="brand" href="%s"><img src="%sassets/wanren-education-logo.png" alt="">'
            '<span>控制考研真题思维导图</span></a>'
            '<nav class="crumbs">%s</nav>'
            '<div class="head-right">%s</div>'
            '</div></header>') % (ph, prefix, prefix, "".join(c), s)


def site_foot(prefix: str) -> str:
    return ('<footer class="site-foot"><div class="inner">'
            '<span>控制考研真题思维导图 · 万人教育</span>'
            '<span>导图内容为本站原创整理，欢迎交流指正</span>'
            '<span class="fwm"><img src="%sassets/wanren-education-logo.png" alt="">'
            '<span>控制考研哪家强，<b>万人教育</b>来领航<br>公众号：控制自动化考研　微信：kongzhiwyz7</span>'
            '</span></div></footer>') % prefix


# ---------------------------------------------------------------- 主流程
def build(out: Path, only: set, site: str, parent: str = "") -> None:
    t0 = time.perf_counter()
    global PARENT_HOME
    PARENT_HOME = parent
    kp_lib, kp_cat = load_kp_lib()
    lib = mm6.load_lib()

    sets = []          # 每套：{key, tier, school, slug, year, code, subject, tree, qs, ...}
    refs = {}          # ref → 出现记录
    for jp in sorted(V6.glob("*.json")):
        key = jp.stem
        if only and key not in only:
            continue
        raw = json.loads(jp.read_text(encoding="utf-8"))
        school = str(raw.get("院校") or key.rsplit("_", 2)[0])
        year = str(raw.get("年份") or key.rsplit("_", 1)[-1])
        code = str(raw.get("科目代码") or "")
        subject = str(raw.get("科目") or "")
        tier = wb.tier(school)
        spec, missing = mm6.expand(raw, lib)
        tree = bi.to_tree(spec)
        tree.pop("uid", None)
        # 导图里的「总览」节点：正文已给出完整特点，这里截断，免得变成一个文本墙盒子
        for ch in tree.get("children", []):
            lab = ch.get("label") or ""
            if ch.get("type") == "warn" and len(lab) > 130:
                ch["label"] = lab[:130] + "…"
        qs = []
        for i, b in enumerate(spec.get("板块", []), 1):
            one = dict(spec)
            one["板块"] = [b]
            t = bi.to_tree(one)
            kps = []
            for kp in b.get("考点", []) or []:
                if isinstance(kp, str):
                    kp = {"名称": kp}
                rid = kp.get("ref")
                n_kf = int(kp.get("_本卷考法") or 0)
                n_kpe = int(kp.get("_本卷易错") or 0)
                item = {"名称": kp.get("名称", ""), "ref": rid,
                        "_大类": kp.get("_大类", ""), "页码": kp.get("页码", ""),
                        "_本卷考法": norm_list(kp.get("考法"))[:n_kf],
                        "本卷实例": kp.get("本卷实例") or {},
                        # 考点库正文（用户要求直接展开在每题下）
                        "要点": norm_list(kp.get("要点")), "步骤": norm_list(kp.get("步骤")),
                        "公式": norm_list(kp.get("公式")), "考法": norm_list(kp.get("考法")),
                        "易错": norm_list(kp.get("易错")),
                        "_n考法": n_kf, "_n易错": n_kpe}
                kps.append(item)
                if rid:
                    refs.setdefault(rid, []).append(
                        {"school": school, "schoolSlug": slug_of(school), "tier": tier,
                         "year": year, "code": code, "subject": subject,
                         "key": key, "i": i, "tab": str(b.get("题号") or i),
                         "名称": b.get("名称", ""), "分值": b.get("分值")})
            qs.append({"i": i, "tab": str(b.get("题号") or ("第%d板块" % i)),
                       "名称": b.get("名称", ""), "分值": b.get("分值"),
                       "思路": norm_list(b.get("思路")), "易错": norm_list(b.get("易错")),
                       "考点": kps, "tree": t})
        sets.append({"key": key, "tier": tier, "school": school, "slug": slug_of(school),
                     "year": year, "code": code, "subject": subject,
                     "来源": str(raw.get("来源") or ""), "备注": str(raw.get("备注") or ""),
                     "总览": spec.get("总览") or {}, "tree": tree, "qs": qs,
                     "缺失ref": missing})

    # 统计聚合
    by_school = {}
    for s in sets:
        by_school.setdefault(s["school"], []).append(s)
    for v in by_school.values():
        v.sort(key=lambda x: x["year"])
    tiers = {}
    for s in sets:
        tiers.setdefault(s["tier"], set()).add(s["school"])

    # 资源
    (out / "assets").mkdir(parents=True, exist_ok=True)
    for f in ("kg.css", "kg.js", "kg-embed.js"):
        shutil.copy2(FRONT / f, out / "assets" / f)
    for f in ("d3.min.js", "wanren-education-logo.png"):
        if (INT_ASSETS / f).exists():
            shutil.copy2(INT_ASSETS / f, out / "assets" / f)
    # 校徽：裁成 72×72，按 slug 命名（ASCII 路径，避免中文 URL）
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

    if (INT_ASSETS / "katex").exists():
        dst = out / "assets" / "katex"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(INT_ASSETS / "katex", dst)

    # ---- 卷页
    for s in sets:
        p = 4                                     # x/tier/school/year
        pre = up(p)
        ylist = [x["year"] for x in by_school[s["school"]]]
        idx = ylist.index(s["year"])
        prev_s = by_school[s["school"]][idx - 1] if idx > 0 else None
        next_s = by_school[s["school"]][idx + 1] if idx + 1 < len(by_school[s["school"]]) else None
        sidelen = []
        for o in by_school[s["school"]]:
            if o["year"] != s["year"]:
                sidelen.append('<a class="yearchip" href="../%s/">%s <span class="n">%d题</span></a>'
                               % (o["year"], esc(o["year"]), len(o["qs"])))
        kpset, kplinks = set(), []
        for q in s["qs"]:
            for kp in q["考点"]:
                if kp.get("ref") and kp["ref"] not in kpset:
                    kpset.add(kp["ref"])
                    nm = kp.get("名称") or kp_lib.get(kp["ref"], {}).get("名称") or kp["ref"]
                    cat = (kp_lib.get(kp["ref"]) or {}).get("_大类", "")
                    kplinks.append('<a class="kplink" href="%sk/%s/" title="考点编号 %s">'
                                   '<span class="ktag">%s</span><span>%s</span></a>'
                                   % (pre, kp["ref"], esc(kp["ref"]), esc(cat), esc(nm)))

        title = "%s %s %s %s 年真题思维导图" % (s["school"], s["code"], s["subject"], s["year"])
        qnames = "；".join("第%s题%s" % (q["tab"], ("（%s）" % q["名称"][:26]) if q["名称"] else "")
                           for q in s["qs"][:6])
        desc = ("%s %s 年 %s %s 考研真题思维导图：共 %d 个大题，逐题思路、考点与易错整理。%s"
                % (s["school"], s["year"], s["code"], s["subject"], len(s["qs"]), qnames))

        tabs = ['<button class="qt on" data-q="all">整卷</button>']
        for q in s["qs"]:
            tabs.append('<button class="qt" data-q="%d">%s%s</button>'
                        % (q["i"], esc(q["tab"]),
                           "<em>%s分</em>" % esc(q["分值"]) if q.get("分值") else ""))

        total = 0
        for q in s["qs"]:
            try:
                total += float(re.sub(r"[^\d.]", "", str(q["分值"] or "")) or 0)
            except ValueError:
                pass
        badges = ['<span class="badge t%s">%s</span>' % (TIER_SLUG[s["tier"]], esc(TIER_NAME[s["tier"]]))]
        badges.append('<span class="badge">共 %d 题</span>' % len(s["qs"]))
        if total:
            badges.append('<span class="badge">合计 %g 分</span>' % total)

        body = [site_head(pre,  [(TIER_NAME[s["tier"]], pre + "x/%s/" % TIER_SLUG[s["tier"]]),
                                (s["school"], pre + "x/%s/%s/" % (TIER_SLUG[s["tier"]], s["slug"])),
                                ("%s 年" % s["year"], None)])]
        body.append('<main class="wrap">')
        _lg2 = ('<img class="hlogo" src="%sassets/logo/%s.jpg" alt="%s校徽" width="52" height="52">'
                % (pre, s["slug"], esc(s["school"]))) if find_logo(s["school"]) else ""
        body.append('<div class="titlebar">%s<h1>%s</h1><div class="actions">'
                    '<button class="btn" data-mode="outline">大纲</button>'
                    '<button class="btn on" data-mode="map">导图</button>'
                    '<button class="btn" id="btn-full">全屏</button></div></div>'
                    % (_lg2, esc(title)))
        body.append('<div class="tagrow">%s</div>' % "".join(badges))
        if s["总览"].get("特点") or s["总览"].get("难度"):
            ov = []
            if s["总览"].get("难度"):
                ov.append("难度：%s" % esc(s["总览"]["难度"]))
            if s["总览"].get("特点"):
                ov.append(esc(s["总览"]["特点"]))
            body.append('<p class="sub muted tiny" style="margin:8px 0 0">%s</p>' % "　".join(ov))
        body.append('<div class="qtabs" id="qtabs">%s</div>' % "".join(tabs))
        body.append('<div class="cols"><div class="mainpane">')
        body.append(MAP_TMPL % pre)
        body.append('<section class="content" id="content">')
        for q in s["qs"]:
            body.append(qcard_html(q, pre))
        body.append("</section></div><aside class=\"side\">")
        if kplinks:
            body.append('<div class="card"><h3>本卷考点</h3><div class="kplist">%s</div></div>'
                        % "".join(kplinks))
        if sidelen:
            body.append('<div class="card"><h3>%s 其它年份</h3><div class="navlist">%s</div></div>'
                        % (esc(s["school"]), "".join(sidelen)))
        nav = []
        if prev_s:
            nav.append('<a class="yearchip" href="../%s/">← %s</a>' % (prev_s["year"], prev_s["year"]))
        if next_s:
            nav.append('<a class="yearchip" href="../%s/">%s →</a>' % (next_s["year"], next_s["year"]))
        if nav:
            body.append('<div class="card"><h3>上下年份</h3><div class="navlist">%s</div></div>' % "".join(nav))
        body.append("</aside></div>")
        body.append("</main>")
        body.append(site_foot(pre))
        payload = {"base": pre, "key": s["key"], "full": s["tree"],
                   "qs": [{"no": q["tab"], "tree": q["tree"]} for q in s["qs"]]}
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        body.append('<script type="application/json" id="kg-data">%s</script>' % data)
        ld = {"@context": "https://schema.org", "@type": "LearningResource",
              "name": title, "inLanguage": "zh-CN",
              "about": [kp_lib[kp]["名称"] for kp in list(kpset)[:10] if kp in kp_lib],
              "educationalLevel": TIER_NAME[s["tier"]],
              "provider": {"@type": "Organization", "name": "万人教育"}}
        if site:
            ld["url"] = "%s/x/%s/%s/%s/" % (site.rstrip("/"), TIER_SLUG[s["tier"]], s["slug"], s["year"])
        extra = '<script type="application/ld+json">%s</script>' % json.dumps(ld, ensure_ascii=False)
        pg = page_shell(title, desc, pre, "\n".join(body), canonical=ld.get("url", ""), extra_head=extra,
                        cls="page-set")
        d = out / "x" / TIER_SLUG[s["tier"]] / s["slug"] / s["year"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(pg, encoding="utf-8")
    print("卷页 %d 个" % len(sets))

    # ---- 嵌入用清单：key → 页面路径（kg-embed.js 用，避免前端猜 slug）
    man = {s["key"]: "x/%s/%s/%s/" % (TIER_SLUG[s["tier"]], s["slug"], s["year"]) for s in sets}
    (out / "assets" / "sets.js").write_text(
        "window.KG_SETS=" + json.dumps(man, ensure_ascii=False, separators=(",", ":")) + ";",
        encoding="utf-8")

    # ---- 站点地图索引（首页 / 分级 / 学校）
    def school_card(school: str, pre: str) -> str:
        items = by_school[school]
        t = wb.tier(school)
        sl = slug_of(school)
        items_desc = sorted(items, key=lambda x: x["year"], reverse=True)
        show = items_desc[:6]
        yrs = "".join('<a class="yearchip" href="%sx/%s/%s/%s/">%s <span class="n">%d题</span></a>'
                      % (pre, TIER_SLUG[t], sl, o["year"], esc(o["year"]), len(o["qs"]))
                      for o in show)
        # 只列最近 6 年（卡片高度统一）；其余年份的数量已在"共 N 套"里体现，故不再放 +N chip

        codes = sorted({o["code"] for o in items if o["code"]})
        key = "%s %s %s %s" % (school, TIER_NAME[t], " ".join(codes), " ".join(o["year"] for o in items))
        badge = ('<img class="slogo" src="%sassets/logo/%s.jpg" alt="%s校徽" width="36" height="36" loading="lazy">'
                 % (pre, sl, esc(school))) if find_logo(school) else ""
        # 注意：卡片外层不能用 <a>——年份 chip 也是 <a>，<a> 嵌 <a> 非法，浏览器会提前闭合外层标签
        return ('<div class="scard" data-k="%s" data-tier="%s">'
                '<a class="scard-link" href="%sx/%s/%s/">'
                '<span class="scard-top">%s<b>%s</b></span>'
                '<div class="sm">%s · %d 套 · %s–%s</div></a>'
                '<div class="years">%s</div></div>'
                % (esc(key), esc(t), pre, TIER_SLUG[t], sl, badge, esc(school), esc(TIER_NAME[t]),
                   len(items), esc(min(o["year"] for o in items)), esc(max(o["year"] for o in items)), yrs))

    # 首页
    pre = ""
    tabs = ['<button class="btn on" data-tier-tab="">全部（%d）</button>' % len(by_school)]
    for t in TIER_ORDER:
        tabs.append('<button class="btn" data-tier-tab="%s">%s（%d）</button>'
                    % (esc(t), esc(TIER_NAME[t]), len(tiers.get(t, ()))))
    stats = [("套数", len(sets)), ("院校", len(by_school)), ("分级", 3), ("年份", "%s–%s" % (YEAR_LO, YEAR_HI))]
    body = [site_head("",  [("首页", None)])]
    body.append('<main class="wrap"><div class="hero"><h1>控制考研真题思维导图</h1>'
                '<p>按「学校分级 → 学校 → 年份 → 题」逐题整理：思路、考点与本卷考法、易错点。'
                '覆盖 %s–%s 年 985 / 211 / 强势双非 院校控制类专业课真题。</p>'
                '<div class="stats">%s</div></div>'
                % (YEAR_LO, YEAR_HI,
                   "".join('<div class="stat"><b>%s</b><span>%s</span></div>' % (v, k) for k, v in stats)))
    body.append('<div class="tabs">%s</div>' % "".join(tabs))
    body.append('<div class="searchbox" style="margin:0 0 12px"><input id="site-q" type="search" '
                'placeholder="搜学校名 / 代码 / 年份，例如：天津 / 812 / 2020"></div>')
    body.append('<div class="grid" id="kg-grid">%s</div>'
                % "".join(school_card(s, pre) for s in sorted(by_school, key=slug_of)))
    body.append('<p class="muted tiny" id="kg-empty" hidden>没有匹配的院校，换个关键词试试。</p>')
    body.append('<div class="card" style="margin-top:18px"><h3>怎么用这个站</h3>'
                '<p class="tiny muted">左侧按分级/学校/年份进入某套卷；卷内顶部可按「整卷 / 单题」切换，'
                '单题视图给出该题的思路、考点与易错；点考点进入考点页，可以看到该考点历年在哪些学校考过、怎么考的。</p></div>')
    body.append("</main>")
    body.append(site_foot(pre))
    (out / "index.html").write_text(page_shell(
        "控制考研真题思维导图 · 985/211/强势双非 控制类真题逐题解析",
        "覆盖 %s–%s 年 %d 所院校 %d 套控制类考研真题的思维导图，按学校分级、学校、年份、题组织，"
        "逐题给出思路、考点与易错点。" % (YEAR_LO, YEAR_HI, len(by_school), len(sets)),
        pre, "\n".join(body),
        canonical=(site.rstrip("/") + "/") if site else "", cls="page-index"), encoding="utf-8")

    # 分级页
    for t in TIER_ORDER:
        ss = sorted(tiers.get(t, ()), key=slug_of)
        if not ss:
            continue
        p = 2
        prefix = up(p)
        body = [site_head(prefix,  [("首页", prefix), (TIER_NAME[t], None)])]
        body.append('<main class="wrap"><div class="hero"><h1>%s · 控制类真题思维导图</h1>'
                    '<p>共 %d 所院校、%d 套卷。</p></div>'
                    '<div class="searchbox" style="margin:14px 0"><input id="site-q" type="search" '
                    'placeholder="搜学校 / 代码 / 年份"></div>'
                    '<div class="grid" id="kg-grid">%s</div>'
                    '<p class="muted tiny" id="kg-empty" hidden>没有匹配的院校。</p></main>'
                    % (esc(TIER_NAME[t]), len(ss),
                       sum(len(by_school[s]) for s in ss),
                       "".join(school_card(s, prefix) for s in ss)))
        body.append(site_foot(prefix))
        d = out / "x" / TIER_SLUG[t]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page_shell(
            "%s 控制类考研真题思维导图（%d 所院校）" % (TIER_NAME[t], len(ss)),
            "%s（%d 所）控制类考研真题思维导图汇总，可按年份进入各校各年真题。" % (TIER_NAME[t], len(ss)),
            prefix, "\n".join(body),
            canonical=(site.rstrip("/") + "/x/%s/" % TIER_SLUG[t]) if site else ""), encoding="utf-8")

    # 学校页
    for school, items in by_school.items():
        t = wb.tier(school)
        sl = slug_of(school)
        p = 3
        prefix = up(p)
        rows = []
        for o in sorted(items, key=lambda x: x["year"]):
            rows.append('<a class="scard" href="%s/" data-k="%s"><b>%s 年</b>'
                        '<div class="sm">%s %s · %d 题</div></a>'
                        % (o["year"], esc(o["year"]), esc(o["year"]), esc(o["code"]),
                           esc(o["subject"]), len(o["qs"])))
        body = [site_head(prefix,  [("首页", prefix),
                                   (TIER_NAME[t], prefix + "x/%s/" % TIER_SLUG[t]),
                                   (school, None)])]
        _lg = ('<img class="hlogo" src="%sassets/logo/%s.jpg" alt="%s校徽" width="56" height="56">'
               % (prefix, sl, esc(school))) if find_logo(school) else ""
        body.append('<main class="wrap"><div class="hero"><div class="hero-title">%s<h1>%s · 控制类真题思维导图</h1></div>'
                    '<p>%s · 共 %d 套（%s–%s）。</p></div>'
                    '<div class="grid" id="kg-grid" style="margin-top:14px">%s</div></main>'
                    % (_lg, esc(school), esc(TIER_NAME[t]), len(items),
                       esc(min(o["year"] for o in items)), esc(max(o["year"] for o in items)),
                       "".join(rows)))
        body.append(site_foot(prefix))
        d = out / "x" / TIER_SLUG[t] / sl
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page_shell(
            "%s 控制类考研真题思维导图（%d 套）" % (school, len(items)),
            "%s（%s）%s–%s 年控制类专业课真题思维导图，共 %d 套，可逐题查看思路与考点。"
            % (school, TIER_NAME[t], min(o["year"] for o in items), max(o["year"] for o in items), len(items)),
            prefix, "\n".join(body),
            canonical=(site.rstrip("/") + "/x/%s/%s/" % (TIER_SLUG[t], sl)) if site else ""), encoding="utf-8")
    print("分级页 %d 个；学校页 %d 个" % (len(tiers), len(by_school)))

    # ---- 考点页
    def url_of_set(rec):
        return "/x/%s/%s/%s/" % (TIER_SLUG[rec["tier"]], rec["schoolSlug"], rec["year"])

    n_kp = 0
    for rid, recs in refs.items():
        info = kp_lib.get(rid, {})
        name = info.get("名称") or recs[0].get("名称") or rid
        p = 2
        prefix = up(p)
        recs2 = sorted(recs, key=lambda r: (r["year"], r["school"]), reverse=True)
        n_sets = len({r["key"] for r in recs2})          # 唯一套数（一套可能有多题命中同一考点）
        schools = sorted({r["school"] for r in recs2})
        yrs = sorted({r["year"] for r in recs2})
        rows = []
        for r in recs2:
            rows.append('<tr><td class="y">%s</td>'
                        '<td><a href="%s%s#q%d">%s</a></td>'
                        '<td>%s</td><td class="y">%s</td></tr>'
                        % (esc(r["year"]), prefix, url_of_set(r)[1:], r["i"], esc(r["school"]),
                           esc(r["tab"] + ("　" + r["名称"][:28] if r["名称"] else "")),
                           esc(r["分值"] if r["分值"] else "—")))
        def sec(title, vals, cls=""):
            vals = norm_list(vals)
            if not vals:
                return ""
            li = "".join("<li>%s</li>" % esc(v) for v in vals)
            return '<div class="card"><h3>%s</h3><ul class="%s" style="margin:0;padding-left:20px">%s</ul></div>' % (title, cls, li)

        body = [site_head(prefix,  [("首页", prefix), ("考点", None), (name, None)])]
        body.append('<main class="wrap"><div class="kphead"><h1>%s</h1>'
                    '<div class="tagrow"><span class="badge">%s</span>'
                    '<span class="badge">%s</span>'
                    '<span class="badge">%d 套卷出现</span><span class="badge">%d 所院校</span>'
                    '<span class="badge">%s–%s</span></div></div>'
                    '<p class="tiny muted rid" style="margin:6px 0 0">%s</p>'
                    % (esc(name), esc(info.get("_大类", "")), esc(rid), n_sets, len(schools),
                       esc(min(yrs)), esc(max(yrs)), esc(rid)))
        cols = '<div class="cols"><section class="content">'
        cols += sec("要点", info.get("要点"))
        cols += sec("步骤", info.get("步骤"))
        if norm_list(info.get("公式")):
            cols += '<div class="card"><h3>公式</h3>%s</div>' % "".join(
                '<div class="formula" data-tex="%s"></div>' % esc(x) for x in norm_list(info.get("公式")))
        cols += sec("通用考法", info.get("考法"))
        cols += sec("常见易错", info.get("易错"))
        cols += ('<div class="card"><h3>历年考法（%d）</h3>'
                 '<div class="tablescroll"><table class="katable"><thead><tr>'
                 '<th>年份</th><th>院校</th><th>题</th><th>分值</th></tr></thead><tbody>%s</tbody>'
                 '</table></div></div>' % (len(rows), "".join(rows)))
        cols += "</section></div>"
        body.append(cols)
        body.append("</main>")
        body.append(site_foot(prefix))
        ld = {"@context": "https://schema.org", "@type": "DefinedTerm", "name": name,
              "inDefinedTermSet": info.get("_大类", ""), "description": "；".join(norm_list(info.get("要点"))[:4])}
        extra = '<script type="application/ld+json">%s</script>' % json.dumps(ld, ensure_ascii=False)
        d = out / "k" / rid
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page_shell(
            "%s · 考点历年考法（%d 套卷 / %d 处题）" % (name, n_sets, len(recs2)),
            "%s（%s）：该考点在 %s–%s 年的控制类考研真题中，共出现于 %d 套卷的 %d 处题目，"
            "覆盖 %d 所院校；此处汇总历年考法与常见易错。" % (name, info.get("_大类", ""), min(yrs),
                                                       max(yrs), n_sets, len(recs2), len(schools)),
            prefix, "\n".join(body),
            canonical=(site.rstrip("/") + "/k/%s/" % rid) if site else "", extra_head=extra), encoding="utf-8")
        n_kp += 1
    print("考点页 %d 个" % n_kp)

    # ---- sitemap / robots
    urls = []
    if site:
        base = site.rstrip("/")
        urls += [base + "/"]
        urls += ["%s/x/%s/" % (base, TIER_SLUG[t]) for t in TIER_ORDER if t in tiers]
        urls += ["%s/x/%s/%s/" % (base, TIER_SLUG[wb.tier(s)], slug_of(s)) for s in by_school]
        urls += ["%s/x/%s/%s/%s/" % (base, TIER_SLUG[s["tier"]], s["slug"], s["year"]) for s in sets]
        urls += ["%s/k/%s/" % (base, rid) for rid in refs]
        sm = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        sm += ["<url><loc>%s</loc></url>" % esc(u) for u in urls]
        sm.append("</urlset>")
        (out / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
        (out / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % base, encoding="utf-8")
    print("URL 合计（sitemap）: %d" % len(urls))
    print("完成，用时 %.1f 秒 → %s" % (time.perf_counter() - t0, out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="网站原型")
    ap.add_argument("--only", nargs="*", help="只生成指定 key（调试用）")
    ap.add_argument("--site", default="https://kaoyan.wanren.example.com",
                    help="站点根 URL，用于 canonical/sitemap；留空则不写")
    ap.add_argument("--parent", default="",
                    help="父站首页的链接（相对或绝对）；填了就显示「← 择校首页」")
    a = ap.parse_args()
    build(HERE / a.out, set(a.only or []), a.site, a.parent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
