"""Regras do JiraClient sobre respostas HTTP simuladas (sem rede)."""
# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access
import unittest
from unittest.mock import MagicMock, patch

from jira_client import JiraClient, JiraError


def response(payload):
    mock = MagicMock()
    mock.json.return_value = payload
    return mock


def transition(transition_id, to_status, fields=None):
    return {"id": transition_id, "name": f"Ir para {to_status}", "to": {"name": to_status}, "fields": fields or {}}


class TransitionToStatusTest(unittest.TestCase):
    def setUp(self):
        self.client = JiraClient("https://exemplo.atlassian.net/", "a@b.c", "token")
        self.request = self.enterContext(patch.object(self.client, "_request"))

    def respond(self, status, transitions):
        self.request.side_effect = [
            response({"fields": {"status": {"name": status}}}),
            response({"transitions": transitions}),
            response({}),
        ]

    def test_posts_the_single_matching_transition(self):
        self.respond("To Do", [transition("11", "Em andamento"), transition("21", "Done")])
        self.assertTrue(self.client.transition_to_status("AB-1", "em ANDAMENTO"))
        self.request.assert_called_with(
            "POST", "/rest/api/3/issue/AB-1/transitions", json={"transition": {"id": "11"}}
        )

    def test_already_in_status_does_nothing(self):
        self.respond("Done", [])
        self.assertFalse(self.client.transition_to_status("AB-1", "done"))
        self.assertEqual(self.request.call_count, 1)

    def test_rejects_missing_or_ambiguous_destination(self):
        for transitions in ([transition("21", "Done")], [transition("11", "QA"), transition("12", "QA")]):
            with self.subTest(transitions=transitions):
                self.respond("To Do", transitions)
                with self.assertRaises(JiraError):
                    self.client.transition_to_status("AB-1", "QA")

    def test_rejects_required_fields_without_default(self):
        fields = {
            "resolution": {"required": True, "hasDefaultValue": False},
            "x": {"required": True, "hasDefaultValue": True},
        }
        self.respond("To Do", [transition("31", "Done", fields)])
        with self.assertRaisesRegex(JiraError, "resolution"):
            self.client.transition_to_status("AB-1", "Done")


class PaginationTest(unittest.TestCase):
    def setUp(self):
        self.client = JiraClient("https://exemplo.atlassian.net", "a@b.c", "token")
        self.request = self.enterContext(patch.object(self.client, "_request"))

    def test_list_comments_reads_all_pages_with_properties(self):
        prop = {"key": "obsidian-sync", "value": {"file": "a.md"}}
        pages = iter([
            {"comments": [{"id": "1", "properties": [prop]}], "total": 2},
            {"comments": [{"id": "2"}], "total": 2},
        ])
        offsets = []

        def fake_request(_method, _path, params):
            offsets.append(params["startAt"])  # o client reaproveita o dict entre páginas
            return response(next(pages))

        self.request.side_effect = fake_request
        comments = self.client.list_comments("AB-1", page_size=1)
        self.assertEqual(
            [(c.id, c.properties) for c in comments], [("1", {"obsidian-sync": {"file": "a.md"}}), ("2", {})]
        )
        self.assertEqual(offsets, [0, 1])

    def test_search_follows_next_page_token(self):
        issue = {"key": "AB-1", "fields": {"status": {"name": "Done"}, "summary": "s", "issuetype": {"name": "Bug"}}}
        pages = iter([{"issues": [issue], "nextPageToken": "t1", "isLast": False}, {"issues": [], "isLast": True}])
        tokens = []

        def fake_request(_method, _path, params):
            tokens.append(params.get("nextPageToken"))
            return response(next(pages))

        self.request.side_effect = fake_request
        issues = self.client.search_issues("project = AB")
        self.assertEqual([(i.key, i.status, i.assignee) for i in issues], [("AB-1", "Done", None)])
        self.assertEqual(tokens, [None, "t1"])


if __name__ == "__main__":
    unittest.main()
