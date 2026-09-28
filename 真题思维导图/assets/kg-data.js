/* 考情数据 · 自测清单交互
   数据：window.KGD = { sch:[校名], pth:[校路径前缀], nm:[题名], kp:{ref:{n,c,rows:[[年,校序,代码,题号,题名序,分值,题序]]}}, years:[...] }
   交互：勾选考点 → 汇总"历年考法清单"（按考点分组，可打印）；?kp=a,b 深链预选；?debug=1 自检 */
(function () {
  "use strict";
  var D = window.KGD;
  if (!D) { return; }
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var picked = {};
  var out = $("#list"), cnt = $("#cnt"), btnAll = $("#btn-all"), btnNone = $("#btn-none");

  function render() {
    var refs = Object.keys(picked).filter(function (r) { return picked[r]; });
    var rows = [];
    refs.sort(function (a, b) { return (D.kp[b].rows.length - D.kp[a].rows.length); });
    refs.forEach(function (r) {
      var kp = D.kp[r];
      rows.push('<h3 class="lgroup">' + esc(kp.n) + '　<span class="tiny muted">' + esc(kp.c) +
                ' · ' + kp.rows.length + ' 处题</span></h3>');
      rows.push('<table class="ltable"><thead><tr><th>年份</th><th>院校</th><th>题</th><th>分值</th></tr></thead><tbody>');
      kp.rows.forEach(function (x) {
        var href = (D.pth[x[1]] || "") + x[0] + "/" + x[2] + "/#q" + x[6];
        rows.push('<tr><td class="y">' + esc(x[0]) + '</td>' +
                  '<td><a href="' + href + '">' + esc(D.sch[x[1]] || "") + '</a></td>' +
                  '<td>' + esc(x[3] + (D.nm[x[4]] ? '　' + D.nm[x[4]] : '')) + '</td>' +
                  '<td class="y">' + esc(x[5] || '—') + '</td></tr>');
      });
      rows.push('</tbody></table>');
    });
    out.innerHTML = rows.length ? rows.join("") :
      '<p class="muted">勾选上面的考点，这里会生成"这个考点历年在哪些学校哪一年哪道题考过"的清单，可直接打印。</p>';
    if (cnt) { cnt.textContent = refs.length + " 个考点 / " + refs.reduce(function (a, r) { return a + D.kp[r].rows.length; }, 0) + " 处题"; }
    syncUrl();
  }

  // URL 同步：只增量增删 kp 参数，不碰 debug / utm / hash（避免把 ?debug=1 抹掉）
  function syncUrl() {
    try {
      var u = new URL(location.href);
      var on = Object.keys(picked).filter(function (r) { return picked[r]; });
      if (on.length) { u.searchParams.set("kp", on.join(",")); } else { u.searchParams.delete("kp"); }
      history.replaceState(null, "", u.pathname + (u.search || "") + (u.hash || ""));
    } catch (e) { /* 老浏览器忽略 */ }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  $$(".kpick").forEach(function (box) {
    box.addEventListener("change", function () { picked[box.dataset.ref] = box.checked; render(); });
  });
  if (btnAll) { btnAll.onclick = function () { $$(".kpick").forEach(function (b) { b.checked = true; picked[b.dataset.ref] = true; }); render(); }; }
  if (btnNone) { btnNone.onclick = function () { $$(".kpick").forEach(function (b) { b.checked = false; picked[b.dataset.ref] = false; }); render(); }; }
  var pb = $("#btn-print");
  if (pb) { pb.onclick = function () { window.print(); }; }

  // 深链：?kp=rl_02,td_03 预选（派发真实 change 事件，走和用户点击同一条路径）
  (function () {
    var pre = [];
    try { pre = ((new URL(location.href)).searchParams.get("kp") || "").split(","); } catch (e) { pre = []; }
    pre = pre.filter(function (r) { return r && D.kp[r]; });
    if (!pre.length) { return; }
    $$(".kpick").forEach(function (b) {
      if (pre.indexOf(b.dataset.ref) >= 0) {
        b.checked = true;
        b.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  })();

  render();

  // ?debug=1 自检：结果写到 body[data-kgdtest]，供无头浏览器读取
  if (/[?&]debug=1/.test(location.search)) {
    var lg = [];
    try {
      var boxes = $$(".kpick");
      boxes[0].checked = true;
      boxes[0].dispatchEvent(new Event("change", { bubbles: true }));
      var t1 = $$("#list .ltable").length, r1 = $$("#list .ltable tbody tr").length;
      var want = D.kp[boxes[0].dataset.ref].rows.length;
      lg.push("勾1个 ref=" + boxes[0].dataset.ref + " 表=" + t1 + " 行=" + r1 + "/" + want + " 判定=" + (t1 === 1 && r1 === want));
      var lnk = $("#list .ltable tbody a");
      lg.push("行链接=" + (lnk ? lnk.getAttribute("href") : "无"));
      $("#btn-all").click();
      lg.push("全选 表=" + $$("#list .ltable").length + "/" + boxes.length + " 判定=" + ($$("#list .ltable").length === boxes.length));
      $("#btn-none").click();
      lg.push("清空 表=" + $$("#list .ltable").length + " 判定=" + ($$("#list .ltable").length === 0));
      lg.push("kp参数已清=" + !((new URL(location.href)).searchParams.get("kp")));
    } catch (e) { lg.push("错误=" + e.message); }
    document.body.setAttribute("data-kgdtest", lg.join(" | "));
  }
})();
