"""Valida o .env: autentica no Jira e lista os status alcançáveis de uma issue, sem movê-la.

Uso: python check_connection.py [CHAVE-123]
"""
from __future__ import annotations

import sys

from config import ConfigError, JiraSettings
from jira_client import JiraClient, JiraError


def main(argv: list[str]) -> int:
    """Retorna 0 se autenticou (e listou transições, se pedido), 1 caso contrário."""
    try:
        jira = JiraSettings.from_env().client()
        user = jira.current_user()
        print(f"Autenticado como: {user.display_name} ({user.email or 'e-mail oculto'})")
        if len(argv) > 1:
            _print_transitions(jira, argv[1])
    except (ConfigError, JiraError) as exc:
        # JiraError traz apenas o corpo da resposta HTTP; JiraSettings omite o token do repr.
        print(exc)
        return 1
    return 0


def _print_transitions(jira: JiraClient, issue_key: str) -> None:
    print(f"{issue_key} está em '{jira.get_issue_status(issue_key)}'. Destinos possíveis:")
    for transition in jira.list_transitions(issue_key):
        print(f"  - {transition.to_status} (transição '{transition.name}', id {transition.id})")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
