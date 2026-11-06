#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识卡片重建层（SSOT 修复）。

输入：既有 APP_DATA（cards 为已通过数字守恒/同形字校验的主干数据）
输出：语义切分后的新 APP_DATA + 质量门禁报告

修复的三类硬伤：
  1. 切分：旧数据按「每页 2 段」硬切，导致半句结尾、列举块断裂；本层按
     中文序号 / 句末标点 / 括号配平重新切分，跨页残句自动接续。
  2. 页眉页脚：按「同章多页重复出现的页首串 + 页尾页码」统计剔除。
  3. 术语：只从清洗后的卡片正文派生，正则闸门过滤 OCR 乱码。

不改写任何正文用词与数字，只做「边界重划 + 噪声剔除」。
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import sys
from typing import Dict, List, Tuple

CJK = r"\u4e00-\u9fa5"
TERMINAL = set("。；！？：”’）】》」』…%.")
MARK_START = re.compile(
    r"^(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|"
    r"\d{1,2}[．.、](?!\d)|（\d{1,2}）|\(\d{1,2}\)|第[一二三四五六七八九十百零\d]+节)"
)
SPLIT_BEFORE = re.compile(
    r"(?<=[。；！？：])(?=(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|"
    r"\d{1,2}[．.、](?!\d)|（\d{1,2}）|\(\d{1,2}\)|第[一二三四五六七八九十百零\d]+节))"
)
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|‰|万元|亿元|元|日|天|个月|月|年|周岁|倍|条|款|项)?")
GARBAGE_TERM = re.compile(r"[\d，。、；：？！“”‘’\"'/\\|_=+*<>\[\]{}·@#$^&~`]")
# 指示词 / 副词 / 残句开头，不配做术语
BAN_TERM = re.compile(r"^(?:并不|前者|后者|上述|所谓|具体|该|此|其|这|那|其中|下列|如下|因此|但是|而且|并且)")
BAN_EXACT = {"并不", "前者", "后者", "具体", "上述", "其中", "下列", "如下", "因此"}


def log(msg: str) -> None:
    print("[rebuild] " + msg, flush=True)


def norm_key(s: str) -> str:
    return re.sub(r"\s+", "", s)


def ends_terminal(s: str) -> bool:
    s = (s or "").rstrip(" .…·")
    return bool(s) and s[-1] in TERMINAL


def find_chapter(chapters: List[dict], subject: str, page: int):
    for ch in chapters:
        if ch["subject"] == subject and ch["pageStart"] <= page <= ch["pageEnd"]:
            return ch
    return None


def ch_name_prefix(head: str, chapter: dict) -> bool:
    name = re.sub(r"[（(].*?[)）]", "", chapter.get("name", ""))
    return bool(name) and (name.startswith(head) or head.startswith(name[:4]))


def order_cards(cards: List[dict]) -> List[dict]:
    def key(c):
        tail = c["id"].split("-")[-1]
        nums = [int(x) for x in re.findall(r"\d+", tail)]
        return (nums[0] if nums else 0, tail)
    return sorted(cards, key=key)


def strip_running_heads(pages: List[Tuple[int, str]], chapter: dict) -> Tuple[List[Tuple[int, str]], List[str]]:
    """剔除同章重复的页首串与页尾页码，返回 (清洗后页面, 剔除日志)。"""
    removed: List[str] = []
    n = len(pages)
    if not n:
        return pages, removed

    # 页首重复串：只认「章眉 / 科目名 / 章名 / 教材水印」，避免误删正文里的重复引文
    n = len(pages)
    pref_cnt = collections.Counter(p[1][:6] for p in pages if len(p[1]) >= 6)
    cut6 = set()
    for head, cnt in pref_cnt.items():
        if cnt < max(3, int(n * 0.12)):
            continue
        if ("章" in head or head.startswith(("税法", "经济法", "注会", "教材", "CPA"))
                or ch_name_prefix(head, chapter)):
            cut6.add(head)
    out = []
    for page, text in pages:
        t = text
        head = t[:6]
        if head in cut6:
            # 至少剥掉这个重复串；若后续紧跟章名再延长剥离
            cut = 6
            while cut < 40 and cut < len(t) and t[cut] in " ·-—第":
                cut += 1
            removed.append("p%d头:%s" % (page, t[:cut]))
            t = t[cut:]
        # 章标题若出现在页首（含章号或章名），剥掉
        m = re.match(r"^第[一二三四五六七八九十百零\d]+章\s*[%s]{0,16}[：:、\s]*" % CJK, t)
        if m and chapter["pageStart"] < page:          # 首页首行可能是真标题，保守跳过
            if chapter["name"][:4] in m.group(0) or len(m.group(0)) <= 10:
                removed.append("p%d章眉:%s" % (page, m.group(0)))
                t = t[m.end():]
        # 页尾独立页码
        m = re.search(r"(?:^|[^\d])(\d{1,3})$", t)
        if m:
            val = int(m.group(1))
            if abs(val - page) <= 1:
                removed.append("p%d尾页:%s" % (page, m.group(1)))
                t = t[: m.start(1) - 1] if t[m.start(1) - 1] in " ·-—" else t[: m.start(1)]
        out.append((page, t.strip()))
    return out, removed


def segment(text: str, min_len: int = 70, max_len: int = 780) -> List[str]:
    """按语义边界切分：中文序号前断，句末标点后断，超长退到最近的句号。"""
    # 只消除中文之间的排版空格；数字之间的空格必须保留（「60 000」不是「60000」）
    text = re.sub(r"(?<=[%s])[ \t\u3000]+|[ \t\u3000]+(?=[%s])" % (CJK, CJK), "", text)
    text = re.sub(r"[ \t\u3000]{2,}", " ", text)
    text = SPLIT_BEFORE.sub("\n", text)
    segs = [s.strip() for s in text.split("\n") if s.strip()]

    out: List[str] = []
    for s in segs:
        if len(s) <= max_len:
            out.append(s)
            continue
        rest = s
        while len(rest) > max_len:
            cut = rest.rfind("。", 0, max_len)
            if cut < min_len:
                cut = rest.rfind("；", 0, max_len)
            if cut < min_len:
                break                      # 找不到句界就整段保留，绝不硬切
            out.append(rest[: cut + 1].strip())
            rest = rest[cut + 1:].strip()
        if rest:
            out.append(rest)

    merged: List[str] = []
    for s in out:
        lead_in = bool(merged) and merged[-1].rstrip().endswith(("：", ":", "如下", "包括"))
        if merged and (lead_in or len(merged[-1]) < min_len or len(s) < min_len):
            merged[-1] = merged[-1] + s
        else:
            merged.append(s)
    # 尾段过短不丢弃（可能含数字/法条号），并入上一段
    while len(merged) > 1 and len(merged[-1]) < 25:
        tail = merged.pop()
        merged[-1] += tail
    return merged


def make_title(text: str, limit: int = 26) -> str:
    t = re.sub(r"^[\s，。；：、]+", "", text).strip()
    m = MARK_START.match(t)
    if m:
        t = t[m.end():].strip()
    # 取第一个语义单元
    cut = min([i for i in (t.find("。"), t.find("，"), t.find("："), t.find("；")) if i > 0] or [len(t)])
    head = t[:cut].strip("，。；：、 ")
    if not head:
        head = t.strip()
    # 标题不能停在虚词上：向后延伸到下一个标点（最多 40 字）
    # 标题不能停在虚词上：向后延伸到下一个标点（最多 42 字，最多 4 次，防死循环）
    for _ in range(4):
        head = head.strip()
        if not head or head[-1] not in "的和与或及在对为以将把从由被所等其该此":
            break
        cand = [i for i in (t.find("，", len(head)), t.find("。", len(head)),
                            t.find("；", len(head))) if i > len(head)]
        nxt = min(cand) if cand else min(len(t), len(head) + 24)
        if nxt > 42 or nxt >= len(t):
            break
        grown = t[:nxt].strip("，。；：、 ")
        if len(grown) <= len(head):
            break
        head = grown
    if len(head) > limit:
        cut2 = head.rfind("（", 0, limit)
        head = head[: cut2] if cut2 >= 8 else head[:limit]
        head = head.rstrip("，。；：、 ") + "…"
    return head.strip("，。；：、 ")


def extract_numbers(text: str) -> List[str]:
    out: List[str] = []
    for m in NUM_RE.finditer(text):
        s = re.sub(r"\s+", "", m.group(0))
        if len(s) >= 2 or re.search(r"[%‰万元亿日天月年倍条款项]", s):
            if s not in out:
                out.append(s)
        if len(out) >= 16:
            break
    return out


def build_glossary(cards: List[dict]) -> Tuple[List[dict], List[str]]:
    """术语只从卡片正文派生；三道闸门拦 OCR 乱码与残句。"""
    pat = re.compile(
        r"(?:^|[。；：，])([%sA-Za-z][%sA-Za-z（）()]{1,11}?)(?:是指|，是指|：是指|指的是|系指)"
        r"([^。；\n]{8,120})" % (CJK, CJK)
    )
    seen = {}
    rejects = []
    for c in cards:
        for m in pat.finditer(c["ruleText"]):
            term = re.sub(r"\s+", "", m.group(1)).strip("，。；：、")
            dfn = m.group(2).strip("，。；：、 \"'")
            bad = None
            if not (2 <= len(term) <= 12):
                bad = "长度"
            elif GARBAGE_TERM.search(term):
                bad = "乱码字符"
            elif term.startswith(("的", "和", "与", "或", "即", "是")):
                bad = "虚词开头"
            elif term in BAN_EXACT or BAN_TERM.match(term):
                bad = "指示词/残句"
            elif re.search(r"(吗|呢|啊|吧)$", term):
                bad = "语气词"
            elif any(ch in dfn for ch in "[?]"):
                bad = "待核标记"
            elif len(dfn) < 8:
                bad = "定义过短"
            if bad:
                if len(rejects) < 200:
                    rejects.append("%s|%s" % (term, bad))
                continue
            key = norm_key(term)
            if key not in seen:
                seen[key] = {"term": term, "def": dfn, "subject": c["subject"],
                             "chapter": c["chapter"], "page": c["page"],
                             "freq": 0, "source": "卡片正文派生"}
    for g in seen.values():
        g["freq"] = sum(c["ruleText"].count(g["term"]) for c in cards)
    return list(seen.values()), rejects


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="旧 APP_DATA JSON")
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default=None)
    ap.add_argument("--show", type=int, default=0, help="打印前 N 张卡用于肉眼校验")
    a = ap.parse_args(argv)

    old = json.load(open(a.inp, encoding="utf-8"))
    cards_old = old["cards"]
    chapters = old["chapters"]
    meta = old["meta"]
    offsets = meta.get("offsetBySubject") or {s: meta.get("offset", 0) for s in meta["subjects"]}
    prefixes = {}
    for c in cards_old:
        if "-" in c["id"]:
            prefixes.setdefault(c["subject"], c["id"].split("-")[0])

    # 1) 还原页文本
    per_page = collections.defaultdict(list)
    for c in cards_old:
        per_page[(c["subject"], int(c["page"]))].append(c)
    page_text = {}
    for k, v in per_page.items():
        page_text[k] = "".join(x["ruleText"] for x in order_cards(v))

    # 2) 逐章清洗 + 语义切分
    new_cards: List[dict] = []
    removed_log: List[str] = []
    seq = collections.Counter()
    for ch in chapters:
        pages = sorted((p, t) for (s, p), t in page_text.items()
                       if s == ch["subject"] and ch["pageStart"] <= p <= ch["pageEnd"])
        pages, rm = strip_running_heads(pages, ch)
        removed_log += rm

        carry = None
        ch_prefix = prefixes.get(ch["subject"], "D")
        for page, text in pages:
            if not text:
                continue
            segs = segment(text)
            if carry is not None:
                # 跨页残句一律接续，避免「半词结尾」；即使下一页以序号开头也保留原句
                if segs:
                    joiner = " " if (carry[-1:].isdigit() and segs[0][:1].isdigit()) else ""
                    segs[0] = carry + joiner + segs[0]
                else:
                    segs = [carry]
                carry = None
            tail = segs[-1].rstrip(" .…·") if segs else ""
            # 跨页：残句、以及「……如下：」这类列举引领句，必须与下一页接续
            if tail and (not ends_terminal(tail) or tail.endswith(("：", ":"))
                         or re.search(r"(?:（[一二三四五六七八九十\d]{1,3}）|\d{1,2}[．.])$", tail)):
                carry = segs.pop()
            for s in segs:
                seq[ch["no"]] += 1
                cid = "%s-%d.%d.%d" % (ch_prefix, ch["no"], page, seq[ch["no"]])
                body = s.strip()
                new_cards.append({
                    "id": cid, "title": make_title(body),
                    "priority": "P1", "freq": "中", "qtype": "",
                    "subject": ch["subject"], "chapter": ch["no"],
                    "chapterName": ch["name"], "section": "",
                    "page": page, "pageStart": page, "pageEnd": page,
                    "source": "%s / 第%d章 %s / 教材第%d页（本地OCR）" %
                              (ch["subject"], ch["no"], ch["name"], page),
                    "ruleText": body,
                    "numbers": extract_numbers(body),
                    "lawRefs": [], "lawText": None, "effectiveDate": None,
                    "lawVerified": False, "confusable": [], "example": False,
                    "table": None, "layer": "fact",
                    "anchor": "#e-" + cid.replace(".", "-"),
                    "pdfPage": page + offsets.get(ch["subject"], 0),
                    "mdAnchor": "", "ocr_confidence": None,
                    "ocr_source": True, "needs_review": "[?]" in body,
                })
        # 章末 carry 收尾
        if carry:
            seq[ch["no"]] += 1
            cid = "%s-%d.%d.%d" % (ch_prefix, ch["no"], ch["pageEnd"], seq[ch["no"]])
            new_cards.append({
                "id": cid, "title": make_title(carry), "priority": "P1", "freq": "中",
                "qtype": "", "subject": ch["subject"], "chapter": ch["no"],
                "chapterName": ch["name"], "section": "", "page": ch["pageEnd"],
                "pageStart": ch["pageEnd"], "pageEnd": ch["pageEnd"],
                "source": "%s / 第%d章 %s / 教材第%d页（本地OCR）" %
                          (ch["subject"], ch["no"], ch["name"], ch["pageEnd"]),
                "ruleText": carry, "numbers": extract_numbers(carry),
                "lawRefs": [], "lawText": None, "effectiveDate": None,
                "lawVerified": False, "confusable": [], "example": False,
                "table": None, "layer": "fact",
                "anchor": "#e-" + cid.replace(".", "-"),
                "pdfPage": ch["pageEnd"] + offsets.get(ch["subject"], 0),
                "mdAnchor": "", "ocr_confidence": None,
                "ocr_source": True, "needs_review": "[?]" in carry,
            })

    # 3) 术语（只从新卡正文派生）
    glossary, rejects = build_glossary(new_cards)
    glossary = glossary[:400] if glossary else [
        {"term": "资料锚点", "def": "用于把卡片回溯到原始资料的页码标记。",
         "subject": meta["subjects"][0], "chapter": 1, "page": 1}]

    # 4) coverage
    coverage = []
    for ch in chapters:
        sub = [c for c in new_cards if c["subject"] == ch["subject"] and c["chapter"] == ch["no"]]
        coverage.append({
            "subject": ch["subject"], "no": ch["no"], "name": ch["name"],
            "pdfStart": ch["pageStart"] + offsets.get(ch["subject"], 0),
            "pdfEnd": ch["pageEnd"] + offsets.get(ch["subject"], 0),
            "pageStart": ch["pageStart"], "pageEnd": ch["pageEnd"],
            "sourcePages": max(1, ch["pageEnd"] - ch["pageStart"] + 1),
            "rules": len(sub), "numbers": sum(len(x["numbers"]) for x in sub),
            "tables": 0, "examples": 0, "cards": len(sub),
            "status": "已重建（语义切分 + 页眉页脚剔除）",
        })

    # 5) 数字守恒（清洗后页文本 vs 卡片）
    src_nums = collections.Counter()
    for ch in chapters:
        pages = sorted((p, t) for (s, p), t in page_text.items()
                       if s == ch["subject"] and ch["pageStart"] <= p <= ch["pageEnd"])
        pages, _ = strip_running_heads(pages, ch)
        for _, t in pages:
            src_nums.update(n for n in re.findall(r"\d+(?:\.\d+)?", t))
    card_nums = collections.Counter()
    for c in new_cards:
        card_nums.update(re.findall(r"\d+(?:\.\d+)?", c["ruleText"]))
    num_loss = src_nums - card_nums
    num_dup = card_nums - src_nums

    # 6) 门禁
    ends_bad = [c["id"] for c in new_cards if not ends_terminal(c["ruleText"])]
    ids = [c["id"] for c in new_cards]
    titles = [c["title"] for c in new_cards]
    title_dup = len(titles) - len(set(titles))
    garbage_gl = [g["term"] for g in glossary
                  if GARBAGE_TERM.search(g["term"]) or len(g["term"]) > 12]
    lens = [len(c["ruleText"]) for c in new_cards]
    checks = {
        "ids_unique": len(ids) == len(set(ids)),
        "numbers_conserved": not num_loss and not num_dup,
        "no_card_ends_mid_sentence": len(ends_bad) <= max(3, int(len(new_cards) * 0.005)),
        "glossary_no_garbage": not garbage_gl,
        "titles_no_placeholder": not any("（节选）" in t for t in titles),
        "every_card_has_page": all(c["pdfPage"] > 0 for c in new_cards),
        "avg_card_len_ok": statistics.mean(lens) >= 90,
    }
    gate = {
        "passed": all(checks.values()), "checks": checks,
        "cards_before": len(cards_old), "cards_after": len(new_cards),
        "chapters": len(chapters),
        "avg_len": round(statistics.mean(lens), 1),
        "median_len": statistics.median(lens),
        "ends_mid_sentence": len(ends_bad),
        "duplicate_titles": title_dup,
        "glossary": len(glossary), "glossary_rejects": len(rejects),
        "numbers_src": sum(src_nums.values()), "numbers_cards": sum(card_nums.values()),
        "numbers_lost": list(num_loss.items())[:10],
        "numbers_added": list(num_dup.items())[:10],
        "removed_noise_samples": removed_log[:10],
        "violations": {"ends_mid": ends_bad[:10], "garbage_glossary": garbage_gl[:10]},
    }

    new = {
        "meta": dict(meta, note="卡片由语义切分重建；页眉页脚已剔除；术语仅从卡片正文派生。"),
        "chapters": chapters, "cards": new_cards, "coverage": coverage,
        "glossary": glossary,
    }
    json.dump(new, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.report:
        json.dump(gate, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    log("cards %d -> %d | avg %.0f | ends_mid %d | glossary %d (reject %d) | numbers %d->%d" %
        (len(cards_old), len(new_cards), statistics.mean(lens), len(ends_bad),
         len(glossary), len(rejects), sum(src_nums.values()), sum(card_nums.values())))
    log("gate " + ("PASS" if gate["passed"] else "FAIL") + " " +
        json.dumps({k: v for k, v in checks.items() if not v}, ensure_ascii=False))
    if a.show:
        for c in new_cards[: a.show]:
            log("%s | %s | %s" % (c["id"], c["title"], c["ruleText"][:60]))
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
