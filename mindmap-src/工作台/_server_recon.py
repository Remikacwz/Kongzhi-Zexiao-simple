# -*- coding: utf-8 -*-
"""同步前侦察：服务器现状（属主 / 磁盘 / 是否已有目标目录 / git 状态 / nginx 根）。

凭据从既有脚本 .qrcheck/sync_upload.py 里读取，不在本文件硬编码。
"""
import re, sys
from pathlib import Path
import paramiko

SRC = Path(r"D:/ZeXiao/.qrcheck/sync_upload.py")
txt = SRC.read_text(encoding="utf-8", errors="replace")
H = re.search(r"(?:^|[;\s])H\s*=\s*['\"]([^'\"]+)", txt, re.M).group(1)
U = re.search(r"(?:^|[;\s])U\s*=\s*['\"]([^'\"]+)", txt, re.M).group(1)
P = re.search(r"(?:^|[;\s])P\s*=\s*['\"]([^'\"]+)", txt, re.M).group(1)
ROOT = re.search(r"(?:^|[;\s])ROOT\s*=\s*['\"]([^'\"]+)", txt, re.M)
ROOT = ROOT.group(1) if ROOT else "/var/www/kaoyan-site"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(H, 22, U, P, timeout=25)


def run(cmd, sudo=False, timeout=120):
    if sudo:
        cmd = "printf '%s\n' " % P + "| sudo -S -p '' bash -c " + repr(cmd)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    return (o.read().decode("utf-8", "ignore") + e.read().decode("utf-8", "ignore")).strip()


print("== 站点根 ==")
print(run("ls -ld %s" % ROOT))
print(run("ls %s | head -40" % ROOT))
print("\n== 目标目录是否已存在 ==")
print(run("ls -ld %s/真题思维导图 2>&1 | head -2; du -sh %s 2>/dev/null" % (ROOT, ROOT)))
print("\n== 磁盘 ==")
print(run("df -h /var/www | tail -2"))
print("\n== git 状态（该目录是否 git 仓库）==")
print(run("cd %s && git rev-parse --is-inside-work-tree 2>&1 | head -1 && git status --short 2>&1 | head -8 && git log -1 --oneline 2>&1" % ROOT))
print("\n== 属主/权限样例 ==")
print(run("stat -c '%U:%G %a %n' %s/index.html %s/nav-data.js %s/真题备考区.html 2>&1" % (ROOT, ROOT, ROOT)))
print("\n== nginx 根与 index 配置 ==")
print(run("grep -rn 'root\\|index ' /etc/nginx/sites-enabled/ 2>/dev/null | head -8"))
print("\n== 关键页面当前 HTTP ==")
for u in ("/", "/真题备考区.html", "/真题思维导图/"):
    print("  %-22s %s" % (u, run("curl -s -o /dev/null -w '%%{http_code}' --max-time 12 http://127.0.0.1%s" % u)))
