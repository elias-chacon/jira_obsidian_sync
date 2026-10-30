"""Cliente da API REST v3 do Jira Cloud: única dependência do Jira no projeto."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

LOG = logging.getLogger(__name__)


class JiraError(RuntimeError):
    """Erro de comunicação, autenticação ou workflow do Jira."""


@dataclass(frozen=True)
class JiraComment:
    id: str
    # Entity properties do comentário (chave → valor JSON); invisíveis na interface do Jira.
    properties: dict[str, Any]


@dataclass(frozen=True)
class IssueSnapshot:
    """Campos de uma issue necessários para montar e posicionar o cartão."""
    key: str
    status: str
    summary: str
    issue_type: str
    assignee: str | None


@dataclass(frozen=True)
class Transition:
    """Transição de workflow disponível a partir do status atual."""
    id: str
    name: str
    to_status: str
    # Campos obrigatórios da tela de transição sem valor padrão.
    required_fields: tuple[str, ...]


@dataclass(frozen=True)
class JiraUser:
    display_name: str
    email: str | None  # oculto conforme a privacidade do perfil


class JiraClient:
    """Cliente Jira Cloud. Mantém toda a dependência Jira neste módulo."""

    def __init__(self, base_url: str, email: str, api_token: str, verify_tls: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        self.session.verify = verify_tls

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        try:
            response = self.session.request(method, f"{self.base_url}{path}", timeout=30, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            detail = exc.response.text[:1000] if exc.response is not None else str(exc)
            raise JiraError(f"Jira API {method} {path} falhou: {detail}") from exc

    def search_issues(self, jql: str, page_size: int = 100) -> list[IssueSnapshot]:
        """Executa JQL percorrendo todas as páginas. Chaves inexistentes em `key in (...)` são ignoradas pelo Jira."""
        params: dict[str, Any] = {"jql": jql, "fields": "summary,status,issuetype,assignee", "maxResults": page_size}
        issues: list[IssueSnapshot] = []
        while True:
            page = self._request("GET", "/rest/api/3/search/jql", params=params).json()
            issues.extend(self._snapshot(item) for item in page.get("issues", []))
            token = page.get("nextPageToken")
            if page.get("isLast", True) or not token:
                return issues
            params["nextPageToken"] = token

    @staticmethod
    def _snapshot(item: dict[str, Any]) -> IssueSnapshot:
        fields = item["fields"]
        return IssueSnapshot(
            key=item["key"],
            status=fields["status"]["name"],
            summary=fields["summary"],
            issue_type=fields["issuetype"]["name"],
            assignee=(fields.get("assignee") or {}).get("displayName"),
        )

    def list_comments(self, issue_key: str, page_size: int = 100) -> list[JiraComment]:
        """Todos os comentários da issue, com suas entity properties."""
        comments: list[JiraComment] = []
        params: dict[str, Any] = {"expand": "properties", "maxResults": page_size, "startAt": 0}
        while True:
            page = self._request("GET", f"/rest/api/3/issue/{issue_key}/comment", params=params).json()
            items = page.get("comments", [])
            comments.extend(
                JiraComment(item["id"], {prop["key"]: prop.get("value") for prop in item.get("properties", [])})
                for item in items
            )
            params["startAt"] += len(items)
            if not items or params["startAt"] >= page.get("total", 0):
                return comments

    def add_comment(self, issue_key: str, body: dict[str, Any], properties: dict[str, Any] | None = None) -> str:
        """Cria comentário com corpo ADF; `properties` são gravadas junto, na mesma requisição."""
        payload: dict[str, Any] = {"body": body}
        if properties:
            payload["properties"] = [{"key": key, "value": value} for key, value in properties.items()]
        return self._request("POST", f"/rest/api/3/issue/{issue_key}/comment", json=payload).json()["id"]

    def update_comment(self, issue_key: str, comment_id: str, body: dict[str, Any], properties: dict[str, Any]) -> None:
        self._request("PUT", f"/rest/api/3/issue/{issue_key}/comment/{comment_id}", json={"body": body})
        for key, value in properties.items():
            self._request("PUT", f"/rest/api/3/comment/{comment_id}/properties/{key}", json=value)

    def current_user(self) -> JiraUser:
        data = self._request("GET", "/rest/api/3/myself").json()
        return JiraUser(data.get("displayName", "?"), data.get("emailAddress"))

    def get_issue_status(self, issue_key: str) -> str:
        data = self._request("GET", f"/rest/api/3/issue/{issue_key}", params={"fields": "status"}).json()
        return data["fields"]["status"]["name"]

    def list_transitions(self, issue_key: str) -> list[Transition]:
        """Transições disponíveis a partir do status atual da issue."""
        data = self._request(
            "GET", f"/rest/api/3/issue/{issue_key}/transitions", params={"expand": "transitions.fields"}
        ).json()
        return [
            Transition(
                id=item["id"],
                name=item.get("name", "?"),
                to_status=item.get("to", {}).get("name", "?"),
                required_fields=tuple(
                    name for name, meta in item.get("fields", {}).items()
                    if meta.get("required") and not meta.get("hasDefaultValue")
                ),
            )
            for item in data.get("transitions", [])
        ]

    def transition_to_status(self, issue_key: str, target_status: str) -> bool:
        """Move a issue por uma transição única até `target_status`. Retorna False se ela já estava lá."""
        current = self.get_issue_status(issue_key)
        if current.casefold() == target_status.casefold():
            LOG.info("%s já está em '%s'; nenhuma ação.", issue_key, current)
            return False
        transitions = self.list_transitions(issue_key)
        matches = [t for t in transitions if t.to_status.casefold() == target_status.casefold()]
        if len(matches) != 1:
            available = sorted({t.to_status for t in transitions})
            raise JiraError(
                f"{issue_key}: destino '{target_status}' não é alcançável por uma transição única. "
                f"Status atual='{current}', destinos disponíveis={available}"
            )
        transition = matches[0]
        # Não inventa valores de campos obrigatórios da tela de transição.
        if transition.required_fields:
            raise JiraError(f"{issue_key}: transição exige campos não configurados: {list(transition.required_fields)}")
        self._request("POST", f"/rest/api/3/issue/{issue_key}/transitions", json={"transition": {"id": transition.id}})
        LOG.info("Issue %s: '%s' → '%s'", issue_key, current, target_status)
        return True
