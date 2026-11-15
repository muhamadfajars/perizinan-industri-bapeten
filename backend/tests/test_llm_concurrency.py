import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.protection import llm


class ConcurrencyTests(unittest.TestCase):
    def child(self, root, limit):
        script = """from pathlib import Path
from app.protection import llm
import sys
llm.storage.ROOT = Path(sys.argv[1])
try:
    with llm.request_slot(wait_seconds=0):
        print("acquired")
except RuntimeError:
    print("full")
"""
        env = {**os.environ, "BAPETEN_LLM_MAX_CONCURRENT": str(limit)}
        return subprocess.check_output(
            [sys.executable, "-c", script, str(root)], env=env, text=True
        ).strip()

    def test_limits_apply_across_processes_and_release_after_exception(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(llm.storage, "ROOT", Path(tmp)):
            for limit in (1, 2):
                with (
                    self.subTest(limit=limit),
                    patch.dict(os.environ, {"BAPETEN_LLM_MAX_CONCURRENT": str(limit)}),
                ):
                    with llm.request_slot(wait_seconds=0):
                        self.assertEqual(
                            self.child(tmp, limit), "full" if limit == 1 else "acquired"
                        )
                        if limit == 2:
                            with llm.request_slot(wait_seconds=0):
                                self.assertEqual(self.child(tmp, limit), "full")
                    self.assertEqual(self.child(tmp, limit), "acquired")
            with patch.dict(os.environ, {"BAPETEN_LLM_MAX_CONCURRENT": "1"}):
                with self.assertRaises(ValueError):
                    with llm.request_slot(wait_seconds=0):
                        raise ValueError("request failed")
                self.assertEqual(self.child(tmp, 1), "acquired")

    def test_invalid_limit_is_rejected(self):
        for value in ("0", "-1", "5", "invalid"):
            with patch.dict(os.environ, {"BAPETEN_LLM_MAX_CONCURRENT": value}):
                with self.assertRaises(ValueError):
                    with llm.request_slot(wait_seconds=0):
                        self.fail("Invalid limit accepted")

    def test_queue_wait_from_env_and_timeout_message(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(llm.storage, "ROOT", Path(tmp)):
            with patch.dict(os.environ, {"BAPETEN_LLM_MAX_CONCURRENT": "1"}):
                with llm.request_slot(wait_seconds=0):
                    env_without_wait = {
                        k: v for k, v in os.environ.items() if k != "BAPETEN_LLM_QUEUE_WAIT"
                    }
                    with (
                        patch.dict(os.environ, env_without_wait, clear=True),
                        patch(
                            "app.protection.llm.time.monotonic", side_effect=[100.0, 279.9, 280.0]
                        ),
                        patch("app.protection.llm.time.sleep") as sleep_mock,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError, r"Antrean Qwen penuh setelah menunggu 180 detik"
                        ):
                            with llm.request_slot():
                                self.fail("Slot acquired while already locked")
                        sleep_mock.assert_called_once_with(0.2)

                    with (
                        patch.dict(os.environ, {"BAPETEN_LLM_QUEUE_WAIT": "45"}),
                        patch("app.protection.llm.time.monotonic", side_effect=[10.0, 54.9, 55.0]),
                        patch("app.protection.llm.time.sleep") as sleep_mock,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError, r"Antrean Qwen penuh setelah menunggu 45 detik"
                        ):
                            with llm.request_slot():
                                self.fail("Slot acquired while already locked")
                        sleep_mock.assert_called_once_with(0.2)

                    with patch.dict(os.environ, {"BAPETEN_LLM_QUEUE_WAIT": "0"}):
                        with self.assertRaisesRegex(
                            RuntimeError, r"Antrean Qwen penuh setelah menunggu 0 detik"
                        ):
                            with llm.request_slot():
                                self.fail("Slot acquired while already locked")

    def test_invalid_queue_wait_is_rejected(self):
        for value in ("-1", "invalid"):
            with patch.dict(os.environ, {"BAPETEN_LLM_QUEUE_WAIT": value}):
                with self.assertRaises(ValueError):
                    with llm.request_slot():
                        self.fail("Invalid queue wait accepted")
