# -*- coding: utf-8 -*-
"""只重建 思维导图_交互/index.html（不重渲 879 个 HTML，HTML 内容未受影响）。

索引行所需字段直接由 JSON 规格算出，与 build_one 的命名/口径保持一致。
"""
import json, shutil, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import mindmap_v6 as mm6            # noqa: E402
import build_interactive as bi      # noqa: E402


def main():
    idx = bi.OUT / "index.html"
    if idx.exists():
        bak = idx.with_name("index_旧_%s.html" % time.strftime("%Y%m%d_%H%M%S"))
        shutil.copy2(idx, bak)
        print("旧索引已备份 ->", bak.name)
    lib = mm6.load_lib()
    rows, missing = [], []
    for jp in sorted((HERE / "思维导图_v6").glob("*.json")):
        raw = json.loads(jp.read_text(encoding="utf-8"))
        spec, _ = mm6.expand(raw, lib)
        name = (f'{spec.get("院校","")}_{spec.get("科目代码") or "NA"}'
                f'_{spec.get("年份","")}.html')
        n = sum(1 for _ in bi._walk(bi.to_tree(spec)))
        if not (bi.OUT / name).exists():
            missing.append(name)
        try:
            yr = int(str(spec.get("年份", "")).strip())
        except ValueError:
            print("  [年份非数字，按 0 处理]", jp.name, repr(spec.get("年份")))
            yr = 0
        rows.append({"file": name, "院校": str(spec.get("院校") or ""), "年份": yr,
                     "代码": spec.get("科目代码"), "科目": spec.get("科目"), "节点": n})
    bi.write_index(rows)
    print("索引行数 %d；对应 HTML 缺失 %d 个" % (len(rows), len(missing)))
    for m in missing[:10]:
        print("   缺:", m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
