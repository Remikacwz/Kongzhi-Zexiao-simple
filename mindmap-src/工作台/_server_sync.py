# -*- coding: utf-8 -*-
"""把导图站的改动同步到生产服务器。

方式（沿用 .qrcheck 既有脚本的模式）：
  ① 本地打包 真题思维导图/ → 传到服务器 /tmp/<ts>/
  ② 服务器端先备份（旧目录/被覆盖的单文件 → /root/kaoyan-mindmap-<ts>/）
  ③ sudo 解包到 /var/www/kaoyan-site/真题思维导图 + 覆盖 3 个改动文件 + 修权限
  ④ 校验：服务器文件数、关键文件 md5 与本地比对、HTTP 状态码、关键内容 grep

凭据从 .qrcheck/sync_upload.py 读取，不硬编码。
用法：python _工作台/_server_sync.py [--dry]
"""
import hashlib, re, sys, time
from pathlib import Path
import paramiko

LOCAL = Path(r"D:/ZeXiao")
SRC = LOCAL / ".qrcheck" / "sync_upload.py"
TGZ = LOCAL / "_sync_真题思维导图.tgz"
FILES = ["nav-data.js", "真题备考区.html", "移动端实时预览.html"]
DRY = "--dry" in sys.argv

txt = SRC.read_text(encoding="utf-8", errors="replace")
H = re.search(r"(?:^|[;\s])H\s*=\s*['\"]([^'\"]+)", txt).group(1)
U = re.search(r"(?:^|[;\s])U\s*=\s*['\"]([^'\"]+)", txt).group(1)
P = re.search(r"(?:^|[;\s])P\s*=\s*['\"]([^'\"]+)", txt).group(1)
ROOT = re.search(r"(?:^|[;\s])ROOT\s*=\s*['\"]([^'\"]+)", txt).group(1)
TS = time.strftime("%Y%m%d-%H%M%S")
TMP = "/tmp/kaoyan-mindmap-" + TS
BAK = "/root/kaoyan-mindmap-" + TS


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(H, 22, U, P, timeout=30)


def run(cmd, sudo=True, timeout=900):
    if sudo:
        cmd = "printf '%s\n' " % P + "| sudo -S -p '' bash -c " + repr(cmd)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    return (o.read().decode("utf-8", "ignore") + e.read().decode("utf-8", "ignore")).strip()


print("=== 0）准备远端临时目录 %s ===" % TMP)
print(run("mkdir -p %s && ls -ld %s" % (TMP, TMP), sudo=False))

if DRY:
    print("[dry-run] 到此为止"); sys.exit(0)

print("\n=== ① 上传（tgz %.1f MB + %d 个改动文件）===" % (TGZ.stat().st_size / 1048576, len(FILES)))
t0 = time.perf_counter()
sftp = c.open_sftp()
sftp.put(str(TGZ), TMP + "/真题思维导图.tgz")
print("  ↑ 真题思维导图.tgz  %.1f MB" % (TGZ.stat().st_size / 1048576))
for f in FILES:
    sftp.put(str(LOCAL / f), TMP + "/" + f)
    print("  ↑ %s  %.0f KB" % (f, (LOCAL / f).stat().st_size / 1024))
sftp.close()
print("  上传用时 %.0f 秒" % (time.perf_counter() - t0))

print("\n=== ② 服务器端备份 → %s ===" % BAK)
cmd = ("mkdir -p %s && cp -a %s/真题思维导图 %s/ 2>/dev/null; "
       % (BAK, ROOT, BAK))
cmd += "".join("cp -a %s/%s %s/ 2>/dev/null; " % (ROOT, f, BAK) for f in FILES)
cmd += "ls -la %s | head -8; echo '--- 备份里的文件数 ---'; find %s -type f | wc -l" % (BAK, BAK)
print(run(cmd))

print("\n=== ③ 解包到站点 + 修权限 ===")
cmd = ("tar -xzf %s/真题思维导图.tgz -C %s && "
       "find %s/真题思维导图 -type d -exec chmod 755 {} + && "
       "find %s/真题思维导图 -type f -exec chmod 644 {} + && "
       "chown -R root:root %s/真题思维导图 && "
       "echo '--- 部署后 ---' && du -sh %s/真题思维导图 && "
       "find %s/真题思维导图 -type f | wc -l && ls -ld %s/真题思维导图"
       % (TMP, ROOT, ROOT, ROOT, ROOT, ROOT, ROOT, ROOT))
print(run(cmd))

print("\n=== ④ 覆盖 3 个改动文件 ===")
cmd = "".join("cp -f %s/%s %s/%s && chmod 644 %s/%s && " % (TMP, f, ROOT, f, ROOT, f) for f in FILES)
cmd += "ls -l %s" % " ".join("%s/%s" % (ROOT, f) for f in FILES)
print(run(cmd))

print("\n=== ⑤ 校验：md5（本地 vs 服务器）===")
checks = ["index.html", "assets/kg.js", "assets/kg.css", "x/985/tianjin/2020/812/index.html",
          "k/rl_02/index.html"] + FILES
bad = 0
for rel in checks:
    local = LOCAL / rel
    remote = "%s/%s" % (ROOT, rel)
    out = run("md5sum '%s' 2>/dev/null | cut -d' ' -f1" % remote, sudo=False)
    lm = md5(local) if local.is_file() else "(本地无)"
    ok = (out.strip() == lm)
    if not ok:
        bad += 1
    print("  %s %-44s 本地=%s 服务器=%s" % ("OK  " if ok else "DIFF", rel, lm[:10], out.strip()[:10]))

print("\n=== ⑥ 校验：HTTP（服务器本机 curl）===")
for u in ("/", "/真题备考区.html", "/真题思维导图/",
          "/真题思维导图/x/985/tianjin/2020/812/", "/真题思维导图/k/rl_02/",
          "/真题思维导图/assets/kg.js", "/真题思维导图/assets/sets.js"):
    code = run("curl -s -o /dev/null -w '%%{http_code}' --max-time 15 http://127.0.0.1%s" % u, sudo=False)
    print("  %-44s %s" % (u, code))

print("\n=== ⑦ 校验：关键内容已生效 ===")
print("  真题备考区 入口按钮:", run("grep -c '真题思维导图/index.html' %s/真题备考区.html" % ROOT, sudo=False))
print("  nav-data 导航条目  :", run("grep -c '真题思维导图/index.html' %s/nav-data.js" % ROOT, sudo=False))
print("  旧路径兼容页存在   :", run("test -f '%s/真题思维导图/x/985/tianjin/2020/index.html' && echo yes || echo no" % ROOT, sudo=False))
print("  卷页数（应 879+840）:", run("find %s/真题思维导图 -name index.html -path '*x/*' | wc -l" % ROOT, sudo=False))
print("\n完成。备份目录：%s　临时目录（可删）：%s" % (BAK, TMP))
print("md5 不符项：%d" % bad)
