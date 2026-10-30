@echo off
rem Registra o sincronizador para iniciar no logon, na sessao do usuario (necessario para a janela de comentario).
rem Remover: uninstall_logon_task.bat
setlocal
cd /d "%~dp0"
rem Um modo de inicio so: o service.lock barra a segunda instancia, mas dois modos instalados confundem.
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\JiraObsidianSync.lnk" (
  echo O atalho de logon da pasta Inicializar ja existe. Remova-o antes com uninstall_startup.bat.
  exit /b 1
)
sc query JiraObsidianSync >nul 2>&1 && (
  echo O servico Windows JiraObsidianSync ja esta instalado. Remova-o antes com uninstall_service.bat.
  exit /b 1
)
if not exist .venv\Scripts\pythonw.exe (
  echo Ambiente .venv ausente. Crie com: py -3 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
schtasks /Create /F /SC ONLOGON /RL LIMITED /TN "JiraObsidianSync" /TR "\"%~dp0.venv\Scripts\pythonw.exe\" \"%~dp0service.py\"" || (
  echo Falha ao criar a tarefa. Se a mensagem for "Acesso negado", execute como Administrador.
  exit /b 1
)
echo Tarefa criada. Para iniciar agora: schtasks /Run /TN JiraObsidianSync
endlocal
