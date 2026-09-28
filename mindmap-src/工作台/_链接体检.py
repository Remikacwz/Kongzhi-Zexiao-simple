# -*- coding: utf-8 -*-
"""站内链接体检：把所有 HTML 里的相对 href/src 解析成文件，报告落不到文件的链接。

用法：python _工作台/_链接体检.py [站点目录，默认 网站原型]
"""
import re, sys, collections
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "网站原型").resolve()
ATTR = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"')
SRC = re.compile(r'<(?:a|link|script|img|iframe)\b', re.I)


def main():
    bad = collections.Counter()
    bad_example = {}
    n_links = 0
    for p in sorted(ROOT.rglob("*.html")):
        s = p.read_text(encoding="utf-8", errors="replace")
        rel_dir = p.parent.relative_to(ROOT)
        for raw in ATTR.findall(s):
            if raw.startswith(("http://", "https://", "//", "mailto:", "tel:", "javascript:", "#", "data:")):
                continue
            target = raw.split("#")[0].split("?")[0]
            if not target:
                continue
            n_links += 1
            t = (p.parent / unquote(target)).resolve()
            ok = (t / "index.html").is_file() if target.endswith("/") else t.is_file()
            if not ok:
                key = target
                bad[key] += 1
                bad_example.setdefault(key, str(rel_dir / p.name))
    print("检查 %d 个链接，坏链 %d 种、共 %d 处" % (n_links, len(bad), sum(bad.values())))
    for tgt, cnt in bad.most_common(25):
        print("  %4d 处  %-46s 例: %s" % (cnt, tgt, bad_example[tgt]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
