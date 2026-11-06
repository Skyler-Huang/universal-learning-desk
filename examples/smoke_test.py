#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地冒烟测试：对全部支持格式跑通 reader → cards → build_html，并验证 HTML 渲染。

    python examples/smoke_test.py --fixtures ./fixtures --out-dir ./smoke_out

浏览器验证为可选项：检测到 chromium / google-chrome 才执行，缺失则跳过（不算失败）。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import run_pipeline                                  # noqa: E402

FORMATS = ["demo.txt", "demo.md", "demo.html", "demo.docx", "demo.pptx",
           "demo.png", "demo_text.pdf", "demo_scan.pdf"]


def browser() -> str:
    for b in ("chromium", "chromium-browser", "google-chrome"):
        if shutil.which(b):
            return b
    return ""


def verify_html(bin_: str, path: str, expect_cards: int) -> dict:
    r = subprocess.run(
        [bin_, "--headless", "--no-sandbox", "--disable-gpu",
         "--disable-dev-shm-usage", "--virtual-time-budget=7000",
         "--dump-dom", "file://" + path],
        capture_output=True, text=True, timeout=180)
    dom = r.stdout
    m = re.search(r"当前\s*(\d+)\s*/\s*(\d+)\s*张卡片", dom)
    shown = int(m.group(1)) if m else -1
    fatal = [l for l in r.stderr.splitlines()
             if re.search(r"Uncaught|SyntaxError|TypeError|ReferenceError", l, re.I)]
    return {
        "browser": os.path.basename(bin_),
        "cards_rendered": shown,
        "cards_expected": expect_cards,
        "render_ok": shown == expect_cards and expect_cards > 0,
        "js_fatal_errors": fatal[:5],
        "has_7_modules": all(k in dom for k in
                             ["章节卡片", "核心框架", "内容导学", "行动规则",
                              "术语大全", "学习自检", "本地笔记"]),
        "has_ocr_tip_css": "ocr-local-tip" in dom,
        "has_gesture": "touchstart" in dom,
        "has_theme": "themeBtn" in dom,
        "external_cdn": bool(re.search(r'<script[^>]+src="https?://|<link[^>]+href="https?://', dom)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", default=os.path.join(HERE, "fixtures"))
    ap.add_argument("--out-dir", default=os.path.join(HERE, "smoke_out"))
    ap.add_argument("--skip-ocr", action="store_true")
    a = ap.parse_args()
    fx, out = os.path.abspath(a.fixtures), os.path.abspath(a.out_dir)
    os.makedirs(out, exist_ok=True)
    bin_ = browser()

    results = []
    for name in FORMATS:
        src = os.path.join(fx, name)
        if not os.path.exists(src):
            results.append({"file": name, "status": "SKIP(样例缺失)"})
            continue
        if a.skip_ocr and name in {"demo.png", "demo_scan.pdf"}:
            results.append({"file": name, "status": "SKIP(--skip-ocr)"})
            continue
        stem = os.path.splitext(name)[0]      # reader 内部产物名（可能与其它格式同名）
        tag = name.replace(".", "_")          # 唯一输出目录，避免 demo.* 互相覆盖
        dest = os.path.join(out, tag)
        print("\n" + "=" * 58)
        print("SMOKE:", name)
        print("=" * 58)
        try:
            rc = run_pipeline.main([
                "--input", src, "--out-dir", dest, "--name", tag,
                "--subject", "冒烟测试资料", "--workers", "1",
                "--title", stem + " 学习台",
            ])
        except Exception as ex:
            results.append({"file": name, "status": "EXCEPTION",
                            "error": "%s: %s" % (type(ex).__name__, ex)})
            continue
        if rc:
            results.append({"file": name, "status": "FAIL(pipeline rc=%d)" % rc})
            continue

        work = os.path.join(dest, "_work")
        md = os.path.join(work, stem + ".md")
        meta = json.load(open(os.path.join(work, stem + ".reader.json"), encoding="utf-8"))
        cards = json.load(open(os.path.join(work, stem + "_cards.json"), encoding="utf-8"))
        gate_f = glob.glob(os.path.join(work, "*quality_gate.json"))[0]
        gate = json.load(open(gate_f, encoding="utf-8"))
        build_f = glob.glob(os.path.join(work, "*build_report.json"))[0]
        build = json.load(open(build_f, encoding="utf-8"))
        html_path = os.path.join(dest, tag + "_学习台.html")

        anchors = sorted(set(re.findall(r"<!--\s*([A-Z_]+)_\d+\s*-->",
                                        open(md, encoding="utf-8").read())))
        sources = [c["source"] for c in cards["cards"]]
        item = {
            "file": name,
            "status": "OK",
            "source_type": meta["source_type"],
            "engine": meta["engine"],
            "anchor_types": anchors,
            "units": meta["total_units"],
            "cards": len(cards["cards"]),
            "chapters": len(cards["chapters"]),
            "needs_review": gate["needs_review"],
            "gate_passed": gate["passed"],
            "build_passed": build["passed"],
            "css_unchanged": build["css_unchanged"],
            "single_file_offline": build["single_file_offline"],
            "source_sample": sources[0] if sources else "",
            "html": html_path,
        }
        if meta["source_type"] == "pptx":
            item["ppt_one_card_per_slide"] = (len(cards["cards"]) == meta["total_units"])
            item["ppt_source_has_幻灯片"] = all("幻灯片" in s for s in sources)
        else:
            item["source_has_文档"] = all("文档" in s for s in sources) if sources else True
        if bin_:
            item["browser"] = verify_html(bin_, html_path, len(cards["cards"]))
        results.append(item)

    report = {"results": results,
              "browser_available": bool(bin_),
              "total": len(results)}
    rp = os.path.join(out, "smoke_test_report.json")
    json.dump(report, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("\n" + "=" * 78)
    print("冒烟测试汇总")
    print("=" * 78)
    print("%-16s %-8s %-6s %-6s %-9s %-9s %s" %
          ("文件", "状态", "单元", "卡片", "门禁", "构建", "浏览器"))
    for r in results:
        b = r.get("browser", {})
        print("%-16s %-8s %-6s %-6s %-9s %-9s %s" %
              (r["file"], r["status"], r.get("units", "-"), r.get("cards", "-"),
               r.get("gate_passed", "-"), r.get("build_passed", "-"),
               ("OK" if b.get("render_ok") else "-") if b else "跳过"))
    print("\n报告: " + rp)
    ok = [r for r in results if r["status"] == "OK"]
    all_ok = (len(ok) == len(results) and
              all(r["gate_passed"] and r["build_passed"] and r["css_unchanged"]
                  and r["single_file_offline"] for r in ok) and
              all(r.get("browser", {}).get("render_ok", True) for r in ok))
    print(">>> " + ("全部通过" if all_ok else "存在失败"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
