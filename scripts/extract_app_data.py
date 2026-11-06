#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从既有学习台/知识台 HTML 抽出 APP_DATA，供 rebuild_cards.py 使用。"""
import argparse
import json
import re
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    s = open(a.html, encoding="utf-8").read()
    m = re.search(r'<script[^>]*id="APP_DATA"[^>]*>(.*?)</script>', s, re.S)
    if not m:
        print("[extract] ERROR 未找到 APP_DATA", file=sys.stderr)
        return 1
    data = json.loads(m.group(1))
    json.dump(data, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[extract] cards=%d glossary=%d -> %s" %
          (len(data.get("cards", [])), len(data.get("glossary", [])), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
