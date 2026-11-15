import io
import os
import threading
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.classification import _classification_concurrency, router
from app.api.dependencies import authorize


class ClassificationApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[authorize] = lambda: None
        self.client = TestClient(app)

    def test_invalid_uploads_are_rejected_before_inspection(self):
        with patch("app.api.classification.classifier.classify_document") as classify:
            for name, content, status in (("x.exe", b"x", 415), ("x.pdf", b"", 422)):
                with self.subTest(name=name):
                    response = self.client.post("/api/v1/classify", files={"file": (name, content)})
                    self.assertEqual(response.status_code, status)
            with patch("app.api.classification.MAX_FILE", 4):
                response = self.client.post("/api/v1/classify", files={"file": ("x.pdf", b"12345")})
                self.assertEqual(response.status_code, 413)
            classify.assert_not_called()

    def test_file_bytes_reach_inspector_and_batch_has_same_policy(self):
        result = {"category": "unknown", "layer": 0, "confidence": 0, "reason": "Periksa"}
        with patch(
            "app.api.classification.classifier.classify_document", return_value=result
        ) as classify:
            response = self.client.post(
                "/api/v1/classify", files={"file": ("Program Proteksi.pdf", b"content")}
            )
            self.assertEqual(response.json(), result)
            classify.assert_called_with("Program Proteksi.pdf", b"content")
            response = self.client.post(
                "/api/v1/classify-batch", files=[("files", ("scan.pdf", b"content"))]
            )
            self.assertEqual(response.json(), {"results": [result]})

    def test_batch_limit(self):
        with patch("app.api.classification.MAX_DOCS", 1):
            response = self.client.post(
                "/api/v1/classify-batch",
                files=[("files", ("a.pdf", b"a")), ("files", ("b.pdf", b"b"))],
            )
        self.assertEqual(response.status_code, 413)

    def test_cpu_inspection_runs_outside_event_loop_thread(self):
        import asyncio
        from fastapi import UploadFile
        from app.api.classification import inspect_file

        async def exercise():
            loop_thread = threading.get_ident()
            with patch(
                "app.api.classification.classifier.classify_document",
                side_effect=lambda *args: threading.get_ident(),
            ):
                worker_thread = await inspect_file(
                    UploadFile(filename="scan.pdf", file=io.BytesIO(b"data"))
                )
            self.assertNotEqual(loop_thread, worker_thread)

        asyncio.run(exercise())

    def test_classification_concurrency_env_validation(self):
        env_without_concurrency = {
            k: v for k, v in os.environ.items() if k != "BAPETEN_CLASSIFY_CONCURRENCY"
        }
        with patch.dict(os.environ, env_without_concurrency, clear=True):
            self.assertEqual(_classification_concurrency(), 2)
        for value, expected in (("1", 1), ("6", 6), ("16", 16)):
            with patch.dict(os.environ, {"BAPETEN_CLASSIFY_CONCURRENCY": value}):
                self.assertEqual(_classification_concurrency(), expected)
        for invalid in ("0", "-1", "17", "invalid"):
            with patch.dict(os.environ, {"BAPETEN_CLASSIFY_CONCURRENCY": invalid}):
                with self.assertRaises(ValueError):
                    _classification_concurrency()
