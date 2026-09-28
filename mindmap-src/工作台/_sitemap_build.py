# -*- coding: utf-8 -*-
"""sitemap 改造（方案 B：sitemap index）。

产出（写到 D:\\ZeXiao）：
  ① sitemap-main.xml —— 主站子 sitemap：扫描磁盘上真实存在的可收录 HTML，真实域名 + 百分号编码 + lastmod
  ② sitemap.xml      —— 根索引：引用 sitemap-main.xml 与 真题思维导图/sitemap.xml
收录规则：排除后台/工具/测试/生成物目录；排除 404 与开发用预览页。
"""
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

ROOT = Path(r"D:/ZeXiao")
DOMAIN = "https://kzkyzx.wanrenjiaoyu.com"
MY_SITEMAP = DOMAIN + "/" + quote("真题思维导图/sitemap.xml", safe="/")

# 不收录：目录
SKIP_DIRS = {"数据库", "tools", "deploy", "docs", "tests", ".qrcheck", ".local_uploads", ".git",
             "uploads", "data", "vendor", "assets", "__pycache__", "真题思维导图", "_工作台_bak"}
# 不收录：文件（开发/错误页）
SKIP_FILES = {"404.html", "移动端实时预览.html", "mobile-preview.html"}


def enc(path: str) -> str:
    return DOMAIN + "/" + quote(path, safe="/")


def collect():
    out = []
    for p in sorted(ROOT.rglob("*.html")):
        rel = p.relative_to(ROOT)
        parts = rel.parts
        if any(x in SKIP_DIRS or x.startswith(".") for x in parts[:-1]):
            continue
        if parts[0].startswith("_") or rel.name in SKIP_FILES:
            continue
        mtime = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
        out.append((enc(rel.as_posix()), mtime))
    return out


def write_urlset(items, path: Path):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lm in items:
        lines.append("<url><loc>%s</loc><lastmod>%s</lastmod></url>" % (loc, lm))
    lines.append("</urlset>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(items)


def write_index(children, path: Path):
    today = time.strftime("%Y-%m-%d")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for c in children:
        lines.append("<sitemap><loc>%s</loc><lastmod>%s</lastmod></sitemap>" % (c, today))
    lines.append("</sitemapindex>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    items = collect()
    n = write_urlset(items, ROOT / "sitemap-main.xml")
    write_index([DOMAIN + "/sitemap-main.xml", MY_SITEMAP], ROOT / "sitemap.xml")
    print("sitemap-main.xml: %d 条" % n)
    # 校验 XML 合法性
    for f in ("sitemap-main.xml", "sitemap.xml"):
        tree = ET.parse(ROOT / f)
        root = tree.getroot()
        tag = root.tag.split("}")[-1]
        print("  %-20s 合法 ✓ 根标签=%s 子项=%d" % (f, tag, len(list(root))))
    # 与旧清单对比（旧文件已备份为 sitemap.xml.bak-*，此处只报告分布）
    import collections
    c = collections.Counter(u.split("/")[3] if u.count("/") >= 4 else "(根目录)" for u, _ in items)
    print("  收录分布:", ", ".join("%s=%d" % kv for kv in c.most_common(8)))
    print("  样例:", items[0][0], "|", items[-1][0])
