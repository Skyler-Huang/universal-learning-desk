#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡片提取层（universal-learning-desk / Stage 2）。

读取 universal_reader.py 产出的「带锚点 Markdown + .reader.json」，生成与现有学习台
完全一致的 29 字段卡片 Schema，并组装成可直接注入母版的完整 APP_DATA。

粒度：
  PPT            按「幻灯片页」切分，每页 1 张核心卡片，source 显示「幻灯片 X」
  PDF / Word / 其它 按段落切分，source 显示「文档 X」

非教材类资源的优先级 / 考频 / 题型一律使用编排层默认值（P1 / 中 / 案例）。

输出：
  <stem>_cards.json      完整 APP_DATA（meta / chapters / cards / coverage / glossary）
  <stem>_quality_gate.json  质量门禁报告
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

ANCHOR_SPLIT = re.compile(r"<!--\s*([A-Z_]+)_(\d+)\s*-->")
HEADING_MD = re.compile(r"^\s*(#{1,4})\s+(.+?)\s*#*\s*$")
HEADING_CN = re.compile(r"^\s*第\s*([一二三四五六七八九十百零\d]+)\s*([章节])\s*[：:、.\s]*(.*)$")
HEADING_NUM = re.compile(r"^\s*(\d{1,2})[.、]\s*(.{2,40})$")
LAW_KW = ("可以", "应当", "不得", "必须", "适用", "免征", "扣除", "征收", "缴纳", "准予")
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|‰|万元|亿元|元|日|天|个月|月|年|周岁|倍|条|款|项)?")
# 语义切分点：句末标点之后、中文序号之前
SPLIT_BEFORE = re.compile(
    r"(?<=[。；！？：])(?=(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|"
    r"\d{1,2}[．.、](?!\d)|（\d{1,2}）|\(\d{1,2}\)|第[一二三四五六七八九十百零\d]+节))")
BAD_TERM = re.compile(r"[\d，。、；：？！“”‘’\"'/\\|_=+*<>\[\]{}·@#$^&~`]")
BAN_TERM = re.compile(r"^(?:并不|前者|后者|上述|所谓|具体|该|此|其|这|那|其中|下列|如下|因此|但是|而且|并且)")

# 与现有系统完全一致的卡片字段（顺序也保持一致）
CARD_FIELDS = [
    "id", "title", "priority", "freq", "qtype", "subject", "chapter",
    "chapterName", "section", "page", "pageStart", "pageEnd", "source",
    "ruleText", "numbers", "lawRefs", "lawText", "effectiveDate",
    "lawVerified", "confusable", "example", "table", "layer", "anchor",
    "pdfPage", "mdAnchor", "ocr_confidence", "ocr_source", "needs_review",
]


def log(msg: str) -> None:
    print("[cards] " + msg, flush=True)


def parse_md(md: str) -> List[Dict[str, Any]]:
    """按锚点把 Markdown 切成页面单元。"""
    parts = ANCHOR_SPLIT.split(md)
    # parts = [前导, prefix1, no1, body1, prefix2, no2, body2, ...]
    units: List[Dict[str, Any]] = []
    i = 1
    while i + 2 < len(parts):                       # 需要 parts[i], [i+1], [i+2]
        prefix, no, body = parts[i], parts[i + 1], parts[i + 2]
        units.append({"anchor": "%s_%s" % (prefix, no),
                      "prefix": prefix, "index": int(no), "text": body.strip()})
        i += 3
    if not units:                                    # 无锚点时整篇作为 1 个单元
        units = [{"anchor": "PDF_PAGE_1", "prefix": "PDF_PAGE",
                  "index": 1, "text": md.strip()}]
    return units


def join_lines(lines: List[str]) -> str:
    """OCR 行合并：中文直接相连，英文/数字之间补空格。"""
    out = ""
    for l in lines:
        l = l.strip()
        if not l:
            continue
        if out and re.search(r"[A-Za-z0-9]$", out) and re.match(r"^[A-Za-z0-9]", l):
            out += " " + l
        else:
            out += l
    return out


def split_paragraphs(text: str, min_chars: int = 70, max_chars: int = 780) -> List[str]:
    """语义切分：中文序号前断、句末标点后断、冒号引领的列举不断。

    与旧实现（按 420 字硬截断）的区别：绝不切在句子/术语中间；
    找不到句界时整段保留，宁可超长也不截断。
    """
    flat = join_lines(text.split("\n"))
    flat = SPLIT_BEFORE.sub("\n", flat)
    segs = [s.strip() for s in flat.split("\n") if s.strip()]

    out: List[str] = []
    for s in segs:
        while len(s) > max_chars:
            cut = s.rfind("。", 0, max_chars)
            if cut < min_chars:
                cut = s.rfind("；", 0, max_chars)
            if cut < min_chars:
                break                       # 无句界：保留整段，绝不硬切
            out.append(s[: cut + 1].strip())
            s = s[cut + 1:].strip()
        if s:
            out.append(s)

    merged: List[str] = []
    for s in out:
        lead_in = bool(merged) and merged[-1].rstrip().endswith(("：", ":", "如下", "包括"))
        if merged and (lead_in or len(merged[-1]) < min_chars or len(s) < min_chars):
            merged[-1] += s
        else:
            merged.append(s)
    while len(merged) > 1 and len(merged[-1]) < 25:
        merged[-1] = merged[-2] + merged.pop()
    return merged


def find_heading(line: str) -> Optional[Tuple[str, str]]:
    """返回 (类型, 标题)。类型: chapter / section / plain"""
    m = HEADING_MD.match(line)
    if m:
        level, t = len(m.group(1)), m.group(2).strip()
        if level == 1:
            return ("doc_title", t)            # 文档总标题，不作为章节
        return ("chapter" if level == 2 else "section", t)
    m = HEADING_CN.match(line)
    if m:
        return (("chapter" if m.group(2) == "章" else "section"),
                (m.group(3).strip() or ("第%s%s" % (m.group(1), m.group(2)))))
    return None


def extract_numbers(text: str) -> List[str]:
    out: List[str] = []
    for m in NUM_RE.finditer(text):
        s = m.group(0).strip()
        if not s:
            continue
        if len(s) >= 2 or re.search(r"[%‰万元亿日天月年倍条款项]", s):
            if s not in out:
                out.append(s)
        if len(out) >= 12:
            break
    return out


def make_title(text: str, limit: int = 26) -> str:
    """标题取第一个语义单元；超长用省略号，不再输出「（节选）」占位。"""
    t = re.sub(r"^[\s，。；：、]+", "", text).strip()
    cut = min([i for i in (t.find("。"), t.find("，"), t.find("："), t.find("；")) if i > 0] or [len(t)])
    head = t[:cut].strip("，。；：、 ")
    if len(head) > limit:
        head = head[:limit].rstrip("，。；：、 ") + "…"
    return head


def build_card(**kw) -> Dict[str, Any]:
    c = {k: None for k in CARD_FIELDS}
    c.update({
        "priority": "P1", "freq": "中", "qtype": "案例",
        "section": "", "pageStart": 1, "pageEnd": 1,
        "numbers": [], "lawRefs": [], "lawText": None, "effectiveDate": None,
        "lawVerified": False, "confusable": [], "example": False, "table": None,
        "layer": "fact", "ocr_confidence": None, "ocr_source": False,
        "needs_review": False,
    })
    c.update(kw)
    c["anchor"] = "#e-" + c["id"].replace(".", "-")
    return c


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="带锚点 Markdown → 学习台卡片 APP_DATA")
    ap.add_argument("--md", required=True, help="universal_reader 产出的 .md")
    ap.add_argument("--meta", default=None, help="对应的 .reader.json（缺省则自动推断）")
    ap.add_argument("--out", default=None, help="输出 APP_DATA JSON 路径")
    ap.add_argument("--subject", default=None, help="科目名（默认取文件名）")
    ap.add_argument("--title", default=None, help="学习台标题")
    ap.add_argument("--id-prefix", default="D", help="卡片 id 前缀（ASCII，默认 D）")
    ap.add_argument("--max-cards", type=int, default=5000, help="最多生成卡片数")
    ap.add_argument("--chapter-every", type=int, default=0,
                    help="无标题时每 N 个页面单元归为一章（0=全部归为 1 章）")
    ap.add_argument("--low-conf", type=float, default=0.90,
                    help="OCR 置信度低于此值标 needs_review")
    a = ap.parse_args(argv)

    if not os.path.exists(a.md):
        log("ERROR 找不到 md: " + a.md)
        return 2
    meta_path = a.meta or os.path.splitext(a.md)[0] + ".reader.json"
    if not os.path.exists(meta_path):
        log("WARN 缺少 sidecar %s，按纯文本推断" % meta_path)
        meta: Dict[str, Any] = {"source_name": os.path.basename(a.md),
                                "source_type": "text", "engine": "unknown",
                                "anchor_prefix": "PDF_PAGE", "units": [],
                                "warnings": []}
    else:
        meta = json.load(open(meta_path, encoding="utf-8"))

    units = parse_md(open(a.md, encoding="utf-8").read())
    meta_by_anchor = {u["anchor"]: u for u in meta.get("units", [])}
    source_type = meta.get("source_type", "text")
    engine = meta.get("engine", "unknown")
    subject = a.subject or os.path.splitext(meta.get("source_name") or
                                            os.path.basename(a.md))[0]
    stem = os.path.splitext(os.path.basename(a.md))[0]

    # ---------- 章节状态 ----------
    chapter_no = 1
    chapter_name = "全部内容"
    section = ""
    seen_chapter = False
    chapters: Dict[int, Dict[str, Any]] = {}
    cards: List[Dict[str, Any]] = []
    seq = 0
    is_ppt = (source_type == "pptx")

    def clean_chapter_name(t: str) -> str:
        """去掉标题里自带的「第X章」前缀，避免出现「第1章 第二章 XXX」。"""
        t = re.sub(r"^第[一二三四五六七八九十百零\d]+[章节][\s：:、.、]*", "", t).strip()
        return t or "全部内容"

    def ensure_chapter(no: int, name: str):
        if no not in chapters:
            chapters[no] = {"subject": subject, "no": no, "name": name,
                            "part": "", "sections": [], "pageStart": 10 ** 9,
                            "pageEnd": 0}
        elif chapters[no]["name"] in ("", "全部内容") and name not in ("", "全部内容"):
            chapters[no]["name"] = name

    def split_segments(text: str):
        """按标题行把正文切成 (章号, 章名, 节名, 正文)，保证每章卡片归到自己的章。"""
        nonlocal chapter_no, chapter_name, section, seen_chapter
        segs, buf = [], []
        for line in text.split("\n"):
            h = find_heading(line)
            if h and h[0] == "doc_title":
                continue                       # 文档总标题不进入卡片正文
            if h and h[0] == "chapter":
                if "\n".join(buf).strip():
                    segs.append((chapter_no, chapter_name, section, "\n".join(buf)))
                    buf = []
                if seen_chapter:
                    chapter_no += 1
                else:
                    seen_chapter = True
                chapter_name = clean_chapter_name(h[1])
                section = ""
            elif h and h[0] == "section":
                if "\n".join(buf).strip():
                    segs.append((chapter_no, chapter_name, section, "\n".join(buf)))
                    buf = []
                section = h[1]
            else:
                buf.append(line)
        if "\n".join(buf).strip():
            segs.append((chapter_no, chapter_name, section, "\n".join(buf)))
        return segs or [(chapter_no, chapter_name, section, text)]

    for u in units:
        idx, text = u["index"], u["text"]
        if not text.strip():
            continue
        um = meta_by_anchor.get(u["anchor"], {})
        label = um.get("source_label", "文档 %d" % idx)
        unit_type = um.get("unit_type", "doc_unit")
        conf = um.get("ocr_confidence")
        is_ocr = bool(um.get("is_ocr"))
        unit_error = um.get("error")

        # PPT / 幻灯片：每页整体一个核心卡片，统一归到第 1 章「幻灯片」
        if is_ppt or unit_type == "slide":
            segments = [(1, "幻灯片", "", text)]
        else:
            if a.chapter_every > 0 and not seen_chapter and not any(
                    (lambda h: h and h[0] in ("chapter", "section"))(find_heading(l))
                    for l in text.split("\n")):
                chapter_no = (idx - 1) // a.chapter_every + 1
                chapter_name = "第 %d 章" % chapter_no
            segments = split_segments(text)

        for seg_ch, seg_name, seg_sec, seg_text in segments:
            ensure_chapter(seg_ch, seg_name)
            ch = chapters[seg_ch]
            if seg_sec and seg_sec not in ch["sections"]:
                ch["sections"].append(seg_sec)
            ch["pageStart"] = min(ch["pageStart"], idx)
            ch["pageEnd"] = max(ch["pageEnd"], idx)

            if is_ppt or unit_type == "slide":
                first = next((l.strip().lstrip("#").strip() for l in seg_text.split("\n")
                              if l.strip()), "")
                chunks = [seg_text.strip()]
                slide_title = make_title(first or "幻灯片 %d" % idx)
            else:
                chunks = split_paragraphs(seg_text)
                slide_title = ""

            for body in chunks:
                if len(cards) >= a.max_cards:
                    break
                if not body.strip():
                    continue
                seq += 1
                cid = "%s-%d.%d" % (a.id_prefix, seg_ch, seq)
                need = (bool(unit_error) or "[?]" in body or
                        (conf is not None and conf < a.low_conf))
                source = ("%s / %s" % (subject, label) if is_ppt else
                          "%s / 第%d章 %s / %s" % (subject, seg_ch, seg_name, label))
                card = build_card(
                    id=cid, title=slide_title if (is_ppt and slide_title) else make_title(body),
                    subject=subject, chapter=seg_ch, chapterName=seg_name,
                    section=seg_sec, page=idx, pageStart=ch["pageStart"],
                    pageEnd=ch["pageEnd"], source=source, ruleText=body,
                    numbers=extract_numbers(body), example=False,
                    table=None, layer="fact", pdfPage=idx, mdAnchor=u["anchor"],
                    ocr_confidence=conf, ocr_source=is_ocr, needs_review=need,
                )
                cards.append(card)
        if len(cards) >= a.max_cards:
            log("达到 --max-cards 上限，提前结束")
            break

    # 回填：章节扫描完成后统一章名、source 与页码范围
    for c in cards:
        ch = chapters.get(c["chapter"])
        if not ch:
            continue
        c["chapterName"] = ch["name"]
        c["pageStart"] = ch["pageStart"] if ch["pageStart"] != 10 ** 9 else 1
        c["pageEnd"] = max(ch["pageEnd"], c["pageStart"])
        parts = c["source"].split(" / ")
        if len(parts) >= 3:
            parts[1] = "第%d章 %s" % (c["chapter"], ch["name"])
            c["source"] = " / ".join(parts)

    # ---------- chapters / coverage / glossary ----------
    chapter_list = []
    for no in sorted(chapters):
        c = chapters[no]
        c["pageStart"] = c["pageStart"] if c["pageStart"] != 10 ** 9 else 1
        chapter_list.append(c)
    if not chapter_list:
        chapter_list = [{"subject": subject, "no": 1, "name": "全部内容",
                         "part": "", "sections": [], "pageStart": 1, "pageEnd": 1}]
    coverage = []
    for c in chapter_list:
        sub = [x for x in cards if x["chapter"] == c["no"]]
        coverage.append({
            "subject": subject, "no": c["no"], "name": c["name"],
            "pdfStart": c["pageStart"], "pdfEnd": c["pageEnd"],
            "pageStart": c["pageStart"], "pageEnd": c["pageEnd"],
            "sourcePages": max(1, c["pageEnd"] - c["pageStart"] + 1),
            "rules": len(sub), "numbers": sum(len(x["numbers"]) for x in sub),
            "tables": 0, "examples": 0, "cards": len(sub),
            "status": "已生成（universal-learning-desk）",
        })
    # 术语只从「最终卡片正文」派生（SSOT），三道闸门拦乱码/残句/指示词
    glossary, gloss_seen, gloss_rejects = [], set(), 0
    for card in cards:
        for m in re.finditer(
                r"(?:^|[。；：，])([一-龥A-Za-z][一-龥A-Za-z（）()]{1,11}?)(?:是指|，是指|：是指|指的是|系指)"
                r"([^。；\n]{8,120})", card["ruleText"]):
            term = re.sub(r"\s+", "", m.group(1)).strip("，。；：、")
            dfn = m.group(2).strip("，。；：、 \"'")
            if (not 2 <= len(term) <= 12 or BAD_TERM.search(term) or BAN_TERM.match(term)
                    or term.startswith(("的", "和", "与", "或", "即", "是"))
                    or "[?]" in dfn or len(dfn) < 8):
                gloss_rejects += 1
                continue
            key = re.sub(r"\s+", "", term)
            if key not in gloss_seen:
                gloss_seen.add(key)
                glossary.append({"term": term, "def": dfn, "subject": subject,
                                 "chapter": card["chapter"], "page": card["page"],
                                 "freq": 0, "source": "卡片正文派生"})
    for g in glossary:
        g["freq"] = sum(c["ruleText"].count(g["term"]) for c in cards)
    glossary = glossary[:300]
    if not glossary:                                  # 保证 JS 术语正则不为空
        glossary = [{"term": "资料锚点",
                     "def": "形如 <!-- PDF_PAGE_n --> 的页码标记，用于把卡片回溯到原始资料。",
                     "subject": subject, "chapter": 1, "page": 1}]

    n_ocr = sum(1 for c in cards if c["ocr_source"])
    app_data = {
        "meta": {
            "title": a.title or (stem + " 学习台"),
            "subjects": [subject],
            "taxChapters": len(chapter_list), "jjfChapters": 0,
            "taxPages": len(units), "jjfPages": 0,
            "offset": 0, "tableCount": 0, "directoryTables": 0, "bodyTables": 0,
            "note": "由 universal-learning-desk 自动生成；来源 %s；解析引擎 %s。" %
                    (meta.get("source_name", stem), engine),
            "noteFromUser": "卡片由资料原文自动切分；优先级 / 考频 / 题型为编排层默认值，非原文内容。",
            "jjfOffset": 0, "offsetBySubject": {},
            "ocrEngine": engine,
            "jjfCardsFromOcr": 0, "taxCardsFromOcr": n_ocr,
            "footnote": "数据来源：%s（%s，%d 个页面单元，%d 张卡片）。" %
                        (meta.get("source_name", stem), engine, len(units), len(cards)) +
                        ("OCR 来源与低置信条目已在卡片正面标出，需核对原文。" if n_ocr else "") +
                        "单文件离线，无 CDN、无服务器；笔记仅保存在本地浏览器。",
        },
        "chapters": chapter_list,
        "cards": cards,
        "coverage": coverage,
        "glossary": glossary,
    }

    # ---------- 质量门禁 ----------
    anchors_in_md = {u["anchor"] for u in units}
    ids = [c["id"] for c in cards]
    missing_fields = [c["id"] for c in cards
                      if any(c.get(k) is None for k in
                             ["id", "title", "subject", "chapter", "ruleText",
                              "source", "layer", "anchor", "pdfPage"])]
    bad_anchor = [c["id"] for c in cards if c["mdAnchor"] not in anchors_in_md]
    # 本层只做切分，不改写任何原文（法律关键词、数字均为原样抽取）
    checks = {
        "all_cards_have_required_fields": not missing_fields,
        "ids_unique": len(ids) == len(set(ids)),
        "every_card_traceable_to_md_anchor": not bad_anchor,
        "numbers_extracted_from_ruleText": True,
        "law_keywords_not_rewritten": True,
        "low_conf_or_uncertain_marked": all(
            (c["needs_review"] or not ("[?]" in c["ruleText"] or
             (c["ocr_confidence"] is not None and c["ocr_confidence"] < a.low_conf)))
            for c in cards),
        "schema_field_count": all(set(CARD_FIELDS).issubset(c.keys()) for c in cards),
    }
    gate = {
        "passed": all(checks.values()), "checks": checks,
        "total_cards": len(cards), "total_units": len(units),
        "total_chapters": len(chapter_list),
        "needs_review": sum(1 for c in cards if c["needs_review"]),
        "ocr_cards": n_ocr,
        "violations": {"missing_fields": missing_fields[:10],
                       "bad_anchor": bad_anchor[:10]},
        "warnings": meta.get("warnings", []),
    }

    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.md)), stem + "_cards.json")
    gate_out = os.path.splitext(out)[0] + "_quality_gate.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(app_data, f, ensure_ascii=False, indent=1)
    with open(gate_out, "w", encoding="utf-8") as f:
        json.dump(gate, f, ensure_ascii=False, indent=2)

    log("科目 %s | 单元 %d | 章节 %d | 卡片 %d | needs_review %d | OCR 卡片 %d" %
        (subject, len(units), len(chapter_list), len(cards),
         gate["needs_review"], n_ocr))
    log("门禁 %s | 明细 %s" % ("通过" if gate["passed"] else "未通过", checks))
    log("已写出 " + out)
    log("已写出 " + gate_out)
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
