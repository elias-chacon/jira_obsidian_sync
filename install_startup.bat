@echo off
rem Inicia o sincronizador no logon pela pasta Inicializar do usuario (shell:startup). Nao exige Administrador.
rem Roda na sessao do usuario, entao a janela de comentario funciona. Remover: uninstall_startup.bat
setlocal
cd /d "%~dp0"
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\JiraObsidianSync.lnk"
rem Um modo de inicio so: o service.lock barra a segunda instancia, mas dois modos instalados confundem.
sc query JiraObsidianSync >nul 2>&1 && (
  echo O servico Windows JiraObsidianSync ja esta instalado. Remova-o antes com uninstall_service.bat.
  exit /b 1
)
schtasks /Query /TN JiraObsidianSync >nul 2>&1 && (
  echo A tarefa de logon JiraObsidianSync ja esta registrada. Remova-a antes com uninstall_logon_task.bat.
  exit /b 1
)
if not exist .venv\Scripts\pythonw.exe (
  echo Ambiente .venv ausente. Crie com: py -3 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SHORTCUT); $s.TargetPath = '%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments = '\"%~dp0service.py\"'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'Jira Obsidian Sync'; $s.Save()" || (
  echo Falha ao criar o atalho em %SHORTCUT%
  exit /b 1
)
echo Atalho criado: %SHORTCUT%
echo O sincronizador sobe no proximo logon. Para iniciar agora: start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0service.py"
endlocal
