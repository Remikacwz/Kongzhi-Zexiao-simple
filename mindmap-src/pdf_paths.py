# -*- coding: utf-8 -*-
"""PDF 归档路径单一事实源。

新布局（2026-09-27 起）：思维导图_PDF/<院校>/<院校>_<代码>_<年份>_品牌版.pdf
旧布局（兼容读）：      思维导图_PDF/<院校>_<代码>_<年份>_品牌版.pdf

- target_of(key)：**写入**用，永远返回分院校路径（父目录需自行 mkdir）。
- pdf_of(key)：**读取**用，分院校存在则用分院校；否则回退旧的平铺路径（迁移期保险）。
- exists(key)：读取存在性。
"""
from pathlib import Path

HERE = Path(__file__).parent
PDF_ROOT = HERE / "思维导图_PDF"


def school_of(key: str) -> str:
    """从 key（院校_代码_年份）取院校名。用 rsplit 以容忍校名内含下划线。"""
    parts = key.split("_")
    if len(parts) >= 3:
        return key.rsplit("_", 2)[0]
    return parts[0]


def target_of(key: str, suffix: str = "_品牌版") -> Path:
    """写入路径：思维导图_PDF/<院校>/<key><suffix>.pdf"""
    return PDF_ROOT / school_of(key) / f"{key}{suffix}.pdf"


def pdf_of(key: str, suffix: str = "_品牌版") -> Path:
    """读取路径：优先分院校，回退平铺（迁移期兼容）。"""
    sub = target_of(key, suffix)
    if sub.exists():
        return sub
    flat = PDF_ROOT / f"{key}{suffix}.pdf"
    return flat if flat.exists() else sub


def exists(key: str, suffix: str = "_品牌版") -> bool:
    return pdf_of(key, suffix).exists()
