---
name: universal-learning-desk
description: |
  把任意格式资料（PDF / 图片 / Word / PPT / HTML / Markdown / TXT）转换为「CPA知识学习台」同款工作台风格的单文件离线 HTML：
  本地 RapidOCR 识别扫描件、markitdown[all] 解析 Office/网页、按段落或幻灯片页切分知识卡片、
  保留深浅色 / 顶栏搜索与筛选 / 卡片标签 / OCR 来源警示条 / 右滑关闭抽屉等全套交互，产出无 CDN 的 xxx_学习台.html。
  仓库提供 library/ 空包模板与构建脚本（CPA 两法 1515 卡的数据包因教材授权不随仓库分发），可用 build_kb.py 直接从自有资料构建、不重跑 OCR；
  并提供 install_skill.py，可安装到 DSH / WorkBuddy / CodeBuddy / Claude Code / Codex 等 Agent。
  触发词：将资料转为学习台、生成学习台、把资料转成工作台、做成卡片学习台、OCR 重建教材、
  把 PPT 做成学习台、扫描版 PDF 转知识卡片、资料转单文件 HTML 工作台、知识库包、library、跨 Agent 安装。
---

# universal-learning-desk

把任意资料变成和现有「CPA知识学习台」**一模一样风格**的单文件 HTML 工作台。
整条流水线来自一次真实跑通的 609 页扫描版《经济法》+ 704 页《税法》OCR 重建项目。

## 1. 目录结构

```
universal-learning-desk/
├── SKILL.md                      本说明书（Agent 入口）
├── README.md                     人类入口：安装、跨 Agent、library、限制
├── REPORT.md                     两法项目实测报告（1515 卡 / 数字守恒 / 门禁）
├── requirements.txt
├── .gitignore
├── assets/
│   ├── template.html             母版（CSS/JS 全保留，数据为 mock）
│   └── app_kb.js                 知识台检索引擎（v2：归一化/拼音/容错/导出）
├── scripts/
│   ├── universal_reader.py       ① 多格式解析 → 带锚点 Markdown + sidecar
│   ├── extract_cards.py          ② 卡片提取 → 完整 APP_DATA JSON + 质量门禁
│   ├── rebuild_cards.py          ②' 既有卡片 → 语义重切分 + 术语重建（v2）
│   ├── build_html.py             ③ 注入母版 → xxx_学习台.html
│   ├── build_kb.py               ③' 注入知识台母版 + 防呆 + 拼音表（v2）
│   ├── run_pipeline.py           一键编排（推荐）
│   ├── build_template.py         可选：从原始学习台 HTML 重新生成母版
│   └── install_skill.py          安装到 DSH / WorkBuddy / Claude / Codex / 任意目录
├── library/                      可复用知识库包（不重跑 OCR）
│   ├── manifest.json
│   ├── README.md
│   └── cpa-two-laws/
│       ├── app_data.json         1515 卡 / 26 章 / 168 术语
│       └── README.md
└── examples/
    ├── make_fixtures.py          生成 8 种格式的测试样例
    └── smoke_test.py             全格式冒烟测试 + 浏览器渲染校验
```

## 2. 安装依赖

```bash
# 推荐：一次装齐
pip install -r requirements.txt

# 或最小集合
pip install "markitdown[all]" PyMuPDF rapidocr-onnxruntime
```

补充（PPT 逐页解析与 Office 兜底需要，通常已随 `markitdown[all]` 带入）：

```bash
pip install python-pptx python-docx beautifulsoup4 Pillow opencv-python-headless
```

> 全部为本地依赖，**运行时不联网、不调用任何云 OCR / LLM API**。
> 若 `markitdown` 或某个可选依赖缺失，脚本会自动降级到本地解析器并在报告中记录 `warnings`，不会崩溃。

## 3. 运行步骤

### 方式 A：一键（推荐）

```bash
python scripts/run_pipeline.py \
    --input   "/path/公司法讲义.pdf" \
    --out-dir  ./output \
    --subject  "公司法" \
    --title    "公司法学习台"
```

产出：`./output/公司法讲义_学习台.html`，中间产物在 `./output/_work/`。

### 方式 B：分三步（便于断点续跑 / 单独调试）

```bash
# ① 任意格式 → 带锚点 Markdown（<stem>.md + <stem>.reader.json）
python scripts/universal_reader.py --input 资料.pptx --out-dir ./work --engine auto

# ② Markdown → 卡片 APP_DATA（<stem>_cards.json + 质量门禁）
python scripts/extract_cards.py --md ./work/资料.md --meta ./work/资料.reader.json \
                                --subject "公司法" --out ./work/资料_cards.json

# ③ APP_DATA + 母版 → 单文件 HTML
python scripts/build_html.py --cards ./work/资料_cards.json \
                             --template assets/template.html \
                             --out ./output/资料_学习台.html
```

### 常用参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--engine auto\|ocr\|text` | PDF 引擎：`auto` 有文字层则直接抽取、否则 OCR；`ocr` 强制重新识别（适合**文字层乱码**的 PDF）；`text` 强制文字层 | `auto` |
| `--dpi` | 扫描 PDF 渲染 DPI | `200` |
| `--workers` | OCR 进程数（按 CPU 核数调整，4 核容器用 4） | `4` |
| `--subject` / `--title` | 科目名 / 学习台标题（同时决定侧栏目录与 `<title>`） | 文件名 |
| `--chapter-every N` | 无标题资料每 N 个页面单元归为一章 | `0`（全部 1 章） |
| `--max-cards` | 最多生成卡片数 | `5000` |
| `--id-prefix` | 卡片 id 前缀（ASCII） | `D` |
| `--low-conf` | OCR 置信度低于此值标 `needs_review` | `0.90` |

> `--engine ocr` 专门解决「PDF 有文字层但字体映射乱码」的情况（例如 `13%` 显示成 `139毛`、
> `无偿` 显示成 `1元偿`）：把每页渲染成 200 DPI 图片重新 OCR，乱码即被消除。

## 3.5 知识台模式（v2，推荐用于已有一版卡片语料的重建）

定位：不是「学习台」，而是**可检索、可导出、可追溯的第二大脑**。适用于已经产出一版卡片、但存在
硬切半句 / 页眉页脚混入 / 术语乱码的语料。

```bash
# 0) 从旧 HTML 抽出 APP_DATA（或直接用手上的 *_cards.json）
python scripts/extract_app_data.py --html 旧.html --out app_data_old.json

# ① 语义重切分 + 术语重建（不重跑 OCR，不改写任何用词与数字）
python scripts/rebuild_cards.py --in app_data_old.json --out app_data_new.json --report rebuild_gate.json

# ② 注入知识台母版（数据防呆 + 拼音表 + 82vw 抽屉）
python scripts/build_kb.py --data app_data_new.json --out 知识台.html --title "CPA知识台"
```

门禁与保证：

- **切分**：中文序号前断、句末标点后断；冒号引领的列举不断；超过上限且无句界时整段保留，绝不硬切；
  跨页残句 / 「如下：」引领句强制接续。
- **噪声**：只删同章高频重复的页首串与页尾页码，删除明细写入报告的 `removed_noise_samples`。
- **数字守恒**：清洗后页文本与最终卡片逐 token 对账，多一个少一个都判 FAIL。
- **术语 SSOT**：只从最终卡片正文派生，乱码 / 残句 / 指示词开头一律拒绝，每条带 `freq` 供前端控制高亮密度。
- **前端**：全角归一、多词 AND、`id:` 精确检索、拼音全拼与首字母、二元组容错、130ms 防抖、
  导出 Markdown / JSON / 术语表 / 笔记、复制引用（标题+原文+页码+锚点）。

### 3.6 从 library 直接构建（不跑 OCR）

`library/` 存放已经整理好的完整 `APP_DATA` 知识包。适用于“数据已经跑出来，只想重建页面”或“换一套母版/标题重新交付”的场景。

```bash
# 现有两法包
python scripts/build_kb.py \
  --data library/cpa-two-laws/app_data.json \
  --out  output/cpa-two-laws.html \
  --title "CPA知识台"
```

新增知识包：

1. 把完整 `app_data.json` 放到 `library/<pack-id>/app_data.json`；
2. 在 `library/manifest.json` 登记 id / 统计 / 来源；
3. 写一个 `library/<pack-id>/README.md`（来源、卡片数、已知残余、构建命令）；
4. 用 `build_kb.py` 构建并用 `examples/smoke_test.py` 或浏览器检查。

最小契约：`meta.title` / `meta.subjects` / `cards[]` / `chapters[]`。完整结构见 `library/README.md` 与第 5 节。

## 4. 格式路由

| 输入 | 主引擎 | 锚点 | 卡片粒度 | `source` 显示 |
|---|---|---|---|---|
| PDF（有文字层） | PyMuPDF | `<!-- PDF_PAGE_n -->` | 按段落 | `文档 n` |
| PDF（扫描 / 强制 ocr） | 本地 RapidOCR | `<!-- PDF_PAGE_n -->` | 按段落 | `文档 n` |
| 图片 PNG/JPG/… | 本地 RapidOCR | `<!-- PDF_PAGE_n -->` | 按段落 | `文档 n` |
| DOCX | `markitdown[all]`（缺依赖则 python-docx） | `<!-- PDF_PAGE_n -->` | 按段落 | `文档 n` |
| HTML / MD / TXT | `markitdown[all]`（缺依赖则 bs4 / 纯文本） | `<!-- PDF_PAGE_n -->` | 按段落 | `文档 n` |
| **PPTX** | python-pptx 逐页（保证每页 1 卡） | `<!-- SLIDE_n -->` | **每页 1 张核心卡片** | `幻灯片 n` |

PPT 采用 python-pptx 而非 markitdown，是为了严格满足「每页一个核心卡片」：
markitdown 的 PPTX 输出不保证稳定的分页面标记；`python-pptx` 缺失时才回退到 markitdown 并解析
`<!-- Slide number: n -->`。Word / HTML / TXT 主路径均为 markitdown。

OCR 逐页结果写入 `<out-dir>/.ocr_cache/`，**支持断点续跑**；单页失败只记录日志，不中断全书。
运行时会生成一份临时单线程 ONNX 配置传入 RapidOCR，避免 4 核环境下多线程超订导致的 CPU 节流，且不修改已安装的包。

## 5. 卡片 JSON Schema

`extract_cards.py` 输出的是**完整 APP_DATA**（`meta / chapters / cards / coverage / glossary`），
其中 `cards[]` 每张与现有学习台 29 字段完全一致；`build_html.py` 也兼容「纯卡片数组」输入。

| 字段 | 说明 |
|---|---|
| `id` | 形如 `D-1.1`，同时生成 `anchor` |
| `subject` / `chapter` / `chapterName` / `section` | 科目与章节，标题启发式识别 |
| `title` / `ruleText` | 标题（超长加「（节选）」）/ 原文（**不改写、不推断**） |
| `source` | 动态：`幻灯片 X` 或 `文档 X`，并带科目/章节 |
| `page` / `pageStart` / `pageEnd` / `pdfPage` | 页码与回溯信息 |
| `mdAnchor` | 对应 `<!-- PDF_PAGE_n -->` / `<!-- SLIDE_n -->` 锚点名 |
| `layer` | 固定 `fact`；另有母版支持的 `inference/skeleton/external/ocr` 分色样式 |
| `numbers` | 从 `ruleText` 原样抽取的数字/百分比/期限 |
| `priority` / `freq` / `qtype` | 非教材资源一律默认值 `P1` / `中` / `案例` |
| `lawRefs` / `lawText` / `lawVerified` / `confusable` / `example` / `table` | 空值 / `False` / `None` |
| `ocr_confidence` / `ocr_source` / `needs_review` | OCR 置信度、是否 OCR 来源、是否需核对 |

质量门禁（`<stem>_cards_quality_gate.json`）：必填字段齐全、id 唯一、每条可回溯到 Markdown 锚点、
数字与原文一致、法律关键词未改写、低置信或含 `[?]` 的条目标记 `needs_review`。

## 6. 母版说明

`assets/template.html` 由最新的 `CPA知识学习台_已合并.html` 生成（`scripts/build_template.py` 可复现）：

- **CSS 13006 字节逐字未改**；所有 JS 交互函数、事件绑定、深浅色切换、顶栏搜索与四维筛选、
  卡片标签、出处弹层、笔记 localStorage、OCR 来源警示条 **100% 保留**。
- **参数化**（通用化的必要改造）：原 JS 有 4 处 `['税法','经济法']` 写死、筛选器科目写死、
  脚注整段写死 CPA 说明。若只换卡片数据，新资料的科目在目录树与卡片分组里**根本渲染不出来**。
  因此把这些改为从 `APP_DATA.meta.subjects` / `meta.footnote` 读取，并把「教材」文案中性化为「资料」。
  交互逻辑与函数结构不变。
- **补齐手势**：原始学习台只有汉堡按钮 / 点遮罩 / Esc 关闭抽屉，**没有 touch 手势**。
  母版新增了移动端手势：抽屉打开时右滑或左滑关闭、从屏幕左边缘右滑打开，并过滤纵向滚动误触。
- 母版内是 6 张 mock 卡片、2 个自定义科目、3 章、3 条术语的演示数据，覆盖 5 种 `layer` 分色、
  OCR 警示条、表格、易混条目、法条引用、例题等全部展示形态；打开即可看到完整工作台风格。

`build_html.py` **只替换 `<script id="APP_DATA">` 的 JSON 内容**（外加页面 `<title>` 与顶栏品牌名），
绝不重复注入脚本；注入前把 `</` 转义为 `<\/`，防止资料中的 `</script>` 截断页面。

## 7. 跨 Agent 安装与调用

本仓库同时是一个可移植的 Skill 目录。`SKILL.md` 是 Agent 入口，`README.md` 是人类入口；脚本与 Agent 无关。

### 7.1 一键安装

```bash
python scripts/install_skill.py --target dsh        # DSH
python scripts/install_skill.py --target workbuddy  # WorkBuddy
python scripts/install_skill.py --target codebuddy  # CodeBuddy
python scripts/install_skill.py --target claude     # Claude Code
python scripts/install_skill.py --target codex      # Codex（支持 skills 的版本）
python scripts/install_skill.py --target custom --dest ./.agents/skills
```

脚本只复制目录，不改任何 Agent 配置；默认不覆盖，`--force` 覆盖，`--dry-run` 只看路径。

### 7.2 常见路径

| 平台 | 常见 skills 目录 | 备注 |
|---|---|---|
| DSH (DeepSeek Harness) | `~/.dsh/skills/` | 本机实测存在 |
| WorkBuddy | `~/.workbuddy/skills/` | 本机实测存在 |
| CodeBuddy | `~/.codebuddy/skills/` | 旧版 SKILL.md 默认路径 |
| Claude Code | `~/.claude/skills/` 或项目 `.claude/skills/` | 以你的版本为准 |
| Codex | `~/.codex/skills/` 或项目 `.codex/skills/` | 只读 AGENTS.md 的版本，把本文件加入项目说明 |
| 其他 Agent | 任意 skills 目录 | 用 `--target custom --dest <dir>` |

> 路径会随平台版本变化；不要把这张表当成硬编码。安装脚本的 `--dest` 永远可用。
> 如果 Agent 不加载 `SKILL.md`，把本文件内容作为项目说明 / system prompt 给它，脚本仍可独立运行。

### 7.3 对话触发与交付

安装后直接说：

- 「**把 /data/公司法讲义.pdf 转为学习台**」
- 「**用 universal-learning-desk 把这份 PPT 做成学习台**」
- 「**扫描版 PDF 乱码，OCR 重建教材并生成学习台**」
- 「**用 library 里的两法包重新构建知识台**」

Agent 加载 SKILL.md 后按第 3 节执行，并把最终 `xxx_学习台.html` 交付。完全脱离 Agent 也可以直接用命令行。

## 8. 冒烟测试

```bash
python examples/make_fixtures.py --out-dir ./fixtures
python examples/smoke_test.py    --fixtures ./fixtures --out-dir ./smoke_out
```

覆盖 8 种格式，逐项校验：解析引擎、锚点类型、卡片/章节数、门禁、CSS 未改、单文件离线，
并在检测到 chromium / google-chrome 时用 headless 浏览器验证「当前 N / N 张卡片」、
7 个模块、手势、主题按钮与无 JS 致命错误。报告写在 `smoke_out/smoke_test_report.json`。

本 Skill 交付前实测：**8/8 格式全部通过**（含 2 个真实 RapidOCR 路径）。

## 9. 已知限制

- 卡片是**段落级 / 幻灯片级**条目，不做知识归纳；`priority/freq/qtype` 为编排层默认值。
- 语义纠错（错别字、断句）不在本 Skill 内自动执行；如需，可在 `extract_cards.py` 之后增加
  「只送审低置信片段」的步骤，别把全文一次性送模型。
- 章节识别依赖 `第X章` / `第X节` / Markdown `#`~`###` 标题；无标题资料请用 `--chapter-every`。
- 页码 `page` 是资料内部的页面单元序号，**不是** PDF 物理页与教材页码的 offset 换算；
  如需要 offset，请在 `extract_cards.py` 之后按资料实际情况映射。
- `100dvh` 需 iOS 15.4+ / Chrome 108+，旧浏览器自动回退 `100vh`。
- 不同资料请使用不同 `--out-dir`：同名不同扩展名（如 `a.pdf` / `a.docx`）的中间产物文件名相同，会互相覆盖。
- `library/cpa-two-laws` 的教材内容仅限个人学习，不在代码许可范围内；公开仓库前请确认授权。

## 10. Library 知识库包

`library/` 是给“已经跑过一次 OCR / 已经有一版 APP_DATA”的人准备的复用层。

```
library/
├── manifest.json        # 包索引：id / 统计 / 来源 / 构建方式
├── README.md            # 包的契约与新增方法
└── cpa-two-laws/
    ├── app_data.json    # 完整 APP_DATA（1515 卡 / 26 章 / 168 术语）
    └── README.md        # 本包来源、统计、已知残余
```

构建：

```bash
python scripts/build_kb.py \
  --data library/cpa-two-laws/app_data.json \
  --out  output/cpa-two-laws.html \
  --title "CPA知识台"
```

包的最小契约：

- `meta.title`、`meta.subjects`
- `cards[]`：`id / title / ruleText / subject / chapter / page / source` 必填
- `chapters[]`：`subject / no / name / pageStart / pageEnd`
- `coverage[]`、`glossary[]` 可以为空

新增包时，把上述数据放进 `library/<pack-id>/`，在 `library/manifest.json` 登记，并在 `library/README.md` 的表格里补一行。**不要**把原始 PDF / 教材全文一起塞进 library；library 存的是已整理的 APP_DATA。
