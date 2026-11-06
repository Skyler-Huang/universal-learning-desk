#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多格式资料读取层（universal-learning-desk / Stage 1）。

把任意格式资料统一转成「带锚点的 Markdown + sidecar 元数据」，供 extract_cards.py 消费。

路由：
  PDF   -> 文字层可用时 PyMuPDF 直接抽取；扫描版/字体映射乱码时本地 RapidOCR（200 DPI）
  图片  -> 本地 RapidOCR
  PPTX  -> python-pptx 逐页（严格每页一个单元）；不可用时 markitdown 兜底
  DOCX/HTML/MD/TXT -> markitdown[all] 转 Markdown；不可用时本地解析器兜底

锚点：
  PPT              <!-- SLIDE_n -->
  PDF / 图片 / 文档 <!-- PDF_PAGE_n -->

输出（--out-dir）：
  <stem>.md            带锚点的 Markdown
  <stem>.reader.json   sidecar：source_type / engine / units / warnings
  .ocr_cache/          逐页 OCR 缓存，支持断点续跑

用法：
  python universal_reader.py --input 资料.pdf --out-dir ./work
  python universal_reader.py --input 讲义.pptx --out-dir ./work --engine text
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import re
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

# 保证能 import 同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_EXT = {".md", ".markdown", ".txt", ".text"}
OFFICE_EXT = {".docx", ".pptx", ".html", ".htm"}
PDF_EXT = {".pdf"}

ANCHOR_RE = re.compile(r"<!--\s*([A-Z_]+)_(\d+)\s*-->")


# ------------------------------------------------------------------ 工具
def log(msg: str) -> None:
    print("[reader] " + msg, flush=True)


def ext_of(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def detect_type(path: str) -> str:
    e = ext_of(path)
    if e in PDF_EXT:
        return "pdf"
    if e in IMAGE_EXT:
        return "image"
    if e == ".pptx":
        return "pptx"
    if e == ".docx":
        return "docx"
    if e in {".html", ".htm"}:
        return "html"
    if e in TEXT_EXT:
        return "text"
    return "unknown"


def _safe_text(s: Any) -> str:
    return "" if s is None else str(s)


# ------------------------------------------------------------------ OCR
_OCR = None
_OCR_CFG: Optional[str] = None


def make_single_thread_config() -> Optional[str]:
    """生成一份临时的单线程 RapidOCR 配置，避免在 4 核容器里 ONNX 开几十个线程导致节流。

    模型路径由 rapidocr 包内的 update_model_path() 依据模块目录解析，与 config_path 无关，
    因此把配置写到 /tmp 是安全的，也不会修改用户已安装的包。
    """
    try:
        import rapidocr_onnxruntime as R
    except ImportError:
        return None
    src = os.path.join(os.path.dirname(R.__file__), "config.yaml")
    if not os.path.exists(src):
        return None
    s = open(src, encoding="utf-8").read()
    s = s.replace("&intra_nums -1", "&intra_nums 1").replace("&inter_nums -1", "&inter_nums 1")
    s = s.replace("&inter_nums -1", "&inter_nums 1")
    fd, dst = tempfile.mkstemp(suffix=".yaml", prefix="uld_ocr_")
    os.close(fd)
    open(dst, "w", encoding="utf-8").write(s)
    return dst


def _init_ocr_worker(cfg: Optional[str]) -> None:
    global _OCR
    from rapidocr_onnxruntime import RapidOCR
    _OCR = RapidOCR(config_path=cfg) if cfg else RapidOCR()


def _ocr_one(task: Dict[str, Any]) -> Dict[str, Any]:
    """子进程：渲染一页 PDF 或读取一张图片并识别。"""
    import numpy as np
    idx = task["index"]
    try:
        t0 = time.time()
        if task.get("pdf"):
            import pymupdf as fitz
            doc = fitz.open(task["pdf"])
            pix = doc[task["page"] - 1].get_pixmap(
                dpi=task["dpi"], colorspace=fitz.csGRAY, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            doc.close()
        else:
            import cv2
            img = cv2.imread(task["image"], cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise RuntimeError("图片无法读取: %s" % task["image"])
        result, _ = _OCR(img, use_cls=False)
        lines = [{"text": _safe_text(r[1]), "score": float(r[2])} for r in (result or [])]
        return {"index": idx, "lines": lines, "elapsed": round(time.time() - t0, 2),
                "error": None}
    except Exception as ex:                                    # 单页失败不中断全书
        return {"index": idx, "lines": [], "elapsed": 0,
                "error": "%s: %s" % (type(ex).__name__, ex)}


def ocr_units(tasks: List[Dict[str, Any]], out_dir: str, workers: int,
              cfg: Optional[str], prefix: str) -> List[Dict[str, Any]]:
    """执行 OCR，逐页原子写缓存，支持断点续跑。返回按 index 排序的原始页结果。"""
    cache = os.path.join(out_dir, ".ocr_cache", prefix)
    os.makedirs(cache, exist_ok=True)
    pending = []
    for t in tasks:
        fp = os.path.join(cache, "page_%04d.json" % t["index"])
        if os.path.exists(fp):                                # 断点续跑
            continue
        pending.append(t)
    if pending:
        log("OCR 待处理 %d 页（已有缓存 %d 页），workers=%d" %
            (len(pending), len(tasks) - len(pending), workers))
        if workers > 1:
            with mp.Pool(workers, initializer=_init_ocr_worker, initargs=(cfg,)) as pool:
                for res in pool.imap_unordered(_ocr_one, pending):
                    _atomic_json(os.path.join(cache, "page_%04d.json" % res["index"]), res)
        else:
            _init_ocr_worker(cfg)
            for t in pending:
                res = _ocr_one(t)
                _atomic_json(os.path.join(cache, "page_%04d.json" % res["index"]), res)
        if cfg and os.path.exists(cfg):
            try:
                os.unlink(cfg)
            except OSError:
                pass
    out = []
    for t in tasks:
        fp = os.path.join(cache, "page_%04d.json" % t["index"])
        out.append(json.load(open(fp, encoding="utf-8")) if os.path.exists(fp)
                   else {"index": t["index"], "lines": [], "error": "缓存缺失"})
    return out


def _atomic_json(path: str, obj: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def lines_to_text(lines: List[Dict[str, Any]]) -> str:
    return "\n".join(x["text"] for x in lines if x["text"].strip())


def page_confidence(lines: List[Dict[str, Any]]) -> Optional[float]:
    sc = [x["score"] for x in lines if x.get("score") is not None]
    return round(sum(sc) / len(sc), 4) if sc else None


# ------------------------------------------------------------------ 各格式
def read_pdf(path: str, out_dir: str, engine: str, dpi: int, workers: int,
             warnings: List[str]) -> Tuple[str, str, List[Dict[str, Any]], str]:
    """返回 (anchor_prefix, engine_name, units, source_type)。"""
    try:
        import pymupdf as fitz
    except ImportError as ex:
        raise RuntimeError("缺少 PyMuPDF，请执行 pip install PyMuPDF") from ex

    doc = fitz.open(path)
    n = doc.page_count
    sample = "".join(doc[i].get_text() for i in range(min(6, n)))
    doc.close()
    has_text = len(sample.strip()) >= 60

    if engine == "ocr" or (engine == "auto" and not has_text):
        cfg = make_single_thread_config()
        if cfg is None:
            raise RuntimeError("缺少 rapidocr-onnxruntime，请执行 pip install rapidocr-onnxruntime")
        tasks = [{"index": i, "pdf": path, "page": i, "dpi": dpi} for i in range(1, n + 1)]
        raw = ocr_units(tasks, out_dir, max(1, workers), cfg, "pdf")
        units, failed = [], []
        for r in raw:
            if r.get("error"):
                failed.append(r["index"])
            lines = r.get("lines", [])
            units.append({
                "index": r["index"], "text": lines_to_text(lines),
                "ocr_confidence": page_confidence(lines), "is_ocr": True,
                "error": r.get("error"),
            })
        if failed:
            warnings.append("OCR 失败页: %s" % failed)
        return "PDF_PAGE", "rapidocr-onnxruntime (200DPI, use_cls=False)", units, "pdf"

    # 文字层路径
    doc = fitz.open(path)
    units = []
    for i in range(n):
        t = doc[i].get_text()
        units.append({"index": i + 1, "text": t.strip(),
                      "ocr_confidence": None, "is_ocr": False, "error": None})
    doc.close()
    if engine == "auto" and has_text:
        warnings.append("PDF 检测到可用文字层，走 PyMuPDF 直接抽取；"
                        "若文字层存在字体映射乱码，请加 --engine ocr 强制重识别")
    return "PDF_PAGE", "pymupdf-text", units, "pdf"


def read_image(path: str, out_dir: str, dpi: int, workers: int,
               warnings: List[str]) -> Tuple[str, str, List[Dict[str, Any]], str]:
    cfg = make_single_thread_config()
    if cfg is None:
        raise RuntimeError("缺少 rapidocr-onnxruntime，请执行 pip install rapidocr-onnxruntime")
    tasks = [{"index": 1, "image": path, "dpi": dpi}]
    raw = ocr_units(tasks, out_dir, 1, cfg, "img")
    r = raw[0]
    if r.get("error"):
        warnings.append("图片 OCR 失败: %s" % r["error"])
    lines = r.get("lines", [])
    units = [{"index": 1, "text": lines_to_text(lines),
              "ocr_confidence": page_confidence(lines), "is_ocr": True,
              "error": r.get("error")}]
    return "PDF_PAGE", "rapidocr-onnxruntime (image)", units, "image"


def read_pptx(path: str, warnings: List[str]) -> Tuple[str, str, List[Dict[str, Any]], str]:
    """严格按幻灯片页切分：每页一个单元，输出 <!-- SLIDE_n -->。"""
    units: List[Dict[str, Any]] = []
    engine = "python-pptx"
    try:
        from pptx import Presentation
        prs = Presentation(path)
        for i, slide in enumerate(prs.slides, 1):
            parts: List[str] = []
            title = ""
            try:
                if slide.shapes.title is not None:
                    title = _safe_text(slide.shapes.title.text).strip()
            except Exception:
                pass
            if title:
                parts.append("# " + title)
            for shape in slide.shapes:
                try:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            t = "".join(run.text for run in para.runs).strip()
                            if t and t != title:
                                parts.append(t)
                    if getattr(shape, "has_table", False):
                        for row in shape.table.rows:
                            cells = [c.text.strip() for c in row.cells]
                            parts.append("| " + " | ".join(cells) + " |")
                except Exception:
                    continue
            try:
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    note = slide.notes_slide.notes_text_frame.text.strip()
                    if note:
                        parts.append("> 备注：" + note)
            except Exception:
                pass
            units.append({"index": i, "text": "\n\n".join(parts).strip(),
                          "ocr_confidence": None, "is_ocr": False, "error": None})
        warnings.append("PPT 使用 python-pptx 逐页提取，保证「每页一张核心卡片」；"
                        "markitdown 仅在其他格式/兜底路径使用")
    except ImportError:
        engine = "markitdown"
        md = _markitdown_convert(path, warnings)
        if md is None:
            raise RuntimeError("缺少 python-pptx 且 markitdown 不可用；"
                               "请执行 pip install 'markitdown[all]'")
        chunks = re.split(r"<!--\s*Slide number:\s*(\d+)\s*-->", md, flags=re.I)
        if len(chunks) > 1:
            for j in range(1, len(chunks), 2):
                no, body = int(chunks[j]), chunks[j + 1].strip()
                units.append({"index": no, "text": body, "ocr_confidence": None,
                              "is_ocr": False, "error": None})
        else:
            units = [{"index": 1, "text": md.strip(), "ocr_confidence": None,
                      "is_ocr": False, "error": None}]
            warnings.append("markitdown 未输出幻灯片分界，整份 PPT 作为 1 个单元")
    if not units:
        units = [{"index": 1, "text": "", "ocr_confidence": None,
                  "is_ocr": False, "error": None}]
    return "SLIDE", engine, units, "pptx"


def _markitdown_convert(path: str, warnings: List[str]) -> Optional[str]:
    """调用 markitdown[all]；不可用时返回 None 由调用方降级。"""
    try:
        from markitdown import MarkItDown
        res = MarkItDown().convert(path)
        md = getattr(res, "text_content", None) or getattr(res, "markdown", None)
        if md is None:
            raise RuntimeError("markitdown 返回为空")
        return md
    except ImportError:
        warnings.append("未安装 markitdown，使用本地解析器兜底（不影响结果）")
        return None
    except Exception as ex:
        warnings.append("markitdown 转换失败(%s: %s)，使用本地解析器兜底" %
                        (type(ex).__name__, ex))
        return None


def _local_docx(path: str) -> str:
    from docx import Document
    d = Document(path)
    out = []
    for p in d.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        style = (p.style.name or "").lower()
        out.append(("# " + t) if style.startswith("heading 1") else
                   ("## " + t) if style.startswith("heading 2") else t)
    for tb in d.tables:
        for row in tb.rows:
            out.append("| " + " | ".join(c.text.strip() for c in row.cells) + " |")
    return "\n\n".join(out)


def _local_html(path: str) -> str:
    raw = open(path, encoding="utf-8", errors="replace").read()
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text("\n", strip=True)
    except ImportError:
        return re.sub(r"<[^>]+>", "\n", raw)


def split_text_units(text: str, max_chars: int = 1400) -> List[str]:
    """无分页的文档按段落累积切成若干「页面单元」，保证每个单元都有锚点。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        return [text.strip()]
    units, buf, size = [], [], 0
    for p in paras:
        while len(p) > max_chars:                 # 超长段落硬切
            if buf:
                units.append("\n\n".join(buf)); buf, size = [], 0
            units.append(p[:max_chars]); p = p[max_chars:]
        if size + len(p) > max_chars and buf:
            units.append("\n\n".join(buf)); buf, size = [], 0
        buf.append(p); size += len(p)
    if buf:
        units.append("\n\n".join(buf))
    return units


def read_document(path: str, kind: str, max_chars: int,
                  warnings: List[str]) -> Tuple[str, str, List[Dict[str, Any]], str]:
    md = _markitdown_convert(path, warnings)
    engine = "markitdown[all]"
    if md is None:
        if kind == "docx":
            md, engine = _local_docx(path), "python-docx (fallback)"
        elif kind == "html":
            md, engine = _local_html(path), "beautifulsoup4 (fallback)"
        else:
            md = open(path, encoding="utf-8", errors="replace").read()
            engine = "plain-text"
    chunks = split_text_units(md, max_chars)
    units = [{"index": i, "text": t, "ocr_confidence": None,
              "is_ocr": False, "error": None} for i, t in enumerate(chunks, 1)]
    return "PDF_PAGE", engine, units, kind


# ------------------------------------------------------------------ 输出
def build_outputs(anchor_prefix: str, engine: str, source_type: str,
                  units: List[Dict[str, Any]], source_file: str,
                  warnings: List[str]) -> Tuple[str, Dict[str, Any]]:
    md_parts: List[str] = []
    meta_units: List[Dict[str, Any]] = []
    for u in units:
        idx = u["index"]
        anchor = "%s_%d" % (anchor_prefix, idx)
        md_parts.append("<!-- %s -->\n%s" % (anchor, u["text"].strip()))
        if source_type == "pptx":
            label, source_label = "幻灯片 %d" % idx, "幻灯片 %d" % idx
            utype = "slide"
        elif source_type == "image":
            label, source_label, utype = "图片 %d" % idx, "文档 %d" % idx, "image"
        elif source_type == "pdf":
            label, source_label, utype = "第 %d 页" % idx, "文档 %d" % idx, "pdf_page"
        else:
            label, source_label, utype = "第 %d 节" % idx, "文档 %d" % idx, "doc_unit"
        meta_units.append({
            "index": idx, "anchor": anchor,
            "anchor_comment": "<!-- %s -->" % anchor,
            "unit_type": utype, "label": label, "source_label": source_label,
            "page": idx, "ocr_confidence": u.get("ocr_confidence"),
            "is_ocr": bool(u.get("is_ocr")), "error": u.get("error"),
            "text_chars": len(u["text"]),
        })
    md = "\n\n".join(md_parts) + "\n"
    meta = {
        "source_file": os.path.abspath(source_file),
        "source_name": os.path.basename(source_file),
        "source_type": source_type,
        "anchor_prefix": anchor_prefix,
        "engine": engine,
        "total_units": len(units),
        "units": meta_units,
        "warnings": warnings,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return md, meta


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="多格式资料 → 带锚点 Markdown")
    ap.add_argument("--input", required=True, help="输入文件（任意支持格式）")
    ap.add_argument("--out-dir", default=None, help="输出目录，默认与输入同级的 <stem>_work")
    ap.add_argument("--engine", choices=["auto", "ocr", "text"], default="auto",
                    help="PDF 引擎：auto=有文字层走抽取否则 OCR；ocr=强制 OCR；text=强制文字层")
    ap.add_argument("--dpi", type=int, default=200, help="PDF 渲染 DPI（默认 200）")
    ap.add_argument("--workers", type=int, default=4, help="OCR 进程数（默认 4，按 CPU 配额调整）")
    ap.add_argument("--max-chars", type=int, default=1400, help="文本文档每个页面单元最大字符数")
    a = ap.parse_args(argv)

    if not os.path.exists(a.input):
        log("ERROR 输入文件不存在: " + a.input)
        return 2
    stem = os.path.splitext(os.path.basename(a.input))[0]
    out_dir = a.out_dir or os.path.join(os.path.dirname(os.path.abspath(a.input)), stem + "_work")
    os.makedirs(out_dir, exist_ok=True)

    kind = detect_type(a.input)
    warnings: List[str] = []
    log("输入 %s | 类型 %s" % (a.input, kind))
    if kind == "pdf":
        ap_, eng, units, stype = read_pdf(a.input, out_dir, a.engine, a.dpi, a.workers, warnings)
    elif kind == "image":
        ap_, eng, units, stype = read_image(a.input, out_dir, a.dpi, a.workers, warnings)
    elif kind == "pptx":
        ap_, eng, units, stype = read_pptx(a.input, warnings)
    elif kind in {"docx", "html", "text"}:
        ap_, eng, units, stype = read_document(a.input, kind, a.max_chars, warnings)
    else:
        log("ERROR 不支持的扩展名: " + ext_of(a.input))
        return 2

    md, meta = build_outputs(ap_, eng, stype, units, a.input, warnings)
    md_path = os.path.join(out_dir, stem + ".md")
    meta_path = os.path.join(out_dir, stem + ".reader.json")
    open(md_path, "w", encoding="utf-8").write(md)
    _atomic_json(meta_path, meta)

    log("引擎 %s | 单元 %d | 锚点 %s_n | 文本 %d 字" % (eng, len(units), ap_, len(md)))
    for w in warnings:
        log("WARN " + w)
    log("已写出 " + md_path)
    log("已写出 " + meta_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
