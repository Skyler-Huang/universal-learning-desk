#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""母版再生成工具（可选，正常调用 Skill 不需要运行本脚本）。

从最新的「CPA知识学习台_已合并.html」生成通用母版 assets/template.html：
  * CSS 一字不动；
  * 全部 JS 交互函数 / 事件绑定 / 深浅色 / 筛选 / 卡片标签 / OCR 警示条 100% 保留；
  * 仅把写死的「税法 / 经济法」科目、CPA 脚注、教材文案改为从 APP_DATA 读取（参数化）；
  * 补齐移动端手势：右滑/左滑关闭抽屉、从左边缘右滑打开抽屉；
  * APP_DATA 中的 2569 张真实卡片替换为演示用 mock 数据。

用法：
  python scripts/build_template.py --source /path/CPA知识学习台_已合并.html \
                                   --out assets/template.html
"""
import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(ROOT, "assets", "template.html")

# ---------------------------------------------------------------- 手势代码
GESTURE = r"""
/* ===== 移动端抽屉手势（母版补齐；不与纵向滚动冲突） ===== */
(function(){
  var x0=null, y0=null, wasOpen=false;
  document.addEventListener('touchstart',function(e){
    if(!e.touches || e.touches.length!==1){ x0=null; return; }
    x0=e.touches[0].clientX; y0=e.touches[0].clientY;
    wasOpen=$('#sidebar').classList.contains('open');
  },{passive:true});
  document.addEventListener('touchend',function(e){
    if(x0==null || !e.changedTouches || !e.changedTouches.length) return;
    var t=e.changedTouches[0], dx=t.clientX-x0, dy=t.clientY-y0, sx=x0;
    x0=null;
    if(Math.abs(dx)<60 || Math.abs(dx)<Math.abs(dy)*1.3) return;   /* 纵向滚动 / 短滑忽略 */
    if(wasOpen){ closeDrawer(); }                                    /* 右滑或左滑均关闭抽屉 */
    else if(sx<40 && dx>0){                                          /* 从左边缘右滑打开 */
      $('#sidebar').classList.add('open'); $('#overlay').classList.add('on');
    }
  },{passive:true});
})();
"""


# ---------------------------------------------------------------- mock 数据
def _card(**kw):
    """按现有系统的完整 Schema 造一张卡片（29 字段）。"""
    base = {
        "id": "S1.1", "title": "示例条目", "priority": "P1", "freq": "中",
        "qtype": "案例", "subject": "示例资料 A", "chapter": 1,
        "chapterName": "基础概念", "section": "", "page": 1,
        "pageStart": 1, "pageEnd": 6, "source": "示例资料 A / 第1章 基础概念 / 文档 1",
        "ruleText": "示例正文。", "numbers": [], "lawRefs": [], "lawText": None,
        "effectiveDate": None, "lawVerified": False, "confusable": [],
        "example": False, "table": None, "layer": "fact", "anchor": "#e-S1-1",
        "pdfPage": 1, "mdAnchor": "PDF_PAGE_1", "ocr_confidence": None,
        "ocr_source": False, "needs_review": False,
    }
    base.update(kw)
    base["anchor"] = "#e-" + base["id"].replace(".", "-")
    return base


def mock_app_data():
    subj_a, subj_b = "示例资料 A", "示例资料 B"
    chapters = [
        {"subject": subj_a, "no": 1, "name": "基础概念", "part": "",
         "sections": ["定义", "适用范围"], "pageStart": 1, "pageEnd": 6},
        {"subject": subj_a, "no": 2, "name": "核心规则", "part": "",
         "sections": ["适用", "例外"], "pageStart": 7, "pageEnd": 12},
        {"subject": subj_b, "no": 1, "name": "演示章节", "part": "",
         "sections": [], "pageStart": 1, "pageEnd": 8},
    ]
    coverage = []
    for ch in chapters:
        n = sum(1 for c in MOCK_CARDS if c["subject"] == ch["subject"] and c["chapter"] == ch["no"])
        coverage.append({
            "subject": ch["subject"], "no": ch["no"], "name": ch["name"],
            "pdfStart": ch["pageStart"], "pdfEnd": ch["pageEnd"],
            "pageStart": ch["pageStart"], "pageEnd": ch["pageEnd"],
            "sourcePages": ch["pageEnd"] - ch["pageStart"] + 1,
            "rules": n, "numbers": 2, "tables": 0, "examples": 1,
            "cards": n, "status": "母版演示数据",
        })
    return {
        "meta": {
            "title": "示例学习台 · 母版演示",
            "subjects": [subj_a, subj_b],
            "taxChapters": 2, "jjfChapters": 1, "taxPages": 12, "jjfPages": 8,
            "offset": 0, "tableCount": 0, "directoryTables": 0, "bodyTables": 0,
            "note": "本页为 universal-learning-desk 的母版演示数据，非真实教材内容。",
            "noteFromUser": "运行本 Skill 处理你的资料后，此处会替换为真实的处理说明。",
            "jjfOffset": 0, "offsetBySubject": {},
            "ocrEngine": "本地 RapidOCR（母版演示）",
            "jjfCardsFromOcr": 0, "taxCardsFromOcr": 0,
            "footnote": "这是 universal-learning-desk 母版演示页：7 个模块、深浅色主题、顶栏搜索与筛选、"
                        "卡片标签、OCR 来源警示条、右滑关闭抽屉均可正常使用。"
                        "单文件离线，无 CDN、无服务器；笔记仅保存在本地浏览器。",
        },
        "chapters": chapters,
        "cards": MOCK_CARDS,
        "coverage": coverage,
        "glossary": [
            {"term": "知识卡片", "def": "把资料原文按段落或幻灯片切分后的最小可复习单元。",
             "subject": subj_a, "chapter": 1, "page": 1},
            {"term": "OCR 来源", "def": "由图片或扫描 PDF 经本地 OCR 识别生成的卡片，低置信条目需核对原文。",
             "subject": subj_a, "chapter": 1, "page": 2},
            {"term": "锚点", "def": "形如 <!-- PDF_PAGE_n --> 的页码标记，用于把卡片回溯到原始资料。",
             "subject": subj_b, "chapter": 1, "page": 1},
        ],
    }


MOCK_CARDS = [
    _card(
        id="S1.1", subject="示例资料 A", chapter=1, chapterName="基础概念",
        title="知识卡片是资料原文切分后的最小复习单元",
        ruleText="知识卡片是把资料原文按段落或幻灯片切分后的最小可复习单元，"
                 "每条卡片都必须能回溯到原始资料的分页锚点。纳税人应当在规定期限内办理申报，"
                 "适用 13% 税率的情形不得擅自扩大。",
        numbers=["13%", "500 万元"], page=1, pdfPage=1, mdAnchor="PDF_PAGE_1",
        lawRefs=[{"law": "示例法", "article": "12"}],
        confusable=["S1.2"], example=True,
        ocr_source=True, ocr_confidence=0.9821, needs_review=False,
        source="示例资料 A / 第1章 基础概念 / 文档 1（本地OCR）",
    ),
    _card(
        id="S1.2", subject="示例资料 A", chapter=1, chapterName="基础概念",
        title="OCR 来源卡片会显示局部警示条",
        ruleText="OCR 来源卡片在正面显示警示条，低置信条目需核对原文。"
                 "本条含不确定的识别片段 [?]，用于演示 needs_review 标记效果。",
        page=2, pdfPage=2, mdAnchor="PDF_PAGE_2", section="定义",
        table="| 项目 | 数值 |\n| --- | --- |\n| 税率 | 13% |\n| 期限 | 30 日 |",
        ocr_source=True, ocr_confidence=0.8234, needs_review=True,
        source="示例资料 A / 第1章 基础概念 / 文档 2（本地OCR）",
    ),
    _card(
        id="S2.1", subject="示例资料 A", chapter=2, chapterName="核心规则",
        title="推断层卡片用于区分编排信息",
        ruleText="优先级、考频、题型等标签属于学习编排（推断层），与资料原文分色显示，"
                 "不得据此推断原文没有的内容。",
        page=7, pageStart=7, pageEnd=12, pdfPage=7, mdAnchor="PDF_PAGE_7",
        layer="inference", qtype="多选", priority="P0", freq="高",
        source="示例资料 A / 第2章 核心规则 / 文档 7",
    ),
    _card(
        id="S2.2", subject="示例资料 A", chapter=2, chapterName="核心规则",
        title="规范性语句会进入「行动规则」模块",
        ruleText="纳税人应当按照规定期限缴纳税款；不得伪造、变造、隐匿、擅自销毁账簿。"
                 "符合免征条件的，可以依法申请减免。",
        page=8, pageStart=7, pageEnd=12, pdfPage=8, mdAnchor="PDF_PAGE_8",
        example=True, qtype="计算", numbers=["30 日"],
        source="示例资料 A / 第2章 核心规则 / 文档 8",
    ),
    _card(
        id="T1.1", subject="示例资料 B", chapter=1, chapterName="演示章节",
        title="材料未覆盖的占位卡片（skeleton）",
        ruleText="资料未涉及该知识点时以占位卡片呈现，不做补写、不编造内容。",
        page=1, pageStart=1, pageEnd=8, pdfPage=1, mdAnchor="PDF_PAGE_1",
        layer="skeleton", source="示例资料 B / 第1章 演示章节 / 文档 1",
    ),
    _card(
        id="T1.2", subject="示例资料 B", chapter=1, chapterName="演示章节",
        title="外部核验层卡片",
        ruleText="需要外部法条或权威来源核验的条目单独标记为外部核验层，"
                 "本 Skill 默认 lawVerified=false。",
        page=2, pageStart=1, pageEnd=8, pdfPage=2, mdAnchor="PDF_PAGE_2",
        layer="external", source="示例资料 B / 第1章 演示章节 / 文档 2",
    ),
]


# ---------------------------------------------------------------- 参数化改造
def generalize(js):
    """只替换硬编码数据/文案来源，不改动任何交互函数与事件结构。"""
    steps = []

    def rep(old, new, cnt=1, label=""):
        nonlocal js
        n = js.count(old)
        assert n == cnt, "替换命中数异常 %r: 期望 %d 实际 %d (%s)" % (old[:60], cnt, n, label)
        js = js.replace(old, new)
        steps.append((label or old[:40], n))

    # 1) 科目列表改为从 APP_DATA 读取
    rep("var state = {view:'cards'",
        "var SUBJECTS = (DATA.meta.subjects && DATA.meta.subjects.length) ? DATA.meta.subjects : ['资料'];\n"
        "var state = {view:'cards'", 1, "注入 SUBJECTS")
    rep("['税法','经济法'].forEach(function(sub){",
        "SUBJECTS.forEach(function(sub){", 4, "4 处科目遍历参数化")
    rep("['subject','科目',['税法','经济法']]",
        "['subject','科目',SUBJECTS]", 1, "筛选器科目参数化")

    # 2) 模块描述中性化
    rep("['framework','核心框架','两本教材的章节与节骨架']",
        "['framework','核心框架','资料的章节与节骨架']", 1, "MODS framework")
    rep("['actions','行动规则','教材原文中的规范性规则']",
        "['actions','行动规则','资料原文中的规范性规则']", 1, "MODS actions")
    rep("['quiz','学习自检','教材例题与案例']",
        "['quiz','学习自检','资料例题与案例']", 1, "MODS quiz")

    # 3) 核心框架页头（原写死 税法14章/经济法12章）
    old_fw = ("  var html='<div class=\"panel\"><h3>核心框架 · 章节骨架（来自教材目录原文）</h3>"
              "<p style=\"font-size:13px;color:var(--muted)\">税法 '+DATA.meta.taxChapters+"
              "' 章 / 经济法 '+DATA.meta.jjfChapters+' 章；经济法分四编，第三编商事法律制度"
              "（第 5–9 章）为案例分析题主要出处。</p></div>';")
    new_fw = ("  var html='<div class=\"panel\"><h3>核心框架 · 章节骨架（来自资料目录）</h3>"
              "<p style=\"font-size:13px;color:var(--muted)\">共 '+SUBJECTS.length+' 个科目 / '"
              "+CHAPTERS.length+' 章；'+esc(DATA.meta.note||'')+'</p></div>';")
    rep(old_fw, new_fw, 1, "核心框架页头参数化")

    # 4) 任务说明标题
    rep("任务说明 · 模型添加（非教材原文）", "编排说明 · 编排层添加（非原文）", 1, "导学标题")

    # 5) OCR 警示条文案（先改，避免被后续全局替换影响）
    rep("OCR 来源，低置信条目需核对教材", "OCR 来源，低置信条目需核对原文", 1, "OCR 警示条")

    # 6) 搜索空态
    rep("两本教材中未检索到该内容，本学习台不补写、不编造。",
        "资料中未检索到该内容，本学习台不补写、不编造。", 1, "搜索空态")

    # 7) 脚注整块改为读 meta.footnote
    s0 = js.index("  $('#footnote').innerHTML=")
    s1 = js.index("\n", js.index("';", s0)) + 1
    js = js[:s0] + ("  $('#footnote').textContent = DATA.meta.footnote || "
                    "'单文件离线学习台 · 无 CDN · 笔记仅存本地浏览器。';\n") + js[s1:]
    steps.append(("脚注改为 meta.footnote", 1))

    # 8) 全局文案中性化（CSS / 逻辑不动）
    n = js.count("教材")
    js = js.replace("教材", "资料")
    steps.append(("教材→资料 文案中性化", n))

    return js, steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="最新的 CPA知识学习台_已合并.html")
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()

    h = open(a.source, encoding="utf-8").read()

    # --- 1) 抽出主 JS 并参数化 ---
    scripts = re.findall(r"<script([^>]*)>(.*?)</script>", h, re.S)
    main_js = max((b for attr, b in scripts
                   if "application/json" not in attr and len(b) > 5000), key=len)
    new_js, steps = generalize(main_js)

    # --- 2) 补齐手势：紧跟 overlay 点击关闭之后 ---
    anchor = "$('#overlay').onclick=closeDrawer;"
    assert anchor in new_js
    new_js = new_js.replace(anchor, anchor + "\n" + GESTURE, 1)

    # --- 3) 用参数化后的 JS 替换原文（只替换主 JS） ---
    assert h.count(main_js) == 1
    h = h.replace(main_js, new_js, 1)

    # --- 4) 替换 APP_DATA 为 mock ---
    m = re.search(r'(<script[^>]*id="APP_DATA"[^>]*>)(.*?)(</script>)', h, re.S)
    assert m, "未找到 APP_DATA"
    payload = json.dumps(mock_app_data(), ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")          # 防止 JSON 中的 </script> 截断
    h = h[:m.start(2)] + payload + h[m.end(2):]

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(h)

    print("母版已生成:", a.out, "字节", len(h))
    print("参数化改造明细:")
    for k, v in steps:
        print("  - %-28s 命中 %d" % (k, v))
    print("  - 移动端手势            已补齐（右滑/左滑关闭、边缘右滑打开）")
    print("  - CSS                   未改动")
    print("  - mock 卡片              %d 张 / 2 个科目 / 3 章 / 3 条术语" % len(MOCK_CARDS))


if __name__ == "__main__":
    main()
