# -*- coding: utf-8 -*-
"""部署 sitemap 改造（方案 B：index）到生产，并在线上做 HTTP 验证。"""
import random, re, time
from pathlib import Path
import paramiko
import xml.etree.ElementTree as ET
from urllib.parse import unquote

LOCAL = Path(r"D:/ZeXiao")
SRC = LOCAL / ".qrcheck" / "sync_upload.py"
txt = SRC.read_text(encoding="utf-8", errors="replace")
H = re.search(r"(?:^|[;\s])H\s*=\s*['\"]([^'\"]+)", txt).group(1)
U = re.search(r"(?:^|[;\s])U\s*=\s*['\"]([^'\"]+)", txt).group(1)
P = re.search(r"(?:^|[;\s])P\s*=\s*['\"]([^'\"]+)", txt).group(1)
ROOT = "/var/www/kaoyan-site"
D = "kzkyzx.wanrenjiaoyu.com"
TS = time.strftime("%Y%m%d-%H%M%S")
FILES = [("sitemap.xml", "%s/sitemap.xml" % ROOT),
         ("sitemap-main.xml", "%s/sitemap-main.xml" % ROOT),
         ("真题思维导图/sitemap.xml", "%s/真题思维导图/sitemap.xml" % ROOT)]

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(H, 22, U, P, timeout=30)


def run(cmd, sudo=False, t=180):
    if sudo:
        cmd = "printf '%s\n' " + P + " | sudo -S -p '' bash -c " + repr(cmd)
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode("utf-8", "ignore") + e.read().decode("utf-8", "ignore")).strip()


print("=== ① 服务器端备份旧 sitemap ===")
print(run("mkdir -p /root/sitemap-bak-%s && cp -a %s/sitemap.xml /root/sitemap-bak-%s/ && ls -l /root/sitemap-bak-%s"
          % (TS, ROOT, TS, TS), sudo=True))

print("\n=== ② 上传（3 个文件，走 /tmp → sudo cp）===")
sftp = c.open_sftp(); tmpmap = {}
for rel, _ in FILES:
    tmp = "/tmp/sm-%s-%s" % (TS, rel.replace("/", "__"))   # 唯一临时名：同名会互相覆盖（已踩过）
    sftp.put(str(LOCAL / rel), tmp)
    tmpmap[rel] = tmp
    print("  ↑ %s  %.0f KB" % (rel, (LOCAL / rel).stat().st_size / 1024))
sftp.close()
cmd = "".join("cp -f %s '%s' && chmod 644 '%s' && " % (tmpmap[rel], dst, dst) for rel, dst in FILES)
cmd += "ls -l " + " ".join("'%s'" % dst for _, dst in FILES)
print(run(cmd, sudo=True))

print("\n=== ③ 线上验证：索引与子 sitemap ===")
for u in ("/sitemap.xml", "/sitemap-main.xml", "/%E7%9C%9F%E9%A2%98%E6%80%9D%E7%BB%B4%E5%AF%BC%E5%9B%BE/sitemap.xml"):
    out = run("curl -sk -o /dev/null -w '%%{http_code} %%{size_download}B' --max-time 20 'https://%s%s'" % (D, u))
    print("  %-58s %s" % (u, out))
print("  索引内容:", run("curl -sk --max-time 20 'https://%s/sitemap.xml' | head -4 | tr -d '\\n'" % D)[:200])

print("\n=== ④ 线上抽样：两个 sitemap 各抽 12 条真实访问 ===")
random.seed(20260928)
def locs(p):
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    return [e.find(ns + "loc").text for e in ET.parse(p).getroot()]
for name, p in (("主站", LOCAL / "sitemap-main.xml"), ("导图", LOCAL / "真题思维导图/sitemap.xml")):
    us = random.sample(locs(p), 12)
    codes = []
    for u in us:
        path = u.replace("https://" + D, "")
        code = run("curl -sk -o /dev/null -w '%%{http_code}' --max-time 20 'https://%s%s'" % (D, path), t=40)
        codes.append(code)
    print("  %s：12 条 → %s" % (name, " ".join(codes)))
