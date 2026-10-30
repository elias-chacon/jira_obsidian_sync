"""Obsidian → Jira: envio só de cartões movidos e gancho de comentário."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import unittest

from board_state import BoardState
from board_sync import BoardSynchronizer
from jira_client import JiraError
from tests.support import temporary_dir


class FakeJira:
    def __init__(self, already_in_status=(), failing=()):
        self.transitions = []
        self.already_in_status = set(already_in_status)
        self.failing = set(failing)

    def transition_to_status(self, key, status):
        if key in self.failing:
            raise JiraError("recusada")
        self.transitions.append((key, status))
        return key not in self.already_in_status


class BoardSynchronizerTest(unittest.TestCase):
    def setUp(self):
        self.dir = temporary_dir(self)
        self.board = self.dir / "Kanban.md"
        self.jira = FakeJira()

    def sync(self, content, state, on_transition=None):
        self.board.write_text(content, encoding="utf-8")
        BoardSynchronizer(self.board, self.jira, 0, state, on_transition).sync_once()

    def test_on_transition_only_for_effective_transitions_and_errors_are_isolated(self):
        self.jira = FakeJira(already_in_status={"AB-2"}, failing={"AB-3"})
        calls = []

        def on_transition(key, status):
            calls.append((key, status))
            raise OSError("pasta inacessível")

        with self.assertLogs("board_sync", "ERROR") as logs:
            self.sync("## A\n- AB-1\n- AB-2\n- AB-3\n- AB-4\n", BoardState(), on_transition)
        self.assertEqual(calls, [("AB-1", "A"), ("AB-4", "A")])
        self.assertEqual(len(logs.records), 3)  # AB-3 recusada; comentário de AB-1 e AB-4 falhou

    def test_on_transition_runs_after_releasing_board_lock(self):
        state = BoardState()
        lock_held = []
        self.sync("## A\n- AB-1\n", state, lambda *_: lock_held.append(state.lock.locked()))
        self.assertEqual(lock_held, [False])

    def test_first_run_pushes_every_card(self):
        self.sync("## A\n- AB-1\n## B\n- AB-2\n", BoardState())
        self.assertEqual(self.jira.transitions, [("AB-1", "A"), ("AB-2", "B")])

    def test_pushes_only_cards_moved_since_synced_state(self):
        state = BoardState(synced_content="## A\n- AB-1\n- AB-2\n## B\n")
        self.sync("## A\n- AB-1\n## B\n- AB-2\n", state)
        self.assertEqual(self.jira.transitions, [("AB-2", "B")])
        self.assertEqual(state.synced_content, "## A\n- AB-1\n## B\n- AB-2\n")

    def test_synced_content_is_not_pushed_again(self):
        content = "## A\n- AB-1\n"
        self.sync(content, BoardState(synced_content=content))
        self.assertEqual(self.jira.transitions, [])

    def test_invalid_board_keeps_previous_synced_state(self):
        state = BoardState(synced_content="## A\n- AB-1\n")
        with self.assertRaises(ValueError):
            self.sync("## A\n- AB-1\n## B\n- AB-1\n", state)
        self.assertEqual(state.synced_content, "## A\n- AB-1\n")


if __name__ == "__main__":
    unittest.main()
