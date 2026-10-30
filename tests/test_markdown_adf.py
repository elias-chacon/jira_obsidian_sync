"""Conversão Markdown → ADF."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import time
import unittest

from markdown_adf import to_adf


def text(value, *marks):
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def paragraph(*content):
    return {"type": "paragraph", "content": list(content)}


class ToAdfTest(unittest.TestCase):
    def blocks(self, markdown):
        return to_adf(markdown)["content"]

    def test_document_envelope_and_empty_input(self):
        self.assertEqual(to_adf(""), {"version": 1, "type": "doc", "content": [{"type": "paragraph"}]})

    def test_front_matter_is_dropped(self):
        self.assertEqual(self.blocks("---\ntags: [a]\n---\nTexto"), [paragraph(text("Texto"))])

    def test_heading_and_paragraph_with_line_breaks(self):
        self.assertEqual(
            self.blocks("## Título ##\nlinha 1\r\nlinha 2\n\nnovo"),
            [
                {"type": "heading", "attrs": {"level": 2}, "content": [text("Título")]},
                paragraph(text("linha 1"), {"type": "hardBreak"}, text("linha 2")),
                paragraph(text("novo")),
            ],
        )

    def test_inline_marks(self):
        strong, em, code = {"type": "strong"}, {"type": "em"}, {"type": "code"}
        link = {"type": "link", "attrs": {"href": "https://x.io"}}
        self.assertEqual(
            self.blocks("**neg _it_** `c` [l **b**](https://x.io) [[Nota|alias]] [[Outra]] ~~t~~ snake_case"),
            [
                paragraph(
                    text("neg ", strong), text("it", strong, em), text(" "), text("c", code), text(" "),
                    text("l ", link), text("b", link, strong), text(" alias Outra "),
                    text("t", {"type": "strike"}), text(" snake_case"),
                )
            ],
        )

    def test_code_block_keeps_content_and_language(self):
        self.assertEqual(
            self.blocks("```java\nint x = 1;\n\n**não é markdown**\n```\ndepois"),
            [
                {"type": "codeBlock", "attrs": {"language": "java"},
                 "content": [text("int x = 1;\n\n**não é markdown**")]},
                paragraph(text("depois")),
            ],
        )

    def test_nested_lists_checkbox_and_continuation(self):
        def item(*content):
            return {"type": "listItem", "content": list(content)}

        self.assertEqual(
            self.blocks("- [ ] a\n  continua\n  1. x\n  2. y\n\n- [x] b\n\n3. z"),
            [
                {"type": "bulletList", "content": [
                    item(
                        paragraph(text("☐ a"), {"type": "hardBreak"}, text("continua")),
                        {"type": "orderedList", "attrs": {"order": 1},
                         "content": [item(paragraph(text("x"))), item(paragraph(text("y")))]},
                    ),
                    item(paragraph(text("☑ b"))),
                ]},
                {"type": "orderedList", "attrs": {"order": 3}, "content": [item(paragraph(text("z")))]},
            ],
        )

    def test_quote_rule_and_table(self):
        self.assertEqual(
            self.blocks("> # T\n> q\n\n---\n| a | b |\n|---|---|\n| 1 | 2 |"),
            [
                {"type": "blockquote", "content": [paragraph(text("T")), paragraph(text("q"))]},
                {"type": "rule"},
                {"type": "codeBlock", "content": [text("| a | b |\n|---|---|\n| 1 | 2 |")]},
            ],
        )


class BacktrackingRegressionTest(unittest.TestCase):
    """Linhas patológicas que levavam os padrões antigos a tempo quadrático ou cúbico."""

    def test_long_whitespace_runs_convert_in_linear_time(self):
        spaces = " " * 20_000
        for line in (f"# a{spaces}b", f"```{spaces}a b", f"-{spaces}", f"- -{spaces}x", f">{spaces}x"):
            with self.subTest(line=line[:6]):
                started = time.perf_counter()
                to_adf(line)
                self.assertLess(time.perf_counter() - started, 0.5)

    def test_heading_closing_hashes(self):
        cases = {"# T #": "T", "# T#": "T#", "# C# ##": "C#", "# ##": "", "# a   b  ": "a   b"}
        for markdown, expected in cases.items():
            with self.subTest(markdown=markdown):
                content = self.heading_content(markdown)
                self.assertEqual("".join(node["text"] for node in content), expected)

    @staticmethod
    def heading_content(markdown):
        return to_adf(markdown)["content"][0].get("content", [])


if __name__ == "__main__":
    unittest.main()
