@echo off
rem Encerra o sincronizador e remove a tarefa de logon JiraObsidianSync do Agendador de Tarefas.
rem Mantem .venv, .env e service.log.
setlocal
schtasks /Query /TN JiraObsidianSync >nul 2>&1 || (
  echo Tarefa JiraObsidianSync nao esta registrada. Nada a remover.
  exit /b 0
)
rem Falha esperada se a tarefa nao estiver em execucao.
schtasks /End /TN JiraObsidianSync >nul 2>&1
schtasks /Delete /TN JiraObsidianSync /F || (
  echo Falha ao remover a tarefa. Se a mensagem for "Acesso negado", execute como Administrador.
  exit /b 1
)
echo Tarefa JiraObsidianSync encerrada e removida.
echo Mantidos em %~dp0: .venv, .env e service.log. Apague manualmente se nao precisar mais.
endlocal
