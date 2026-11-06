#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染注入层（universal-learning-desk / Stage 3）。

只替换母版 assets/template.html 中 <script id="APP_DATA"> 的 JSON 内容，
CSS / JS / 手势 / 深浅色 / 筛选 / 卡片标签 / OCR 警示条全部原样保留，
绝不重复注入脚本，产出单文件、离线、无 CDN 的 xxx_学习台.html。

输入：
  --cards   extract_cards.py 的完整 APP_DATA JSON；也兼容「纯卡片数组」
  --template 母版（默认 ../assets/template.html）
输出：
  --out     xxx_学习台.html
  --report  build_report.json（可选）
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(os.path.dirname(HERE), "assets", "template.html")
REQUIRED_TOP = ["meta", "chapters", "cards", "coverage", "glossary"]
REQUIRED_CARD = ["id", "subject", "chapter", "title", "ruleText", "source",
                 "page", "layer", "pdfPage"]


def log(msg: str) -> None:
    print("[build] " + msg, flush=True)


def load_app_data(path: str) -> Dict[str, Any]:
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, list):                       # 兼容「纯卡片数组」输入
        cards = d
        subject = cards[0].get("subject", "资料") if cards else "资料"
        chapters = []
        for no in sorted({x.get("chapter", 1) for x in cards}):
            first = next((x for x in cards if x.get("chapter", 1) == no), {})
            chapters.append({"subject": subject, "no": no,
                             "name": first.get("chapterName", "第 %s 章" % no),
                             "part": "", "sections": [], "pageStart": 1, "pageEnd": 1})
        d = {
            "meta": {"title": subject + " 学习台", "subjects": [subject],
                     "offset": 0, "note": "由 universal-learning-desk 生成。",
                     "noteFromUser": "优先级/考频/题型为编排层默认值。",
                     "footnote": "单文件离线学习台，无 CDN。",
                     "taxChapters": len(chapters), "jjfChapters": 0,
                     "taxPages": 0, "jjfPages": 0, "tableCount": 0,
                     "directoryTables": 0, "bodyTables": 0, "jjfOffset": 0,
                     "offsetBySubject": {}, "ocrEngine": "",
                     "jjfCardsFromOcr": 0, "taxCardsFromOcr": 0},
            "chapters": chapters, "cards": cards, "coverage": [], "glossary": [],
        }
    missing = [k for k in REQUIRED_TOP if k not in d]
    assert not missing, "APP_DATA 缺少顶层字段: %s" % missing
    assert isinstance(d["cards"], list), "cards 必须是数组"
    assert d["meta"].get("subjects"), "meta.subjects 不能为空"
    if not d["glossary"]:                         # JS 术语正则依赖非空
        d["glossary"] = [{"term": "资料锚点",
                          "def": "形如 <!-- PDF_PAGE_n --> 的页码标记，用于把卡片回溯到原始资料。",
                          "subject": d["meta"]["subjects"][0], "chapter": 1, "page": 1}]
    return d


def render(template: str, app_data: Dict[str, Any], out: str) -> Dict[str, Any]:
    tpl = open(template, encoding="utf-8").read()
    css_before = re.search(r"<style[^>]*>(.*?)</style>", tpl, re.S).group(1)

    m = re.search(r'(<script[^>]*id="APP_DATA"[^>]*>)(.*?)(</script>)', tpl, re.S)
    assert m, "母版缺少 <script id=\"APP_DATA\">，模板可能被破坏"

    payload = json.dumps(app_data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")       # 防止资料中的 </script> 截断页面

    h = tpl[:m.start(2)] + payload + tpl[m.end(2):]

    # 展示层数据：标题与顶栏品牌名跟随资料（不改动任何样式或脚本）
    title = html_lib.escape(str(app_data["meta"].get("title") or "学习台"))
    h = re.sub(r"(<title[^>]*>).*?(</title>)",
               lambda x: x.group(1) + title + x.group(2), h, count=1, flags=re.S)
    h = h.replace("CPA知识学习台</div>", title + "</div>", 1)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, "w", encoding="utf-8").write(h)

    # ---------- 校验 ----------
    css_after = re.search(r"<style[^>]*>(.*?)</style>", h, re.S).group(1)
    injected = re.search(r'<script[^>]*id="APP_DATA"[^>]*>(.*?)</script>', h, re.S).group(1)
    parsed = json.loads(injected.replace("<\\/", "</"))
    bad = [c.get("id") for c in parsed["cards"]
           if any(k not in c for k in REQUIRED_CARD)]
    external = re.findall(r'<script[^>]+src=["\']https?://|<link[^>]+href=["\']https?://', h)
    report = {
        "template": os.path.abspath(template),
        "output": os.path.abspath(out),
        "output_bytes": len(h),
        "title": app_data["meta"].get("title"),
        "subjects": app_data["meta"]["subjects"],
        "cards_injected": len(parsed["cards"]),
        "chapters": len(parsed["chapters"]),
        "needs_review": sum(1 for c in parsed["cards"] if c.get("needs_review")),
        "ocr_cards": sum(1 for c in parsed["cards"] if c.get("ocr_source")),
        "css_unchanged": css_before == css_after,
        "app_data_roundtrip_ok": len(parsed["cards"]) == len(app_data["cards"]),
        "cards_missing_required_fields": bad[:10],
        "external_scripts_or_styles": external,
        "gesture_touchstart_kept": "touchstart" in h,
        "ocr_tip_kept": "ocr-local-tip" in h,
        "theme_switch_kept": "themeBtn" in h,
        "single_file_offline": not bool(external),
        "passed": (css_before == css_after and not bad and not external
                   and len(parsed["cards"]) == len(app_data["cards"])),
    }
    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="APP_DATA + 母版 → 单文件学习台 HTML")
    ap.add_argument("--cards", required=True, help="extract_cards.py 输出的 JSON")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE, help="母版 template.html")
    ap.add_argument("--out", default=None, help="输出 HTML（默认 <名称>_学习台.html）")
    ap.add_argument("--report", default=None, help="构建报告 JSON 路径")
    a = ap.parse_args(argv)

    if not os.path.exists(a.template):
        log("ERROR 母版不存在: " + a.template)
        return 2
    app_data = load_app_data(a.cards)
    stem = os.path.splitext(os.path.basename(a.cards))[0].replace("_cards", "")
    out = a.out or os.path.join(os.getcwd(), stem + "_学习台.html")
    report = render(a.template, app_data, out)
    rep = a.report or os.path.splitext(out)[0] + "_build_report.json"
    with open(rep, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    log("卡片 %d 张 | 科目 %s | CSS 未改 %s | 单文件离线 %s" %
        (report["cards_injected"], report["subjects"],
         report["css_unchanged"], report["single_file_offline"]))
    log("校验 %s" % ("通过" if report["passed"] else "未通过"))
    log("已写出 " + out)
    log("已写出 " + rep)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
