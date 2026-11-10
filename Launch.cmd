@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 full_world.py %*
) else (
    python full_world.py %*
)
if errorlevel 1 pause
endlocal
