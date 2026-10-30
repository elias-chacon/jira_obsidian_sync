"""Lançamento da janela de comentário em processo separado (subprocess simulado; a janela Tk não é aberta)."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import subprocess
import unittest
from unittest.mock import patch

from comment_dialog import TkCommentPrompt


class TkCommentPromptTest(unittest.TestCase):
    def setUp(self):
        self.run = self.enterContext(patch("comment_dialog.subprocess.run"))

    def answer(self, returncode, stdout=b"", stderr=b""):
        self.run.return_value = subprocess.CompletedProcess([], returncode, stdout, stderr)
        return TkCommentPrompt(timeout_seconds=5).ask("AB-1", "Done")

    def test_returns_typed_text_decoded_as_utf8(self):
        self.assertEqual(self.answer(0, "**ação**".encode()), "**ação**")
        args, kwargs = self.run.call_args
        self.assertEqual(args[0][-2:], ["AB-1", "Done"])
        self.assertEqual(kwargs["timeout"], 5)
        self.assertEqual(kwargs["env"]["PYTHONIOENCODING"], "utf-8")

    def test_cancel_returns_none_silently(self):
        with self.assertNoLogs("comment_dialog"):
            self.assertIsNone(self.answer(1))

    def test_crash_is_logged(self):
        with self.assertLogs("comment_dialog", "ERROR"):
            self.assertIsNone(self.answer(1, stderr=b"Traceback: TclError"))

    def test_timeout_returns_none(self):
        self.run.side_effect = subprocess.TimeoutExpired("python", 5)
        with self.assertLogs("comment_dialog", "WARNING"):
            self.assertIsNone(TkCommentPrompt(timeout_seconds=5).ask("AB-1", "Done"))


if __name__ == "__main__":
    unittest.main()
