# -*- coding: utf-8 -*-
"""修回归：筛选器的搜索框无效（页面有两个 id="site-q"，JS 只绑到顶栏那个）。

① site_build.py：筛选器输入 id 改为 kg-q
② kg.js：筛选器与顶栏两个搜索框都绑定同一状态并互相同步；非索引页顶栏搜索回车 → 回首页 ?q=
③ kg.js：?debug=1 下增加自测——往搜索框派发 input 事件，报告"可见卡片数"是否真的变了
"""
import io

# ---------- ① 生成端 ----------
P = "site_build.py"
t = io.open(P, encoding="utf-8").read()
old = """                    '<input id="site-q" type="search" placeholder="搜学校 / 代码 / 年份">'"""
new = """                    '<input id="kg-q" type="search" placeholder="搜学校 / 代码 / 年份">'"""
assert t.count(old) == 1, "gen-input"
t = t.replace(old, new)
# 顶栏占位统一（不承诺搜考点，因为卡片筛选只匹配院校/代码/年份）
t = t.replace("""placeholder="搜学校 / 年份 / 代码" aria-label="搜索">') if show_search else """,
              """placeholder="搜学校 / 代码 / 年份" aria-label="搜索">') if show_search else """)
io.open(P, "w", encoding="utf-8").write(t)
print("site_build.py：筛选器输入改为 #kg-q")

# ---------- ②③ JS ----------
J = "网站前端/kg.js"
s = io.open(J, encoding="utf-8").read()

old_bind = """    var q = $("#site-q"), codeSel = $("#kg-code"), kpSel = $("#kg-kp"), sortSel = $("#kg-sort"),
        clearBtn = $("#kg-clear"), res = $("#kg-result"), empty = $("#kg-empty");"""
new_bind = """    // 顶栏与筛选器各有一个搜索框：两个都要绑（曾因都叫 #site-q，$ 只拿到第一个 → 筛选器里的输入无效）
    var qInputs = $$("#kg-q, .head-inp");
    var q = qInputs[0] || null;
    var codeSel = $("#kg-code"), kpSel = $("#kg-kp"), sortSel = $("#kg-sort"),
        clearBtn = $("#kg-clear"), res = $("#kg-result"), empty = $("#kg-empty");"""
assert s.count(old_bind) == 1, "js-decl"
s = s.replace(old_bind, new_bind)

old_q = """    if (q) {
      q.value = st.q || "";
      var t = null;
      q.addEventListener("input", function () {
        clearTimeout(t);
        t = setTimeout(function () { st.q = q.value.trim(); apply(false); }, 160);
      });
    }"""
new_q = """    qInputs.forEach(function (el) {
      el.value = st.q || "";
      var timer = null;
      el.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          st.q = el.value.trim();
          qInputs.forEach(function (x) { if (x !== el) { x.value = el.value; } });
          apply(false);
        }, 160);
      });
    });"""
assert s.count(old_q) == 1, "js-bind"
s = s.replace(old_q, new_q)

# 清除筛选：两个框都清空
old_clr = """        if (q) { q.value = ""; }"""
new_clr = """        qInputs.forEach(function (el) { el.value = ""; });"""
assert s.count(old_clr) == 1, "js-clear"
s = s.replace(old_clr, new_clr)

# apply() 里把状态回写到输入框（例如从 URL 带 ?q= 进来时）
old_app = """      grid.classList.toggle("filtered", active);"""
new_app = """      grid.classList.toggle("filtered", active);
      qInputs.forEach(function (el) { if (el.value !== st.q) { el.value = st.q; } });"""
assert s.count(old_app) == 1, "js-apply"
s = s.replace(old_app, new_app)

# 非索引页：顶栏搜索回车 → 回首页带 ?q=（此前那个搜索框在非索引页点了没反应）
old_boot = """    var h = (location.hash || "").match(/^#q(\\d+)$/);"""
new_boot = """    var hi = $(".head-inp");
    if (hi && !$("#kg-grid")) {
      hi.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" && hi.value.trim()) {
          var brand = $("a.brand");
          var base = brand ? brand.getAttribute("href") : "./";
          location.href = base + "?q=" + encodeURIComponent(hi.value.trim());
        }
      });
    }

    var h = (location.hash || "").match(/^#q(\\d+)$/);"""
assert s.count(old_boot) == 1, "js-nonindex"
s = s.replace(old_boot, new_boot)

# 自测钩子：?debug=1 时模拟输入，报告卡片数变化
old_dbg = """  function scanOverflow() {
    if (!/[?&]debug=1/.test(location.search)) { return; }"""
new_dbg = """  function selfTestSearch() {
    if (!/[?&]debug=1/.test(location.search)) { return; }
    var box = $("#kg-q") || $(".head-inp"), grid = $("#kg-grid");
    if (!box || !grid) { return; }
    var before = $$(".scard", grid).filter(function (c) { return !c.classList.contains("off"); }).length;
    box.value = "天津";
    box.dispatchEvent(new Event("input", { bubbles: true }));
    setTimeout(function () {
      var after = $$(".scard", grid).filter(function (c) { return !c.classList.contains("off"); }).length;
      report("SELFTEST q=天津 卡片 " + before + " → " + after + "  （绑定框 id=" + (box.id || box.className) + "）");
    }, 500);
  }

  function scanOverflow() {
    if (!/[?&]debug=1/.test(location.search)) { return; }"""
assert s.count(old_dbg) == 1, "js-selftest"
s = s.replace(old_dbg, new_dbg)
s = s.replace("boot(); bootIndex(); bootFormulas(); scanOverflow();",
              "boot(); bootIndex(); bootFormulas(); scanOverflow(); selfTestSearch();")
io.open(J, "w", encoding="utf-8").write(s)
print("kg.js：双搜索框绑定 + 非索引页回车搜索 + 自测钩子 已加")
