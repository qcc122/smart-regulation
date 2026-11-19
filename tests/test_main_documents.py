import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, UploadFile
from app.modules.document.parser import DocumentParseError
from app.modules.document import router as main
from app.modules.document.service import IngestionResult


class FakeSession:
    def __init__(self, record=None):
        self.record = record

    async def get(self, _model, doc_id):
        return self.record if self.record and self.record.doc_id == doc_id else None


class MainDocumentRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_route_uses_shared_pipeline_and_keeps_new_upload(self):
        result = IngestionResult(
            doc_id="abcdef123456",
            source_file="法规.pdf",
            title="法规",
            parent_count=2,
            chunk_count=4,
            created=True,
        )
        with tempfile.TemporaryDirectory() as folder:
            with patch("app.modules.document.router.UPLOAD_DIR", folder), patch(
                "app.modules.document.router.ingest_document", new=AsyncMock(return_value=result)
            ) as ingest, patch("app.modules.document.router.uuid.uuid4", return_value=SimpleNamespace(hex="abcdef1234567890")):
                response = await main.upload_document(
                    UploadFile(filename="法规.pdf", file=BytesIO(b"pdf bytes")),
                    object(),
                    FakeSession(),
                )

            stored_file = Path(folder) / "abcdef123456_法规.pdf"
            self.assertTrue(stored_file.is_file())
            self.assertEqual(stored_file.read_bytes(), b"pdf bytes")
            self.assertEqual(response["data"]["doc_id"], "abcdef123456")
            self.assertEqual(response["data"]["chunk_count"], 4)
            self.assertEqual(ingest.await_args.args[3:], ("abcdef123456", "法规.pdf"))

    async def test_duplicate_upload_removes_temporary_copy_and_returns_existing_id(self):
        result = IngestionResult(
            doc_id="111111111111",
            source_file="已入库.pdf",
            title="已入库",
            parent_count=1,
            chunk_count=2,
            created=False,
        )
        with tempfile.TemporaryDirectory() as folder:
            with patch("app.modules.document.router.UPLOAD_DIR", folder), patch(
                "app.modules.document.router.ingest_document", new=AsyncMock(return_value=result)
            ):
                response = await main.upload_document(
                    UploadFile(filename="重复.pdf", file=BytesIO(b"same bytes")),
                    object(),
                    FakeSession(),
                )

            self.assertEqual(list(Path(folder).iterdir()), [])
            self.assertEqual(response["data"]["doc_id"], "111111111111")
            self.assertEqual(response["message"], "文档已存在")

    async def test_parse_error_removes_upload_and_returns_client_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("app.modules.document.router.UPLOAD_DIR", folder), patch(
                "app.modules.document.router.ingest_document", new=AsyncMock(side_effect=DocumentParseError("MinerU 解析失败"))
            ):
                with self.assertRaises(HTTPException) as raised:
                    await main.upload_document(
                        UploadFile(filename="错误.pdf", file=BytesIO(b"pdf bytes")),
                        object(),
                        FakeSession(),
                    )

            self.assertEqual(raised.exception.status_code, 400)
            self.assertEqual(list(Path(folder).iterdir()), [])

    async def test_delete_route_removes_database_vectors_then_upload_copy(self):
        record = SimpleNamespace(doc_id="abcdef123456", source_file="法规.pdf")
        session = FakeSession(record)
        with tempfile.TemporaryDirectory() as folder:
            uploaded = Path(folder) / "abcdef123456_法规.pdf"
            unrelated = Path(folder) / "abcdef123456_extra.pdf"
            uploaded.write_bytes(b"upload")
            unrelated.write_bytes(b"keep")

            async def delete_data(_session, _milvus, _doc_id):
                self.assertTrue(uploaded.exists())

            with patch("app.modules.document.router.UPLOAD_DIR", folder), patch(
                "app.modules.document.router.delete_document_data", new=AsyncMock(side_effect=delete_data)
            ) as delete_data_mock:
                response = await main.remove_document("abcdef123456", object(), session)

            delete_data_mock.assert_awaited_once_with(session, unittest.mock.ANY, "abcdef123456")
            self.assertEqual(response["message"], "删除成功")
            self.assertFalse(uploaded.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
