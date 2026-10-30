"""Comentários publicados quando um cartão movido no board transiciona a issue no Jira.

Se a pasta da task tem notas Markdown, cada nota vira um comentário (em ordem de criação do arquivo);
uma nota editada atualiza o comentário que ela gerou. Sem notas, pede um comentário ao usuário.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from jira_client import JiraComment
from markdown_adf import to_adf

LOG = logging.getLogger(__name__)
# Entity property gravada em cada comentário gerado de nota: {"file": nome, "sha256": hash do conteúdo}.
PROPERTY_KEY = "obsidian-sync"


@dataclass(frozen=True)
class NoteFile:
    """Nota Markdown da pasta da task."""
    name: str
    text: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


class TaskNotes:
    """Notas da task em `<root>/<projeto identificado>/<CHAVE>/*.md`."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def find(self, issue_key: str) -> list[NoteFile]:
        """Notas não vazias em ordem de criação; ValueError se a chave tiver mais de uma pasta."""
        folders = [path for path in self.root.glob(f"*/{issue_key}") if path.is_dir()]
        if len(folders) > 1:
            raise ValueError(f"{issue_key}: mais de uma pasta de task: {[str(f) for f in folders]}")
        if not folders:
            return []
        files = sorted((f for f in folders[0].glob("*.md") if f.is_file()), key=lambda f: (_created_at(f), f.name))
        notes = [NoteFile(f.name, f.read_text(encoding="utf-8")) for f in files]
        return [note for note in notes if note.text.strip()]


def _created_at(path: Path) -> float:
    stat = path.stat()
    # st_birthtime: data de criação no Windows (Python 3.12+); st_ctime é o equivalente em versões anteriores.
    return getattr(stat, "st_birthtime", stat.st_ctime)


class CommentGateway(Protocol):
    """Operações de comentário do Jira usadas por `TransitionCommenter`."""
    def list_comments(self, issue_key: str) -> list[JiraComment]: ...

    def add_comment(self, issue_key: str, body: dict[str, Any], properties: dict[str, Any] | None = None) -> str: ...

    def update_comment(
        self, issue_key: str, comment_id: str, body: dict[str, Any], properties: dict[str, Any]
    ) -> None: ...


class CommentPrompt(Protocol):
    def ask(self, issue_key: str, status: str) -> str | None:
        """Texto Markdown digitado pelo usuário, ou None se ele não quiser comentar."""


class TransitionCommenter:
    """Callback `on_transition`: publica as notas da task ou pede um comentário."""
    def __init__(self, notes: TaskNotes, jira: CommentGateway, prompt: CommentPrompt | None) -> None:
        self.notes = notes
        self.jira = jira
        # None quando não há sessão interativa (ex.: serviço Windows na sessão 0).
        self.prompt = prompt

    def __call__(self, issue_key: str, status: str) -> None:
        notes = self.notes.find(issue_key)
        if notes:
            self._publish_notes(issue_key, notes)
            return
        if self.prompt is None:
            LOG.info("%s: sem notas na pasta da task e sem janela disponível; nenhum comentário.", issue_key)
            return
        text = self.prompt.ask(issue_key, status)
        if text and text.strip():
            self.jira.add_comment(issue_key, to_adf(text))
            LOG.info("%s: comentário digitado publicado.", issue_key)

    def _publish_notes(self, issue_key: str, notes: list[NoteFile]) -> None:
        published = {
            marker["file"]: (comment.id, marker.get("sha256"))
            for comment in self.jira.list_comments(issue_key)
            if isinstance(marker := comment.properties.get(PROPERTY_KEY), dict) and "file" in marker
        }
        for note in notes:
            properties = {PROPERTY_KEY: {"file": note.name, "sha256": note.digest}}
            if note.name not in published:
                self.jira.add_comment(issue_key, to_adf(note.text), properties)
                LOG.info("%s: comentário criado a partir de %s.", issue_key, note.name)
                continue
            comment_id, digest = published[note.name]
            if digest != note.digest:
                self.jira.update_comment(issue_key, comment_id, to_adf(note.text), properties)
                LOG.info("%s: comentário %s atualizado a partir de %s.", issue_key, comment_id, note.name)
