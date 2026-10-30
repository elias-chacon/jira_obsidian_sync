"""Leitura, edição e regravação do board Markdown."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import time
import unittest

from kanban_format import KanbanDocument, card_key, format_card

BOARD = """---
kanban-plugin: board
---

## To Do

- [ ] PROJ-1 — Primeira [SR-99] · Tarefa · @Ana
- [ ] PROJ-2 — Multilinha · Tarefa · @Bia
  continuação do cartão
- [ ] nota livre sem chave

## Done



%% kanban:settings
```
{"kanban-plugin":"board"}
```
%%
"""


class KanbanDocumentTest(unittest.TestCase):
    def test_render_preserves_untouched_board(self):
        self.assertEqual(KanbanDocument.parse(BOARD).render(), BOARD)

    def test_cards_maps_first_key_of_line_to_column(self):
        self.assertEqual(KanbanDocument.parse(BOARD).cards(), {"PROJ-1": "To Do", "PROJ-2": "To Do"})

    def test_duplicate_card_is_rejected(self):
        with self.assertRaises(ValueError):
            KanbanDocument.parse("## A\n- PROJ-1\n## B\n- PROJ-1\n")

    def test_move_carries_continuation_lines(self):
        document = KanbanDocument.parse(BOARD)
        document.move_card("PROJ-2", "Done")
        rendered = document.render()
        self.assertIn("## Done\n\n- [ ] PROJ-2 — Multilinha · Tarefa · @Bia\n  continuação do cartão\n", rendered)
        self.assertNotIn("continuação do cartão\n- [ ] nota", rendered)

    def test_add_goes_after_last_card(self):
        document = KanbanDocument.parse(BOARD)
        document.add_card("PROJ-3", "- [ ] PROJ-3", "to do")
        self.assertIn("  continuação do cartão\n- [ ] PROJ-3\n- [ ] nota livre", document.render())

    def test_add_rejects_existing_key_and_unknown_column(self):
        document = KanbanDocument.parse(BOARD)
        with self.assertRaises(ValueError):
            document.add_card("PROJ-1", "- PROJ-1", "Done")
        with self.assertRaises(KeyError):
            document.add_card("PROJ-9", "- PROJ-9", "Inexistente")

    def test_column_for_ignores_case(self):
        self.assertEqual(KanbanDocument.parse(BOARD).column_for("DONE"), "Done")
        self.assertIsNone(KanbanDocument.parse(BOARD).column_for("CANCELADO"))


class CardTest(unittest.TestCase):
    def test_format_card_puts_key_first(self):
        line = format_card("PROJ-7", " [SR-1] Resumo ", "Tarefa", "Elias Alves")
        self.assertEqual(line, "- [ ] PROJ-7 — [SR-1] Resumo · Tarefa · @Elias")
        self.assertEqual(card_key(line), "PROJ-7")

    def test_format_card_without_assignee(self):
        self.assertTrue(format_card("PROJ-7", "x", "Bug", None).endswith("@-"))

    def test_card_key_requires_list_item(self):
        self.assertIsNone(card_key("PROJ-1 fora de lista"))

    def test_card_key_boundaries(self):
        self.assertEqual(card_key("- 9SQD01-3 [SR-1] SQD01-42"), "SR-1")
        self.assertEqual(card_key("- SQD01-42x"), "SQD01-42")


class BacktrackingRegressionTest(unittest.TestCase):
    def test_long_lines_parse_in_linear_time(self):
        long_run = "A" * 50_000
        for markdown in (f"## a{' ' * 50_000}b", f"## X\n- {long_run}", f"## X\n- {long_run}-"):
            with self.subTest(markdown=markdown[:8]):
                started = time.perf_counter()
                KanbanDocument.parse(markdown)
                self.assertLess(time.perf_counter() - started, 0.5)


if __name__ == "__main__":
    unittest.main()
