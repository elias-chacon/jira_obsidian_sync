"""Conversão de Markdown (subconjunto usado nas notas Obsidian) para Atlassian Document Format.

Suportado: front matter (descartado), títulos, parágrafos, listas com e sem ordem (aninhadas por
indentação, checkboxes viram ☐/☑), blocos de código, citações, linha horizontal, negrito, itálico,
tachado, código inline, links e wikilinks. Tabelas viram bloco de código para manter o alinhamento.

Os padrões de bloco evitam quantificadores adjacentes que casem o mesmo caractere: com eles, uma linha
longa de espaços leva o motor de regex a backtracking polinomial (ver tests/test_markdown_adf.py).
"""
from __future__ import annotations

import re
from typing import Any

Node = dict[str, Any]

_FRONT_MATTER = re.compile(r"\A---\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_FENCE = re.compile(r"^[ \t]*(```|~~~)[ \t]*(?:([\w+-]+)[ \t]*)?$")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(\S.*)?$")
_RULE = re.compile(r"^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_QUOTE = re.compile(r"^[ \t]*> ?(.*)$")
_LIST_ITEM = re.compile(r"^([ \t]*)([-*+]|\d+[.)])[ \t]+(\S.*)?$")
_TABLE_ROW = re.compile(r"^[ \t]*\|")
_CHECKBOX = re.compile(r"^\[([ xX])\][ \t]+")
_INLINE = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\[\[(?P<wiki>[^\]|]+)(?:\|(?P<wiki_alias>[^\]]+))?\]\]"
    r"|\[(?P<link_text>[^\]]+)\]\((?P<link_url>[^)\s]+)\)"
    r"|\*\*(?P<strong>.+?)\*\*|__(?P<strong_alt>.+?)__"
    r"|~~(?P<strike>.+?)~~"
    r"|(?<![\w*])\*(?P<em>[^*\s](?:.*?[^*\s])?)\*(?!\w)"
    r"|(?<!\w)_(?P<em_alt>[^_\s](?:.*?[^_\s])?)_(?!\w)"
)
# Grupo nomeado do _INLINE → marca ADF.
_EMPHASIS_GROUPS = (
    ("strong", "strong"), ("strong_alt", "strong"), ("strike", "strike"), ("em", "em"), ("em_alt", "em")
)


def to_adf(markdown: str) -> Node:
    """Documento ADF (`version`/`type: doc`) pronto para o corpo de um comentário Jira."""
    text = _FRONT_MATTER.sub("", markdown.replace("\r\n", "\n"), count=1)
    content = _blocks(text.expandtabs(4).split("\n"))
    return {"version": 1, "type": "doc", "content": content or [{"type": "paragraph"}]}


def _blocks(lines: list[str]) -> list[Node]:
    nodes: list[Node] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif fence := _FENCE.match(line):
            i = _code_block(lines, i, fence, nodes)
        elif heading := _HEADING.match(line):
            level = len(heading.group(1))
            nodes.append({"type": "heading", "attrs": {"level": level}, "content": _inline(_heading_text(heading))})
            i += 1
        elif _RULE.match(line):
            nodes.append({"type": "rule"})
            i += 1
        elif _QUOTE.match(line):
            i = _blockquote(lines, i, nodes)
        elif item := _LIST_ITEM.match(line):
            node, i = _list(lines, i, len(item.group(1)))
            nodes.append(node)
        elif _TABLE_ROW.match(line):
            end = _advance_while(lines, i, lambda text: bool(_TABLE_ROW.match(text)))
            nodes.append(_code("\n".join(lines[i:end]).strip(), None))
            i = end
        else:
            end = _advance_while(lines, i, lambda text: bool(text.strip()) and not _starts_block(text))
            nodes.append(_paragraph(lines[i:end]))
            i = end
    return nodes


def _heading_text(heading: re.Match[str]) -> str:
    """Texto do título sem a sequência opcional de `#` de fechamento (`## Título ##`)."""
    text = (heading.group(2) or "").rstrip()
    without_closing = text.rstrip("#")
    if without_closing != text and (not without_closing or without_closing[-1] in " \t"):
        return without_closing.rstrip()
    return text


def _starts_block(line: str) -> bool:
    return any(p.match(line) for p in (_FENCE, _HEADING, _RULE, _QUOTE, _LIST_ITEM, _TABLE_ROW))


def _advance_while(lines: list[str], start: int, predicate) -> int:
    end = start + 1
    while end < len(lines) and predicate(lines[end]):
        end += 1
    return end


def _code_block(lines: list[str], start: int, fence: re.Match[str], nodes: list[Node]) -> int:
    end = _advance_while(lines, start, lambda text: not text.strip().startswith(fence.group(1)))
    nodes.append(_code("\n".join(lines[start + 1 : end]), fence.group(2)))
    return end + 1  # pula a cerca de fechamento (ou o fim do arquivo)


def _blockquote(lines: list[str], start: int, nodes: list[Node]) -> int:
    end = _advance_while(lines, start, lambda text: bool(_QUOTE.match(text)))
    inner = _blocks([_QUOTE.match(text).group(1) for text in lines[start:end]])
    # Citação no ADF não aceita título: vira parágrafo com o mesmo conteúdo.
    content = [{"type": "paragraph", "content": n["content"]} if n["type"] == "heading" else n for n in inner]
    if content:
        nodes.append({"type": "blockquote", "content": content})
    return end


def _list(lines: list[str], start: int, indent: int) -> tuple[Node, int]:
    marker = _LIST_ITEM.match(lines[start]).group(2)
    ordered = marker[0].isdigit()
    node: Node = {"type": "orderedList" if ordered else "bulletList", "content": []}
    if ordered:
        node["attrs"] = {"order": int(marker.rstrip(".)"))}
    i = start
    while item := _sibling_item(lines, i, indent, ordered):
        list_item, i = _list_item(lines, i + 1, indent, item)
        node["content"].append(list_item)
        i = _skip_blank_before_sibling(lines, i, indent)
    return node, i


def _sibling_item(lines: list[str], i: int, indent: int, ordered: bool) -> re.Match[str] | None:
    item = _LIST_ITEM.match(lines[i]) if i < len(lines) else None
    if item and len(item.group(1)) == indent and item.group(2)[0].isdigit() == ordered:
        return item
    return None


def _list_item(lines: list[str], i: int, indent: int, item: re.Match[str]) -> tuple[Node, int]:
    """Item e as linhas mais indentadas que o seguem: continuação de texto ou sublistas."""
    text_lines = [_checkbox(item.group(3) or "")]
    children: list[Node] = []
    while i < len(lines) and lines[i].strip() and _indent(lines[i]) > indent:
        if child := _LIST_ITEM.match(lines[i]):
            nested, i = _list(lines, i, len(child.group(1)))
            children.append(nested)
        else:
            text_lines.append(lines[i].strip())
            i += 1
    return {"type": "listItem", "content": [_paragraph(text_lines), *children]}, i


def _skip_blank_before_sibling(lines: list[str], i: int, indent: int) -> int:
    """Linha em branco entre itens da mesma lista não encerra a lista."""
    if i >= len(lines) or lines[i].strip():
        return i
    following = _advance_while(lines, i, lambda text: not text.strip())
    next_item = _LIST_ITEM.match(lines[following]) if following < len(lines) else None
    return following if next_item and len(next_item.group(1)) == indent else i


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _checkbox(text: str) -> str:
    box = _CHECKBOX.match(text)
    if not box:
        return text
    symbol = "☐" if box.group(1) == " " else "☑"
    return f"{symbol} {text[box.end():]}"


def _paragraph(lines: list[str]) -> Node:
    content: list[Node] = []
    for index, line in enumerate(lines):
        if index:
            content.append({"type": "hardBreak"})
        content.extend(_inline(line.strip()))
    return {"type": "paragraph", "content": content} if content else {"type": "paragraph"}


def _code(text: str, language: str | None) -> Node:
    node: Node = {"type": "codeBlock", "content": [{"type": "text", "text": text}] if text else []}
    if language:
        node["attrs"] = {"language": language}
    return node


def _inline(text: str, marks: tuple[Node, ...] = ()) -> list[Node]:
    nodes: list[Node] = []
    position = 0
    for match in _INLINE.finditer(text):
        nodes.extend(_text(text[position : match.start()], marks))
        nodes.extend(_inline_match(match, marks))
        position = match.end()
    nodes.extend(_text(text[position:], marks))
    return _merge_adjacent(nodes)


def _merge_adjacent(nodes: list[Node]) -> list[Node]:
    """Une nós de texto vizinhos com as mesmas marcas (ex.: texto puro antes/depois de wikilink)."""
    merged: list[Node] = []
    for node in nodes:
        if merged and merged[-1].get("marks") == node.get("marks"):
            merged[-1] = {**merged[-1], "text": merged[-1]["text"] + node["text"]}
        else:
            merged.append(node)
    return merged


def _inline_match(match: re.Match[str], marks: tuple[Node, ...]) -> list[Node]:
    group = match.group
    if group("code") is not None:
        # Código inline só pode ser combinado com link no ADF.
        return _text(group("code"), tuple(m for m in marks if m["type"] == "link") + ({"type": "code"},))
    if group("wiki") is not None:
        return _text(group("wiki_alias") or group("wiki"), marks)
    if group("link_text") is not None:
        return _inline(group("link_text"), _with(marks, {"type": "link", "attrs": {"href": group("link_url")}}))
    for name, mark in _EMPHASIS_GROUPS:
        if group(name) is not None:
            return _inline(group(name), _with(marks, {"type": mark}))
    raise AssertionError("grupo inline não tratado")


def _with(marks: tuple[Node, ...], mark: Node) -> tuple[Node, ...]:
    return marks if any(m["type"] == mark["type"] for m in marks) else (*marks, mark)


def _text(text: str, marks: tuple[Node, ...]) -> list[Node]:
    if not text:
        return []
    node: Node = {"type": "text", "text": text}
    if marks:
        node["marks"] = list(marks)
    return [node]
