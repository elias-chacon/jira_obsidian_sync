"""Notas da task e publicação de comentários na transição."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import unittest

from jira_client import JiraComment
from markdown_adf import to_adf
from task_comments import PROPERTY_KEY, NoteFile, TaskNotes, TransitionCommenter
from tests.support import temporary_dir


class FakeJira:
    def __init__(self, comments=()):
        self.comments = list(comments)
        self.added = []
        self.updated = []

    def list_comments(self, _issue_key):
        return self.comments

    def add_comment(self, issue_key, body, properties=None):
        self.added.append((issue_key, body, properties))
        return str(len(self.added))

    def update_comment(self, issue_key, comment_id, body, properties):
        self.updated.append((issue_key, comment_id, body, properties))


class FakePrompt:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def ask(self, issue_key, status):
        self.calls.append((issue_key, status))
        return self.answer


def marker(note):
    return {PROPERTY_KEY: {"file": note.name, "sha256": note.digest}}


class TaskNotesTest(unittest.TestCase):
    def setUp(self):
        self.dir = temporary_dir(self)
        self.root = self.dir

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_finds_markdown_in_creation_order_and_skips_empty(self):
        self.write("PFN/AB-1/z-analise.md", "análise")
        self.write("PFN/AB-1/a-resumo.md", "resumo")
        self.write("PFN/AB-1/vazio.md", "  \n")
        self.write("PFN/AB-1/anexo.txt", "ignorado")
        self.write("PFN/AB-12/outra.md", "outra task")
        notes = TaskNotes(self.root).find("AB-1")
        # Arquivos gravados em sequência: a ordem de criação é a ordem de escrita.
        self.assertEqual([n.name for n in notes], ["z-analise.md", "a-resumo.md"])

    def test_missing_folder_returns_no_notes(self):
        self.assertEqual(TaskNotes(self.root).find("AB-1"), [])

    def test_same_key_in_two_projects_is_ambiguous(self):
        self.write("PFN/AB-1/a.md", "x")
        self.write("DFC/AB-1/b.md", "y")
        notes = TaskNotes(self.root)
        with self.assertRaises(ValueError):
            notes.find("AB-1")


class StubNotes:
    def __init__(self, notes):
        self.notes = notes

    def find(self, _issue_key):
        return self.notes


class TransitionCommenterTest(unittest.TestCase):
    def test_creates_missing_updates_changed_and_skips_unchanged(self):
        new, same, edited = NoteFile("novo.md", "# Novo"), NoteFile("igual.md", "igual"), NoteFile("editado.md", "v2")
        jira = FakeJira([
            JiraComment("10", marker(same)),
            JiraComment("11", {PROPERTY_KEY: {"file": "editado.md", "sha256": "hash-antigo"}}),
            JiraComment("12", {}),  # comentário manual: ignorado
        ])
        TransitionCommenter(StubNotes([new, same, edited]), jira, FakePrompt("não usado"))("AB-1", "Done")
        self.assertEqual(jira.added, [("AB-1", to_adf("# Novo"), marker(new))])
        self.assertEqual(jira.updated, [("AB-1", "11", to_adf("v2"), marker(edited))])

    def test_without_notes_asks_and_posts_typed_comment(self):
        jira, prompt = FakeJira(), FakePrompt("**ok**")
        TransitionCommenter(StubNotes([]), jira, prompt)("AB-1", "Done")
        self.assertEqual(prompt.calls, [("AB-1", "Done")])
        self.assertEqual(jira.added, [("AB-1", to_adf("**ok**"), None)])

    def test_cancelled_or_blank_prompt_posts_nothing(self):
        for answer in (None, "   "):
            jira = FakeJira()
            TransitionCommenter(StubNotes([]), jira, FakePrompt(answer))("AB-1", "Done")
            self.assertEqual(jira.added, [])

    def test_non_interactive_mode_does_not_prompt(self):
        jira = FakeJira()
        TransitionCommenter(StubNotes([]), jira, None)("AB-1", "Done")
        self.assertEqual(jira.added, [])


if __name__ == "__main__":
    unittest.main()
