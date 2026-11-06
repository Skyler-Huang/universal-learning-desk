# 知识包模板（pack-template）

这个目录是**空包模板**：把 `app_data.example.json` 复制成你自己的 `<pack-id>/app_data.json`，照着字段填满，再登记到 `library/manifest.json`。

```bash
mkdir -p library/my-pack
cp library/pack-template/app_data.example.json library/my-pack/app_data.json
# 填好后（至少 100 张卡，见下）：
python scripts/build_kb.py --data library/my-pack/app_data.json --out output/my-pack.html --title "我的知识台"
```

> ⚠️ **模板本身构建不过**，这不是 bug。`build_kb.py` 有一道数据门禁：卡片少于 100 张、或缺 `pdfPage`、或 id 重复/为空、或术语含乱码，一律拒绝构建。它的用途是防止半成品知识台被当成成品发出去。模板只有 1 张卡，只用来对齐字段。

## 契约

最小可构建的 `APP_DATA`：

| 键 | 要求 |
|---|---|
| `meta.title` | 必填，构建时会被 `--title` 覆盖 |
| `meta.subjects` | 必填，字符串数组，决定筛选下拉的科目 |
| `meta.pyMap` | 可选，术语的拼音映射；缺省时构建会自己生成（需装 `pypinyin`） |
| `meta.offset` / `offsetBySubject` | 可选，资料页序 → PDF 物理页的偏移，缺省 0 |
| `chapters[]` | 至少一项，含 `subject / no / name / pageStart / pageEnd`；`sections` 可为空 |
| `cards[]` | **≥100 张**，每张必填 `id / title / ruleText / subject / chapter / chapterName / page / pdfPage / source` |
| `coverage[]` | 可为空 |
| `glossary[]` | 可为空；术语 ≤12 字，不得含乱码或不透明指示词 |

`chapter` 是章号（数字），章名放 `chapterName`，两者都要有——前端按 `chapterName` 分组显示，按 `chapter` 排序。

`ruleText` 必须是**原文**。这个技能的定位是「可检索的原文」，不是「AI 改写过的笔记」：一旦改写，页码锚点和数字守恒就都失去了意义。

## 为什么不附带教材数据包

`library/cpa-two-laws/` 的 1515 张卡片来自个人合法持有的 CPA 教材，仅限个人学习使用，**不随本仓库分发**（见仓库根 `README.md` 的权利说明）。你需要时用自己手上的教材跑一遍流水线即可：

```bash
python scripts/run_pipeline.py --input 你的教材.pdf --out output/
```
