#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成冒烟测试用的假资料（覆盖 PDF / 图片 / Word / PPT / HTML / MD / TXT）。

    python examples/make_fixtures.py --out-dir ./fixtures
"""
from __future__ import annotations

import argparse
import glob
import os

TXT = """第一章 基本概念

本资料所称知识卡片，是指把资料原文按段落切分后的最小复习单元。每张卡片都必须能够回溯到原始资料的分页锚点，不得凭空补写或推断原文没有的内容。

增值税一般纳税人适用 13% 税率的货物，应当在规定期限内申报纳税，不得擅自扩大适用范围。500 万元以下的固定资产可以一次性扣除。

第二章 核心规则

纳税人应当按照法律、行政法规的规定缴纳税款。符合免征条件的，可以依法申请减免，但必须提交完整材料。

资料锚点，是指形如 PDF_PAGE_n 的页码标记，用于把卡片回溯到原始资料。低置信条目需核对原文。
"""

MD = """# 企业所得税讲义

## 第一章 纳税义务人

居民企业应当就其来源于中国境内、境外的所得缴纳企业所得税，适用税率为 25%。

非居民企业在中国境内设立机构、场所的，应当就其所设机构、场所取得的来源于中国境内的所得缴纳企业所得税。

## 第二章 应纳税所得额

企业每一纳税年度的收入总额，减除不征税收入、免税收入、各项扣除以及允许弥补的以前年度亏损后的余额，为应纳税所得额。

符合条件的固定资产，单位价值不超过 500 万元的，可以一次性计入当期成本费用，不得分年度计算折旧。
"""

HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>合同法复习提纲</title></head><body>
<h1>合同法复习提纲</h1>
<h2>第一章 合同的订立</h2>
<p>当事人订立合同，应当具有相应的民事权利能力和民事行为能力。要约到达受要约人时生效，承诺应当在要约确定的期限内到达要约人。</p>
<p>采用格式条款订立合同的，提供格式条款的一方应当遵循公平原则确定当事人之间的权利和义务，不得免除其责任、加重对方责任。</p>
<h2>第二章 合同的效力</h2>
<p>依法成立的合同，自成立时生效。法律、行政法规规定应当办理批准、登记等手续生效的，依照其规定。</p>
</body></html>
"""

PPT_SLIDES = [
    ("增值税基础", ["增值税是以商品在流转过程中产生的增值额为计税依据征收的流转税。",
                "一般纳税人销售货物适用 13% 税率，小规模纳税人适用 3% 征收率。",
                "纳税人应当在规定期限内办理纳税申报，不得逾期。"]),
    ("申报与期限", ["增值税的纳税期限分别为 1 日、3 日、5 日、10 日、15 日、1 个月或者 1 个季度。",
                "以 1 个月为纳税期的，自期满之日起 15 日内申报纳税。",
                "逾期申报的，税务机关可以依法加收滞纳金。"]),
    ("减免与优惠", ["符合免征条件的项目，可以依法申请免征增值税，但必须提交完整证明材料。",
                "销售额未超过 10 万元的小规模纳税人，免征增值税。",
                "任何单位和个人不得擅自扩大减免税适用范围。"]),
]

DOCX_PARAS = [
    ("h1", "票据法要点"),
    ("h2", "第一章 票据基础"),
    ("p", "票据是指汇票、本票和支票。票据的签发、取得和转让，应当遵循诚实信用的原则，具有真实的交易关系和债权债务关系。"),
    ("p", "票据金额、日期、收款人名称不得更改，更改的票据无效。持票人应当在规定期限内提示付款，逾期不得主张票据权利。"),
    ("h2", "第二章 票据权利"),
    ("p", "持票人对票据的出票人和承兑人的权利，自票据到期日起 2 年内不行使而消灭。"),
]

IMG_LINES = ["增值税税率说明", "一般纳税人适用 13% 税率", "小规模纳税人适用 3% 征收率",
             "纳税期限为 15 日", "符合免征条件可以申请减免"]


def cjk_font() -> str:
    cand = glob.glob("/usr/share/fonts/opentype/noto/NotoSerifCJK-*.ttc") + \
           glob.glob("/usr/share/fonts/truetype/**/*CJK*.*tf", recursive=True) + \
           glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
    return cand[0] if cand else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="./fixtures")
    a = ap.parse_args()
    d = os.path.abspath(a.out_dir)
    os.makedirs(d, exist_ok=True)

    open(os.path.join(d, "demo.txt"), "w", encoding="utf-8").write(TXT)
    open(os.path.join(d, "demo.md"), "w", encoding="utf-8").write(MD)
    open(os.path.join(d, "demo.html"), "w", encoding="utf-8").write(HTML)

    # ---- PPTX ----
    from pptx import Presentation
    from pptx.util import Inches, Pt
    prs = Presentation()
    for title, lines in PPT_SLIDES:
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text = title
        s.placeholders[1].text = "\n".join(lines)
    prs.save(os.path.join(d, "demo.pptx"))

    # ---- DOCX ----
    from docx import Document
    doc = Document()
    for style, text in DOCX_PARAS:
        if style == "h1":
            doc.add_heading(text, 1)
        elif style == "h2":
            doc.add_heading(text, 2)
        else:
            doc.add_paragraph(text)
    doc.save(os.path.join(d, "demo.docx"))

    # ---- 图片（中文 PNG） ----
    from PIL import Image, ImageDraw, ImageFont
    font_path = cjk_font()
    font = ImageFont.truetype(font_path, 30) if font_path else ImageFont.load_default()
    im = Image.new("RGB", (1000, 420), "white")
    dr = ImageDraw.Draw(im)
    for i, line in enumerate(IMG_LINES):
        dr.text((40, 40 + i * 70), line, fill="black", font=font)
    im.save(os.path.join(d, "demo.png"))
    im.save(os.path.join(d, "demo_scan.pdf"), "PDF", resolution=150.0)

    # ---- 带文字层的 PDF（中文，用 PyMuPDF 内置 china-s，不嵌入字体文件） ----
    import pymupdf as fitz
    pdf = fitz.open()
    page = pdf.new_page()
    y = 60
    for line in ["第一章 消费税概述",
                 "消费税是对特定消费品征收的间接税，纳税人应当按照规定期限申报缴纳。",
                 "适用税率包括 13% 与 20% 两档，不得擅自调整。",
                 "纳税人应当在规定期限内办理纳税申报，不得逾期申报。"]:
        page.insert_text((50, y), line, fontname="china-s", fontsize=13,
                         color=(0, 0, 0))
        y += 34
    pdf.save(os.path.join(d, "demo_text.pdf"), deflate=True)
    pdf.close()

    print("样例已生成于", d)
    for f in sorted(os.listdir(d)):
        print("  ", f, os.path.getsize(os.path.join(d, f)))


if __name__ == "__main__":
    main()
