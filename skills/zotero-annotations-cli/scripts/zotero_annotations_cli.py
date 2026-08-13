#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zotero_annotations_cli.py — Zotero 批注命令行工具（单一命令，参数合并）。

读取批注元数据与读取批注原文上下文不做子命令区分，合并为一个命令：
  - 基础参数（--key/--query/--collection）必选其一，定位文献。
  - 若只给基础参数（或 --full/--json/--no-color/--cache-dir）→ 元数据模式，
    只读批注元数据（纯标准库，不读 PDF）。
  - 若给了上下文参数（--color/--ann-key/--before/--after/--fulltext/--export-pdf）
    中的任一 → 上下文模式，读 PDF 原文，按批注精确位置（annotationPosition）
    提取高亮处前后 N 句，可导出全文/PDF 副本。需要 PyMuPDF。

本命令全程只读（Zotero 本地 API + 本地存储 PDF），绝不写库、不改 PDF。

用法（本源码打包为可执行文件后运行；Windows 下为 zotero_annotations_cli.exe）：
  zotero_annotations_cli --key ASDFGHJK                      # 元数据
  zotero_annotations_cli --query "示例标题" --collection 示例合集
  zotero_annotations_cli --key ASDFGHJK --full --json        # 元数据全量/JSON
  zotero_annotations_cli --key ASDFGHJK --color red          # 上下文：红色标注
  zotero_annotations_cli --key ASDFGHJK --ann-key AAAA0000 --before 2 --after 2
  zotero_annotations_cli --key ASDFGHJK --fulltext --export-pdf

参数：
  定位：
    --query TEXT / --collection TEXT / --key KEY   定位文献（必选其一）
  通用：
    --json           输出原始 JSON
    --cache-dir PATH 缓存目录
  元数据模式：
    --full           忽略缓存，全量输出
    --no-color       不按颜色分组
  上下文模式（任给其一即进入；需 PyMuPDF）：
    --color NAME|HEX   只处理指定颜色批注（可多次：red / #ff6666）
    --ann-key KEY      只处理指定批注 key（可多次）
    --before N / --after N   上下文前/后句数，默认 2/2（共 5 句）
    --fulltext         导出全文文本到 <cache>/<key>.txt
    --export-pdf       复制 PDF 到 <cache>/<key>.pdf（按 item key 命名）

缓存目录优先级：--cache-dir > 当前工作目录下 .zotero-annotations/ > 系统 temp。
无论落在哪，脚本都会在输出里给出 cache= 路径。

退出码：0 成功，1 失败。错误信息见 stderr 的 `ERROR <HTTP码> <LABEL>: 文字`。
"""

import argparse
import datetime
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import urllib.parse

BASE = "http://127.0.0.1:23119"

# Zotero 内置批注颜色（hex -> 友好名）。
COLOR_NAMES = {
    "#ff6666": "red",
    "#ffd400": "yellow",
    "#2ea8e5": "blue",
    "#ff7f2a": "orange",
    "#98fb98": "green",
    "#ff00ff": "magenta",
    "#000000": "black",
}

try:
    import pymupdf as fitz  # 新版包名；旧版 fitz 亦可用（上下文模式才需要）
except ImportError:
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None  # type: ignore

PLACEHOLDER = "\uE000"  # 私有区字符，用于分句时保护缩写点号

PREFIX = "[zotero-annotations-cli]"


def api(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fail(code, label, text):
    """统一错误输出：文字直接可读，并带 HTTP 风格错误码（如 404 NOT_FOUND）。
    进程退出码统一为 1（HTTP 码 >255 会被 shell 截断，故不放退出码里）。"""
    print(f"{PREFIX} ERROR {code} {label}: {text}", file=sys.stderr)
    sys.exit(1)


def check_status():
    """端口可访问返回 True，否则打印提示并返回 False（调用方 fail 503）。"""
    try:
        api("/api/schema")  # 真实 JSON 端点；根 /api/ 是纯文本
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"{PREFIX} 无法连接 Zotero 本地 API: {exc}", file=sys.stderr)
        fail(503, "SERVICE_UNAVAILABLE",
             "Zotero 本地 API 不可用。请在 Zotero 中开启本地服务："
             "Settings(Preferences) -> Advanced -> Server -> "
             "'Allow other applications on this system to communicate with Zotero'，然后重启 Zotero。")


def find_collection(name):
    cols = api("/api/users/0/collections", {"format": "json", "limit": 100})
    wanted = name.strip().lower()
    matches = [
        c["data"]
        for c in cols
        if c.get("data", {}).get("name", "").strip().lower() == wanted
    ]
    if not matches:
        available = sorted(c["data"]["name"] for c in cols)
        fail(404, "NOT_FOUND", f"集合 '{name}' 不存在。可用集合："
             + (", ".join(available) if available else "(无)"))
    if len(matches) > 1:
        print(f"{PREFIX} 存在多个同名集合 '{name}'，使用第一个。", file=sys.stderr)
    return matches[0]


def items_in_collection(col_key):
    items = []
    start = 0
    while True:
        batch = api(
            f"/api/users/0/collections/{col_key}/items",
            {"format": "json", "limit": 100, "start": start},
        )
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        start += len(batch)
    return items


def all_annotations():
    """分页抓取库中全部 annotation 条目。"""
    out = []
    start = 0
    while True:
        batch = api(
            "/api/users/0/items",
            {"itemType": "annotation", "format": "json", "limit": 100, "start": start},
        )
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        start += len(batch)
    return out


def normalize(text):
    """标题归一化：小写、统一 Unicode 破折号/空白，使带连字符与不带连字符的标题可互配。"""
    if not text:
        return ""
    out = text.lower()
    for ch in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212":
        out = out.replace(ch, "-")
    for ch in "\u00a0\u2009\u202f\u200b":
        out = out.replace(ch, " ")
    return " ".join(out.split())


def find_item_by_title(items, query):
    q = normalize(query)
    hits = [it["data"] for it in items if it.get("data", {}).get("itemType") != "attachment"]
    hits = [d for d in hits if q in normalize(d.get("title"))]
    return hits


def creator_string(d):
    return ", ".join(f"{c.get('firstName','')} {c.get('lastName','')}".strip() for c in d.get("creators", [])) or "?"


def page_key(d):
    label = d.get("annotationPageLabel") or ""
    num = int(label) if label.isdigit() else 10**9
    return (num, d.get("annotationSortIndex", ""))


def color_name(hexc):
    return COLOR_NAMES.get((hexc or "").lower(), hexc or "?")


def fetch_attachment_pdfs(item_key):
    try:
        kids = api(f"/api/users/0/items/{item_key}/children", {"format": "json"})
    except Exception:  # noqa: BLE001
        return []
    return [k["data"] for k in kids if k.get("data", {}).get("itemType") == "attachment"]


def locate_item(args):
    """按 --key / --query [--collection] 定位文献条目，返回 item data。"""
    if args.key:
        return api(f"/api/users/0/items/{args.key}", {"format": "json"})["data"]
    if args.collection:
        col = find_collection(args.collection)
        if not col:
            sys.exit(1)
        candidates = find_item_by_title(items_in_collection(col["key"]), args.query)
    else:
        candidates = find_item_by_title(
            api("/api/users/0/items/top", {"format": "json", "limit": 100}),
            args.query,
        )
    if not candidates:
        fail(404, "NOT_FOUND", f"没有匹配标题 '{args.query}' 的条目")
    if len(candidates) > 1:
        for c in candidates:
            print(f"  - {c['key']}  {c.get('title')}", file=sys.stderr)
        fail(300, "MULTIPLE_CHOICES",
             f"标题 '{args.query}' 命中 {len(candidates)} 条，有歧义。"
             "请用 --key 精确定位或细化 --query。")
    return candidates[0]


# ---------------------------------------------------------------------------
# 增量缓存
# ---------------------------------------------------------------------------

def resolve_cache_dir(explicit=None):
    """缓存目录优先级：--cache-dir > 当前工作目录 .zotero-annotations/ > 系统 temp。
    调用方需把最终 cache 路径提示给用户。"""
    if explicit:
        return explicit
    try:
        cwd = os.getcwd()
        if cwd and os.access(cwd, os.W_OK):
            return os.path.join(cwd, ".zotero-annotations")
    except Exception:  # noqa: BLE001
        pass
    return os.path.join(tempfile.gettempdir(), "zotero-annotations")


def load_cache(cache_dir, item_key):
    path = os.path.join(cache_dir, item_key + ".json")
    if not os.path.exists(path):
        return None, path
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path
    except (OSError, json.JSONDecodeError):
        return None, path


def save_cache(cache_dir, path, item_key, annos, versions, reading=None):
    os.makedirs(cache_dir, exist_ok=True)
    payload = {
        "item_key": item_key,
        "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "reading": reading,
        "annotations": {
            a["key"]: {
                "version": versions.get(a["key"]),
                "type": a.get("annotationType"),
                "color": a.get("annotationColor"),
                "page": a.get("annotationPageLabel"),
                "text": a.get("annotationText"),
                "comment": a.get("annotationComment"),
            }
            for a in annos
        },
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def print_ann_block(d):
    """每条批注用可 grep 的起止标记包裹。"""
    page = d.get("annotationPageLabel") or "?"
    atype = d.get("annotationType", "?")
    color = d.get("annotationColor") or ""
    text = (d.get("annotationText") or "").replace("\n", " ")
    comment = (d.get("annotationComment") or "").replace("\n", " ") or "(无)"
    print(f"<<<ANN key={d.get('key')} color={color_name(color)} hex={color} page={page} type={atype}")
    print(f"TEXT: {text}")
    print(f"COMMENT: {comment}")
    print(">>>ANN")


def reading_position(annos, new_changed):
    """推测用户当前阅读位置（纯批注元数据推导，不读全文，不越界）。"""
    r = {"method2_farthest": None, "method1_delta": None}
    if annos:
        last = max(annos, key=page_key)
        r["method2_farthest"] = {
            "page": last.get("annotationPageLabel") or "?",
            "key": last.get("key"),
            "total": len(annos),
        }
    if new_changed:
        pages = []
        for a in new_changed:
            label = a.get("annotationPageLabel") or ""
            if label.isdigit():
                pages.append(int(label))
        if pages:
            pages.sort()
            r["method1_delta"] = {
                "count": len(pages),
                "pages": pages,
                "min": pages[0],
                "max": pages[-1],
            }
    return r


def render_reading(r, old_r=None):
    """输出阅读定位块（可 grep：grep '阅读定位' 定位整块）。"""
    print("\n### 阅读定位（推测当前读到哪，无需拉取全文）")
    f = r.get("method2_farthest")
    if f:
        prog = ""
        if old_r and old_r.get("method2_farthest"):
            old_p = old_r["method2_farthest"].get("page")
            if str(old_p) != str(f["page"]):
                prog = f"  [上次: 第 {old_p} 页]"
        print(f"最远标记: 第 {f['page']} 页 (key={f['key']}, 共 {f['total']} 条批注){prog}")
    else:
        print("最远标记: (无批注)")
    d = r.get("method1_delta")
    if d:
        print(f"新增分布: {d['count']} 条新增/更新，页码 {d['pages']}，"
              f"范围 {d['min']}–{d['max']} 页")
    else:
        print("新增分布: (本次无新增/更新)")


def render_rows(rows, no_color):
    if no_color:
        for d in rows:
            print_ann_block(d)
        return
    groups = {}
    for d in rows:
        groups.setdefault(d.get("annotationColor"), []).append(d)
    if not groups:
        return
    # 红色(内容标注)优先展示
    order = sorted(groups.items(), key=lambda kv: (kv[0] != "#ff6666", kv[0] or ""))
    for color, rs in order:
        print(f"\n### 颜色 {color_name(color)} ({color}) — {len(rs)} 条")
        for d in rs:
            print_ann_block(d)


# ---------------------------------------------------------------------------
# 上下文提取（基于批注精确位置 annotationPosition）
# ---------------------------------------------------------------------------

def zotero_data_dir_candidates():
    """收集可能的 Zotero 数据目录：prefs.js 里的 dataDir + 默认 ~/Zotero。"""
    out = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        for prefs in (
            glob.glob(os.path.join(appdata, "Zotero", "Zotero", "prefs.js"))
            + glob.glob(os.path.join(appdata, "Zotero", "Zotero", "*", "prefs.js"))
        ):
            try:
                with open(prefs, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        m = re.search(
                            r'user_pref\("extensions\.zotero\.dataDir",\s*"([^"]*)"\)',
                            line,
                        )
                        if m:
                            out.append(m.group(1).encode().decode("unicode_escape"))
            except OSError:
                pass
    out.append(os.path.join(os.path.expanduser("~"), "Zotero"))
    return out


def locate_pdf_file(att):
    """在 Zotero 本地存储里定位 PDF 文件的绝对路径（只读）。找不到返回 None。"""
    link = att.get("linkMode") or ""
    path = att.get("path") or ""
    fname = att.get("filename") or ""
    key = att.get("key")
    if link == "linked_file" and path:
        p = path[len("attachments:") :] if path.startswith("attachments:") else path
        if os.path.exists(p):
            return p
    if path.startswith("storage:"):
        fname = path[len("storage:") :] or fname
    for data_dir in zotero_data_dir_candidates():
        p = os.path.join(data_dir, "storage", key, fname)
        if os.path.exists(p):
            return p
    for data_dir in zotero_data_dir_candidates():
        d = os.path.join(data_dir, "storage", key)
        if os.path.isdir(d):
            pdfs = glob.glob(os.path.join(d, "*.pdf"))
            if pdfs:
                return pdfs[0]
    return None


def conv_rect(page, r):
    """Zotero annotationPosition 的 rect 是 PDF 原生坐标（左下原点）；
    转成 PyMuPDF 的左上原点坐标系。"""
    H = page.rect.height
    x0, y0, x1, y1 = r
    return fitz.Rect(x0, H - y1, x1, H - y0)


def exact_phrase(page, rects):
    """按批注 rect 逐块取词并拼接，得到高亮的精确文本。"""
    frags = [page.get_textbox(conv_rect(page, r)).strip() for r in rects]
    return " ".join(f for f in frags if f)


def split_sentences(text):
    """粗略分句：句号/问号/叹号（含其后引用编号如 [2]）+ 空白 + 大写/数字 开头为新句。
    先保护常见缩写（e.g., Fig., et al., 数字点号）避免误切。"""
    def protect(m):
        return m.group(0).replace(".", PLACEHOLDER)

    t = re.sub(
        r"\b(?:e\.g|i\.e|et al|etc|vs|cf|approx|al|Fig|Figs|Figure|Ref|Refs|"
        r"Eq|Eqs|No|Nos|Dr|Prof|Mr|Mrs|Ms|St|Mt|Jan|Feb|Mar|Apr|Jun|Jul|Aug|"
        r"Sep|Oct|Nov|Dec|U\.S|U\.K|Ph\.D|Inc|Ltd|Corp|Co)\.",
        protect,
        text,
        flags=re.IGNORECASE,
    )
    parts = re.split(
        r"(?<=[.!?])\s*(?:\[[0-9][^\]\n]{0,15}\]\s*)*(?=[A-Z0-9\"'“])", t
    )
    return [p.replace(PLACEHOLDER, ".").strip() for p in parts if p.strip()]


def page_lines(page):
    """取页内所有文本行 (bbox, 归一化文本)，用于定位锚点行。"""
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            txt = "".join(s["text"] for s in line["spans"])
            txt = re.sub(r"\s+", " ", txt).strip()
            if txt:
                out.append((fitz.Rect(line["bbox"]), txt))
    return out


def anchor_line_text(page, rect):
    """找与高亮 rect 垂直重叠面积最大的那一行，返回其文本（定位锚点）。"""
    best_txt, best_ov = None, -1
    for bbox, txt in page_lines(page):
        ov = rect & bbox
        if ov.is_empty:
            continue
        area = (ov.x1 - ov.x0) * (ov.y1 - ov.y0)
        if area > best_ov:
            best_ov, best_txt = area, txt
    return best_txt


def find_phrase_offset(ntext, nphrase, anchor=None):
    """在页文本里定位短语偏移。若有锚点行文本，优先找锚点附近的那次出现，
    解决"同一短语在标题/正文重复"时定位到错误出现的问题。"""
    if anchor:
        ai = ntext.find(anchor)
        if ai >= 0:
            lo, hi = max(0, ai - len(anchor)), min(len(ntext), ai + len(anchor) * 2)
            idx = ntext.lower().find(nphrase.lower(), lo, hi)
            if idx >= 0:
                return idx
    return ntext.lower().find(nphrase.lower())


def context_window(page_text, phrase, before, after, anchor=None):
    """在页文本里定位 phrase，返回 (句子列表, 命中句索引, (start,end))。"""
    ntext = re.sub(r"\s+", " ", page_text).strip()
    nphrase = re.sub(r"\s+", " ", phrase).strip()
    if not nphrase:
        return None, None, None
    idx = find_phrase_offset(ntext, nphrase, anchor)
    if idx < 0:
        return None, None, None
    sents = split_sentences(ntext)
    pos = 0
    offsets = []
    for s in sents:
        st = ntext.find(s, pos)
        if st < 0:
            st = pos
        offsets.append((st, st + len(s)))
        pos = st + len(s)
    target = None
    for i, (st, en) in enumerate(offsets):
        if st <= idx < en:
            target = i
            break
    if target is None:
        return None, None, None
    lo = max(0, target - before)
    hi = min(len(sents), target + after + 1)
    return sents, target, (lo, hi)


def extract_fulltext(doc):
    """整篇 PDF 文本，页间用分隔行。"""
    parts = []
    for i, page in enumerate(doc):
        parts.append(f"\n\n===== PAGE {i + 1} =====\n\n" + page.get_text("text"))
    return "".join(parts)


def print_ctx(r_, before, after):
    print(f"<<<CTX key={r_['key']} color={color_name(r_['color'])} page={r_['page']}")
    print(f"PHRASE: {r_['phrase']}")
    if r_.get("comment"):
        print(f"COMMENT: {r_['comment']}")
    if r_.get("sentences"):
        sents = r_["sentences"]
        tgt = r_["target_idx"]
        lo, hi = r_["window"]
        for i in range(lo, hi):
            mark = ">>>" if i == tgt else "   "
            rel = i - tgt
            label = "S0" if rel == 0 else f"S{'+' if rel > 0 else ''}{rel}"
            print(f"  {mark} [{label}] {sents[i]}")
    else:
        print("  (无法在页文本中定位该短语；可能是跨栏排版或文本为图片)")
    print(">>>CTX")


# ---------------------------------------------------------------------------
# 主流程（单命令，自动判定模式）
# ---------------------------------------------------------------------------

def is_context_requested(args):
    """是否进入上下文模式：给了上下文参数中的任一。"""
    return bool(args.color or args.ann_key or args.fulltext or args.export_pdf)


def main():
    ap = argparse.ArgumentParser(description="Zotero 批注工具：默认读元数据；给上下文参数即读原文上下文")
    ap.add_argument("--query")
    ap.add_argument("--collection")
    ap.add_argument("--key")
    # 通用
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--cache-dir")
    # 元数据模式
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--no-color", action="store_true")
    # 上下文模式（任给其一即进入）
    ap.add_argument("--color", action="append", default=[])
    ap.add_argument("--ann-key", action="append", default=[])
    ap.add_argument("--before", type=int, default=2)
    ap.add_argument("--after", type=int, default=2)
    ap.add_argument("--fulltext", action="store_true")
    ap.add_argument("--export-pdf", action="store_true")
    args = ap.parse_args()

    if not (args.key or args.query):
        ap.error("provide --key or --query")

    if not check_status():
        sys.exit(1)

    if is_context_requested(args):
        cmd_context(args)
    else:
        cmd_annotate(args)


# ---------------------------------------------------------------------------
# 元数据模式
# ---------------------------------------------------------------------------

def cmd_annotate(args):
    item = locate_item(args)
    pdfs = fetch_attachment_pdfs(item["key"])
    if not pdfs:
        fail(422, "UNPROCESSABLE_ENTITY",
             f"条目 {item['key']} 没有 PDF 附件，无法读取批注")

    pdf_keys = {p["key"] for p in pdfs}
    raw = [a for a in all_annotations() if a["data"].get("parentItem") in pdf_keys]
    versions = {a["data"]["key"]: a.get("version") for a in raw}
    annos = [a["data"] for a in raw]
    annos.sort(key=page_key)

    cache_dir = resolve_cache_dir(args.cache_dir)
    old_cache, cache_path = load_cache(cache_dir, item["key"])
    old = (old_cache or {}).get("annotations", {})
    old_reading = (old_cache or {}).get("reading")
    had_cache = bool(old)
    current_keys = {a["key"] for a in annos}
    new_changed = [
        a for a in annos
        if a["key"] not in old or old[a["key"]].get("version") != versions.get(a["key"])
    ]
    removed = [k for k in old if k not in current_keys]
    reading = reading_position(annos, new_changed)
    save_cache(cache_dir, cache_path, item["key"], annos, versions, reading)

    if args.json:
        print(json.dumps(
            {
                "item": {
                    "key": item["key"],
                    "itemType": item.get("itemType"),
                    "title": item.get("title"),
                    "creators": creator_string(item),
                    "year": item.get("date", ""),
                    "publication": item.get("publicationTitle"),
                    "doi": item.get("DOI"),
                    "collections": item.get("collections", []),
                },
                "attachments": [{"key": p["key"], "title": p.get("title")} for p in pdfs],
                "annotations": annos,
                "delta": {
                    "new_or_changed": [a["key"] for a in new_changed],
                    "removed": removed,
                },
                "reading": reading,
                "reading_prev": old_reading,
                "cache_path": cache_path,
            },
            ensure_ascii=False,
            indent=2,
        ))
        return

    print("=" * 72)
    print("Title :", item.get("title"))
    print("Author:", creator_string(item))
    print("Source:", item.get("publicationTitle") or "", item.get("date") or "")
    if item.get("DOI"):
        print("DOI   :", item["DOI"])
    print("PDF(s):", ", ".join(p.get("title") or p["key"] for p in pdfs))
    print(f"Annotations: {len(annos)}")
    mode = "incremental" if (not args.full and had_cache) else ("full" if had_cache else "first")
    reading_txt = "none"
    if reading.get("method2_farthest"):
        reading_txt = f"page{reading['method2_farthest']['page']}"
    print(f"STATUS: OK | mode=annotate | mode2={mode} | annotations={len(annos)} "
          f"| new_updated={len(new_changed)} | removed={len(removed)} "
          f"| reading={reading_txt} | cache={cache_path}")
    print("=" * 72)

    render_reading(reading, old_reading)

    if not args.full and had_cache:
        print(f"增量：新增/更新 {len(new_changed)} 条，删除 {len(removed)} 条（缓存: {cache_path}）")
        if not new_changed and not removed:
            print("（无变化）")
        if new_changed:
            render_rows(new_changed, args.no_color)
        if removed:
            print("已删除:", ", ".join(removed))
    else:
        if had_cache:
            print(f"全量输出 {len(annos)} 条（--full）")
        else:
            print(f"首次读取，共 {len(annos)} 条")
        render_rows(annos, args.no_color)


# ---------------------------------------------------------------------------
# 上下文模式
# ---------------------------------------------------------------------------

def cmd_context(args):
    if fitz is None:
        fail(500, "DEPENDENCY_MISSING",
             "本机未安装 PyMuPDF，无法读取 PDF 原文。请先执行：pip install pymupdf")

    item = locate_item(args)
    pdfs = fetch_attachment_pdfs(item["key"])
    if not pdfs:
        fail(422, "UNPROCESSABLE_ENTITY", f"条目 {item['key']} 没有 PDF 附件")
    att = pdfs[0]
    pdf_path = locate_pdf_file(att)
    if not pdf_path:
        fail(404, "PDF_NOT_FOUND",
             f"在 Zotero 本地存储中找不到附件 {att.get('filename') or att['key']} 的 PDF 文件"
             "（可能未同步或为网页快照）。")

    doc = fitz.open(pdf_path)

    pdf_keys = {p["key"] for p in pdfs}
    raw = [a for a in all_annotations() if a["data"].get("parentItem") in pdf_keys]
    annos = [a["data"] for a in raw]

    def color_to_hex(c):
        c = c.lower().lstrip("#")
        for h, name in COLOR_NAMES.items():
            if name == c:
                return h.lstrip("#")
        return c
    wanted_colors = {color_to_hex(c) for c in args.color}

    def keep(a):
        if args.ann_key and a["key"] not in set(args.ann_key):
            return False
        if args.color:
            col = (a.get("annotationColor") or "").lstrip("#").lower()
            if col not in wanted_colors:
                return False
        return True
    annos = [a for a in annos if keep(a)]

    results = []
    for a in annos:
        pos = a.get("annotationPosition")
        page_label = a.get("annotationPageLabel")
        try:
            info = json.loads(pos) if pos else {}
            page_idx = int(info["pageIndex"])
            rects = info.get("rects", [])
        except (ValueError, KeyError, TypeError):
            info, page_idx, rects = {}, None, []
        if rects and page_idx is not None and page_idx < doc.page_count:
            page = doc[page_idx]
            phrase = exact_phrase(page, rects) or a.get("annotationText") or ""
            anchor = anchor_line_text(page, conv_rect(page, rects[0]))
            sents, tgt, (lo, hi) = context_window(
                page.get_text("text"), phrase, args.before, args.after, anchor
            )
        else:
            phrase = a.get("annotationText") or ""
            sents, tgt, lo, hi, page = None, None, None, None, None
        results.append({
            "key": a["key"],
            "color": a.get("annotationColor"),
            "page": page_label,
            "text": a.get("annotationText"),
            "comment": a.get("annotationComment"),
            "phrase": phrase,
            "page_index": page_idx,
            "sentences": sents,
            "target_idx": tgt,
            "window": (lo, hi) if sents else None,
            "rects": rects,
        })

    cache_dir = resolve_cache_dir(args.cache_dir)
    os.makedirs(cache_dir, exist_ok=True)
    txt_path, pdf_out = None, None
    if args.fulltext:
        txt_path = os.path.join(cache_dir, item["key"] + ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(extract_fulltext(doc))
    if args.export_pdf:
        pdf_out = os.path.join(cache_dir, item["key"] + ".pdf")
        shutil.copy2(pdf_path, pdf_out)

    if args.json:
        print(json.dumps({
            "item": {
                "key": item["key"],
                "title": item.get("title"),
                "creators": creator_string(item),
                "year": item.get("date", ""),
            },
            "pdf_source": pdf_path,
            "exports": {"fulltext_txt": txt_path, "pdf_copy": pdf_out},
            "contexts": results,
        }, ensure_ascii=False, indent=2))
        return

    print("=" * 72)
    print("Title :", item.get("title"))
    print("Author:", creator_string(item))
    print("PDF   :", pdf_path)
    print(f"STATUS: OK | mode=context | item={item['key']} | contexts={len(results)} "
          f"| before={args.before} after={args.after} "
          f"| fulltext_txt={txt_path or 'none'} | pdf_copy={pdf_out or 'none'}")
    print("=" * 72)

    if not args.no_color:
        groups = {}
        for r_ in results:
            groups.setdefault(r_["color"], []).append(r_)
        ordered = sorted(groups.items(), key=lambda kv: (kv[0] != "#ff6666", kv[0] or ""))
        ordered = [(c, rs) for c, rs in ordered if rs]
        for color, rs in ordered:
            print(f"\n### 颜色 {color_name(color)} ({color}) — {len(rs)} 条")
            for r_ in rs:
                print_ctx(r_, args.before, args.after)
    else:
        for r_ in results:
            print_ctx(r_, args.before, args.after)

    if not results:
        print("（无匹配批注）")

    if txt_path:
        print(f"\n全文已导出: {txt_path}")
    if pdf_out:
        print(f"PDF 副本已导出: {pdf_out}（按 item key 命名，可对接 PDF 阅读插件）")


if __name__ == "__main__":
    main()
