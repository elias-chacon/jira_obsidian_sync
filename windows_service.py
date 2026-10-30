"""Hospedagem como serviço Windows (pywin32).

Uso: python windows_service.py install|start|stop|restart|remove|update|debug

Serviços rodam na sessão 0, sem área de trabalho: a janela de comentário fica desativada. Para tê-la,
use install_logon_task.bat, que roda service.py na sessão do usuário.
"""
from __future__ import annotations

import logging

import servicemanager
import win32event
import win32service
import win32serviceutil

from service import build_service, configure_logging

LOG = logging.getLogger(__name__)


class JiraObsidianWindowsService(win32serviceutil.ServiceFramework):
    """Serviço `JiraObsidianSync`; nomes `Svc*` são exigidos pelo pywin32."""

    _svc_name_ = "JiraObsidianSync"
    _svc_display_name_ = "Jira Obsidian Kanban Sync"
    _svc_description_ = "Sincroniza movimentos do Kanban Obsidian com status do Jira."

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.sync = None

    def SvcStop(self):  # pylint: disable=invalid-name
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        if self.sync:
            self.sync.stop()

    def SvcDoRun(self):  # pylint: disable=invalid-name
        """Inicia a sincronização e bloqueia até SvcStop."""
        configure_logging()
        servicemanager.LogInfoMsg("Jira Obsidian Sync iniciando")
        try:
            self.sync = build_service(interactive=False)
            self.sync.start()
        except Exception:
            # Sem isto a falha só apareceria no Visualizador de Eventos, não em service.log.
            LOG.exception("Falha ao iniciar o serviço")
            servicemanager.LogErrorMsg("Jira Obsidian Sync falhou ao iniciar; veja service.log")
            raise
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)


def handle_command_line() -> None:
    win32serviceutil.HandleCommandLine(JiraObsidianWindowsService)


if __name__ == "__main__":
    handle_command_line()
