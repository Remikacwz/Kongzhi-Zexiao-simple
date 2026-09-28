#!/usr/bin/env python3
"""检查院校详情库里的「该校就业去向」链接是否都有对应页面（防止 404）。

详情库页面不再生成，直接链接到「院校就业去向」板块已有的页面；
本脚本只做校验，不修改任何文件。

用法：python tools/check_job_links.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAT = re.compile(r'<a[^>]+href="([^"]*就业相关/院校就业去向/schools/[^"]*)"[^>]*>')


def main():
    missing, total = [], 0
    for p in sorted((ROOT / 'school_detail').glob('*.html')):
        if p.stem in ('index', 'route'):
            continue
        for m in PAT.finditer(p.read_text(encoding='utf-8')):
            total += 1
            if not (p.parent / m.group(1)).resolve().exists():
                missing.append((p.name, m.group(1)))
    print(f'就业去向链接总数: {total}')
    print(f'失效链接: {len(missing)}')
    for f, h in missing:
        print(f'  ✗ {f} → {h}')
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
