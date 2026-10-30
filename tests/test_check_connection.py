"""Script de verificação de conexão, com Jira e configuração simulados."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import check_connection
from config import ConfigError
from jira_client import JiraError, JiraUser, Transition


class CheckConnectionTest(unittest.TestCase):
    def setUp(self):
        from_env = self.enterContext(patch.object(check_connection.JiraSettings, "from_env"))
        self.jira = from_env.return_value.client.return_value
        self.jira.current_user.return_value = JiraUser("Ana Lima", None)
        self.from_env = from_env

    def main(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = check_connection.main(["check_connection.py", *args])
        return code, output.getvalue()

    def test_authenticates_without_issue(self):
        code, output = self.main()
        self.assertEqual(code, 0)
        self.assertIn("Ana Lima (e-mail oculto)", output)
        self.jira.list_transitions.assert_not_called()

    def test_lists_transitions_of_issue(self):
        self.jira.get_issue_status.return_value = "To Do"
        self.jira.list_transitions.return_value = [Transition("11", "Start", "Em andamento", ())]
        code, output = self.main("AB-1")
        self.assertEqual(code, 0)
        self.assertIn("AB-1 está em 'To Do'", output)
        self.assertIn("Em andamento (transição 'Start', id 11)", output)

    def test_configuration_and_api_errors_return_1(self):
        for error in (ConfigError("Variáveis ausentes"), JiraError("401")):
            with self.subTest(error=error):
                self.from_env.side_effect = error
                code, output = self.main()
                self.assertEqual((code, output.strip()), (1, str(error)))


if __name__ == "__main__":
    unittest.main()
