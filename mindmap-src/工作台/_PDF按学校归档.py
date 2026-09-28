# -*- coding: utf-8 -*-
"""把 思维导图_PDF 下的平铺 PDF 归档为：思维导图_PDF/<院校>/<key>_品牌版.pdf

用法：
  python _工作台/_PDF按学校归档.py --dry     # 只看清单，不动文件
  python _工作台/_PDF按学校归档.py           # 实际归档

规则：
  - 目标不存在 → 移动（同盘移动，秒级）；
  - 目标已存在且大小相同 → 视为重复，删掉平铺的那份（内容一致）；
  - 目标已存在但大小不同 → 平铺那份改名加后缀 _重复保留.pdf 放同目录，绝不覆盖；
  - 非 *_品牌版.pdf 的平铺文件一律不动，只报告。
"""
import collections, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import pdf_paths as PP          # noqa: E402

ROOT = PP.PDF_ROOT
SUF = "_品牌版.pdf"


def main():
    dry = "--dry" in sys.argv
    flat = sorted(p for p in ROOT.glob("*.pdf") if p.name.endswith(SUF))
    other = sorted(p for p in ROOT.glob("*.pdf") if not p.name.endswith(SUF))
    print("平铺品牌版 PDF：%d 份；其它平铺 PDF：%d 份%s"
          % (len(flat), len(other), "（--dry 只报告）" if dry else ""))
    for p in other:
        print("   [不动] 非品牌版:", p.name)

    cnt = collections.Counter()
    moved = dup = kept = 0
    for p in flat:
        stem = p.name[:-len(SUF)]
        school = PP.school_of(stem)
        cnt[school] += 1
        tgt = PP.target_of(stem)
        if tgt.exists():
            if tgt.stat().st_size == p.stat().st_size:
                dup += 1
                if not dry:
                    p.unlink()
            else:
                kept += 1
                if not dry:
                    p.rename(tgt.with_name(tgt.stem + "_重复保留.pdf"))
            continue
        moved += 1
        if not dry:
            tgt.parent.mkdir(parents=True, exist_ok=True)
            p.rename(tgt)
    print("→ 移动 %d 份；目标已存在且同大小（删平铺）%d 份；目标冲突改名保留 %d 份"
          % (moved, dup, kept))
    print("→ 涉及院校 %d 个，各校份数（前 15）：%s"
          % (len(cnt), " ".join("%s:%d" % kv for kv in cnt.most_common(15))))
    if not dry:
        left = len([p for p in ROOT.glob("*.pdf") if p.name.endswith(SUF)])
        tot = len(list(ROOT.glob("*/*" + SUF)))
        print("→ 归档后：平铺剩 %d 份；分院校下共 %d 份" % (left, tot))
    return 0


if __name__ == "__main__":
    sys.exit(main())
