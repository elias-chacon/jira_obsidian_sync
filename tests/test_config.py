"""Leitura de configuração isolada dos arquivos .env reais."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import unittest
from unittest.mock import patch

from config import ConfigError, JiraSettings, SyncSettings
from tests.support import temporary_dir


class ConfigTest(unittest.TestCase):
    def setUp(self):
        # Os testes não podem depender do .env da máquina.
        self.enterContext(patch("config.load_env"))
        self.board = temporary_dir(self) / "Kanban.md"
        self.board.write_text("## A\n", encoding="utf-8")

    def env(self, **values):
        return patch.dict("os.environ", values, clear=True)

    def test_jira_settings_hide_token_and_parse_tls(self):
        with self.env(JIRA_BASE_URL="https://x", JIRA_EMAIL="a@b.c", JIRA_API_TOKEN="segredo", JIRA_VERIFY_TLS="No"):
            settings = JiraSettings.from_env()
        self.assertFalse(settings.verify_tls)
        self.assertNotIn("segredo", repr(settings))

    def test_missing_variables_are_listed(self):
        with self.env(JIRA_EMAIL="a@b.c"), self.assertRaisesRegex(ConfigError, "JIRA_BASE_URL, JIRA_API_TOKEN"):
            JiraSettings.from_env()

    def test_sync_settings_without_pull(self):
        with self.env(OBSIDIAN_BOARD_FILE=str(self.board)):
            settings = SyncSettings.from_env()
        self.assertFalse(settings.pull_enabled)

    def test_sync_settings_with_pull(self):
        values = {
            "OBSIDIAN_BOARD_FILE": str(self.board),
            "JIRA_PULL_INTERVAL_SECONDS": "60",
            "JIRA_PROJECT_KEY": "SQD01",
            "JIRA_USERS": " Ana Lima ; ;Bia ",
        }
        with self.env(**values):
            settings = SyncSettings.from_env()
        self.assertTrue(settings.pull_enabled)
        self.assertEqual(settings.assignees, ("Ana Lima", "Bia"))

    def test_pull_requires_project_and_valid_interval(self):
        for interval, message in (("60", "JIRA_PROJECT_KEY"), ("1m", "JIRA_PULL_INTERVAL_SECONDS")):
            with self.subTest(interval=interval):
                values = {"OBSIDIAN_BOARD_FILE": str(self.board), "JIRA_PULL_INTERVAL_SECONDS": interval}
                with self.env(**values), self.assertRaisesRegex(ConfigError, message):
                    SyncSettings.from_env()

    def test_missing_board_file(self):
        with self.env(OBSIDIAN_BOARD_FILE=str(self.board.with_name("x.md"))), self.assertRaises(ConfigError):
            SyncSettings.from_env()


if __name__ == "__main__":
    unittest.main()
