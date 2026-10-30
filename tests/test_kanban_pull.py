"""Jira → Obsidian: reconciliação, JQL e regras de conflito."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import unittest

from board_state import BoardState
from jira_client import IssueSnapshot
from kanban_format import KanbanDocument
from kanban_pull import JiraToKanbanSync, reconcile, squad_jql
from tests.support import temporary_dir

BOARD = "## To Do\n\n- [ ] PROJ-1 — A · Tarefa · @Ana\n\n## Doing\n\n\n## Done\n\n"


def issue(key: str, status: str) -> IssueSnapshot:
    return IssueSnapshot(key=key, status=status, summary=f"Resumo {key}", issue_type="Tarefa", assignee="Ana Lima")


class ReconcileTest(unittest.TestCase):
    def test_moves_adds_and_reports_unmapped(self):
        document = KanbanDocument.parse(BOARD + "- [ ] PROJ-5\n")
        report = reconcile(document, [issue("PROJ-1", "doing"), issue("PROJ-2", "To Do"), issue("PROJ-5", "CANCELADO")])
        self.assertEqual(report.moved, ["PROJ-1"])
        self.assertEqual(report.added, ["PROJ-2"])
        self.assertEqual(report.unmapped, {"PROJ-5": "CANCELADO"})
        self.assertEqual(
            document.cards(), {"PROJ-1": "Doing", "PROJ-2": "To Do", "PROJ-5": "Done"}
        )
        self.assertIn("## Doing\n\n- [ ] PROJ-1 — A · Tarefa · @Ana\n", document.render())

    def test_is_idempotent(self):
        document = KanbanDocument.parse(BOARD)
        issues = [issue("PROJ-1", "Doing")]
        reconcile(document, issues)
        self.assertFalse(reconcile(document, issues).changed)


class SquadJqlTest(unittest.TestCase):
    def test_builds_and_escapes(self):
        self.assertEqual(
            squad_jql("SQD01", ['Ana "A"', "", "Bia"], " resolution is EMPTY "),
            'project = "SQD01" AND statusCategory != Done AND assignee in ("Ana \\"A\\"", "Bia")'
            " AND (resolution is EMPTY)",
        )

    def test_without_assignees(self):
        self.assertEqual(squad_jql("SQD01"), 'project = "SQD01" AND statusCategory != Done')


class FakeSource:
    def __init__(self, issues, on_search=None):
        self.issues = issues
        self.on_search = on_search
        self.queries = []

    def search_issues(self, jql):
        self.queries.append(jql)
        if self.on_search:
            self.on_search()
        return self.issues


class JiraToKanbanSyncTest(unittest.TestCase):
    def setUp(self):
        self.dir = temporary_dir(self)
        self.board = self.dir / "Kanban.md"
        self.board.write_bytes(BOARD.replace("\n", "\r\n").encode("utf-8"))

    def test_updates_board_keeps_crlf_and_records_synced_state(self):
        state = BoardState()
        source = FakeSource([issue("PROJ-1", "Done")])
        JiraToKanbanSync(self.board, source, "project = X", state).sync_once()
        raw = self.board.read_bytes().decode("utf-8")
        self.assertIn("## Done\r\n\r\n- [ ] PROJ-1", raw)
        self.assertNotIn("\n\n", raw.replace("\r\n", ""))
        self.assertEqual(state.synced_content, raw.replace("\r\n", "\n"))
        self.assertEqual(source.queries, ["(project = X) OR key in (PROJ-1) ORDER BY key"])
        self.assertFalse(self.board.with_name("Kanban.md.tmp").exists())

    def test_unchanged_board_is_not_rewritten_but_marked_synced(self):
        state = BoardState()
        before = self.board.stat().st_mtime_ns
        JiraToKanbanSync(self.board, FakeSource([issue("PROJ-1", "To Do")]), "x", state).sync_once()
        self.assertEqual(self.board.stat().st_mtime_ns, before)
        self.assertEqual(state.synced_content, BOARD)

    def test_skips_round_while_local_edit_is_not_pushed(self):
        state = BoardState(synced_content="conteúdo anterior")
        source = FakeSource([issue("PROJ-1", "Done")])
        JiraToKanbanSync(self.board, source, "x", state).sync_once()
        self.assertEqual(source.queries, [])
        self.assertEqual(state.synced_content, "conteúdo anterior")

    def test_does_not_overwrite_edit_made_during_search(self):
        edited = "## To Do\n\n- [ ] PROJ-1 movido pelo usuário\n"
        state = BoardState()
        def edit_board():
            self.board.write_text(edited, encoding="utf-8")

        source = FakeSource([issue("PROJ-1", "Done")], on_search=edit_board)
        JiraToKanbanSync(self.board, source, "x", state).sync_once()
        self.assertEqual(self.board.read_text(encoding="utf-8"), edited)
        self.assertIsNone(state.synced_content)


if __name__ == "__main__":
    unittest.main()
