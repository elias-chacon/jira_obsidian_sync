"""Configuração lida dos arquivos .env: o da pasta do helper tem precedência sobre o da raiz do projeto."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from jira_client import JiraClient

# Credenciais Jira ficam no .env da raiz; o .env local guarda só a configuração do serviço.
ENV_FILES = (Path(__file__).with_name(".env"), Path(__file__).resolve().parents[2] / ".env")
_FALSE_VALUES = {"false", "0", "no"}


class ConfigError(RuntimeError):
    """Variável obrigatória ausente ou valor inválido no .env."""


def load_env() -> None:
    """Carrega os .env sem sobrescrever variáveis já definidas no ambiente."""
    for env_file in ENV_FILES:
        load_dotenv(env_file)


def _require(*names: str) -> None:
    absent = [name for name in names if not os.getenv(name)]
    if absent:
        raise ConfigError(f"Variáveis ausentes no .env: {', '.join(absent)}")


@dataclass(frozen=True)
class JiraSettings:
    """Acesso à API do Jira (JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_VERIFY_TLS)."""
    base_url: str
    email: str
    api_token: str = field(repr=False)  # nunca aparece em logs ou mensagens de erro
    verify_tls: bool = True

    @classmethod
    def from_env(cls) -> JiraSettings:
        load_env()
        _require("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
        return cls(
            base_url=os.environ["JIRA_BASE_URL"],
            email=os.environ["JIRA_EMAIL"],
            api_token=os.environ["JIRA_API_TOKEN"],
            verify_tls=os.getenv("JIRA_VERIFY_TLS", "true").lower() not in _FALSE_VALUES,
        )

    def client(self) -> JiraClient:
        return JiraClient(self.base_url, self.email, self.api_token, self.verify_tls)


@dataclass(frozen=True)
class SyncSettings:
    """Board monitorado e sincronização Jira → Obsidian (JIRA_PULL_INTERVAL_SECONDS etc.)."""
    board_file: Path
    # 0 desativa a sincronização Jira → Obsidian.
    pull_interval_seconds: float = 0
    project_key: str = ""
    assignees: tuple[str, ...] = ()
    jql_extra: str = ""

    @property
    def pull_enabled(self) -> bool:
        return self.pull_interval_seconds > 0

    @classmethod
    def from_env(cls) -> SyncSettings:
        """Lê e valida as variáveis; ConfigError se faltar algo ou o board não existir."""
        load_env()
        _require("OBSIDIAN_BOARD_FILE")
        board = Path(os.environ["OBSIDIAN_BOARD_FILE"])
        if not board.is_file():
            raise ConfigError(f"Kanban não encontrado: {board}")
        try:
            interval = float(os.getenv("JIRA_PULL_INTERVAL_SECONDS", "0"))
        except ValueError as exc:
            raise ConfigError("JIRA_PULL_INTERVAL_SECONDS deve ser um número de segundos") from exc
        if interval > 0:
            _require("JIRA_PROJECT_KEY")
        return cls(
            board_file=board,
            pull_interval_seconds=interval,
            project_key=os.getenv("JIRA_PROJECT_KEY", ""),
            assignees=tuple(name.strip() for name in os.getenv("JIRA_USERS", "").split(";") if name.strip()),
            jql_extra=os.getenv("JIRA_JQL_EXTRA", ""),
        )
