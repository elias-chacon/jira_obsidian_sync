"""Composição e ciclo de vida do sincronizador."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import unittest
from unittest.mock import MagicMock, call, patch

import service
from config import SyncSettings
from kanban_pull import JiraToKanbanSync
from tests.support import temporary_dir


class SyncServiceTest(unittest.TestCase):
    def test_start_applies_jira_before_watching_and_stop_reverses(self):
        events = MagicMock()
        sync = service.SyncService(events.watcher, events.pull, 60)
        sync.poller = events.poller
        sync.start()
        sync.stop()
        # Ignora __bool__ registrado pelos `if self.pull` / `if self.poller`.
        operations = [c for c in events.mock_calls if not c[0].endswith("__")]
        self.assertEqual(
            operations,
            [call.pull.sync_once(), call.watcher.start(), call.poller.start(), call.poller.stop(), call.watcher.stop()],
        )

    def test_lock_is_taken_first_and_released_on_stop(self):
        events = MagicMock()
        sync = service.SyncService(events.watcher, events.pull, 60, events.lock)
        sync.poller = events.poller
        sync.start()
        sync.stop()
        operations = [c for c in events.mock_calls if not c[0].endswith("__")]
        self.assertEqual(operations[0], call.lock.acquire())
        self.assertEqual(operations[-1], call.lock.release())

    def test_failed_start_releases_lock_and_reraises(self):
        events = MagicMock()
        events.pull.sync_once.side_effect = RuntimeError("Jira fora do ar")
        sync = service.SyncService(events.watcher, events.pull, 60, events.lock)
        with self.assertRaisesRegex(RuntimeError, "Jira fora do ar"):
            sync.start()
        events.lock.release.assert_called_once_with()
        events.watcher.start.assert_not_called()

    def test_already_running_instance_does_not_touch_jira(self):
        events = MagicMock()
        events.lock.acquire.side_effect = service.AlreadyRunningError("Outra instância já está rodando")
        sync = service.SyncService(events.watcher, events.pull, 60, events.lock)
        with self.assertRaises(service.AlreadyRunningError):
            sync.start()
        events.pull.sync_once.assert_not_called()

    def test_without_pull_only_watches(self):
        watcher = MagicMock()
        sync = service.SyncService(watcher, None, 0)
        sync.start()
        sync.stop()
        self.assertIsNone(sync.poller)
        self.assertEqual(watcher.mock_calls, [call.start(), call.stop()])


class BuildServiceTest(unittest.TestCase):
    def setUp(self):
        self.board = temporary_dir(self) / "Kanban.md"
        self.board.write_text("## A\n", encoding="utf-8")
        jira_settings = self.enterContext(patch.object(service.JiraSettings, "from_env"))
        self.jira = jira_settings.return_value.client.return_value
        self.sync_settings = self.enterContext(patch.object(service.SyncSettings, "from_env"))

    def build(self, interactive=True, **settings):
        self.sync_settings.return_value = SyncSettings(board_file=self.board, **settings)
        return service.build_service(interactive)

    def commenter(self, sync):
        return sync.watcher.synchronizer.on_transition

    def test_pull_disabled(self):
        sync = self.build()
        self.assertIsNone(sync.pull)
        self.assertIs(sync.watcher.synchronizer.jira, self.jira)

    def test_pull_enabled_shares_state_and_builds_squad_jql(self):
        sync = self.build(pull_interval_seconds=30, project_key="SQD01", assignees=("Ana",))
        self.assertIsInstance(sync.pull, JiraToKanbanSync)
        self.assertIs(sync.pull.state, sync.watcher.synchronizer.state)
        self.assertEqual(sync.pull.base_jql, 'project = "SQD01" AND statusCategory != Done AND assignee in ("Ana")')

    def test_task_notes_live_next_to_board_and_prompt_depends_on_mode(self):
        self.assertEqual(self.commenter(self.build()).notes.root, self.board.parent)
        self.assertIsNotNone(self.commenter(self.build()).prompt)
        self.assertIsNone(self.commenter(self.build(interactive=False)).prompt)


if __name__ == "__main__":
    unittest.main()
