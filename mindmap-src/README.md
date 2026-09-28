# 控制考研真题思维导图 · 站点源码与数据

> 本目录是站点源码与数据的**镜像**（主仓库：`Remikacwz/Zexiao`）。路径引用按本仓库布局调整过：
> 生成时请 `cd mindmap-src` 后再运行 `python site_build.py ...`（依赖与前端资源都在本目录的 `assets/`）。


站点生成器 + 数据源。**产物不入库**（见 `.gitignore`）。生产：`https://kzkyzx.wanrenjiaoyu.com/真题思维导图/`

## 数据规模
- **879 套**：89 所院校 × 2015–2025（985 / 211 / 强势双非）
- **103 个考点**（17 个大类），含要点/步骤/公式/考法/易错
- 站点结构：首页（分级/学校/年份/代码/考点 筛选）→ 学校页 → 卷页（整卷/单题导图 + 考点详解）→ 考点页（历年考法）→ 考点索引

## 目录
```
site_build.py          站点生成器（唯一入口：读 JSON → 输出静态站）
思维导图_v6/*.json      卷级数据源（879 个，唯一不可再生的数据）
考点库/*.json           考点库（17 大类 / 103 考点）
网站前端/               kg.css / kg.js / kg-embed.js（站点样式与交互，生成时复制进 assets/）
根目录 *.py              mindmap_v6.py（渲染 core）· build_pdf.py（PDF）· build_interactive.py（旧版交互页）
                       pdf_paths.py（PDF 归档路径）· verify.py / qc.py（验收）· workbench.py / nextkeys.py（工作台）
assets/                自包含前端资源：d3.min.js · katex/ · 品牌 logo · logo/<slug>.jpg（89 校徽，已裁 72×72）
工作台/                 交接.md（判据账本，含全部工程判据与踩坑）· sources.json · 重卷映射.json · 各类体检/同步脚本
```

## 重新生成
```bash
py -3.12 site_build.py                                    # 独立原型 → 网站原型/
py -3.12 site_build.py --out "D:/ZeXiao/真题思维导图" \
    --parent "../index.html" --site "https://kzkyzx.wanrenjiaoyu.com/真题思维导图"   # 接入主站
py -3.12 build_pdf.py <key> --brand                 # 单套 PDF（Edge headless）
```
依赖：Python 3.12、graphviz(`dot`)、Edge headless（PDF/截图）、`pypdf`、`Pillow`。
**本仓库自包含**：前端资源在 `assets/`，校徽在 `assets/logo/`（`site_build.find_logo()` 会回退到这里），无需外部目录即可重新生成站点。

## 验收（改完必跑）
```bash
py -3.12 verify.py --range 2015-2025     # 每套四件产物 + SVG 张数（必看"套数/失败数"两个数字）
py -3.12 qc.py                           # 硬错误必须为 0
py -3.12 工作台/_链接体检.py <站点目录>          # 全站相对链接落地（出站前必跑）
```
`?debug=1` 提供页面自测：搜索框/代码/考点筛选（`SELFTEST`）、卷页大纲跳题与全屏（`SETTEST`）。

## 数据边界
本站**只放导图与考点**（自制内容），**不含真题原文/答案**（版权与商业考虑）。真题素材（宝典A/发布册 PDF）不在本仓库。

## 注意
- **生成时务必带 `--site`**：带 `--parent`（接入主站）却不给 `--site` 会丢掉 canonical/sitemap（生成器已加警告）。
- 生成结果必须**可复现**：源码里禁止对 `set` 直接 `list()` 后写进产物（受哈希随机化影响），需先排序。
