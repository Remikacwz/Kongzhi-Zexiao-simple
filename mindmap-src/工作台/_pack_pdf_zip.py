# -*- coding: utf-8 -*-
"""把思维导图 PDF 按院校打包成一个 zip。

结构：<院校名>/<院校_代码_年份>_品牌版.pdf
排除：_备份旧产物/、_work/、assets/（都不是交付物）
输出：E:/真题思维导图/_导出/真题思维导图PDF_按院校打包.zip
"""
import sys, time, zipfile
from pathlib import Path

SRC = Path(r"E:/真题思维导图/_索引/思维导图_PDF")
OUT_DIR = Path(r"E:/真题思维导图/_导出")
OUT = OUT_DIR / "真题思维导图PDF_按院校打包.zip"
SKIP = {"_备份旧产物", "_work", "assets"}

OUT_DIR.mkdir(parents=True, exist_ok=True)
schools = sorted([d for d in SRC.iterdir() if d.is_dir() and d.name not in SKIP], key=lambda d: d.name)
files = []
for d in schools:
    for f in sorted(d.glob("*.pdf")):
        files.append((f, "%s/%s" % (d.name, f.name)))
total_bytes = sum(f.stat().st_size for f, _ in files)
print("院校 %d 个，PDF %d 份，合计 %.2f GB" % (len(schools), len(files), total_bytes / 1073741824), flush=True)

t0 = time.perf_counter()
done = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as z:
    for f, arc in files:
        z.write(f, arc)
        done += 1
        if done % 100 == 0:
            el = time.perf_counter() - t0
            print("  %d/%d  已用 %.0f 秒  预计还需 %.0f 秒  输出 %.2f GB"
                  % (done, len(files), el, el / done * (len(files) - done), OUT.stat().st_size / 1073741824),
                  flush=True)

print("打包完成，用时 %.0f 秒" % (time.perf_counter() - t0), flush=True)
print("文件：%s" % OUT, flush=True)
print("大小：%.2f GB（原始 %.2f GB，压缩率 %.0f%%）"
      % (OUT.stat().st_size / 1073741824, total_bytes / 1073741824,
         100 * OUT.stat().st_size / total_bytes), flush=True)

# 校验：条目数 + 目录数 + 抽样可读
with zipfile.ZipFile(OUT) as z:
    names = z.namelist()
    dirs = sorted({n.split("/")[0] for n in names})
    print("条目 %d，院校目录 %d" % (len(names), len(dirs)), flush=True)
    for n in names[:2] + names[-2:]:
        info = z.getinfo(n)
        data = z.read(n)
        print("  样本 %-46s %8.2f MB 可读=%s" % (n, info.file_size / 1048576, data[:5] == b"%PDF-"), flush=True)
    missing = [n for n in names if not n.endswith(".pdf")]
    print("非 pdf 条目：%d" % len(missing), flush=True)
