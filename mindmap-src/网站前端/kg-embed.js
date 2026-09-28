/* 控制考研真题思维导图 - 嵌入片段（iframe 方式：最省事，但不利于 SEO 收录）
   用法：
     <div data-kg-embed="天津大学_812_2020" data-h="760"></div>
     <script src="https://你们的域名.com/kaoyan/assets/kg-embed.js"></script>
   也可直接给路径：<div data-kg-path="/x/985/tianjin/2020/"></div>
   收录建议：要 SEO 请用「整目录部署 + 内链进入」或「片段挂载」，不建议只用 iframe。 */
(function () {
  "use strict";
  var me = document.currentScript || (function () { var s = document.getElementsByTagName("script"); return s[s.length - 1]; })();
  var KG_ROOT = "";   // 例："https://你们的域名.com/kaoyan/"；留空则按脚本自身 URL 推导
  var base = KG_ROOT || (me && me.src ? me.src.replace(/assets\/kg-embed\.js[^/]*$/, "") : "");

  var MAN = null, waiters = [];

  function loadManifest(cb) {
    if (MAN) { cb(MAN); return; }
    if (window.KG_SETS) { MAN = window.KG_SETS; cb(MAN); return; }
    waiters.push(cb);
    if (waiters.length > 1) { return; }
    var s = document.createElement("script");
    s.src = base + "assets/sets.js";
    s.onload = function () { MAN = window.KG_SETS || {}; waiters.splice(0).forEach(function (f) { f(MAN); }); };
    s.onerror = function () { MAN = {}; waiters.splice(0).forEach(function (f) { f(MAN); }); };
    document.head.appendChild(s);
  }

  function notice(box, text, href) {
    var d = document.createElement("div");
    d.style.cssText = "border:1px solid #e4e9ef;border-radius:12px;padding:16px;background:#fff;font:14px/1.6 system-ui,sans-serif;color:#5b6b7a";
    d.textContent = text;
    if (href) {
      d.appendChild(document.createElement("br"));
      var a = document.createElement("a");
      a.href = href; a.textContent = href; a.style.color = "#1f4e79";
      d.appendChild(a);
    }
    box.appendChild(d);
  }

  function mount(box) {
    if (box.dataset.kgDone) { return; }
    box.dataset.kgDone = "1";
    var key = box.getAttribute("data-kg-embed") || "";
    var direct = box.getAttribute("data-kg-path") || "";
    var h = parseInt(box.getAttribute("data-h") || "740", 10);

    function draw(path) {
      if (!path) {
        notice(box, "找不到这套卷（key：" + key + "），也可改用 data-kg-path 直接指定路径。", base);
        return;
      }
      var f = document.createElement("iframe");
      f.src = base + String(path).replace(/^\//, "");
      f.loading = "lazy";
      f.style.cssText = "width:100%;height:" + h + "px;border:1px solid #e4e9ef;border-radius:12px;background:#fff";
      f.setAttribute("title", "控制考研真题思维导图");
      box.appendChild(f);
    }

    if (direct) { draw(direct); return; }
    loadManifest(function (m) { draw(m[key]); });
  }

  function boot() {
    var boxes = document.querySelectorAll("[data-kg-embed]");
    for (var i = 0; i < boxes.length; i++) { mount(boxes[i]); }
  }
  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", boot); } else { boot(); }
})();
