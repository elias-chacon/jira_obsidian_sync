"""Composição do sincronizador e execução em primeiro plano (também usada no logon, via pythonw).

Uso: python service.py   (primeiro plano, até Ctrl+C). O serviço Windows fica em windows_service.py.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from pathlib import Path

from board_state import BoardState
from board_sync import BoardSynchronizer, BoardWatcher
from comment_dialog import TkCommentPrompt
from config import JiraSettings, SyncSettings, load_env
from instance_lock import AlreadyRunningError, InstanceLock
from kanban_pull import JiraToKanbanSync, PollingWorker, squad_jql
from task_comments import TaskNotes, TransitionCommenter

LOG = logging.getLogger("jira_obsidian_service")
LOG_FILE = Path(__file__).with_name("service.log")
LOCK_FILE = Path(__file__).with_name("service.lock")


class SyncService:
    """Obsidian → Jira sempre; Jira → Obsidian quando `pull` é configurado."""

    def __init__(
        self,
        watcher: BoardWatcher,
        pull: JiraToKanbanSync | None,
        pull_interval_seconds: float,
        lock: InstanceLock | None = None,
    ) -> None:
        self.watcher = watcher
        self.pull = pull
        self.poller = PollingWorker(pull.sync_once, pull_interval_seconds, "jira-pull") if pull else None
        self.lock = lock

    def start(self) -> None:
        """Obtém o lock de instância única, aplica o Jira ao board (se configurado), monitora e inicia o polling.

        AlreadyRunningError se outra instância estiver rodando; qualquer falha aqui libera o lock.
        """
        if self.lock:
            self.lock.acquire()
        try:
            if self.pull:
                # Jira prevalece sobre o que mudou no board com o serviço parado. Falha aqui aborta o início:
                # sem esse passo, o watcher reenviaria ao Jira um board desatualizado.
                self.pull.sync_once()
            self.watcher.start()
            if self.poller:
                self.poller.start()
        except BaseException:
            self._release_lock()
            raise

    def stop(self) -> None:
        if self.poller:
            self.poller.stop()
        self.watcher.stop()
        self._release_lock()

    def _release_lock(self) -> None:
        if self.lock:
            self.lock.release()


def build_service(interactive: bool = True) -> SyncService:
    """`interactive=False` desativa a janela de comentário (serviço Windows roda na sessão 0, sem desktop)."""
    jira = JiraSettings.from_env().client()
    settings = SyncSettings.from_env()
    board = settings.board_file
    state = BoardState()
    # O board fica em vault/Squad/<projeto Jira>/; as pastas das tasks, em <projeto identificado>/<CHAVE>/ ao lado.
    commenter = TransitionCommenter(TaskNotes(board.parent), jira, TkCommentPrompt() if interactive else None)
    watcher = BoardWatcher(BoardSynchronizer(board, jira, state=state, on_transition=commenter))
    lock = InstanceLock(LOCK_FILE)
    if not settings.pull_enabled:
        return SyncService(watcher, None, 0, lock)
    jql = squad_jql(settings.project_key, settings.assignees, settings.jql_extra)
    return SyncService(watcher, JiraToKanbanSync(board, jira, jql, state), settings.pull_interval_seconds, lock)


def configure_logging(*extra_handlers: logging.Handler) -> None:
    """Grava em service.log com o nível de LOG_LEVEL; carrega o .env antes para que a variável valha."""
    load_env()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), *extra_handlers],
    )


def run_foreground() -> int:
    """Executa até Ctrl+C ou SIGTERM. Código de saída 1 se outra instância já estiver rodando."""
    # Sob pythonw (execução no logon, sem console) não há stderr.
    configure_logging(*([logging.StreamHandler()] if sys.stderr else []))
    sync = build_service()
    stop_event = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    try:
        sync.start()
    except AlreadyRunningError as exc:
        # NOSONAR abaixo: segunda instância é condição esperada; traceback (logging.exception) seria só ruído.
        LOG.error("%s; esta execução foi encerrada.", exc)  # NOSONAR
        return 1
    try:
        stop_event.wait()
    finally:
        sync.stop()
    return 0


if __name__ == "__main__":
    sys.exit(run_foreground())
