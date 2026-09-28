# -*- coding: utf-8 -*-
"""封面年份全库核查：逐份 PDF 取第 1 页文字，找「<数字> 年硕士研究生入学考试」，
与 key 里的年份比对（封面年份修正的落地证据）。
用法：python _工作台/_封面年份核查.py
"""
import re, sys, time
from pathlib import Path
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent.parent
PDF = HERE / "思维导图_PDF"
PAT = re.compile("\u5e74\u7855\u58eb\u7814\u7a76\u751f\u5165\u5b66\u8003\u8bd5")   # 「年硕士研究生入学考试」
NUM = re.compile("[0-9]{3,4}")


def year_before(text, pos):
    seg = text[max(0, pos - 8):pos]
    m = NUM.findall(seg)
    return m[-1] if m else None


def main():
    t0 = time.perf_counter()
    files = sorted(PDF.glob("*_品牌版.pdf"))
    bad = []
    n_ok = 0
    for p in files:
        key = p.name[:-len("_品牌版.pdf")]
        want = key.rsplit("_", 1)[-1]
        try:
            r = PdfReader(str(p))
            t = r.pages[0].extract_text() or ""
        except Exception as e:
            bad.append((key, "读失败: %s" % e)); continue
        t = " ".join(t.split())
        pos = t.find("年硕士研究生入学考试")
        if pos < 0:
            bad.append((key, "封面未见「年硕士研究生入学考试」: %s" % t[:60])); continue
        got = year_before(t, pos)
        if got == want:
            n_ok += 1
        else:
            bad.append((key, "封面年份=%r 应为 %r" % (got, want)))
    print("核查 %d 份，封面年份正确 %d，异常 %d（用时 %.1fs）"
          % (len(files), n_ok, len(bad), time.perf_counter() - t0))
    for k, why in bad[:30]:
        print("  ✗ %-28s %s" % (k, why))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
