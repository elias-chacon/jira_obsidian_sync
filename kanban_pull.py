"""Sincronização Jira → Obsidian: move cartões para a coluna do status atual e adiciona issues novas da squad.

Regra de conflito: o Jira prevalece, exceto sobre alterações locais ainda não enviadas pelo
`BoardSynchronizer` — nesse caso a rodada é adiada para não desfazer o movimento do usuário.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from board_state import BoardState
from jira_client import IssueSnapshot
from kanban_format import KanbanDocument, format_card

LOG = logging.getLogger(__name__)


class IssueSource(Protocol):
    def search_issues(self, jql: str) -> list[IssueSnapshot]: ...


@dataclass
class ReconcileReport:
    """Resultado de `reconcile`: cartões movidos, adicionados e status sem coluna."""
    moved: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    # Issues cujo status não tem coluna no board; o cartão (se existir) fica onde está.
    unmapped: dict[str, str] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.moved or self.added)


def reconcile(document: KanbanDocument, issues: Iterable[IssueSnapshot]) -> ReconcileReport:
    """Aplica ao documento o status atual de cada issue."""
    report = ReconcileReport()
    cards = document.cards()
    for issue in issues:
        target = document.column_for(issue.status)
        if target is None:
            report.unmapped[issue.key] = issue.status
        elif issue.key not in cards:
            line = format_card(issue.key, issue.summary, issue.issue_type, issue.assignee)
            document.add_card(issue.key, line, target)
            report.added.append(issue.key)
        elif cards[issue.key] != target:
            document.move_card(issue.key, target)
            report.moved.append(issue.key)
    return report


def squad_jql(project_key: str, assignees: Iterable[str] = (), extra: str = "") -> str:
    """Issues abertas da squad: candidatas a entrar no board."""
    clauses = [f'project = "{_quote(project_key)}"', "statusCategory != Done"]
    names = ", ".join(f'"{_quote(name)}"' for name in assignees if name)
    if names:
        clauses.append(f"assignee in ({names})")
    if extra.strip():
        clauses.append(f"({extra.strip()})")
    return " AND ".join(clauses)


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class JiraToKanbanSync:
    """Aplica ao board o estado atual das issues no Jira."""
    def __init__(self, board_file: Path, source: IssueSource, base_jql: str, state: BoardState) -> None:
        self.board_file = board_file.resolve()
        self.source = source
        self.base_jql = base_jql
        self.state = state
        self._warned: set[tuple[str, str]] = set()

    def sync_once(self) -> None:
        """Uma rodada de consulta e reconciliação; adiada se houver alteração local pendente."""
        with self.state.lock:
            raw = self._read_raw()
            content = _normalize(raw)
            synced = self.state.synced_content
            if synced is not None and content != synced:
                LOG.debug("Board com alterações locais ainda não enviadas ao Jira; rodada adiada.")
                return
            document = KanbanDocument.parse(content)
            # Inclui cartões já no board para acompanhá-los mesmo após saírem do filtro (ex.: concluídos).
            report = reconcile(document, self.source.search_issues(self._jql(document.cards().keys())))
            self._warn_unmapped(report.unmapped)
            if not report.changed:
                self.state.synced_content = content
                return
            updated = document.render()
            if not self._replace_if_unchanged(raw, updated):
                LOG.info("Board alterado durante a consulta ao Jira; rodada adiada.")
                return
            self.state.synced_content = updated
        LOG.info("Board atualizado pelo Jira: movidos=%s adicionados=%s", report.moved, report.added)

    def _jql(self, board_keys: Iterable[str]) -> str:
        keys = ", ".join(sorted(board_keys))
        tracked = f" OR key in ({keys})" if keys else ""
        return f"({self.base_jql}){tracked} ORDER BY key"

    def _read_raw(self) -> str:
        with self.board_file.open(encoding="utf-8", newline="") as stream:
            return stream.read()

    def _replace_if_unchanged(self, expected_raw: str, content: str) -> bool:
        """Grava de forma atômica, a menos que o arquivo tenha mudado desde `expected_raw`."""
        if self._read_raw() != expected_raw:
            return False
        newline = "\r\n" if "\r\n" in expected_raw else "\n"
        temp = self.board_file.with_name(self.board_file.name + ".tmp")
        with temp.open("w", encoding="utf-8", newline=newline) as stream:
            stream.write(content)
        os.replace(temp, self.board_file)
        return True

    def _warn_unmapped(self, unmapped: dict[str, str]) -> None:
        for key, status in unmapped.items():
            if (key, status) not in self._warned:
                self._warned.add((key, status))
                LOG.warning("%s está em '%s', que não tem coluna no board; cartão não foi alterado.", key, status)


def _normalize(raw: str) -> str:
    # Mesmo texto que Path.read_text entrega ao BoardSynchronizer, para comparar com `synced_content`.
    return raw.replace("\r\n", "\n")


class PollingWorker:
    """Executa `task` a cada `interval_seconds` em thread própria até `stop()`."""

    def __init__(self, task: Callable[[], None], interval_seconds: float, name: str) -> None:
        self.task = task
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.task()
            except Exception:  # pylint: disable=broad-exception-caught  # falha de uma rodada não encerra o polling
                LOG.exception("Falha na sincronização periódica")
