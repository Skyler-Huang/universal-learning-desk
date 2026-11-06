#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把重建后的 APP_DATA 注入知识台母版，产出单文件离线 HTML。

与 build_html.py 的差别：
  1. 主脚本替换为 assets/app_kb.js（检索型前端：归一化 / 多词 AND / 拼音 / 容错 / 导出）
  2. 构建期数据防呆（空卡、坏 id、术语乱码直接拒绝构建）
  3. 注入拼音表 meta.pyMap（仅标题/章名/术语用字，约 20KB）
  4. 移动端抽屉 82vw + 版本号/生成时间
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAD_TERM = re.compile(r"[\d，。、；：？！“”‘’\"'/\\|_=+*<>\[\]{}·@#$^&~`]")


def log(m: str) -> None:
    print("[build] " + m, flush=True)


def guard(data: Dict[str, Any]) -> List[str]:
    errs = []
    cards = data.get("cards") or []
    gloss = data.get("glossary") or []
    if len(cards) < 100:
        errs.append("卡片过少：%d" % len(cards))
    if not data.get("chapters"):
        errs.append("chapters 为空")
    ids = [c["id"] for c in cards if c.get("id")]
    if len(ids) != len(cards):
        errs.append("存在无 id 卡片")
    if len(set(ids)) != len(ids):
        errs.append("id 重复")
    for c in cards:
        if not c.get("ruleText"):
            errs.append("空正文：%s" % c.get("id"))
            break
        if c.get("pdfPage") in (None, 0):
            errs.append("缺 pdfPage：%s" % c.get("id"))
            break
    bad = [g["term"] for g in gloss if BAD_TERM.search(g.get("term", "")) or len(g.get("term", "")) > 12]
    if bad:
        errs.append("术语乱码未清除：%s" % bad[:5])
    return errs


def build_py_map(data: Dict[str, Any]) -> Dict[str, str]:
    # 已打包的 library 通常自带完整的 pyMap：直接复用，避免为了重建页面强装 pypinyin。
    existing = (data.get("meta") or {}).get("pyMap")
    if isinstance(existing, dict) and existing:
        return existing
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        return {}
    chars = set()
    for c in data["cards"]:
        chars.update(c.get("title", ""))
        chars.update(c.get("chapterName", ""))
    for g in data["glossary"]:
        chars.update(g.get("term", ""))
    out = {}
    for ch in chars:
        if "\u4e00" <= ch <= "\u9fa5":
            py = lazy_pinyin(ch)[0]
            if py and py != ch:
                out[ch] = py
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--template", default=os.path.join(ROOT, "assets", "template.html"))
    ap.add_argument("--js", default=os.path.join(ROOT, "assets", "app_kb.js"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="CPA知识台")
    a = ap.parse_args(argv)

    data = json.load(open(a.data, encoding="utf-8"))
    errs = guard(data)
    if errs:
        for e in errs:
            log("防呆拒绝：" + e)
        return 1

    meta = data["meta"]
    meta["title"] = a.title
    meta["generated"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    meta["pyMap"] = build_py_map(data)
    meta["version"] = "kb-2.0"
    meta["footnote"] = (
        "数据来源：%s；共 %d 张卡片（%s），术语 %d 条。卡片由已校验主干数据重建："
        "语义切分、页眉页脚剔除、数字守恒校验，正文用词与数字未改写。"
        "术语仅从卡片正文派生并通过乱码闸门。" % (
            meta.get("sourceNote", "两本教材 PDF"),
            len(data["cards"]),
            " / ".join("%s %d" % (s, sum(1 for c in data["cards"] if c["subject"] == s)) for s in meta["subjects"]),
            len(data["glossary"]),
        )
    )

    tpl = open(a.template, encoding="utf-8").read()
    js = open(a.js, encoding="utf-8").read()

    # 1) 注入数据
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl, n = re.subn(r'(<script[^>]*id="APP_DATA"[^>]*>).*?(</script>)',
                     lambda m: m.group(1) + payload + m.group(2), tpl, count=1, flags=re.S)
    if n != 1:
        log("ERROR 未找到 APP_DATA 容器")
        return 2

    # 2) 替换主脚本（保留后置的布局修复脚本）
    tpl, n = re.subn(r'(<script data-page-node-id="4ZjgohMnHKMe8IZCBlwQ39"[^>]*>).*?(</script>)',
                     lambda m: m.group(1) + "\n" + js + "\n" + m.group(2),
                     tpl, count=1, flags=re.S)
    if n != 1:
        log("ERROR 未找到主脚本容器")
        return 2

    # 3) 标题 / 品牌 / 侧栏标题
    tpl = re.sub(r"<title[^>]*>.*?</title>", "<title>%s</title>" % a.title, tpl, count=1, flags=re.S)
    tpl = re.sub(r'(<div[^>]*class="brand"[^>]*>.*?</span>)(?:<!--.*?-->)?[^<]*(</div>)',
                 lambda m: m.group(1) + a.title + m.group(2), tpl, count=1, flags=re.S)
    tpl = tpl.replace("六大模块", "知识模块")

    # 4) 移动端抽屉 82vw（保留原 top/height 与手势）
    tpl = tpl.replace(
        "  .sidebar{position:fixed;left:0;top:var(--topbar-h);",
        "  .sidebar{position:fixed;left:0;top:var(--topbar-h);\n    width:82vw;max-width:82vw;flex-basis:82vw;",
        1)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(tpl)

    log("输出 %s | %.2f MB | 卡片 %d | 术语 %d | pyMap %d 字" % (
        a.out, os.path.getsize(a.out) / 1048576, len(data["cards"]),
        len(data["glossary"]), len(meta["pyMap"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
