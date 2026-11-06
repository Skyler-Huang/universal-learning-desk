# universal-learning-desk

把 PDF / 扫描件 / PPT / Word / HTML / Markdown / TXT 变成**一个单文件、离线、可检索、可导出、可追溯**的知识台。

它不是又一个「把 PDF 转成 Markdown」的脚本，而是一条从**原始资料 → 带锚点的中间层 → 语义卡片 → 单文件 HTML**的完整流水线，附带质量门禁和一套可以直接交付的工作台界面。

> 代表产物：CPA《税法》+《经济法》1515 张卡片 / 168 条术语 / 26 章，线上示例 <https://hletian.cn/cpa/>
>
> 代码与脚本在本地运行，**不上传资料、不调用云 OCR、不调用 LLM API**。

---

## 它解决什么问题

| 常见做法 | 问题 | 这个项目 |
|---|---|---|
| PDF 直接丢给聊天窗口 | 页码、原文、数字不可追溯；长文被截断 | 每张卡都有 `page / source / anchor`，可回到资料位置 |
| PDF → Markdown → 手动整理 | 页眉页脚混入、半句切断、公式/数字被改写 | 语义切分 + 数字 token 守恒 + 噪声剔除，构建期门禁 |
| 用 Notion/飞书做知识库 | 需要账号、联网、导出受限 | 单文件 HTML，双击可开，可放 GitHub Pages |
| 让模型总结全书 | 归纳会丢原文，法条/教材不能这么用 | 卡片保留原文，不做自动改写；归纳由使用者决定 |
| 只在某个 Agent 里可用 | 换平台就失效 | CLI 独立可跑；同时提供多 Agent 安装方式 |

**定位**：不是「学习台」，而是**可检索、可导出、可追溯的第二大脑**。适合教材、法条、规范、讲义、培训资料等「原文本身有价值」的材料。

---

## 30 秒上手

要求：Python 3.10+。

```bash
git clone <this-repo> universal-learning-desk
cd universal-learning-desk

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

### 最简：从已有知识包构建（不跑 OCR）

> 仓库**不附带**教材数据包（授权原因）。数据包得自己产出：用自有资料跑一遍流水线，或照着 `library/pack-template/app_data.example.json` 的字段手填。

```bash
python scripts/build_kb.py \
  --data library/my-pack/app_data.json \
  --out  output/my-pack.html \
  --title "我的知识台"
```

> 构建前有门禁：卡片 ≥100 张、每张必须有 `pdfPage`，否则直接拒绝——防止半成品知识台被当成成品发出去。字段清单见 [`library/pack-template/README.md`](library/pack-template/README.md)。

打开 `output/my-pack.html`。界面和线上 <https://hletian.cn/cpa/> 是同一套。

### 从一份新资料构建

```bash
python scripts/run_pipeline.py \
  --input  "/path/公司法讲义.pdf" \
  --out-dir ./output \
  --subject "公司法" \
  --title   "公司法知识台"
```

产出：`./output/公司法讲义_学习台.html`。中间产物（Markdown、sidecar、卡片 JSON、门禁）在 `./output/_work/`。

### 只想要一个空母版看看

直接用浏览器打开 `assets/template.html`。里面是 mock 数据，展示 7 个模块、深浅色、抽屉手势、搜索/筛选/导出/笔记全部交互。

---

## 目录

```
universal-learning-desk/
├── README.md                     # 本文件（人类入口）
├── SKILL.md                      # Agent 入口（DSH / WorkBuddy / CodeBuddy / Claude Code / Codex 通用）
├── REPORT.md                     # 两法项目实测报告（1515 卡 / 数字守恒 / 门禁）
├── requirements.txt
├── .gitignore
├── assets/
│   ├── template.html             # 单文件母版（CSS/JS 全量，mock 数据）
│   └── app_kb.js                 # 检索/拼音/容错/导出引擎
├── scripts/
│   ├── universal_reader.py       # ① 多格式 → 带锚点 Markdown + sidecar
│   ├── extract_cards.py          # ② Markdown → APP_DATA + 质量门禁
│   ├── rebuild_cards.py          # ②' 已有卡片 → 语义重切分 + 术语重建
│   ├── build_html.py             # ③ 注入学习台母版
│   ├── build_kb.py               # ③' 注入知识台母版（推荐）
│   ├── run_pipeline.py           # 一键编排
│   ├── build_template.py         # 可选：从旧 HTML 重建母版
│   ├── extract_app_data.py       # 从旧 HTML 抽 APP_DATA
│   └── install_skill.py          # 安装到多个 Agent 的 skills 目录
├── library/                      # 可复用知识包（不重跑 OCR）
│   ├── manifest.json
│   ├── README.md
│   ├── pack-template/            # 空包模板：app_data.example.json + 字段说明
│   └── cpa-two-laws/
│       ├── app_data.json         # 不随仓库分发（教材授权），用自有资料重建
│       └── README.md             # 1515 卡 / 26 章 / 168 术语的来源与统计
└── examples/
    ├── make_fixtures.py          # 生成 8 种格式测试样例
    └── smoke_test.py             # 全格式冒烟 + 浏览器渲染校验
```

---

## 多 Agent 安装

这个仓库同时是一个 **Agent Skill**：`SKILL.md` 是给 Agent 读的入口，`README.md` 是给人读的入口。脚本本身与 Agent 无关。

### 一键安装

```bash
# 安装到 DSH
python scripts/install_skill.py --target dsh

# 安装到 WorkBuddy
python scripts/install_skill.py --target workbuddy

# 安装到 CodeBuddy
python scripts/install_skill.py --target codebuddy

# 安装到 Claude Code
python scripts/install_skill.py --target claude

# 安装到 Codex（支持 skills 的版本）
python scripts/install_skill.py --target codex

# 任意目录（例如项目内 .agents/skills）
python scripts/install_skill.py --target custom --dest ./.agents/skills
```

脚本会把整个目录复制到目标 `skills/universal-learning-desk/`，默认不覆盖；需要覆盖加 `--force`，只看路径加 `--dry-run`。

### 各平台手工路径

| 平台 | 常见位置 | 说明 |
|---|---|---|
| **DSH (DeepSeek Harness)** | `~/.dsh/skills/universal-learning-desk/` | 本机实测存在 |
| **WorkBuddy** | `~/.workbuddy/skills/universal-learning-desk/` | 本机实测存在 |
| **CodeBuddy** | `~/.codebuddy/skills/universal-learning-desk/` | 旧版 SKILL.md 里的默认路径 |
| **Claude Code** | `~/.claude/skills/universal-learning-desk/` 或项目 `.claude/skills/` | 以你的 Claude Code 版本为准 |
| **Codex** | `~/.codex/skills/universal-learning-desk/` 或项目 `.codex/skills/` | 若版本只读 `AGENTS.md`，把 `SKILL.md` 加进项目说明即可 |
| **其他 Agent** | 任意 skills 目录 | 只要平台会加载 `SKILL.md`；不会加载也能直接跑 CLI |

> 路径不是教条：不同版本可能变化。用 `install_skill.py --target custom --dest <你的目录>` 最稳。
> 如果你的 Agent 不读 `SKILL.md`，把 `SKILL.md` 的内容作为项目说明 / system prompt 喂给它，脚本仍可独立运行。

### 在对话里怎么触发

装好后直接说：

- 「把 `/data/公司法讲义.pdf` 转成知识台」
- 「用 universal-learning-desk 把这份 PPT 做成单文件工作台」
- 「扫描版 PDF 有乱码，OCR 重建教材并生成知识台」
- 「把这份资料加入 library，生成一个可检索的知识包」

Agent 会加载 `SKILL.md`，按里面的步骤调用脚本。没有 Agent 也能用，见下面的 CLI。

---

## 两种模式

### 学习台（v1）

适合第一次处理资料：按段落 / 幻灯片页生成卡片，保留原文，带 OCR 来源警示。

```bash
python scripts/run_pipeline.py --input 资料.pdf --out-dir ./output --subject "科目" --title "标题"
```

### 知识台（v2，推荐）

适合**已经有一版卡片**、但存在硬切半句 / 页眉页脚 / 术语乱码的语料。不重跑 OCR，不改写用词和数字，只做语义重切分、术语重建和检索增强。

```bash
# 0) 从旧 HTML 抽数据（或用现有 *_cards.json）
python scripts/extract_app_data.py --html 旧.html --out app_data_old.json

# 1) 语义重切分 + 术语重建
python scripts/rebuild_cards.py --in app_data_old.json --out app_data_new.json --report rebuild_gate.json

# 2) 注入知识台母版
python scripts/build_kb.py --data app_data_new.json --out 知识台.html --title "知识台"
```

### 从 library 构建（不跑 OCR）

```bash
# 仓库不带数据包：把自有资料产出的 app_data.json 放进 library/<pack-id>/
python scripts/build_kb.py \
  --data library/my-pack/app_data.json \
  --out  output/my-pack.html \
  --title "我的知识台"
```

新增一个知识包：见 [`library/README.md`](library/README.md)。包的契约是完整的 `APP_DATA`（`meta / chapters / cards / coverage / glossary`），最少要有 `meta.title / meta.subjects / cards[] / chapters[]`。

---

## 为什么是单文件

- **可交付**：一个 `.html` 发给别人，双击就能看，不需要账号、服务器、数据库。
- **可离线**：资料不出本机；不依赖 CDN、字体、API。
- **可部署**：直接放 GitHub Pages / 任意静态托管，路径下 `index.html` 即可。
- **可归档**：HTML 里内嵌 `APP_DATA`，十年后仍能打开；不依赖某个 SaaS。
- **可审计**：每张卡保留 `source / page / anchor`，能回到原文位置。

---

## 数据契约（APP_DATA）

`build_kb.py` 接受完整 APP_DATA：

```json
{
  "meta": {
    "title": "CPA知识台",
    "subjects": ["税法", "经济法"],
    "note": "构建说明",
    "footnote": "页脚说明"
  },
  "chapters": [
    {"subject": "税法", "no": 1, "name": "税法总论", "pageStart": 1, "pageEnd": 30}
  ],
  "cards": [
    {
      "id": "税-1.1.1",
      "title": "税收是国家取得财政收入的主要形式",
      "ruleText": "原文……",
      "subject": "税法",
      "chapter": 1,
      "chapterName": "税法总论",
      "page": 1,
      "source": "税法 / 第1章 / 教材第1页",
      "anchor": "#e-税-1-1-1"
    }
  ],
  "coverage": [],
  "glossary": []
}
```

`build_html.py` 也兼容「纯卡片数组」输入；`build_kb.py` 要求完整结构，因为它要渲染章节树、覆盖记录、术语索引和数据体检。

---

## 质量门禁

这不是「生成完就算」的脚本。`rebuild_cards.py` / `extract_cards.py` 会写门禁报告，不过则 FAIL：

- **id 唯一**，每卡有页码、有出处、可回溯到锚点；
- **数字守恒**：清洗后的页文本与最终卡片逐 token 对账，多一个少一个都 FAIL；
- **半句结尾** ≤ 0.5%（按句末标点判断）；
- **术语 SSOT**：只从最终卡片正文派生，拒绝乱码 / 指示词开头 / 定义过短；
- **标题**：语义标题，不出现「（节选）」；
- **运行期**：JSON 异常给可读错误页，不白屏。

`examples/smoke_test.py` 覆盖 8 种格式，检查解析引擎、锚点、卡片/章节数、门禁、CSS 未改、单文件离线，并在有 Chromium 时用 headless 浏览器验证模块切换、手势、主题按钮和 JS 错误。

---

## 部署到 GitHub Pages

1. 把生成的 `xxx_知识台.html` 改名为目标目录的 `index.html`，例如 `cpa/index.html`；
2. 提交到 GitHub Pages 仓库；
3. 访问 `https://<你的域名>/cpa/`。

本项目的 `library/cpa-two-laws` 就是线上 <https://hletian.cn/cpa/> 的数据来源。

---

## 常见问题

**Q：一定要装 RapidOCR 吗？**
不是。有文字层的 PDF 走 PyMuPDF；PPT 走 python-pptx；Office/HTML 走 markitdown。只有扫描件/乱码文字层才需要 OCR。缺依赖会自动降级并记录 warnings。

**Q：卡片是模型总结的吗？**
不是。`ruleText` 保留原文，脚本不改写、不推断。`priority / freq / qtype` 是编排层默认值；`lawRefs` 为空时不会伪造法条。

**Q：能在手机上用吗？**
生成的 HTML 响应式，抽屉 82vw，触控目标 44px；iOS 15.4+ / Chrome 108+ 支持 `100dvh`，旧浏览器回退 `100vh`。

**Q：能处理多大的书？**
两法项目实测 609 + 704 页、1515 张卡片、2.2 MB 单文件。更大的书建议按科目/分册拆开，`--max-cards` 可限制。

**Q：为什么不做自动摘要？**
教材/法条的原文位置和数字本身就是证据。自动摘要会引入不可追溯的改写；这个工具的价值是「可回原文」，不是「替你总结」。

---

## 已知限制

- 卡片是**段落级 / 幻灯片级**条目，不做知识归纳；`priority/freq/qtype` 为编排层默认值。
- 语义纠错（错别字、断句）不在 Skill 内自动执行；建议只送审低置信片段，别把全文一次性送模型。
- 章节识别依赖 `第X章 / 第X节 / Markdown #~###`；无标题资料用 `--chapter-every`。
- `page` 是资料内部页面单元序号，不是 PDF 物理页 / 出版社页码的自动换算；需要时按 `offsetBySubject` 映射。
- 不同资料用不同 `--out-dir`：同名不同扩展名（`a.pdf` / `a.docx`）的中间产物会互相覆盖。
- 大文件（数百 MB PDF）建议先拆分；OCR 时间和内存随页数增长。
- **教材内容仅限个人学习**：仓库不附带数据包，你若用自有教材构建，产出物不在代码许可范围内。

---

## 许可与权利

- **代码 / 脚本 / 母版**：MIT，见 [`LICENSE`](LICENSE)。
- **`library/` 数据**：仓库**不附带**教材数据包。`cpa-two-laws` 的 1515 张卡片来自用户合法持有的教材，**仅供个人学习**，不公开再分发；`library/*/app_data.json` 已写入 `.gitignore`。
- 第三方依赖（PyMuPDF、markitdown、RapidOCR、python-pptx 等）各自遵循其许可证。

---

## 相关

- 线上示例：<https://hletian.cn/cpa/>
- 原始项目报告：`REPORT.md`（1515 卡重建、数字守恒、门禁结果）
- 单文件学习台示例：<https://hletian.cn/cet6/>（另一个独立项目，不是本仓库）

如果这个项目对你有用，欢迎把它当成一个可复用的「资料 → 知识台」底座，而不是一次性脚本。
