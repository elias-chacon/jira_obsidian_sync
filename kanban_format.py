"""Formato Markdown do quadro Obsidian Kanban, compartilhado pelas duas direções de sincronização."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Captura chave Jira em link markdown/wikilink ou texto de cartão. Quantificadores possessivos (Python 3.11+)
# impedem backtracking em sequências longas de maiúsculas sem hífen.
ISSUE_KEY = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9]++-\d++)")
COLUMN_HEADING = re.compile(r"^##[ \t]+(\S.*)$")
CARD_LINE = re.compile(r"^\s*[-*+]\s+")
# Bloco de configuração que o plugin Kanban grava no fim do arquivo.
SETTINGS_MARKER = "%% kanban:settings"


def column_name(line: str) -> str | None:
    match = COLUMN_HEADING.match(line)
    return match.group(1).strip() if match else None


def card_key(line: str) -> str | None:
    """Chave Jira do cartão: a primeira chave da linha de item de lista."""
    if not CARD_LINE.match(line):
        return None
    match = ISSUE_KEY.search(line)
    return match.group(1) if match else None


def format_card(key: str, summary: str, issue_type: str, assignee: str | None) -> str:
    # A chave vem primeiro: resumos costumam citar outras chaves (ex.: SR-123).
    owner = assignee.split()[0] if assignee else "-"
    return f"- [ ] {key} — {summary.strip()} · {issue_type} · @{owner}"


@dataclass
class _Block:
    """Linhas consecutivas do board; `key` presente quando o bloco é um cartão Jira."""

    lines: list[str]
    key: str | None = None


@dataclass
class _Column:
    name: str
    heading: str
    blocks: list[_Block] = field(default_factory=list)


class KanbanDocument:
    """Board editável: H2 são colunas, itens de lista com chave Jira são cartões.

    Todo o resto (front matter, texto livre, configurações do plugin) é preservado em `render()`.
    """

    def __init__(self, preamble: list[str], columns: list[_Column], epilogue: list[str]) -> None:
        self._preamble = preamble
        self._columns = columns
        self._epilogue = epilogue

    @classmethod
    def parse(cls, markdown: str) -> KanbanDocument:
        """ValueError se a mesma chave Jira aparecer em dois cartões."""
        preamble: list[str] = []
        columns: list[_Column] = []
        epilogue: list[str] = []
        seen: set[str] = set()
        lines = markdown.split("\n")
        for index, line in enumerate(lines):
            if line.startswith(SETTINGS_MARKER):
                epilogue = lines[index:]
                break
            heading = column_name(line)
            if heading:
                columns.append(_Column(heading, line))
                continue
            if not columns:
                preamble.append(line)
                continue
            blocks = columns[-1].blocks
            key = card_key(line)
            if key:
                if key in seen:
                    raise ValueError(f"Cartão duplicado no board: {key}")
                seen.add(key)
                blocks.append(_Block([line], key))
            elif blocks and blocks[-1].key and line[:1].isspace() and line.strip():
                blocks[-1].lines.append(line)  # continuação indentada de cartão multilinha
            else:
                blocks.append(_Block([line]))
        return cls(preamble, columns, epilogue)

    def cards(self) -> dict[str, str]:
        """Chave Jira → nome da coluna."""
        return {block.key: column.name for column in self._columns for block in column.blocks if block.key}

    def column_for(self, status: str) -> str | None:
        """Nome da coluna que representa o status (comparação sem diferenciar maiúsculas)."""
        column = self._column(status)
        return column.name if column else None

    def move_card(self, key: str, column: str) -> None:
        source, block = self._find(key)
        source.blocks.remove(block)
        self._insert(self._require_column(column), block)

    def add_card(self, key: str, line: str, column: str) -> None:
        if key in self.cards():
            raise ValueError(f"Cartão duplicado no board: {key}")
        self._insert(self._require_column(column), _Block([line], key))

    def render(self) -> str:
        """Markdown do board; idêntico à entrada se nada foi alterado."""
        lines = list(self._preamble)
        for column in self._columns:
            lines.append(column.heading)
            lines.extend(line for block in column.blocks for line in block.lines)
        lines.extend(self._epilogue)
        return "\n".join(lines)

    def _column(self, name: str) -> _Column | None:
        return next((c for c in self._columns if c.name.casefold() == name.casefold()), None)

    def _require_column(self, name: str) -> _Column:
        column = self._column(name)
        if column is None:
            raise KeyError(f"Coluna inexistente no board: {name}")
        return column

    def _find(self, key: str) -> tuple[_Column, _Block]:
        for column in self._columns:
            for block in column.blocks:
                if block.key == key:
                    return column, block
        raise KeyError(f"Cartão inexistente no board: {key}")

    @staticmethod
    def _insert(column: _Column, block: _Block) -> None:
        """Insere após o último cartão; em coluna vazia, após a linha em branco que segue o título."""
        card_positions = [i for i, b in enumerate(column.blocks) if b.key]
        if card_positions:
            position = card_positions[-1] + 1
        else:
            position = 1 if column.blocks and not "".join(column.blocks[0].lines).strip() else 0
        column.blocks.insert(position, block)
