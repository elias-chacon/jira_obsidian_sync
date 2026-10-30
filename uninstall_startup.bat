@echo off
rem Remove o atalho da pasta Inicializar e encerra o sincronizador em execucao (qualquer processo que rode o
rem service.py com o .venv desta pasta). Mantem .venv, .env e service.log.
setlocal
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\JiraObsidianSync.lnk"
if exist "%SHORTCUT%" (
  del "%SHORTCUT%" || exit /b 1
  echo Atalho removido: %SHORTCUT%
) else (
  echo Atalho nao existe. Nada a remover.
)
rem O python.exe/pythonw.exe do venv e um redirecionador que abre o interpretador base como filho; os dois
rem levam o caminho do venv na linha de comando, entao o filtro encontra ambos.
powershell -NoProfile -Command "$venv = '%~dp0.venv\Scripts\python'; $p = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like ('*' + $venv + '*service.py*') }); if ($p.Count) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; 'Processos encerrados: ' + ($p.ProcessId -join ', ') } else { 'Nenhuma instancia em execucao.' }"
echo Mantidos em %~dp0: .venv, .env e service.log. Apague manualmente se nao precisar mais.
endlocal
