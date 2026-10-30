"""Sincronização Obsidian → Jira: cada cartão movido no board transiciona a issue para o status da coluna."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from board_state import BoardState
from jira_client import JiraError
from kanban_format import KanbanDocument

LOG = logging.getLogger(__name__)


class StatusTransitioner(Protocol):
    def transition_to_status(self, issue_key: str, target_status: str) -> bool:
        """Retorna True se a issue foi transicionada, False se já estava no status."""


class BoardSynchronizer:
    """Envia ao Jira os cartões que mudaram de coluna desde o último estado consistente do board."""

    def __init__(
        self,
        board_file: Path,
        jira: StatusTransitioner,
        debounce_seconds: float = 1.0,
        state: BoardState | None = None,
        on_transition: Callable[[str, str], None] | None = None,
    ) -> None:
        self.board_file = board_file.resolve()
        self.jira = jira
        self.debounce_seconds = debounce_seconds
        self.state = state or BoardState()
        # Chamado com (chave, status) após cada transição efetivamente feita no Jira, fora do lock do board:
        # pode aguardar o usuário (janela de comentário) sem bloquear a sincronização Jira → Obsidian.
        self.on_transition = on_transition

    def sync_once(self) -> None:
        """Envia ao Jira os cartões movidos e, já sem o lock, publica os comentários."""
        # Obsidian grava arquivo em etapas; debounce reduz leitura durante escrita.
        time.sleep(self.debounce_seconds)
        with self.state.lock:
            transitioned = self._push_moved_cards()
        for issue_key, status in transitioned:
            self._notify(issue_key, status)

    def _push_moved_cards(self) -> list[tuple[str, str]]:
        content = self.board_file.read_text(encoding="utf-8")
        previous = self.state.synced_content
        if content == previous:
            return []
        cards = KanbanDocument.parse(content).cards()
        # Sem estado consistente anterior (1ª execução sem consulta ao Jira), envia todos os cartões.
        baseline = KanbanDocument.parse(previous).cards() if previous is not None else {}
        self.state.synced_content = content
        transitioned: list[tuple[str, str]] = []
        for issue_key, target_status in cards.items():
            if baseline.get(issue_key) == target_status:
                continue
            try:
                if self.jira.transition_to_status(issue_key, target_status):
                    transitioned.append((issue_key, target_status))
            except JiraError:
                # Um cartão inválido não impede sincronização dos demais.
                LOG.exception("Não foi possível sincronizar %s", issue_key)
        return transitioned

    def _notify(self, issue_key: str, status: str) -> None:
        if not self.on_transition:
            return
        try:
            self.on_transition(issue_key, status)
        except (JiraError, OSError, ValueError):
            LOG.exception("%s transicionada, mas o comentário falhou", issue_key)


class BoardChangeHandler(FileSystemEventHandler):
    """Dispara a sincronização quando o arquivo do board é gravado."""
    def __init__(self, synchronizer: BoardSynchronizer) -> None:
        self.synchronizer = synchronizer
        self.path = str(synchronizer.board_file)

    def on_modified(self, event) -> None:
        if not event.is_directory and str(Path(event.src_path).resolve()) == self.path:
            self._sync()

    def on_created(self, event) -> None:
        self.on_modified(event)

    def _sync(self) -> None:
        try:
            self.synchronizer.sync_once()
        except (OSError, ValueError):  # ValueError inclui UnicodeDecodeError e cartão duplicado
            LOG.exception("Falha lendo quadro Kanban")


class BoardWatcher:
    """Monitora a pasta do board com watchdog."""
    def __init__(self, synchronizer: BoardSynchronizer) -> None:
        self.synchronizer = synchronizer
        self.observer = Observer()

    def start(self) -> None:
        """Sincroniza uma vez e passa a monitorar o arquivo."""
        self.synchronizer.sync_once()  # reconcilia estado ao iniciar
        handler = BoardChangeHandler(self.synchronizer)
        self.observer.schedule(handler, str(self.synchronizer.board_file.parent), recursive=False)
        self.observer.start()
        LOG.info("Monitorando %s", self.synchronizer.board_file)

    def stop(self) -> None:
        self.observer.stop()
        self.observer.join(timeout=10)
