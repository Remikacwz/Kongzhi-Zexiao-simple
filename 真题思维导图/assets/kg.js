/* 控制考研真题思维导图 · 前端交互
   设计原则：
   - 内容是真实 DOM（大纲），JS 只做增强：切题、导图、搜索；
   - 画布是页内一块，绝不劫持整页滚动；
   - 移动端默认大纲视图（可读性优先），导图按需切换；
   - 公式按需懒加载 KaTeX（全库几乎无公式，不白下载 1.5MB）。 */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // 错误上报：出问题时把原因写到 <html data-kgerr>，便于排障（正常时无副作用）
  function report(msg) {
    try { document.documentElement.setAttribute("data-kgerr", String(msg).slice(0, 300)); } catch (e) { /* ignore */ }
  }
  window.addEventListener("error", function (ev) {
    report((ev.message || "error") + " @ " + String(ev.filename || "").split("/").pop() + ":" + (ev.lineno || 0));
  });

  // 节点类型的配色：[标签, 边框, 底色]
  var TYPES = {
    root: ["", "#a92122", "#a92122"],
    block: ["题", "#2f6fa8", "#e8f1f9"],
    idea: ["思路", "#7aa5c9", "#f2f7fb"],
    warn: ["易错", "#c98a2e", "#fdf6ec"],
    kp: ["考点", "#4b8b5a", "#eef7f0"],
    ins: ["实例", "#8d7bb5", "#f4f1fa"],
    k1: ["关键一步", "#8d7bb5", "#f7f5fc"],
    k2: ["中间结果", "#8d7bb5", "#f7f5fc"],
    k3: ["卡点", "#c9564f", "#fdf2f1"],
    yd: ["要点", "#4b8b5a", "#f4faf5"],
    bz: ["步骤", "#4b8b5a", "#f4faf5"],
    fm: ["公式", "#6b7b8c", "#f4f6f8"],
    kf: ["考法", "#b8860b", "#fdf8ec"],
    kpe: ["易错", "#c98a2e", "#fdf6ec"]
  };
  var selfSrc = (document.currentScript && document.currentScript.src) || "";
  // 资源基址：优先从 kg.js 自身 URL 推导（页面无 kg-data 时也能用，如考点页）
  var BASE = selfSrc ? selfSrc.replace(/assets\/kg\.js[^/]*$/, "") : "";
  function asset(p) { return (BASE || ((KG && KG.base) || "")) + p; }
  function T(t, i, def) { var v = TYPES[t]; return v && v[i] != null ? v[i] : def; }

  var KG = null;
  var dataEl = $("#kg-data");
  if (dataEl) { try { KG = JSON.parse(dataEl.textContent); } catch (e) { KG = null; } }

  /* ---------------- KaTeX 懒加载（仅当真有公式节点） ---------------- */
  var katexState = 0, katexCbs = [];
  function hasTex(node) {
    var hit = false;
    (function w(n) { if (!n) { return; } if (n.tex) { hit = true; } (n.children || []).forEach(w); })(node);
    return hit;
  }
  function loadKatex(cb) {
    if (katexState === 2) { cb(); return; }
    katexCbs.push(cb);
    if (katexState === 1) { return; }
    katexState = 1;
    var css = document.createElement("link");
    css.rel = "stylesheet"; css.href = asset("assets/katex/katex.min.css");
    document.head.appendChild(css);
    var js = document.createElement("script");
    js.src = asset("assets/katex/katex.min.js");
    js.onload = function () { katexState = 2; katexCbs.splice(0).forEach(function (f) { f(); }); };
    js.onerror = function () { katexState = 0; };
    document.head.appendChild(js);
  }

  /* ---------------- 导图 ---------------- */
  var COL = 300, GAP = 9, DEFH = 36;
  var svg, g, linkG, nodeG, ZOOM, root = null, H = {}, pass = 0, curTree = null;

  function initD3() {
    svg = d3.select("#svg"); g = d3.select("#g");
    linkG = g.append("g"); nodeG = g.append("g");
    ZOOM = d3.zoom().scaleExtent([0.04, 3]).on("zoom", function (e) { g.attr("transform", e.transform); });
    svg.call(ZOOM);
    var nd = svg.node();
    nd.addEventListener("mousedown", function () { nd.classList.add("grabbing"); });
    window.addEventListener("mouseup", function () { nd.classList.remove("grabbing"); });
    $$("[data-zoom]").forEach(function (b) {
      b.onclick = function () {
        var k = d3.zoomTransform(svg.node()).k, f = b.dataset.zoom === "in" ? 1.3 : 1 / 1.3;
        svg.transition().duration(180).call(ZOOM.scaleBy, f);
      };
    });
    var fb = $("[data-fit]"); if (fb) { fb.onclick = function () { fitView(); }; }
    $$("[data-depth]").forEach(function (b) {
      b.onclick = function () {
        setDepth(parseInt(b.dataset.depth, 10));
        $$("[data-depth]").forEach(function (x) { x.classList.toggle("on", x === b); });
      };
    });
    var q = $("#map-q");
    if (q) { q.oninput = function () { applySearch(q.value.trim()); }; }
  }

  function buildRoot(tree) {
    curTree = tree;
    root = d3.hierarchy(tree);
    var u = 0;
    (function tag(n) { n.uid = "n" + (u++); (n.children || []).forEach(tag); })(tree);
    H = {}; pass = 0;
  }

  function layout() {
    d3.tree().nodeSize([1, 1])(root);
    var cur = 0, pos = new Map();
    (function pack(n) {
      if (!n.children || !n.children.length) {
        var h = H[n.data.uid] || DEFH;
        pos.set(n, cur + h / 2); cur += h + GAP; return;
      }
      n.children.forEach(pack);
      pos.set(n, (pos.get(n.children[0]) + pos.get(n.children[n.children.length - 1])) / 2);
    })(root);
    root.each(function (n) { n.yy = pos.get(n); n.xx = n.depth * COL; });
  }
  function nodeH(d) { return H[d.data.uid] || DEFH; }

  function draw() {
    if (!root) { return; }
    layout();
    var nodes = root.descendants(), links = root.links();
    var ymin = d3.min(nodes, function (d) { return d.yy; });
    var ymax = d3.max(nodes, function (d) { return d.yy; });
    var mid = (ymin + ymax) / 2;

    linkG.selectAll("path").data(links, function (d) { return d.target.data.uid; })
      .join("path").attr("class", "link")
      .attr("d", function (d) {
        var y0 = d.source.yy - mid, y1 = d.target.yy - mid;
        var x0 = d.source.xx + 8, x1 = d.target.xx - 4, mx = (x0 + x1) / 2;
        return "M" + x0 + "," + y0 + "C" + mx + "," + y0 + " " + mx + "," + y1 + " " + x1 + "," + y1;
      });

    var sel = nodeG.selectAll("g.nd").data(nodes, function (d) { return d.data.uid; });
    sel.exit().remove();
    var ent = sel.enter().append("g").attr("class", "nd");
    ent.on("click", function (ev, d) {
      if (d.children) { d._children = d.children; d.children = null; }
      else if (d._children) { d.children = d._children; d._children = null; }
      else { return; }
      ev.stopPropagation(); pass = 0; draw();
    });
    ent.append("foreignObject").append("xhtml:div").attr("class", "box");

    var all = ent.merge(sel);
    all.select("foreignObject")
      .attr("x", function (d) { return d.xx; })
      .attr("y", function (d) { return d.yy - mid - nodeH(d) / 2 - 12; })
      .attr("width", 296)
      .attr("height", function (d) { return nodeH(d) + 24; });

    all.select(".box")
      .attr("class", function (d) { return "box" + (d.data.own ? " own" : ""); })
      .style("background", function (d) { return T(d.data.type, 2, "#eef1f4"); })
      .style("border-color", function (d) { return T(d.data.type, 1, "#999"); })
      .style("color", function (d) { return d.data.type === "root" ? "#fff" : "#243238"; })
      .each(function (d) {
        var boxd = d3.select(this);
        boxd.selectAll("*").remove();
        if (d.data.type === "fm") {
          var sp = boxd.append("span").text(d.data.tex || "");
          loadKatex(function () {
            try {
              window.katex.render(d.data.tex, sp.node(), { displayMode: false, throwOnError: false, strict: false, trust: true });
            } catch (err) { /* 保持纯文本 */ }
          });
          return;
        }
        var tg = T(d.data.type, 0, "");
        if (tg) {
          boxd.append("span").attr("class", "tag").style("color", T(d.data.type, 1, "#666")).text(tg);
        }
        boxd.append("span").text(d.data.label || "");
        if (d.data.sub) { boxd.append("div").attr("class", "sub").text(d.data.sub); }
      });

    if (pass === 0) {                       // 第一遍：量出每个盒子的真实高度再重排
      var m = {};
      nodeG.selectAll("g.nd").each(function (d) {
        var b = this.querySelector(".box");
        m[d.data.uid] = b ? Math.ceil(b.getBoundingClientRect().height) + 12 : DEFH;
      });
      H = m; pass = 1; draw(); return;
    }
    applySearch(($("#map-q") || {}).value ? $("#map-q").value.trim() : "");
  }

  function setDepth(depth) {
    if (!root) { return; }
    root.each(function (d) {
      if (d.depth < depth) {
        if (d._children) { d.children = d._children; d._children = null; }
      } else if (d.children) { d._children = d.children; d.children = null; }
    });
    pass = 0; draw();
    setTimeout(function () { fitView(); }, 60);
  }

  function fitView() {
    if (!root) { return; }
    var nodes = root.descendants();
    var y0 = d3.min(nodes, function (d) { return d.yy - nodeH(d) / 2; });
    var y1 = d3.max(nodes, function (d) { return d.yy + nodeH(d) / 2; });
    var x1 = d3.max(nodes, function (d) { return d.xx; });
    var w = svg.node().clientWidth || 800, h = svg.node().clientHeight || 600;
    var bw = x1 + 360, bh = (y1 - y0) + 90;
    var top = 54, bot = 12;              // 给左上角浮动工具栏/底部提示留位，避免盖住节点
    var hh = Math.max(120, h - top - bot);
    var k = Math.max(0.06, Math.min(w / bw, hh / bh, 1.05));
    // draw() 已把内容居中到 y=0（mid 偏移），此处把内容放回「工具栏以下」区域中心
    var ty = top + hh / 2 + 6;
    var tx = Math.max(16, (w - k * bw) / 2);   // 高度受限时水平居中，避免右侧大片空白
    try {
      document.documentElement.setAttribute("data-kgfit",
        "w=" + Math.round(w) + " h=" + Math.round(h) + " bw=" + Math.round(bw) + " bh=" + Math.round(bh) +
        " k=" + k.toFixed(3) + " nodes=" + nodes.length);
    } catch (e) { /* ignore */ }
    svg.transition().duration(280).call(ZOOM.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
  }

  function applySearch(q) {
    if (!root) { return; }
    nodeG.selectAll("g.nd").classed("hit", false).classed("dim", false);
    if (!q) { return; }
    var hit = new Set();
    root.each(function (d) {
      var s = (d.data.label || "") + " " + (d.data.tex || "") + " " + (d.data.sub || "");
      if (s.indexOf(q) >= 0) { d.ancestors().forEach(function (a) { hit.add(a); }); d.descendants().forEach(function (a) { hit.add(a); }); }
    });
    nodeG.selectAll("g.nd").each(function (d) {
      d3.select(this).classed(hit.has(d) ? "hit" : "dim", true);
    });
  }

  /* ---------------- 切题 / 视图切换 ---------------- */
  var mode = null;
  function setMode(m) {
    mode = m;
    var mapw = $("#mapwrap"), content = $("#content");
    if (m === "map") {
      mapw.hidden = false; content.hidden = true;
      if (!svg) { initD3(); }
      renderQ(); svg.call(ZOOM.transform, d3.zoomIdentity); fitView();
    } else {
      mapw.hidden = true; content.hidden = false;
    }
    $$("[data-mode]").forEach(function (b) { b.classList.toggle("on", b.dataset.mode === m); });
    try { localStorage.setItem("kg-mode", m); } catch (e) { /* 隐私模式 */ }
  }

  var curQ = "all";
  function renderQ() {
    if (mode !== "map") { return; }
    var tree = curQ === "all" ? KG.full : (KG.qs[parseInt(curQ, 10) - 1] || {}).tree;
    if (!tree) { return; }
    var same = curTree && curTree.label === tree.label;
    buildRoot(tree);
    if (!same) { $$("[data-depth]").forEach(function (x) { x.classList.remove("on"); }); }
    draw(); fitView();
  }

  function selectQ(q, push) {
    curQ = String(q);
    $$("#qtabs .qt").forEach(function (b) { b.classList.toggle("on", b.dataset.q === curQ); });
    $$("#content .qcard").forEach(function (c) { c.classList.toggle("sel", c.dataset.q === curQ); });
    if (mode === "map") {
      renderQ();
    } else {
      // 大纲模式：滚到该题（此前只加高亮类、不滚动，用户感觉"点了没反应"）
      var anchor = (q === "all") ? $("#content")
                 : document.querySelector('#content .qcard[data-q="' + q + '"]');
      if (anchor) {
        // scrollIntoView + CSS scroll-margin-top 让开粘性顶栏；700ms 未到位则直接跳（部分环境平滑滚动不生效）
        var tY = Math.max(0, anchor.getBoundingClientRect().top + window.pageYOffset - 74);
        try { anchor.scrollIntoView({ behavior: "smooth", block: "start" }); }
        catch (e) { window.scrollTo(0, tY); }
        setTimeout(function () {
          if (Math.abs(window.pageYOffset - tY) > 8) { window.scrollTo(0, tY); }
        }, 700);
      }
    }
    if (push !== false) {
      try { history.replaceState(null, "", curQ === "all" ? location.pathname : "#q" + curQ); } catch (e) { /* file:// */ }
    }
  }

  /* ---------------- 启动 ---------------- */
  function boot() {
    if (!KG) { if ($("#mapwrap")) { report("no #kg-data"); } return; }
    var isWide = window.matchMedia("(min-width: 981px)").matches;
    var saved = null;
    try { saved = localStorage.getItem("kg-mode"); } catch (e) { saved = null; }
    setMode(saved || (isWide ? "map" : "outline"));

    $$("[data-mode]").forEach(function (b) { b.onclick = function () { setMode(b.dataset.mode); }; });
    $$("#qtabs .qt").forEach(function (b) { b.onclick = function () { selectQ(b.dataset.q); }; });

    var fsm = $("#mapwrap"), fsb = $("#btn-full");
    if (fsb && fsm) {
      fsb.onclick = function () {
        if (document.fullscreenElement) { document.exitFullscreen(); return; }
        // 大纲模式下 #mapwrap 是 hidden：对隐藏元素全屏会得到空白全屏（表现为"卡死"）→ 先切回导图
        if (fsm.hidden) { setMode("map"); }
        try {
          var pr = fsm.requestFullscreen ? fsm.requestFullscreen() : null;
          if (pr && pr.catch) { pr.catch(function () { fsm.classList.add("fs-fallback"); }); }
        } catch (e) { fsm.classList.add("fs-fallback"); }
      };
      var exitfs = $("#btn-exitfs");
      if (exitfs) {
        exitfs.onclick = function () {
          if (document.fullscreenElement) { document.exitFullscreen(); }
          else { fsm.classList.remove("fs-fallback"); }
        };
      }
      document.addEventListener("fullscreenchange", function () {
        fsb.classList.toggle("on", !!document.fullscreenElement);
        if (exitfs) { exitfs.hidden = !document.fullscreenElement; }
        if (mode === "map") { setTimeout(fitView, 80); }
      });
    }
    window.addEventListener("resize", function () { if (mode === "map") { fitView(); } });

    var hi = $(".head-inp");
    if (hi && !$("#kg-grid")) {
      hi.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" && hi.value.trim()) {
          var brand = $("a.brand");
          var base = brand ? brand.getAttribute("href") : "./";
          location.href = base + "?q=" + encodeURIComponent(hi.value.trim());
        }
      });
    }

    var h = (location.hash || "").match(/^#q(\d+)$/);
    if (h) { selectQ(h[1], false); }
    else { selectQ("all", false); }

    // 首次进入的默认展开层级：整卷看板块，单题看到考点
    if (mode === "map") {
      var d0 = (curQ === "all") ? 1 : 2;
      setDepth(d0);
      $$("[data-depth]").forEach(function (x) { x.classList.toggle("on", parseInt(x.dataset.depth, 10) === d0); });
    }

    // 面包屑之外：题锚点点击后同步切题
    $$("#content .anchorlink").forEach(function (a) {
      a.onclick = function () { selectQ(a.dataset.q, true); };
    });
  }

  /* ---------------- 索引页筛选（分级 / 年份 / 代码 / 搜索 / 排序） ---------------- */
  function bootIndex() {
    var grid = $("#kg-grid");
    if (!grid) { return; }
    var bar = $("#kg-filter");
    var cards = $$(".scard", grid);
    if (!cards.length) { return; }
    // 顶栏与筛选器各有一个搜索框：两个都要绑（曾因都叫 #site-q，$ 只拿到第一个 → 筛选器里的输入无效）
    var qInputs = $$("#kg-q, .head-inp");
    var q = qInputs[0] || null;
    var codeSel = $("#kg-code"), kpSel = $("#kg-kp"), sortSel = $("#kg-sort"),
        clearBtn = $("#kg-clear"), res = $("#kg-result"), empty = $("#kg-empty");
    var st = { tier: "", year: "", code: "", kp: "", q: "", sort: "tier" };

    // 从 URL 恢复筛选状态（可分享链接）
    try {
      var pr = new URLSearchParams(location.search);
      ["tier", "year", "code", "kp", "q", "sort"].forEach(function (k) { if (pr.get(k)) { st[k] = pr.get(k); } });
    } catch (e) { /* ignore */ }

    function syncUrl() {
      try {
        // 从现有 query 出发，只增删本页管理的筛选参数——否则会把 ?debug=1 / utm_* 等无关参数一并抹掉
        var pr = new URLSearchParams(location.search);
        ["tier", "year", "code", "kp", "q", "sort"].forEach(function (k) {
          if (st[k]) { pr.set(k, st[k]); } else { pr.delete(k); }
        });
        var qs = pr.toString();
        history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
      } catch (e) { /* file:// 下忽略 */ }
    }

    function markChips(group, val) {
      if (!bar) { return; }
      $$('[data-' + group + ']', bar).forEach(function (b) {
        b.classList.toggle("on", (b.getAttribute("data-" + group) || "") === (val || ""));
      });
    }

    function apply(sortIt) {
      var nCards = 0, nSets = 0, active = !!(st.tier || st.year || st.code || st.kp || st.q), nq = st.q.toLowerCase();
      cards.forEach(function (c) {
        var ok = true;
        if (st.tier && c.dataset.tier !== st.tier) { ok = false; }
        if (ok && nq && (c.dataset.k || "").toLowerCase().indexOf(nq) < 0) { ok = false; }
        if (ok && st.kp && ("," + (c.dataset.kps || "") + ",").indexOf("," + st.kp + ",") < 0) { ok = false; }
        var chips = $$(".yearchip", c), shown = 0, setLevel = !!(st.year || st.code || st.kp);
        chips.forEach(function (ch) {
          var vis = (!st.year || ch.getAttribute("data-year") === st.year) &&
                    (!st.code || ch.getAttribute("data-code") === st.code) &&
                    (!st.kp || ("," + (ch.getAttribute("data-kps") || "") + ",").indexOf("," + st.kp + ",") >= 0);
          ch.classList.toggle("off", !vis);
          if (vis) { shown++; }
        });
        if (ok && setLevel) { ok = shown > 0; }
        c.classList.toggle("off", !ok);
        if (ok) { nCards++; nSets += shown; }   // chip = 一套卷（全部年份都渲染，计数即真实套数）
      });
      grid.classList.toggle("filtered", active);
      qInputs.forEach(function (el) { if (el.value !== st.q) { el.value = st.q; } });
      if (res) { res.innerHTML = "共 <b>" + nCards + "</b> 所院校 · <b>" + nSets + "</b> 套卷"; }
      if (empty) { empty.hidden = nCards > 0; }
      if (clearBtn) { clearBtn.classList.toggle("on", active); }

      if (sortIt) {
        var vis = cards.slice().sort(function (a, b) {
          if (st.sort === "count") { return (+b.dataset.sets || 0) - (+a.dataset.sets || 0); }
          if (st.sort === "name") { return (a.dataset.k || "").localeCompare(b.dataset.k || "", "zh"); }
          var o = { "985": 0, "211": 1, "强势双非": 2 };
          var d = (o[a.dataset.tier] || 9) - (o[b.dataset.tier] || 9);
          return d !== 0 ? d : (a.dataset.k || "").localeCompare(b.dataset.k || "", "zh");
        });
        vis.forEach(function (c) { grid.appendChild(c); });
      }
      syncUrl();
    }

    function bindChips(group, key) {
      if (!bar) { return; }
      $$('[data-' + group + ']', bar).forEach(function (b) {
        b.addEventListener("click", function () {
          st[key] = b.getAttribute("data-" + group) || "";
          markChips(group, st[key]);
          apply(false);
        });
      });
    }
    bindChips("tier", "tier");
    bindChips("year", "year");

    var sbtn = $("#kg-search-btn"), head = $(".site-head");
    if (sbtn && head) {
      sbtn.addEventListener("click", function () {
        var open = head.classList.toggle("search-open");
        if (open && q) { q.focus(); }
      });
    }
    qInputs.forEach(function (el) {
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
    });
    if (codeSel) {
      codeSel.value = st.code || "";
      codeSel.addEventListener("change", function () { st.code = codeSel.value; apply(false); });
    }
    if (kpSel) {
      kpSel.value = st.kp || "";
      kpSel.addEventListener("change", function () { st.kp = kpSel.value; apply(false); });
    }
    if (sortSel) {
      sortSel.value = st.sort || "tier";
      sortSel.addEventListener("change", function () { st.sort = sortSel.value; apply(true); });
    }
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        st.tier = ""; st.year = ""; st.code = ""; st.kp = ""; st.q = "";
        qInputs.forEach(function (el) { el.value = ""; });
        if (codeSel) { codeSel.value = ""; }
        if (kpSel) { kpSel.value = ""; }
        markChips("tier", ""); markChips("year", "");
        apply(true);
      });
    }

    markChips("tier", st.tier); markChips("year", st.year);
    apply(true);
  }

  /* ---------------- 静态公式（考点页 / 卷页的 .formula[data-tex]） ---------------- */
  function bootFormulas() {
    var nodes = $$(".formula[data-tex]");
    if (!nodes.length) { return; }
    loadKatex(function () {
      nodes.forEach(function (n) {
        try {
          window.katex.render(n.dataset.tex, n, { displayMode: false, throwOnError: false, strict: false, trust: true });
        } catch (e) { n.textContent = n.dataset.tex; }
      });
    });
  }

  /* ---------------- 调试：?debug=1 时列出撑宽页面的元素 ---------------- */
  function selfTestSearch() {
    if (!/[?&]debug=1/.test(location.search)) { return; }
    var box = $("#kg-q") || $(".head-inp"), grid = $("#kg-grid");
    if (!box || !grid) { return; }
    var before = $$(".scard", grid).filter(function (c) { return !c.classList.contains("off"); }).length;
    box.value = "天津";
    box.dispatchEvent(new Event("input", { bubbles: true }));
    var vis = function () { return $$(".scard", grid).filter(function (c) { return !c.classList.contains("off"); }).length; };
    var msg = [];
    setTimeout(function () {
      msg.push("q=天津 " + before + "→" + vis() + "（框 id=" + (box.id || box.className) + "）");
      box.value = ""; box.dispatchEvent(new Event("input", { bubbles: true }));
      setTimeout(function () {
        var cs = $("#kg-code");
        if (cs) { cs.value = "812"; cs.dispatchEvent(new Event("change", { bubbles: true })); msg.push("代码=812 →" + vis()); cs.value = ""; cs.dispatchEvent(new Event("change", { bubbles: true })); }
        var ks = $("#kg-kp");
        if (ks) { ks.value = "rl_02"; ks.dispatchEvent(new Event("change", { bubbles: true })); msg.push("考点=rl_02 →" + vis()); }
        report("SELFTEST " + msg.join(" | ") + "（全量=" + before + "）");
      }, 400);
    }, 500);
  }

  function selfTestSet() {
    if (!/[?&]debug=1/.test(location.search)) { return; }
    var tabs = $$("#qtabs .qt");
    if (!tabs.length) { return; }
    var msg = [];
    // 先切到大纲模式（宽屏默认是导图）
    var ob = document.querySelector('[data-mode="outline"]');
    if (ob) { ob.click(); }
    setTimeout(function () {
      var y0 = window.pageYOffset;
      var t3 = tabs[Math.min(3, tabs.length - 1)];
      var want = t3.dataset.q;
      t3.click();
      setTimeout(function () {
        var card = document.querySelector('#content .qcard[data-q="' + want + '"]');
        var dy = window.pageYOffset - y0;
        var samples = [window.pageYOffset];
        setTimeout(function () { samples.push(window.pageYOffset); }, 400);
        setTimeout(function () { samples.push(window.pageYOffset); }, 1000);
        setTimeout(function () {
          var aligned = card ? Math.abs(card.getBoundingClientRect().top - 74) < 60 : false;
          msg.push("大纲点第" + want + "题 scrollY " + y0 + "→" + samples.join("/") +
                   " 该题rect.top=" + (card ? Math.round(card.getBoundingClientRect().top) : "null") +
                   " 期望≈74 判定=" + aligned);
          finish();
        }, 1400);
        function finish() {
        var errs = [];
        window.addEventListener("error", function (e) { errs.push(e.message); });
        var fsb = $("#btn-full");
        if (fsb) { fsb.click(); }
        setTimeout(function () {
          var fs = !!document.fullscreenElement, fb = document.querySelector("#mapwrap").classList.contains("fs-fallback");
          msg.push("大纲点全屏 → fullscreen=" + fs + " fallback=" + fb + " 页面未卡死=yes 错误=" + (errs.length ? errs.join(";") : "无"));
          var ex = $("#btn-exitfs");
          if (ex) { ex.click(); }
          setTimeout(function () {
            msg.push("退出后 fullscreen=" + !!document.fullscreenElement);
            report("SETTEST " + msg.join(" | "));
          }, 400);
        }, 900);
        }
      }, 700);
    }, 300);
  }

  function scanOverflow() {
    if (!/[?&]debug=1/.test(location.search)) { return; }
    var vw = document.documentElement.clientWidth, out = [];
    $$("body *").forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) { return; }
      if (r.right > vw + 1) {
        out.push((el.tagName || "").toLowerCase() + "." + String(el.className || "").split(" ")[0] +
                 "[w=" + Math.round(r.width) + ",r=" + Math.round(r.right) + "]");
      }
    });
    var probe = "";
    var tg = document.querySelector(".kplink .ktag"), lk = document.querySelector(".kplink");
    if (tg) { var c1 = getComputedStyle(tg); probe += " ktag[color=" + c1.color + " bg=" + c1.backgroundColor + " fs=" + c1.fontSize + "]"; }
    if (lk) { var c2 = getComputedStyle(lk); probe += " kplink[color=" + c2.color + "]"; }
    var mw = document.getElementById("mapwrap");
    if (mw) {
      var r1 = mw.getBoundingClientRect(); probe += " mapwrap[x=" + Math.round(r1.left) + " y=" + Math.round(r1.top) +
        " w=" + Math.round(r1.width) + " h=" + Math.round(r1.height) + "]";
    }
    var de = document.documentElement, bd = document.body;
    report("OVERFLOW vw=" + vw + " docScrollW=" + de.scrollWidth + " bodyScrollW=" + bd.scrollWidth +
           probe + " | " + out.slice(0, 6).join(" | "));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      boot(); bootIndex(); bootFormulas(); scanOverflow(); selfTestSearch(); selfTestSet();
    });
  } else { boot(); bootIndex(); bootFormulas(); scanOverflow(); selfTestSearch(); selfTestSet(); }
})();
