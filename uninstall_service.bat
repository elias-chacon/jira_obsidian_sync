@echo off
rem Para e remove o servico Windows JiraObsidianSync. Exige terminal como Administrador.
rem Usa sc.exe (nao o .venv), para funcionar mesmo com o ambiente Python ausente ou quebrado.
rem Mantem .venv, .env e service.log.
setlocal
net session >nul 2>&1 || (
  echo Execute este script em um terminal como Administrador.
  exit /b 1
)
sc query JiraObsidianSync >nul 2>&1 || (
  echo Servico JiraObsidianSync nao esta instalado. Nada a remover.
  exit /b 0
)
rem Falha esperada se o servico ja estiver parado.
sc stop JiraObsidianSync >nul 2>&1
rem Com o servico ainda parando, o Windows conclui a remocao assim que ele terminar.
sc delete JiraObsidianSync || exit /b 1
echo Servico JiraObsidianSync removido.
echo Mantidos em %~dp0: .venv, .env e service.log. Apague manualmente se nao precisar mais.
endlocal
