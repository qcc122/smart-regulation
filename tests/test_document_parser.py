import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from pydantic import SecretStr

from app.modules.document.parser import DocumentParseError, _extract_with_mineru, parse_document


class DocumentParserTests(unittest.TestCase):
    def make_file(self, folder, name, data=b"source"):
        path = Path(folder) / name
        path.write_bytes(data)
        return path

    def make_settings(self):
        return SimpleNamespace(mineru_token=SecretStr("mineru-token"))

    def test_parse_document_returns_markdown_from_precision_extract(self):
        markdown = "# 第一章 总则\n\n第一条 建设单位应当保存施工资料。"
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_file(folder, "law.pdf")
            with (
                patch("app.modules.document.parser.get_settings", return_value=self.make_settings()),
                patch("app.modules.document.parser._extract_with_mineru", return_value=markdown) as extract,
            ):
                parsed = parse_document(path, source_file="law.pdf")

        self.assertEqual(parsed, markdown)
        self.assertEqual(extract.call_args.args, (path, "mineru-token"))

    def test_sdk_client_receives_token_and_uses_extract_markdown_property(self):
        seen = {}

        class FakeResult:
            markdown = "# 已提取的 Markdown"

        class FakeClient:
            def __init__(self, token):
                seen["token"] = token

            def __enter__(self):
                return self

            def __exit__(self, *_):
                seen["closed"] = True

            def extract(self, path):
                seen["path"] = path
                return FakeResult()

        fake_module = types.ModuleType("mineru")
        fake_module.MinerU = FakeClient
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_file(folder, "law.pdf")
            with patch.dict(sys.modules, {"mineru": fake_module}):
                markdown = _extract_with_mineru(path, "mineru-token")

        self.assertEqual(markdown, "# 已提取的 Markdown")
        self.assertEqual(seen, {"token": "mineru-token", "path": str(path), "closed": True})

    def test_unsupported_missing_and_empty_files_fail_clearly(self):
        with self.assertRaisesRegex(DocumentParseError, "仅支持 PDF/DOCX"):
            parse_document("rules.txt")
        with self.assertRaisesRegex(DocumentParseError, "源文件不存在"):
            parse_document("missing.pdf")

        with tempfile.TemporaryDirectory() as folder:
            path = self.make_file(folder, "empty.pdf", b"")
            with self.assertRaisesRegex(DocumentParseError, "源文件为空"):
                parse_document(path)

            path = self.make_file(folder, "blank.pdf")
            with (
                patch("app.modules.document.parser.get_settings", return_value=self.make_settings()),
                patch("app.modules.document.parser._extract_with_mineru", return_value="  \n"),
            ):
                with self.assertRaisesRegex(DocumentParseError, "未提取到 Markdown"):
                    parse_document(path)

    def test_mineru_failure_is_wrapped_without_internal_details(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_file(folder, "broken.pdf")
            with (
                patch("app.modules.document.parser.get_settings", return_value=self.make_settings()),
                patch("app.modules.document.parser._extract_with_mineru", side_effect=RuntimeError("private detail")),
            ):
                with self.assertRaisesRegex(DocumentParseError, "broken.pdf") as raised:
                    parse_document(path, source_file=r"C:\fakepath\broken.pdf")

        self.assertNotIn("private detail", str(raised.exception))

    def test_network_failure_logs_host_without_signed_url_or_token(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_file(folder, "law.pdf")
            error = httpx.ConnectError("private", request=httpx.Request(
                "GET", "https://download.example/result.zip?token=secret"
            ))
            with (
                patch("app.modules.document.parser.get_settings", return_value=self.make_settings()),
                patch("app.modules.document.parser._extract_with_mineru", side_effect=error),
                self.assertLogs("app.modules.document.parser", level="ERROR") as logs,
            ):
                with self.assertRaises(DocumentParseError):
                    parse_document(path)
        self.assertIn("target_host=download.example", logs.output[0])
        self.assertNotIn("secret", logs.output[0])


if __name__ == "__main__":
    unittest.main()
