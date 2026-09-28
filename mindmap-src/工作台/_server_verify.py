# -*- coding: utf-8 -*-
"""同步后的服务器校验（纯 ASCII 输出，避免 Windows 控制台编码崩溃）。

校验项：① 关键文件 md5（本地 vs 服务器）② 服务器本机 HTTP 状态
        ③ 关键内容是否生效 ④ 页面/文件计数
"""
import hashlib, re
from pathlib import Path
import paramiko

LOCAL = Path(r"D:/ZeXiao")
SITE = LOCAL / "真题思维导图"
SRC = LOCAL / ".qrcheck" / "sync_upload.py"
txt = SRC.read_text(encoding="utf-8", errors="replace")
H = re.search(r"(?:^|[;\s])H\s*=\s*['\"]([^'\"]+)", txt).group(1)
U = re.search(r"(?:^|[;\s])U\s*=\s*['\"]([^'\"]+)", txt).group(1)
P = re.search(r"(?:^|[;\s])P\s*=\s*['\"]([^'\"]+)", txt).group(1)
ROOT = re.search(r"(?:^|[;\s])ROOT\s*=\s*['\"]([^'\"]+)", txt).group(1)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(H, 22, U, P, timeout=30)


def run(cmd, sudo=False, timeout=300):
    if sudo:
        cmd = "printf '%s\n' " % P + "| sudo -S -p '' bash -c " + repr(cmd)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    return (o.read().decode("utf-8", "ignore") + e.read().decode("utf-8", "ignore")).strip()


print("== (1) md5: local vs server ==")
checks = ["index.html", "assets/kg.js", "assets/kg.css", "assets/sets.js",
          "x/985/tianjin/2020/812/index.html", "x/985/tianjin/2020/index.html",
          "k/rl_02/index.html", "nav-data.js", "真题备考区.html", "移动端实时预览.html"]
bad = 0
for rel in checks:
    lf = (SITE / rel) if rel not in ("nav-data.js", "真题备考区.html", "移动端实时预览.html") else (LOCAL / rel)
    lm = hashlib.md5(lf.read_bytes()).hexdigest() if lf.is_file() else "(missing-local)"
    rpath = ("%s/真题思维导图/%s" % (ROOT, rel)) if rel not in ("nav-data.js", "真题备考区.html", "移动端实时预览.html") else ("%s/%s" % (ROOT, rel))
    rm = run("md5sum '%s' 2>/dev/null | cut -d' ' -f1" % rpath)
    ok = (lm == rm)
    bad += 0 if ok else 1
    print("  %-6s %-42s %s / %s" % ("[OK]" if ok else "[DIFF]", rel, lm[:12], rm[:12] or "(none)"))

print("\n== (2) server-side HTTP ==")
for u in ("/", "/真题备考区.html", "/真题思维导图/", "/真题思维导图/x/985/tianjin/2020/812/",
          "/真题思维导图/x/985/tianjin/2020/", "/真题思维导图/x/985/nankai/2020/",
          "/真题思维导图/k/", "/真题思维导图/k/rl_02/",
          "/真题思维导图/assets/kg.js", "/真题思维导图/assets/sets.js",
          "/真题思维导图/assets/logo/tianjin.jpg"):
    code = run("curl -sk -o /dev/null -w '%%{http_code}' --max-time 15 'https://%s%s'" % ("kzkyzx.wanrenjiaoyu.com", u))
    print("  %-4s %s" % (code, u))

print("\n== (3) content live ==")
print("  nav-data 新条目      :", run("grep -c '真题思维导图/index.html' %s/nav-data.js" % ROOT))
print("  真题备考区 入口      :", run("grep -c '真题思维导图/index.html' %s/真题备考区.html" % ROOT))
print("  移动预览 预设        :", run("grep -c '真题思维导图' %s/移动端实时预览.html" % ROOT))
print("  首页 title           :", run("grep -o '<title>[^<]*' %s/真题思维导图/index.html | head -1" % ROOT))
print("  卷页 title           :", run("grep -o '<title>[^<]*' '%s/真题思维导图/x/985/tianjin/2020/812/index.html' | head -1" % ROOT))
print("  合计分规则(北航873)  :", run("grep -c 'badge\">合计' '%s/真题思维导图/x/985/beijinghangkonghangtian/2015/873/index.html'" % ROOT))

print("\n== (4) counts ==")
print("  目录总文件数         :", run("find %s/真题思维导图 -type f | wc -l" % ROOT))
print("  x/ 下 index.html     :", run("find %s/真题思维导图/x -name index.html | wc -l" % ROOT), "(应 879 卷页 + 840 旧路径兼容 = 1719)")
print("  k/ 下 index.html     :", run("find %s/真题思维导图/k -name index.html | wc -l" % ROOT), "(应 103 考点页 + 1 索引 = 104)")
print("  磁盘占用             :", run("du -sh %s/真题思维导图" % ROOT))
print("\nmd5 不符项: %d" % bad)
