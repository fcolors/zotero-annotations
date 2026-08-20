#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""搜索分页回归测试 + PDF Bridge fetch_pdf_bytes 测试。

背景：修复"标题搜索只查前 100 条 / 集合只查前 100 个"的 bug。
回归点：
  1. top_items() 必须分页拉全（第 101 条之后的条目仍可按标题搜到）；
  2. all_collections() 必须分页拉全（第 101 个之后的集合仍能 find_collection）；
  3. normalize() 的 Unicode 破折号/空白归一化、子串匹配语义保持不变；
  4. fetch_pdf_bytes() 走 zotero-pdf-bridge base64 只读通道，校验 %PDF- 头。

不依赖真实 Zotero：全部通过 monkeypatch 模块级 api() / urllib 完成。
"""

import base64
import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKILL1_PATH = os.path.join(
    REPO, "skills", "zotero-annotations", "scripts", "zotero_annotations.py"
)
CLI_PATH = os.path.join(
    REPO, "skills", "zotero-annotations-cli", "scripts", "zotero_annotations_cli.py"
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_items(n, title_fmt="Paper {:03d}", start_key=0):
    """构造 n 个顶层条目的 Local API 返回结构（{"key","version","data"}）。"""
    out = []
    for i in range(n):
        key = f"KEY{start_key + i:04d}"
        out.append(
            {
                "key": key,
                "version": 1,
                "data": {
                    "key": key,
                    "itemType": "journalArticle",
                    "title": title_fmt.format(start_key + i),
                },
            }
        )
    return out


def make_collections(n, name_fmt="Collection {:03d}"):
    out = []
    for i in range(n):
        key = f"COL{i:04d}"
        out.append(
            {
                "key": key,
                "version": 1,
                "data": {"key": key, "name": name_fmt.format(i), "parentCollection": False},
            }
        )
    return out


class PaginationBase(unittest.TestCase):
    """通过 monkeypatch 模块级 api() 模拟 Zotero Local API 的分页响应。"""

    ITEMS = None  # 子类注入
    COLLS = None  # 子类注入

    def fake_api(self, path, params=None):
        params = params or {}
        start = int(params.get("start", 0))
        limit = int(params.get("limit", 100))
        if path == "/api/users/0/items/top":
            return self.ITEMS[start : start + limit]
        if path == "/api/users/0/collections":
            return self.COLLS[start : start + limit]
        raise AssertionError(f"unexpected api path: {path}")

    def run_with_patched_api(self, mod, fn, *args, **kwargs):
        with mock.patch.object(mod, "api", side_effect=self.fake_api):
            return fn(*args, **kwargs)

    def top_items_patched(self, mod):
        """在 api 被 patch 的上下文里调用 top_items()（分页拉全）。"""
        with mock.patch.object(mod, "api", side_effect=self.fake_api):
            return mod.top_items()


class TestSearchBeyondFirstPage(PaginationBase):
    """回归：标题搜索必须能命中第 101 条之后的条目（分页拉全）。"""

    @classmethod
    def setUpClass(cls):
        # 100 个无关条目 + 第 101 个是 Target Paper
        items = make_items(100, "Unrelated {:03d}")
        items.append(
            {
                "key": "KEY9999",
                "version": 1,
                "data": {"key": "KEY9999", "itemType": "journalArticle", "title": "Target Paper"},
            }
        )
        cls.ITEMS = items
        cls.COLLS = make_collections(150)

    def _skill1(self):
        return load_module("zotero_annotations", SKILL1_PATH)

    def _cli(self):
        return load_module("zotero_annotations_cli", CLI_PATH)

    def test_skill1_top_items_paginates_and_finds_101st(self):
        mod = self._skill1()
        found = self.run_with_patched_api(
            mod, mod.find_item_by_title, self.top_items_patched(mod), "target paper"
        )
        self.assertEqual(len(found), 1, "第 101 条 Target Paper 必须能被标题搜到")
        self.assertEqual(found[0]["key"], "KEY9999")

    def test_cli_top_items_paginates_and_finds_101st(self):
        mod = self._cli()
        found = self.run_with_patched_api(
            mod, mod.find_item_by_title, self.top_items_patched(mod), "target paper"
        )
        self.assertEqual(len(found), 1, "CLI 侧第 101 条 Target Paper 必须能被标题搜到")
        self.assertEqual(found[0]["key"], "KEY9999")

    def test_skill1_collection_beyond_100(self):
        mod = self._skill1()
        col = self.run_with_patched_api(mod, mod.find_collection, "collection 101")
        self.assertEqual(col["key"], "COL0101", "第 101 个集合必须能被找到")

    def test_cli_collection_beyond_100(self):
        mod = self._cli()
        col = self.run_with_patched_api(mod, mod.find_collection, "collection 101")
        self.assertEqual(col["key"], "COL0101", "CLI 侧第 101 个集合必须能被找到")


class TestNormalizeSemantics(unittest.TestCase):
    """回归：normalize() 与子串匹配语义不得改变。"""

    def _skill1(self):
        return load_module("zotero_annotations", SKILL1_PATH)

    def _cli(self):
        return load_module("zotero_annotations_cli", CLI_PATH)

    def test_dash_and_whitespace_normalize_unchanged(self):
        for mod in (self._skill1(), self._cli()):
            # Unicode 破折号 -> ASCII 连字符
            self.assertEqual(mod.normalize("Deep\u2014Learning"), "deep-learning")
            # NBSP / 窄空格 / 零宽空格 -> 普通空格并折叠
            self.assertEqual(mod.normalize("A\u00a0B\u2009C\u200bD"), "a b c d")
            # 大小写不敏感
            self.assertEqual(mod.normalize("  Mixed CASE  "), "mixed case")
            # 空输入
            self.assertEqual(mod.normalize(""), "")
            self.assertEqual(mod.normalize(None), "")

    def test_substring_match_unchanged(self):
        mod = self._skill1()
        items = make_items(5, "Attention Is All You Need {:d}")
        # normalize 后 query 是子串即命中（不要求完全相等）
        self.assertEqual(len(mod.find_item_by_title(items, "attention")), 5)
        self.assertEqual(len(mod.find_item_by_title(items, "all you need")), 5)
        self.assertEqual(len(mod.find_item_by_title(items, "nothing here")), 0)


class TestFetchPdfBytes(unittest.TestCase):
    """fetch_pdf_bytes() 走 zotero-pdf-bridge base64 只读通道，校验 %PDF- 头。"""

    def _cli(self):
        return load_module("zotero_annotations_cli", CLI_PATH)

    @staticmethod
    def _fake_resp(body_bytes):
        return mock.MagicMock(
            __enter__=mock.MagicMock(return_value=mock.MagicMock(read=lambda: body_bytes)),
            __exit__=mock.MagicMock(return_value=False),
        )

    def test_valid_pdf_base64(self):
        mod = self._cli()
        pdf = b"%PDF-1.7\n%%EOF\n"
        b64 = base64.b64encode(pdf)
        with mock.patch(
            "urllib.request.urlopen", return_value=self._fake_resp(b64)
        ) as urlopen:
            data = mod.fetch_pdf_bytes("KEY9999")
        self.assertEqual(data, pdf)
        self.assertTrue(data.startswith(b"%PDF-"))
        # 请求的是 bridge 端点
        urlopen.assert_called_once_with(
            mod.BRIDGE_BASE + "/KEY9999", timeout=30
        )

    def test_non_pdf_body_fails_invalid(self):
        mod = self._cli()
        b64 = base64.b64encode(b"not a pdf")
        with mock.patch(
            "urllib.request.urlopen", return_value=self._fake_resp(b64)
        ):
            with self.assertRaises(SystemExit) as cm:
                mod.fetch_pdf_bytes("KEY9999")
        self.assertEqual(cm.exception.code, 1)


class TestStdlibOnlyNoThirdParty(unittest.TestCase):
    """回归：整个 skill 零第三方依赖——没有 PyMuPDF（fitz=None）时，
    元数据模式照常可用，只有上下文模式报 DEPENDENCY_MISSING（不炸机、不半途而废）。"""

    def _cli(self):
        return load_module("zotero_annotations_cli", CLI_PATH)

    def test_import_works_without_fitz(self):
        # 加载即成功：脚本对 pymupdf/fitz 是惰性 try/except，缺库时 fitz=None 而非 ImportError
        mod = self._cli()
        self.assertTrue(hasattr(mod, "fitz"))

    def test_metadata_mode_works_with_fitz_none(self):
        mod = self._cli()
        with mock.patch.object(mod, "fitz", None):
            # 元数据路径用到的纯标准库逻辑不受影响
            items = make_items(3)
            self.assertEqual(len(mod.find_item_by_title(items, "paper")), 3)
            self.assertEqual(mod.normalize("Deep\u2014Learning"), "deep-learning")

    def test_context_mode_requires_dependency_with_install_hint(self):
        # 上下文模式守卫：fitz 缺失 → DEPENDENCY_MISSING（SystemExit=1），
        # 且消息给出 requirements.txt 安装提示，不炸机、不半途而废
        mod = self._cli()
        with mock.patch.object(mod, "fitz", None):
            with mock.patch("sys.stderr", new=io.StringIO()) as err, \
                 self.assertRaises(SystemExit) as cm:
                mod.cmd_context(mock.MagicMock())
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("DEPENDENCY_MISSING", err.getvalue())
        self.assertIn("requirements.txt", err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
