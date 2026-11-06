# 知识库包（library）

`library/` 存放已经整理好的 `APP_DATA` 知识包。它让你**不再重跑 OCR**，直接用一份 JSON 构建知识台。

> **本仓库不附带任何教材数据包。** `cpa-two-laws` 的 1515 张卡片来自个人合法持有的 CPA 教材，仅限个人学习，出于授权原因不随仓库分发（见文末「权利与边界」）。仓库里给的是**空包模板**：`library/pack-template/`。拿你自己的教材跑一遍流水线，产出的 `app_data.json` 放回 `library/<pack-id>/` 即可。

```bash
# 从模板起步
cp library/pack-template/app_data.example.json library/my-pack/app_data.json
python scripts/build_kb.py \
  --data library/my-pack/app_data.json \
  --out  output/my-pack.html \
  --title "我的知识台"
```

## 一个知识包长什么样

```
library/<pack-id>/
├── app_data.json      # 必须是完整的 APP_DATA：meta / chapters / cards / coverage / glossary
└── README.md          # 来源、统计、构建命令、已知残余
```

`app_data.json` 的结构与 `scripts/build_kb.py --data` 完全一致。最小要求：

- `meta.title`、`meta.subjects`
- `cards[]`：`id / title / ruleText / subject / chapter / page / source` 必填
- `chapters[]`：至少有 `subject / no / name / pageStart / pageEnd`
- `coverage[]`、`glossary[]`：可以为空，但建议保留

## 现有的包

| id | 内容 | 卡片 | 章 | 术语 | 随仓库分发 |
|---|---|---:|---:|---:|---|
| `cpa-two-laws` | 2026 CPA《税法》+《经济法》 | 1515 | 26 | 168 | ❌ 否，授权原因 |
| `pack-template` | 空包模板（示范字段与切分粒度） | 1 | 1 | 0 | ✅ 是 |

`cpa-two-laws` 的元数据登记在 `manifest.json` 里，`bundled: false`：它告诉你「这个技能的产出长什么样、规模多大」，但要自己用教材重建才有数据。

## 新增一个包

1. 用 `scripts/run_pipeline.py` 或 `scripts/rebuild_cards.py` 产出一份 `app_data.json`；
2. 放进 `library/<pack-id>/app_data.json`；
3. 在 `library/manifest.json` 的 `packs` 里登记；
4. 跑一次 `build_kb.py`，用 `examples/smoke_test.py` 或浏览器检查。

## 权利与边界

这个技能的**代码**是 MIT（见仓库根 `LICENSE`），**教材内容**不是。

`cpa-two-laws` 的卡片来自用户合法持有的教材，仅用于个人学习。**不要把这份数据包当成人人可以再分发的开放语料**——本仓库因此不收录它，`library/*/app_data.json` 也写进了 `.gitignore`，避免你本地构建完顺手提交上去。要公开分享，请先确认教材授权，或只发布构建脚本和空包模板。代码本身与数据包的权利分开处理。
