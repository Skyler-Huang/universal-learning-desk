#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键编排（universal-learning-desk）。

    python scripts/run_pipeline.py --input 任意资料.pdf --subject 公司金融

依次执行：universal_reader → extract_cards → build_html，
中间产物落在 <out-dir>/_work/，最终 HTML 落在 <out-dir>/<name>_学习台.html。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import universal_reader            # noqa: E402
import extract_cards               # noqa: E402
import build_html                  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="任意资料 → 单文件学习台 HTML（一键）")
    ap.add_argument("--input", required=True, help="输入文件（PDF/图片/Word/PPT/HTML/MD/TXT）")
    ap.add_argument("--out-dir", default="./output", help="输出目录（默认 ./output）")
    ap.add_argument("--name", default=None, help="输出名（默认取输入文件名）")
    ap.add_argument("--subject", default=None, help="科目名（默认取文件名）")
    ap.add_argument("--title", default=None, help="学习台标题")
    ap.add_argument("--engine", choices=["auto", "ocr", "text"], default="auto")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-cards", type=int, default=5000)
    ap.add_argument("--chapter-every", type=int, default=0,
                    help="无标题时每 N 个页面单元归为一章")
    ap.add_argument("--id-prefix", default="D")
    a = ap.parse_args(argv)

    src = os.path.abspath(a.input)
    if not os.path.exists(src):
        print("[pipeline] ERROR 输入不存在: " + src)
        return 2
    stem = os.path.splitext(os.path.basename(src))[0]
    name = a.name or stem
    out_dir = os.path.abspath(a.out_dir)
    work = os.path.join(out_dir, "_work")
    os.makedirs(work, exist_ok=True)

    print("=" * 62)
    print("universal-learning-desk | 输入 %s" % os.path.basename(src))
    print("=" * 62)

    # ---- Stage 1 ----
    print("\n[1/3] 多格式解析")
    rc = universal_reader.main([
        "--input", src, "--out-dir", work, "--engine", a.engine,
        "--dpi", str(a.dpi), "--workers", str(a.workers),
    ])
    if rc:
        return rc
    md = os.path.join(work, stem + ".md")
    meta = os.path.join(work, stem + ".reader.json")

    # ---- Stage 2 ----
    print("\n[2/3] 卡片提取")
    cards = os.path.join(work, stem + "_cards.json")
    args2 = ["--md", md, "--meta", meta, "--out", cards,
             "--max-cards", str(a.max_cards),
             "--chapter-every", str(a.chapter_every),
             "--id-prefix", a.id_prefix]
    if a.subject:
        args2 += ["--subject", a.subject]
    if a.title:
        args2 += ["--title", a.title]
    rc = extract_cards.main(args2)
    if rc:
        return rc

    # ---- Stage 3 ----
    print("\n[3/3] 渲染注入")
    out_html = os.path.join(out_dir, name + "_学习台.html")
    rc = build_html.main([
        "--cards", cards, "--out", out_html,
        "--report", os.path.join(work, stem + "_build_report.json"),
    ])
    if rc:
        return rc

    data = json.load(open(cards, encoding="utf-8"))
    gate = json.load(open(os.path.splitext(cards)[0] + "_quality_gate.json", encoding="utf-8"))
    print("\n" + "=" * 62)
    print("完成 | 卡片 %d 张 | 章节 %d | needs_review %d | 门禁 %s" %
          (len(data["cards"]), len(data["chapters"]),
           gate["needs_review"], "通过" if gate["passed"] else "未通过"))
    print("最终 HTML : " + out_html)
    print("中间产物 : " + work)
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
