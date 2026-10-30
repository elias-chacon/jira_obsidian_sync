@echo off
rem Instala e inicia o servico Windows JiraObsidianSync (sem janela de comentario). Exige Administrador.
rem Remover: uninstall_service.bat
setlocal
cd /d "%~dp0"
net session >nul 2>&1 || (
  echo Execute este script em um terminal como Administrador.
  exit /b 1
)
rem Um modo de inicio so: o service.lock barra a segunda instancia, mas dois modos instalados confundem.
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\JiraObsidianSync.lnk" (
  echo O atalho de logon da pasta Inicializar ja existe. Remova-o antes com uninstall_startup.bat.
  exit /b 1
)
schtasks /Query /TN JiraObsidianSync >nul 2>&1 && (
  echo A tarefa de logon JiraObsidianSync ja esta registrada. Remova-a antes com uninstall_logon_task.bat.
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv || exit /b 1
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt || exit /b 1
if not exist .env (
  copy .env.example .env
  echo Configure .env e rode novamente.
  exit /b 2
)
.venv\Scripts\python.exe windows_service.py install --startup auto
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe windows_service.py start
endlocal
